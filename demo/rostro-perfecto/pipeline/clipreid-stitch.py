"""Offline tracklet stitching with CLIP-ReID on any track file. Merges A->B when: B starts after A ends
(no temporal overlap), gap <= MAX_GAP s, endpoint distance small, and appearance cosine >= TH.
Greedy, best score first; a track gets at most one successor and one predecessor."""
from pathlib import Path
import gzip,json,sys,math,collections
import av,numpy as np
import os
ROOT=Path(__file__).resolve().parents[1];HV=ROOT/'outputs/heavy/roi-enhanced'/os.environ.get('RPP_TAG','');C=HV/'stitch-crops';C.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'scripts/vendor'));import animalx_embed as embed
name=sys.argv[1] if len(sys.argv)>1 else 'B-retracked';TH=float(sys.argv[2]) if len(sys.argv)>2 else .82;MAX_GAP=20;MAX_DIST=.12
R=[json.loads(l) for l in gzip.open(HV/f'{name}.jsonl.gz','rt')]
tr=collections.defaultdict(list)
for r in R:
    for p in r['p']:tr[p[0]].append((r['sod'],p[1:5],p[5]))
tr={k:v for k,v in tr.items() if len(v)>=3}
# up to 6 crops per tracklet, from the 6 most confident and reasonably sized boxes
jobs=collections.defaultdict(list)
for t,v in tr.items():
    good=sorted([x for x in v if (x[1][2]-x[1][0])*1920>=16 and (x[1][3]-x[1][1])*1080>=28],key=lambda x:-x[2])[:6] or v[:2]
    for s,b,_ in good:jobs[round(s,3)].append((t,b))
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2];s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
ts=sorted(jobs);c=av.open(str(ROOT/src['mp4_file']));st=c.streams.video[0];st.thread_type='AUTO';off=float((st.start_time or 0)*st.time_base);c.seek(int((ts[0]-s0+off)/st.time_base),stream=st,backward=True)
paths=[];owner=[];k=0
for fr in c.decode(st):
    if k>=len(ts):break
    sod=s0+float(fr.pts*st.time_base)-off
    if sod<ts[k]-.03:continue
    im=fr.to_image()
    while k<len(ts) and ts[k]<=sod+.03:
        for t,b in jobs[ts[k]]:
            p=C/f'{name}_{t}_{round(ts[k]*1000)}.jpg';im.crop((round(b[0]*1920),round(b[1]*1080),round(b[2]*1920),round(b[3]*1080))).save(p,quality=90);paths.append(p);owner.append(t)
        k+=1
c.close()
enc=embed.get('clipreid');enc.BS=64;E=enc(paths);owner=np.array(owner)
emb={t:E[owner==t].mean(0)/np.linalg.norm(E[owner==t].mean(0)) for t in set(owner)}
ctr=lambda b:((b[0]+b[2])/2,(b[1]+b[3])/2)
pairs=[]
for a,va in tr.items():
    for b,vb in tr.items():
        if a==b or a not in emb or b not in emb:continue
        gap=vb[0][0]-va[-1][0]
        if not 0<gap<=MAX_GAP:continue
        d=math.dist(ctr(va[-1][1]),ctr(vb[0][1]))
        if d>MAX_DIST+0.01*gap:continue
        s=float(emb[a]@emb[b])
        if s>=TH:pairs.append((s,a,b,gap,d))
pairs.sort(reverse=True);nxt={};prv={}
for s,a,b,gap,d in pairs:
    if a in nxt or b in prv:continue
    # forbid cycles / temporal overlap within a chain
    nxt[a]=b;prv[b]=a
root={}
for t in tr:
    r=t
    while r in prv:r=prv[r]
    root[t]=r
out=HV/f'{name}-stitched.jsonl.gz'
with gzip.open(out,'wt') as f:
    for r in R:f.write(json.dumps({**r,'p':[[root.get(p[0],p[0]),*p[1:]] for p in r['p']]},separators=(',',':'))+'\n')
print(name,'tracklets',len(tr),'candidate pairs',len(pairs),'merges',len(nxt),'->',out.name)
