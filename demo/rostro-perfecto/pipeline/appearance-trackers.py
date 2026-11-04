"""Appearance-aware tracking on saved Enfocado (full+ROI) detections: BoT-SORT and Deep OC-SORT
(BoxMOT, OSNet-AIN MSMT17 ReID, CMC on). Frames are re-decoded for crops; RF-DETR is not rerun."""
from pathlib import Path
import gzip,json,time,sys
import av,numpy as np
import os
ROOT=Path(__file__).resolve().parents[1];HV=ROOT/'outputs/heavy/roi-enhanced'/os.environ.get('RPP_TAG','');OUT=ROOT/'outputs/roi-enhanced'
from boxmot import BotSort,DeepOcSort,BotSortConfig,DeepOcSortConfig,ReIDConfig
raw=[json.loads(l) for l in gzip.open(HV/'B-raw.jsonl.gz','rt')];times=[r['sod'] for r in raw]
reid=lambda:ReIDConfig('osnet_ain_x1_0_msmt17',device='cuda:0',precision='fp16')
# 5 fps: frame-based ages scaled from 30 fps defaults (~10 s lost buffer).
trk={'botsort':BotSort(BotSortConfig(max_age=50,max_lost_frames=50,min_hits=2,track_high_thresh=.45,track_low_thresh=.1,new_track_thresh=.5,det_thresh=.3,appearance_thresh=.35,proximity_thresh=.5),reid=reid()),
     'deepocsort':DeepOcSort(DeepOcSortConfig(max_age=50,min_hits=2,det_thresh=.3,iou_threshold=.2,w_association_emb=.75),reid=reid())}
trk={k:v for k,v in trk.items() if k in os.environ.get('RPP_TRACKERS','botsort,deepocsort').split(',')}
fh={k:gzip.open(HV/f'B-{k}.jsonl.gz','wt') for k in trk}
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2];s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
c=av.open(str(ROOT/src['mp4_file']));st=c.streams.video[0];st.thread_type='AUTO';off=float((st.start_time or 0)*st.time_base);c.seek(int((times[0]-s0+off)/st.time_base),stream=st,backward=True)
k=0;t0=time.time();W,H=1920,1080
for fr in c.decode(st):
    if k>=len(raw):break
    sod=s0+float(fr.pts*st.time_base)-off
    if sod<times[k]-.03:continue
    img=fr.to_ndarray(format='bgr24');r=raw[k]
    d=np.array(r['d'],dtype=np.float32).reshape(-1,5)
    dets=np.concatenate([d,np.zeros((len(d),1),np.float32)],1) if len(d) else np.zeros((0,6),np.float32)
    for name,t in trk.items():
        out=t.update(dets,img)
        out=np.asarray(out) if not isinstance(out,tuple) else np.asarray(out[0])
        p=[[int(o[4]),*[round(float(v),5) for v in o[:4]/np.array([W,H,W,H])],round(float(o[5]),4)] for o in out] if len(out) else []
        fh[name].write(json.dumps({'sod':r['sod'],'raw_people':len(d),'p':p},separators=(',',':'))+'\n')
    k+=1
    if k%500==0:print(k,'/',len(raw),round(k/(time.time()-t0),1),'fps',flush=True)
c.close();[f.close() for f in fh.values()]
print('done',k,'frames',round(time.time()-t0,1),'s')
