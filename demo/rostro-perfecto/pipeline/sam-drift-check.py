"""Identity-drift check for SAM provider track: CLIP-ReID of 1 Hz SAM crops + overlap with client mask."""
from pathlib import Path
import json,sys,random
import av,numpy as np
from PIL import Image,ImageDraw,ImageOps,ImageFont
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/sam-provider';H=ROOT/'outputs/heavy/sam-provider/v2-crops';H.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'scripts/vendor'));import animalx_embed as embed
rows=json.loads((OUT/'v2-track.json').read_text())
inv=json.loads((ROOT/'outputs/reid-provider-430/inventory.json').read_text())
refs=[ROOT/'outputs/heavy/reid-provider-430'/c['file'] for c in inv['crops'] if c['track'] in (429,430,446,450)]
client_refs=[ROOT/'outputs/heavy/reid-407'/c['file'] for c in json.loads((ROOT/'outputs/reid-407/inventory.json').read_text())['crops'] if c['track']==407 and c['sod']>=40462]
pick=[];last=-9
for r in rows:
    if r['objects'].get('1') and r['sod']-last>=1:pick.append(r);last=r['sod']
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2];s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
c=av.open(str(ROOT/src['mp4_file']));st=c.streams.video[0];st.thread_type='AUTO';off=float((st.start_time or 0)*st.time_base);c.seek(int((pick[0]['sod']-s0+off)/st.time_base),stream=st,backward=True)
k=0;paths=[]
for fr in c.decode(st):
    if k>=len(pick):break
    sod=s0+float(fr.pts*st.time_base)-off
    if sod<pick[k]['sod']-.03:continue
    im=fr.to_image()
    while k<len(pick) and pick[k]['sod']<=sod+.03:
        b=pick[k]['objects']['1']['box'];bb=(round(b[0]*1920),round(b[1]*1080),round(b[2]*1920),round(b[3]*1080))
        # No clock masking: at this station the clock covers most of the torso; refs share the overlay.
        p=H/f"{round(pick[k]['sod']*1000):08d}.jpg";im.crop(bb).save(p,quality=92);paths.append(p);k+=1
c.close()
enc=embed.get('clipreid');enc.BS=64
E=enc(paths);R=enc(refs);C=enc(client_refs)
sp=np.sort(E@R.T,axis=1)[:,-3:].mean(1);sc=np.sort(E@C.T,axis=1)[:,-3:].mean(1)
def iou(a,b):
    x1,y1,x2,y2=max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3]);i=max(0,x2-x1)*max(0,y2-y1)
    return i/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-i+1e-12)
out=[]
for r,p,a_,b_ in zip(pick,paths,sp,sc):
    cl=r['objects'].get('2');ov=iou(r['objects']['1']['box'],cl['box']) if cl else 0
    flag='provider-like' if a_>=b_+0.02 and ov<.5 else ('client-like' if b_>a_+0.02 else 'ambiguous')
    if ov>=.5:flag='merged-with-client'
    out.append({'sod':r['sod'],'provider_score':round(float(a_),4),'client_score':round(float(b_),4),'iou_client':round(ov,3),'flag':flag,'crop':str(p.relative_to(ROOT))})
counts={f:sum(o['flag']==f for o in out) for f in ['provider-like','client-like','ambiguous','merged-with-client']}
(OUT/'v2-drift.json').write_text(json.dumps({'samples_1hz':len(out),'counts':counts,'rows':out},indent=2))
print(counts)
for o in out:
    if o['flag']!='provider-like':print(o['sod'],o['flag'],o['provider_score'],o['client_score'],o['iou_client'])
random.seed(3);s=sorted(random.sample(out,min(40,len(out))),key=lambda o:o['sod'])
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',12);sheet=Image.new('RGB',(10*150,4*205),'#0b1320');d=ImageDraw.Draw(sheet)
for i,o in enumerate(s):
    im=ImageOps.contain(Image.open(ROOT/o['crop']),(140,175));x=(i%10)*150;y=(i//10)*205;sheet.paste(im,(x+5,y+5));t=int(o['sod'])
    d.text((x+5,y+185),f"{t//3600:02}:{t%3600//60:02}:{t%60:02} {o['flag'][:8]}",font=font,fill='white' if o['flag']=='provider-like' else '#f2c878')
sheet.save(ROOT/'outputs/heavy/sam-provider/v2-random40.png')
