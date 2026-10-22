# Adaptive CN — AI-Powered Adaptive Network Congestion Prediction & Routing

A semester-end Computer Networks lab: forecast congestion, compute a weighted shortest path, and change OpenFlow forwarding rules. Includes a local dashboard, a trained lightweight predictor, a packet-network experiment runner, telemetry CSV export, and reproducible simulation comparisons.

## Start here on your Windows laptop

1. Install Python 3.11 or 3.12, including the Python launcher or Add Python to PATH option.
2. Extract this entire folder from the ZIP.
3. Double-click `start-demo.bat`. Keep the terminal open.
4. Open **http://127.0.0.1:8080** if the browser opened before the server was ready.
5. Click **Start experiment**. Allow at least 10 seconds for prediction warm-up. The gradual-ramp scenario becomes congested later, and the route should move through S3.
6. Try Static, Reactive, and Predictive modes. Reset between comparisons.

No Node.js, PostgreSQL, paid API, CUDA, Torch, or model downloads are needed. NumPy is the only runtime dependency; first setup needs Internet to install it. The included trained model works immediately. Demo mode uses analytical simulation; do not present its numbers as measured network improvements.

Manual alternative (PowerShell, from this folder):

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m cn.server
```

Linux/macOS demo: `bash start-demo.sh`.

## The actual CN demonstration

Use an Ubuntu Linux VM or Linux machine with Mininet and Open vSwitch. This mode exchanges actual packets between emulated hosts. The Python controller implements the required OpenFlow 1.3 messages and programs Open vSwitch flow tables. There is no Ryu dependency in this implementation; it serves the same controller role for this fixed teaching topology.

Read **docs/MININET_GUIDE.md** for the three-terminal setup, traffic experiments, and packet/flow verification. The controller supports this fixed topology and IPv4 host flows only; it is intentionally not a general-purpose Ethernet controller.

## What is included

| Path | Purpose |
|---|---|
| `cn/server.py` | Local HTTP API and dashboard server |
| `cn/engine.py` | Telemetry, routing decisions, simulation, run archive |
| `cn/model.py` | Training, forecasting, held-out evaluation |
| `cn/routing.py` | Weighted Dijkstra, cooldown and hysteresis |
| `sdn/controller.py` | OpenFlow 1.3 controller |
| `sdn/topology.py` | Mininet topology and iperf3/ping experiment runner |
| `web/` | Responsive dependency-free dashboard |
| `scripts/train.py` | Synthetic or measured-data training |
| `scripts/benchmark.py` | 60 deterministic analytical simulation trials |
| `scripts/compare_real.py` | Aggregate measured Mininet summaries |
| `tests/test_project.py` | Automated model, routing, API, and wire-protocol checks |
| `docs/` | Network setup, experiment design, architecture, viva explanation |

## Model: what we train, and what we do not claim

The initial model is **ridge autoregressive forecasting**, not LSTM. It receives the last 10 utilization samples plus trend and variability features, and predicts utilization five samples ahead. At one-second sampling, that is a five-second horizon. An empirical calibration-residual distribution estimates the risk of exceeding 85% utilization. This is an empirical estimate under the calibration-data distribution, not a guaranteed or universally calibrated probability.

The bundled model is trained on **synthetic** ramps, bursts, and variable traffic. Train/calibration/test partitions are split by independent sequences, not randomly mixed overlapping windows. Its metrics are included in `data/model.json`; they are synthetic holdout metrics. Sudden unpredictable bursts cannot reliably be anticipated.

For real training, collect at least six independent Mininet sessions (preferably 20+) and run:

```bash
.venv/bin/python scripts/train.py --csv data/mininet/*.csv --output data/model.json
```

Then restart the backend. Training currently uses each session's upper bottleneck-link sequence and assumes one-second polling. Keep varied scenarios and enough congestion examples in every partition. Test routing on additional independent runs not used for training or calibration. See `docs/EXPERIMENTS.md`.

## Routing

Static mode keeps S1–S2–S4. Reactive mode penalizes observed utilization above 85%. Predictive mode uses forecast risk and forecast utilization to change Dijkstra's link costs. A 10-sample cooldown and 15% path-cost improvement requirement reduce route oscillation. Predictive mode uses reactive costs during warm-up or if no trained forecast is available. The dashboard distinguishes requested and controller-confirmed routes.

## Run checks and experiments

```bash
python -m unittest discover -s tests -v
python scripts/benchmark.py
python scripts/compare_real.py
```

Simulation benchmark output is explicitly labelled. Real summaries appear only after running the Mininet experiment runner. No successful physical-network experiment is claimed by this package.

## Persistence and privacy

All data stays in this folder. Export CSV in the dashboard. **Save run** writes JSON to `data/runs/`; reset archives the previous run. Mininet experiments save iperf3 output, ping samples, summary JSON, and telemetry CSV in `data/mininet/`. Training writes `data/model.json`. No database service is used.

The server and controller bind to localhost. Agent write endpoints require `CN_AGENT_TOKEN`; use the same value in all Linux terminals. Dashboard controls are intended for a trusted local lab. Do not expose this service directly to the Internet.

## Docker

The supplied Compose demo uses host networking, intended for Linux Docker. Run `docker compose up --build`, then open localhost:8080. Prefer `start-demo.bat` on Windows; Docker Desktop host networking varies by configuration. Mininet mode runs on the Linux host, not in the demo container.

## Honest scope

The project implements the complete local lab workflow, but its Mininet runtime must be verified on your Linux machine. Available automated checks validate routing/model behavior, API responses, OpenFlow encoding, and a mocked switch handshake. They do not establish successful Open vSwitch forwarding. Model quality and network improvements must be measured; an AI predictor may underperform reactive routing in some scenarios. No claim that this research idea is globally new is made.
