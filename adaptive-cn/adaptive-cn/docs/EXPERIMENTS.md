# Evaluation and training protocol

## Three distinct kinds of evidence

1. **Synthetic model holdout:** model.json gives forecasting/classification metrics on held-out synthetic sequences.
2. **Analytical routing simulation:** benchmark.csv gives 60 controlled, paired toy-network trials. These are generated values, not Mininet observations.
3. **Mininet packet experiments:** data/mininet contains real kernel-network packet measurements, once you run the Linux runner. These are emulated-network results, not measurements of a physical campus network.

Never combine these categories in one unqualified result table.

## Measured-data training

Collect at least six independent sessions; 20–30 sessions across normal, ramp, burst, and heavy scenarios is preferable. First collect with static routing to preserve the congestion signal; dynamic interventions can otherwise hide the congestion your model is meant to learn. Use varied traffic schedules for stronger generalization; the shipped runner's fixed scenario schedules are a teaching starting point.

Train with `python scripts/train.py --csv data/mininet/*.csv`. Each whole session stays in one partition. The script uses the S2–S4 utilization sequence per session and splits sessions in supplied order: approximately 60% training, 20% calibration, 20% test. Deliberately distribute traffic scenarios across these partitions; ordering all ramps first and all bursts last can give misleading or very weak evaluation. The code rejects mixed synthetic CSVs and duplicate/missing tick sequences. Verify roughly one-second real timestamps before treating five samples as five seconds.

The model predicts a future utilization sample, not current congestion. Congestion labels are future utilization ≥85%. Precision/recall/F1 use estimated risk ≥60%; forecast errors use MAE and RMSE. Risk is estimated from held-out calibration residuals and can be unreliable under distribution shift. The bundled synthetic test F1 is modest; do not claim near-perfect detection.

## Routing evaluation

After training, freeze the model. Run additional experiments not used to fit, calibrate, or evaluate the predictor. For every scenario, run all three modes at least five times. Alternate mode order to reduce timing/order effects. Use the same topology, foreground/background schedule, link bandwidth/delay/queue, duration, and model file.

Report mean and variation in:

- Foreground receiver throughput (iperf3 receiver aggregate).
- Foreground UDP packet loss and jitter (iperf3 receiver aggregate).
- Ping RTT, including the number of unanswered probes rather than silently treating losses as zero latency.
- Route changes and switch confirmation delays, if separately instrumented.
- Congestion exposure measured on links. A 100% busy link is not itself proof of end-to-end packet loss.

`compare_real.py` summarizes available measured run files; it does not invent missing metrics or rerouting times. The runner records RTT samples including null timeouts. Current implementation does not measure queue occupancy or one-way delay. OpenFlow utilization uses transmitted byte deltas, so it cannot see offered traffic that was dropped before transmission. This limits how early saturation can be forecast.

## Expected tradeoffs

The longer route has a higher propagation delay, so rerouting under light load can make latency worse. Sudden bursts may defeat prediction. Cooldown reduces oscillation but can delay recovery. Similar results between predictive and reactive modes are valid findings. Investigate these outcomes rather than force a positive conclusion.
