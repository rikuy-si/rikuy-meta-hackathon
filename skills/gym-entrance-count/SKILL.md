---
name: gym-entrance-count
description: Count people through a gym (or any turnstile) entrance from the existing camera and reconcile them against the access-control log, then build the web audit. Use when the owner asks how many people came in, whether the access log matches reality, about tailgating, phantom check-ins, or the morning rush.
---

# Gym entrance count

The pipeline runs on-premises next to the bridge; muse-spark-1.3 writes the owner's answer.
Reference implementation: `demo/animalx-gym/inference/` (package `rikuy_gym`, CLI `rikuy-gym`).
Reuse it; generate new code only for what a site needs differently.

References: `references/models.md` (models and roles), `references/data-contract.md`
(what the viewer reads), `references/report-prompt.md` (answer and citation rules).

Steps marked **GPU** run on Modal per `skills/modal-gpu/SKILL.md`: quote price and ETA for all of
them together and get the user's approval before the first one.

## Inputs to collect

- Bridge id and the entrance channel, confirmed by the user.
- The date and time window (e.g. 05:30–06:45).
- The access-control export for that window: CSV with one `time` row per granted record.
- The turnstile line in normalized image coordinates and which side is inside (set in step 1
  when the user does not give it).

## Procedure

1. **Place the line.** Follow `skills/rikuy-video/SKILL.md`, live image, for the entrance
   channel. Open the frame, draw the line, and write it into a site config like
   `demo/animalx-gym/inference/gym.json`.
   Done when the user has confirmed the line drawn on the frame.
2. **Fetch the recordings.** Follow the historical-clip section of `skills/rikuy-video/SKILL.md`
   for the window. Name each file `YYYYMMDDTHHMMSS.mp4` (camera start time) in one `clips/` dir.
   Done when `rikuy-gym timeline --clips clips/ --work work/ --concat` lists every recording
   and writes `work/review.mp4`.
3. **Count and reconcile** (GPU for `detect`). From `demo/animalx-gym/inference/`:

   ```bash
   uv sync --extra detect --extra segment
   uv run rikuy-gym detect    --clips clips/ --work work/             # RF-DETR, 5 fps
   uv run rikuy-gym reconcile --work work/ --access access.csv --config gym.json
   ```

   Done when `work/audit.json` exists and `reconcile` prints entries, exits, records,
   confirmed, phantom and unrecorded.
4. **Masks** (GPU). SAM 3 at 2 fps over the window, then 15 fps on the recording that covers
   `stats.peak_5min.from` in `work/audit.json`:

   ```bash
   uv run rikuy-gym segment --clips clips/ --work work/
   uv run rikuy-gym segment --clips clips/ --work work/ --hd <RECORDING_AT_PEAK>
   ```

   Done when `work/sam.json` and `work/sam_hd.json` exist.
5. **Answer.** `uv run rikuy-gym report --work work/ --config gym.json` (muse-spark-1.3).
   Done when `audit.json` has `muse.answer.en` and `muse.answer.es`.
6. **Build.** Upload `work/review.mp4` with `upload_to_r2`, then:

   ```bash
   uv run rikuy-gym build --work work/ --config gym.json --out export/ --video-url <R2_URL>
   ```

   Done when `export/index.html` opens, the header counts match `work/audit.json`, masks sit
   on people at the peak minutes, and every `[E..]`/`[R..]` id in the answer exists in the audit.

## Rules

- Count anonymous line crossings. Outputs carry track ids and counts only.
- Raw footage and `review.mp4` stay private (R2, presigned). Only the audit, overlays and a
  recorded walkthrough leave the site.
- Word every mismatch as a finding "awaiting the owner's review".

## Done when

The reply has the muse-spark-1.3 answer, the totals (entries, exits, records, confirmed,
phantom, unrecorded) and the path or link to the built web audit.
