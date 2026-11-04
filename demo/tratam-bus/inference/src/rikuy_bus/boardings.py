"""Boarding candidates from the occupancy series, and the fare-counter reconciliation.

A boarding is a rise in people in view that holds for ``hold_s`` seconds. The hold
filters mask flicker (a passenger occluded for a second). Each candidate gets a
window ``[t - pre_s, t + post_s]`` that the agent reviews as a short clip and marks
``boarded`` or ``rejected``; the published audit carries the reviewed windows.
"""

from __future__ import annotations


def candidates(occ: dict, hold_s: float = 2.0, pre_s: float = 3.0, post_s: float = 4.0) -> list[dict]:
    fps, v = occ["fps"], occ["values"]
    hold = max(1, round(hold_s * fps))
    level, run_v, run_n, start = v[0], None, 0, 0
    ups: list[float] = []
    for i, x in enumerate(v):
        if x == run_v:
            run_n += 1
        else:
            run_v, run_n, start = x, 1, i
        if run_n == hold and x != level:
            if x > level:
                ups += [start / fps] * (x - level)
            level = x
    return [{"id": f"B{i + 1}", "t0": max(0.0, t - pre_s), "t1": t + post_s, "t": t, "status": "pending"}
            for i, t in enumerate(ups)]


def reconcile(boardings: list[dict], fare_counter: int) -> dict:
    """Compare reviewed boardings with the fare counter. A gap is a finding to review, not a loss."""
    seen = [b for b in boardings if b.get("status") != "rejected"]
    ts = sorted(b["t0"] for b in seen)
    burst = {"n": 0, "seconds": 0.0}
    for i in range(len(ts)):  # largest run of boardings inside 60 s
        j = i
        while j + 1 < len(ts) and ts[j + 1] - ts[i] <= 60:
            j += 1
        if j - i + 1 > burst["n"]:
            burst = {"n": j - i + 1, "seconds": ts[j] - ts[i]}
    return {"seen": len(seen), "fare_counter": fare_counter, "gap": len(seen) - fare_counter,
            "pending": sum(b.get("status") == "pending" for b in boardings), "burst": burst}
