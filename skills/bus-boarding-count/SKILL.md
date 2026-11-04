---
name: bus-boarding-count
description: Count passengers boarding a bus from its cabin camera and reconcile them against the fare counter, then build the web audit. Use when a transport operator asks how many people boarded, whether the fare counter matches, or when and where a bus fills up.
---

# Bus boarding count

Every look-and-analyze step (the cabin frame, each boarding clip) is evidence the agent reads;
each decision cites the clip it came from.
Reference implementation: `demo/tratam-bus/inference/` (package `rikuy_bus`, CLI `rikuy-bus`);
it reuses the SAM 3 stage of `demo/animalx-gym/inference/`. The viewer is `demo/tratam-bus/export/`.

## Inputs to collect

- Bridge id and the cabin channel, confirmed by the user.
- The stop or trip window (date, start, end).
- The fare counter for the same window, as reported by the operator.
- The cabin zone in normalized image coordinates (set in step 1 when the user does not give it).

## Procedure

1. **Place the zone.** Follow `skills/rikuy-video/SKILL.md`, live image, for the cabin channel.
   Draw the zone that covers the aisle and seats and leaves out the windshield and the street.
   Done when the user has confirmed the zone drawn on the frame.
2. **Fetch the recording.** Follow `skills/rikuy-video/SKILL.md`, historical clip, for the window.
   Done when the clip covers the whole window.
3. **Masks and occupancy.** From `demo/tratam-bus/inference/`:

   ```bash
   uv sync --extra segment
   uv run rikuy-bus segment --clip cabin.mp4 --start <CAMERA_START_ISO> --work work/   # SAM 3, 15 fps
   uv run rikuy-bus count   --work work/ --zone x,y x,y x,y x,y
   ```

   Done when `work/occupancy.json` starts at the people in view at the first frame (driver included).
4. **Boarding candidates.** `uv run rikuy-bus boardings --work work/` (a rise held ≥ 2 s).
   Watch each candidate window and set its `status` in `work/boardings.json` to `boarded` or
   `rejected`.
   Done when no candidate is `pending`.
5. **Build.** Upload the clip with `upload_to_r2`, then:

   ```bash
   uv run rikuy-bus build --work work/ --fare-counter <N> --out export/ --video-url <R2_URL>
   ```

   Done when `export/audit/bus.html` opens, the boardings list matches `work/boardings.json`,
   and masks sit on the passengers at each boarding.

## Rules

- Count anonymous people in view. Outputs carry counts and boarding windows only.
- Word the gap between boardings and the fare counter as "to reconcile": crew, a pass or a fare
  not collected are all possible.
- Footage stays private (R2, presigned); the audit and a recorded walkthrough leave the bus.

## Done when

The reply has the boardings on camera, the fare counter, the gap with each boarding id to
review, the busiest minute, and the link to the built audit.
