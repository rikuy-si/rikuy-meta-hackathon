#!/usr/bin/env python3
"""Per-candidate and whole-window process evidence from A/B tracks, RTMW3D hands and SAM 3 material masks.

Outputs (vision-analysis/analysis/ and web/):
 - events-analysis.json  per CP candidate C01..C40 (window -60 s .. +30 s camera time)
 - excursions.json       A/B away-from-home episodes with destination points (whole window)
 - zone-timeline.json    per 5 s bin: A/B zone, hands-at-device flags, garment area per zone
Everything is measurement of visible image evidence; nothing here confirms a CP press or a finished garment.
"""
import gzip, json, collections, math
from pathlib import Path
import numpy as np
import sys; sys.path.insert(0, str(Path(__file__).parent))
from material_filter import split

ROOT = Path(__file__).resolve().parents[1]
VR = ROOT / "enpiso/video-review"
VA = VR / "media/vision-analysis"
AN = VA / "analysis"; AN.mkdir(exist_ok=True)
pl = json.load(open(VR / "full-playlist.json"))
EV = pl["events"]

# Zones in normalized image coordinates (1440x810 reference frame, fixed camera).
ZONES = {
    "cp_device": [0.555, 0.665, 0.610, 0.750],        # black CP keypad, right end of central table
    "central_table": [0.20, 0.66, 0.60, 1.0],         # A's work table (JACK machine), foreground
    "b_station": [0.60, 0.45, 0.86, 1.0],             # B's overlock station (right foreground)
    "right_racks": [0.75, 0.25, 1.0, 0.60],           # brown garment racks / tables behind B
    "front_left": [0.0, 0.60, 0.20, 1.0],
    "back_left_tables": [0.0, 0.25, 0.42, 0.66],
    "back_center_aisle": [0.42, 0.20, 0.75, 0.66],
}
DEV = ZONES["cp_device"]; DEVC = ((DEV[0] + DEV[2]) / 2, (DEV[1] + DEV[3]) / 2)


def inside(pt, z, pad=0.0):
    return z[0] - pad <= pt[0] <= z[2] + pad and z[1] - pad <= pt[1] <= z[3] + pad


def zone_of(pt):
    for k, z in ZONES.items():
        if k != "cp_device" and inside(pt, z):
            return k
    return "other"

# --- load A/B boxes
box = {"A": {}, "B": {}}
for l in gzip.open(VA / "ab/ab-detections.jsonl.gz", "rt"):
    d = json.loads(l)
    box[d["label"]][round(d["t"], 1)] = d["box"]

# --- load pose hands (wrists 9,10 + hand keypoints 91..132), scores
HAND = [9, 10] + list(range(91, 133))
hands = {"A": {}, "B": {}}
for lab in "AB":
    p = VA / f"pose/pose-{lab}.npz"
    if not p.exists():
        continue
    z = np.load(p)
    k2, s = z["k2"].astype(np.float32), z["s"].astype(np.float32)
    for i, t in enumerate(z["t"]):
        ok = s[i, HAND] >= 0.3
        pts = k2[i, HAND][ok]
        hands[lab][round(float(t), 1)] = pts

# --- material: garment area per zone per sampled second
mat = {}
for p in sorted((VA / "sam3").glob("sam3-rec*.jsonl.gz")):
    try:
        for l in gzip.open(p, "rt"):
            d = json.loads(l)
            za = collections.Counter()
            surf, _onp = split(d)
            for m in surf:
                cx, cy = (m["b"][0] + m["b"][2]) / 2, (m["b"][1] + m["b"][3]) / 2
                za[zone_of((cx, cy)) if not inside((cx, cy), DEV, 0.03) else "cp_device"] += m["a"]
            mat[round(d["t"])] = za
    except EOFError:
        pass


def secs(hms):
    h, m, s = map(int, hms.split(":")); return h * 3600 + m * 60 + s

# --- excursions (whole window)
exc = {}
for lab in "AB":
    ts = sorted(box[lab])
    feet = np.array([[(box[lab][t][0] + box[lab][t][2]) / 2, box[lab][t][3]] for t in ts])
    ctr = np.array([[(box[lab][t][0] + box[lab][t][2]) / 2, (box[lab][t][1] + box[lab][t][3]) / 2] for t in ts])
    home = np.median(ctr, 0)
    away = np.linalg.norm(ctr - home, axis=1) > 0.12
    eps, cur = [], None
    for i, t in enumerate(ts):
        if away[i]:
            if cur and t - cur["t1"] <= 2.0:
                cur["t1"] = t; cur["idx"].append(i)
            else:
                if cur: eps.append(cur)
                cur = {"t0": t, "t1": t, "idx": [i]}
    if cur: eps.append(cur)
    out = []
    for e in eps:
        if e["t1"] - e["t0"] < 3.0:
            continue
        far = max(e["idx"], key=lambda i: np.linalg.norm(ctr[i] - home))
        zs = collections.Counter(zone_of(tuple(ctr[i])) for i in e["idx"])
        out.append({"t0": e["t0"], "t1": e["t1"], "duration_s": round(e["t1"] - e["t0"], 1),
                    "farthest_t": ts[far], "farthest_center": [round(float(v), 3) for v in ctr[far]],
                    "zones_visited": dict(zs.most_common()),
                    "camera_start": None})
    exc[lab] = {"home_center": [round(float(v), 3) for v in home], "episodes": out,
                "tracked_seconds": round(len(ts) / 5, 1)}

R = pl["recordings"]
def cam(t):
    i = max(j for j, r in enumerate(R) if r["timelineStart"] <= t + 1e-6)
    s = secs(R[i]["cameraStart"][11:19]) + (t - R[i]["timelineStart"])
    return f"{int(s // 3600):02d}:{int(s // 60) % 60:02d}:{int(s) % 60:02d}"
for lab in "AB":
    for e in exc[lab]["episodes"]:
        e["camera_start"] = cam(e["t0"]); e["camera_end"] = cam(e["t1"])

# --- per event
events = {}
for e in EV:
    tc = e["timeline"]; lo, hi = tc - 60, tc + 30
    rec = {"id": e["id"], "cpTime": e["cpTime"], "cameraTime": e["cameraTime"], "timeline": tc, "window": [lo, hi]}
    flags = []
    for lab in "AB":
        ts = [t for t in box[lab] if lo <= t <= hi]
        cov = len(ts) / (90 * 5)
        near = []
        for t in ts:
            pts = hands[lab].get(t)
            if pts is None or not len(pts):
                continue
            dmin = float(np.min(np.hypot(pts[:, 0] - DEVC[0], pts[:, 1] - DEVC[1])))
            inside_dev = bool(np.any([inside(p, DEV, 0.012) for p in pts]))
            near.append((t, dmin, inside_dev))
        dev_secs = [t for t, d, ins in near if ins]
        best = min(near, key=lambda x: x[1]) if near else None
        exc_in = [x for x in exc[lab]["episodes"] if x["t1"] >= lo and x["t0"] <= hi]
        rec[lab] = {"trackedPct": round(100 * cov), "handSamplesInDeviceZone": len(dev_secs),
                    "handInDeviceZoneSeconds": round(len(dev_secs) / 5, 1),
                    "firstHandAtDeviceRelS": round(min(dev_secs) - tc, 1) if dev_secs else None,
                    "lastHandAtDeviceRelS": round(max(dev_secs) - tc, 1) if dev_secs else None,
                    "closestHandToDeviceNorm": round(best[1], 3) if best else None,
                    "closestHandRelS": round(best[0] - tc, 1) if best else None,
                    "awayEpisodes": [{"relStart": round(x["t0"] - tc, 1), "relEnd": round(x["t1"] - tc, 1), "zones": x["zones_visited"]} for x in exc_in]}
    # material change around candidate: garment area per zone, 20 s before vs 20 s after
    def zone_area(a, b):
        acc = collections.Counter(); n = 0
        for s_ in range(int(a), int(b) + 1):
            if s_ in mat:
                acc.update(mat[s_]); n += 1
        return {k: round(v / n, 4) for k, v in acc.items()} if n else None
    before, after = zone_area(tc - 25, tc - 5), zone_area(tc + 5, tc + 25)
    rec["garmentAreaBefore"], rec["garmentAreaAfter"] = before, after
    if before and after:
        rec["garmentAreaDelta"] = {k: round(after.get(k, 0) - before.get(k, 0), 4) for k in set(before) | set(after)}
    # flags & summary
    who = [lab for lab in "AB" if rec[lab]["handInDeviceZoneSeconds"] > 0]
    if who:
        flags.append("hand_in_device_zone:" + "+".join(who))
    else:
        flags.append("no_tracked_hand_in_device_zone")
    for lab in "AB":
        if rec[lab]["trackedPct"] < 50:
            flags.append(f"{lab}_low_tracking")
        if rec[lab]["awayEpisodes"]:
            flags.append(f"{lab}_left_home_position")
    rec["flags"] = flags
    parts = []
    for lab in "AB":
        r_ = rec[lab]
        if r_["handInDeviceZoneSeconds"]:
            parts.append(f"{lab}: hand keypoints inside the CP-device zone for {r_['handInDeviceZoneSeconds']} s (first {r_['firstHandAtDeviceRelS']:+.0f} s, last {r_['lastHandAtDeviceRelS']:+.0f} s vs candidate)")
        elif r_["closestHandToDeviceNorm"] is not None:
            parts.append(f"{lab}: closest visible hand {r_['closestHandToDeviceNorm']:.2f} frame-widths from the device at {r_['closestHandRelS']:+.0f} s")
        else:
            parts.append(f"{lab}: hands not visible/tracked in window")
        if r_["awayEpisodes"]:
            z = collections.Counter()
            for x in r_["awayEpisodes"]:
                z.update(x["zones"])
            parts.append(f"{lab} moved away from home position toward {', '.join(k.replace('_', ' ') for k, _ in z.most_common(2))}")
    rec["summary"] = "; ".join(parts) + ". Estimates from video only; not a confirmed press or completed garment."
    events[e["id"]] = rec

# zone timeline (5 s bins) — bin actual sample times (timelineStart has fractional offsets)
binned = {lab: collections.defaultdict(list) for lab in "AB"}
for lab in "AB":
    for t in box[lab]:
        binned[lab][int(t // 5) * 5].append(t)
tl = []
for b in range(0, 7545, 5):
    row = {"t": b}
    for lab in "AB":
        ts = sorted(binned[lab].get(b, []))
        if ts:
            bx = box[lab][ts[len(ts) // 2]]
            row[lab] = zone_of(((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2))
            row[lab + "dev"] = sum(1 for t in ts if t in hands[lab] and len(hands[lab][t]) and any(inside(p, DEV, 0.012) for p in hands[lab][t]))
    g = collections.Counter()
    for s_ in range(b, b + 5):
        g.update(mat.get(s_, {}))
    row["garment"] = {k: round(v / 5, 4) for k, v in g.items()}
    tl.append(row)

RN = AN / "reviewer-notes.json"
if RN.exists():
    notes = json.load(open(RN))
    for k, r_ in events.items():
        if k in notes:
            r_["reviewer"] = {**notes[k], "basis": "Coordinator visual review of storyboard frames at -30/-15/-5/0/+5/+15 s (work-area crop with A/B boxes and hand keypoints). 'possible' = a person's body/hands at the device end with the device occluded; never a confirmed press."}
            r_["summary"] = f"Reviewer: {notes[k]['note']} | Automated: " + r_["summary"]
meta = {"reviewerCounts": dict(collections.Counter(n["deviceInteractionAroundCandidate"] for n in json.load(open(RN)).values())) if RN.exists() else None, "zones": ZONES, "deviceZoneNote": "Fixed zone around the black CP keypad at the right end of the central table; hand-in-zone means 2D hand keypoints project into it (pad 0.012), not confirmed contact.",
        "window": "candidate -60 s .. +30 s (camera clock, offset ±5 s)", "material": "SAM 3 'garment' masks at 1 fps, excluding instances >=60% inside a SAM 3 person mask (worn or held); area = fraction of frame"}
json.dump({"meta": meta, "events": events}, open(AN / "events-analysis.json", "w"), indent=1)
json.dump({"meta": meta, **exc}, open(AN / "excursions.json", "w"), indent=1)
json.dump({"meta": meta, "bins": tl}, open(AN / "zone-timeline.json", "w"), separators=(",", ":"))
web = VA / "web"; web.mkdir(exist_ok=True)
json.dump({"meta": meta, "events": events}, open(web / "events-analysis.json", "w"), separators=(",", ":"))
json.dump({"meta": meta, "bins": tl}, open(web / "zone-timeline.json", "w"), separators=(",", ":"))
json.dump({"meta": meta, **exc}, open(web / "excursions.json", "w"), separators=(",", ":"))
c = collections.Counter(f for r in events.values() for f in r["flags"])
print(json.dumps(c.most_common(), indent=0))
print("A episodes", len(exc["A"]["episodes"]), "B episodes", len(exc["B"]["episodes"]))
