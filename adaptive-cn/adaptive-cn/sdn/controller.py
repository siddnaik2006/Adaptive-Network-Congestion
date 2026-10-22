"""OpenFlow 1.3 controller with dynamic topology support and OpenFlow barrier confirmations."""
import argparse
import json
import os
import socket
import struct
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, List, Dict, Optional
import sys

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cn.topologies import get_topology, TOPOLOGIES

# Backward compatibility module-level constants for diamond topology
PORTS = TOPOLOGIES['diamond']['ports']
LINK_PORTS = TOPOLOGIES['diamond']['link_ports']

def message(kind: int, xid: int, body: bytes = b'') -> bytes:
    """Pack OpenFlow 1.3 header."""
    return struct.pack('!BBHI', 4, kind, 8 + len(body), xid) + body

def oxm(field: int, value: bytes) -> bytes:
    """Pack OpenFlow 1.3 basic OXM match TLV."""
    return struct.pack('!HBB', 0x8000, field << 1, len(value)) + value

def flow_body(destination: str, port: int) -> bytes:
    """Build OpenFlow 1.3 FlowMod message body for IPv4 destination forwarding."""
    fields = oxm(5, struct.pack('!H', 0x0800)) + oxm(12, socket.inet_aton(destination))
    match = struct.pack('!HH', 1, 4 + len(fields)) + fields
    match += b'\0' * ((-len(match)) % 8)
    action = struct.pack('!HHIH6x', 0, 16, port, 0)
    instruction = struct.pack('!HH4x', 4, 8 + len(action)) + action
    fixed = struct.pack('!QQBBHHHIIIHH', 0x434e, 0, 0, 0, 0, 0, 100, 0xffffffff, 0xffffffff, 0xffffffff, 0, 0)
    return fixed + match + instruction

def read_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from stream socket."""
    data = b''
    while len(data) < n:
        piece = sock.recv(n - len(data))
        if not piece:
            raise ConnectionError('Switch disconnected')
        data += piece
    return data

class Switch:
    def __init__(self, sock: socket.socket, controller: Any):
        self.sock = sock
        self.controller = controller
        self.dpid = None
        self.xid = 0
        self.lock = threading.Lock()
        self.pending = {}
        self.stats = {}

    def send(self, kind: int, body: bytes = b'') -> int:
        with self.lock:
            self.xid += 1
            self.sock.sendall(message(kind, self.xid, body))
            return self.xid

    def barrier(self):
        event = threading.Event()
        with self.lock:
            self.xid += 1
            barrier_xid = self.xid
            self.pending[barrier_xid] = event
            self.sock.sendall(message(20, barrier_xid))
        okay = event.wait(3.0)
        with self.lock:
            self.pending.pop(barrier_xid, None)
        if not okay:
            raise TimeoutError('OpenFlow barrier timeout')

    def run(self):
        try:
            self.send(0)  # OFPT_HELLO
            self.send(5)  # OFPT_FEATURES_REQUEST
            while True:
                version, kind, length, xid = struct.unpack('!BBHI', read_exact(self.sock, 8))
                if length < 8 or length > 65535:
                    raise ValueError('Invalid OpenFlow message length')
                body = read_exact(self.sock, length - 8)
                if version != 4:
                    raise ValueError('OpenFlow 1.3 required')
                if kind == 2:  # OFPT_ECHO_REQUEST
                    self.sock.sendall(message(3, xid, body))  # OFPT_ECHO_REPLY
                elif kind == 6:  # OFPT_FEATURES_REPLY
                    self.dpid = struct.unpack_from('!Q', body)[0]
                    if self.dpid not in self.controller.ports:
                        raise ValueError(f"Unexpected switch DPID {self.dpid} for active topology")
                    self.controller.switches[self.dpid] = self
                    self.controller.applied = None
                    self.send(9, struct.pack('!HH', 0, 128))  # OFPT_SET_CONFIG
                    print(f"s{self.dpid} connected", flush=True)
                elif kind == 21:  # OFPT_BARRIER_REPLY
                    if xid in self.pending:
                        self.pending[xid].set()
                elif kind == 1:  # OFPT_ERROR
                    self.controller.error = f"OpenFlow error on s{self.dpid}: {body.hex()}"
                    print(self.controller.error, flush=True)
                elif kind == 19 and len(body) >= 8:  # OFPT_MULTIPART_REPLY
                    mtype, flags = struct.unpack_from('!HH', body)
                    if mtype == 4:  # OFPMP_PORT_STATS
                        for offset in range(8, len(body) - 111, 112):
                            port = struct.unpack_from('!I', body, offset)[0]
                            counters = struct.unpack_from('!QQQQQQQQQQQQ', body, offset + 8)
                            self.stats[port] = (time.monotonic(), counters[3], counters[1], counters[5])
        except (OSError, ConnectionError, ValueError, struct.error) as e:
            print(f"Switch closed: {e}", flush=True)
        finally:
            if self.dpid and self.controller.switches.get(self.dpid) is self:
                self.controller.switches.pop(self.dpid, None)
            self.sock.close()

class Controller:
    def __init__(self, url: str, token: str, topology: str = 'diamond'):
        self.url = url
        self.token = token
        self.topology_name = topology
        self.topo = get_topology(topology)
        self.ports = self.topo['ports']
        self.link_ports = self.topo['link_ports']
        self.switches = {}
        self.applied = None
        self.previous = {}
        self.error = None

    def api(self, path: str, data: Any = None) -> Any:
        payload = None if data is None else json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            self.url + path,
            data=payload,
            headers={'Content-Type': 'application/json; charset=utf-8', 'Authorization': 'Bearer ' + self.token}
        )
        with urllib.request.urlopen(req, timeout=2.5) as r:
            return json.loads(r.read().decode('utf-8'))

    def install(self, route: List[str]):
        before = self.error
        h1_ip = self.topo['hosts']['h1']['ip']
        h2_ip = self.topo['hosts']['h2']['ip']
        
        # Install rules: downstream first, ingress last in each direction to avoid drops
        for destination, path, host in [(h2_ip, route, 'h2'), (h1_ip, route[::-1], 'h1')]:
            for i in reversed(range(len(path))):
                dpid = int(path[i][1:])
                nxt = path[i + 1] if i + 1 < len(path) else host
                switch = self.switches[dpid]
                switch.send(14, flow_body(destination, self.ports[dpid][nxt]))
                switch.barrier()
                
        # Background flow installation for h3 -> h4
        h3_ip = self.topo['hosts']['h3']['ip']
        h4_ip = self.topo['hosts']['h4']['ip']
        bg_sender_sw = int(self.topo['hosts']['h3']['switch'][1:])
        bg_recv_sw = int(self.topo['hosts']['h4']['switch'][1:])
        
        # In diamond/presets, install forward/reverse rules for background hosts
        if bg_sender_sw in self.switches and bg_recv_sw in self.switches:
            if bg_sender_sw != bg_recv_sw:
                # Flow from bg_sender towards bg_recv
                s_send = self.switches[bg_sender_sw]
                nxt_hop = f"s{bg_recv_sw}" if f"s{bg_recv_sw}" in self.ports[bg_sender_sw] else 's4'
                if nxt_hop in self.ports[bg_sender_sw]:
                    s_send.send(14, flow_body(h4_ip, self.ports[bg_sender_sw][nxt_hop]))
                    s_send.barrier()
                s_recv = self.switches[bg_recv_sw]
                s_recv.send(14, flow_body(h4_ip, self.ports[bg_recv_sw]['h4']))
                s_recv.barrier()
                # Reverse direction for background traffic
                s_recv.send(14, flow_body(h3_ip, self.ports[bg_recv_sw][f"s{bg_sender_sw}"] if f"s{bg_sender_sw}" in self.ports[bg_recv_sw] else self.ports[bg_recv_sw]['s2']))
                s_recv.barrier()
                s_send.send(14, flow_body(h3_ip, self.ports[bg_sender_sw]['h3']))
                s_send.barrier()
                
        if self.error != before:
            raise RuntimeError(self.error)
        self.applied = route[:]
        print(f"Applied route: {' -> '.join(route)}", flush=True)

    def loop(self):
        expected_count = len(self.topo['switches'])
        while True:
            started = time.monotonic()
            try:
                if len(self.switches) == expected_count:
                    desired = self.api('/api/controller/route')['route']
                    if desired != self.applied:
                        self.install(desired)
                    self.api('/api/controller/ack', {'route': self.applied})
                    
                    values = {}
                    for k, (left, lp, right, rp) in self.link_ports.items():
                        rates = []
                        for dpid, port in [(left, lp), (right, rp)]:
                            sample = self.switches[dpid].stats.get(port)
                            old = self.previous.get((dpid, port))
                            if sample and old and sample[0] > old[0] and sample[1] >= old[1]:
                                rates.append((sample[1] - old[1]) * 8.0 / (sample[0] - old[0]) / 1e6)
                            if sample:
                                self.previous[(dpid, port)] = sample
                        rate_val = max(rates, default=0.0)
                        values[k] = {
                            'utilization': rate_val / 10.0,
                            'tx_mbps': round(rate_val, 2),
                            'measurement': 'OpenFlow port TX counters'
                        }
                    if all(self.switches[d].stats for d in self.ports):
                        self.api('/api/telemetry', {'links': values})
                        
                for switch in list(self.switches.values()):
                    switch.send(18, struct.pack('!HH4xI4x', 4, 0, 0xffffffff))
            except Exception as e:
                print(f"Controller cycle: {e}", flush=True)
            time.sleep(max(0.05, 1.0 - (time.monotonic() - started)))

    def serve(self, port: int):
        threading.Thread(target=self.loop, daemon=True).start()
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', port))
            listener.listen()
            print(f"OpenFlow 1.3 controller listening on 127.0.0.1:{port} (topology={self.topology_name})", flush=True)
            while True:
                sock, _ = listener.accept()
                threading.Thread(target=Switch(sock, self).run, daemon=True).start()

if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Adaptive CN OpenFlow 1.3 Controller')
    p.add_argument('--api', default='http://127.0.0.1:8080')
    p.add_argument('--port', type=int, default=6653)
    p.add_argument('--topology', choices=list(TOPOLOGIES.keys()), default='diamond')
    a = p.parse_args()
    token = os.environ.get('CN_AGENT_TOKEN', '')
    if len(token) < 16:
        raise SystemExit('Set CN_AGENT_TOKEN (same value as backend).')
    Controller(a.api, token, a.topology).serve(a.port)
