---
name: modal-gpu
description: Run GPU or heavy-CPU work on Modal instead of the Muse VM, with a price and ETA quoted before launch. Use when a skill step needs a GPU (RF-DETR, SAM 3, SAM 3D, RTMPose, CLIP-ReID, Hunyuan3D), more than ~4 GB of RAM, or more than ~10 minutes of CPU.
---

# Modal GPU

The Muse VM has 4 vCPU, ~8 GB RAM (mostly in use), no GPU, and 147 GB free in the home volume.
Light steps (reconcile, report, build, ffmpeg trims, JSON) stay on the VM; everything that
`references/budget.md` sends to Modal runs there. Prices and throughputs: `references/budget.md`.
App template: `templates/modal_app.py`. Quote calculator: `scripts/estimate.py`.

## Procedure

1. **Decide where it runs.** Check the step against the VM limits above.
   Done when each step is marked `vm` or `modal`, with the reason.
2. **Quote.** For each `modal` step, pick the GPU from `references/budget.md` and run
   `python3 scripts/estimate.py --model <key> --frames <N> --gpu <GPU>`; it prints ETA and USD
   with a ±50 % band. Show the user the quote table (step, GPU, frames, ETA, USD) and the total.
   Done when the user has approved the quote, or asked for a cheaper GPU or fewer frames.
3. **Calibrate.** Run the step on a 60 s sample (`modal run modal_app.py::run --sample 60`),
   read the measured frames/s from its log, and re-run `estimate.py --fps <measured>`.
   Done when the new quote is shown; ask again when it is > 1.5× the approved one.
4. **Run.** Copy `templates/modal_app.py` next to the pipeline, set `GPU`, `IMAGE` and the
   function body to the pipeline call, put inputs in the `rikuy-work` Volume, then
   `modal run modal_app.py::run`. Let `timeout` be 2× the ETA.
   Done when outputs are back on the VM (`modal volume get rikuy-work <path> work/`) and the
   step's own "Done when" holds.
5. **Report cost.** Read the spend in the Modal dashboard or `modal app logs`, and add actual
   ETA and USD next to the quote.
   Done when the reply shows quoted vs. actual.

## Rules

- Footage goes to Modal only through the private `rikuy-work` Volume or a presigned R2 URL;
  delete it from the Volume when the step is done.
- Credentials come from `modal token` and Modal Secrets (`rikuy-r2`, `hf-token`), never from code.
- Cache model weights in the `rikuy-models` Volume so each run pays the download once.
- Pick the cheapest GPU that fits the model in memory; move up only when the ETA does not fit
  the deadline.

## Done when

Every heavy step ran on Modal, its outputs are on the VM, and the reply shows each step's
quoted and actual ETA and USD.
