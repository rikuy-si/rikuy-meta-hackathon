#!/usr/bin/env python3
"""Compare detected cycle events with manual labels (poc-enpiso-zoe-v0.0.2/manual-labels.json)."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from v002_common import *

TOL = 8
M = json.load(open(POC / "manual-labels.json"))
C = json.load(open(VA / "analysis/v002-cycles.json"))["cycles"]
def evaluate(labels, lo, hi):
  res = {}
  for key_m, key_d in (("take", "handoff_start"), ("deposit", "b_deposit"), ("back", "handoff_end"), ("a_supply", "a_place")):
      man = [c[key_m] for c in labels if c[key_m] is not None]
      det = [c[key_d] for c in C if c[key_d] is not None and lo <= c[key_d] <= hi]
      used = set(); err = []
      for m in man:
          cand = [(abs(d - m), i) for i, d in enumerate(det) if i not in used and abs(d - m) <= TOL]
          if cand:
              e, i = min(cand); used.add(i); err.append(det[i] - m)
      tp = len(err)
      res[key_m] = dict(manual=len(man), detected=len(det), matched=tp,
                        recall=round(tp / len(man), 2) if man else None,
                        precision=round(tp / len(det), 2) if det else None,
                        mae_s=round(float(np.mean(np.abs(err))), 1) if err else None,
                        median_signed_err_s=round(float(np.median(err)), 1) if err else None)
  return res


out = dict(tolerance_s=TOL,
           tuning=dict(window=M["tuning_window"], n=len(M["cycles"]), results=evaluate(M["cycles"], *M["tuning_window"])),
           heldout=dict(window=M["heldout_window"], n=len(M["heldout"]), results=evaluate(M["heldout"], *M["heldout_window"])))
json.dump(out, open(VA / "analysis/v002-validation.json", "w"), indent=1)
print(json.dumps(out, indent=1))
