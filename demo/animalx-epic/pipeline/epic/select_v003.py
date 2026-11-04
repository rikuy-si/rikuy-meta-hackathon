"""Phase M (part 1): pick the v003 shots, lifting first.

usage: select_v003.py CLIENT DAY [DAY ...]
Per day: arrival (first reception clip) -> up to --per-day sets (one per exercise name, best epic then lifting score,
identity confirmed/mixed/rescued only, confidence high/med) in time order -> the day's peak set (highest epic,
then slowdown). One hero beat (configurable) and one finale set across days (highest epic, then slowdown).
Each set window covers ~3-4 reps around the middle of the set. Writes work/v003/<client>/plan.json.
"""
import sys, json, pathlib, argparse
ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser(); ap.add_argument('client'); ap.add_argument('days', nargs='+')
ap.add_argument('--per-day', type=int, default=5)
ap.add_argument('--hero', default=None, help='DAY:CLIP:T_IN:DUR:caption')
ap.add_argument('--window', type=float, default=7.0)
ap.add_argument('--finale', default=None); ap.add_argument('--exclude', action='append', default=[])
ap.add_argument('--override', action='append', default=[], help='SET_ID:T_IN:T_OUT manual window (pose undercounts)')
a = ap.parse_args()
OV = {o.split(':')[0]: tuple(map(float, o.split(':')[1:])) for o in a.override}
OK_ID = {'confirmed', 'mixed', 'rescued'}


def rep_times(day, clip):
    E = json.load(open(ROOT / 'source' / a.client / day / 'clips' / f'{clip}.events.json'))
    return sorted(t for s in E['sets'] for t in s['rep_times'])


def window(day, e, dur):
    if e['id'] in OV:
        t_in, t_out = OV[e['id']]; return t_in, t_out - t_in
    R = [t for t in rep_times(day, e['clip']) if e['t0'] - 0.5 <= t <= e['t1'] + 0.5]
    if len(R) < 2:
        return e['t0'], min(dur, e['t1'] - e['t0'] + 1)
    # densest window: the start (0.8 s before a rep) that holds the most reps; ties -> later in the set (more effort)
    best = max(range(len(R)), key=lambda i: (sum(1 for t in R if R[i] - 0.8 <= t <= R[i] - 0.8 + dur), i))
    t_in = max(e['t0'] - 0.5, R[best] - 0.8)
    return round(t_in, 2), round(min(dur, e['t1'] + 1.0 - t_in), 2)


def shot(kind, day, e, t_in, dur):
    R = rep_times(day, e['clip'])
    before = sum(1 for t in R if e['t0'] - 0.5 <= t < t_in)
    return {'kind': kind, 'day': day, 'set_id': e['id'], 'clip': e['clip'], 'camera': e['camera'], 't_in': t_in, 'dur': dur,
            'exercise': e['exercise'], 'start': e['start'], 'epic': e['epic'], 'spotter': e['spotter'],
            'rep_times': [round(t - t_in, 2) for t in R if t_in <= t <= t_in + dur and e['t0'] - 0.5 <= t <= e['t1'] + 0.5],
            'rep_offset': before, 'reps_pose_set': e['reps_pose'], 'identity': e['identity']}


plan = {'client': a.client, 'days': [], 'hero': None, 'finale': None}
allsets = []
for day in a.days:
    base = ROOT / 'source' / a.client / day
    ex = [e for e in json.load(open(base / 'exercises.json'))['sets']
          if e['is_exercise'] and e['identity'] in OK_ID and e['id'] not in a.exclude and e['id'] != a.finale and e['confidence'] in ('high', 'med') and e['epic'] >= 3 and e['clip']]
    allsets += [(day, e) for e in ex]
    peak = max(ex, key=lambda e: (e['epic'], e['slowdown'] or 0, e['lifting_score'] or 0)) if ex else None
    best = {}
    for e in sorted(ex, key=lambda e: (-e['epic'], -(e['lifting_score'] or 0))):
        k = e['exercise'].split(' (')[0]
        if k not in best and (peak is None or e['id'] != peak['id']): best[k] = e
    picks = sorted(list(best.values())[:a.per_day], key=lambda e: e['start'])
    pres = json.load(open(base / 'presence.json'))
    # arrival: the reception camera is top-down and the client sits at the frame edge, so use the first
    # floor sightings (cam01/02/04) and the 3.5 s window where the confirmed box is largest
    floor = sorted((i for c in ('cam101', 'cam201', 'cam401') for i in pres.get(c, []) if i['verified'] in ('confirmed', 'mixed')),
                   key=lambda i: i['w0'])[:4]
    arr, best = None, -1
    for iv in floor:
        B = [b for b in json.load(open(base / 'clips' / f"{iv['name']}.track.json"))['boxes'] if b['status'] == 'confirmed']
        for b0 in B:
            wb = [b['box'] for b in B if b0['t'] <= b['t'] <= b0['t'] + 3.5]
            win = [bb[3] - bb[1] for bb in wb]
            inside = all(bb[0] >= 12 and bb[2] <= 1268 and bb[3] <= 712 for bb in wb)   # whole body in frame
            if inside and len(win) >= 14 and b0['t'] + 3.5 < iv['duration'] and sum(win) / len(win) > best:
                best = sum(win) / len(win); arr = {'name': iv['name'], 'camera': iv['camera'], 't_in': round(b0['t'], 2)}
    tl = json.load(open(base / 'timeline.json'))
    d = {'day': day, 'first_seen': tl['first_seen'], 'last_seen': tl['last_seen'],
         'arrival': {'kind': 'arrival', 'day': day, 'clip': arr['name'], 'camera': arr['camera'], 't_in': arr['t_in'], 'dur': 3.5} if arr else None,
         'sets': [shot('set', day, e, *window(day, e, a.window)) for e in picks],
         'peak': shot('peak', day, peak, *window(day, peak, a.window + 3)) if peak else None}
    plan['days'].append(d)
if a.hero:
    day, clip, t_in, dur, cap = a.hero.split(':', 4)
    plan['hero'] = {'kind': 'hero', 'day': day, 'clip': clip, 't_in': float(t_in), 'dur': float(dur), 'caption': cap}
if a.finale:
    fin = next((day, e) for day in a.days for e in json.load(open(ROOT / 'source' / a.client / day / 'exercises.json'))['sets'] if e['id'] == a.finale)
else:
    fin = max(allsets, key=lambda de: (de[1]['epic'], de[1]['camera'] == 'cam101', de[1]['slowdown'] or 0))
    for d in plan['days']:
        d['sets'] = [s for s in d['sets'] if s['set_id'] != fin[1]['id']]
        if d['peak'] and d['peak']['set_id'] == fin[1]['id']:
            d['peak'] = None
R = [t for t in rep_times(fin[0], fin[1]['clip']) if fin[1]['t0'] - 0.5 <= t <= fin[1]['t1'] + 0.5]
t_out = (R[-1] + 2.0) if R else fin[1]['t1']
t_in = max(fin[1]['t0'] - 1.0, t_out - 16)
plan['finale'] = shot('finale', fin[0], fin[1], round(t_in, 2), round(t_out - t_in, 2))
out = ROOT / 'work' / 'v003' / a.client; out.mkdir(parents=True, exist_ok=True)
json.dump(plan, open(out / 'plan.json', 'w'), indent=1, ensure_ascii=False)
for d in plan['days']:
    print(d['day'], 'sets', [(s['set_id'], s['exercise'][:28], s['t_in'], s['dur'], len(s['rep_times'])) for s in d['sets']],
          'peak', d['peak'] and (d['peak']['set_id'], d['peak']['exercise'][:30]))
print('finale', plan['finale']['set_id'], plan['finale']['exercise'], plan['finale']['t_in'], plan['finale']['dur'])
