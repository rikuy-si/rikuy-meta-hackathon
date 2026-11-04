"""Full-frame + provider-station ROI RF-DETR, merged, re-tracked with ByteTrack.

A = full frame only (re-run, same settings as baseline) ; B = full frame + 2.5x station ROI.
Both are run on the same sampled frames so the comparison is apples-to-apples.
Window 11:02:54-11:25:19 (app 19:52-42:17). Baseline files are not modified.
"""
from pathlib import Path
import gzip,json,time
import av,numpy as np,torch,supervision as sv
from PIL import Image
import os
TAG=os.environ.get('RPP_TAG','')
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/roi-enhanced'/TAG;HV=ROOT/'outputs/heavy/roi-enhanced'/TAG;OUT.mkdir(parents=True,exist_ok=True);HV.mkdir(parents=True,exist_ok=True)
T0,T1=float(os.environ.get('RPP_T0',39774)),float(os.environ.get('RPP_T1',41119))
RX0,RY0,RX1,RY1=0.08,0.0,0.36,0.32;SCALE=2.5;EDGE=0.02
TH_FULL,TH_ROI,NMS_IOU,BATCH=0.35,0.30,0.5,8
times=[]
with gzip.open(ROOT/'outputs/heavy/full-day/segment-02.jsonl.gz','rt') as f:
    for l in f:
        r=json.loads(l)
        if T0<=r['sod']<T1:times.append(r['sod'])
from rfdetr import RFDETRMedium
from trackers import ByteTrackTracker
model=RFDETRMedium(pretrain_weights=str(ROOT/'models/rf-detr-medium.pth'));model.inference(compile=False,dtype=torch.float16)
mk=lambda:ByteTrackTracker(frame_rate=5,lost_track_buffer=20,track_activation_threshold=.5,high_conf_det_threshold=.5)
trA,trB=mk(),mk()
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2];s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
c=av.open(str(ROOT/src['mp4_file']));st=c.streams.video[0];st.thread_type='AUTO';off=float((st.start_time or 0)*st.time_base);c.seek(int((T0-s0+off)/st.time_base),stream=st,backward=True)
W,H=1920,1080;bx=(round(RX0*W),round(RY0*H),round(RX1*W),round(RY1*H))
outA=gzip.open(HV/'A-full.jsonl.gz','wt');rawA=gzip.open(HV/'A-raw.jsonl.gz','wt');rawB=gzip.open(HV/'B-raw.jsonl.gz','wt');outB=gzip.open(HV/'B-full-roi.jsonl.gz','wt');buf=[];k=0;t_start=time.time();stats={'roi_added':0,'frames':0}
def person(d):return d[d.class_id==1]
def write(fh,sod,raw,trk):
    p=[[int(t),*[round(float(v),5) for v in xy/np.array([W,H,W,H])],round(float(cf),4)] for t,xy,cf in zip(trk.tracker_id,trk.xyxy,trk.confidence) if t is not None and int(t)>=0]
    fh.write(json.dumps({'sod':round(sod,3),'raw_people':int(raw),'p':p},separators=(',',':'))+'\n')
def flush():
    if not buf:return
    fulls=[b[1] for b in buf];rois=[b[2] for b in buf];n=len(buf)
    pad=lambda L:L+[L[-1]]*(BATCH-len(L))
    dF=model.predict(fulls,threshold=TH_FULL);dR=model.predict(rois,threshold=TH_ROI)
    dF=dF if isinstance(dF,list) else [dF];dR=dR if isinstance(dR,list) else [dR]
    for (sod,_,_),f,r in zip(buf,dF,dR):
        f=person(f);r=person(r)
        f=sv.Detections(xyxy=f.xyxy,confidence=f.confidence,class_id=f.class_id)
        if len(r):
            xy=r.xyxy/SCALE+np.array([bx[0],bx[1],bx[0],bx[1]])
            # drop ROI boxes touching ROI border (truncated people); full frame covers those
            nx=xy/np.array([W,H,W,H]);keep=(nx[:,0]>RX0+EDGE)&(nx[:,2]<RX1-EDGE)&(nx[:,3]<RY1-EDGE)
            r=sv.Detections(xyxy=xy[keep],confidence=r.confidence[keep],class_id=r.class_id[keep])
        merged=sv.Detections.merge([f,r]) if len(r) else f
        before=len(f)+len(r)
        if len(merged):merged=merged.with_nms(threshold=NMS_IOU,class_agnostic=True)
        stats['roi_added']+=max(0,len(merged)-len(f))
        for fh,d in ((rawA,f),(rawB,merged)):fh.write(json.dumps({'sod':round(sod,3),'d':[[*[round(float(v),2) for v in xy],round(float(cf),4)] for xy,cf in zip(d.xyxy,d.confidence)]},separators=(',',':'))+'\n')
        write(outA,sod,len(f),trA.update(f));write(outB,sod,len(merged),trB.update(merged));stats['frames']+=1
    buf.clear()
for fr in c.decode(st):
    if k>=len(times):break
    sod=s0+float(fr.pts*st.time_base)-off
    if sod<times[k]-.03:continue
    while k<len(times) and times[k]<sod-.03:k+=1
    if k>=len(times):break
    if abs(sod-times[k])>.03:continue
    im=fr.to_image();roi=im.crop(bx).resize((round((bx[2]-bx[0])*SCALE),round((bx[3]-bx[1])*SCALE)),Image.BICUBIC)
    buf.append((times[k],im,roi));k+=1
    if len(buf)>=BATCH:flush()
    if k%500==0:print('frames',k,'/',len(times),round(k/(time.time()-t_start),1),'fps',flush=True)
flush();c.close();outA.close();outB.close();rawA.close();rawB.close()
stats.update(window=[T0,T1],sampled_frames_expected=len(times),runtime_s=round(time.time()-t_start,1),roi_normalized=[RX0,RY0,RX1,RY1],scale=SCALE,thresholds={'full':TH_FULL,'roi':TH_ROI,'nms_iou':NMS_IOU},tracker='trackers ByteTrack, same params as baseline')
(OUT/'run.json').write_text(json.dumps(stats,indent=2));print(stats)
