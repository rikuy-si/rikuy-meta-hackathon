---
name: gym-epic-video
description: Make an "epic" training video of one gym member from the gym's existing CCTV, plus a retention page for the owner. Use when a gym owner asks to reward a loyal member, win back an at-risk member, or turn a member's workouts into a shareable highlight video.
---

# Gym epic video

Every look-and-analyze step (contact sheets, crops, labels, QA frames) is evidence the agent
reads; each decision cites the sheet or frame it came from.
Reference implementation: `demo/animalx-epic/pipeline/` (Animal X, Oct 29–31, 2026).
Reuse it; generate new code only for what a gym needs differently (camera map, zones, brand).

References: `references/models.md` (models and roles), `references/pipeline.md`
(command and output per stage), `references/qa-gates.md` (gates for step 7).

Steps marked **GPU** run on Modal per `skills/modal-gpu/SKILL.md`: quote price and ETA for all of
them together and get the user's approval before the first one.

## Inputs to collect

- Bridge id and the camera map: which channel is the entrance, which ones cover the floor.
- The member to feature and why (loyal, at-risk). From the gym's ERP or access log, read-only:
  visit history, plan end date and one reference photo.
- The days to cover (1–3 visits is enough).
- The owner's consent to process this member's footage, and the language(s) for on-screen text.

## Procedure

1. **Pick and justify the member.** From the access history compute visits per month, months
   active in the last 12, the Aug–Oct vs. May–Jul trend and days to plan end.
   Done when the owner's consent is recorded and the reason fits in one sentence (it opens
   the owner page).
2. **Fetch footage.** Follow `skills/rikuy-video/SKILL.md`, historical clips, for every floor
   camera over each visit window (entrance minute −5 min to last sighting +5 min).
   Done when every camera × visit window has clips on disk.
3. **Find the member at the entrance** (GPU). Match the access-log minute to turnstile crossings
   (−40 s / +20 s) and compare the crops with the reference photo.
   Done when one crossing per visit is confirmed against the photo.
4. **Find the member on the floor** (GPU). Detect and track everyone, embed each track, rank tracks
   against the confirmed entrance sighting, and review contact sheets in rounds.
   Done when the next candidates are ≥ 90 % precise and every interval is `confirmed`,
   `mixed`, `auto` or `rescued`.
5. **Understand the training** (GPU). Pose on every library clip, detect sets and reps, merge sets
   seen by two cameras, label each set (exercise, equipment, spotter, epic rating 1–5,
   confidence) from one sheet row per set.
   Done when every set has a label and ≥ 10 sets have a manual rep count.
6. **Select and render** (GPU). Best set per exercise from `confirmed`/`mixed`/`rescued` identity;
   the densest 7 s of reps; slow motion on the peak rep; SAM 3 mask on the member for the rim
   light and virtual camera; a SAM 3D Body replay of the finale; music on a fixed BPM with
   every cut on the beat.
   Done when 16:9 and 9:16 exist in each requested language, each with `edl.json` and `audit.json`.
7. **Run the QA gates** in `references/qa-gates.md`. Fix and re-render.
   Done when every gate passes on every render.
8. **Build the owner page**: why this member matters (ERP facts), the videos, how it was
   measured. Upload videos with `upload_to_r2`; publish the page unlisted.
   Done when `page/lang_check.py` reports 0 issues on the published URL.

## Rules

- Identity comes from the access-log minute, the reference photo reviewed by the agent, and
  clothing continuity across tracks; face recognition stays out of the pipeline.
- Published text uses first names and ERP facts only (visits, months active, plan end).
- Every number shown comes from a file (ERP export, audits, EDL). A dramatized moment
  (e.g. "new record") is flagged in the EDL and states no weight.
- Other members appear in CCTV: blur them, or mark the video as a private draft shared only
  with the featured member.
- Raw footage, the source library and the member list stay private (R2, git-ignored).

## Done when

The reply has the owner page link, each video link (format, language, length), the member
facts used, and the QA gate results.
