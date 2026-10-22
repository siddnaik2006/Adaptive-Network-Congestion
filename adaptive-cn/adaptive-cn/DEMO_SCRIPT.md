# Demonstration Script & Professor Presentation Guide • Adaptive CN

This script provides an exact, step-by-step presentation workflow for demonstrating **AI-Powered Network Congestion Prediction & Routing** to an instructor, professor, or technical audience.

---

## 1. Elevator Pitch (30 Seconds)

> *"In traditional computer networks, routing protocols like OSPF use static link metrics and react only after congestion has caused buffer overflow and dropped packets.*
> *In this project, we built a Software-Defined Networking (SDN) system with an AI prediction engine. By monitoring time-series link utilization, our model forecasts congestion 5 seconds ahead. The SDN controller then dynamically reroutes critical foreground traffic using weighted Dijkstra with cooldown and hysteresis, preventing packet loss before it begins."*

---

## 2. Step-by-Step Live Demo Script

### Step 1: Open the Dashboard and Explain the Topology
1. Launch the lab using `start-demo.bat` or navigate to `http://127.0.0.1:8080`.
2. Point out the introductory card:
   > *"We send data between two computers: host H1 is sending critical foreground data to host H2. The upper path via switch S2 has 10 ms round-trip propagation delay. The lower path via switch S3 has 16 ms propagation delay."*
3. Show the **"Understand this experiment"** collapsible section to define Host, SDN Switch, Link, Congestion, Prediction, and Routing.
4. Point out the network diagram:
   - **H1:** Foreground sender (the transfer we want to protect).
   - **H2:** Foreground receiver.
   - **H3 & H4:** Background traffic sender and receiver competing for bottleneck capacity.
   - **SDN Controller & AI Predictor:** Rendered outside the data forwarding path with dashed control plane connections.

---

### Step 2: Run the Baseline (Static Routing Under Heavy Congestion)
1. In the controls panel:
   - Set **Routing strategy:** `Static Shortest Path`.
   - Set **Traffic scenario:** `Gradual Ramp` (or `Sustained Heavy Load`).
   - Click **"Apply inputs"** and then **"Start experiment"**.
2. **What happens on screen:**
   - Background traffic ramps up on link `S2–S4`.
   - Offered load exceeds 100% of link capacity.
   - The link turns **red (Congested)**.
   - In the charts, watch **Latency** jump from 20 ms to 60+ ms, **Packet Loss** climb to 10%–25%, and **Throughput** degrade.
   - Point to the Routing Audit timeline: *0 route changes occurred* because static routing is blind to dynamic network load.
3. Click **"Reset"**.

---

### Step 3: Run the AI Predictive Routing Demonstration
1. Click **"★ Start guided demo"** on the hero banner.
2. Direct the professor's attention to the **"What is happening now?"** panel:
   - **Phase 1 (Ticks 0–12):** Baseline traffic on `S1 → S2 → S4`. System is collecting initial sliding window observations (progress bar: *6 of 10 samples*).
   - **Phase 2 (Ticks 13–24):** Competing background traffic ramps up on link `S2–S4`.
   - **Phase 3 (Ticks 25–34):** The model observation window is full. The prediction engine outputs a 5-second forecast and estimates congestion risk climbing above 70%.
   - **Phase 4 (Ticks 35–45):** The weighted Dijkstra cost of `S2–S4` increases dramatically due to risk penalization. The controller detects that alternate path `S1 → S3 → S4` has significantly lower cost and executes a route change.
   - **Phase 5 (Ticks 45+):** Traffic now traverses `S1 → S3 → S4`. Notice that **Packet Loss drops to 0%**, **Throughput remains at 4.0 Mbps**, and latency stabilizes at base propagation delay.
3. Point to the **Routing Decision Rationale box**:
   > *"Notice the controller explains exactly why it rerouted: 'Congestion detected on current path. Rerouting to S1 → S3 → S4 (cost reduced from 92.4 to 16.0)'."*

---

### Step 4: Run the Fair Routing Comparison
1. Click **"⚖ Run comparison"** in the top action bar.
2. In the modal, click **"Run Simulation Comparison"**.
3. Walk the professor through the resulting benchmark table:

| Routing Strategy | Mean Latency | Mean Throughput | Mean Packet Loss | Route Changes | Congested Seconds |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Static** | ~48.2 ms | ~3.42 Mbps | ~14.5% | 0 | 45s |
| **Reactive** | ~32.1 ms | ~3.81 Mbps | ~4.7% | 2 | 22s |
| **Predictive** | ~24.5 ms | ~3.98 Mbps | ~0.4% | 1 | 8s |

4. **Explanation for the Professor:**
   > *"Static routing suffers severe packet loss because it never switches away from the congested bottleneck.*
   > *Reactive routing only switches after link buffers are already overwhelmed and packets are actively dropping.*
   > *Predictive routing acts before queue overflow occurs, preserving near-perfect throughput and avoiding route flapping."*

---

### Step 5: Demonstrate Topologies Beyond 4 Switches
1. Close the modal and select **Network topology:** `6-Switch Ladder` or `8-Switch Mesh Grid`.
2. Click **"Apply inputs"**.
3. Point out how the dynamic SVG redraws the multi-path topology with cross links and alternate routes.
4. Click on any link or switch to open the **Link Inspector**, showing live capacity, offered load, transmitted rate, 5-sample forecast, and congestion risk.

---

## 3. Explaining Technical Decisions to a Professor

### Q1: "Why Ridge Autoregressive Regression instead of a Deep LSTM or Transformer?"
> *"For line-rate telemetry polled at 1 Hz in an edge SDN controller, a Ridge autoregressive model with empirical residual risk calibration offers three decisive engineering advantages:*
> 1. *It runs deterministically in sub-millisecond execution time on standard CPU without PyTorch/GPU dependencies.*
> 2. *It requires minimal training data (sample-efficient) and avoids overfitting on non-stationary traffic spikes.*
> 3. *It uses empirical calibration residuals to output a true probabilistic risk score: $P(u_{t+5} + e \ge 0.85)$, which directly feeds into Dijkstra's cost function."*

---

### Q2: "How does your Dijkstra cost function prevent route flapping?"
> *"Route flapping (oscillating rapidly between paths) is prevented through three deliberate mechanisms:*
> 1. *Risk-penalized edge cost: $\text{cost} = \text{delay} + 80 \times \text{risk} + 20 \times \max(0, \text{forecast} - 0.65)$.*
> 2. *Cooldown timer: After any route modification, the controller enforces a 10-second cooldown period where further changes are locked.*
> 3. *Hysteresis threshold: A candidate route must offer at least a 15% cost reduction ($C_{\text{new}} < 0.85 \times C_{\text{current}}$) before a reroute is granted."*

---

### Q3: "Can the model predict sudden, unobserved traffic bursts?"
> *"No, and we explicitly document this in our model card. Autoregressive models predict trend continuations and ramps based on past observations. A sudden random burst that appears out of nowhere at $t=20$ cannot be foreseen before it begins. However, once the first spike observation enters the sliding window, the model immediately forecasts persistent congestion and initiates protective rerouting."*

---

### Q4: "What is the difference between Windows Simulation Mode and Mininet Mode?"
> *"On Windows, the system runs an analytical simulation engine with mathematical queuing formulas for latency, jitter, and buffer overflow packet loss. When deployed to a Linux machine with Open vSwitch and Mininet, the exact same controller code connects via OpenFlow 1.3 switch sockets, reads hardware TX byte counters, and verifies route changes through OpenFlow barrier replies."*

---

### Q5: "Why do you distinguish Offered Load from Transmitted Utilization?"
> *"When a link has a 10 Mbps physical capacity and traffic demand reaches 14 Mbps, the physical transmitter is saturated at 100% (10 Mbps), but the offered load is 140%. Labeling both as the same measurement creates confusion. In our engine, offered load tracks demand while utilization tracks transmitted rate, allowing the buffer queue modeling to accurately compute packet drop percentage."*
