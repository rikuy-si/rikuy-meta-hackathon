"""Grab DVR frames for review: peek.py CLIENT DAY OUT.jpg CAM:TID:SOD [CAM:TID:SOD ...]
Each item -> 640x360 frame (scaled from 1280x720) with that track's box drawn, plus a 2x crop of the box."""
import sys, json, pathlib, subprocess, numpy as np, cv2
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import visit_videos as vv
client, day, out = sys.argv[1:4]
base = ROOT / 'source' / client / day
rows_cache = {}
tiles = []
for it in sys.argv[4:]:
    cam, tid, s = it.split(':'); tid = int(tid); s = float(s)
    if cam not in rows_cache: rows_cache[cam] = json.load(open(base / 'tracks' / cam / 'tracks.json'))['rows']
    R = [r for r in rows_cache[cam] if r[0] == tid]
    r = min(R, key=lambda r: abs(r[1] - s)) if R else None
    seg = next(((p, s0) for p, s0, s1 in vv.segments(day, cam[3:]) if s0 <= s < s1), None)
    if seg is None: continue
    raw = subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-ss', f'{s - seg[1]:.2f}', '-i', str(seg[0]), '-frames:v', '1',
                          '-vf', 'scale=1280:720', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], capture_output=True).stdout
    if len(raw) < 1280 * 720 * 3: continue
    img = np.frombuffer(raw[:1280 * 720 * 3], np.uint8).reshape(720, 1280, 3).copy()
    crop = np.zeros((360, 240, 3), np.uint8)
    if r:
        x0, y0, x1, y1 = map(int, r[2:6]); cv2.rectangle(img, (x0, y0), (x1, y1), (0, 255, 255), 2)
        h = y1 - y0; w = x1 - x0; cx, cy = (x0 + x1) // 2, (y0 + y1) // 2; S = int(max(h, w * 1.5) * 0.65)
        c = img[max(0, cy - S):cy + S, max(0, cx - int(S / 1.5)):cx + int(S / 1.5)]
        if c.size: crop = cv2.resize(c, (240, 360))
    f = cv2.resize(img, (640, 360))
    cv2.putText(f, it, (5, 20), 0, .6, (0, 255, 255), 2)
    tiles.append(np.hstack([f, crop]))
cv2.imwrite(out, np.vstack(tiles))
