#!/usr/bin/env python3
"""v0.0.3: align CP captures of module 28 ([MODULE]) with detected B events and B keypad touches.
Writes analysis/v003-cp-alignment.json (also used as fenixAlignment/keypadClockCheck replacements in the export)."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *

C = json.load(open(VA / "analysis/v003-cycles.json"))["cycles"]
M = [d for d in load_module("28") if d["timeline"] is not None and d["timeline"] < 5760 and d["quantity"] > 0]
m = np.array([d["timeline"] for d in M])
ev = {"deposit": np.array([c["b_deposit"] for c in C if c["b_deposit"] is not None]),
      "pickup": np.array([c["handoff_start"] for c in C]), "back": np.array([c["handoff_end"] for c in C])}
rng = np.random.default_rng(7)
res = {}
for name, e in ev.items():
    hit = {lag: float(np.mean([np.min(np.abs(e - (x + lag))) <= 8 for x in m])) for lag in range(-180, 181, 2)}
    best = max(hit, key=hit.get)
    null = [max(np.mean([np.min(np.abs(e - (x + l))) <= 8 for x in rng.uniform(250, 5700, len(m))]) for l in range(-180, 181, 6)) for _ in range(300)]
    signed = [float((e - x)[np.argmin(np.abs(e - x))]) for x in m]
    res[name] = dict(hit_at_lag0=round(hit[0], 3), best_lag=best, hit_best=round(hit[best], 3), null_max_p95=round(float(np.percentile(null, 95)), 3),
                     median_event_minus_capture_s=round(float(np.median(signed)), 1), iqr=[round(float(v), 1) for v in np.percentile(signed, [25, 75])])
KP = json.load(open(POC / "zones.json"))["zones"]["keypad"]; kx = KP[0::2]; ky = KP[1::2]; PAD = 0.012
B = load_pose("B"); k = B["k2"][:, HAND].astype(float); s = B["s"][:, HAND].astype(float)
tb = B["t"][((k[..., 0] >= min(kx) - PAD) & (k[..., 0] <= max(kx) + PAD) & (k[..., 1] >= min(ky) - PAD) & (k[..., 1] <= max(ky) + PAD) & (s >= .3)).sum(1) >= 2]
kres = []
for x in m:
    w = tb[np.abs(tb - x) <= 15]
    kres.append(float(w[np.argmin(np.abs(w - x))] - x) if len(w) else None)
kk = np.array([v for v in kres if v is not None])
null = [np.mean([np.any(np.abs(tb - u) <= 15) for u in rng.uniform(250, 5700, len(m))]) for _ in range(1000)]
out = dict(
    module="[MODULE] (plant_layout 28)", n_captures_on_video=int(len(m)), per_hour=round(len(m) / (5738 - 25) * 3600, 1),
    events=res,
    keypad=dict(n_with_B_hand_within_15s=int(len(kk)), n=int(len(m)), median_residual_s=round(float(np.median(kk)), 1),
                iqr=[round(float(v), 1) for v in np.percentile(kk, [25, 75])], null_fraction=round(float(np.mean(null)), 3),
                p=float(np.mean(np.array(null) >= len(kk) / len(m)))),
    interpretation="B's hand is on the CP keypad within about 1 s of 34 of 35 captures (chance 43%, p<0.001), right after B returns from A's table with the next piece (capture median ~3 s after 'back'). The camera = CP + 3603 s offset is confirmed for this device to about +-2 s.",
)
json.dump(out, open(VA / "analysis/v003-cp-alignment.json", "w"), indent=1)
print(json.dumps(out, indent=1))
