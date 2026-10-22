"""Core simulation and telemetry engine with generalized topology and live decision tracking."""
import csv
import io
import json
import math
import random
import threading
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from .model import Predictor, WINDOW, HORIZON, THRESHOLD
from .routing import choose, shortest_path
from .topologies import get_topology, key, TOPOLOGIES, find_all_paths

class Engine:
    def __init__(self, root: Path, source: str = 'simulation', seed: int = 42, topology: str = 'diamond'):
        self.root = Path(root)
        self.source = source
        self.lock = threading.RLock()
        self.seed = seed
        self.model = Predictor(self.root / 'data/model.json')
        self.running = False
        self.mode = 'predictive'
        self.scenario = 'ramp'
        self.topology_name = topology
        self.foreground_mbps = 4.0
        self.custom_capacity = 10.0
        self.duration_seconds: Optional[int] = 120
        self.reset()

    def reset(self):
        """Reset all metrics, history, series, and topology state."""
        with self.lock:
            self.tick = 0
            self.topology = get_topology(self.topology_name)
            self.ingress_switch = self.topology['ingress_switch']
            self.egress_switch = self.topology['egress_switch']
            self.links_def = self.topology['links']
            self.bottleneck_link = self.topology['bottleneck_link']
            
            # Initial route is the static shortest path by base propagation delay
            initial_route, _ = shortest_path({}, start=self.ingress_switch, end=self.egress_switch, links=self.links_def)
            self.route = initial_route
            self.applied_route = [] if self.source == 'mininet' else self.route[:]
            
            self.last_change = -100
            self.events = deque(maxlen=100)
            self.history = deque(maxlen=240)
            self.series = {key(a, b): deque(maxlen=WINDOW) for a, b, _, _ in self.links_def}
            self.samples = []
            self.last_seen = None
            self.controller_seen = None
            self.rng = random.Random(self.seed)
            self.metrics = {
                'latency_ms': None,
                'loss_percent': None,
                'throughput_mbps': None,
                'jitter_ms': None
            }
            self.traffic_mbps = 0.0
            self.session = str(int(time.time() * 1000))
            self.probes = []
            self.last_decision = {
                'tick': 0,
                'mode': self.mode,
                'current': self.route,
                'target': self.route,
                'target_cost': 0.0,
                'current_cost': 0.0,
                'cooldown_ticks_remaining': 0,
                'reason': 'Initial path selected',
                'explanation': f"Initial route {' → '.join(self.route).upper()} selected by base propagation delay.",
                'route_changed': False,
            }
            
            # Populate link states immediately so UI can render topology before step 1
            self.links = {}
            for a, b, cap, delay in self.links_def:
                k = key(a, b)
                self.links[k] = {
                    'id': k,
                    'source': a,
                    'target': b,
                    'capacity_mbps': self.custom_capacity or cap,
                    'base_delay_ms': delay,
                    'offered_mbps': 0.0,
                    'tx_mbps': 0.0,
                    'offered_load': 0.0,
                    'utilization': 0.0,
                    'forecast': None,
                    'risk': None,
                    'prediction_status': 'warming up (0/10 samples)' if self.model.ready else 'untrained'
                }

    def configure(self, mode: Optional[str] = None, scenario: Optional[str] = None,
                  topology: Optional[str] = None, foreground_mbps: Optional[float] = None,
                  link_capacity: Optional[float] = None, duration: Optional[int] = None):
        """Update runtime configuration with backend validation."""
        with self.lock:
            if mode is not None:
                if mode not in ['static', 'reactive', 'predictive']:
                    raise ValueError(f"Invalid routing mode '{mode}'. Expected: static, reactive, predictive.")
                self.mode = mode
                
            if scenario is not None:
                if scenario not in ['normal', 'ramp', 'burst', 'heavy']:
                    raise ValueError(f"Invalid scenario '{scenario}'. Expected: normal, ramp, burst, heavy.")
                self.scenario = scenario
                
            if topology is not None:
                if topology not in TOPOLOGIES:
                    raise ValueError(f"Unknown topology '{topology}'. Expected: {list(TOPOLOGIES.keys())}.")
                if self.running and topology != self.topology_name:
                    raise ValueError("Cannot change topology while experiment is running. Please pause or reset first.")
                if topology != self.topology_name:
                    self.topology_name = topology
                    self.reset()
                    
            if foreground_mbps is not None:
                val = float(foreground_mbps)
                if not (0.1 <= val <= 100.0):
                    raise ValueError("Foreground traffic must be between 0.1 and 100.0 Mbps.")
                self.foreground_mbps = val
                
            if link_capacity is not None:
                cap = float(link_capacity)
                if not (1.0 <= cap <= 1000.0):
                    raise ValueError("Link capacity must be between 1.0 and 1000.0 Mbps.")
                self.custom_capacity = cap
                for k in self.links:
                    self.links[k]['capacity_mbps'] = cap
                    
            if duration is not None:
                if duration == 0:
                    self.duration_seconds = None
                else:
                    d = int(duration)
                    if d < 5:
                        raise ValueError("Experiment duration must be at least 5 seconds (or 0 for unlimited).")
                    self.duration_seconds = d

    def demand(self, t: int) -> float:
        """Compute time-varying background demand in Mbps."""
        if self.scenario == 'normal':
            return 2.0 + 0.4 * math.sin(t / 7.0)
        if self.scenario == 'ramp':
            # Ramps smoothly from 1.0 to 8.8 Mbps, stays heavy, then cools down
            return min(8.8, 1.0 + max(0, t - 12) * 0.22) if t < 85 else max(1.0, 8.8 - (t - 85) * 0.15)
        if self.scenario == 'burst':
            # Periodic bursts
            return 9.2 if 20 <= (t % 65) < 42 else 1.5
        # Heavy load
        return 8.8

    def process(self, values: Dict[str, Dict[str, Any]]):
        """Process link utilization telemetry and run predictor and routing logic."""
        self.tick += 1
        now = time.time()
        self.last_seen = now
        
        for a, b, cap, delay in self.links_def:
            k = key(a, b)
            m = dict(values.get(k, {'utilization': 0.0, 'tx_mbps': 0.0, 'offered_mbps': 0.0, 'offered_load': 0.0}))
            u = float(m.get('utilization', 0.0))
            self.series[k].append(u)
            
            prediction = self.model.predict(list(self.series[k]))
            capacity = self.custom_capacity or cap
            m.update({
                'id': k,
                'source': a,
                'target': b,
                'capacity_mbps': capacity,
                'base_delay_ms': delay,
                'forecast': prediction['forecast'],
                'risk': prediction['risk'],
                'prediction_status': prediction['status'],
                'samples_collected': prediction.get('samples_collected', len(self.series[k])),
                'samples_required': WINDOW,
            })
            self.links[k] = m
            self.samples.append({
                'session': self.session,
                'source': self.source,
                'topology': self.topology_name,
                'mode': self.mode,
                'scenario': self.scenario,
                'tick': self.tick,
                'time': now,
                'link': k,
                'offered_mbps': m.get('offered_mbps', 0.0),
                'tx_mbps': m.get('tx_mbps', 0.0),
                'utilization': u,
                'offered_load': m.get('offered_load', 0.0),
                'forecast': prediction['forecast'],
                'risk': prediction['risk']
            })

        target, reason, details = choose(
            self.mode, self.links, self.route, self.tick, self.last_change,
            topology=self.topology, start=self.ingress_switch, end=self.egress_switch
        )
        self.last_decision = details
        
        if target != self.route:
            self.events.appendleft({
                'tick': self.tick,
                'old': self.route[:],
                'new': target[:],
                'reason': reason,
                'details': details.get('explanation', ''),
                'status': 'applied in simulation' if self.source == 'simulation' else 'requested; awaiting controller barrier'
            })
            self.route = target
            self.last_change = self.tick
            
        self.history.append({
            'tick': self.tick,
            **self.metrics,
            'max_utilization': max((m['utilization'] for m in self.links.values()), default=0.0),
            'max_offered_load': max((m.get('offered_load', 0.0) for m in self.links.values()), default=0.0)
        })
        
        # Stop if configured duration has been reached
        if self.duration_seconds and self.tick >= self.duration_seconds:
            self.running = False

    def step(self):
        """Execute one simulation cycle."""
        with self.lock:
            if self.source != 'simulation':
                return
            background = self.demand(self.tick)
            foreground = self.foreground_mbps
            self.traffic_mbps = round(background + foreground, 2)
            
            values = {}
            active_links = set(key(a, b) for a, b in zip(self.route, self.route[1:]))
            
            for a, b, cap, delay in self.links_def:
                k = key(a, b)
                capacity = self.custom_capacity or cap
                
                # Bottleneck link carries full background traffic; other links have minimal baseline background
                offered_bg = background if k == self.bottleneck_link else 0.25
                offered_fg = foreground if k in active_links else 0.0
                total_offered = offered_bg + offered_fg
                
                # Transmitted rate cannot exceed link capacity
                tx = min(capacity, total_offered)
                offered_load = total_offered / max(1e-6, capacity)
                
                # Transmitted utilization is bounded at 1.0 (with slight measurement noise)
                base_u = tx / max(1e-6, capacity)
                noise = self.rng.uniform(-0.005, 0.005)
                measured_u = max(0.0, min(1.0, base_u + noise))
                
                values[k] = {
                    'utilization': round(measured_u, 4),
                    'offered_mbps': round(total_offered, 2),
                    'tx_mbps': round(tx, 2),
                    'offered_load': round(offered_load, 4),
                }
                
            # Quality of Service modeling on the active forwarding path
            worst_offered_load = max((values[k]['offered_load'] for k in active_links), default=0.0)
            
            # Loss occurs when offered load overwhelms buffer / capacity (offered_load > 1.0)
            loss_percent = max(0.0, (1.0 - 1.0 / max(1.0, worst_offered_load))) * 100.0
            throughput = round(foreground * (1.0 - loss_percent / 100.0), 3)
            
            # Latency is propagation delay + queuing delay under heavy load
            active_delays = [d for a, b, _, d in self.links_def if key(a, b) in active_links]
            base_propagation_ms = 2.0 * sum(active_delays)  # Round-trip base delay
            queuing_delay_ms = max(0.0, worst_offered_load - 0.70) * 110.0
            latency = round(base_propagation_ms + queuing_delay_ms, 2)
            jitter = round(max(0.0, worst_offered_load - 0.70) * 14.0, 3)
            
            self.metrics = {
                'latency_ms': latency,
                'loss_percent': round(loss_percent, 2),
                'throughput_mbps': throughput,
                'jitter_ms': jitter
            }
            
            self.process(values)
            self.applied_route = self.route[:]

    def ingest(self, data: Dict[str, Any]):
        """Ingest OpenFlow port telemetry from Mininet."""
        with self.lock:
            if self.source != 'mininet':
                raise ValueError('Telemetry ingestion requires mininet source')
            values = data.get('links', {})
            expected = {key(a, b) for a, b, _, _ in self.links_def}
            if set(values) != expected:
                raise ValueError(f"Telemetry missing links for active topology. Expected: {expected}")
            for m in values.values():
                u = m.get('utilization')
                if not isinstance(u, (int, float)) or not math.isfinite(u) or not (0 <= u <= 10):
                    raise ValueError('Invalid utilization measurement')
            self.process(values)

    def acknowledge(self, route: List[str]):
        """Acknowledge route application confirmed by OpenFlow barrier messages."""
        with self.lock:
            all_valid = find_all_paths(self.topology)
            if route not in all_valid:
                raise ValueError(f"Invalid applied route {route} for topology {self.topology_name}")
            self.applied_route = route
            self.controller_seen = time.time()
            for event in self.events:
                if event['new'] == route and event['status'].startswith('requested'):
                    event['status'] = 'confirmed by OpenFlow barriers'
                    break

    def probe(self, data: Dict[str, Any]):
        """Store measured end-to-end probes (ping / iperf3)."""
        with self.lock:
            clean = {}
            for name in self.metrics:
                v = data.get(name)
                if v is not None and (not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0):
                    raise ValueError(f"Invalid probe metric for {name}")
                clean[name] = v
            self.metrics = clean
            self.probes.append({'tick': self.tick, **clean})

    def determine_status_state(self) -> Tuple[str, str, str]:
        """Determine backend state, short title, and live explanation for the 'What is happening now?' panel."""
        if self.source == 'mininet':
            age = None if self.last_seen is None else time.time() - self.last_seen
            if age is None or age > 5:
                return (
                    'telemetry_stale',
                    'Telemetry disconnected or stale',
                    f"No telemetry received from Mininet in {round(age or 0, 1)}s. Ensure sdn/topology.py is running on Linux."
                )
            if self.applied_route != self.route:
                return (
                    'route_change_requested',
                    'Route change requested',
                    f"Rerouting to {' → '.join(self.route).upper()} requested; waiting for OpenFlow barrier acknowledgment."
                )
            if self.events and self.events[0]['status'].startswith('confirmed'):
                return (
                    'route_change_confirmed',
                    'Route change confirmed',
                    f"Controller confirmed route {' → '.join(self.applied_route).upper()} via OpenFlow barriers."
                )
            return (
                'generating_traffic',
                'Mininet packet forwarding active',
                f"Live OpenFlow counters polling link utilization. Active route: {' → '.join(self.applied_route).upper()}."
            )
            
        # Simulation source logic
        if self.tick == 0 and not self.running:
            return (
                'not_started',
                'Experiment not started',
                'Click "Start experiment" or "Start guided demo" to begin packet forwarding and live forecasting.'
            )
        if not self.running:
            if self.duration_seconds and self.tick >= self.duration_seconds:
                return (
                    'duration_complete',
                    'Experiment duration reached',
                    f"Experiment completed {self.tick}s run. Click Reset to configure a new test or Run Comparison to evaluate modes."
                )
            return (
                'paused',
                'Experiment paused',
                f"Simulation paused at t={self.tick}s. Click Resume to continue packet transmission."
            )
            
        warmup_obs = min((len(s) for s in self.series.values()), default=0)
        if warmup_obs < WINDOW:
            return (
                'warming_up',
                f"Model collecting observations: {warmup_obs} of {WINDOW}",
                f"Collecting initial sliding window ({warmup_obs}/{WINDOW} observations). Model begins 5-second forecasts once 10 samples are logged."
            )
            
        # Check active path congestion
        active_links = [key(a, b) for a, b in zip(self.route, self.route[1:])]
        max_active_risk = max((self.links[k].get('risk') or 0.0 for k in active_links), default=0.0)
        max_active_u = max((self.links[k].get('utilization') or 0.0 for k in active_links), default=0.0)
        
        # Check if route change just occurred
        if self.events and self.events[0]['tick'] == self.tick:
            return (
                'route_change_confirmed',
                f"Route changed to {' → '.join(self.route).upper()}",
                self.events[0].get('details', self.last_decision.get('explanation', 'Route change applied.'))
            )
            
        if self.last_decision.get('candidate_target') != self.route and (max_active_risk >= 0.5 or max_active_u >= 0.75):
            candidate = self.last_decision.get('candidate_target', [])
            cand_str = ' → '.join(candidate).upper()
            if self.last_decision.get('cooldown_ticks_remaining', 0) > 0:
                return (
                    'alternative_evaluated_cooldown',
                    'Alternative path evaluated (cooldown)',
                    f"Alternative path {cand_str} evaluated, but held by cooldown ({self.last_decision['cooldown_ticks_remaining']}s left) to avoid route oscillation."
                )
            return (
                'alternative_evaluated_hysteresis',
                'Alternative path evaluated (hysteresis)',
                f"Alternative path {cand_str} evaluated, but cost reduction is below the 15% hysteresis threshold. Route remains on current path."
            )
            
        if max_active_risk >= 0.6:
            return (
                'congestion_risk_increasing',
                'Congestion risk increasing',
                f"Model predicts elevated congestion risk ({round(max_active_risk * 100)}%) on current path. Link intelligence active."
            )
            
        return (
            'forecast_available',
            'Traffic steady • Forecast ready',
            f"Network load within normal limits. Predictor forecasting 5 seconds ahead. Path: {' → '.join(self.route).upper()}."
        )

    def state(self) -> Dict[str, Any]:
        """Produce complete snapshot of network state for the API and dashboard."""
        with self.lock:
            age = None if self.last_seen is None else round(time.time() - self.last_seen, 1)
            state_key, status_title, status_detail = self.determine_status_state()
            warmup_obs = min((len(s) for s in self.series.values()), default=0)
            
            return {
                'source': self.source,
                'running': self.running,
                'mode': self.mode,
                'scenario': self.scenario,
                'topology': self.topology_name,
                'topology_meta': {
                    'name': self.topology['name'],
                    'description': self.topology['description'],
                    'mininet_verified': self.topology['mininet_verified'],
                    'verification_notice': self.topology['verification_notice'],
                    'switches': self.topology['switches'],
                    'hosts': self.topology['hosts'],
                    'foreground_pair': self.topology['foreground_pair'],
                    'background_pair': self.topology['background_pair'],
                    'bottleneck_link': self.topology['bottleneck_link'],
                    'links': [
                        {'source': a, 'target': b, 'capacity_mbps': self.custom_capacity or cap, 'delay_ms': d, 'id': key(a, b)}
                        for a, b, cap, d in self.links_def
                    ],
                    'layout': self.topology['layout'],
                },
                'tick': self.tick,
                'duration_seconds': self.duration_seconds,
                'foreground_mbps': self.foreground_mbps,
                'traffic_mbps': self.traffic_mbps,
                'route': self.route[:],
                'applied_route': self.applied_route[:],
                'links': list(self.links.values()),
                'metrics': self.metrics.copy(),
                'history': list(self.history),
                'events': list(self.events),
                'last_decision': self.last_decision,
                'status_state': state_key,
                'status_title': status_title,
                'status_detail': status_detail,
                'warmup_progress': {
                    'current': warmup_obs,
                    'required': WINDOW,
                    'percent': min(100, int(warmup_obs * 100 / WINDOW)),
                    'ready': warmup_obs >= WINDOW,
                },
                'horizon_info': {
                    'horizon_samples': HORIZON,
                    'sample_interval_seconds': 1,
                    'horizon_seconds': HORIZON,
                    'label': 'Predicting 5 seconds ahead (5 samples at 1s intervals)',
                },
                'telemetry_age_seconds': age,
                'stale': self.source == 'mininet' and (age is None or age > 5),
                'controller_age_seconds': None if self.controller_seen is None else round(time.time() - self.controller_seen, 1),
                'model': self.model.metadata,
                'metric_provenance': 'analytical simulation' if self.source == 'simulation' else 'iperf3/ping probes; unavailable metrics are null'
            }

    def csv_text(self) -> str:
        """Export raw telemetry samples in CSV format with full metadata."""
        with self.lock:
            out = io.StringIO()
            fields = ['session', 'source', 'topology', 'mode', 'scenario', 'tick', 'time',
                      'link', 'offered_mbps', 'tx_mbps', 'utilization', 'offered_load', 'forecast', 'risk']
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.samples)
            return out.getvalue()

    def archive(self) -> str:
        """Save run snapshot to disk with UTF-8 encoding."""
        with self.lock:
            folder = self.root / 'data/runs'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{self.session}.json"
            content = json.dumps({'state': self.state(), 'samples': self.samples, 'probes': self.probes}, indent=2)
            path.write_text(content, encoding='utf-8')
            return path.name

    def run_comparison(self, duration: int = 60, seed: int = 42,
                       scenario: Optional[str] = None, topology: Optional[str] = None) -> Dict[str, Any]:
        """Execute a fair, deterministic comparison of static, reactive, and predictive modes."""
        scen = scenario or self.scenario
        topo = topology or self.topology_name
        modes = ['static', 'reactive', 'predictive']
        results = {}
        
        for m in modes:
            e = Engine(self.root, source='simulation', seed=seed, topology=topo)
            e.configure(mode=m, scenario=scen, foreground_mbps=self.foreground_mbps,
                        link_capacity=self.custom_capacity, duration=duration)
            e.running = True
            for _ in range(duration):
                e.step()
                
            h = list(e.history)
            n = len(h) if h else 1
            latencies = [x['latency_ms'] for x in h if x.get('latency_ms') is not None]
            throughputs = [x['throughput_mbps'] for x in h if x.get('throughput_mbps') is not None]
            losses = [x['loss_percent'] for x in h if x.get('loss_percent') is not None]
            
            results[m] = {
                'mode': m,
                'mean_latency_ms': round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
                'mean_throughput_mbps': round(sum(throughputs) / len(throughputs), 2) if throughputs else 0.0,
                'mean_loss_percent': round(sum(losses) / len(losses), 2) if losses else 0.0,
                'route_changes': len(e.events),
                'congested_samples': sum(1 for x in h if x.get('max_utilization', 0.0) >= THRESHOLD),
                'total_ticks': e.tick,
                'timeseries': [
                    {
                        'tick': row['tick'],
                        'latency_ms': row.get('latency_ms'),
                        'throughput_mbps': row.get('throughput_mbps'),
                        'loss_percent': row.get('loss_percent'),
                        'max_utilization': row.get('max_utilization'),
                    }
                    for row in h
                ]
            }
            
        return {
            'source': 'analytical simulation',
            'topology': topo,
            'scenario': scen,
            'duration_seconds': duration,
            'seed': seed,
            'foreground_mbps': self.foreground_mbps,
            'results': results,
            'timestamp': time.time(),
        }
