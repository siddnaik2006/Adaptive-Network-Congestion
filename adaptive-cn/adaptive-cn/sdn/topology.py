"""Run as root on Linux with Mininet/Open vSwitch/iperf3 installed.

Consumes the shared topology definition from cn/topologies.py.
"""
import argparse
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any
import sys

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cn.topologies import get_topology, TOPOLOGIES

def network(topology_name: str = 'diamond'):
    topo = get_topology(topology_name)
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    
    # Create hosts
    hosts = {}
    for hid, hmeta in topo['hosts'].items():
        hosts[hid] = net.addHost(hid, ip=f"{hmeta['ip']}/24")
        
    # Create switches
    switches = {}
    for sw in topo['switches']:
        dpid_int = int(sw[1:])
        switches[sw] = net.addSwitch(sw, dpid=f'{dpid_int:016x}', protocols='OpenFlow13', failMode='secure')
        
    # Attach hosts to switches
    for hid, hmeta in topo['hosts'].items():
        sw_name = hmeta['switch']
        port_num = hmeta['port']
        net.addLink(hosts[hid], switches[sw_name], port2=port_num, bw=100)
        
    # Inter-switch links
    for a, b, bw, delay in topo['links']:
        k = '-'.join(sorted((a, b)))
        d1, p1, d2, p2 = topo['link_ports'][k]
        sw1 = f"s{d1}"
        sw2 = f"s{d2}"
        net.addLink(switches[sw1], switches[sw2], port1=p1, port2=p2, bw=int(bw), delay=f'{int(delay)}ms', max_queue_size=50)
        
    net.start()
    net.waitConnected(timeout=15)
    
    for a in hosts.values():
        for b in hosts.values():
            if a != b:
                a.setARP(b.IP(), b.MAC())
                
    return net, hosts, topo

def api(url: str, token: str, path: str, data: Any = None) -> Any:
    payload = None if data is None else json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        url + path,
        data=payload,
        headers={'Content-Type': 'application/json; charset=utf-8', 'Authorization': 'Bearer ' + token}
    )
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode('utf-8'))

def background_rate(scenario: str, t: int) -> float:
    if scenario == 'normal':
        return 2.0
    if scenario == 'heavy':
        return 9.0
    if scenario == 'burst':
        return 9.0 if 25 <= t % 70 < 45 else 1.0
    return min(9.0, 1.0 + max(0, t - 12) * 0.2) if t < 85 else max(1.0, 9.0 - (t - 85) * 0.15)

def run(net, hosts, a, topo):
    token = os.environ.get('CN_AGENT_TOKEN', '')
    if len(token) < 16:
        raise RuntimeError('CN_AGENT_TOKEN required (minimum 16 characters).')
        
    if not topo['mininet_verified']:
        print(f"[NOTICE] Topology '{a.topology}' is unverified in this Linux/Mininet testbed. Verified preset is 'diamond'.", flush=True)

    api(a.api, token, '/api/control', {'action': 'reset', 'mode': a.mode, 'scenario': a.scenario, 'topology': a.topology})
    api(a.api, token, '/api/control', {'action': 'start'})
    
    deadline = time.monotonic() + 25
    initial_route = [topo['ingress_switch']]
    while time.monotonic() < deadline:
        state = api(a.api, token, '/api/state')
        if state.get('applied_route'):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError('Controller did not acknowledge initial route')

    processes = []
    bg = None
    rate = None
    folder = ROOT / 'data/mininet'
    folder.mkdir(parents=True, exist_ok=True)
    stamp = f"{a.mode}-{a.scenario}-{a.topology}-{int(time.time())}"
    
    try:
        h2_ip = topo['hosts']['h2']['ip']
        h4_ip = topo['hosts']['h4']['ip']
        processes.append(hosts['h2'].popen(['iperf3', '-s', '-p', '5201']))
        processes.append(hosts['h4'].popen(['iperf3', '-s', '-p', '5202']))
        time.sleep(1)
        
        foreground_path = folder / f"{stamp}-iperf.json"
        with foreground_path.open('w', encoding='utf-8') as foreground_output:
            foreground = hosts['h1'].popen(
                ['iperf3', '-c', h2_ip, '-u', '-b', '4M', '-t', str(a.seconds), '-i', '1', '-J', '--get-server-output'],
                stdout=foreground_output
            )
            processes.append(foreground)
            begin = time.monotonic()
            ping_rows = []
            
            while time.monotonic() - begin < a.seconds:
                t = int(time.monotonic() - begin)
                newrate = round(background_rate(a.scenario, t))
                if newrate != rate:
                    if bg:
                        bg.terminate()
                        bg.wait(timeout=5)
                    bg = hosts['h3'].popen(
                        ['iperf3', '-c', h4_ip, '-u', '-b', f"{newrate}M", '-t', str(a.seconds), '-p', '5202'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    rate = newrate
                    
                result = hosts['h1'].cmd(f"ping -c 1 -W 1 {h2_ip}")
                match = re.search(r'time[=<]([\d.]+)', result)
                latency = float(match.group(1)) if match else None
                ping_rows.append({'elapsed': t, 'rtt_ms': latency, 'background_mbps': newrate})
                api(a.api, token, '/api/probe', {'latency_ms': latency})
                time.sleep(0.85)
                
            foreground.wait(timeout=10)
            
        report = json.loads(foreground_path.read_text(encoding='utf-8'))
        if report.get('error'):
            raise RuntimeError('iperf3 failed: ' + report['error'])
        summary = report.get('end', {}).get('sum_received') or report.get('end', {}).get('sum', {})
        if not summary or 'bits_per_second' not in summary:
            raise RuntimeError('Missing iperf3 receiver summary')
            
        successful_rtts = [x['rtt_ms'] for x in ping_rows if x['rtt_ms'] is not None]
        measured = {
            'latency_ms': sum(successful_rtts) / len(successful_rtts) if successful_rtts else None,
            'throughput_mbps': summary['bits_per_second'] / 1e6,
            'loss_percent': summary.get('lost_percent'),
            'jitter_ms': summary.get('jitter_ms')
        }
        api(a.api, token, '/api/probe', measured)
        (folder / f"{stamp}-ping.json").write_text(json.dumps(ping_rows, indent=2), encoding='utf-8')
        state = api(a.api, token, '/api/state')
        (folder / f"{stamp}-summary.json").write_text(
            json.dumps({
                'source': 'Mininet packets',
                'topology': a.topology,
                'mininet_verified': topo['mininet_verified'],
                'mode': a.mode,
                'scenario': a.scenario,
                'seconds': a.seconds,
                'metrics': measured,
                'state': state,
                'iperf_file': foreground_path.name
            }, indent=2),
            encoding='utf-8'
        )
        
        with urllib.request.urlopen(a.api + '/api/export') as response:
            (folder / f"{stamp}.csv").write_bytes(response.read())
        api(a.api, token, '/api/control', {'action': 'save'})
        print(json.dumps(measured, indent=2))
        print(f"Raw experiment results saved to: {folder}")
    finally:
        if bg and bg.poll() is None:
            bg.terminate()
            bg.wait(timeout=5)
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Mininet Topology Runner')
    p.add_argument('--interactive', action='store_true')
    p.add_argument('--api', default='http://127.0.0.1:8080')
    p.add_argument('--topology', choices=list(TOPOLOGIES.keys()), default='diamond')
    p.add_argument('--mode', choices=['static', 'reactive', 'predictive'], default='predictive')
    p.add_argument('--scenario', choices=['normal', 'ramp', 'burst', 'heavy'], default='ramp')
    p.add_argument('--seconds', type=int, default=120)
    a = p.parse_args()
    
    if a.seconds < 20:
        raise SystemExit('Use at least 20 seconds per experiment.')
    if os.name == 'nt':
        raise SystemExit('Mininet requires a Linux kernel with Open vSwitch and network namespaces.')
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo -E python3 sdn/topology.py')
        
    net, hosts, topo = network(a.topology)
    try:
        if a.interactive:
            CLI(net)
        else:
            run(net, hosts, a, topo)
    finally:
        net.stop()
