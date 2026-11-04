"""SAM 3 'person' masks: the evidence layer drawn over the footage.

SAM 3 (Meta) is prompted with the text concept ``person`` on sampled frames.
Masks are reduced to polygons so the static viewer can draw them. Output per
recording is the viewer's ``OVERLAY.sam`` format:

    {"start": iso, "fps": 2, "frames": [[[obj, score, [x0,y0,x1,y1], [[x,y,x,y,...]]], ...], ...]}

Use ``fps=2`` for the whole window and ``fps=15`` (``--hd``) on the peak
minutes; the HD pass is written to ``OVERLAY_HD`` with ``scale=1000`` ints.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .detect import iter_frames
from .recordings import Segment


def load_processor():
    from sam3.model.sam3_image_processor import Sam3Processor
    from sam3.model_builder import build_sam3_image_model

    return Sam3Processor(build_sam3_image_model())


def polygons(mask: np.ndarray, w: int, h: int, scale: float, eps: float = 2.0) -> list[list]:
    m = (mask > 0.5).astype(np.uint8)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:2]:
        if cv2.contourArea(c) < 40:
            continue
        c = cv2.approxPolyDP(c, eps, True).reshape(-1, 2) / np.array([w, h])
        out.append(_q(c.flatten(), scale))
    return out


def _q(a, scale: float) -> list:
    return [int(round(v * scale)) for v in a] if scale > 1 else [round(float(v), 4) for v in a]


def segment_frame(processor, frame_bgr: np.ndarray, prompt: str, scale: float, min_score: float) -> list:
    from PIL import Image

    h, w = frame_bgr.shape[:2]
    state = processor.set_image(Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)))
    res = processor.set_text_prompt(state=state, prompt=prompt)
    masks = res["masks"].squeeze(1).float().cpu().numpy()
    boxes = res["boxes"].float().cpu().numpy()
    scores = res["scores"].float().cpu().numpy()
    objs = []
    for i, (m, b, s) in enumerate(zip(masks, boxes, scores)):
        if s < min_score:
            continue
        box = _q(np.array(b) / np.array([w, h, w, h]), scale)
        objs.append([i, round(float(s), 2), box, polygons(m, w, h, scale)])
    return objs


def run(clips_dir: Path, segs: list[Segment], out: Path, fps: float = 2.0, hd: list[str] | None = None,
        prompt: str = "person", min_score: float = 0.5) -> None:
    processor = load_processor()
    scale = 1000.0 if hd else 1.0
    result = {}
    for s in segs:
        if hd and s.recording not in hd:
            continue
        frames = [segment_frame(processor, f, prompt, scale, min_score)
                  for _, f in iter_frames(clips_dir / s.recording, fps)]
        result[s.recording] = {"start": s.cam_start, "fps": fps, "frames": frames}
        if hd:
            result[s.recording]["scale"] = 1000
        print(f"segment {s.recording}: {len(frames)} frames")
    out.write_text(json.dumps(result))
