"""Phase B: detect + track people on one camera within a time window.

usage: track.py DAY TRACK W0 W1 OUTDIR   (W0/W1 = seconds of day, local time)
Writes OUTDIR/tracks.json and OUTDIR/crops/<tid>_<sod*10>.jpg (one crop per track per second).
Runs RF-DETR (COCO person) at ~5 fps + ByteTrack (roboflow trackers) on the GPU.
"""
import json, sys, pathlib, time
import av, cv2, numpy as np, supervision as sv
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import visit_videos as vv
from rfdetr import RFDETRMedium
from trackers import ByteTrackTracker

day, track, w0, w1, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), pathlib.Path(sys.argv[5])
FPS, BATCH, CONF = 5.0, 16, 0.35
(out / 'crops').mkdir(parents=True, exist_ok=True)
model = RFDETRMedium()
PERSON = 1  # COCO category id returned by rfdetr predict
print('person class id', PERSON, flush=True)

segs = [s for s in vv.segments(day, track) if s[2] > w0 and s[1] < w1]
rows, tid_off, last_t = [], 0, None
tracker = None
last_crop = {}
t_start = time.time()


def flush(batch):
    global tid_off
    if not batch:
        return
    dets = model.predict([b[1][:, :, ::-1].copy() for b in batch], threshold=CONF)
    if not isinstance(dets, list):
        dets = [dets]
    for (sod, img), d in zip(batch, dets):
        if PERSON is not None:
            d = d[d.class_id == PERSON]
        d = tracker.update(d)
        for (x1, y1, x2, y2), tid, c in zip(d.xyxy, d.tracker_id, d.confidence):
            if tid is None or tid < 0:
                continue
            g = int(tid) + tid_off
            rows.append([g, round(sod, 2), int(x1), int(y1), int(x2), int(y2), round(float(c), 3)])
            if sod - last_crop.get(g, -9) >= 1.0 and (y2 - y1) >= 48 and (x2 - x1) >= 20:
                last_crop[g] = sod
                cr = img[max(0, int(y1)):int(y2), max(0, int(x1)):int(x2)]
                cv2.imwrite(str(out / 'crops' / f'{g:06d}_{int(sod * 10):06d}.jpg'), cr, [cv2.IMWRITE_JPEG_QUALITY, 90])


for path, s0, s1 in segs:
    if last_t is None or s0 - last_t > 3.0:  # gap -> new tracker, unique ids
        tid_off = (max([r[0] for r in rows]) + 1) if rows else 0
        tracker = ByteTrackTracker(frame_rate=FPS, lost_track_buffer=int(FPS * 4), track_activation_threshold=0.5, high_conf_det_threshold=0.5)
    try:
        c = av.open(str(path))
    except Exception as e:
        print('skip', path.name, e, flush=True)
        continue
    st = c.streams.video[0]
    st.thread_type = 'AUTO'
    nxt, batch = max(s0, w0), []
    try:
        for fr in c.decode(st):
            if fr.pts is None:
                continue
            sod = s0 + float((fr.pts - (st.start_time or 0)) * st.time_base)
            if sod < nxt:
                continue
            if sod > w1:
                break
            nxt = sod + 1.0 / FPS
            batch.append((sod, fr.to_ndarray(format='bgr24')))
            if len(batch) >= BATCH:
                flush(batch); batch = []
    except av.error.InvalidDataError as e:
        print('decode err', path.name, e, flush=True)
    flush(batch)
    c.close()
    last_t = s1
    print(f'{path.name} done rows={len(rows)} elapsed={time.time()-t_start:.0f}s', flush=True)

json.dump({'day': day, 'track': track, 'w0': w0, 'w1': w1, 'fps': FPS,
           'cols': ['tid', 'sod', 'x1', 'y1', 'x2', 'y2', 'conf'], 'rows': rows}, open(out / 'tracks.json', 'w'))
print('DONE', len(rows), 'rows', len({r[0] for r in rows}), 'tracks', f'{time.time()-t_start:.0f}s')
