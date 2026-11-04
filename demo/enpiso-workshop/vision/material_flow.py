#!/usr/bin/env python3
"""Material-flow evidence for white pieces (SAM 3 'white fabric', 1 fps).

Per second: white-fabric area (fraction of frame) on the central table surface, on B's station surface,
and inside B's / A's person box (carried/held). For every B visit to the central-table side, compare
central-table white area before (-8..-3 s from visit start) vs after (+3..+8 s from visit end) and
whether B's box contained white fabric when arriving / leaving -> classify deposit / pickup / ambiguous.
These are visual estimates; area changes can also come from A rearranging pieces or occlusion."""
import gzip, json, collections, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from material_filter import raster

ROOT = Path(__file__).resolve().parents[1]
VA = ROOT / "enpiso/video-review/media/vision-analysis"
ZT = [0.23, 0.70, 0.56, 1.0]   # central table surface (A side + middle, left of the JACK machine/device)
ZB = [0.70, 0.62, 0.92, 1.0]   # B station surface (overlock table)

def zmask(z):
    m = np.zeros((203, 360), np.uint8); m[int(z[1] * 203):int(z[3] * 203), int(z[0] * 360):int(z[2] * 360)] = 1; return m
MT, MB = zmask(ZT), zmask(ZB)

boxes = {"A": {}, "B": {}}
for l in gzip.open(VA / "ab/ab-detections.jsonl.gz", "rt"):
    d = json.loads(l); boxes[d["label"]][int(round(d["t"]))] = d["box"]

series = {}
for p in sorted((VA / "sam3").glob("sam3white-rec*.jsonl.gz")):
    try:
        for l in gzip.open(p, "rt"):
            d = json.loads(l)
            m = np.zeros((203, 360), np.uint8)
            for g in d.get("white fabric", []):
                if g["s"] >= 0.45:
                    m |= raster(g["poly"])
            t = int(round(d["t"])); row = {"table": float((m & MT).sum()) / m.size, "bstation": float((m & MB).sum()) / m.size}
            for lab in "AB":
                b = boxes[lab].get(t)
                if b:
                    bm = zmask(b); row["in" + lab] = float((m & bm).sum()) / m.size
            series[t] = row
    except EOFError:
        pass

visits = json.load(open(VA / "analysis/b-central-table-visits.json"))["visits"]

def avg(key, a, b):
    v = [series[t][key] for t in range(int(a), int(b) + 1) if t in series and key in series[t]]
    return float(np.mean(v)) if v else None

out = []
for t0, t1 in visits:
    tb, ta = avg("table", t0 - 8, t0 - 3), avg("table", t1 + 3, t1 + 8)
    carry_in, carry_out = avg("inB", t0 - 3, t0 + 1), avg("inB", t1 - 1, t1 + 3)
    if tb is None or ta is None:
        cls = "no_material_data"
    else:
        d = ta - tb; TH = 0.002  # 0.2 % of frame
        cin, cout = (carry_in or 0) > 0.004, (carry_out or 0) > 0.004
        if d > TH and cin and not cout:
            cls = "deposit_likely"
        elif d < -TH and cout and not cin:
            cls = "pickup_likely"
        elif d > TH:
            cls = "table_white_increased"
        elif d < -TH:
            cls = "table_white_decreased"
        elif cin or cout:
            cls = "carrying_no_clear_table_change"
        else:
            cls = "no_visible_white_transfer"
    out.append({"t0": t0, "t1": t1, "tableWhiteBefore": tb, "tableWhiteAfter": ta,
                "BcarryArriving": carry_in, "BcarryLeaving": carry_out, "class": cls})
cnt = collections.Counter(x["class"] for x in out)
res = {"method": __doc__, "zones": {"central_table_surface": ZT, "b_station_surface": ZB}, "visits": out, "counts": dict(cnt),
       "series_seconds": len(series)}
json.dump(res, open(VA / "analysis/material-flow.json", "w"), indent=1)
json.dump({"counts": dict(cnt), "visits": out, "zones": res["zones"]}, open(VA / "web/material-flow.json", "w"), separators=(",", ":"))
# compact per-5s series for the app
ser = {str(t): {k: round(v * 100, 2) for k, v in r.items()} for t, r in series.items() if t % 5 == 0}
json.dump(ser, open(VA / "web/white-series.json", "w"), separators=(",", ":"))
print(dict(cnt), "seconds", len(series))
