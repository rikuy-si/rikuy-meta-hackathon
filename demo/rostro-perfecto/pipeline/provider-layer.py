"""Build reviewed provider-candidate layer and timesheet from ROI ReID; baseline untouched."""
from pathlib import Path
import json,csv,datetime as dt
import av
from PIL import Image,ImageOps,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/reid-provider-430';H=ROOT/'outputs/heavy/reid-provider-430'
r=json.loads((OUT/'roi-reid.json').read_text())
TH,AR=0.87,1.2
gate=lambda p:p['score']>=TH and (p['box'][3]-p['box'][1])*1080>=AR*(p['box'][2]-p['box'][0])*1920
# After 11:20:36 crops overlap other people near the station; excluded as ambiguous after review.
CUT=40836.5
acc=[{k:p[k] for k in ['sod','box','score']} for p in r['path'] if gate(p) and p['sod']<CUT]
excluded=[{k:p[k] for k in ['sod','box','score']} for p in r['path'] if gate(p) and p['sod']>=CUT]
clock=lambda t:dt.datetime.fromtimestamp(t,dt.timezone.utc).strftime('%H:%M:%S')
secs=sorted({int(p['sod']) for p in acc});chair=[s for s in secs if 40462<=s<=40824]
seated=[p for p in acc if p['sod']<40816];walking=[p for p in acc if p['sod']>=40816]
layer={'schema':1,'status':'agent-visual-review-provisional','segment':2,'seed_track':430,'reference_tracks':r['references'],'method':'Supplementary 2.5x zoomed ROI RF-DETR Medium pass at 2 fps over 11:14:00-11:21:00, then AnimalX CLIP-ReID against reviewed seed crops; gate score>=0.87 and upright box.','gate':{'score':TH,'min_height_to_width':AR,'calibrated':False},'candidates':acc,'random_sample_review':{'n':30,'visually_consistent':30,'note':'Small agent visual sample; not a precision estimate with confidence bounds.'},'coverage':{'baseline_seat_detection_seconds':15,'roi_candidate_seconds_chair_episode':len(chair),'chair_episode_seconds':362},'observed':{'first_seated_candidate':clock(seated[0]['sod']),'last_seated_candidate':clock(seated[-1]['sod']),'walking_away':[clock(walking[0]['sod']),clock(walking[-1]['sod'])] if walking else None},'excluded_ambiguous':excluded,'excluded_reason':'After 11:20:36 candidate crops overlap other people near the station.','pos_recorded_provider':'the provider (POS assignment for candidate turn 2026-4872)','identity_confirmed':False,'notes':['Same-camera appearance/time review of an anonymous worker; not a named or biometric identity.','Gaps reflect occlusion/missed detections; no interpolation.','Baseline track IDs (#429, #430, #446, #450, #456) remain unchanged.']}
(OUT/'provider-layer.json').write_text(json.dumps(layer,indent=2))
# timesheet
picks=[40482,40530,40600,40700,40780,40812,40816,40825,40832]
src=json.loads((ROOT/'outputs/channel6-day-manifest.json').read_text())['recordings'][2];s0=json.loads((ROOT/'outputs/vision/full-day/segment-02.json').read_text())['source_start_sod']
client=json.loads((ROOT/'outputs/reid-407/review-layer.json').read_text())
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17);small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13)
sheet=Image.new('RGB',(2400,100+3*430),'#0b1320');d=ImageDraw.Draw(sheet)
d.text((18,12),'Provider candidate near reviewed client | seed R2 #430 | ROI + CLIP-ReID | 2026-11-03',font=font,fill='white')
d.text((18,43),f"Magenta: provider candidate. Seated {layer['observed']['first_seated_candidate']}-{layer['observed']['last_seated_candidate']}; POS-assigned provider: the provider (not confirmed).",font=small,fill='#9fb3c8')
d.text((18,67),'No interpolation; gaps are occlusion/missed detections. Not facial recognition.',font=small,fill='#9fb3c8')
rows=[]
for k,t in enumerate(picks):
    p=min(acc,key=lambda x:abs(x['sod']-t));rows.append(p)
    c=av.open(str(ROOT/src['mp4_file']));s=c.streams.video[0];off=float((s.start_time or 0)*s.time_base);sec=p['sod']-s0;c.seek(int((sec+off)/s.time_base),stream=s,backward=True)
    for fr in c.decode(s):
        if float(fr.pts*s.time_base)-off>=sec-.03:im=fr.to_image();break
    c.close();w,h=im.size;b=tuple(round(v*q) for v,q in zip(p['box'],[w,h,w,h]))
    ctxim=im.copy();ImageDraw.Draw(ctxim).rectangle(b,outline='#ff5fd2',width=5)
    x=(k%3)*800;y=100+(k//3)*430;d.text((x+12,y+6),f"{clock(p['sod'])} | score {p['score']:.3f}",font=font,fill='#ff5fd2')
    sheet.paste(ImageOps.contain(ctxim,(640,360)),(x,y+35));cr=ImageOps.contain(im.crop(b),(150,350));sheet.paste(cr,(x+645+(150-cr.width)//2,y+38+(350-cr.height)//2))
    d.text((x+12,y+401),'standing / leaving station' if p['sod']>=40816 else 'at client workstation',font=small,fill='#ff5fd2')
sheet.save(H/'provider-timesheet.png')
with (OUT/'provider-timeline.csv').open('w',newline='') as f:
    wr=csv.writer(f,lineterminator='\n');wr.writerow(['time_local','seconds_of_day','score','observation'])
    for p in rows:wr.writerow([clock(p['sod']),p['sod'],p['score'],'standing / leaving station' if p['sod']>=40816 else 'at client workstation'])
print(json.dumps(layer['coverage']),layer['observed'])
