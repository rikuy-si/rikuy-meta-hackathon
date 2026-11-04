# Models

| Stage | Model | Code (`demo/enpiso-workshop/vision/`) |
|---|---|---|
| Person detection + tracking | **RF-DETR** (COCO person), Roboflow `trackers` ByteTrack, streamed over full recordings | `detect_track.py` |
| Station assignment (A/B) | **DINOv2-small** appearance galleries seeded from the reference frame | `embed_tracks.py`, `assign_ab.py` |
| 3D whole-body pose (133 kpts) | **RTMW3D-x** (rtmlib, onnxruntime), 5 fps | `pose3d.py` |
| Overlay skeleton (65 kpts, hands and feet) | **RTMW** | exported by `export_web.py` |
| Material masks | **SAM 3** (Meta), text prompts ("white fabric", "white t-shirt"), 1 fps | `sam3_material.py`, `material_filter.py`, `material_flow.py`, `v004_video_masks.py` |
| Estimated 3D objects | **SAM 3D Objects** (Meta), single frame → GLB, composed in camera frame | `compose_scene.py` |
| Product 3D from the CP image | **Hunyuan3D-2** (shape) + planar texture projection | `v004_hy3d.py`, `v004_texture.py` |
| Look and analyze (storyboards, strips, cycle sheets, labels) | **Muse Code** agent on pi.dev, model **Muse Wonder** | `storyboards.py`, `v002_strip.py`, `v002_sheets.py`, `qa_*.py`, `contact_sheet.py` |
| Code generation (pipeline and app) | **Muse Code** agent on pi.dev, model **Muse Wonder** | everything |

A SAM 3.1 control through the hosted Meta API was run on one clip (0 people on the 17:16 clip,
10 sewing machines on the control frame); the production run used local SAM 3 on an RTX 3090.
