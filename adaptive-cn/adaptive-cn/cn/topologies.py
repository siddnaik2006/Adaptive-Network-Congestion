"""Shared topology definitions, port mappings, and graph validation."""
from typing import Dict, List, Tuple, Any

def key(a: str, b: str) -> str:
    """Canonical link identifier sorted alphabetically."""
    return '-'.join(sorted((a, b)))

TOPOLOGIES: Dict[str, Dict[str, Any]] = {
    'diamond': {
        'id': 'diamond',
        'name': '4-Switch Diamond',
        'description': 'Classic 4-switch diamond topology with primary upper path and alternate lower path.',
        'mininet_verified': True,
        'verification_notice': 'Verified in Mininet OpenFlow testbed and analytical simulation.',
        'ingress_switch': 's1',
        'egress_switch': 's4',
        'switches': ['s1', 's2', 's3', 's4'],
        'hosts': {
            'h1': {'ip': '10.0.0.1', 'switch': 's1', 'port': 1, 'role': 'sender', 'label': 'H1 (Foreground Sender)'},
            'h2': {'ip': '10.0.0.2', 'switch': 's4', 'port': 3, 'role': 'receiver', 'label': 'H2 (Foreground Receiver)'},
            'h3': {'ip': '10.0.0.3', 'switch': 's2', 'port': 3, 'role': 'bg_sender', 'label': 'H3 (Background Sender)'},
            'h4': {'ip': '10.0.0.4', 'switch': 's4', 'port': 4, 'role': 'bg_receiver', 'label': 'H4 (Background Receiver)'},
        },
        'foreground_pair': ('h1', 'h2'),
        'background_pair': ('h3', 'h4'),
        'bottleneck_link': 's2-s4',
        'links': [
            ('s1', 's2', 10.0, 5.0),
            ('s2', 's4', 10.0, 5.0),
            ('s1', 's3', 10.0, 8.0),
            ('s3', 's4', 10.0, 8.0),
        ],
        'ports': {
            1: {'s2': 2, 's3': 3, 'h1': 1},
            2: {'s1': 1, 's4': 2, 'h3': 3},
            3: {'s1': 1, 's4': 2},
            4: {'s2': 1, 's3': 2, 'h2': 3, 'h4': 4},
        },
        'link_ports': {
            's1-s2': (1, 2, 2, 1),
            's2-s4': (2, 2, 4, 1),
            's1-s3': (1, 3, 3, 1),
            's3-s4': (3, 2, 4, 2),
        },
        'layout': {
            'viewBox': '0 0 740 340',
            'switches': {
                's1': {'x': 165, 'y': 170},
                's2': {'x': 350, 'y': 75},
                's3': {'x': 350, 'y': 265},
                's4': {'x': 535, 'y': 170},
            },
            'hosts': {
                'h1': {'x': 50, 'y': 170, 'attach': 's1'},
                'h2': {'x': 650, 'y': 170, 'attach': 's4'},
                'h3': {'x': 350, 'y': 16, 'attach': 's2'},
                'h4': {'x': 650, 'y': 75, 'attach': 's4'},
            },
            'controller': {'x': 165, 'y': 16},
            'engine': {'x': 535, 'y': 16},
        },
    },
    'six_switch': {
        'id': 'six_switch',
        'name': '6-Switch Ladder',
        'description': '6-switch network with dual bottleneck opportunities and cross-ladder backup routes.',
        'mininet_verified': False,
        'verification_notice': 'Simulation verified. Mininet runtime verification pending in Linux OVS environment.',
        'ingress_switch': 's1',
        'egress_switch': 's6',
        'switches': ['s1', 's2', 's3', 's4', 's5', 's6'],
        'hosts': {
            'h1': {'ip': '10.0.0.1', 'switch': 's1', 'port': 1, 'role': 'sender', 'label': 'H1 (Foreground Sender)'},
            'h2': {'ip': '10.0.0.2', 'switch': 's6', 'port': 3, 'role': 'receiver', 'label': 'H2 (Foreground Receiver)'},
            'h3': {'ip': '10.0.0.3', 'switch': 's2', 'port': 4, 'role': 'bg_sender', 'label': 'H3 (Background Sender)'},
            'h4': {'ip': '10.0.0.4', 'switch': 's4', 'port': 4, 'role': 'bg_receiver', 'label': 'H4 (Background Receiver)'},
        },
        'foreground_pair': ('h1', 'h2'),
        'background_pair': ('h3', 'h4'),
        'bottleneck_link': 's2-s4',
        'links': [
            ('s1', 's2', 10.0, 4.0),
            ('s2', 's4', 10.0, 4.0),
            ('s4', 's6', 10.0, 4.0),
            ('s1', 's3', 10.0, 7.0),
            ('s3', 's5', 10.0, 7.0),
            ('s5', 's6', 10.0, 7.0),
            ('s2', 's5', 10.0, 8.0),
            ('s3', 's4', 10.0, 8.0),
        ],
        'ports': {
            1: {'h1': 1, 's2': 2, 's3': 3},
            2: {'s1': 1, 's4': 2, 's5': 3, 'h3': 4},
            3: {'s1': 1, 's5': 2, 's4': 3},
            4: {'s2': 1, 's6': 2, 's3': 3, 'h4': 4},
            5: {'s3': 1, 's6': 2, 's2': 3},
            6: {'s4': 1, 's5': 2, 'h2': 3},
        },
        'link_ports': {
            's1-s2': (1, 2, 2, 1),
            's2-s4': (2, 2, 4, 1),
            's4-s6': (4, 2, 6, 1),
            's1-s3': (1, 3, 3, 1),
            's3-s5': (3, 2, 5, 1),
            's5-s6': (5, 2, 6, 2),
            's2-s5': (2, 3, 5, 3),
            's3-s4': (3, 3, 4, 3),
        },
        'layout': {
            'viewBox': '0 0 820 340',
            'switches': {
                's1': {'x': 150, 'y': 170},
                's2': {'x': 320, 'y': 80},
                's3': {'x': 320, 'y': 260},
                's4': {'x': 490, 'y': 80},
                's5': {'x': 490, 'y': 260},
                's6': {'x': 660, 'y': 170},
            },
            'hosts': {
                'h1': {'x': 45, 'y': 170, 'attach': 's1'},
                'h2': {'x': 765, 'y': 170, 'attach': 's6'},
                'h3': {'x': 320, 'y': 16, 'attach': 's2'},
                'h4': {'x': 490, 'y': 16, 'attach': 's4'},
            },
            'controller': {'x': 150, 'y': 16},
            'engine': {'x': 660, 'y': 16},
        },
    },
    'eight_mesh': {
        'id': 'eight_mesh',
        'name': '8-Switch Mesh Grid',
        'description': '8-switch grid topology with high path diversity, diagonal shortcuts, and robust rerouting.',
        'mininet_verified': False,
        'verification_notice': 'Simulation verified. Mininet runtime verification pending in Linux OVS environment.',
        'ingress_switch': 's1',
        'egress_switch': 's8',
        'switches': ['s1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'],
        'hosts': {
            'h1': {'ip': '10.0.0.1', 'switch': 's1', 'port': 1, 'role': 'sender', 'label': 'H1 (Foreground Sender)'},
            'h2': {'ip': '10.0.0.2', 'switch': 's8', 'port': 3, 'role': 'receiver', 'label': 'H2 (Foreground Receiver)'},
            'h3': {'ip': '10.0.0.3', 'switch': 's2', 'port': 4, 'role': 'bg_sender', 'label': 'H3 (Background Sender)'},
            'h4': {'ip': '10.0.0.4', 'switch': 's3', 'port': 4, 'role': 'bg_receiver', 'label': 'H4 (Background Receiver)'},
        },
        'foreground_pair': ('h1', 'h2'),
        'background_pair': ('h3', 'h4'),
        'bottleneck_link': 's2-s3',
        'links': [
            ('s1', 's2', 10.0, 4.0),
            ('s2', 's3', 10.0, 4.0),
            ('s3', 's4', 10.0, 4.0),
            ('s4', 's8', 10.0, 5.0),
            ('s1', 's5', 10.0, 6.0),
            ('s2', 's6', 10.0, 6.0),
            ('s3', 's7', 10.0, 6.0),
            ('s5', 's6', 10.0, 7.0),
            ('s6', 's7', 10.0, 7.0),
            ('s7', 's8', 10.0, 7.0),
            ('s2', 's7', 10.0, 8.0),
            ('s3', 's6', 10.0, 8.0),
        ],
        'ports': {
            1: {'h1': 1, 's2': 2, 's5': 3},
            2: {'s1': 1, 's3': 2, 's6': 3, 'h3': 4, 's7': 5},
            3: {'s2': 1, 's4': 2, 's7': 3, 'h4': 4, 's6': 5},
            4: {'s3': 1, 's8': 2},
            5: {'s1': 1, 's6': 2},
            6: {'s5': 1, 's7': 2, 's2': 3, 's3': 4},
            7: {'s6': 1, 's8': 2, 's3': 3, 's2': 4},
            8: {'s4': 1, 's7': 2, 'h2': 3},
        },
        'link_ports': {
            's1-s2': (1, 2, 2, 1),
            's2-s3': (2, 2, 3, 1),
            's3-s4': (3, 2, 4, 1),
            's4-s8': (4, 2, 8, 1),
            's1-s5': (1, 3, 5, 1),
            's2-s6': (2, 3, 6, 3),
            's3-s7': (3, 3, 7, 3),
            's5-s6': (5, 2, 6, 1),
            's6-s7': (6, 2, 7, 1),
            's7-s8': (7, 2, 8, 2),
            's2-s7': (2, 5, 7, 4),
            's3-s6': (3, 5, 6, 4),
        },
        'layout': {
            'viewBox': '0 0 840 350',
            'switches': {
                's1': {'x': 150, 'y': 95},
                's2': {'x': 320, 'y': 95},
                's3': {'x': 490, 'y': 95},
                's4': {'x': 660, 'y': 95},
                's5': {'x': 150, 'y': 255},
                's6': {'x': 320, 'y': 255},
                's7': {'x': 490, 'y': 255},
                's8': {'x': 660, 'y': 255},
            },
            'hosts': {
                'h1': {'x': 45, 'y': 95, 'attach': 's1'},
                'h2': {'x': 765, 'y': 255, 'attach': 's8'},
                'h3': {'x': 320, 'y': 16, 'attach': 's2'},
                'h4': {'x': 490, 'y': 16, 'attach': 's3'},
            },
            'controller': {'x': 150, 'y': 16},
            'engine': {'x': 660, 'y': 16},
        },
    },
}

def get_topology(name: str = 'diamond') -> Dict[str, Any]:
    """Retrieve topology definition by preset name."""
    if name not in TOPOLOGIES:
        raise ValueError(f"Unknown topology '{name}'. Supported: {list(TOPOLOGIES.keys())}")
    return TOPOLOGIES[name]

def list_topologies() -> List[Dict[str, Any]]:
    """List summary metadata for all supported topologies."""
    return [
        {
            'id': t['id'],
            'name': t['name'],
            'description': t['description'],
            'switches_count': len(t['switches']),
            'links_count': len(t['links']),
            'mininet_verified': t['mininet_verified'],
            'verification_notice': t['verification_notice'],
            'ingress_switch': t['ingress_switch'],
            'egress_switch': t['egress_switch'],
            'bottleneck_link': t['bottleneck_link'],
        }
        for t in TOPOLOGIES.values()
    ]

def find_all_paths(topology: Dict[str, Any], start: str = None, end: str = None) -> List[List[str]]:
    """Find all simple acyclic paths between start and end switches."""
    start = start or topology['ingress_switch']
    end = end or topology['egress_switch']
    adj: Dict[str, List[str]] = {}
    for a, b, _, _ in topology['links']:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    
    paths: List[List[str]] = []
    
    def dfs(curr: str, target: str, visited: List[str]):
        if curr == target:
            paths.append(list(visited))
            return
        for nxt in adj.get(curr, []):
            if nxt not in visited:
                visited.append(nxt)
                dfs(nxt, target, visited)
                visited.pop()

    dfs(start, end, [start])
    return paths

def validate_topology(topology: Dict[str, Any]) -> bool:
    """Validate graph connectivity, port mappings, and host assignments."""
    paths = find_all_paths(topology)
    if not paths:
        raise ValueError(f"Topology {topology.get('id')} has no valid path between ingress and egress.")
    
    # Check that all switches have ports defined
    for sw in topology['switches']:
        dpid = int(sw[1:])
        if dpid not in topology['ports']:
            raise ValueError(f"Switch {sw} (dpid {dpid}) missing from ports mapping.")
    
    # Check link ports
    for a, b, _, _ in topology['links']:
        k = key(a, b)
        if k not in topology['link_ports']:
            raise ValueError(f"Link {k} missing from link_ports mapping.")
        d1, p1, d2, p2 = topology['link_ports'][k]
        sw1 = f"s{d1}"
        sw2 = f"s{d2}"
        if topology['ports'][d1].get(sw2) != p1 or topology['ports'][d2].get(sw1) != p2:
            raise ValueError(f"Port mapping mismatch on link {k}: {topology['link_ports'][k]}")
    
    return True
