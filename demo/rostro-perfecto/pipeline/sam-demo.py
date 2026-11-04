"""SAM 3 masks for the demo: provider, client 1 (man), client 2 (woman), 2 fps, 11:05:40-11:23:00.
Prompts (automatic, every ~10 s) come from the reviewed/automatic tracks we already have. Saves RLE-free
compact masks as PNG per object per frame (cold storage) + per-frame boxes JSON."""
from pathlib import Path
import json,gzip,time
import av,numpy as np,torch
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];H=ROOT/'outputs/heavy/sam-demo';H.mkdir(parents=True,exist_ok=True);OUT=ROOT/'outputs/sam-demo';OUT.mkdir(exist_ok=True)
T0,T1,FPS=39940.0,40980.0,2.0
# region of interest for SAM (station + reception + exit path), full res crop
X0,Y0,X1,Y1=0,0,1344,1080
def to_crop(b):return [b[0]*1920-X0,b[1]*1080-Y0,b[2]*1920-X0,b[3]*1080-Y0]
prompts=[]  # (sod,obj,box)
man=json.loads((ROOT/'outputs/provider-stable/case0-man.json').read_text())['track']
man=[x for x in man if x['kind']=='observed' and (x.get('score') or 0)>0.045 and (x['box'][1]+x['box'][3])/2<.25]
p1=json.loads((ROOT/'outputs/provider-stable/case1.json').read_text())['track']
p1=[x for x in p1 if x['kind']=='observed' and (x.get('score') or -1)>0.03 and (x['box'][1]+x['box'][3])/2<.2 and x['sod']<40420]
sam=json.loads((ROOT/'outputs/sam-provider/provider-sam-layer.json').read_text())['candidates']
rv=json.loads((ROOT/'outputs/reid-407/review-layer.json').read_text());cl=[]
for l in gzip.open(ROOT/'outputs/heavy/full-day/segment-02.jsonl.gz','rt'):
    r=json.loads(l)
    for p in r['p']:
        if any(t['id']==p[0] and t['start_sod']<=r['sod']<=t['end_sod'] for t in rv['tracklets']):cl.append({'sod':r['sod'],'box':p[1:5]})
def every(lst,obj,gap=10):
    last=-1e9
    for x in sorted(lst,key=lambda x:x['sod']):
        if x['sod']-last>=gap:prompts.append((x['sod'],obj,x['box']));last=x['sod']
every(man,2);every(p1,1,12);every(sam,1,12);every(cl,3,10)
prompts.sort()
from transformers import Sam3TrackerVideoModel,Sam3TrackerVideoProcessor
dev='cuda';proc=Sam3TrackerVideoProcessor.from_pretrained('facebook/sam3');model=Sam3TrackerVideoModel.from_pretrained('facebook/sam3',torch_dtype=torch.bfloat16).to(dev).eval()
sess=proc.init_video_session(inference_device=dev,inference_state_device='cpu',video_storage_device='cpu',processing_device='cpu',dtype=torch.bfloat16)
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2];s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
c=av.open(str(ROOT/src['mp4_file']));st=c.streams.video[0];st.thread_type='AUTO';off=float((st.start_time or 0)*st.time_base);c.seek(int((T0-s0+off)/st.time_base),stream=st,backward=True)
nxt=T0;idx=0;pi=0;rows=[];started=set();t0=time.time()
with torch.inference_mode():
    for fr in c.decode(st):
        sod=s0+float(fr.pts*st.time_base)-off
        if sod<nxt-.02:continue
        if sod>=T1:break
        nxt+=1/FPS
        img=fr.to_image().crop((X0,Y0,X1,Y1));inp=proc(images=img,device=dev,return_tensors='pt')
        while pi<len(prompts) and prompts[pi][0]<=sod+.26:
            ps,obj,b=prompts[pi];pi+=1
            if abs(ps-sod)<=.5:
                proc.add_inputs_to_inference_session(inference_session=sess,frame_idx=idx,obj_ids=obj,input_boxes=[[to_crop(b)]],original_size=inp.original_sizes[0]);started.add(obj)
        if not started:continue
        out=model(inference_session=sess,frame=inp.pixel_values[0].to(dev,torch.bfloat16))
        m=proc.post_process_masks([out.pred_masks],original_sizes=inp.original_sizes,binarize=True)[0]
        rec={'sod':round(sod,3),'objects':{}}
        for k,oid in enumerate(out.object_ids):
            mk=m[k,0].cpu().numpy().astype(bool)
            if mk.sum()<200:continue
            ys,xs=np.nonzero(mk);rec['objects'][str(oid)]=[int(xs.min())+X0,int(ys.min())+Y0,int(xs.max())+X0,int(ys.max())+Y0,int(mk.sum())]
            Image.fromarray(mk.astype(np.uint8)*255).save(H/f'{oid}_{round(sod*1000):08d}.png',optimize=True)
        rows.append(rec);idx+=1
        if idx%200==0:print(idx,round(sod),round(idx/(time.time()-t0),2),'fps',flush=True)
c.close()
(OUT/'masks-index.json').write_text(json.dumps({'window':[T0,T1],'fps':FPS,'roi':[X0,Y0,X1,Y1],'objects':{'1':'provider','2':'client 1 (man)','3':'client 2 (woman, target)'},'prompts':len(prompts),'frames':rows}))
print('done',len(rows),'frames',round(time.time()-t0),'s; prompts',len(prompts))
