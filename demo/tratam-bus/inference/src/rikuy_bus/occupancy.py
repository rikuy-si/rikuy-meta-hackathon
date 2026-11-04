"""People in view per sample, from SAM 3 'person' masks.

Input is the ``sam`` overlay written by ``rikuy_gym.segment`` (one recording):
``{"fps": f, "scale": s, "frames": [[[obj, score, [x0,y0,x1,y1], polys], ...], ...]}``.
A mask counts when its score passes ``min_score`` and its box center falls inside
the cabin zone (normalized polygon), so people outside the windshield are ignored.
"""

from __future__ import annotations


def inside(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    x, y = pt
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            hit = not hit
    return hit


def count(frame: list, zone: list[tuple[float, float]] | None, scale: float, min_score: float) -> int:
    n = 0
    for _obj, score, box, _polys in frame:
        if score < min_score:
            continue
        cx, cy = (box[0] + box[2]) / 2 / scale, (box[1] + box[3]) / 2 / scale
        if zone is None or inside((cx, cy), zone):
            n += 1
    return n


def series(sam: dict, out_fps: float = 2.0, zone=None, min_score: float = 0.5) -> dict:
    """Downsample to ``out_fps`` taking the max count in each bucket (masks flicker off, rarely on)."""
    fps, scale = sam["fps"], float(sam.get("scale", 1))
    counts = [count(f, zone, scale, min_score) for f in sam["frames"]]
    step = max(1, round(fps / out_fps))
    values = [max(counts[i:i + step]) for i in range(0, len(counts), step)]
    return {"fps": out_fps, "values": values}
