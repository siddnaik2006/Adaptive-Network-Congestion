"""Deterministic paired SIMULATION experiments, never hardware results."""
import csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cn.engine import Engine
root=Path(__file__).resolve().parents[1]; rows=[]
for scenario in ['normal','ramp','burst','heavy']:
    for seed in range(5):
        for mode in ['static','reactive','predictive']:
            e=Engine(root,seed=seed);e.configure(mode,scenario)
            for _ in range(120):e.step()
            h=list(e.history);n=len(h)
            rows.append({'source':'analytical simulation','scenario':scenario,'seed':seed,'mode':mode,
                'latency_ms':sum(x['latency_ms'] for x in h)/n,'loss_percent':sum(x['loss_percent'] for x in h)/n,
                'throughput_mbps':sum(x['throughput_mbps'] for x in h)/n,
                'congested_samples':sum(x['max_utilization']>=.85 for x in h),'route_changes':len(e.events)})
out=root/'data/benchmark.csv'
with out.open('w', newline='', encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
print(f'Saved {len(rows)} SIMULATION experiments to {out}')
