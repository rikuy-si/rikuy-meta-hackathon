"""Rep-count check: pose reps (rep_times of the clip's sets inside the window) vs the review agent's manual count (Muse Code agent on pi.dev (model: Muse Wonder))."""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent
M = json.load(open(ROOT / 'work' / 'sets' / 'repcheck' / 'manual_counts.json')); rows = []
for m in M:
    E = json.load(open(ROOT / 'source' / m['client'] / m['day'] / 'clips' / f"{m['clip']}.events.json"))
    n = sum(1 for s in E['sets'] for t in s['rep_times'] if m['t_a'] <= t <= m['t_b'])
    rows.append({**m, 'pose_reps': n, 'diff': n - m['reps'], 'ok': abs(n - m['reps']) <= 1})
ok = sum(r['ok'] for r in rows)
json.dump({'n': len(rows), 'within_1': ok, 'rate': round(ok / len(rows), 2), 'rows': rows}, open(ROOT / 'work' / 'sets' / 'repcheck' / 'result.json', 'w'), indent=1)
for r in rows: print(f"{r['id']:8} manual {r['reps']:3} pose {r['pose_reps']:3} {'ok' if r['ok'] else 'MISS'}  {r['what']}")
print('within +-1:', ok, '/', len(rows))
