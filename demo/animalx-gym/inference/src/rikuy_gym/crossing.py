"""Net crossing of the turnstile line -> entries and exits.

A track is an entry when its anchor point (box center) starts on
the outside of the line and ends on the inside, crossing the line's span.
Exits are the reverse. Counting is anonymous: tracks, never identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Line:
    a: tuple[float, float]
    b: tuple[float, float]
    inside: str = "left"  # side of the directed line a->b that is "inside the gym"

    def side(self, p: tuple[float, float]) -> int:
        (ax, ay), (bx, by) = self.a, self.b
        cross = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
        s = 1 if cross < 0 else -1  # image y grows downward: cross<0 is left of a->b
        return s if self.inside == "left" else -s

    def spans(self, p: tuple[float, float], margin: float = 0.05) -> bool:
        (ax, _), (bx, _) = self.a, self.b
        return min(ax, bx) - margin <= p[0] <= max(ax, bx) + margin


def anchor(box: list[float]) -> tuple[float, float]:
    # Box center: the turnstile camera looks down at an angle, so feet are
    # often occluded by the turnstile itself; the center is the stable point.
    x0, y0, x1, y1 = box
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def crossings(tracks: dict, segs, line: Line, min_frames: int = 3) -> tuple[list[dict], list[dict]]:
    """tracks: {recording: [[t, [[tid, box], ...]], ...]} -> (entries, exits)."""
    start = {s.recording: datetime.fromisoformat(s.cam_start) for s in segs}
    entries, exits = [], []
    for rec, frames in tracks.items():
        path: dict[str, list[tuple[float, tuple[float, float]]]] = {}
        for t, boxes in frames:
            for tid, box in boxes:
                path.setdefault(tid, []).append((t, anchor(box)))
        for tid, pts in path.items():
            if len(pts) < min_frames:
                continue
            sides = [(t, line.side(p)) for t, p in pts if line.spans(p)]
            if len(sides) < 2 or sides[0][1] == sides[-1][1]:
                continue
            # Moment of crossing: first sample on the final side.
            t_cross = next(t for t, s in sides if s == sides[-1][1])
            ev = {"track": tid,
                  "cam": (start[rec] + timedelta(seconds=t_cross)).isoformat(timespec="milliseconds")}
            (entries if sides[-1][1] == 1 else exits).append(ev)
    entries.sort(key=lambda e: e["cam"])
    exits.sort(key=lambda e: e["cam"])
    return entries, exits
