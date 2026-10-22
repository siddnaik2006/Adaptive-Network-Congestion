"""Comprehensive verification suite for Adaptive CN.

Covers:
- UTF-8 decoding & Windows encoding checks
- Generalized topologies (diamond, six_switch, eight_mesh)
- Dijkstra shortest path & path enumeration
- Ridge autoregressive model training, warmup, and prediction
- Dynamic routing decision logic, cooldown, and hysteresis
- Offered load vs transmitted capacity capping
- State transitions, 'What is happening now?' states
- Input validation & safety during active execution
- Fair comparison execution & reproducibility
- OpenFlow 1.3 FlowMod layout, handshake, barrier, echo, and stats
- HTTP REST API endpoints and UTF-8 charset validation
"""
import io
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cn.engine import Engine
from cn.model import Predictor, train, synthetic_sequences, WINDOW, HORIZON, THRESHOLD
from cn.routing import shortest_path, choose
from cn.topologies import get_topology, list_topologies, validate_topology, find_all_paths, TOPOLOGIES
from sdn.controller import Controller, Switch, message, flow_body, read_exact

class ProjectTests(unittest.TestCase):

    def test_dijkstra(self):
        """Verify Dijkstra shortest path finds optimal routes under empty and congested costs."""
        self.assertEqual(shortest_path({})[0], ['s1', 's2', 's4'])
        self.assertEqual(shortest_path({'s1-s2': 100, 's2-s4': 100})[0], ['s1', 's3', 's4'])

    def test_topologies_validity_and_connectivity(self):
        """Verify all presets are connected, have valid port mappings, and find acyclic paths."""
        presets = ['diamond', 'six_switch', 'eight_mesh']
        self.assertEqual(len(list_topologies()), 3)
        for name in presets:
            topo = get_topology(name)
            self.assertTrue(validate_topology(topo))
            paths = find_all_paths(topo)
            self.assertGreater(len(paths), 1)
            # Check shortest path from ingress to egress
            path, cost = shortest_path({}, start=topo['ingress_switch'], end=topo['egress_switch'], links=topo['links'])
            self.assertEqual(path[0], topo['ingress_switch'])
            self.assertEqual(path[-1], topo['egress_switch'])
            self.assertGreater(cost, 0)

    def test_windows_utf8_file_reads(self):
        """Verify that web source files are valid UTF-8 and contain no cp1252 corruption patterns."""
        for filename in ['index.html', 'app.js', 'style.css']:
            content = (ROOT / 'web' / filename).read_text(encoding='utf-8')
            for bad_str in ['â€™', 'â€', 'Â', 'Ã', 'â†']:
                self.assertNotIn(bad_str, content, f"Found corrupted sequence '{bad_str}' in web/{filename}")
            # Ensure proper symbols exist
            if filename == 'index.html':
                self.assertIn('charset="utf-8"', content)
                self.assertIn('ADAPTIVE', content)

    def test_model_training_and_warmup(self):
        """Verify Ridge AR training produces valid weights, residuals, and holdout metadata."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'model.json'
            meta = train(synthetic_sequences(count=12), path, 'test synthetic')
            model = Predictor(path)
            # Before WINDOW samples, status is warming up and risk is None
            self.assertIsNone(model.predict([0.5] * 3)['risk'])
            self.assertEqual(model.predict([0.5] * 3)['status'], 'warming up (3/10 samples)')
            # At WINDOW samples, forecast and risk are computed
            result = model.predict([0.9] * 10)
            self.assertTrue(0 <= result['risk'] <= 1)
            self.assertEqual(result['status'], 'ready')
            self.assertGreater(meta['test_samples'], 0)
            self.assertIn('rmse', meta)
            self.assertIn('f1', meta)

    def test_reroute_and_cooldown(self):
        """Verify predictive mode reroutes upon congestion and respects 10s cooldown."""
        e = Engine(ROOT)
        e.configure(mode='predictive', scenario='ramp')
        for _ in range(80):
            e.step()
        self.assertTrue(e.events)
        self.assertEqual(e.applied_route, ['s1', 's3', 's4'])
        events = list(reversed(e.events))
        self.assertTrue(all(b['tick'] - a['tick'] >= 10 for a, b in zip(events, events[1:])))

    def test_static_never_changes(self):
        """Verify static routing never reroutes even under heavy continuous congestion."""
        e = Engine(ROOT)
        e.configure(mode='static', scenario='heavy')
        for _ in range(60):
            e.step()
        self.assertFalse(e.events)
        self.assertEqual(e.route, ['s1', 's2', 's4'])

    def test_offered_load_vs_transmitted_capacity(self):
        """Verify offered load can exceed 100% while tx_mbps is capped at link capacity."""
        e = Engine(ROOT)
        e.configure(mode='static', scenario='heavy', foreground_mbps=4.0, link_capacity=10.0)
        for _ in range(15):
            e.step()
        bottleneck = e.links['s2-s4']
        self.assertGreater(bottleneck['offered_mbps'], 10.0)
        self.assertGreater(bottleneck['offered_load'], 1.0)
        self.assertLessEqual(bottleneck['tx_mbps'], 10.0)
        self.assertLessEqual(bottleneck['utilization'], 1.0)
        self.assertGreater(e.metrics['loss_percent'], 0.0)

    def test_input_validation(self):
        """Verify backend input validation for modes, scenarios, rates, and active topology locks."""
        e = Engine(ROOT)
        with self.assertRaises(ValueError):
            e.configure(mode='bogus')
        with self.assertRaises(ValueError):
            e.configure(scenario='bogus')
        with self.assertRaises(ValueError):
            e.configure(topology='nonexistent')
        with self.assertRaises(ValueError):
            e.configure(foreground_mbps=-5)
        with self.assertRaises(ValueError):
            e.configure(link_capacity=0)
        
        # Changing topology while running must be rejected
        e.running = True
        with self.assertRaises(ValueError):
            e.configure(topology='six_switch')
        e.running = False
        e.configure(topology='six_switch')
        self.assertEqual(e.topology_name, 'six_switch')

    def test_reset_clears_stale_state(self):
        """Verify reset clears history, events, and renders fresh zero-load link states."""
        e = Engine(ROOT)
        e.configure(mode='predictive', scenario='ramp')
        for _ in range(30):
            e.step()
        self.assertGreater(e.tick, 0)
        self.assertTrue(len(e.history) > 0)
        
        e.reset()
        self.assertEqual(e.tick, 0)
        self.assertEqual(len(e.history), 0)
        self.assertEqual(len(e.events), 0)
        self.assertFalse(e.running)
        self.assertEqual(e.determine_status_state()[0], 'not_started')
        for l in e.links.values():
            self.assertEqual(l['utilization'], 0.0)
            self.assertEqual(l['tx_mbps'], 0.0)
            self.assertIsNone(l['forecast'])

    def test_warmup_and_live_states(self):
        """Verify step-by-step state progression from not_started, warming_up, to forecast active."""
        e = Engine(ROOT)
        self.assertEqual(e.determine_status_state()[0], 'not_started')
        e.running = True
        e.step()
        self.assertEqual(e.determine_status_state()[0], 'warming_up')
        state = e.state()
        self.assertEqual(state['warmup_progress']['current'], 1)
        self.assertFalse(state['warmup_progress']['ready'])
        
        for _ in range(9):
            e.step()
        self.assertTrue(e.state()['warmup_progress']['ready'])
        self.assertNotEqual(e.determine_status_state()[0], 'warming_up')

    def test_fair_comparison_runner(self):
        """Verify comparison runner executes all 3 modes deterministically with identical parameters."""
        e = Engine(ROOT)
        res1 = e.run_comparison(duration=25, seed=42, scenario='ramp')
        res2 = e.run_comparison(duration=25, seed=42, scenario='ramp')
        self.assertEqual(set(res1['results'].keys()), {'static', 'reactive', 'predictive'})
        # Deterministic match
        self.assertEqual(res1['results']['static']['mean_latency_ms'], res2['results']['static']['mean_latency_ms'])
        self.assertEqual(res1['results']['predictive']['mean_throughput_mbps'], res2['results']['predictive']['mean_throughput_mbps'])

    def test_telemetry_validation(self):
        """Verify Mininet telemetry validation requires all links for the active topology."""
        e = Engine(ROOT, source='mininet')
        with self.assertRaises(ValueError):
            e.ingest({'links': {}})
        self.assertTrue(e.state()['stale'])
        self.assertIsNone(e.metrics['throughput_mbps'])

    def test_flowmod_wire_layout(self):
        """Verify binary wire format of OpenFlow 1.3 FlowMod message."""
        body = flow_body('10.0.0.2', 2)
        self.assertEqual(len(body), 88)
        self.assertEqual(struct.unpack_from('!H', body, 22)[0], 100)
        self.assertEqual(struct.unpack_from('!HH', body, 40), (1, 18))
        self.assertEqual(struct.unpack_from('!HH', body, 64), (4, 24))
        self.assertEqual(struct.unpack_from('!I', body, 76)[0], 2)

    def test_switch_handshake_barrier_stats_and_echo(self):
        """Verify OpenFlow 1.3 switch handshake, barrier acknowledgment, and port stats parsing."""
        left, right = socket.socketpair()
        controller = Controller('unused', 'token')
        switch = Switch(left, controller)
        worker = threading.Thread(target=switch.run, daemon=True)
        worker.start()

        def receive():
            _, kind, n, xid = struct.unpack('!BBHI', read_exact(right, 8))
            return kind, xid, read_exact(right, n - 8)

        self.assertEqual(receive()[0], 0)  # OFPT_HELLO
        self.assertEqual(receive()[0], 5)  # OFPT_FEATURES_REQUEST
        right.sendall(message(6, 2, struct.pack('!QIBB2xII', 1, 256, 1, 0, 0, 0)))
        self.assertEqual(receive()[0], 9)  # OFPT_SET_CONFIG
        
        barrier_error = []
        def barrier():
            try:
                switch.barrier()
            except Exception as exc:
                barrier_error.append(exc)
        thread = threading.Thread(target=barrier)
        thread.start()
        kind, xid, _ = receive()
        self.assertEqual(kind, 20)  # OFPT_BARRIER_REQUEST
        right.sendall(message(21, xid))  # OFPT_BARRIER_REPLY
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertFalse(barrier_error)

        stats = struct.pack('!I4xQQQQQQQQQQQQII', 2, 100, 101, 10000, 1250000, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0)
        right.sendall(message(19, 8, struct.pack('!HH4x', 4, 0) + stats))
        right.sendall(message(2, 12, b'ping'))
        kind, xid, body = receive()
        self.assertEqual((kind, xid, body), (3, 12, b'ping'))
        self.assertEqual(switch.stats[2][1], 1250000)
        right.close()
        worker.join(2)

    def test_http_end_to_end_and_utf8_serving(self):
        """Verify HTTP server startup, REST endpoints, UTF-8 charset headers, and comparisons API."""
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()
        
        env = os.environ.copy()
        env['CN_AGENT_TOKEN'] = 'integration-test-token'
        process = subprocess.Popen(
            [sys.executable, '-m', 'cn.server', '--source', 'mininet', '--port', str(port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL
        )
        base = f"http://127.0.0.1:{port}"

        def request(path, data=None, auth=False):
            headers = {'Content-Type': 'application/json; charset=utf-8'}
            if auth:
                headers['Authorization'] = 'Bearer integration-test-token'
            payload = None if data is None else json.dumps(data).encode('utf-8')
            req = urllib.request.Request(base + path, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.info().get('Content-Type'), r.read()

        try:
            for _ in range(40):
                try:
                    request('/api/state')
                    break
                except OSError:
                    time.sleep(0.1)

            # Test UTF-8 charset headers and content
            ct_html, body_html = request('/')
            self.assertIn('charset=utf-8', ct_html)
            self.assertIn(b'ADAPTIVE', body_html)
            self.assertIn(b'utf-8', body_html.lower())

            ct_js, body_js = request('/app.js')
            self.assertIn('charset=utf-8', ct_js)
            self.assertIn(b'function render', body_js)

            # Test authentication requirement on controller route
            with self.assertRaises(urllib.error.HTTPError) as error:
                request('/api/controller/route')
            self.assertEqual(error.exception.code, 401)

            # Test telemetry ingestion with auth
            links = {k: {'utilization': 0.4} for k in ['s1-s2', 's2-s4', 's1-s3', 's3-s4']}
            request('/api/telemetry', {'links': links}, auth=True)
            
            _, state_raw = request('/api/state')
            state = json.loads(state_raw.decode('utf-8'))
            self.assertEqual(state['tick'], 1)
            self.assertFalse(state['stale'])

            # Test controller acknowledgment
            request('/api/controller/ack', {'route': ['s1', 's2', 's4']}, auth=True)
            request('/api/probe', {'latency_ms': 23.4, 'loss_percent': 1.0, 'throughput_mbps': 3.8}, auth=True)
            
            _, state_after = request('/api/state')
            self.assertEqual(json.loads(state_after.decode('utf-8'))['metrics']['latency_ms'], 23.4)

            # Test export endpoint
            ct_exp, body_exp = request('/api/export')
            self.assertIn('charset=utf-8', ct_exp)
            self.assertIn(b'mininet', body_exp)

            # Test comparison run API endpoint
            _, comp_raw = request('/api/comparison/run', {'duration': 15, 'seed': 42})
            comp = json.loads(comp_raw.decode('utf-8'))
            self.assertIn('results', comp)
            self.assertIn('predictive', comp['results'])

            # Test input validation rejected
            with self.assertRaises(urllib.error.HTTPError) as error:
                request('/api/control', {'mode': 'invalid_mode'})
            self.assertEqual(error.exception.code, 400)

        finally:
            process.terminate()
            process.wait(timeout=5)

if __name__ == '__main__':
    unittest.main(verbosity=2)
