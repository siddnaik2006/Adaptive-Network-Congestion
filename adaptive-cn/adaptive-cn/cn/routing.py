"""Weighted Dijkstra with cooldown and hysteresis across generalized network topologies."""
import heapq
from typing import Dict, List, Tuple, Any, Optional
from .topologies import get_topology, key, TOPOLOGIES

# Backward-compatibility alias for the default diamond topology links
LINKS = TOPOLOGIES['diamond']['links']

def shortest_path(costs: Optional[Dict[str, float]] = None,
                  start: str = 's1',
                  end: str = 's4',
                  links: Optional[List[Tuple[str, str, float, float]]] = None) -> Tuple[List[str], float]:
    """Find the shortest weighted path using Dijkstra's algorithm."""
    costs = costs or {}
    links = links if links is not None else LINKS
    graph: Dict[str, List[Tuple[str, float]]] = {}
    
    for a, b, _, delay in links:
        cost = costs.get(key(a, b), float(delay))
        graph.setdefault(a, []).append((b, cost))
        graph.setdefault(b, []).append((a, cost))
        
    heap = [(0.0, start, [start])]
    seen = set()
    
    while heap:
        cost, node, path = heapq.heappop(heap)
        if node in seen:
            continue
        seen.add(node)
        if node == end:
            return path, cost
        for nxt, w in graph.get(node, []):
            if nxt not in seen:
                heapq.heappush(heap, (cost + w, nxt, path + [nxt]))
                
    raise ValueError(f"No path found between {start} and {end}")

def choose(mode: str,
           links: Dict[str, Dict[str, Any]],
           current: List[str],
           tick: int,
           last_change: int,
           topology: Any = 'diamond',
           start: Optional[str] = None,
           end: Optional[str] = None) -> Tuple[List[str], str, Dict[str, Any]]:
    """Select the optimal path based on static, reactive, or predictive link costs."""
    topo = get_topology(topology) if isinstance(topology, str) else topology
    start = start or topo['ingress_switch']
    end = end or topo['egress_switch']
    links_def = topo['links']
    
    if mode == 'static':
        target, cost = shortest_path({}, start=start, end=end, links=links_def)
        details = {
            'tick': tick,
            'mode': mode,
            'current': current,
            'target': target,
            'target_cost': round(cost, 2),
            'current_cost': round(cost, 2),
            'cooldown_ticks_remaining': 0,
            'hysteresis_applied': False,
            'reason': 'Static shortest path',
            'explanation': f"Static routing maintains fixed shortest path {' → '.join(target).upper()} (base delay: {cost:.1f} ms).",
            'route_changed': False,
        }
        return target, 'Static shortest path', details
        
    costs: Dict[str, float] = {}
    for a, b, _, delay in links_def:
        k = key(a, b)
        m = links.get(k, {})
        utilization = float(m.get('utilization', 0.0))
        risk = m.get('risk')
        forecast = m.get('forecast')
        
        if mode == 'predictive' and risk is not None:
            # Weighted predictive cost: propagation delay + risk penalty + forecast overflow penalty
            costs[k] = float(delay) + 80.0 * float(risk) + 20.0 * max(0.0, float(forecast or 0.0) - 0.65)
        else:
            # Reactive cost: propagation delay + heavy penalty when measured utilization exceeds threshold
            costs[k] = float(delay) + 100.0 * max(0.0, utilization - 0.85)
            
    candidate_target, candidate_cost = shortest_path(costs, start=start, end=end, links=links_def)
    current_cost = sum(costs.get(key(a, b), 0.0) for a, b in zip(current, current[1:]))
    cooldown_remaining = max(0, 10 - (tick - last_change))
    
    # Evaluate route stability checks: cooldown and hysteresis
    if candidate_target != current:
        if cooldown_remaining > 0:
            target = current
            reason = f"Cooldown in effect ({cooldown_remaining}s remaining)"
            explanation = (f"Alternative path {' → '.join(candidate_target).upper()} has lower cost ({candidate_cost:.1f} vs {current_cost:.1f}), "
                           f"but rerouting is held for {cooldown_remaining}s cooldown to prevent route oscillation.")
            changed = False
        elif candidate_cost >= current_cost * 0.85:
            target = current
            reason = "Hysteresis threshold not met"
            explanation = (f"Alternative path {' → '.join(candidate_target).upper()} cost ({candidate_cost:.1f}) is not at least 15% better "
                           f"than current path ({current_cost:.1f}). Hysteresis prevents unnecessary route switching.")
            changed = False
        else:
            target = candidate_target
            reason = 'Predicted congestion risk' if mode == 'predictive' else 'Measured congestion'
            explanation = (f"Congestion detected on current path. Rerouting to {' → '.join(target).upper()} "
                           f"(cost reduced from {current_cost:.1f} to {candidate_cost:.1f}).")
            changed = True
    else:
        target = current
        reason = "Current path remains preferable"
        explanation = f"Current path {' → '.join(current).upper()} remains optimal (cost: {current_cost:.1f})."
        changed = False

    details = {
        'tick': tick,
        'mode': mode,
        'current': current,
        'target': target,
        'candidate_target': candidate_target,
        'target_cost': round(candidate_cost if changed else current_cost, 2),
        'candidate_cost': round(candidate_cost, 2),
        'current_cost': round(current_cost, 2),
        'cooldown_ticks_remaining': cooldown_remaining,
        'hysteresis_threshold_met': candidate_cost < current_cost * 0.85 if candidate_target != current else True,
        'reason': reason,
        'explanation': explanation,
        'route_changed': changed,
    }
    
    return target, reason, details
