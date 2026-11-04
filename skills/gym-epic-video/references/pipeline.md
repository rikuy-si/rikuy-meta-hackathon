# Pipeline, stage by stage

Scripts live in `demo/animalx-epic/pipeline/`. They read and write `source/<member>/<day>/`,
`work/` and `edit/` next to the scripts; all three are private and git-ignored.

| # | Stage | Command | Output |
|---|---|---|---|
| 0 | Entrance passages | `entrance/gate.py`, `entrance/analyze.py` | turnstile passages with direction, on the DVR clock |
| 0b | Entrance cards | `entrance/build_app.py` | per access-log entry: candidate crops, full frame, 8 s clip |
| 1 | Track | `epic/track.py CLIENT DAY CAM` | per-track boxes and 1 Hz crops |
| 2 | Embed + score | `epic/match.py`, `epic/embed.py` | CLIP-ReID embeddings, scores vs. the reference |
| 3 | Rank + review | `epic/rank.py CLIENT DAY CAM --sheet OUT.jpg`, then `epic/lab.py CLIENT DAY CAM 1|0|p tid…` | labels; repeat until candidates are ≥ 90 % precise |
| 4 | Library | `epic/build_source.py` | intervals (±3 s), native clips, per-frame boxes, sheets |
| 5 | Timeline | `epic/timeline.py` (zones in `epic/zones/zones.json`) | best camera per second, activity blocks |
| 6 | Index | `epic/build_index.py` | `source/<member>/index.html` |
| 7 | Pose | `epic/pose2d.py` | RTMPose keypoints per clip |
| 8 | Sets + reps | `epic/pose_events.py`, `epic/sets_day.py` | `sets.json` per day (two-camera merge) |
| 9 | Rescue holes | `epic/holes.py`, `epic/holes_report.py`, `epic/peek.py` | reviewed `rescued` tracks for minutes with no match |
| 10 | Exercise labels | `epic/exercises.py`, `epic/repstrip.py`, `epic/repcheck.py` | `exercises.json`; manual vs. pose rep check |
| 11 | Shot selection | `epic/select_v003.py` | `plan.json`: best set per exercise, densest 7 s, finale |
| 12 | Masks | `epic/masks_v003.py` | SAM 3 masks on the selected shots |
| 13 | 3D finale | `epic/s3d_replay2.py CLIENT --mode bench|standing` (env `SAM3D_BODY_REPO`, `SAM3D_BODY_CKPT`) | stabilised 3D replay |
| 14 | Edit | `epic/edit5.py CLIENT --title NAME --gender m|f --erp-doc ID --lang es|en --aspect 16x9|9x16` | MP4 + `edl.json` + `audit.json` + `texts.json` |
| 15 | QA | `epic/qa_video.py`, `epic/label_check.py` | see `qa-gates.md` |
| 16 | Owner page | `page/prepare_assets.py`, `page/build_page.py` (needs private `page/members.json`), `page/lang_check.py` | bilingual page + web and WhatsApp encodes |

Design system: `epic/ds.py` (Rikuy tokens, fonts and draw-time guards).
