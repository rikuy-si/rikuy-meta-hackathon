# Models

| Stage | Model | Where it runs | Why |
|---|---|---|---|
| Person detection + tracking, 5 fps | **RF-DETR** (Roboflow, `rfdetr`, COCO `person`) + ByteTrack (`supervision`) | On-premises, next to the bridge | Real-time detector; boxes feed the line-crossing count. Footage does not leave the site. |
| Evidence masks, 2 fps (15 fps on peak minutes) | **SAM 3** (Meta, text prompt `person`) | On-premises GPU or a private worker | Pixel-accurate masks make each counted crossing reviewable by the owner. |
| Answer to the owner's question | **muse-spark-1.3** | API (`MUSE_BASE_URL`, `MUSE_API_KEY`) | Reads only aggregates and event ids, writes the EN/ES answer with `[E..]` citations. |
| Code generation | **Muse Wonder** | Agent side | Writes or adapts the pipeline (`rikuy_gym`) and the viewer for a new site from this skill. |

Code: `demo/animalx-gym/inference/src/rikuy_gym/` — `detect.py` (RF-DETR),
`segment.py` (SAM 3), `report.py` (muse-spark-1.3).

The recorded Animal X walkthrough (Oct 29, 2026) was produced with an earlier
stack (YOLOX-s detector, SAM 3.1 masks); its numbers are kept in
`demo/animalx-gym/export/` as the reference the tests replay.
