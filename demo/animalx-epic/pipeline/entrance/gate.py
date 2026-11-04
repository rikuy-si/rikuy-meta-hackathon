"""Detect people at the entrance turnstile (camera 03) across 2026-10-29 05:00-22:00.

Outputs (in work/):
  det/<clip>.json   per-clip detections: [t_rel, x1,y1,x2,y2, conf] for people overlapping the gate ROI
  osd/<clip>.json   OCR'd on-screen clock samples: [t_rel, osd_seconds_of_day]
Detector: RF-DETR Medium (Apache-2.0, COCO person), the same model as epic/track.py.
Run: uv run --with rfdetr --with supervision --with av --with opencv-python-headless python gate.py [workers]
"""
import json, sys, os, re, subprocess, tempfile, pathlib, multiprocessing as mp
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
import os as _os
WORK = ROOT / _os.environ.get('GATE_WORK', 'work')
GATE = (360, 40, 720, 380)          # x1,y1,x2,y2 in 1280x720 frame (turnstile area)
STRIDE = 5                          # analyse every 5th frame (~5 fps at 25 fps)
OSD_EVERY = 30.0                    # seconds between OSD clock reads
CONF = 0.35                         # detection threshold
PERSON = 1                          # COCO category id returned by rfdetr predict

def clips(day='2026-10-29', track='301'):
    """(absolute path, start) for every recording of `track` on `day` (local time)."""
    out = []
    if day == '2026-10-29':
        from frames import REC, DVR
        for r in REC:
            if r['track'] == track and r['start'][:10] == day and '05' <= r['start'][11:13] < '22':
                out.append((str(DVR / r['file']), r['start']))
    else:
        man = json.load(open(ROOT / 'visits' / 'dvr' / 'manifest.json'))
        for k, c in man.items():
            if c.get('ok') and c['track'] == track and c['start'][:10] == day:
                out.append((str(ROOT / 'visits' / 'dvr' / c['file']), c['start']))
    return sorted(out, key=lambda x: x[1])

def ocr_osd(img):
    import cv2
    crop = img[30:64, 222:372]
    crop = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    variants = [255 - g, g, np.where(g > 200, 0, 255).astype(np.uint8), np.where(g < 60, 0, 255).astype(np.uint8)]
    votes = {}
    with tempfile.TemporaryDirectory() as d:
        for i, v in enumerate(variants):
            p = os.path.join(d, f'{i}.png'); cv2.imwrite(p, v)
            t = subprocess.run(['tesseract', p, '-', '--psm', '7', '-c', 'tessedit_char_whitelist=0123456789:'],
                               capture_output=True, text=True).stdout.replace(' ', '')
            m = re.search(r'(\d{2}):?(\d{2}):?(\d{2})', t)
            if m:
                H, M, S = map(int, m.groups())
                if H < 24 and M < 60 and S < 60:
                    s = H * 3600 + M * 60 + S
                    votes[s] = votes.get(s, 0) + 1
    return max(votes, key=votes.get) if votes else None

def overlap(b):
    x1, y1, x2, y2 = b
    ix = max(0, min(x2, GATE[2]) - max(x1, GATE[0])); iy = max(0, min(y2, GATE[3]) - max(y1, GATE[1]))
    return ix * iy / max(1.0, (x2 - x1) * (y2 - y1))

def worker(job):
    idx, items = job
    import av, cv2
    from rfdetr import RFDETRMedium
    model = RFDETRMedium()
    for rel, start in items:
        name = pathlib.Path(rel).stem
        dp, op = WORK / 'det' / f'{name}.json', WORK / 'osd' / f'{name}.json'
        if dp.exists() and op.exists():
            continue
        dets, osd = [], []
        try:
            c = av.open(rel); s = c.streams.video[0]; s.thread_type = 'AUTO'
            t0 = None; n = 0; next_osd = 0.0; batch, times = [], []
            def flush():
                if not batch: return
                res = model.predict([im[:, :, ::-1].copy() for im in batch], threshold=CONF)  # BGR -> RGB
                if not isinstance(res, list):
                    res = [res]
                for t, d in zip(times, res):
                    d = d[d.class_id == PERSON]
                    for b, cf in zip(d.xyxy.tolist(), d.confidence.tolist()):
                        if overlap(b) >= 0.3:
                            dets.append([round(t, 2)] + [round(v) for v in b] + [round(cf, 3)])
                batch.clear(); times.clear()
            for fr in c.decode(s):
                if fr.pts is None: continue
                t = float(fr.pts * s.time_base)
                if t0 is None: t0 = t
                rel_t = t - t0
                n += 1
                take_osd = rel_t >= next_osd
                if n % STRIDE and not take_osd: continue
                img = fr.to_ndarray(format='bgr24')
                if take_osd:
                    v = ocr_osd(img)
                    if v is not None: osd.append([round(rel_t, 2), v])
                    next_osd = rel_t + OSD_EVERY
                if n % STRIDE == 0:
                    batch.append(img); times.append(rel_t)
                    if len(batch) >= 32: flush()
            flush(); c.close()
        except Exception as e:
            print('ERR', name, e, flush=True)
        dp.write_text(json.dumps({'start': start, 'dets': dets}))
        op.write_text(json.dumps({'start': start, 'osd': osd}))
        print(idx, name, len(dets), 'dets', len(osd), 'osd', flush=True)

if __name__ == '__main__':
    (WORK / 'det').mkdir(parents=True, exist_ok=True); (WORK / 'osd').mkdir(parents=True, exist_ok=True)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    cs = clips(_os.environ.get('GATE_DAY', '2026-10-29'))
    jobs = [(i, cs[i::n]) for i in range(n)]
    mp.set_start_method('spawn')
    with mp.Pool(n) as p:
        p.map(worker, jobs)
    print('DONE', len(cs))
