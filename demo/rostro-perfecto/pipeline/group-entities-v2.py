"""Entity grouping v2 over the full window: appearance galleries + station prior, no time-limited references.

Per tracklet (stitched Deep OC-SORT, Enfocado detections):
  p_sim  = CLIP-ReID similarity to the PROVIDER gallery (SAM-tracked provider crops + reviewed #429/#430/#446/#450 crops)
  c_sim  = similarity to the CLIENT gallery (reviewed #398/#407 crops)
  seat   = share of its boxes whose center lies in the provider's minimal station ROI
Rules (uncalibrated, case-tuned):
  PRESTADORA if (seat >= SEAT and p_sim >= P_SEAT) or (p_sim >= P_HI and p_sim - c_sim >= MARGIN)
  CLIENTA    if c_sim >= C_HI and c_sim - p_sim >= MARGIN and the tracklet overlaps her visit window
             (visit window = first/last reviewed sighting +/- 60 s; for the full day this comes from POS/arrival)
  both rules true -> ambiguous (not assigned). One box per entity per frame (highest-scoring tracklet wins).
Galleries come from the earlier short-window work; they are visual anchors, not identities."""
from pathlib import Path
import gzip,json,sys,collections,os
import av,numpy as np
from PIL import Image,ImageDraw,ImageOps,ImageFont
ROOT=Path(__file__).resolve().parents[1];TAG=os.environ.get('RPP_TAG','full70');HV=ROOT/'outputs/heavy/roi-enhanced'/TAG;OUT=ROOT/'outputs/entities'
sys.path.insert(0,str(ROOT/'scripts/vendor'));import animalx_embed as embed
SEAT,P_SEAT,P_HI,C_HI,MARGIN,ID_OFFSET=.5,.80,.88,.88,.03,100000
roi=json.loads((OUT/'provider-min-roi.json').read_text());RX0,RY0,RX1,RY1=roi['x']/1920,roi['y']/1080,(roi['x']+roi['w'])/1920,(roi['y']+roi['h'])/1080
VISIT=(40371.8-60,40942.0+60)
R=[json.loads(l) for l in gzip.open(HV/'B-deepocsort-stitched.jsonl.gz','rt')]
tr=collections.defaultdict(list)
for r in R:
    for p in r['p']:tr[p[0]].append((r['sod'],p[1:5],p[5]))
tr={k:v for k,v in tr.items() if len(v)>=5}
jobs=collections.defaultdict(list)
for t,v in tr.items():
    good=[x for x in v if (x[1][2]-x[1][0])*1920>=16 and (x[1][3]-x[1][1])*1080>=28] or v
    for k in sorted(set(np.linspace(0,len(good)-1,min(8,len(good))).round().astype(int))):
        s,b,_=good[k];jobs[round(s,3)].append((t,b))
C=HV/'group-crops';C.mkdir(exist_ok=True)
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
            p=C/f'{t}_{round(ts[k]*1000)}.jpg';im.crop((round(b[0]*1920),round(b[1]*1080),round(b[2]*1920),round(b[3]*1080))).save(p,quality=90);paths.append(p);owner.append(t)
        k+=1
c.close()
prov_gal=sorted((ROOT/'outputs/heavy/sam-provider/v2-crops').glob('*.jpg'))
drift={round(d['sod']*1000):d['flag'] for d in json.loads((ROOT/'outputs/sam-provider/v2-drift.json').read_text())['rows']}
prov_gal=[p for p in prov_gal if drift.get(int(p.stem))=='provider-like']
inv=json.loads((ROOT/'outputs/reid-provider-430/inventory.json').read_text())
prov_gal+=[ROOT/'outputs/heavy/reid-provider-430'/x['file'] for x in inv['crops'] if x['track'] in (429,430,446,450)]
ci=json.loads((ROOT/'outputs/reid-407/inventory.json').read_text())
cli_gal=[ROOT/'outputs/heavy/reid-407'/x['file'] for x in ci['crops'] if (x['track']==398 and x['sod']>=40384) or (x['track']==407 and x['sod']>=40462)]
enc=embed.get('clipreid');enc.BS=64
E=enc(paths);G_p=enc(prov_gal);G_c=enc(cli_gal);owner=np.array(owner)
def score(Q,G):
    s=np.sort(Q@G.T,axis=1)[:,-5:].mean(1);s=np.sort(s)[::-1];return float(s[:max(1,(len(s)+1)//2)].mean())
feat={}
for t,v in tr.items():
    if not (owner==t).any():continue
    Q=E[owner==t];ctr=[((b[0]+b[2])/2,(b[1]+b[3])/2) for _,b,_ in v]
    seat=float(np.mean([RX0<=x<=RX1 and RY0<=y<=RY1 for x,y in ctr]))
    feat[t]={'p_sim':round(score(Q,G_p),4),'c_sim':round(score(Q,G_c),4),'seat':round(seat,3),'frames':len(v),'first':v[0][0],'last':v[-1][0]}
role={}
for t,f in feat.items():
    prov=(f['seat']>=SEAT and f['p_sim']>=P_SEAT) or (f['p_sim']>=P_HI and f['p_sim']-f['c_sim']>=MARGIN)
    cli=f['c_sim']>=C_HI and f['c_sim']-f['p_sim']>=MARGIN and f['last']>=VISIT[0] and f['first']<=VISIT[1]
    role[t]='ambiguous' if prov and cli else 'provider' if prov else 'client' if cli else None
    f['role']=role[t]
clock=lambda x:f'{int(x)//3600:02}:{int(x)%3600//60:02}:{int(x)%60:02}'
ents={'provider':{'id':'provider-1','role':'provider','label':'PRESTADORA','color':'#ff5fd2'},'client':{'id':'client-1','role':'client','label':'CLIENTA','color':'#59e4c5'}}
for e in ents.values():
    e['members']=[{'track_id':t+ID_OFFSET,'raw_track_id':t,'mode':'full',**{k:(clock(v) if k in('first','last') else v) for k,v in feat[t].items() if k!='role'}} for t in sorted(feat,key=lambda t:feat[t]['first']) if role[t]==e['role']]
assign=[];claimed=collections.Counter()
for r in R:
    best={}
    for p in r['p']:
        ro=role.get(p[0])
        if ro not in ents:continue
        sc=feat[p[0]]['p_sim' if ro=='provider' else 'c_sim']
        if ro not in best or sc>best[ro][0]:best[ro]=(sc,p[0])
    for ro,(sc,t) in best.items():assign.append([r['sod'],t+ID_OFFSET,ents[ro]['id']]);claimed[ents[ro]['id']]+=1
doc={'schema':2,'layer':f'{TAG}/B-deepocsort-stitched','id_offset':ID_OFFSET,'window':[clock(R[0]['sod']),clock(R[-1]['sod'])],
 'rules':{'seat':SEAT,'p_sim_with_seat':P_SEAT,'p_sim_alone':P_HI,'c_sim':C_HI,'margin':MARGIN,'client_visit_window':[clock(VISIT[0]),clock(VISIT[1])],'station_roi':roi,'calibrated':False},
 'galleries':{'provider_crops':len(prov_gal),'client_crops':len(cli_gal)},'entities':list(ents.values()),
 'ambiguous':[{'raw_track_id':t,**feat[t]} for t in feat if role[t]=='ambiguous'],
 'dropped':[{'raw_track_id':t,'reason':'no rule matched'} for t in feat if role[t] is None],
 'assigned_boxes':dict(claimed),'identity_confirmed':False,'tracklet_features':{str(t):f for t,f in feat.items()}}
(OUT/f'entities-{TAG}.json').write_text(json.dumps(doc,indent=2,ensure_ascii=False))
json.dump(assign,gzip.open(ROOT/'review-app/media/entity-assignments.json.gz','wt'),separators=(',',':'))
for e in ents.values():print(e['label'],len(e['members']),'tracklets',claimed[e['id']],'boxes',[(m['raw_track_id'],m['first'],m['last'],m['p_sim'],m['c_sim'],m['seat']) for m in e['members']][:40])
print('ambiguous',len(doc['ambiguous']),'dropped',len(doc['dropped']),'of',len(feat))
# contact sheet: provider members across the window, for visual verification
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',12)
for e in ents.values():
    mem=e['members'];rows=(len(mem)+9)//10 or 1;sheet=Image.new('RGB',(10*150,rows*200),'#0b1320');d=ImageDraw.Draw(sheet)
    for i,m in enumerate(mem):
        ps=[p for p,o in zip(paths,owner) if o==m['raw_track_id']]
        if not ps:continue
        im=ImageOps.contain(Image.open(ps[len(ps)//2]),(140,170));x=(i%10)*150;y=(i//10)*200;sheet.paste(im,(x+5,y+5));d.text((x+5,y+180),f"#{m['track_id']} {m['first'][:5]}",font=font,fill=e['color'])
    sheet.save(HV/f"members-{e['role']}.png")
