"""Access-control log vs. camera entries -> the audit the viewer renders.

The access log is a per-minute export with no identities (one row per granted
record). The camera clock and the access-control clock drift, so camera times
are shifted by ``clock_offset_s`` before pairing:

    access_time = camera_time - clock_offset_s

Verdicts:
    record  confirmed  -> paired with a camera entry in the same minute (+ tolerance)
    record  phantom    -> granted, but nobody crossed the turnstile
    entry   recorded   -> paired with a record
    entry   unrecorded -> crossed with no record (a tailgate if it follows a
                          recorded entry within ``tailgate_s``)
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

ISO_MS = "milliseconds"


def read_access_log(path: Path) -> list[datetime]:
    """CSV with a ``time`` column (``2026-10-29 05:38`` or ISO). One row per granted record."""
    with path.open(newline="") as f:
        return sorted(datetime.fromisoformat(r["time"].strip().replace(" ", "T")) for r in csv.DictReader(f))


def _hm(t: datetime) -> str:
    return t.strftime("%H:%M")


def reconcile(entries: list[dict], exits: list[dict], records: list[datetime], *, window: tuple[str, str],
              validated: tuple[str, str], clock_offset_s: float = 0.0, tailgate_s: float = 5.0,
              tolerance_s: float = 10.0, lag_s: float = 30.0) -> dict:
    w0, w1 = (datetime.fromisoformat(x) for x in window)
    v0, v1 = (datetime.fromisoformat(x) for x in validated)
    off = timedelta(seconds=clock_offset_s)

    ents = []
    for i, e in enumerate(sorted(entries, key=lambda e: e["cam"]), 1):
        acc = datetime.fromisoformat(e["cam"]) - off
        ents.append({**e, "direction": "in", "acc": acc.isoformat(timespec=ISO_MS), "id": f"E{i:02d}",
                     "_acc": acc, "verdict": "unrecorded", "validated": v0 <= acc < v1, "gap_s": None,
                     "tailgate": False})

    recs = []
    for i, r in enumerate(records, 1):
        recs.append({"id": f"R{i:02d}", "minute": _hm(r), "access_ts": r.isoformat(),
                     "cam_ts": (r + off).isoformat(), "verdict": "phantom", "_t": r})

    # Records only carry the minute, so pairing is order-preserving: walk records
    # in time order and give each the earliest free entry inside its minute,
    # allowing ``tolerance_s`` before and ``lag_s`` after (turnstile queue).
    tol, lag = timedelta(seconds=tolerance_s), timedelta(seconds=lag_s)
    j = 0
    for r in recs:
        lo, hi = r["_t"] - tol, r["_t"] + timedelta(minutes=1) + lag
        while j < len(ents) and ents[j]["_acc"] < lo:
            j += 1
        if j < len(ents) and ents[j]["_acc"] < hi:
            e = ents[j]
            e["verdict"], r["verdict"] = "recorded", "confirmed"
            r["entry"], e["record"] = e["id"], r["id"]
            j += 1

    last_recorded = None
    for e in ents:
        if e["verdict"] == "recorded":
            last_recorded = e["_acc"]
        elif last_recorded and (e["_acc"] - last_recorded).total_seconds() <= tailgate_s:
            e["tailgate"] = True
        if e["verdict"] == "unrecorded" and e["validated"] and recs:
            e["gap_s"] = round(min(abs((e["_acc"] - r["_t"]).total_seconds()) for r in recs) % 60, 1)

    minutes = {}
    t = w0
    while t < w1:
        minutes[_hm(t)] = {"records": 0, "phantom": 0, "entries": 0, "unrecorded": 0, "exits": 0}
        t += timedelta(minutes=1)
    for r in recs:
        if r["minute"] in minutes:
            minutes[r["minute"]]["records"] += 1
            minutes[r["minute"]]["phantom"] += r["verdict"] == "phantom"
    for e in ents:
        m = minutes.get(_hm(e["_acc"]))
        if m:
            m["entries"] += 1
            m["unrecorded"] += e["verdict"] == "unrecorded"
    for x in exits:
        m = minutes.get(_hm(datetime.fromisoformat(x["cam"]) - off))
        if m:
            m["exits"] += 1

    stats = {
        "records": len(recs),
        "confirmed": sum(r["verdict"] == "confirmed" for r in recs),
        "phantom": sum(r["verdict"] == "phantom" for r in recs),
        "phantom_burst": phantom_burst(minutes),
        "entries": len(ents),
        "recorded": sum(e["verdict"] == "recorded" for e in ents),
        "unrecorded": sum(e["verdict"] == "unrecorded" for e in ents),
        "tailgates": sum(e["tailgate"] for e in ents),
        "exits": len(exits),
        "validated": {
            "from": _hm(v0), "to": _hm(v1),
            "entries": sum(e["validated"] for e in ents),
            "recorded": sum(e["validated"] and e["verdict"] == "recorded" for e in ents),
            "unrecorded": sum(e["validated"] and e["verdict"] == "unrecorded" for e in ents),
            "records": sum(v0 <= r["_t"] < v1 for r in recs),
        },
        "median_gap_s": median_gap([e["_acc"] for e in ents if e["validated"]]),
        "peak_5min": peak(minutes, 5),
    }
    for e in ents:
        e.pop("_acc")
    for r in recs:
        r.pop("_t")
    return {"window": {"from": window[0], "to": window[1]}, "clock_offset_s": clock_offset_s,
            "tailgate_s": tailgate_s, "stats": stats, "records": recs, "entries": ents,
            "exits": sorted(exits, key=lambda x: x["cam"]), "minutes": minutes}


def phantom_burst(minutes: dict) -> dict | None:
    """Longest run of minutes with phantom records and zero camera entries."""
    best, run = None, []
    for k, m in list(minutes.items()) + [("", {"phantom": 0, "entries": 0})]:
        if m["phantom"] and not m["entries"]:
            run.append(k)
            continue
        if run and (not best or sum(minutes[x]["phantom"] for x in run) > best["records"]):
            best = {"from": run[0], "to": run[-1], "records": sum(minutes[x]["phantom"] for x in run),
                    "entries_seen": 0}
        run = []
    return best


def median_gap(times: list[datetime]) -> float | None:
    """Median seconds between consecutive entries (how tight the rush is)."""
    gaps = sorted((b - a).total_seconds() for a, b in zip(times, times[1:]))
    if not gaps:
        return None
    mid = len(gaps) // 2
    return round(gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2, 1)


def peak(minutes: dict, span: int) -> dict:
    keys = list(minutes)
    best = max(range(max(1, len(keys) - span + 1)),
               key=lambda i: sum(minutes[k]["entries"] for k in keys[i:i + span]), default=0)
    return {"from": keys[best] if keys else None,
            "entries": sum(minutes[k]["entries"] for k in keys[best:best + span])}
