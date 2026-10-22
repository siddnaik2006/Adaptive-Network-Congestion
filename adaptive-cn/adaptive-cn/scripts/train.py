import argparse,csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cn.model import train,synthetic_sequences
p=argparse.ArgumentParser();p.add_argument('--csv',nargs='+');p.add_argument('--output',default='data/model.json');a=p.parse_args()
if a.csv:
    groups={}
    for filename in a.csv:
        with open(filename, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row['source']!='mininet':raise SystemExit('Real training requires only mininet-source CSV files')
                groups.setdefault((filename,row['session'],row['link']),[]).append((int(row['tick']),float(row['utilization'])))
    seq=[]
    for k,rows in groups.items():
        rows.sort(); ticks=[t for t,u in rows]
        if len(set(ticks))!=len(ticks) or any(b-a!=1 for a,b in zip(ticks,ticks[1:])):raise SystemExit('Non-contiguous or duplicate telemetry ticks')
    # Split by whole sessions, so correlated links from one run never cross partitions.
    sessions=list(dict.fromkeys((k[0],k[1]) for k in groups))
    if len(sessions)<6:raise SystemExit('Collect at least six independent Mininet sessions before real-data training')
    # Each sequence is one session's upper bottleneck; fixed one-second polling required.
    for filename,session in sessions:
        rows=groups.get((filename,session,'s2-s4'),[])
        if len(rows)>16:seq.append([u for t,u in rows])
    provenance='Mininet measured one-second port utilization; independent session split'
else:seq=synthetic_sequences();provenance='SYNTHETIC demonstration data, not real network evidence'
print(json.dumps(train(seq,a.output,provenance),indent=2))
