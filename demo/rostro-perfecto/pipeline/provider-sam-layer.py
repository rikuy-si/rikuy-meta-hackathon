"""Gate SAM provider track with 1 Hz ReID drift check; write app layer (baseline untouched)."""
from pathlib import Path
import json,numpy as np,datetime as dt
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/sam-provider'
rows=json.loads((OUT/'v2-track.json').read_text());drift=json.loads((OUT/'v2-drift.json').read_text())['rows'];summ=json.loads((OUT/'v2-summary.json').read_text())
dt_=np.array([d['sod'] for d in drift]);first_merge=min([d['sod'] for d in drift if d['flag']=='merged-with-client'],default=1e9)
clock=lambda t:dt.datetime.fromtimestamp(t,dt.timezone.utc).strftime('%H:%M:%S')
keep=[]
for r in rows:
    o=r['objects'].get('1')
    if not o or r['sod']>=first_merge-1:continue
    j=int(np.argmin(np.abs(dt_-r['sod'])))
    if abs(dt_[j]-r['sod'])>.6 or drift[j]['flag']!='provider-like':continue
    keep.append({'sod':r['sod'],'box':o['box'],'score':drift[j]['provider_score']})
secs={int(k['sod']) for k in keep};chair={s for s in secs if 40462<=s<=40824}
layer={'schema':2,'status':'agent-automatic-provisional','segment':2,'seed_track':430,'reference_tracks':[429,430,446,450],
 'method':'RF-DETR (2.5x ROI) + CLIP-ReID anchors -> SAM 3 video tracker (2x ROI, 5 fps, client as 2nd object) -> 1 Hz CLIP-ReID provider-vs-client drift gate. No manual labels.',
 'gate':{'drift':'nearest 1 Hz sample provider-like (provider score >= client score + 0.02, IoU with client mask < 0.5)','cut_before_first_client_merge':clock(first_merge) if first_merge<1e9 else None,'calibrated':False},
 'validation':{'heldout_detector_reid_candidates':summ['holdout_candidates'],'heldout_iou_ge_0_5':summ['holdout_iou_ge_0_5'],'heldout_iou_median':summ['holdout_iou_median'],'drift_counts_1hz':json.loads((OUT/'v2-drift.json').read_text())['counts'],'note':'Self-consistency vs held-out automatic candidates, not human ground truth.'},
 'coverage':{'baseline_seat_detection_seconds':15,'roi_reid_seconds':110,'sam_gated_seconds_chair_episode':len(chair),'chair_episode_seconds':362},
 'observed':{'first':clock(keep[0]['sod']),'last':clock(keep[-1]['sod'])},'pos_recorded_provider':'the provider (POS assignment for turn 2026-4872)','identity_confirmed':False,'candidates':keep}
(OUT/'provider-sam-layer.json').write_text(json.dumps(layer,indent=2))
print(layer['coverage'],layer['observed'],len(keep))
