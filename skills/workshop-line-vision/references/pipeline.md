# Pipeline, stage by stage

Scripts live in `demo/enpiso-workshop/vision/`. They read the private recordings and CP exports
(`enpiso/.secrets/`, `media/`) of the experiment and write `media/vision-analysis/`.

| # | Stage | Script | Output |
|---|---|---|---|
| 0 | CP candidates on the camera clock | `extract.py --stage pilot|all` (env `CP_DEVICE_NAME`) | candidate photos/clips per CP capture |
| 1 | Detect + track | `detect_track.py` | per-recording tracklets |
| 2 | Appearance | `embed_tracks.py` | DINOv2 embeddings, 1 fps |
| 3 | Assign stations | `assign_ab.py`, `contact_sheet.py` | A/B/uncertain per tracklet + review sheet |
| 4 | Pose | `pose3d.py` | RTMW3D keypoints for A/B, 5 fps |
| 5 | Material | `sam3_material.py STEP PROMPTS TAG END`, `material_filter.py`, `material_flow.py` | SAM 3 masks inside zones, piece flow |
| 6 | Candidate evidence | `analyze_events.py`, `peri_event.py`, `storyboards.py`, `qa_device.py`, `qa_excursions.py` | per-candidate evidence, keypad-touch enrichment test |
| 7 | Signals → cycles | `v002_signals.py`, `v002_episodes.py`, `v002_cycles.py`, `v002_sheets.py`, `v002_strip.py`, `v002_validate.py` (shared: `v002_common.py`) | events, cycles, sheets, agreement with manual labels |
| 8 | CP alignment | `v003_cp_alignment.py` | per-capture residuals vs. B's keypad touch |
| 9 | App data | `v003_export.py`, `export_web.py` | `zoe-v003.json`, per-recording overlay JSON |
| 10 | Product 3D (optional) | `v004_clean_product.py`, `v004_hy3d.py`, `v004_texture.py`, `v004_preview*.py`, `v004_export.py` | textured product GLB |
| 11 | 3D scene (optional) | `compose_scene.py` | SAM 3D Objects scene GLB |
| 12 | Figures | `make_figures.py` | position density, process timeline |

The client app is `demo/enpiso-workshop/app/` (`build.py` → `dist/`); its README covers build,
tests and data sources.
