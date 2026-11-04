#!/usr/bin/env bash
# Full 70-min review window: Enfocado RF-DETR -> Deep OC-SORT -> CLIP-ReID stitch.
set -euo pipefail
cd "$(dirname "$0")/.."
export RPP_TAG=full70 RPP_T0=38582 RPP_T1=42831 RPP_TRACKERS=deepocsort
echo "[$(date -Is)] step 1/3 Enfocado RF-DETR"
/opt/arpagon/venvs/tejiendo-vision/bin/python scripts/roi-enhanced.py
echo "[$(date -Is)] step 2/3 Deep OC-SORT"
${EPICENV:-python3} scripts/appearance-trackers.py
echo "[$(date -Is)] step 3/3 CLIP-ReID stitch"
${EPICENV:-python3} scripts/clipreid-stitch.py B-deepocsort 0.82
echo "[$(date -Is)] DONE"
