import json
from pathlib import Path

from rikuy_bus import boardings, occupancy

SHIPPED = json.loads((Path(__file__).parent / "fixtures/bus_shipped.json").read_text())


def test_candidates_match_shipped_count():
    c = boardings.candidates(SHIPPED["occupancy"])
    assert len(c) == len(SHIPPED["boardings"]) == 9
    # every candidate rise falls inside or next to a reviewed boarding window
    for cand in c:
        assert any(b["t0"] - 3 <= cand["t"] <= b["t1"] + 1 for b in SHIPPED["boardings"])


def test_reconcile_shipped():
    r = boardings.reconcile(SHIPPED["boardings"], SHIPPED["fare_counter"])
    assert (r["seen"], r["fare_counter"], r["gap"]) == (9, 7, 2)
    assert r["burst"]["n"] == 5


def test_occupancy_zone_and_score():
    frame = [[0, 0.9, [100, 100, 200, 200], []], [1, 0.3, [400, 400, 500, 500], []], [2, 0.9, [800, 800, 900, 900], []]]
    zone = [(0.0, 0.0), (0.6, 0.0), (0.6, 0.6), (0.0, 0.6)]
    assert occupancy.count(frame, zone, 1000, 0.5) == 1
    assert occupancy.series({"fps": 4, "scale": 1000, "frames": [frame, [], frame, frame]}, out_fps=2)["values"] == [2, 2]
