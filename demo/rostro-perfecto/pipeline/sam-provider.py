"""SAM 3 streaming tracker over zoomed station ROI, auto-prompted by RF-DETR+ReID anchors.

No manual labels. Anchors: ROI-ReID provider candidates with score >= ANCHOR_TH, spaced >= ANCHOR_GAP s.
Held-out validation: other accepted candidates (never used as prompts) compared by IoU with SAM boxes.
The reviewed client (#407) is tracked as a second object so SAM separates the two people.
"""
from pathlib import Path
import json,gzip,time,argparse
import av,numpy as np,torch
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/sam-provider';H=ROOT/'outputs/heavy/sam-provider';OUT.mkdir(exist_ok=True);H.mkdir(parents=True,exist_ok=True)
ap=argparse.ArgumentParser();ap.add_argument('--anchor-gap',type=float,default=15);ap.add_argument('--anchor-th',type=float,default=.89);ap.add_argument('--tag',default='v1');a=ap.parse_args()
T0,T1,FPS=40440.0,40860.0,5.0
RX0,RY0,RX1,RY1=0.08,0.0,0.36,0.32;SCALE=2.0
W,Hh=1920,1080;cx0,cy0,cx1,cy1=round(RX0*W),round(RY0*Hh),round(RX1*W),round(RY1*Hh);CW,CH=(cx1-cx0)*SCALE,(cy1-cy0)*SCALE
def to_crop(b):return [(b[0]*W-cx0)*SCALE,(b[1]*Hh-cy0)*SCALE,(b[2]*W-cx0)*SCALE,(b[3]*Hh-cy0)*SCALE]
def to_norm(b):return [(b[0]/SCALE+cx0)/W,(b[1]/SCALE+cy0)/Hh,(b[2]/SCALE+cx0)/W,(b[3]/SCALE+cy0)/Hh]
layer=json.loads((ROOT/'outputs/reid-provider-430/provider-layer.json').read_text());cands=layer['candidates']
anchors=[];last=-1e9
for c in sorted(cands,key=lambda c:c['sod']):
    if c['score']>=a.anchor_th and c['sod']-last>=a.anchor_gap:anchors.append(c);last=c['sod']
anchor_t={round(c['sod'],1) for c in anchors};holdout=[c for c in cands if round(c['sod'],1) not in anchor_t]
client={};rv=json.loads((ROOT/'outputs/reid-407/review-layer.json').read_text())
with gzip.open(ROOT/'outputs/heavy/full-day/segment-02.jsonl.gz','rt') as f:
    for l in f:
        r=json.loads(l)
        if T0<=r['sod']<T1:
            for p in r['p']:
                if any(t['id']==p[0] and t['start_sod']<=r['sod']<=t['end_sod'] for t in rv['tracklets']):client[r['sod']]=p[1:5]
cks=sorted(client);client_anchors=[];last=-1e9
for t in cks:
    if t-last>=20:client_anchors.append((t,client[t]));last=t
from transformers import Sam3TrackerVideoModel,Sam3TrackerVideoProcessor
dev='cuda';proc=Sam3TrackerVideoProcessor.from_pretrained('facebook/sam3');model=Sam3TrackerVideoModel.from_pretrained('facebook/sam3',torch_dtype=torch.bfloat16).to(dev).eval()
# Keep accumulated per-frame state on CPU; GPU only holds the working set.
sess=proc.init_video_session(inference_device=dev,inference_state_device='cpu',video_storage_device='cpu',processing_device='cpu',dtype=torch.bfloat16)
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2];s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
c=av.open(str(ROOT/src['mp4_file']));st=c.streams.video[0];st.thread_type='AUTO';off=float((st.start_time or 0)*st.time_base)
c.seek(int((T0-s0+off)/st.time_base),stream=st,backward=True)
nxt=T0;idx=0;rows=[];ai=0;ci=0;started={1:False,2:False};t_start=time.time()
masks_dir=H/a.tag;masks_dir.mkdir(exist_ok=True)
with torch.inference_mode():
    for fr in c.decode(st):
        sod=s0+float(fr.pts*st.time_base)-off
        if sod<nxt-.02:continue
        if sod>=T1:break
        nxt+=1/FPS
        img=fr.to_image().crop((cx0,cy0,cx1,cy1)).resize((round(CW),round(CH)),Image.BICUBIC)
        inp=proc(images=img,device=dev,return_tensors='pt')
        objs=[];boxes=[]
        while ai<len(anchors) and anchors[ai]['sod']<=sod+.1:
            if abs(anchors[ai]['sod']-sod)<=.25:objs.append(1);boxes.append(to_crop(anchors[ai]['box']))
            ai+=1
        while ci<len(client_anchors) and client_anchors[ci][0]<=sod+.1:
            if abs(client_anchors[ci][0]-sod)<=.25:objs.append(2);boxes.append(to_crop(client_anchors[ci][1]))
            ci+=1
        for o,b in zip(objs,boxes):
            proc.add_inputs_to_inference_session(inference_session=sess,frame_idx=idx,obj_ids=o,input_boxes=[[b]],original_size=inp.original_sizes[0]);started[o]=True
        # idx must equal the session's internal frame counter: only count frames actually streamed.
        if not any(started.values()):continue
        out=model(inference_session=sess,frame=inp.pixel_values[0].to(dev,torch.bfloat16))
        m=proc.post_process_masks([out.pred_masks],original_sizes=inp.original_sizes,binarize=True)[0]
        rec={'sod':round(sod,3),'idx':idx,'prompted':objs,'objects':{}}
        for k,oid in enumerate(out.object_ids):
            mk=m[k,0].cpu().numpy().astype(bool);area=int(mk.sum())
            if area<150:rec['objects'][str(oid)]=None;continue
            ys,xs=np.nonzero(mk);bb=[float(xs.min()),float(ys.min()),float(xs.max()),float(ys.max())]
            rec['objects'][str(oid)]={'box':[round(v,5) for v in to_norm(bb)],'area_px_crop':area}
            if oid==1 and idx%5==0:Image.fromarray((mk*255).astype(np.uint8)).save(masks_dir/f'p_{round(sod*1000):08d}.png')
        rows.append(rec);idx+=1
        if idx%200==0:print('frame',idx,round(sod,1),round(idx/(time.time()-t_start),2),'fps',flush=True)
c.close()
def iou(a,b):
    x1,y1,x2,y2=max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3]);i=max(0,x2-x1)*max(0,y2-y1)
    return i/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-i+1e-12)
ts=np.array([r['sod'] for r in rows]);ious=[];miss=0
for h in holdout:
    j=int(np.argmin(np.abs(ts-h['sod'])))
    if abs(ts[j]-h['sod'])>.15:continue
    o=rows[j]['objects'].get('1')
    if not o:miss+=1;ious.append(0.0);continue
    ious.append(iou(o['box'],h['box']))
present=[r for r in rows if r['objects'].get('1')];chair=[r for r in present if 40462<=r['sod']<=40824]
res={'tag':a.tag,'method':'SAM 3 tracker video (streaming, bf16) on 2x zoomed ROI, 5 fps; auto box prompts from RF-DETR ROI + CLIP-ReID anchors; client tracked as second object','window':[T0,T1],'anchor_threshold':a.anchor_th,'anchor_gap_s':a.anchor_gap,'provider_anchors':len(anchors),'client_anchors':len(client_anchors),'holdout_candidates':len(ious),'holdout_iou_median':round(float(np.median(ious)),3) if ious else None,'holdout_iou_ge_0_5':round(float(np.mean(np.array(ious)>=.5)),3) if ious else None,'holdout_missed':miss,'frames':len(rows),'provider_present_frames':len(present),'chair_episode_provider_seconds':len({int(r['sod']) for r in chair}),'chair_episode_seconds':362,'runtime_s':round(time.time()-t_start,1),'no_manual_labels':True,'limitations':['Self-consistency validation against held-out detector+ReID candidates, not ground truth.','Mask presence does not prove correct identity; drift checked separately with ReID.']}
(OUT/f'{a.tag}-summary.json').write_text(json.dumps(res,indent=2));(OUT/f'{a.tag}-track.json').write_text(json.dumps(rows))
print(json.dumps(res,indent=1))
