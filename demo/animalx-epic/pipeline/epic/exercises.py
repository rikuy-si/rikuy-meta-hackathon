"""Phase K: merge the review agent's per-set labels (Muse Code agent on pi.dev (model: Muse Wonder)) (work/sets/labels_<client>_<day>.tsv) into
source/<client>/<day>/exercises.json, keyed by set id, with the pose numbers next to them.
Extra manual sets (pose undercounted / below the review score) come from work/sets/manual_<client>_<day>.json."""
import sys, json, csv, pathlib
ROOT = pathlib.Path(__file__).resolve().parent
for tsv in sorted((ROOT / 'work' / 'sets').glob('labels_*.tsv')):
    client, day = tsv.stem.split('_')[1:]
    base = ROOT / 'source' / client / day
    S = {s['id']: s for s in json.load(open(base / 'sets.json'))['sets']}
    out = []
    for r in csv.DictReader(open(tsv), delimiter='\t'):
        s = S[r['id']]
        out.append({'id': r['id'], 'start': s['start'], 'clip': s['clip'], 'camera': s['camera'], 't0': s['t0'], 't1': s['t1'],
                    'identity': s['verified'], 'is_exercise': r['is_exercise'] == '1', 'exercise': r['exercise_es'],
                    'equipment': r['equipment'], 'spotter': r['spotter'] == '1', 'epic': int(r['epic']), 'confidence': r['conf'],
                    'reps_pose': s['reps'], 'reps_agent': None, 'rom': s['rom'], 'slowdown': s['slowdown'],
                    'lifting_score': s['score'], 'notes': r['notes'], 'source': 'review sheet'})
    man = ROOT / 'work' / 'sets' / f'manual_{client}_{day}.json'
    if man.exists():
        for m in json.load(open(man)):
            s = S.get(m['id'], {})
            out.append({**{k: s.get(k) for k in ('start', 'clip', 'camera', 't0', 't1')}, 'identity': s.get('verified'),
                        'reps_pose': s.get('reps'), 'rom': s.get('rom'), 'slowdown': s.get('slowdown'), 'lifting_score': s.get('score'),
                        'reps_agent': None, **m, 'source': 'manual (below review score)'})
    mc = {m['id']: m['reps'] for m in json.load(open(ROOT / 'work' / 'sets' / 'repcheck' / 'manual_counts.json'))}
    for o in out:
        if o['id'] in mc: o['reps_agent'] = mc[o['id']]
    json.dump({'client': client, 'day': day, 'labeller': 'Muse Code agent on pi.dev (model: Muse Wonder), from pose key sheets', 'sets': sorted(out, key=lambda x: x['start'] or '')},
              open(base / 'exercises.json', 'w'), indent=1, ensure_ascii=False)
    ex = [o for o in out if o['is_exercise']]
    print(client, day, len(out), 'labelled', len(ex), 'exercise', 'epic>=4:', [o['id'] for o in out if o['epic'] >= 4])
