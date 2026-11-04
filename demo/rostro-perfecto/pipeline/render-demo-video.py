"""Render the demo time-lapse: SAM 3 masks (provider = Amarillo, client 1 = Hielo, client 2 = Menta), Rikuy navy tint,
viewfinder corners on the workstation, face blur for clients and bystanders. No text burned in: the HTML page
draws bilingual overlays synced to video time. 12x speed, 25 fps, H.264 (plays everywhere)."""
from pathlib import Path
import json,gzip,subprocess
import av,numpy as np
from PIL import Image,ImageFilter,ImageDraw
ROOT=Path(__file__).resolve().parents[1];H=ROOT/'outputs/heavy/sam-demo';OUTD=ROOT/'demo/media';OUTD.mkdir(parents=True,exist_ok=True)
T0,T1,SPEED,FPS=39940.0,41100.0,12.0,25
CROP=(0,0,1440,1080);OW,OH=1280,960
idx=json.loads((ROOT/'outputs/sam-demo/masks-index.json').read_text());mf={}
for r in idx['frames']:
    for o in r['objects']:mf.setdefault(o,[]).append(r['sod'])
mt={o:np.array(v) for o,v in mf.items()}
COL={'1':(220,224,100),'2':(169,182,211),'3':(127,204,180)}
from PIL import ImageChops
people=[json.loads(l) for l in gzip.open(ROOT/'outputs/heavy/roi-enhanced/full70/B-deepocsort-stitched.jsonl.gz','rt')]
pt=np.array([r['sod'] for r in people])
def mask(o,t):
    if o not in mt:return None
    j=int(np.argmin(np.abs(mt[o]-t)))
    if abs(mt[o][j]-t)>.6:return None
    p=H/f'{o}_{round(mt[o][j]*1000):08d}.png'
    if not p.exists():return None
    m=np.zeros((1080,1920),bool);sm=np.asarray(Image.open(p))>0;m[:sm.shape[0],:sm.shape[1]]=sm;return m
def tint(img):
    a=np.asarray(img.convert('L'),np.float32)/255.
    lo=np.array([20,19,63],np.float32);hi=np.array([234,240,248],np.float32)
    return lo+(hi-lo)*a[...,None]
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2];s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
c=av.open(str(ROOT/src['mp4_file']));st=c.streams.video[0];st.thread_type='AUTO';off=float((st.start_time or 0)*st.time_base);c.seek(int((T0-s0+off)/st.time_base),stream=st,backward=True)
out=OUTD/'demo-timelapse.mp4'
ff=subprocess.Popen(['/usr/bin/ffmpeg','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{OW}x{OH}','-r',str(FPS),'-i','-','-c:v','h264_nvenc','-preset','p6','-cq','21','-pix_fmt','yuv420p','-movflags','+faststart','-y',str(out)],stdin=subprocess.PIPE)
targets=np.arange(T0,T1,SPEED/FPS);k=0
fidx=np.array([r['sod'] for r in idx['frames']])
def union(t):
    j=int(np.argmin(np.abs(fidx-t)))
    if abs(fidx[j]-t)>.6:return None
    bs=[b for b in idx['frames'][j]['objects'].values()]
    if not bs:return None
    return [min(b[0] for b in bs),min(b[1] for b in bs),max(b[2] for b in bs),max(b[3] for b in bs)]
cams=[];last=[0,0,1440,1080]
for t in targets:
    u=union(t)
    if u is None:cams.append(last);continue
    cx,cy=(u[0]+u[2])/2,(u[1]+u[3])/2;w=max(720,(u[2]-u[0])+260,((u[3]-u[1])+200)*4/3);w=min(w,1440);h=w*3/4
    x0=min(max(0,cx-w/2),1920-w);y0=min(max(0,cy-h/2),1080-h);last=[x0,y0,x0+w,y0+h];cams.append(last)
cams=np.array(cams,float);a=.025
for i in range(1,len(cams)):cams[i]=a*cams[i]+(1-a)*cams[i-1]
for i in range(len(cams)-2,-1,-1):cams[i]=a*cams[i]+(1-a)*cams[i+1]
for fr in c.decode(st):
    if k>=len(targets):break
    sod=s0+float(fr.pts*st.time_base)-off
    if sod<targets[k]:continue
    t=targets[k];k+=1
    img=fr.to_image();arr=np.asarray(img).astype(np.float32)
    base=tint(img)*.82+arr*.18
    # face blur: top 30% of every non-provider person box (clients and bystanders)
    j=int(np.argmin(np.abs(pt-t)));pm=mask('1',t)
    blurred=np.asarray(img.filter(ImageFilter.GaussianBlur(14))).astype(np.float32)
    bl=tint(Image.fromarray(blurred.astype(np.uint8)))*.82+blurred*.18
    heads=[]
    for p in people[j]['p']:
        x1,y1,x2,y2=int(p[1]*1920),int(p[2]*1080),int(p[3]*1920),int(p[4]*1080)
        if pm is not None and pm[y1:y2,x1:x2].mean()>.35:continue  # provider stays visible
        hw=max(14,int((x2-x1)*.42));hh=max(14,int((y2-y1)*.16));cx=(x1+x2)//2;cy=y1+hh
        heads.append((cx-hw,cy-hh,cx+hw,cy+hh))
    masks={o:mask(o,t) for o in ('2','3','1')}
    for o in ('2','3'):
        m=masks[o]
        if m is None:continue
        ys,xs=np.nonzero(m)
        if len(ys):
            y1,y2=ys.min(),ys.max();x1,x2=xs.min(),xs.max();hw=max(16,int((x2-x1)*.45));hh=max(16,int((y2-y1)*.18));cx=(x1+x2)//2;heads.append((cx-hw,y1-4,cx+hw,y1+2*hh))
    if heads:
        hm=Image.new('L',(1920,1080),0);dd=ImageDraw.Draw(hm)
        for e in heads:dd.ellipse(e,fill=255)
        hm=np.asarray(hm.filter(ImageFilter.GaussianBlur(6)),np.float32)[...,None]/255.
        base=base*(1-hm)+bl*hm
    for o in ('2','3','1'):
        m=masks[o]
        if m is None:continue
        col=np.array(COL[o],np.float32);base[m]=base[m]*.30+arr[m]*.25+col*.45
        e=Image.fromarray((m*255).astype(np.uint8)).filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
        edge=np.asarray(e)>0;base[edge]=col
    cx0,cy0,cx1,cy1=cams[k-1];im=Image.fromarray(np.clip(base,0,255).astype(np.uint8))
    d=ImageDraw.Draw(im);x1,y1,x2,y2=290,4,546,214;L=26;mc=(127,204,180)
    for (cx,cy,dx,dy) in ((x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)):
        d.line([(cx,cy),(cx+dx*L,cy)],fill=mc,width=4);d.line([(cx,cy),(cx,cy+dy*L)],fill=mc,width=4)
    im=im.crop((int(cx0),int(cy0),int(cx1),int(cy1)));ff.stdin.write(np.asarray(im.resize((OW,OH),Image.LANCZOS)).tobytes())
ff.stdin.close();ff.wait();c.close()
meta={'video':'media/demo-timelapse.mp4','t0_sod':T0,'speed':SPEED,'fps':FPS,'frames':k,'duration_s':round(k/FPS,2),'camera':'virtual, follows SAM masks','size':[OW,OH],'colors':{'provider':'#DCE064','client1':'#A9B6D3','client2':'#7FCCB4'}}
(ROOT/'demo/video.json').write_text(json.dumps(meta,indent=2));print(meta)
# poster frame and highlight stills for cards
