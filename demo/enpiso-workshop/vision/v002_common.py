"""Shared helpers for POC EnPiso ZOE v0.0.2 ([MODULE-2] A -> queue -> B cycle timing)."""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"
VA = VR / "media/vision-analysis"
V2 = VA / "v002"
V2.mkdir(exist_ok=True)
POC = ROOT / "poc-enpiso-zoe-v0.0.2"
PL = json.load(open(VR / "full-playlist.json"))
R = PL["recordings"]
W, H = 1440, 810
CLOCK_OFFSET = 3603.0  # camera = CP + offset (validated/updated in validation.md)
HAND = [9, 10] + list(range(91, 133))


def cam_to_tl(cam_s):
    for r in R:
        h, m, x = map(int, r["cameraStart"][11:19].split(":"))
        a = h * 3600 + m * 60 + x
        if a <= cam_s < a + r["duration"]:
            return r["timelineStart"] + cam_s - a
    return None


def tl_to_cam(t):
    i = max(j for j, r in enumerate(R) if r["timelineStart"] <= t)
    h, m, x = map(int, R[i]["cameraStart"][11:19].split(":"))
    return h * 3600 + m * 60 + x + (t - R[i]["timelineStart"])


def hms(s):
    s = int(round(s)); return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"


MODULE_RAW = {"76": "transaction-search-day30-fenix76-vs-29.raw", "29": "transaction-search-day30-fenix76-vs-29.raw",
              "28": "transaction-search-day30-module28.raw"}


def load_fenix(offset=CLOCK_OFFSET, private=True, module="76"):
    """CP capture headers for one module (default [MODULE-2] 76; 28 = [MODULE]) on 2026-10-30,
    deduped by headerHistoryId. Returns list of dicts WITHOUT employee data."""
    raw = open(ROOT / "enpiso/.secrets" / MODULE_RAW[module]).read().strip()
    s = json.loads(raw); s = json.loads(s) if isinstance(s, str) else s
    hdr = {}
    for x in s[module]["records"]:
        h = x["headerHistoryId"]
        if h in hdr: hdr[h]["members"] += 1; continue
        hh, mm, ss = map(int, x["endTime"][11:19].split(":"))
        cp = hh * 3600 + mm * 60 + ss
        hdr[h] = dict(header=h, cp_end=x["endTime"], cp_s=cp, quantity=float(x["quantity"] or 0),
                      event=x["event"], offstandard=x["offstandardName"] or "", product=x["productName"],
                      operation=x["operationName"], sam=x.get("sam"), members=1)
    out = sorted(hdr.values(), key=lambda d: d["cp_s"])
    for i, d in enumerate(out):
        d["timeline"] = cam_to_tl(d["cp_s"] + offset)
    return out


class Frames:
    """Sequential-friendly frame reader for the browser copies."""
    def __init__(self):
        import av; self.av = av; self.c = None; self.i = None

    def get(self, t):
        i = max(j for j, r in enumerate(R) if r["timelineStart"] <= t)
        av = self.av
        c = av.open(str(VR / "media/full-playlist-v1" / R[i]["file"])); s = c.streams.video[0]
        off = t - R[i]["timelineStart"]; c.seek(int(max(0, off - 2) / s.time_base), stream=s)
        img = None
        for fr in c.decode(s):
            if float(fr.pts * s.time_base) >= off - 0.04:
                img = fr.to_ndarray(format="bgr24"); break
        c.close(); return img


def load_module(module, offset=CLOCK_OFFSET):
    return load_fenix(offset, module=module)


def load_pose(lab):
    z = np.load(VA / f"pose/pose-{lab}.npz")
    return {k: z[k] for k in z}
