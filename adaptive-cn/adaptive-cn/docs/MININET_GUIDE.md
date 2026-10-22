# Real packet-network setup

## 1. Environment

Use an Ubuntu 22.04/24.04 Linux VM or native Linux. A VM with 2 vCPUs and 4 GB RAM is a reasonable starting allocation. Windows demo mode does not run Mininet. A VM is preferable to ordinary Windows Python; WSL networking/service setup may need additional configuration.

Install system packages:

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch iperf3 python3-venv python3-numpy
sudo systemctl start openvswitch-switch
sudo mn --test pingall
sudo mn -c
```

The basic `mn --test pingall` may depend on the distribution's default controller availability. Our supplied topology uses the separate controller below. Do not run the default `mn` command and the supplied topology at the same time.

Extract the project onto Linux. Open three terminals in the `adaptive-cn` folder. Generate a private token, and copy the same token to terminals 2 and 3:

```bash
python3 -c 'import secrets; print(secrets.token_hex(24))'
```

Do not include the token in screenshots or your report.

## 2. Terminal 1: dashboard backend

```bash
export CN_AGENT_TOKEN='PASTE_YOUR_GENERATED_TOKEN'
python3 -m venv --system-site-packages .venv
.venv/bin/python -m cn.server --source mininet
```

Open http://127.0.0.1:8080 inside the Linux VM's browser. The API is intentionally localhost-only. The bundled model initially uses synthetic training; collect real data and retrain before reporting real predictive-model performance.

## 3. Terminal 2: OpenFlow controller

```bash
export CN_AGENT_TOKEN='PASTE_THE_SAME_TOKEN'
python3 sdn/controller.py
```

Expect `OpenFlow 1.3 listening on 127.0.0.1:6653`.

## 4. Terminal 3: Mininet experiment

```bash
export CN_AGENT_TOKEN='PASTE_THE_SAME_TOKEN'
sudo -E python3 sdn/topology.py --mode predictive --scenario ramp --seconds 120
```

This creates hosts H1–H4, four switches, two alternate paths, and constrained 10 Mbps inter-switch links. H1→H2 sends 4 Mbps foreground UDP traffic. H3→H4 sends background traffic on S2–S4, forcing congestion on the upper route. The lower route has higher configured delay but more spare capacity. Static ARP entries avoid broadcasting loops; this controller intentionally forwards only the configured IPv4 pairs.

The runner saves raw iperf3 JSON, ping samples, summary JSON, telemetry CSV, and a backend run archive. In the dashboard, utilization is live. RTT comes from ping samples. Receiver throughput/loss/jitter are final experiment aggregates and appear after iperf3 completes; they are not fabricated live estimates. Missing metrics display a dash.

Run the same scenario with each mode, allowing the runner to stop and recreate the network between runs:

```bash
sudo -E python3 sdn/topology.py --mode static --scenario ramp --seconds 120
sudo -E python3 sdn/topology.py --mode reactive --scenario ramp --seconds 120
sudo -E python3 sdn/topology.py --mode predictive --scenario ramp --seconds 120
.venv/bin/python scripts/compare_real.py
```

## 5. Prove actual forwarding

For an interactive session instead of automated traffic:

```bash
sudo -E python3 sdn/topology.py --interactive
```

At `mininet>`:

```text
h1 ping -c 4 h2
h3 ping -c 4 h4
sh ovs-ofctl -O OpenFlow13 dump-flows s1
sh ovs-ofctl -O OpenFlow13 dump-flows s2
sh ovs-ofctl -O OpenFlow13 dump-ports s1
h2 iperf3 -s -D
h4 iperf3 -s -p 5202 -D
h1 iperf3 -c 10.0.0.2 -u -b 4M -t 90 &
h3 iperf3 -c 10.0.0.4 -u -b 9M -p 5202 -t 90 &
```

You should observe controller logs acknowledging route changes, destination 10.0.0.2 forwarding on a different S1 output port, and counters increasing on the selected links. Only configured H1↔H2 and H3↔H4 connectivity is expected; `pingall` is not supported by this fixed-flow controller.

## Troubleshooting

- **No switch connections:** check controller terminal, `sudo systemctl status openvswitch-switch`, and `ss -ltn | rg 6653` (use grep if rg is absent).
- **401 in controller logs:** the three terminals have different/missing `CN_AGENT_TOKEN` values.
- **Backend waiting for telemetry:** controller needs all four switches and a first port-statistics reply.
- **iperf3 connection refused:** ensure the runner owns the hosts and the controller has acknowledged initial forwarding. Inspect raw output for iperf errors.
- **No reroute:** wait for model warm-up, use ramp/heavy traffic, inspect actual utilization and predicted risk. A forecast is not a guarantee of rerouting.
- **Stale Mininet interfaces after interrupted run:** stop the topology, then run `sudo mn -c`; this clears Mininet lab interfaces and should not be used while another Mininet experiment is running.
- **Permission denied reading root-created files:** use `sudo chown -R "$USER":"$(id -gn)" data/mininet data/runs` after experiments if needed.

## Validation boundary

This package's Mininet/Open vSwitch execution has not been run in the build environment. Perform the interactive forwarding checks above before presenting the experiment as validated. OpenFlow protocol unit checks are included; they are not substitutes for a packet-network integration test.
