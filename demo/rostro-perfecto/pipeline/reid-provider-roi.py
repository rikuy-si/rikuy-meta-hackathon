"""Score zoomed ROI detections against reviewed provider references; output a gated candidate path."""
from pathlib import Path
import json,sys,gzip,math
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/reid-provider-430';H=ROOT/'outputs/heavy/reid-provider-430';M=H/'roi-masked';M.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'scripts/vendor'));import animalx_embed as embed
inv=json.loads((OUT/'inventory.json').read_text());roi=json.loads((OUT/'roi-detections.json').read_text())
REF_IDS=[429,430,446,450]  # visually reviewed: same seated black-uniform worker, same station
refs=[H/c['file'] for c in inv['crops'] if c['track'] in REF_IDS]
client={}
with gzip.open(ROOT/'outputs/heavy/full-day/segment-02.jsonl.gz','rt') as f:
    for l in f:
        r=json.loads(l)
        if 40440<=r['sod']<40860:
            for p in r['p']:
                if p[0]==407 and r['sod']>=40462:client[round(r['sod'],1)]=p[1:5]
ckeys=np.array(sorted(client))
def iou(a,b):
    x1,y1,x2,y2=max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3]);i=max(0,x2-x1)*max(0,y2-y1)
    return i/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-i+1e-9)
items=[]
for fr in roi['frames']:
    cb=None
    if len(ckeys):
        j=int(np.argmin(np.abs(ckeys-fr['sod'])))
        if abs(ckeys[j]-fr['sod'])<=.6:cb=client[ckeys[j]]
    for d in fr['detections']:
        b=d['box']
        if (b[2]-b[0])*1920<20 or (b[3]-b[1])*1080<30:continue
        if cb and iou(b,cb)>.5:continue  # skip the reviewed client's own box
        im=Image.open(H/d['file']).convert('RGB');x0,y0=b[0]*1920,b[1]*1080;dr=ImageDraw.Draw(im)
        rx1,ry1,rx2,ry2=0-x0,45-y0,640-x0,115-y0
        if rx2>0 and ry2>0 and rx1<im.width and ry1<im.height:dr.rectangle((max(0,rx1),max(0,ry1),min(im.width,rx2),min(im.height,ry2)),fill=(127,127,127))
        p=M/Path(d['file']).name;im.save(p,quality=92);items.append({'sod':fr['sod'],**d,'masked':str(p)})
enc=embed.get('clipreid');enc.BS=64
R=enc(refs);E=enc([Path(i['masked']) for i in items]);S=(E@R.T)
for i,s in zip(items,S):i['score']=round(float(np.sort(s)[-3:].mean()),4)
# Controls: scores of the seated client reference crops and adjacent-worker #402 crops for calibration context only.
best={}
for i in items:
    k=round(i['sod'],2)
    if k not in best or i['score']>best[k]['score']:best[k]=i
path=sorted(best.values(),key=lambda x:x['sod'])
TH=0.90
acc=[p for p in path if p['score']>=TH]
seconds=len({int(p['sod']) for p in acc});total=int(roi['window'][1]-roi['window'][0])
res={'references':REF_IDS,'reference_crops':len(refs),'threshold_review_only':TH,'threshold_note':'Chosen from visual review of this case; not calibrated. Accepted frames are candidates for human review.','frames':len(roi['frames']),'scored_detections':len(items),'candidate_frames':len(acc),'candidate_seconds':seconds,'window_seconds':total,'path':[{k:p[k] for k in ['sod','box','confidence','score','file']} for p in path]}
(OUT/'roi-reid.json').write_text(json.dumps(res,indent=2))
base_sec=15
print('Baseline seat-proximal detection seconds 11:14:22-11:20:24:',base_sec,'/362')
print('ROI candidate seconds',seconds,'/',total,'frames',len(acc),'/',len(roi['frames']),'score quantiles',np.round(np.quantile([p['score'] for p in path],[.1,.5,.9]),3))
