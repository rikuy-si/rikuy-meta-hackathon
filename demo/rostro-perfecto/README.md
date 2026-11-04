# Rostro Perfecto — salon services vs. POS (Rikuy × Titivate)

Field deployment at Rostro Perfecto (beauty salon, Santo Domingo). Rikuy read camera 6 from the
salon's Hikvision NVR and the Titivate POS (read-only) and followed one provider through two
services on Nov 3, 2026, 11:05–11:25.

Skill: `skills/salon-service-audit/`.

## Result

- Published page (unlisted, expires around Dec 4, 2026):
  https://ve.rikuy.si/tmp/arpagon/arpagon-01-med/pi/01a1a8b3-661b-7268-873e-7e3378d30fa7/rostro-perfecto-poc.html

| Service | On camera | POS |
|---|---|---|
| Client 1 (a man), at the provider's station | 11:06:19–11:13:47 (7:28) | **no ticket** before 11:13:02: a flag to check |
| Client 2, on the bed | 11:14:22–11:20:24 (6:02) | turn 2026-4872, invoice 2026-14927, RD$450 cash, paid 11:13:02 |

Invoice 2026-14926 was voided at 11:24:48. POS `created_at` is local time with a `Z` suffix;
`completed_at` is real UTC. Camera times carry about 1 s of uncertainty.

Video: 96.7 s time-lapse (12×) with SAM 3 masks for the provider and both clients, a virtual
camera that follows the masks, and blurred faces for clients and bystanders.

## Layout

| Path | What |
|---|---|
| `pipeline/` | RF-DETR + ByteTrack, Deep OC-SORT + CLIP-ReID stitching, entity grouping with positive/negative galleries, provider stabilisation, SAM 3 masks and drift check, POS reads, time-lapse render, page data. Shared ReID code: `pipeline/vendor/animalx_embed.py`. |
| `export/` | The published page (`rostro-perfecto-poc.html`, `data.json`, `video.json`), ES/EN. |

## Removed for the public repo

- The video, the poster and the three stills (the provider's face is not blurred), and the
  commercially licensed Grift font.
- The provider's name and the client's initials (now "the provider", "[C2]"), the branch name,
  NVR addresses and the tunnel host. POS credentials, branch and provider come from env
  (`RPP_POS_USER`, `RPP_POS_PASS`, `POS_BRANCH`, `POS_PROVIDER`).
- The NVR still/download scripts: in the product, `rikuy-bridge` fetches recordings and skills
  ask for them through the gateway MCP (`download_history`).

The code is the code that produced the published page, with the edits above; it expects the
private recordings, POS exports and `outputs/` tree, so it is not runnable from this repo alone.
