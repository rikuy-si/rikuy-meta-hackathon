"""Re-apply entity rules on cached tracklet features (no re-embedding). Rules v2.1:
the station ROI also contains the CLIENT (she lies on the bed), so seat alone never decides the role;
the PROVIDER must look more like the provider gallery than the client gallery in every rule.
  PRESTADORA: p-c >= M and ((seat >= .5 and p >= .85) or p >= P_HI)
  CLIENTA   : c-p >= M and c >= C_HI and overlaps visit window"""
from pathlib import Path
import gzip,json,collections,os,sys
ROOT=Path(__file__).resolve().parents[1];TAG=os.environ.get('RPP_TAG','full70');HV=ROOT/'outputs/heavy/roi-enhanced'/TAG;OUT=ROOT/'outputs/entities'
M=float(os.environ.get('M',.03));P_HI=float(os.environ.get('P_HI',.93));C_HI=float(os.environ.get('C_HI',.90));ID_OFFSET=100000;VISIT=(40371.8-60,40942.0+60)
doc=json.loads((OUT/f'entities-{TAG}.json').read_text());F={int(k):v for k,v in doc['tracklet_features'].items()}
role={}
for t,f in F.items():
    p,c=f['p_sim'],f['c_sim']
    prov=p-c>=M and ((f['seat']>=.5 and p>=.85) or p>=P_HI)
    cli=c-p>=M and c>=C_HI and f['last']>=VISIT[0] and f['first']<=VISIT[1]
    role[t]='provider' if prov else 'client' if cli else None;f['role']=role[t]
clock=lambda x:f'{int(x)//3600:02}:{int(x)%3600//60:02}:{int(x)%60:02}'
ents={'provider':{'id':'provider-1','role':'provider','label':'PRESTADORA','color':'#ff5fd2'},'client':{'id':'client-1','role':'client','label':'CLIENTA','color':'#59e4c5'}}
for e in ents.values():
    e['members']=[{'track_id':t+ID_OFFSET,'raw_track_id':t,'mode':'full','first':clock(F[t]['first']),'last':clock(F[t]['last']),'frames':F[t]['frames'],'p_sim':F[t]['p_sim'],'c_sim':F[t]['c_sim'],'seat':F[t]['seat']} for t in sorted(F,key=lambda t:F[t]['first']) if role[t]==e['role']]
R=[json.loads(l) for l in gzip.open(HV/'B-deepocsort-stitched.jsonl.gz','rt')]
assign=[];claimed=collections.Counter();secs=collections.defaultdict(set)
for r in R:
    best={}
    for p in r['p']:
        ro=role.get(p[0])
        if ro is None:continue
        sc=F[p[0]]['p_sim']-F[p[0]]['c_sim'] if ro=='provider' else F[p[0]]['c_sim']-F[p[0]]['p_sim']
        if ro not in best or sc>best[ro][0]:best[ro]=(sc,p[0])
    for ro,(sc,t) in best.items():assign.append([r['sod'],t+ID_OFFSET,ents[ro]['id']]);claimed[ents[ro]['id']]+=1;secs[ro].add(int(r['sod']))
doc.update(schema=2.1,entities=list(ents.values()),rules={**doc['rules'],'version':'2.1','margin':M,'p_sim_alone':P_HI,'c_sim':C_HI,'note':'seat prior requires provider-over-client appearance margin'},assigned_boxes=dict(claimed),coverage_seconds={k:len(v) for k,v in secs.items()},
           dropped=[{'raw_track_id':t,'reason':'no rule matched'} for t in F if role[t] is None],ambiguous=[])
(OUT/f'entities-{TAG}.json').write_text(json.dumps(doc,indent=2,ensure_ascii=False))
json.dump(assign,gzip.open(ROOT/'review-app/media/entity-assignments.json.gz','wt'),separators=(',',':'))
for e in ents.values():print(e['label'],len(e['members']),'tracklets',claimed[e['id']],'boxes',len(secs[e['role']]),'s');
for e in ents.values():print(e['label'],[(m['raw_track_id'],m['first'],m['last'],m['frames'],m['p_sim'],m['c_sim'],m['seat']) for m in e['members'] if m['frames']>=50])
