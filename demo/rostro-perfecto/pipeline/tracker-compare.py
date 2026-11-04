"""Compare tracker variants on provider coverage, ID stability AND purity vs automatic references
(SAM provider layer; reviewed client #407). No manual labels."""
from pathlib import Path
import gzip,json,collections
import numpy as np
ROOT=Path(__file__).resolve().parents[1];HV=ROOT/'outputs/heavy/roi-enhanced';OUT=ROOT/'outputs/roi-enhanced'
sam=json.loads((ROOT/'outputs/sam-provider/provider-sam-layer.json').read_text())['candidates'];st=np.array([c['sod'] for c in sam])
cl={}
with gzip.open(ROOT/'outputs/heavy/full-day/segment-02.jsonl.gz','rt') as f:
    for l in f:
        r=json.loads(l)
        if 40462<=r['sod']<=40942:
            for p in r['p']:
                if p[0]==407:cl[round(r['sod'],1)]=p[1:5]
def iou(a,b):
    x1,y1,x2,y2=max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3]);i=max(0,x2-x1)*max(0,y2-y1)
    return i/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-i+1e-12)
def best(r,ref):
    b=max(((iou(p[1:5],ref),p[0]) for p in r['p']),default=(0,None));return b[1] if b[0]>=.3 else None
def evalf(name):
    R=[json.loads(l) for l in gzip.open(HV/f'{name}.jsonl.gz','rt')]
    pv=[];cv=[]
    for r in R:
        j=int(np.argmin(np.abs(st-r['sod'])))
        if abs(st[j]-r['sod'])<=.25:pv.append((r['sod'],best(r,sam[j]['box'])))
        c=cl.get(round(r['sod'],1))
        if c:cv.append((r['sod'],best(r,c)))
    ids=[t for _,t in pv if t is not None]
    main=collections.Counter(ids).most_common(1)[0][0] if ids else None
    # purity: how often the provider's main ID is found on the client's box instead
    contam=sum(1 for _,t in cv if t is not None and t==main)
    cids=[t for _,t in cv if t is not None]
    return {'provider_detected_s':len({int(s) for s,t in pv if t is not None}),'provider_ids':len(set(ids)),'provider_switches':sum(a!=b for a,b in zip(ids,ids[1:])),
     'provider_main_id_share':round(ids.count(main)/len(ids),3) if ids else 0,'provider_main_id_on_client_frames':contam,
     'client_ids':len(set(cids)),'client_main_id_share':round(collections.Counter(cids).most_common(1)[0][1]/len(cids),3) if cids else 0,
     'total_track_ids':len({p[0] for r in R for p in r['p']})}
names=['A-full','B-full-roi','B-retracked','B-retracked-stitched','B-botsort','B-botsort-stitched','B-deepocsort','B-deepocsort-stitched']
res={n:evalf(n) for n in names}
(OUT/'tracker-comparison.json').write_text(json.dumps(res,indent=2))
cols=['provider_detected_s','provider_ids','provider_switches','provider_main_id_share','provider_main_id_on_client_frames','client_ids','client_main_id_share','total_track_ids']
print('variant'.ljust(24)+' '.join(c[:14].rjust(14) for c in cols))
for n,m in res.items():print(n.ljust(24)+' '.join(str(m[c]).rjust(14) for c in cols))
