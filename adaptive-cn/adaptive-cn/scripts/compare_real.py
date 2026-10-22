import csv,json,statistics
from pathlib import Path
root=Path(__file__).resolve().parents[1];groups={}
for path in sorted((root/'data/mininet').glob('*-summary.json')):
    d=json.loads(path.read_text(encoding='utf-8'))
    if d.get('source')!='Mininet packets':continue
    groups.setdefault((d['scenario'],d['mode']),[]).append(d)
rows=[]
for (scenario,mode),runs in groups.items():
    row={'source':'Mininet packets','scenario':scenario,'mode':mode,'runs':len(runs)}
    for metric in ['latency_ms','loss_percent','throughput_mbps','jitter_ms']:
        v=[d['metrics'][metric] for d in runs if d['metrics'].get(metric) is not None]
        row[metric+'_mean']=statistics.mean(v) if v else ''
        row[metric+'_std']=statistics.stdev(v) if len(v)>1 else ''
        row[metric+'_n']=len(v)
    rows.append(row)
if not rows:print('No measured Mininet summaries yet. Run sdn/topology.py on Linux first.')
else:
    path=root/'data/real-comparison.csv'
    with path.open('w', newline='', encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(f'Measured comparison saved: {path}')
