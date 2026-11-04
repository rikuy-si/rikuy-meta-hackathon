#!/usr/bin/env python3
"""RF-DETR people detection + anonymous short-term ByteTrack over every day segment.

Streams video, never dumps all frames or crops people. Covers the requested local
wall-clock interval at a declared sampling rate, not every native video frame.
"""
import argparse,collections,datetime as dt,gzip,hashlib,importlib.metadata,json,math,os,sys,time
from pathlib import Path
import av,numpy as np,torch

ROOT=Path(__file__).resolve().parents[1]
def atomic(path,value):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2));temp.replace(path)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',type=float,default=0);ap.add_argument('--end',type=float,default=86400)
    ap.add_argument('--fps',type=float,default=5);ap.add_argument('--batch',type=int,default=8);ap.add_argument('--threshold',type=float,default=.35)
    ap.add_argument('--tag',default='full-day');a=ap.parse_args()
    if not (0<=a.start<a.end<=86400 and 0<a.fps<=20 and a.batch>0):raise ValueError('Invalid interval/rate/batch')
    if not a.tag.replace('-','').isalnum():raise ValueError('Invalid output tag')
    out=ROOT/'outputs/vision'/a.tag;heavy=ROOT/'outputs/heavy'/a.tag;out.mkdir(parents=True,exist_ok=True);heavy.mkdir(parents=True,exist_ok=True)
    versions={k:importlib.metadata.version(k) for k in ['torch','rfdetr','trackers','av','supervision']}
    settings={'model':'RFDETRMedium','inference_dtype':'float16','person_class_id':1,'fps':a.fps,'batch':a.batch,'threshold':a.threshold,'start_sod':a.start,'end_sod':a.end,'versions':versions,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    manifest=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())
    if manifest['state']!='complete':raise RuntimeError('Source downloads not complete')
    day=dt.datetime(2026,11,3);segments=[]
    for i,r in enumerate(manifest['recordings']):
        start=(dt.datetime.fromisoformat(r['startTime'].rstrip('Z'))-day).total_seconds()
        end=(dt.datetime.fromisoformat(r['endTime'].rstrip('Z'))-day).total_seconds()
        if end>a.start and start<a.end:
            segments.append((i,r,start,min(end,a.end)))
    config=out/'config.json'
    if config.exists() and json.loads(config.read_text())!=settings:raise RuntimeError('Existing run settings differ; use a new tag')
    atomic(config,settings)
    progress={'state':'initializing','settings':settings,'source_segments':len(segments),'completed_segments':0,'sampled_frames':0,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat()};atomic(out/'progress.json',progress)
    torch.set_num_threads(4)
    from rfdetr import RFDETRMedium
    from trackers import ByteTrackTracker
    print('MODEL LOADING',flush=True)
    model=RFDETRMedium(pretrain_weights=str(ROOT/'models/rf-detr-medium.pth'))
    optimized=False
    try:
        model.inference(compile=False,dtype=torch.float16);optimized=True
    except Exception as e:print('Optional optimization skipped:',type(e).__name__,str(e)[:200],flush=True)
    model_ready=time.monotonic();torch.cuda.reset_peak_memory_stats();print('MODEL READY optimized',optimized,flush=True)
    all_summaries=[];processed=0;covered_seconds=0
    for ordinal,(i,r,s0,s1) in enumerate(segments):
        result=out/f'segment-{i:02d}.json';dest=heavy/f'segment-{i:02d}.jsonl.gz'
        if result.exists() and dest.exists():
            summary=json.loads(result.read_text());all_summaries.append(summary);processed+=summary['sampled_frames'];covered_seconds+=summary['covered_seconds'];print('SKIP',i,flush=True);continue
        video=ROOT/r['mp4_file'];lo=max(s0,a.start);hi=min(s1,a.end)
        tracker=ByteTrackTracker(frame_rate=a.fps,lost_track_buffer=round(a.fps*4),track_activation_threshold=.5,high_conf_det_threshold=.5)
        c=av.open(str(video));stream=c.streams.video[0];stream.thread_type='AUTO'
        offset=float((stream.start_time or 0)*stream.time_base)
        seek=max(0,lo-s0)
        if seek>0:c.seek(int((seek+offset)/float(stream.time_base)),stream=stream,backward=True)
        partial=dest.with_suffix('.gz.part');n=0;last_bin=-1;buf=[];minutes=collections.defaultdict(list);track_ids=set();t0=time.monotonic();last_report=t0;first_t=None;last_t=None
        print('SEGMENT START',i,'local_sod',lo,hi,'file',video.name,flush=True)
        with gzip.open(partial,'wt',compresslevel=3) as f:
            def flush():
                nonlocal n,first_t,last_t
                if not buf:return
                imgs=[img for _,img in buf]
                # Optimization is batch-specific; pad the last partial batch, discard extra outputs.
                predict_imgs=imgs+[imgs[-1]]*(a.batch-len(imgs)) if optimized and len(imgs)<a.batch else imgs
                detections=model.predict(predict_imgs,threshold=a.threshold)
                if not isinstance(detections,list):detections=[detections]
                for (sod,img),d in zip(buf,detections):
                    d=d[d.class_id==1];raw_count=len(d);tracked=tracker.update(d);h,w=img.shape[:2]
                    people=[]
                    for tid,xy,conf in zip(tracked.tracker_id,tracked.xyxy,tracked.confidence):
                        if tid is None or int(tid)<0:continue
                        tid=int(tid);track_ids.add(tid)
                        people.append([tid,*[round(float(v),5) for v in xy/np.array([w,h,w,h])],round(float(conf),4)])
                    f.write(json.dumps({'segment':i,'sod':round(sod,3),'raw_people':raw_count,'p':people},separators=(',',':'))+'\n')
                    minutes[int(sod//60)].append(raw_count);n+=1
                    if first_t is None:first_t=sod
                    last_t=sod
                buf.clear()
            for frame in c.decode(stream):
                if frame.pts is None:continue
                sod=s0+float(frame.pts*stream.time_base)-offset
                if sod<lo-1e-4:continue
                if sod>=hi-1e-4:break
                bin_id=math.floor((sod-a.start)*a.fps+1e-4)
                if bin_id==last_bin:continue
                last_bin=bin_id;buf.append((sod,frame.to_ndarray(format='rgb24')))
                if len(buf)>=a.batch:flush()
                now=time.monotonic()
                if now-last_report>=30:
                    progress.update(state='running',segment=i,completed_segments=ordinal,sampled_frames=processed+n,current_sod=round(sod,2),inference_sample_fps=round(n/(now-t0),2),elapsed_processing_seconds=round(now-model_ready,1),peak_vram_gib=round(torch.cuda.max_memory_allocated()/2**30,2))
                    atomic(out/'progress.json',progress);print(json.dumps(progress),flush=True);last_report=now
            flush()
        c.close()
        expected_samples=(hi-lo)*a.fps
        if n<expected_samples*.98:raise RuntimeError(f'Incomplete sampled coverage in segment {i}: {n}/{expected_samples:.0f}')
        partial.replace(dest)
        elapsed=time.monotonic()-t0
        summary={'segment':i,'source':str(video.relative_to(ROOT)),'source_start_sod':s0,'requested_start_sod':lo,'requested_end_sod':hi,'sampled_frames':n,'first_sample_sod':first_t,'last_sample_sod':last_t,'covered_seconds':hi-lo,'elapsed_seconds':round(elapsed,3),'sample_fps':round(n/elapsed,3),'anonymous_track_fragments':len(track_ids),'track_ids_reset_each_segment':True,'minutes':[{'minute':k,'local_time':f'{k//60:02d}:{k%60:02d}','samples':len(v),'mean_people':round(float(np.mean(v)),3),'median_people':float(np.median(v)),'max_people':int(max(v))} for k,v in sorted(minutes.items())]}
        atomic(result,summary);all_summaries.append(summary);processed+=n;covered_seconds+=hi-lo;print('SEGMENT DONE',i,n,'frames',round(elapsed,1),'seconds',flush=True)
    minute_rows=[row for s in all_summaries for row in s['minutes']]
    final={'state':'complete','settings':settings,'completed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'sampled_frames':processed,'covered_seconds':covered_seconds,'model_ready_processing_seconds':round(time.monotonic()-model_ready,2),'segments':len(all_summaries),'peak_vram_gib':round(torch.cuda.max_memory_allocated()/2**30,2),'minutes':minute_rows,'limitations':['People detections and anonymous track fragments are not unique customers, roles, identities, services or validated throughput.','Local timeline derived from recorder wall-clock fields, approx 1-second OSD offset observed; not aligned to POS.','Sampling at declared FPS covers whole interval but is not inference on every native frame.','No person crops, recognition or audio processing; seated/occluded people may be missed.','Mirrors and overlapping partial/body boxes can inflate counts; no reflection/zone suppression or occupancy ground truth yet.']}
    atomic(out/'summary.json',final);progress.update(state='complete',completed_segments=len(all_summaries),sampled_frames=processed,completed_utc=final['completed_utc']);atomic(out/'progress.json',progress);print('RUN COMPLETE',processed,'frames',flush=True)
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('RUN FAILED',type(e).__name__,str(e),file=sys.stderr,flush=True);raise
