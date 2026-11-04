"""Zoomed ROI RF-DETR pass over the reviewed client's workstation; baseline is not modified."""
from pathlib import Path
import json,math
import av,numpy as np,torch
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/reid-provider-430';H=ROOT/'outputs/heavy/reid-provider-430';C=H/'roi-crops';C.mkdir(parents=True,exist_ok=True)
T0,T1,FPS=40440.0,40860.0,2.0  # 11:14:00-11:21:00
X0,Y0,X1,Y1=0.08,0.0,0.36,0.32  # normalized ROI around station
SCALE=2.5;THRESH=0.25
from rfdetr import RFDETRMedium
model=RFDETRMedium(pretrain_weights=str(ROOT/'models/rf-detr-medium.pth'));model.inference(compile=False,dtype=torch.float16)
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2]
s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
c=av.open(str(ROOT/src['mp4_file']));s=c.streams.video[0];s.thread_type='AUTO';off=float((s.start_time or 0)*s.time_base)
c.seek(int((T0-s0+off)/s.time_base),stream=s,backward=True)
nxt=T0;rows=[];buf=[]
def flush():
    if not buf:return
    dets=model.predict([b[2] for b in buf],threshold=THRESH)
    if not isinstance(dets,list):dets=[dets]
    for (sod,full,roi,box),d in zip(buf,dets):
        d=d[d.class_id==1];rw,rh=roi.size;fx0,fy0,fx1,fy1=box
        out=[]
        for k,(xy,cf) in enumerate(zip(d.xyxy,d.confidence)):
            gx1=fx0+xy[0]/SCALE;gy1=fy0+xy[1]/SCALE;gx2=fx0+xy[2]/SCALE;gy2=fy0+xy[3]/SCALE
            nb=[gx1/1920,gy1/1080,gx2/1920,gy2/1080]
            name=f'{round(sod*1000):08d}_{k}.jpg';full.crop((round(gx1),round(gy1),round(gx2),round(gy2))).save(C/name,quality=92)
            out.append({'box':[round(float(v),5) for v in nb],'confidence':round(float(cf),4),'file':'roi-crops/'+name})
        rows.append({'sod':round(sod,3),'detections':out})
    buf.clear()
for fr in c.decode(s):
    sod=s0+float(fr.pts*s.time_base)-off
    if sod<nxt-.02:continue
    if sod>=T1:break
    nxt+=1/FPS;full=fr.to_image();box=(round(X0*1920),round(Y0*1080),round(X1*1920),round(Y1*1080))
    roi=full.crop(box).resize((round((box[2]-box[0])*SCALE),round((box[3]-box[1])*SCALE)),Image.BICUBIC)
    buf.append((sod,full,roi,box))
    if len(buf)>=8:flush()
flush();c.close()
(OUT/'roi-detections.json').write_text(json.dumps({'window':[T0,T1],'fps':FPS,'roi_normalized':[X0,Y0,X1,Y1],'scale':SCALE,'threshold':THRESH,'model':'RFDETRMedium FP16','note':'Experimental supplementary detector pass; full-frame baseline remains authoritative and unchanged.','frames':rows},indent=2))
n=sum(len(r['detections']) for r in rows);print('ROI frames',len(rows),'detections',n,'frames with any detection',sum(bool(r['detections']) for r in rows))
