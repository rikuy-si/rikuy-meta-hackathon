"""Self-review for an edit: automatic checks + contact sheets for a review pass over EVERY second by the Muse Code agent on pi.dev (model: Muse Wonder).

usage: qa_video.py EDIT_DIR|VIDEO.mp4 [--fine START END]   (a .mp4 with <stem>.edl.json/.audit.json/.texts.json beside it)
Writes EDIT_DIR/qa/: sheet_NN.jpg (one tile per second, 4x4, labelled with time and EDL segment),
fine_NN.jpg (2 fps, 960x540 tiles) for --fine START..END, and qa.json with the automatic checks:
  flashes      WCAG 2.3.1 general-flash proxy: luminance swings >= 10 % in both directions, <= 3 per second
  black        frames with mean < 6 (the brand has no pure black; fades go through Noche)
  frozen       runs of > 2 s with identical frames outside freeze segments
  audio        peak dBFS (clipping if > -0.1) and silent stretches > 1 s
  texts        every text drawn, from texts.json (dash, safe-area, size and glyph guards already ran at draw time)
  cuts         cut-to-beat error from audit.json
"""
import sys, json, pathlib, subprocess, argparse
import numpy as np, cv2, soundfile as sf

ap = argparse.ArgumentParser(); ap.add_argument('edit'); ap.add_argument('--fine', nargs=2, type=float, action='append', default=[])
a = ap.parse_args()
P = pathlib.Path(a.edit)
if P.suffix == '.mp4':
    mp4 = P; E = P.parent; stem = P.with_suffix(''); q = E / f'qa_{P.stem}'
    EDL, AUD, TXT = [pathlib.Path(f'{stem}.{k}.json') for k in ('edl', 'audit', 'texts')]
else:
    E = P; mp4 = next(p for p in E.glob('*.mp4')); q = E / 'qa'
    EDL, AUD, TXT = E / 'edl.json', E / 'audit.json', E / 'texts.json'
q.mkdir(exist_ok=True)
edl = json.load(open(EDL))
segat = lambda t: next((e['kind'] for e in edl if e['t'] <= t < e['t'] + e['dur']), '?')
cap = cv2.VideoCapture(str(mp4)); fps = cap.get(5); N = int(cap.get(7))
PORT = cap.get(4) > cap.get(3)
TW, TH = (216, 384) if PORT else (480, 270)
FW, FH = (432, 768) if PORT else (960, 540)
COLS, FCOLS = (8, 4) if PORT else (4, 2)
lum, prev, frozen_run, frozen = [], None, 0, []
per_sec = {}
fine_t = {round(t * 2) / 2 for s, e in a.fine for t in np.arange(s, e, 0.5)}
fine = {}
for i in range(N):
    ok, fr = cap.read()
    if not ok: break
    t = i / fps
    g = cv2.cvtColor(cv2.resize(fr, (192, 108)), cv2.COLOR_BGR2GRAY)
    lum.append(float(g.mean()) / 255)
    if prev is not None and np.abs(g.astype(int) - prev).mean() < 0.3:
        frozen_run += 1
    else:
        if frozen_run > 2 * fps: frozen.append((round((i - frozen_run) / fps, 2), round(frozen_run / fps, 2), segat((i - frozen_run) / fps)))
        frozen_run = 0
    prev = g.astype(int)
    if i % int(round(fps)) == 0:
        tile = cv2.copyMakeBorder(cv2.resize(fr, (TW, TH), interpolation=cv2.INTER_AREA), 0, 24, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(tile, f'{t:5.0f}s {segat(t)}'[:30], (4, TH + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
        per_sec[int(round(t))] = tile
    if round(t * 2) / 2 in fine_t and abs(t * 2 - round(t * 2)) < 1 / fps:
        tile = cv2.copyMakeBorder(cv2.resize(fr, (FW, FH), interpolation=cv2.INTER_AREA), 0, 30, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(tile, f'{t:6.2f}s  {segat(t)}', (8, FH + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1, cv2.LINE_AA)
        fine[round(t * 2) / 2] = tile
for p in q.glob('*.jpg'): p.unlink()
keys = sorted(per_sec); blank = np.zeros((TH + 24, TW, 3), np.uint8)
for k in range(0, len(keys), 16):
    ts = [per_sec[x] for x in keys[k:k + 16]] + [blank] * (16 - len(keys[k:k + 16]))
    cv2.imwrite(str(q / f'sheet_{k // 16:02d}.jpg'), np.vstack([np.hstack(ts[r:r + COLS]) for r in range(0, 16, COLS)]), [cv2.IMWRITE_JPEG_QUALITY, 88])
fk = sorted(fine); blank2 = np.zeros((FH + 30, FW, 3), np.uint8)
for k in range(0, len(fk), 4):
    ts = [fine[x] for x in fk[k:k + 4]] + [blank2] * (4 - len(fk[k:k + 4]))
    cv2.imwrite(str(q / f'fine_{k // 4:02d}.jpg'), np.vstack([np.hstack(ts[r:r + FCOLS]) for r in range(0, 4, FCOLS)]), [cv2.IMWRITE_JPEG_QUALITY, 88])
L = np.array(lum)
# general-flash proxy: count opposing swings >= 0.1 within each 1 s window
d = np.diff(L); ev = []
i = 0
while i < len(d):
    if abs(d[i]) >= 0.1:
        ev.append((i, np.sign(d[i]))); i += 2
    else:
        i += 1
flash_rate = 0
for k in range(len(ev)):
    win = [s for j, s in ev if ev[k][0] <= j < ev[k][0] + fps]
    pairs = sum(1 for x, y in zip(win, win[1:]) if x != y)
    flash_rate = max(flash_rate, (pairs + 1) // 2)
black = [round(i / fps, 2) for i, v in enumerate(L) if v < 6 / 255]
au = subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-i', str(mp4), '-ac', '1', '-ar', '22050', '-f', 'wav', '-'], capture_output=True).stdout
open(q / 'audio.wav', 'wb').write(au); y, sr = sf.read(q / 'audio.wav'); (q / 'audio.wav').unlink()
rms = np.sqrt(np.convolve(y ** 2, np.ones(sr // 10) / (sr // 10), 'valid'))
silent = (rms < 10 ** (-50 / 20)); runs, r0 = [], None
for i, s in enumerate(silent[::sr // 20]):
    if s and r0 is None: r0 = i
    if not s and r0 is not None:
        if (i - r0) / 20 > 1: runs.append((round(r0 / 20, 2), round((i - r0) / 20, 2)))
        r0 = None
audit = json.load(open(AUD))
texts = json.load(open(TXT)) if TXT.exists() else []
uniq = sorted({x['text'] for x in texts if not x['text'].isdigit()})
res = {'video': str(mp4), 'frames': len(L), 'duration_s': round(len(L) / fps, 2),
       'flashes_max_per_s': flash_rate, 'flash_ok': flash_rate <= 3,
       'black_frames': len(black), 'black_first': black[:5],
       'frozen_runs_gt_2s': frozen,
       'audio_peak_dbfs': round(20 * np.log10(np.abs(y).max() + 1e-9), 2), 'audio_silent_runs_gt_1s': runs,
       'cuts_on_beat_max_err_s': audit.get('cuts_on_beat_max_err_s'),
       'texts_unique': uniq, 'sheets': len(list(q.glob('sheet_*.jpg'))), 'fine_sheets': len(list(q.glob('fine_*.jpg')))}
json.dump(res, open(q / 'qa.json', 'w'), indent=1, ensure_ascii=False)
print(json.dumps({k: v for k, v in res.items() if k != 'texts_unique'}, ensure_ascii=False))
print('TEXTS:', ' | '.join(uniq))
