# Rikuy Connect

**Let any AI agent see through the cameras a business already has, with the owner's permission and every call audited.**

Built for the **Meta Global AI Developer Hackathon** (Cerebral Valley × Meta, Oct 26 – Nov 4, 2026), Startup track.
Rikuy is a product of [Elevate Endeavors LLC](https://elevateendeavors.ai/) (Florida, USA).

- Demo video (3 min): **VIDEO_URL**
- Repository: https://github.com/rikuy-si/rikuy-meta-hackathon

## What existed before vs. what we built this week

**Built during the hackathon (Oct 26 – Nov 4, 2026):** every line of code in `apps/`, `skills/` and `demo/`. The repository was created on Oct 26, 2026 and has no earlier history.

**Pre-existing, reused as-is:**

| What | Where | Origin |
|---|---|---|
| `writing-for-agents` skill (how we write skills) | `.agents/skills/writing-for-agents/` | Matt Pocock, MIT (license included) |
| `experiment-mode` skill (scratch workspaces) | `.agents/skills/experiment-mode/` | Rikuy's internal knowledge base |
| Rikuy logos and design tokens | `demo/animalx-epic/pipeline/epic/assets/brand/` | rikuy.si design system |
| Onest and JetBrains Mono fonts | `*/fonts/` | SIL Open Font License (included) |
| Open-source models and libraries | see [Models](#models) | their own licenses |

## The problem

Most small businesses already own a DVR or IP cameras, and nobody watches them. The footage could answer real questions (did the shop open on time, did the package arrive, does the turnstile log match the people who came in) but it is locked inside a box on the shop's network, behind vendor protocols, with no safe way to let an agent in.

Rikuy Connect is the safe connection layer:

```
[AI agent + Rikuy skills]          Muse Code agent (Muse Wonder) on pi.dev
        │ MCP
        ▼
[FastMCP gateway]  apps/gateway     per-agent grants · audit log · instant revocation
        │ HTTPS, outbound-only from the customer side
        ▼
[Rust bridge]      apps/rikuy-bridge   runs on the customer network (Linux or Windows)
   ├─ hikvision: Hikvision / HiLook DVR/NVR (ISAPI + RTSP)
   └─ ezviz:     Ezviz / any ONVIF camera (Profile T live, Profile G replay)
        │ presigned PUT
        ▼
[Object storage (Cloudflare R2)]    clips and evidence → shareable link back to the agent
```

- **Bridge** (Rust): discovers cameras, takes live snapshots, searches and downloads recordings, resumes partial downloads, never stores credentials on disk, and uploads straight to object storage through backend-issued presigned URLs. Cross-compiles to Windows.
- **Gateway** (Python, FastMCP): four MCP tools — `list_cameras`, `live_image`, `download_history`, `upload_to_r2`. Every call is checked against a grant (actor × bridge × action, with expiry) and written to the audit log; a revoked grant fails the next call.
- **Skills** (`skills/`): turn an owner's question into evidence by driving those tools.

## Field deployments (real cameras, real owners)

Each one went from an existing camera, through the bridge, to an answer the owner can audit.

| Site | Question | Result | Code |
|---|---|---|---|
| Gym, Caldas (Hikvision DVR) | Does the turnstile log match the people who came in? | 26 entries and 20 exits on camera vs. 39 access records; 16 pair to an entry, 23 records in 6 minutes have nobody at the turnstile, 8 validated entries have no record. Awaiting the owner's review. | `demo/animalx-gym/` |
| Urban bus, cabin camera | Do boardings match the fare counter? | 9 boardings on camera vs. 7 on the fare counter at one stop; 2 to reconcile. | `demo/tratam-bus/` |
| Garment workshop (EZVIZ camera + EnPiso production-control ERP) | Where does the sewing module lose time? | Station B sets the pace at 127 s per piece; 34 of 35 ERP captures match the operator's hand on the keypad (median −1.2 s); 13 of 45 cycles have no capture. | `demo/enpiso-workshop/` |
| Gym, Caldas (4 cameras + ERP) | Which members are worth keeping, and show them why | Two members' training highlight videos from three mornings of CCTV, plus an owner page; rep count within ±1 on 8 of 10 sets. | `demo/animalx-epic/` |
| Mock Ezviz camera | Did the package arrive at the door? | Full agent run: skill → MCP → bridge → camera → object store → link. Reproducible offline. | `demo/run_poc.py` |

Customer footage, member identities and ERP exports are private and are **not** in this repository. Exports are anonymized; see each demo's README.

## Models

Meta models are on the main path: the agent, the masks that make every count reviewable, and the answer the owner reads.

| Step | Model | Meta? | Where |
|---|---|---|---|
| Agent: plans, writes and adapts pipeline code, looks at frames and checks results | **Muse Wonder** (Muse Code on pi.dev) | ✅ Meta | `skills/*/SKILL.md` |
| Answer to the owner, with citations to event ids | **Muse Spark 1.3** (Meta Model API) | ✅ Meta | `demo/animalx-gym/inference/src/rikuy_gym/report.py` |
| Pixel masks that make each counted person reviewable; occupancy; material flow | **SAM 3 / SAM 3.1** | ✅ Meta | `rikuy_gym/segment.py`, `rikuy_bus/occupancy.py`, `enpiso-workshop/vision/sam3_material.py`, `animalx-epic/pipeline/epic/masks_v003.py` |
| 3D body replay; 3D product shape | **SAM 3D Body**, **SAM 3D Objects** | ✅ Meta | `animalx-epic/pipeline/epic/s3d_replay2.py`, `enpiso-workshop/vision/compose_scene.py` |
| Station assignment embeddings | **DINOv2** | ✅ Meta | `enpiso-workshop/vision/embed_tracks.py` |
| Fast person boxes before SAM | RF-DETR (Roboflow, Apache-2.0) + ByteTrack | open source | `rikuy_gym/detect.py`, `animalx-epic/pipeline/epic/track.py`, `entrance/gate.py`, `enpiso-workshop/vision/detect_track.py` |
| On-screen DVR clock reading | Tesseract OCR | open source | `animalx-epic/pipeline/entrance/osd.py`, `gate.py` |
| Re-identifying one member across cameras | CLIP-ReID, CLIP ViT-L/14 | open source | `animalx-epic/pipeline/epic/embed.py`, `attr.py` |
| Pose for sets and reps | RTMPose, RTMW3D | open source | `animalx-epic/pipeline/epic/pose2d.py`, `enpiso-workshop/vision/pose3d.py` |
| Textured product mesh | Hunyuan3D-2 | open source | `enpiso-workshop/vision/v004_hy3d.py` |

The gym audit export that was recorded for the demo (`demo/animalx-gym/export/`) was produced with an earlier YOLOX-s tracker plus SAM 3.1 masks; `inference/` re-implements it on RF-DETR + SAM 3 + Muse Spark and replays the recorded data in tests. Model comparisons that were run and rejected (OSNet-AIN, PLIP) are kept in `animalx-epic/pipeline/epic/modelcmp.py`.

## Quickstart (no keys, no camera, no GPU)

Needs `uv`, a Rust toolchain (`cargo`), and `ffmpeg` + `ffprobe` on `PATH`.

```bash
git clone https://github.com/rikuy-si/rikuy-meta-hackathon && cd rikuy-meta-hackathon

# 1. The full agent path against a mock Ezviz camera: skill → MCP → bridge → camera → object store.
cd apps/gateway && uv sync --extra dev && cd ../..
apps/gateway/.venv/bin/python demo/run_poc.py      # writes demo/artifacts/ (JPEG, MP4, transcript)

# 2. Tests
(cd apps/rikuy-bridge/crates && cargo test)        # bridge: ISAPI, ONVIF, daemon, uploads (mock DVR, camera, R2)
(cd apps/rikuy-bridge/mocks && cargo test)
(cd apps/gateway && uv run --extra dev pytest -q)   # gateway, incl. end-to-end with the real bridge daemons
(cd demo/animalx-gym/inference && uv run --with pytest --with-editable . pytest -q)
(cd demo/tratam-bus/inference && uv run --with pytest --with-editable . pytest -q -p no:anyio)
```

The web audits open offline: `demo/animalx-gym/export/index.html` and `demo/tratam-bus/export/index.html`.

With your own keys (Muse Spark answer, real R2): copy `.env.example` to `.env` and fill it in. The GPU steps (RF-DETR, SAM 3) run on any CUDA GPU or on Modal (`skills/modal-gpu/`); without a GPU, the exports above are the recorded results.

## Skills

| Skill | What it does |
|---|---|
| `rikuy-video` | Live image or historical clip from a camera bridge, returned as a shareable URL. The base for the others. |
| `shop-opened` | Did the shop open on time? Pulls the clip that covers the opening window. |
| `find-moment` | Find when something happened on camera and save that clip. |
| `package-at-door` | Is there a package at the door? |
| `gym-entrance-count` | Count people through a turnstile and reconcile them against the access-control log. |
| `bus-boarding-count` | Count bus boardings and reconcile them against the fare counter. |
| `workshop-line-vision` | Measure a sewing or assembly module from its camera and its production-control captures. |
| `gym-epic-video` | Turn a member's CCTV into a training highlight video plus a retention page for the owner. |
| `modal-gpu` | Run GPU steps on Modal with a price and ETA quoted before launch. |

## Privacy and permissions

- The bridge only connects outbound; nothing on the customer network is exposed.
- Device credentials are held per job in memory and never written to disk or logs.
- Every agent call needs a grant and lands in the audit log; revocation is immediate.
- Identity in the gym videos comes from the access-log minute, reference photo review and clothing continuity, never face recognition.
- Each site owner gave Rikuy access to their own cameras and records; nothing that identifies customers, members or workers is in this repository.

## Known limitations

- The Windows bridge cross-compiles (`x86_64-pc-windows-gnu`) but has not been run on a Windows host yet.
- R2 presigned uploads are verified against an R2 stand-in in tests; a run against a real bucket is pending.
- Gym: `detect.py` (RF-DETR), `segment.py` (SAM 3) and `report.py` have not been re-run end to end from the `inference/` package; the export is the recorded run.
- Gym entrance stage (`animalx-epic/pipeline/entrance/gate.py`) moved from YOLOv8s to RF-DETR after the field run and has not been re-run end to end.
- Field-deployment code expects private recordings and ERP exports, so it is not runnable from this repository alone.

## License

MIT — see `LICENSE`.
