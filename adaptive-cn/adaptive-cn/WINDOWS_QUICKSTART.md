# Windows Quickstart Guide • Adaptive CN

This guide provides exact Windows launch instructions, configuration workflows, and metric explanations for the **AI-Powered Network Congestion Prediction & Routing** lab.

---

## 1. Prerequisites

- **Operating System:** Windows 10 or Windows 11 (64-bit)
- **Python:** Python 3.9 or newer (installed and accessible in PATH or via `py`)
- **Web Browser:** Chrome, Edge, Firefox, or Brave
- **Dependencies:** Lightweight (only `numpy` required; automatically installed into `.venv`)

> [!NOTE]
> **No Linux, VM, or Mininet installation is required on Windows.**
> In Windows mode, the lab runs an **analytical simulation engine** modeling network queuing, link capacities, propagation delays, packet losses, and OpenFlow route switches. If you later deploy to Linux with Mininet, the exact same controller and web interface work with live OpenFlow 1.3 hardware counters.

---

## 2. Launch Instructions

### Option A: One-Click Launch (Recommended)
1. Open File Explorer to your project folder (`adaptive-cn`).
2. Double-click **`start-demo.bat`**.
3. The script will:
   - Create the local `.venv` virtual environment if not present.
   - Install minimal requirements (`numpy`).
   - Train the default Ridge autoregressive model (`data/model.json`) if not already generated.
   - Automatically launch your default web browser to [http://127.0.0.1:8080](http://127.0.0.1:8080).
   - Start the HTTP dashboard server.

---

### Option B: PowerShell / Command Prompt
Open PowerShell or Command Prompt in the project folder and run:

```powershell
# 1. Activate or create virtual environment
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Verify baseline model exists (train if missing)
.\.venv\Scripts\python.exe scripts\train.py

# 3. Launch dashboard server
.\.venv\Scripts\python.exe -m cn.server
```

Open your browser to: **[http://127.0.0.1:8080](http://127.0.0.1:8080)**

To run on a custom port or topology preset:
```powershell
.\.venv\Scripts\python.exe -m cn.server --port 9090 --topology diamond
```

---

## 3. Verifying the Display in Windows

When the dashboard opens, verify the clean Windows rendering:
- **No corrupted characters:** Confirm arrows (`S1 → S2 → S4`), bullets (`•`), placeholders (`—`), and em dashes render crisply without `â€™`, `Â`, or broken glyphs.
- **Header Badge:** Displays `SIMULATION • DEMO` with a glowing green connection indicator.
- **Live SVG Topology:** The selected network topology (hosts H1–H4, switches S1–S4, SDN controller, and AI prediction engine) is drawn immediately, even before starting the experiment.

---

## 4. Key Metrics Explained

| Metric | Units | Ideal Direction | What It Means |
| :--- | :--- | :--- | :--- |
| **Round-Trip Latency** | `ms` | Lower is better | Propagation delay plus queuing delay experienced by foreground packets traversing the active route. |
| **Packet Loss** | `%` | Lower is better | Percentage of packets dropped when total offered traffic overwhelms the link buffer/capacity. |
| **Foreground Throughput** | `Mbps` | Higher is better (up to demand) | Actual delivery rate received by host H2 (`throughput = foreground × (1 - loss)`). |
| **Max Congestion Risk** | `%` | Lower is better | Empirical probability that predicted link utilization 5 samples ahead will exceed the congestion threshold (85%). |
| **Offered Load** | `Mbps` / `%` | &mdash; | Total traffic hosts attempt to send. Can exceed 100% of physical capacity during heavy congestion. |
| **Transmitted Rate (`tx_mbps`)** | `Mbps` | Capped at capacity | Physical traffic successfully transmitted through the link (cannot exceed link capacity). |

---

## 5. Experiment Walkthrough

### 1. Guided Demonstration
- Click **"★ Start guided demo"** on the main hero banner.
- The system automatically resets, selects the **Gradual Ramp** scenario with **AI Predictive Routing**, and steps through 5 educational phases:
  1. *Phase 1:* Normal baseline traffic on initial path `S1 → S2 → S4`.
  2. *Phase 2:* Background traffic steadily ramps up on link `S2–S4`.
  3. *Phase 3:* The model completes its 10-sample warm-up window and forecasts impending congestion 5 seconds ahead.
  4. *Phase 4:* Weighted Dijkstra detects elevated congestion risk and reroutes to `S1 → S3 → S4` before buffer dropouts occur.
  5. *Phase 5:* Traffic stabilizes on the lower path with 0% packet loss.

### 2. Fair Routing Comparison
- Click **"⚖ Run comparison"** in the top action bar.
- In the comparison modal, click **"Run Simulation Comparison"**.
- The engine executes **Static**, **Reactive**, and **Predictive** modes under identical conditions (same topology, traffic schedule, duration, and random seed).
- Observe how Predictive routing achieves lower mean latency and near-zero packet loss compared to Static and Reactive modes.
- Click **"Export Comparison CSV"** or **"Export Comparison JSON"** to save benchmark data.

### 3. Exploring Larger Topologies
- Under **Network & Traffic Configuration**, change **Network topology**:
  - `4-Switch Diamond`: Classic benchmark network.
  - `6-Switch Ladder`: Dual-bottleneck topology with cross-ladder alternate paths.
  - `8-Switch Mesh Grid`: High path-diversity mesh grid.
- Notice how the interactive SVG updates dynamically, showing all nodes, switches, and link utilization.

---

## 6. Running Automated Tests

To run the complete automated test suite on Windows:

```powershell
.\.venv\Scripts\python.exe -m unittest tests/test_project.py
```

Expected result:
```text
Ran 15 tests in ~0.8s
OK
```
This verifies UTF-8 decoding, Dijkstra routing, model warm-up, cooldown/hysteresis stability, topology presets, input validation, offered vs transmitted load distinction, and OpenFlow wire layouts.
