"""Label check: for every footage shot in an EDL, 5 crops around the client (source resolution) in one row.
usage: label_check.py CLIENT EDIT_DIR -> EDIT_DIR/qa/labels_NN.jpg (5 shots per sheet)"""
import sys, json, pathlib
import numpy as np, cv2
ROOT = pathlib.Path(__file__).resolve().parent
client, E = sys.argv[1], pathlib.Path(sys.argv[2])
EDL = E if E.suffix == '.json' else E / 'edl.json'
if E.suffix == '.json': E = E.parent / ('labels_' + E.name.split('.')[0])
edl = [e for e in json.load(open(EDL)) if 'clip' in e]
wd = ROOT / 'work' / 'v003' / client
rows = []
for e in edl:
    clip = ROOT / 'source' / client / e['day'] / 'clips' / f"{e['clip']}.mp4"
    mk = [p for p in (wd / 'masks').glob(f"{e['day']}_{e['clip']}_*.npz")]
    zs = [np.load(p) for p in mk]                                     # the mask whose time range covers this shot
    z = max(zs, key=lambda z: min(z['times'].max(), e['src_out']) - max(z['times'].min(), e['src_in'])); cap = cv2.VideoCapture(str(clip)); vf = cap.get(5)
    tiles = []
    for t in np.linspace(e['src_in'], e['src_out'], 5):
        cap.set(1, int(round(t * vf))); fr = cap.read()[1]
        i = int(np.argmin(np.abs(z['times'] - t))); m = np.unpackbits(z['masks'][i], axis=-1)[:, :1280].astype(bool)
        ys, xs = np.nonzero(m)
        cx, cy, s = (xs.mean(), ys.mean(), max(np.ptp(xs), np.ptp(ys)) * 1.4) if len(xs) else (640, 360, 400)
        s = int(np.clip(s, 200, 700)); x0 = int(np.clip(cx - s / 2, 0, 1280 - s)); y0 = int(np.clip(cy - s / 2, 0, 720 - s))
        tiles.append(cv2.resize(fr[y0:y0 + s, x0:x0 + s], (360, 360)))
    row = np.hstack(tiles)
    bar = np.full((36, row.shape[1], 3), 255, np.uint8)
    cv2.putText(bar, f"{e['t']:.0f}s {e['kind']} {e.get('set_id')} | {e['lower'][0]} | {e['day']} {e['clip']} {e['src_in']}-{e['src_out']}", (6, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    rows.append(np.vstack([bar, row]))
(E / 'qa').mkdir(parents=True, exist_ok=True)
for k in range(0, len(rows), 5):
    cv2.imwrite(str(E / 'qa' / f'labels_{k // 5:02d}.jpg'), np.vstack(rows[k:k + 5]), [cv2.IMWRITE_JPEG_QUALITY, 85])
print(len(rows), 'shots')
