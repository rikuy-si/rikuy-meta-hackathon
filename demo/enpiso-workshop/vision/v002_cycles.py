#!/usr/bin/env python3
"""v0.0.2 event detection + cycle assembly (CPU, existing data).

Inputs : pose/pose-{A,B}.npz (5 fps), sam3/sam3white-recNN (1 fps), v002/signals.npz, [MODULE-2] CP headers (private).
Outputs: analysis/v002-events.json, analysis/v002-cycles.json, analysis/v002-states.json (per-second state lanes).

Model (validated visually, see poc-enpiso-zoe-v0.0.2/validation.md):
  queue  = left part of A's front table (white printed pieces waiting for B)
  A_place  : A hand(s) in queue zone with queue white-area rising (or queue becoming occupied)
  A_direct : A stands and walks to B's side (x>=0.44) carrying the piece (bypasses the queue)
  B_take   : B leaves his overlock to the front table (B cx < 0.56) and reaches the queue
  B_turn   : B torso turned toward the camera at/near his station with the finished piece
             (the basket is off-camera; deposit is INFERRED from this rotation)
  B_mark   : [MODULE-2] CP capture endTime + clock offset (refined to B hand on keypad within +-10 s if seen)
"""
import sys, gzip
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *
from material_filter import raster

TMAX = 5760
ZONES = json.load(open(POC / "zones.json"))["zones"]
Q = ZONES["queue"]; KP = ZONES["keypad"]
z = np.load(V2 / "signals.npz"); S = {k: z[k] for k in z}
P = {l: load_pose(l) for l in "AB"}
OFFSET = json.load(open(POC / "zones.json")).get("clock_offset_s", CLOCK_OFFSET)
import os
VER = os.environ.get("ZOE_VERSION", "v002"); CPMOD = os.environ.get("CP_MODULE", "76")


def bbox(poly):
    a = np.array(poly).reshape(-1, 2); return [a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()]


def runs(mask, minlen=2, gap=2):
    out = []; st = None; last = None
    for i, m in enumerate(mask):
        if m:
            if st is None or i - last > gap:
                if st is not None and last - st + 1 >= minlen: out.append([st, last + 1])
                st = i
            last = i
    if st is not None and last - st + 1 >= minlen: out.append([st, last + 1])
    return out


def hand_in(lab, poly, pad=0.01):
    """per-second count of visible hand keypoints inside polygon bbox (5 fps -> max per second)."""
    bx = bbox(poly); zz = P[lab]; k = zz["k2"][:, HAND].astype(float); s = zz["s"][:, HAND].astype(float)
    inz = ((k[..., 0] >= bx[0] - pad) & (k[..., 0] <= bx[2] + pad) & (k[..., 1] >= bx[1] - pad) & (k[..., 1] <= bx[3] + pad) & (s >= .3)).sum(1)
    out = np.zeros(TMAX); sec = np.floor(zz["t"]).astype(int); m = sec < TMAX
    np.maximum.at(out, sec[m], inz[m]); return out


def queue_area():
    qa = np.full(TMAX, np.nan); qpoly = (np.array(Q).reshape(-1, 2) * [360, 203]).astype(np.int32)
    qm = np.zeros((203, 360), np.uint8); import cv2; cv2.fillPoly(qm, [qpoly], 1); qn = qm.sum()
    for r in range(1, 7):
        for l in gzip.open(VA / f"sam3/sam3white-rec{r:02d}.jsonl.gz", "rt"):
            d = json.loads(l); t = int(round(d["t"]))
            if t >= TMAX: continue
            m = raster([c for g in d.get("white fabric", []) if g["s"] >= .4 for c in g["poly"]])
            qa[t] = (m & qm).sum() / qn
    # fill 1 fps gaps, light median smoothing
    idx = np.arange(TMAX); ok = ~np.isnan(qa)
    qa = np.interp(idx, idx[ok], qa[ok])
    from scipy.ndimage import median_filter
    return median_filter(qa, 5)


def main():
    qa = queue_area()
    occ = qa > 0.04
    hA_q = hand_in("A", Q); hB_q = hand_in("B", Q); hB_k = hand_in("B", KP, 0.012)
    Bcx = S["B_cx"]; Acx = S["A_cx"]; Ahg = S["A_hgt"]; Bsh = S["B_sh"]
    Bpresent = ~np.isnan(Bcx); Apresent = ~np.isnan(Acx)
    ev = []
    # B_take: B at the front table episodes
    for a, b in runs(Bcx < 0.56, 2):
        reach = np.where(hB_q[max(0, a - 2):b + 2] > 0)[0]
        t = a - 2 + int(reach[0]) if len(reach) else a
        t = max(t, a - 2)
        qbefore = float(np.max(qa[max(0, a - 8):a + 2])); qafter = float(np.mean(qa[b:b + 6]))
        ev.append(dict(kind="B_take", t=int(t), start=int(a), end=int(b), queue_before=round(qbefore, 3),
                       queue_after=round(qafter, 3), reached_queue=bool(len(reach))))
    # A_direct: A stands away from seat toward B's side
    for a, b in runs((Acx >= 0.44) & (Ahg >= 0.36), 2):
        ev.append(dict(kind="A_direct", t=int(a), start=int(a), end=int(b)))
    # A_place: queue rising edges (occupancy start) with A hands near
    for a, b in runs(occ, 2, gap=4):
        win = hA_q[max(0, a - 15):a + 3]
        hits = np.where(win > 0)[0]
        t = max(0, a - 15) + int(hits[-1]) if len(hits) else a
        ev.append(dict(kind="A_place", t=int(min(t, a)), start=int(a), end=int(b), a_hand=bool(len(hits)),
                       peak_area=round(float(qa[a:b].max()), 3)))
    # B_turn: B torso toward camera while at/near own station
    for a, b in runs(Bsh > 0.0, 2):
        cx = float(np.nanmedian(Bcx[a:b]))
        if cx >= 0.56:
            ev.append(dict(kind="B_turn", t=int(a), start=int(a), end=int(b), cx=round(cx, 3)))
    # B_mark: [MODULE-2] captures
    F = load_fenix(OFFSET, module=CPMOD)
    for d in F:
        T = d["timeline"]
        if T is None or T >= TMAX or d["quantity"] <= 0: continue
        w = np.arange(max(0, int(T) - 10), min(TMAX, int(T) + 11))
        k = w[hB_k[w] > 0]
        ref = int(k[np.argmin(np.abs(k - T))]) if len(k) else None
        ev.append(dict(kind="B_mark", t=round(T, 1), header=d["header"], cp_end=d["cp_end"][11:], product=d["product"],
                       quantity=d["quantity"], keypad_touch=ref))
    ev.sort(key=lambda e: e["t"])
    for i, e in enumerate(ev): e["id"] = i

    # ---- cycles (B-centric, matches observed pattern; see validation.md):
    # handoff_n (B at A's front table, or A walks the piece to B) -> B works at overlock ->
    # B turns toward camera with the piece and lowers it out of frame (deposit, inferred) -> next handoff
    turns0 = [e for e in ev if e["kind"] == "B_turn"]
    fronts = [[e["start"], e["end"], "take"] for e in ev if e["kind"] == "B_take"]
    for e in ev:
        if e["kind"] != "A_direct" or any(f[0] - 6 <= e["start"] <= f[1] + 6 for f in fronts):
            continue
        # A walked to B's side: a hand-off only if B turns to receive within the episode (+15 s)
        rx = [u for u in turns0 if e["start"] - 5 <= u["t"] <= e["end"] + 15]
        if rx:
            u = rx[-1]
            fronts.append([u["t"] + 2, max(e["end"], u["end"]), "direct"])
    fronts.sort()
    H = []
    for f in fronts:
        if H and f[0] - H[-1][1] <= 8:
            H[-1][1] = max(H[-1][1], f[1]); continue
        H.append(list(f))
    places = [e for e in ev if e["kind"] == "A_place" and e["a_hand"]]
    supply = sorted([p["t"] for p in places] + [e["t"] for e in ev if e["kind"] == "A_direct"])
    turns = [e for e in ev if e["kind"] == "B_turn"]
    marks = [e for e in ev if e["kind"] == "B_mark"]
    occ2 = qa > 0.08
    PICK = 10  # nominal pick-up/transfer seconds at the front table
    cycles = []
    for i, (hs, he, kind) in enumerate(H):
        nxt = H[i + 1][0] if i + 1 < len(H) else None
        prev_he = H[i - 1][1] if i > 0 else max(0, hs - 400)
        # deposit: last B_turn at station in [he+15, nxt+2]
        lim = nxt + 2 if nxt is not None else min(TMAX, he + 400)
        tt = [u for u in turns if he + 15 <= u["t"] <= lim]
        if not tt and nxt is not None:
            # deposit usually happens 2-6 s before B leaves for the next piece; accept a turn up to the next hand-off end
            tt = [u for u in turns if he + 15 <= u["t"] <= H[i + 1][1]]
        dep = tt[-1] if tt else None
        # A supply = first queue-occupancy rising edge after the previous pick-up (FIFO); direct hand-off otherwise
        w0 = int(prev_he) + 1
        seg = occ2[w0:int(hs) + 3]
        rise = [w0 + j for j in range(1, len(seg)) if seg[j] and not seg[j - 1]]
        if len(seg) and seg[0] and not rise: rise = [w0]
        ap = rise[0] if rise else (hs if kind == "direct" else None)
        dur = he - hs
        c = dict(n=len(cycles) + 1, handoff=kind, a_place=ap, handoff_start=hs, handoff_end=he,
                 b_deposit=dep["t"] if dep else None, next_handoff=nxt)
        c["queue_dwell"] = max(0, hs - ap) if ap is not None else None
        c["b_at_front"] = dur
        prev_dep = cycles[-1]["b_deposit"] if cycles else None
        c["b_ready"] = prev_dep
        c["b_wait_for_piece"] = max(0, ap - prev_dep) if (ap is not None and prev_dep is not None and ap > prev_dep) else (0 if prev_dep is not None and ap is not None else None)
        c["b_extra_at_front"] = max(0, dur - PICK)
        c["b_wait"] = (c["b_wait_for_piece"] or 0) + c["b_extra_at_front"] if c["b_wait_for_piece"] is not None else None
        c["b_work"] = (dep["t"] - he) if dep else None
        c["deposit_to_next"] = (nxt - dep["t"]) if (dep and nxt is not None) else None
        c["b_cycle"] = (nxt - hs) if nxt is not None else None
        mk = [m for m in marks if hs <= m["t"] < (nxt if nxt is not None else hs + 400)]
        c["cp_marks"] = [dict(header=m["header"], t=m["t"], cp_end=m["cp_end"]) for m in mk]
        if dep and mk: c["mark_minus_deposit"] = round(mk[0]["t"] - dep["t"], 1)
        flags = []
        if ap is None: flags.append("no_A_place_detected")
        if dep is None: flags.append("no_deposit_turn_detected")
        if c["b_cycle"] and c["b_cycle"] > 400: flags.append("long_gap_check_video")
        c["flags"] = flags; c["confidence"] = "medium" if not flags else "low"
        sup_prev = [x for x in supply if x < (ap if ap is not None else hs) - 5]
        c["a_interval"] = ((ap if ap is not None else hs) - sup_prev[-1]) if sup_prev else None
        cycles.append(c)
    states = dict(queue_area=[round(float(x), 3) for x in qa], queue_occupied=[int(x) for x in occ])
    json.dump(ev, open(VA / f"analysis/{VER}-events.json", "w"), indent=1)
    json.dump(dict(model=__doc__, zones=ZONES, clock_offset_s=OFFSET, cycles=cycles, cp_module=CPMOD), open(VA / f"analysis/{VER}-cycles.json", "w"), indent=1)
    json.dump(states, open(VA / f"analysis/{VER}-states.json", "w"))
    from collections import Counter
    print(Counter(e["kind"] for e in ev)); print("cycles", len(cycles))
    for c in cycles:
        print({k: c[k] for k in ("n", "handoff", "a_place", "handoff_start", "handoff_end", "b_deposit", "queue_dwell", "b_wait", "b_work", "deposit_to_next", "b_cycle", "flags")}, [m["t"] for m in c["cp_marks"]])


if __name__ == "__main__":
    main()
