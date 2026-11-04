"""Stable provider track: per-box positive/negative CLIP-ReID score + Viterbi + One-Euro smoothing + short gap fill.

Candidates: boxes (Enfocado layer) whose center is in the expanded station zone (provider workplace).
Emission: s = top5 sim(positive gallery) - top5 sim(negative gallery).
Negatives (automatic, from reviewed errors): reviewed client crops, man in grey/jeans (#202/#255 full70), lying clients.
Viterbi states: each candidate box, plus ABSENT. Transitions penalize jumps in position/size and entering/leaving.
Output: one box per sampled frame (or none), with flags observed/interpolated.
usage: RPP_TAG=full70 stabilize-provider.py T0 T1 OUTNAME
"""
from pathlib import Path
import gzip,json,sys,os,math,collections
import av,numpy as np
ROOT=Path(__file__).resolve().parents[1];TAG=os.environ.get('RPP_TAG','full70');HV=ROOT/'outputs/heavy/roi-enhanced'/TAG;OUT=ROOT/'outputs/provider-stable';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'scripts/vendor'));import animalx_embed as embed
T0,T1,NAME=float(sys.argv[1]),float(sys.argv[2]),sys.argv[3]
ZONE=(0.05,0.0,0.40,0.42);EMB_EVERY=2  # embed every 2nd sample (2.5 fps); emissions carried to neighbours
R=[json.loads(l) for l in gzip.open(HV/'B-deepocsort-stitched.jsonl.gz','rt')];R=[r for r in R if T0<=r['sod']<T1]
ctr=lambda b:((b[0]+b[2])/2,(b[1]+b[3])/2)
cand=[[p for p in r['p'] if ZONE[0]<=ctr(p[1:5])[0]<=ZONE[2] and ZONE[1]<=ctr(p[1:5])[1]<=ZONE[3] and (p[3]-p[1])*1920>=14 and (p[4]-p[2])*1080>=20] for r in R]
C=ROOT/'outputs/heavy/provider-stable'/NAME;C.mkdir(parents=True,exist_ok=True)
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2];s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
need={i for i in range(len(R)) if i%EMB_EVERY==0 and cand[i]}
c=av.open(str(ROOT/src['mp4_file']));st=c.streams.video[0];st.thread_type='AUTO';off=float((st.start_time or 0)*st.time_base);c.seek(int((R[0]['sod']-s0+off)/st.time_base),stream=st,backward=True)
paths=[];key=[];i=0;order=sorted(need)
for fr in c.decode(st):
    if i>=len(order):break
    sod=s0+float(fr.pts*st.time_base)-off;t=R[order[i]]['sod']
    if sod<t-.03:continue
    im=fr.to_image()
    while i<len(order) and R[order[i]]['sod']<=sod+.03:
        for k,p in enumerate(cand[order[i]]):
            b=[round(p[1]*1920),round(p[2]*1080),round(p[3]*1920),round(p[4]*1080)];q=C/f'{order[i]}_{k}.jpg';im.crop(b).save(q,quality=88);paths.append(q);key.append((order[i],p[0]))
        i+=1
c.close()
pos=[p for p in sorted((ROOT/'outputs/heavy/sam-provider/v2-crops').glob('*.jpg'))]
drift={round(d['sod']*1000):d['flag'] for d in json.loads((ROOT/'outputs/sam-provider/v2-drift.json').read_text())['rows']}
pos=[p for p in pos if drift.get(int(p.stem))=='provider-like']
inv=json.loads((ROOT/'outputs/reid-provider-430/inventory.json').read_text())
pos+=[ROOT/'outputs/heavy/reid-provider-430'/x['file'] for x in inv['crops'] if x['track'] in (429,430,446,450,456)]
gc=ROOT/'outputs/heavy/roi-enhanced/full70/group-crops'
neg=[p for p in gc.glob('*.jpg') if p.name.split('_')[0] in ('202','255','290','293')]
ci=json.loads((ROOT/'outputs/reid-407/inventory.json').read_text());neg+=[ROOT/'outputs/heavy/reid-407'/x['file'] for x in ci['crops'] if x['track']==407 and x['sod']>=40462]
neg+=[p for p in gc.glob('*.jpg') if p.name.split('_')[0] in ('619','688') and 41280<=int(p.stem.split('_')[1])/1000<=41420]  # lying clients 11:48-11:50
enc=embed.get('clipreid');enc.BS=96
E=enc(paths);P=enc(pos);N=enc(neg)
s=np.sort(E@P.T,1)[:,-5:].mean(1)-np.sort(E@N.T,1)[:,-5:].mean(1)
score=collections.defaultdict(dict)
for (fi,tid),v in zip(key,s):score[fi][tid]=float(v)
# emissions for every sample: carry nearest embedded score of same track id (<=1 sample away), else neutral
em=[]
for fi in range(len(R)):
    row={}
    for p in cand[fi]:
        v=score.get(fi,{}).get(p[0])
        if v is None:
            for d in (1,-1,2,-2):
                v=score.get(fi+d,{}).get(p[0])
                if v is not None:break
        row[p[0]]=v
    em.append(row)
vals=np.array([v for r in em for v in r.values() if v is not None])
A,S0,JUMP,SIZE,ENTER=60.0,0.0,6.0,2.0,4.0
NEUTRAL=-0.02
states=[[('ABSENT',None)]+[(p[0],p[1:5]) for p in cand[fi]] for fi in range(len(R))]
def emis(fi,st):
    if st[0]=='ABSENT':return 0.0
    v=em[fi].get(st[0]);v=NEUTRAL if v is None else v
    return A*(v-S0)
def trans(a,b):
    if a[0]=='ABSENT' and b[0]=='ABSENT':return 0.0
    if a[0]=='ABSENT' or b[0]=='ABSENT':return -ENTER
    (ax,ay),(bx,by)=ctr(a[1]),ctr(b[1]);h=max(a[1][3]-a[1][1],.02)
    sa=(a[1][2]-a[1][0])*(a[1][3]-a[1][1]);sb=(b[1][2]-b[1][0])*(b[1][3]-b[1][1])
    return -JUMP*math.hypot(ax-bx,ay-by)/h-SIZE*abs(math.log((sb+1e-6)/(sa+1e-6)))+(0.5 if a[0]==b[0] else 0)
V=[emis(0,x) for x in states[0]];back=[]
for fi in range(1,len(R)):
    nv=[];bk=[]
    for b in states[fi]:
        best=max(range(len(states[fi-1])),key=lambda j:V[j]+trans(states[fi-1][j],b));nv.append(V[best]+trans(states[fi-1][best],b)+emis(fi,b));bk.append(best)
    V=nv;back.append(bk)
j=int(np.argmax(V));path=[j]
for bk in reversed(back):j=bk[j];path.append(j)
path=path[::-1]
seq=[(R[fi]['sod'],states[fi][path[fi]]) for fi in range(len(R))]
# One-Euro-style smoothing (fixed alpha EMA forward+backward) on observed boxes, gap fill <= 3 s
obs=[(t,np.array(b)) for t,(tid,b) in seq if tid!='ABSENT']
out=[];a=.35
if obs:
    arr=np.array([b for _,b in obs]);f=arr.copy()
    for k in range(1,len(f)):f[k]=a*arr[k]+(1-a)*f[k-1]
    g=f.copy()
    for k in range(len(f)-2,-1,-1):g[k]=a*f[k]+(1-a)*g[k+1]
    sm={round(t,3):g[k] for k,(t,_) in enumerate(obs)};ts=[t for t,_ in obs]
    for t,(tid,b) in seq:
        if tid!='ABSENT':out.append({'sod':t,'box':[round(float(v),5) for v in sm[round(t,3)]],'kind':'observed','track':tid,'score':em[[r['sod'] for r in R].index(t)].get(tid)})
    filled=[]
    for (t1,b1),(t2,b2) in zip(obs,obs[1:]):
        if .25<t2-t1<=3.0:
            for t in [x['sod'] for x in ({'sod':r['sod']} for r in R) if t1<x['sod']<t2]:
                w=(t-t1)/(t2-t1);bb=(1-w)*sm[round(t1,3)]+w*sm[round(t2,3)];filled.append({'sod':t,'box':[round(float(v),5) for v in bb],'kind':'interpolated'})
    out+=filled;out.sort(key=lambda x:x['sod'])
present={int(x['sod']) for x in out}
res={'window':[T0,T1],'tag':TAG,'samples':len(R),'embedded_crops':len(paths),'pos_gallery':len(pos),'neg_gallery':len(neg),'params':{'A':A,'S0':S0,'JUMP':JUMP,'SIZE':SIZE,'ENTER':ENTER,'NEUTRAL':NEUTRAL,'zone':ZONE},
     'score_quantiles':np.quantile(vals,[.1,.25,.5,.75,.9]).round(4).tolist(),'present_seconds':len(present),'observed':sum(x['kind']=='observed' for x in out),'interpolated':sum(x['kind']=='interpolated' for x in out),'track':out}
(OUT/f'{NAME}.json').write_text(json.dumps(res))
print({k:v for k,v in res.items() if k!='track'})
