# EnPiso × Rikuy — garment module vision

Field deployment at a garment workshop that runs EnPiso (production-control ERP). Rikuy read
the module's EZVIZ camera and the EnPiso CP captures (read-only), tracked the two stations of a
sewing module, detected every work cycle, matched CP entries to the video, and built a
bilingual app for the plant owner: findings first, then the full recording with a timeline,
overlays and proof.

Skill: `skills/workshop-line-vision/`.

## Result (EnPiso Visión v0.1.3)

- Published app (unlisted, expires around Dec 3, 2026):
  https://ve.rikuy.si/tmp/arpagon/arpagon-01-med/pi/01a1a754-5bbf-70d3-b414-543e4da1e4f7/index.html
  (`?lang=en` for English).

| Finding | Number | Source · confidence |
|---|---|---|
| Station B sets the module's pace | 127 s per piece at B (19 clean cycles); pieces wait ~36 s in the queue, B waits 3 s | Video · media |
| Module efficiency swung during the day | 59 % average over 9 h; best 13:00 at 73 %; lowest 09:00–10:00 at 32 % | CP · media |
| B sewed 74 of 96 minutes | 77 % sewing; 14 min fetching, 1.5 delivering, 1.3 waiting | Video · media |
| CP vs. video | 34 of 35 CP captures match B's hand on the keypad, median −1.2 s (chance 43 %) | CP + Video · alta |
| To review | 13 of 45 cycles have no CP capture | CP + Video · media |

## Layout

| Path | What |
|---|---|
| `vision/` | Inference and analysis: RF-DETR + ByteTrack, DINOv2 station assignment, RTMW3D pose, SAM 3 material masks, cycles, CP alignment, SAM 3D Objects / Hunyuan3D-2 product 3D, review sheets. Stage list: `skills/workshop-line-vision/references/pipeline.md`. |
| `app/` | The client app source (v0.1.3): `build.py` (stdlib only), vanilla JS in `src/js/`, ES/EN catalogs in `src/i18n/`, node + browser tests, `plan.md` (insight choice and copy deck). |
| `export/` | The built app as shipped, minus the private parts below. Pose files are anonymous keypoints. |

## Removed for the public repo

- Recordings and their URLs (the export plays no video), proof stills and the poster (they show
  workers' faces), and the commercially licensed Grift font.
- Employee names and codes, client, plant, module, product and work-order identifiers, replaced
  by `[MODULE]`, `[PLANT]`, `[PRODUCT]`, `None`. The privacy scan in `build.py` and the tests now
  reads its name list from a private `private/pii.json` (`PII_PATTERNS`).
- The one-off EZVIZ acquisition scripts used during the field run: in the product, `rikuy-bridge`
  (`apps/rikuy-bridge/crates/ezviz`) fetches recordings and the skill asks for them through the
  gateway MCP (`download_history`). Also removed: the ERP browser scripts and every secret.

The code is the code that produced the published app, with the edits above; it expects the
private recordings, CP exports and analysis tree, so it is not runnable from this repo alone.
