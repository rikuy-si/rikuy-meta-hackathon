"""Offline tests: crossing geometry, and reconcile replayed on the recorded demo.

The access export has minute resolution, so the replay checks the audit totals,
not which entry each record pairs with.
"""

import json
from datetime import datetime
from pathlib import Path

from rikuy_gym.crossing import Line, crossings
from rikuy_gym.recordings import Segment
from rikuy_gym.reconcile import reconcile

EXPORT = Path(__file__).resolve().parents[2] / "export" / "audit" / "data" / "audit.js"
LINE = Line((0.33, 0.3), (0.64, 0.3), "left")


def load_export():
    t = EXPORT.read_text()
    return json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))


def test_line_sides():
    # a->b points right; with image y down, "left" of it is above the line (smaller y).
    assert LINE.side((0.5, 0.1)) == 1
    assert LINE.side((0.5, 0.6)) == -1


def test_crossing_entry_and_exit():
    seg = [Segment("20261029T055509.mp4", "2026-10-29T05:55:09", 0.0, 60.0)]
    walk_in = [[t / 5, [["r0t1", [0.45, 0.2, 0.55, 0.6 - 0.1 * t]]]] for t in range(6)]
    walk_out = [[t / 5, [["r0t2", [0.45, 0.0, 0.55, 0.1 + 0.1 * t]]]] for t in range(9)]
    entries, exits = crossings({"20261029T055509.mp4": walk_in + walk_out}, seg, LINE)
    assert [e["track"] for e in entries] == ["r0t1"]
    assert [x["track"] for x in exits] == ["r0t2"]


def test_reconcile_replays_recorded_demo():
    a = load_export()
    records = [datetime.fromisoformat(r["access_ts"]) for r in a["records"]]
    entries = [{"track": e["track"], "cam": e["cam"]} for e in a["entries"]]
    out = reconcile(entries, a["exits"], records, window=(a["window"]["from"], a["window"]["to"]),
                    validated=("2026-10-29T05:44:00", "2026-10-29T06:38:00"),
                    clock_offset_s=a["clock_offset_s"], tailgate_s=a["tailgate_s"])
    s, ref = out["stats"], a["stats"]
    for k in ("records", "confirmed", "phantom", "entries", "recorded", "unrecorded", "exits"):
        assert s[k] == ref[k], k
    assert s["validated"]["unrecorded"] == ref["validated"]["unrecorded"]
    assert (s["phantom_burst"]["from"], s["phantom_burst"]["records"]) == ("05:38", 23)


def test_crossing_replays_recorded_tracks():
    """Recorded on-site tracks through our line logic land near the shipped counts (26 in / 20 out)."""
    o = EXPORT.with_name("overlay.js").read_text()
    tracks = json.loads(o[o.index("=") + 1:].rstrip().rstrip(";"))["local"]
    segs = [Segment(**s) for s in load_export()["video"]["segments"]]
    entries, exits = crossings(tracks, segs, LINE)
    assert 20 <= len(entries) <= 30 and 16 <= len(exits) <= 24
