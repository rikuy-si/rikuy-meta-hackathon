"""RF-DETR person detection + ByteTrack tracking, sampled at 5 fps.

Runs on-premises next to the bridge: footage never leaves the site for this
stage. Output per recording is the viewer's ``OVERLAY.local`` format:

    [[t_rel_s, [[track_id, [x0, y0, x1, y1]], ...]], ...]   # boxes normalized 0..1
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .recordings import Segment

PERSON = 1  # COCO class id for "person" in RF-DETR's label map


def load_model(size: str = "base"):
    from rfdetr import RFDETRBase, RFDETRLarge

    model = RFDETRLarge() if size == "large" else RFDETRBase()
    model.optimize_for_inference()
    return model


def iter_frames(path: Path, fps: float):
    cap = cv2.VideoCapture(str(path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    step = max(1, round(src_fps / fps))
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            yield i / src_fps, frame
        i += 1
    cap.release()


def track_recording(model, path: Path, prefix: str, fps: float = 5.0, threshold: float = 0.5) -> list:
    import supervision as sv

    tracker = sv.ByteTrack(frame_rate=int(fps))
    out = []
    for t, frame in iter_frames(path, fps):
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        det = model.predict(rgb, threshold=threshold)
        det = det[det.class_id == PERSON]
        det = tracker.update_with_detections(det)
        boxes = []
        for xyxy, tid in zip(det.xyxy, det.tracker_id):
            x0, y0, x1, y1 = (xyxy / np.array([w, h, w, h])).round(4).tolist()
            boxes.append([f"{prefix}t{int(tid)}", [x0, y0, x1, y1]])
        out.append([round(t, 1), boxes])
    return out


def run(clips_dir: Path, segs: list[Segment], out: Path, fps: float = 5.0, size: str = "base") -> None:
    model = load_model(size)
    tracks = {}
    for i, s in enumerate(segs):
        # Prefix keeps track ids unique across recordings (r29t1, ...).
        tracks[s.recording] = track_recording(model, clips_dir / s.recording, f"r{i}", fps)
        print(f"detect {s.recording}: {len(tracks[s.recording])} frames")
    out.write_text(json.dumps(tracks))
