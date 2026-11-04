---
name: gym-entrance-count
description: Count people through a gym (or any turnstile) entrance from the existing camera and reconcile them against the access-control log, then build the web audit. Use when the owner asks how many people came in, whether the access log matches reality, about tailgating, phantom check-ins, or the morning rush.
---

# Gym entrance count

Muse runs this skill end to end. Muse Wonder writes or adapts the pipeline code;
the pipeline runs on-premises next to the bridge; muse-spark-1.3 writes the answer.
Models and roles: `references/models.md`.

Reference implementation: `demo/animalx-gym/inference/` (package `rikuy_gym`,
CLI `rikuy-gym`). Reuse it; generate new code only for what a site needs differently.

## Inputs to collect

- Bridge id and the entrance channel (ask; do not assume).
- The time window (e.g. 05:30–06:45) and the date.
- The access-control export for that window: CSV with one `time` row per granted record.
- The turnstile line in normalized image coordinates and which side is inside.
  If unknown, take a live image (step 1), draw the line on it, and confirm with the user.

## Procedure

1. Follow `skills/rikuy-video/SKILL.md`, live image, for the entrance channel. Open the
   frame and write the line into a site config like `demo/animalx-gym/inference/gym.json`.
2. Follow the historical-clip section of `skills/rikuy-video/SKILL.md` for the window.
   Keep every recording; name files `YYYYMMDDTHHMMSS.mp4` (camera start time) in one `clips/` dir.
3. Run the pipeline from `demo/animalx-gym/inference/`:

   ```bash
   uv sync --extra detect --extra segment
   uv run rikuy-gym timeline  --clips clips/ --work work/ --concat
   uv run rikuy-gym detect    --clips clips/ --work work/             # RF-DETR, 5 fps
   uv run rikuy-gym segment   --clips clips/ --work work/             # SAM 3, 2 fps
   uv run rikuy-gym segment   --clips clips/ --work work/ --hd <PEAK_RECORDING>
   uv run rikuy-gym reconcile --work work/ --access access.csv --config gym.json
   uv run rikuy-gym report    --work work/ --config gym.json          # muse-spark-1.3
   ```

4. Upload `work/review.mp4` with `upload_to_r2` and keep the URL private.
5. Build the web audit from `templates/viewer/`:

   ```bash
   uv run rikuy-gym build --work work/ --config gym.json --out export/ --video-url <R2_URL>
   ```

6. Check before replying: open `export/index.html`; the camera, access-log and
   finding counts in the header match `work/audit.json`; masks draw on people at the
   peak minutes; every `[E..]`/`[R..]` id in the answer exists in the audit.

## Rules

- Count crossings, never identify people. No faces, names or member ids in any output.
- Raw footage and `review.mp4` stay private (R2, presigned). Only the audit, overlays and a
  recorded walkthrough leave the site.
- Report findings as "awaiting the owner's review", never as fraud or theft.
- Data contract the viewer expects: `references/data-contract.md`.
- Prompt and citation rules for the answer: `references/report-prompt.md`.

## Done when

The reply has the muse-spark-1.3 answer, the totals (entries, exits, records, confirmed,
phantom, unrecorded) and the path or link to the built web audit.
