# Budget: where it runs, prices, throughputs

## VM or Modal

| Step | Where | Why |
|---|---|---|
| reconcile, report, build, cycles, CP alignment, page builds | vm | pure Python, seconds |
| ffmpeg trim / concat / remux, contact sheets | vm | CPU, light |
| Tesseract OCR every 30 s | vm | light |
| RF-DETR, ByteTrack | modal | GPU |
| SAM 3 (image or video tracker), SAM 3D Body / Objects | modal | GPU, 8–24 GB VRAM |
| RTMPose / RTMW3D, CLIP-ReID, DINOv2 embeddings | modal | GPU (CPU is 20–50× slower) |
| Hunyuan3D-2 | modal | GPU, ≥ 24 GB VRAM |
| Video render (`edit5.py`, SAM masks composite) | modal (CPU 8 cores) | VM RAM is too small |

## Modal prices (standard, USD, checked 2026-11-04 at modal.com/pricing)

| GPU | VRAM | $/h | Use for |
|---|---|---|---|
| T4 | 16 GB | 0.59 | RTMPose, embeddings |
| L4 | 24 GB | 0.80 | RF-DETR, SAM 3 image, CLIP-ReID — default |
| A10 | 24 GB | 1.10 | same as L4, faster |
| L40S | 48 GB | 1.95 | SAM 3 video tracker, SAM 3D, Hunyuan3D-2 |
| A100 80GB | 80 GB | 2.50 | long SAM 3 video batches |
| H100 | 80 GB | 3.95 | deadline only |

CPU: $0.047 per physical core-hour; memory: $0.008 per GiB-hour. Add ~$0.01 of CPU/RAM per GPU-hour
for the container. Cold start: 1–3 min per run (image pull and weights from `rikuy-models`).

## Planning throughputs (frames/s per GPU)

Starting points for the first quote. Step 3 of the skill replaces them with measured values.

| Key | Model | T4 | L4 | A10 | L40S | A100 | H100 |
|---|---|---|---|---|---|---|---|
| `rfdetr` | RF-DETR Base, 560 px | 12 | 25 | 30 | 50 | 60 | 90 |
| `sam3-image` | SAM 3, text prompt "person" | 1.5 | 3 | 4 | 7 | 8 | 12 |
| `sam3-video` | SAM 3 video tracker | 2 | 4 | 5 | 9 | 10 | 15 |
| `rtmpose` | RTMPose-l / RTMW3D-x per person | 40 | 80 | 90 | 140 | 160 | 220 |
| `reid` | CLIP-ReID / DINOv2 crop embeddings | 300 | 600 | 700 | 1100 | 1300 | 1800 |
| `sam3d-body` | SAM 3D Body per frame | – | 0.5 | 0.6 | 1.2 | 1.4 | 2 |
| `hunyuan3d` | Hunyuan3D-2 shape per object (s/obj) | – | – | – | 90 | 70 | 45 |

Frames to process = seconds of footage × sampling fps (e.g. gym window 75 min at 2 fps SAM 3 = 9,000 frames).

## Reference runs

| Run | Frames | Measured |
|---|---|---|
| Tratam bus, SAM 3.1 hosted (Meta API), 15 fps | 8,079 | US$1.62 |
| Animal X / EnPiso, local RTX 3090 | — | not timed; record future runs here |
