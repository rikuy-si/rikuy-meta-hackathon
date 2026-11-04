"""Turn gate detections into passage events, align ERP entry minutes with video time,
and pick candidate frames for each identified entry.

Outputs: work/events.json, work/alignment.json, work/matches.json
"""
import json, glob, pathlib, csv, statistics, datetime as dt
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
import os as _os
W = ROOT / _os.environ.get('GATE_WORK', 'work')
CORE = (400, 60, 680, 360)   # tighter turnstile box for "passing" (1280x720 coords)

def day_seconds(iso):
    t = dt.datetime.fromisoformat(iso.rstrip('Z'))
    return t.hour * 3600 + t.minute * 60 + t.second

def clip_mapping(osd_file):
    d = json.load(open(osd_file))
    s0 = day_seconds(d['start'])
    pts = [(t, v) for t, v in d['osd'] if abs(v - (s0 + t)) < 900]
    if len(pts) >= 2:
        offs = [v - t for t, v in pts]
        med = statistics.median(offs)
        good = [(t, v) for t, v in pts if abs((v - t) - med) <= 3]
        if len(good) >= 3:
            a, b = np.polyfit([t for t, _ in good], [v for _, v in good], 1)
            if 0.9 < a < 1.1:
                return lambda t, a=a, b=b: a * t + b, 'fit', len(good)
        return lambda t, m=med: t + m, 'median', len(pts)
    if len(pts) == 1:
        m = pts[0][1] - pts[0][0]
        return lambda t, m=m: t + m, 'single', 1
    return lambda t, s0=s0: s0 + t, 'manifest', 0

def in_core(x1, y1, x2, y2):
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    return CORE[0] <= cx <= CORE[2] and CORE[1] <= cy <= CORE[3]

def build():
    frames = []   # (day_s, clip, t_rel, box, conf)
    stats = {}
    for f in sorted(glob.glob(str(W / 'det' / '*.json'))):
        name = pathlib.Path(f).stem
        d = json.load(open(f))
        fmap, kind, n = clip_mapping(W / 'osd' / f'{name}.json')
        stats[kind] = stats.get(kind, 0) + 1
        for t, x1, y1, x2, y2, cf in d['dets']:
            if in_core(x1, y1, x2, y2):
                frames.append((fmap(t), name, t, (x1, y1, x2, y2), cf))
    frames.sort()
    # group into passage events: detections separated by < 2.5 s belong to the same event
    events = []
    for fr in frames:
        if events and fr[0] - events[-1]['end'] < 2.5:
            e = events[-1]; e['end'] = fr[0]; e['dets'].append(fr)
        else:
            events.append({'start': fr[0], 'end': fr[0], 'dets': [fr]})
    out = []
    for e in events:
        dur = e['end'] - e['start']
        if dur < 0.6 or dur > 120:     # flicker or someone lingering at the desk
            continue
        # prefer a frame where the whole person is visible (box not cut at the top edge), then size x confidence
        best = max(e['dets'], key=lambda d: (d[3][2] - d[3][0]) * (d[3][3] - d[3][1]) * d[4] * (1.0 if d[3][1] > 12 else 0.35))
        ds = e['dets']; k = max(1, len(ds) // 6)
        samples = [{'clip': d[1], 't_rel': d[2], 'day_s': round(d[0], 1), 'box': d[3]} for d in ds[::k][:6]]
        out.append({'start': round(e['start'], 1), 'end': round(e['end'], 1), 'n': len(e['dets']), 'samples': samples,
                    'best': {'clip': best[1], 't_rel': best[2], 'day_s': round(best[0], 1), 'box': best[3], 'conf': best[4]}})
    json.dump({'mapping_kinds': stats, 'events': out}, open(W / 'events.json', 'w'))
    return out, stats

def align(events, entries):
    starts = np.array([e['start'] for e in events])
    best = None
    scores = []
    for lag in range(-600, 601, 2):
        hit = 0
        for m in entries:
            lo, hi = m * 60 + lag, m * 60 + 60 + lag
            if ((starts >= lo) & (starts < hi)).any():
                hit += 1
        scores.append((lag, hit))
        if best is None or hit > best[1]:
            best = (lag, hit)
    # prefer the lag closest to 0 among near-ties
    top = max(h for _, h in scores)
    near = [l for l, h in scores if h >= top - 1]
    lag = min(near, key=abs)
    return lag, top, scores

def add_direction(events):
    import bisect, collections
    tracks = collections.defaultdict(list)
    for f in glob.glob(str(W / 'det' / '*.json')):
        n = pathlib.Path(f).stem; fm, _, _ = clip_mapping(W / 'osd' / f'{n}.json')
        for t, x1, y1, x2, y2, c in json.load(open(f))['dets']:
            tracks[n].append((fm(t), (x1 + x2) / 2, y2))
    for n in tracks: tracks[n].sort()
    for e in events:
        L = tracks[e['best']['clip']]; ts = [d[0] for d in L]
        seg = L[bisect.bisect_left(ts, e['start'] - 4):bisect.bisect_right(ts, e['end'] + 4)]
        if len(seg) < 3: e['dir'] = None; continue
        k = max(1, len(seg) // 4); a, b = seg[:k], seg[-k:]
        e['dir'] = [round(sum(p[1] for p in b) / k - sum(p[1] for p in a) / k), round(sum(p[2] for p in b) / k - sum(p[2] for p in a) / k)]
    json.dump({'events': events}, open(W / 'events_dir.json', 'w'))

def main():
    events, stats = build()
    add_direction(events)
    rows = list(csv.DictReader(open(ROOT / 'exports' / 'entradas_2026-10-29.csv')))
    mins = [int(r['hora_local'][:2]) * 60 + int(r['hora_local'][3:]) for r in rows]
    lag, top, scores = align(events, mins)
    base = sum(1 for m in mins if any(m * 60 <= e['start'] < m * 60 + 60 for e in events))
    json.dump({'lag_s': lag, 'hits': top, 'entries': len(mins), 'hits_at_zero': base, 'events': len(events),
               'mapping_kinds': stats, 'scores': scores}, open(W / 'alignment.json', 'w'))
    print('events', len(events), 'mapping', stats, 'lag', lag, 'hits', top, '/', len(mins), 'at lag0', base)

if __name__ == '__main__':
    main()
