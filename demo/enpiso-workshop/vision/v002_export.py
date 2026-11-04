#!/usr/bin/env python3
"""Export public v0.0.2 data for the app: media/vision-analysis/web/v002/zoe-v002.json (+ sheets copied as cycle-NN.jpg).
No employee names, codes or IDs; CP headers are reduced to time, quantity, product and event type."""
import sys, shutil
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *

TMAX = 5760
OUT = VA / "web/v002"; OUT.mkdir(parents=True, exist_ok=True)
CY = json.load(open(VA / "analysis/v002-cycles.json"))
C = CY["cycles"]
ST = json.load(open(VA / "analysis/v002-states.json"))
VAL = json.load(open(VA / "analysis/v002-validation.json"))
ALN = json.load(open(VA / "analysis/v002-fenix-alignment.json"))
KPC = json.load(open(VA / "analysis/v002-keypad-clock-check.json"))
z = np.load(V2 / "signals.npz"); S = {k: z[k] for k in z}
qa = np.array(ST["queue_area"]); occ = qa > 0.08


def rle(arr):
    out = []; prev = None; st = 0
    for i, v in enumerate(arr):
        if v != prev:
            if prev is not None: out.append([st, i, prev])
            prev = v; st = i
    out.append([st, len(arr), prev]); return out


# ---- per-second lanes
B = ["absent"] * TMAX
Bpres = ~np.isnan(S["B_cx"])
# fill short detector gaps (<=3 s) so 'absent' means really out of view
pres = Bpres.copy()
for a, b, v in rle(list(Bpres)):
    if not v and b - a <= 3 and a > 0: pres[a:b] = True
for i in range(TMAX):
    if pres[i]: B[i] = "unassigned"
for k, c in enumerate(C):
    hs, he, dep = c["handoff_start"], c["handoff_end"], c["b_deposit"]
    for i in range(hs, min(he + 1, TMAX)):
        if pres[i]: B[i] = "pickup"
    end = dep if dep is not None else (c["next_handoff"] if c["next_handoff"] else min(TMAX, he + 120))
    for i in range(he + 1, min(end, TMAX)):
        if pres[i]: B[i] = "work"
    if dep is not None:
        for i in range(dep, min(dep + 4, TMAX)):
            if pres[i]: B[i] = "deposit"
        nxt = c["next_handoff"] if c["next_handoff"] else min(TMAX, dep + 30)
        for i in range(dep + 4, min(nxt, TMAX)):
            if pres[i]: B[i] = "to_queue" if occ[i] else "wait"
A = []
for i in range(TMAX):
    if np.isnan(S["A_cx"][i]):
        A.append("absent")
    elif S["A_cx"][i] >= 0.44 and S["A_hgt"][i] >= 0.36:
        A.append("up")
    else:
        A.append("seat")
# A absent gaps <=3 s -> previous
for a, b, v in rle(A):
    if v == "absent" and b - a <= 3 and a > 0:
        for i in range(a, b): A[i] = A[a - 1]
lanes = dict(B=rle(B), A=rle(A), queue=rle([bool(x) for x in occ]))

# ---- KPIs (only cycles without flags for the core times; all for counts)
def stat(key, rows):
    v = np.array([r[key] for r in rows if r.get(key) is not None], float)
    if not len(v): return None
    return dict(n=int(len(v)), median=round(float(np.median(v)), 1), p25=round(float(np.percentile(v, 25)), 1),
                p75=round(float(np.percentile(v, 75)), 1), mean=round(float(v.mean()), 1), min=round(float(v.min()), 1), max=round(float(v.max()), 1))

clean = [c for c in C if not c["flags"]]
span0, span1 = C[0]["handoff_start"], (C[-1]["b_deposit"] or C[-1]["handoff_end"])
Bl = np.array(B[span0:span1]); Al = np.array(A[span0:span1])
util = {k: round(float(np.mean(Bl == k)), 3) for k in ("work", "pickup", "deposit", "wait", "to_queue", "unassigned", "absent")}
autil = {k: round(float(np.mean(Al == k)), 3) for k in ("seat", "up", "absent")}
kpis = dict(
    window=[span0, span1], cycles_detected=len(C), cycles_clean=len(clean),
    pieces_per_hour=round(len(C) / (span1 - span0) * 3600, 1),
    b_cycle=stat("b_cycle", clean), b_work=stat("b_work", clean), queue_dwell=stat("queue_dwell", clean),
    b_wait=stat("b_wait", clean), b_at_front=stat("b_at_front", clean), deposit_to_next=stat("deposit_to_next", clean),
    a_interval=stat("a_interval", clean),
    b_time_share=util, a_time_share=autil, queue_occupied_share=round(float(np.mean(occ[span0:span1])), 3),
    fenix_captures_on_video=ALN["n_marks"], fenix_per_hour=round(ALN["n_marks"] / (span1 - span0) * 3600, 1),
)
bw, qd = kpis["b_wait"], kpis["queue_dwell"]
if bw and qd:
    if bw["median"] > qd["median"]:
        verdict = "B waits for pieces more than pieces wait for B: A (supply) paces the line in this sample."
    else:
        verdict = "Pieces wait in the queue longer than B waits: B (overlock + deposit) paces the line in this sample."
    kpis["bottleneck"] = dict(verdict=verdict, basis="median B wait vs median queue dwell over clean cycles",
                              b_wait_median=bw["median"], queue_dwell_median=qd["median"])

# ---- [MODULE-2] marks (public subset)
F = load_fenix()
fenix = []
for d in F:
    fenix.append(dict(cp=d["cp_end"][11:19], timeline=round(d["timeline"], 1) if d["timeline"] is not None else None,
                      quantity=d["quantity"], product=d["product"], operation=d["operation"],
                      event=d["event"], pause=d["offstandard"] or None,
                      abOnVideo=bool(d["timeline"] is not None and d["timeline"] < TMAX)))

# ---- sheets
sheets = json.load(open(V2 / "sheets/sheets.json"))
for s in sheets:
    shutil.copy2(V2 / "sheets" / s["file"], OUT / s["file"])
shutil.copy2(V2 / "sheets/index.jpg", OUT / "cycle-index.jpg")

PUB = ("n", "handoff", "a_place", "handoff_start", "handoff_end", "b_deposit", "next_handoff", "queue_dwell", "b_at_front",
       "b_wait_for_piece", "b_extra_at_front", "b_wait", "b_work", "deposit_to_next", "b_cycle", "a_interval", "flags", "confidence")
cycles = []
for c in C:
    r = {k: c.get(k) for k in PUB}
    r["cpMarks"] = [dict(timeline=m["t"], cp=m["cp_end"][:8]) for m in c["cp_marks"]]
    r["sheet"] = f"cycle-{c['n']:02d}.jpg"
    cycles.append(r)

doc = dict(
    version="0.0.2", title="POC EnPiso ZOE v0.0.2", generated=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
    module=dict(name="[MODULE-2]", plant="[PLANT]", product="[PRODUCT-2]", operation="Confección", source="EnPiso CP read-only transaction search, 2026-10-30"),
    clock=dict(offsetSeconds=3603, uncertaintySeconds=5, note="camera = CP + offset"),
    analysisWindow=[0, TMAX], zones=json.load(open(POC / "zones.json"))["zones"],
    model=[
        "A sews at the front table and leaves the piece in the queue (left part of her table) or walks it to the right end.",
        "B leaves the overlock, picks the piece up at A's table (pickup), returns and works (work).",
        "B turns toward the camera and lowers the finished piece below the frame edge (deposit; basket off-camera, inferred).",
        "Wait = B ready (after deposit) while the queue is empty; to_queue = B walking to an already waiting piece.",
    ],
    caveats=[
        "Estimates from a single fixed camera at 5 fps (pose/boxes) and 1 fps (masks); event times about ±2 s.",
        "The basket is off-camera: deposits are inferred from B turning and the piece leaving the frame.",
        "[MODULE-2] CP captures are NOT one-per-piece in this video: ~29 detected B cycles/h vs ~14 [MODULE-2] captures/h, and no stable time lock at any clock offset.",
        "Product type cannot be confirmed from this camera; the white printed piece is consistent with, not proof of, [PRODUCT-2].",
        "A supply (piece enters the queue) is the weakest event: precision ~0.3 against manual labels.",
        "A and B are anonymous roles within this video; these are process/balance metrics, not individual productivity scores.",
    ],
    kpis=kpis, validation=VAL, fenixAlignment={k: v for k, v in ALN.items()}, keypadClockCheck=KPC,
    lanes=lanes, cycles=cycles, fenix=fenix, sheets=[s["file"] for s in sheets], sheetIndex="cycle-index.jpg",
)
s = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
for bad in ("employee", "Employee", "employeeName", "employeeCode"):
    assert bad not in s, bad
(OUT / "zoe-v002.json").write_text(s)
print(OUT / "zoe-v002.json", len(s) // 1024, "KiB;", len(cycles), "cycles;", len(fenix), "fenix rows")
print(json.dumps(kpis, indent=1))
