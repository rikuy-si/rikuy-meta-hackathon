#!/usr/bin/env python3
"""Stream full-recording browser copies, detect people with RF-DETR, track with ByteTrack.

Outputs compact per-recording JSONL.gz (one line per sampled frame) under the cold
vision-analysis directory. Never materializes raw RGB frames on disk.
Original frame indices are preserved (browser copies keep every source video frame).
"""
import argparse, gzip, json, time, sys
from pathlib import Path

import av
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"
OUT = VR / "media/vision-analysis/tracks"
WINDOW_END = 7544.0  # timeline seconds (camera 16:15:08)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--recordings", default="1-8")
    ap.add_argument("--max-seconds", type=float, default=None, help="benchmark limit per run")
    ap.add_argument("--start", type=float, default=0.0, help="start offset in first recording (s)")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--model", default="small")
    ap.add_argument("--tag", default="run")
    a = ap.parse_args()

    from rfdetr import RFDETRSmall, RFDETRMedium
    from trackers import ByteTrackTracker

    model = (RFDETRSmall if a.model == "small" else RFDETRMedium)()
    try:
        model.optimize_for_inference()
    except Exception as e:  # optional
        print("optimize_for_inference skipped:", e, file=sys.stderr)
    tracker = ByteTrackTracker(frame_rate=a.fps)
    pl = json.load(open(VR / "full-playlist.json"))
    lo, hi = map(int, a.recordings.split("-"))
    recs = [r for r in pl["recordings"] if lo <= r["id"] <= hi]
    OUT.mkdir(parents=True, exist_ok=True)
    step = round(15 / a.fps)
    t0 = time.time(); n = 0; done_media = 0.0
    torch.cuda.reset_peak_memory_stats()
    for r in recs:
        limit_frames = r["frames"]
        if r["timelineStart"] + r["duration"] > WINDOW_END:
            limit_frames = int((WINDOW_END - r["timelineStart"]) * 15) + 1
        out = OUT / f"{a.tag}-rec{r['id']:02d}.jsonl.gz"
        f = gzip.open(out, "wt")
        c = av.open(str(VR / "media/full-playlist-v1" / r["file"]))
        s = c.streams.video[0]; s.thread_type = "AUTO"
        start_frame = int(a.start * 15) if r is recs[0] else 0
        if start_frame:
            c.seek(int(start_frame / 15 / s.time_base), stream=s, backward=True)
        buf = []

        def flush():
            nonlocal n
            if not buf:
                return
            dets = model.predict([b[1] for b in buf], threshold=a.threshold)
            if not isinstance(dets, list):
                dets = [dets]
            for (idx, img), d in zip(buf, dets):
                d = d[d.class_id == 1] if d.class_id is not None else d  # COCO person (rfdetr 1-indexed)
                d = tracker.update(d)
                h, w = img.shape[:2]
                rows = [[int(t), *[round(float(v), 4) for v in (xy / [w, h, w, h])], round(float(cf), 3)]
                        for t, xy, cf in zip(d.tracker_id, d.xyxy, d.confidence)]
                f.write(json.dumps({"rec": r["id"], "frame": idx, "t": round(r["timelineStart"] + idx / 15, 3), "p": rows}) + "\n")
                n += 1
            buf.clear()

        for fr in c.decode(s):
            idx = round(float(fr.pts * s.time_base) * 15)
            if idx < start_frame or idx % step:
                continue
            if idx >= limit_frames:
                break
            if a.max_seconds and (idx - start_frame) / 15 > a.max_seconds:
                break
            buf.append((idx, fr.to_ndarray(format="rgb24")))
            if len(buf) >= a.batch:
                flush()
        flush(); f.close(); c.close()
        done_media += min(limit_frames, r["frames"]) / 15
        el = time.time() - t0
        print(json.dumps({"rec": r["id"], "frames_out": n, "elapsed_s": round(el, 1), "fps": round(n / el, 2),
                          "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2)}), flush=True)
        if a.max_seconds:
            break


if __name__ == "__main__":
    main()
