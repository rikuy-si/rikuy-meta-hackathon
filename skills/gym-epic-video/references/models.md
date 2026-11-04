# Models

| Stage | Model | Code (`demo/animalx-epic/pipeline/`) |
|---|---|---|
| Entrance person detection | YOLOv8s (COCO person), ~5 fps on the turnstile camera | `entrance/gate.py` |
| On-screen DVR clock | Tesseract OCR every 30 s | `entrance/osd.py`, `entrance/gate.py` |
| Floor detection + tracking | **RF-DETR Medium** (COCO person), 5 fps, Roboflow `trackers` ByteTrack | `epic/track.py` |
| Re-identification | **CLIP-ReID ViT-B/16** (MSMT17) + per-camera logistic regression on reviewed labels | `epic/embed.py`, `epic/match.py`, `epic/rank.py` |
| ReID baselines (rejected) | OSNet-AIN, PLIP, DINOv2 | `epic/modelcmp.py` |
| Zero-shot attribute cue | CLIP ViT-L/14 (e.g. "bald head") | `epic/attr.py` |
| Pose, sets and reps | **RTMPose-l** (onnxruntime-gpu) | `epic/pose2d.py`, `epic/pose_events.py` |
| Member mask | **SAM 3** (Meta) video tracker, prompted with the confirmed box at 15 fps | `epic/masks_v003.py` |
| 3D replay of the finale | **SAM 3D Body** (Meta), Kabsch-stabilised torso, pyrender | `epic/s3d_replay2.py` |
| Look and analyze: sheets → labels, exercise names, epic rating, QA frames | **Muse Code** agent on pi.dev, model **Muse Wonder** | `epic/review.py`, `epic/lab.py`, `epic/exercises.py`, `epic/label_check.py` |
| Code generation | **Muse Code** agent on pi.dev, model **Muse Wonder** | the whole pipeline |
| Music | Synthesized 120 BPM track, beat-checked with librosa | `epic/make_music.py` |

Model gate measured on Animal X (zero-shot AP, lower bound):

| Camera / day | CLIP-ReID | OSNet-AIN | PLIP | DINOv2 |
|---|---|---|---|---|
| Member A 30-10 cam01 | **0.662** | 0.413 | 0.132 | 0.043 |
| Member A 29-10 cam01 | 0.614 | 0.722 | **0.779** | 0.019 |
| Member B 29-10 cam04 | **0.457** | 0.380 | 0.202 | 0.027 |

CLIP-ReID was best on 2 of 3 cameras and never bad; with reviewed labels, the per-camera
classifier reached 90–100 % precision on the next candidates. No fine-tuning.
