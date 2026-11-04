"""Pose -> phases, sets, reps, effort signals (+ optional key-moment sheet).

Signals per frame (from <clip>.pose.json): elbow, knee and hip angles (left/right), torso tilt,
box centre motion, wrist height. A frame is "active" when one joint channel oscillates
(windowed std > 15 deg) while the box stays roughly in place (not walking).
Each active run >= 4 s with >= 3 extension peaks becomes a set, described by:
driver joint, reps, rep times/durations, range of motion, slowdown (last rep / median),
rest before the set (within the clip), and a post-set "arms up" celebration cue.
A lifting score ranks sets for the edit.

Usage: pose_events.py CLIP.mp4 [...] [--sheet]
"""
import sys, json, cv2, numpy as np
from scipy.signal import savgol_filter, find_peaks

SK = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]
CH = ['l_elbow', 'r_elbow', 'l_knee', 'r_knee', 'l_hip', 'r_hip']


def series(F, fn):
    v = np.array([fn(f) if f else np.nan for f in F], float)
    m = ~np.isnan(v)
    if m.sum() > 2: v = np.interp(np.arange(len(v)), np.flatnonzero(m), v[m])
    elif m.sum() <= 2: v[:] = np.nan
    return v, m


def wstd(x, w):
    """Windowed std (centred, half-width w) via cumulative sums; NaN-safe enough for interpolated series."""
    x = np.nan_to_num(x); c1 = np.concatenate([[0], np.cumsum(x)]); c2 = np.concatenate([[0], np.cumsum(x * x)])
    i = np.arange(len(x)); a = np.maximum(0, i - w); b = np.minimum(len(x), i + w); n = b - a
    m = (c1[b] - c1[a]) / n
    return np.sqrt(np.maximum(0, (c2[b] - c2[a]) / n - m * m))


def smooth(v, k):
    if np.isnan(v).all() or len(v) <= k: return v
    return savgol_filter(v, k, 2)


def lifting_score(s):
    reps = min(s['reps'], 15) / 10
    rom = min(s['rom'], 120) / 90
    effort = 1 + 0.5 * float(np.clip((s['slowdown'] or 1) - 1, 0, 2))
    sc = reps * rom * effort * min(1.2, s['conf'] / 0.6) * min(1.3, s['box_h'] / 160)
    if s['id_jump']: sc *= 0.5
    if s['moving']: sc *= 0.3
    return round(float(sc), 3)


def analyze(clip):
    P = json.load(open(clip[:-4] + '.pose.json')); F = P['frames']; fps = P['fps']; n = len(F)
    if sum(1 for f in F if f) < 3 * fps:
        return {'clip': clip, 'fps': fps, 'n': n, 'phases': [], 'sets': []}
    kp = lambda f, i: np.array(f['kp'][i]) if f['sc'][i] > 0.3 else None

    def mid(f, a, b):
        p, q = kp(f, a), kp(f, b)
        return (p + q) / 2 if p is not None and q is not None else (p if p is not None else q)

    def torso(f):
        s, h = mid(f, 5, 6), mid(f, 11, 12)
        if s is None or h is None: return np.nan
        d = s - h; return float(np.degrees(np.arctan2(abs(d[0]), -d[1])))

    def arms_up(f):  # both wrists above the nose / shoulder line by > 0.1 box heights
        h = max(1, f['box'][3] - f['box'][1]); S = mid(f, 5, 6)
        L, R = kp(f, 9), kp(f, 10)
        if S is None or L is None or R is None: return np.nan
        return float(min(S[1] - L[1], S[1] - R[1]) / h)

    tor = smooth(series(F, torso)[0], 31)
    up = series(F, arms_up)[0]
    bh = series(F, lambda f: f['box'][3] - f['box'][1])[0]
    cx = series(F, lambda f: (f['box'][0] + f['box'][2]) / 2)[0]
    cy = series(F, lambda f: (f['box'][1] + f['box'][3]) / 2)[0]
    # locomotion: centre travel over 1 s, in box heights
    W1 = int(fps)
    travel = np.zeros(n)
    travel[W1:] = np.hypot(cx[W1:] - cx[:-W1], cy[W1:] - cy[:-W1]) / np.maximum(bh[W1:], 1)
    moving = np.convolve(travel, np.ones(W1) / W1, 'same') > 0.25
    conf = np.array([np.mean(f['sc']) if f else 0 for f in F])
    jump = np.zeros(n, bool)
    for i in range(1, n):
        if F[i] and F[i - 1]:
            a, b = F[i]['box'], F[i - 1]['box']; h = max(1, a[3] - a[1])
            jump[i] = abs((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2) > .8 * h
    # phases per 1 s
    lab = []
    for s in range(0, n, int(fps)):
        seg = tor[s:s + int(fps)]
        t = np.nanmedian(seg) if not np.isnan(seg).all() else np.nan
        lab.append('unknown' if np.isnan(t) else 'lying' if t > 60 else 'bent' if t > 30 else 'upright')
    phases = []
    for i, l in enumerate(lab):
        if phases and phases[-1]['pose'] == l: phases[-1]['t1'] = i + 1
        else: phases.append({'pose': l, 't0': i, 't1': i + 1})
    # joint channels
    ang, sd = {}, {}
    win = int(fps * 1.5)
    for c in CH:
        v, m = series(F, lambda f, c=c: f['ang'][c] if f['ang'][c] is not None else np.nan)
        if np.isnan(v).all(): continue
        v = smooth(v, 21)
        ang[c] = v
        s = wstd(v, win)
        s[~np.convolve(m, np.ones(win), 'same').astype(bool)] = 0  # no real data nearby
        s = np.where(moving, 0, s)  # limbs swing while walking
        sd[c] = s
    if not sd:
        return {'clip': clip, 'fps': fps, 'n': n, 'phases': phases, 'sets': []}
    S = np.stack([sd[c] for c in sd]); names = list(sd)
    act = (S.max(0) > 15) & (conf > 0.45)
    runs, i = [], 0
    while i < n:
        if act[i]:
            j = i
            while j < n and act[j]: j += 1
            if runs and i - runs[-1][1] < 1.5 * fps: runs[-1][1] = j
            else: runs.append([i, j])
            i = j
        else: i += 1
    sets = []
    for a, b in runs:
        if b - a < 4 * fps: continue
        drv = names[int(np.argmax(S[:, a:b].sum(1)))]
        x = ang[drv][a:b]; amp = np.percentile(x, 95) - np.percentile(x, 5)
        pk, _ = find_peaks(x, prominence=max(15, amp * 0.4), distance=int(fps * 0.8))
        if len(pk) < 3: continue
        pk = pk + a; dur = np.diff(pk) / fps
        u = up[b:min(n, b + int(4 * fps))]
        cel = float(np.nanmax(u)) if len(u) and not np.isnan(u).all() else None
        s = {'t0': round(a / fps, 1), 't1': round(b / fps, 1), 'pose': lab[min(len(lab) - 1, int((a + b) / 2 / fps))],
             'driver': drv, 'reps': len(pk), 'rep_times': [round(p / fps, 1) for p in pk],
             'rep_dur': [round(d, 2) for d in dur], 'rom': round(float(amp)), 'elbow_rom': round(float(amp)) if 'elbow' in drv else None,
             'slowdown': round(float(dur[-1] / np.median(dur)), 2) if len(dur) > 1 else None,
             'max_rep_dur': round(float(dur.max()), 2) if len(dur) else None,
             'conf': round(float(conf[a:b].mean()), 2), 'box_h': round(float(np.nanmedian(bh[a:b]))),
             'id_jump': bool(jump[a:b].any()), 'moving': bool(moving[a:b].mean() > 0.5),
             'arms_up_after': round(cel, 2) if cel is not None else None,
             'celebration': bool(cel is not None and cel > 0.1)}
        s['rest_before'] = round(s['t0'] - sets[-1]['t1'], 1) if sets else None
        s['score'] = lifting_score(s)
        sets.append(s)
    return {'clip': clip, 'fps': fps, 'n': n, 'phases': phases, 'sets': sets}


def draw(img, fr):
    K = np.array(fr['kp']); S = fr['sc']
    for a, b in SK:
        if S[a] > .3 and S[b] > .3: cv2.line(img, tuple(map(int, K[a])), tuple(map(int, K[b])), (0, 200, 255), 2)
    for i in range(17):
        if S[i] > .3: cv2.circle(img, tuple(map(int, K[i])), 3, (0, 255, 0), -1)


def tile(cap, F, fps, t, label, size=240, zoom=1.3):
    n = len(F); f = int(t * fps)
    if f < 0 or f >= n: return None
    cap.set(1, f); ok, img = cap.read()
    near = next((F[j] for j in (f, f - 3, f + 3, f - 8, f + 8) if 0 <= j < n and F[j]), None)
    if not ok or near is None: return None
    draw(img, near)
    x0, y0, x1, y1 = near['box']; cx, cy, s = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) * zoom
    X0, Y0 = int(max(0, cx - s / 2)), int(max(0, cy - s / 2))
    c = cv2.resize(img[Y0:int(min(720, cy + s / 2)), X0:int(min(1280, cx + s / 2))], (size, size))
    cv2.rectangle(c, (0, 0), (size, 18), (0, 0, 0), -1)
    cv2.putText(c, label, (3, 13), 0, 0.42, (255, 255, 255), 1)
    return c


def sheet(clip, ev):
    P = json.load(open(clip[:-4] + '.pose.json')); F = P['frames']; fps = P['fps']
    keys = [(p['t0'] + 0.5, p['pose']) for p in ev['phases'] if p['t1'] - p['t0'] >= 3]
    for k, s in enumerate(ev['sets']):
        R = s['rep_times']
        for j in sorted({0, len(R) // 2, len(R) - 1}):
            keys.append((R[j], f"set{k+1} rep{j+1}/{s['reps']}"))
    keys.sort()
    cap = cv2.VideoCapture(clip)
    tiles = [x for x in (tile(cap, F, fps, t, f'{t:5.1f}s {l}') for t, l in keys[:40]) if x is not None]
    if not tiles: return
    while len(tiles) % 8: tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(clip[:-4] + '.keys.jpg', np.vstack([np.hstack(tiles[i:i + 8]) for i in range(0, len(tiles), 8)]))


def main(clip):
    ev = analyze(clip)
    json.dump(ev, open(clip[:-4] + '.events.json', 'w'), indent=1)
    if '--sheet' in sys.argv: sheet(clip, ev)
    print(clip.rsplit('/', 1)[1], len(ev['sets']), 'sets', [(s['t0'], s['reps'], s['driver'], s['score']) for s in ev['sets']])


if __name__ == '__main__':
    for c in sys.argv[1:]:
        if c.endswith('.mp4'): main(c)
