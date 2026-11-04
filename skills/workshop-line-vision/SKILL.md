---
name: workshop-line-vision
description: Measure a sewing or assembly module from its existing camera and its production-control (CP) captures: cycle time per station, the bottleneck, waits and queues, hourly efficiency, and how well CP entries match the video. Use when a plant owner asks where the line loses time, which station sets the pace, whether CP records are trustworthy, or wants a station dashboard over the recording.
---

# Workshop line vision

Every look-and-analyze step (storyboards, strips, cycle sheets, QA crops) is evidence the agent
reads; each finding cites the sheet, frame or file it came from.
Reference implementation: `demo/enpiso-workshop/` (EnPiso × Rikuy, a garment module, Oct 30, 2026).
Reuse it; generate new code only for what a plant needs differently (zones, workflow, CP source).

References: `references/models.md` (models and roles), `references/pipeline.md` (command and
output per stage), `references/evidence-rules.md` (what each signal can and cannot prove; read
before writing any finding).

## Inputs to collect

- Bridge id and the channel that sees the module, and the recording window.
- The CP export for the window (one row per capture: time, quantity, operation, device), read-only.
- The technical sheet: SAM (standard minutes) per operation, operators in the module.
- A reference frame with the stations to study marked (e.g. A left, B right) and the workflow
  in one sentence ("A sews and leaves the piece in the queue; B picks it up, keys CP, sews, deposits").
- The owner's consent to process the footage.

## Procedure

1. **Fetch and align clocks.** Follow `skills/rikuy-video/SKILL.md`, historical clips, for the
   window. Find the camera-to-CP offset (DST, drift) from at least three keypad touches.
   Done when every recording has a start time on the CP clock with a stated uncertainty (±s).
2. **Track the stations.** Detect and track people, embed tracklets, seed station A/B galleries
   from the reference frame, assign tracklets.
   Done when the contact sheet of every assigned and uncertain tracklet has been reviewed and
   unresolved tracklets are split and flagged.
3. **Pose and material.** Whole-body pose for A/B at 5 fps; SAM 3 text-prompted masks for the
   material ("white fabric") at 1 fps inside the zones.
   Done when pose and mask files cover the window and the QA strips around 5 candidates look right.
4. **Cycles.** Per-second role signals → events (fetch, sew, deposit, wait, key CP) → cycles.
   Done when detected cycles agree with ≥ 10 manually labelled cycles, including a held-out
   window not used for tuning, and every cycle has a confidence.
5. **CP alignment.** Match each CP capture to B's keypad touch; report the median residual and
   the chance rate.
   Done when every capture is matched or listed as unmatched, and every cycle without a capture
   is listed for review.
6. **Findings.** Pick the three strongest findings (pace-setting station, efficiency per hour,
   minutes per activity), each with number, source, confidence and proof timestamps, worded per
   `references/evidence-rules.md`.
   Done when every number traces to an export file and every finding has ≥ 1 proof timestamp.
7. **Build the app** from `demo/enpiso-workshop/app/` (`python3 build.py`, then `test/run.sh`).
   Upload the recordings with `upload_to_r2`; publish unlisted.
   Done when the unit and browser tests pass against the published URL in ES and EN.

## Rules

- People appear only as stations ("Puesto A", "Puesto B"). Station ids, names and employee codes
  stay in the private `private/pii.json` the build scans against.
- Compare stations, never people; report efficiency by station and by hour.
- Estimated 3D (pose, objects) is labelled as estimate, apart from the video evidence.
- A mock technical sheet is labelled "Ejemplo" on every element that uses it.
- Footage, CP exports and the technical sheet stay private (R2, git-ignored).

## Done when

The reply has the app link (ES and EN), the three findings with number, source and confidence,
the CP-vs-video agreement, and the list of cycles to review.
