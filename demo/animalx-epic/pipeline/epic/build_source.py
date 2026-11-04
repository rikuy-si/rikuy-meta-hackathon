"""Phase E: build the per-client source library from labels + classifier output.

usage: build_source.py CLIENT DAY [--auto 0.9] [--no-video]
Presence per camera = rows of tracks labeled 1 (confirmed) + rows of unlabeled tracks with classifier
probability >= --auto (auto) + rows of tracks labeled "p" (ID switch) restricted to +-1 s around crops
with crop probability >= 0.5 (auto). Rows are merged into intervals (gap <= 20 s), padded +-3 s, and cut
from the DVR recordings at native 1280x720 / 30 fps (h264_nvenc, cq 19).
Outputs under source/<client>/<day>/:  clips/*.mp4, clips/*.track.json, sheets/*.jpg, presence.json
"""
import sys, json, pathlib, argparse, subprocess, tempfile, collections
import numpy as np, cv2

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import visit_videos as vv

ap = argparse.ArgumentParser()
ap.add_argument('client'); ap.add_argument('day')
ap.add_argument('--auto', type=float, default=0.9); ap.add_argument('--no-video', action='store_true')
ap.add_argument('--gap', type=float, default=20); ap.add_argument('--pad', type=float, default=3)
a = ap.parse_args()
base = ROOT / 'source' / a.client / a.day
labels = json.load(open(base / 'labels.json')) if (base / 'labels.json').exists() else {}
# phase J: tracks rescued from library holes after review by the Muse Code agent on pi.dev (model: Muse Wonder) (work/rescue/<client>_<day>/review.json)
_rv = ROOT / 'work' / 'rescue' / f'{a.client}_{a.day}' / 'review.json'
_sod = lambda s: sum(int(v) * m for v, m in zip(s.split(':'), (3600, 60, 1)))
RESCUED = collections.defaultdict(dict)
if _rv.exists():
    for r in json.load(open(_rv))['accepted']:
        RESCUED[r['cam']][r['tid']] = None if r['range'] == 'all' else (_sod(r['range'][0]) - 0.5, _sod(r['range'][1]) + 0.5)
FPS = 30


def hms(s, sep=''):
    s = int(round(s)); return f'{s // 3600:02d}{sep}{s % 3600 // 60:02d}{sep}{s % 60:02d}'


def enc(args, dest, dur):
    r = subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-y', *args, '-an', '-t', f'{dur:.3f}',
                        '-vf', f'fps={FPS},scale=1280:720,setsar=1,format=yuv420p,tpad=stop=-1:stop_mode=clone',
                        '-c:v', 'h264_nvenc', '-preset', 'p5', '-cq', '19', '-g', str(FPS * 2), '-r', str(FPS),
                        '-video_track_timescale', '90000', str(dest)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-300:])


def cut(track, w0, w1, dest):
    segs = [s for s in vv.segments(a.day, track) if s[2] > w0 and s[1] < w1]
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        tmp = pathlib.Path(tmp); pieces = []; cursor = w0

        def gap(d):
            if d >= 1 / FPS:
                p = tmp / f'{len(pieces):04d}.mp4'
                enc(['-f', 'lavfi', '-i', f'color=black:s=1280x720:r={FPS}:d={d:.3f}'], p, d); pieces.append(p)
        for path, s0, s1 in segs:
            x, y = max(s0, w0, cursor), min(s1, w1)
            if y - x < 0.2:
                continue
            gap(x - cursor)
            p = tmp / f'{len(pieces):04d}.mp4'
            try:
                enc(['-ss', f'{x - s0:.3f}', '-t', f'{y - x:.3f}', '-i', str(path)], p, y - x); pieces.append(p)
            except RuntimeError:
                gap(y - x)
            cursor = y
        gap(w1 - cursor)
        lst = tmp / 'list.txt'; lst.write_text(''.join(f"file '{p.name}'\n" for p in pieces))
        r = subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst), '-c', 'copy',
                            '-movflags', '+faststart', str(dest)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr[-300:])


for d in ['clips', 'sheets']:
    (base / d).mkdir(exist_ok=True)
# time gate for automatic (unlabeled) tracks: from the first to the last confirmed sighting (+-120 s)
conf_t = []
for cam_dir in (base / 'tracks').glob('cam*'):
    if (cam_dir / 'tracks.json').exists():
        lab = labels.get(cam_dir.name, {})
        conf_t += [r[1] for r in json.load(open(cam_dir / 'tracks.json'))['rows'] if lab.get(str(r[0])) == 1]
GATE = (min(conf_t) - 120, max(conf_t) + 120) if conf_t else (0, 86400)
print('auto gate', hms(GATE[0], ':'), hms(GATE[1], ':'))
presence = {}
for cam_dir in sorted((base / 'tracks').glob('cam*')):
    cam = cam_dir.name
    if not (cam_dir / 'tracks.json').exists():
        continue
    rows = json.load(open(cam_dir / 'tracks.json'))['rows']
    lab = labels.get(cam, {})
    rk = base / 'matches' / f'rank_{cam}.json'
    rk = json.load(open(rk)) if rk.exists() else {'track_prob': {}, 'crop_prob': {}}
    tprob = {int(k): v for k, v in rk['track_prob'].items()}
    ptimes = collections.defaultdict(list)
    for n, v in rk['crop_prob'].items():
        if v >= 0.5:
            ptimes[int(n[:6])].append(int(n[7:13]) / 10)
    status = {}
    for t in {r[0] for r in rows}:
        v = lab.get(str(t))
        if t in RESCUED.get(cam, {}) and v != 1:
            status[t] = 'rescued'
        elif v == 1:
            status[t] = 'confirmed'
        elif v == 0:
            continue
        elif v == 'p':
            status[t] = 'partial'
        elif tprob.get(t, 0) >= a.auto:
            status[t] = 'auto'
    sel = []
    for r in rows:
        st = status.get(r[0])
        if not st:
            continue
        if st == 'rescued':
            rg = RESCUED[cam][r[0]]
            if rg and not (rg[0] <= r[1] <= rg[1]):
                continue
        elif st != 'confirmed' and not (GATE[0] <= r[1] <= GATE[1]):
            continue
        if st == 'partial' and not any(abs(r[1] - x) <= 1.0 for x in ptimes.get(r[0], [])):
            continue
        sel.append(r + [st])
    sel.sort(key=lambda r: r[1])
    ivs = []
    for r in sel:
        if ivs and r[1] - ivs[-1]['t1'] <= a.gap:
            ivs[-1]['t1'] = r[1]; ivs[-1]['rows'].append(r)
        else:
            ivs.append({'t0': r[1], 't1': r[1], 'rows': [r]})
    out = []
    for iv in ivs:
        if iv['t1'] - iv['t0'] < 2:
            continue
        w0, w1 = iv['t0'] - a.pad, iv['t1'] + a.pad
        name = f'{cam}_{hms(w0)}-{hms(w1)}'
        sts = collections.Counter(r[-1] for r in iv['rows'])
        verified = ('confirmed' if set(sts) == {'confirmed'} else 'rescued' if set(sts) == {'rescued'}
                    else 'auto' if not ({'confirmed', 'rescued'} & set(sts)) else 'mixed')
        tids = sorted({r[0] for r in iv['rows']})
        boxes = [{'sod': r[1], 't': round(r[1] - w0, 2), 'box': r[2:6], 'tid': r[0], 'status': r[-1]} for r in iv['rows']]
        json.dump({'client': a.client, 'day': a.day, 'camera': cam, 'w0': w0, 'w1': w1, 'fps': FPS, 'tids': tids,
                   'verified': verified, 'status_counts': dict(sts), 'boxes': boxes}, open(base / 'clips' / f'{name}.track.json', 'w'))
        # contact sheet from the client's crops in this interval
        crops = sorted(p for t in tids for p in (cam_dir / 'crops').glob(f'{t:06d}_*.jpg') if iv['t0'] - 1 <= int(p.name[7:13]) / 10 <= iv['t1'] + 1)
        if crops:
            pick = [crops[i] for i in np.linspace(0, len(crops) - 1, min(8, len(crops))).round().astype(int)]
            cv2.imwrite(str(base / 'sheets' / f'{name}.jpg'), np.hstack([cv2.resize(cv2.imread(str(p)), (100, 200)) for p in pick]))
        dest = base / 'clips' / f'{name}.mp4'
        if not a.no_video and not dest.exists():
            cut(cam[3:], w0, w1, dest)
        out.append({'name': name, 'camera': cam, 'start': hms(w0, ':'), 'end': hms(w1, ':'), 'w0': w0, 'w1': w1,
                    'duration': round(w1 - w0, 1), 'tids': tids, 'verified': verified,
                    'score': round(float(np.mean([tprob.get(t, 1.0) for t in tids])), 3)})
    presence[cam] = out
    print(cam, len(out), 'intervals', round(sum(o['duration'] for o in out) / 60, 1), 'min', dict(collections.Counter(o['verified'] for o in out)), flush=True)
json.dump(presence, open(base / 'presence.json', 'w'), indent=1)
# clips whose interval changed (merged with rescued rows) are moved aside with their derived files
names = {o['name'] for v in presence.values() for o in v}
old = [p for p in (base / 'clips').glob('cam*.track.json') if p.name[:-11] not in names]
if old:
    (base / 'clips' / '_superseded').mkdir(exist_ok=True)
    for p in old:
        for q in (base / 'clips').glob(p.name[:-11] + '.*'):
            q.rename(base / 'clips' / '_superseded' / q.name)
    print('superseded', len(old), 'clips')
