# Animal X — epic member videos

Field deployment at Animal X (gym, Caldas). Rikuy reached the gym's existing DVR (4 cameras)
through `rikuy-bridge-hikvision`, read the access history from the gym's ERP (read-only), picked
two members worth keeping, a loyal one and one whose plan ends soon, and turned three mornings
of CCTV into a training highlight video for each, plus a page for the owner explaining why.

Skill: `skills/gym-epic-video/`. Everything was built and reviewed by the Muse Code agent on
pi.dev (model: Muse Wonder) following that skill.

## Result

- Owner page (shared privately with the gym owner; not linked here because it names members).
- 8 videos: 2 members × Spanish/English × 16:9 (web) / 9:16 (WhatsApp).
- Member A (loyal): 1,539 visits since 2020, 12 of 12 months active, but September 2026 was
  the lowest month since 2021 (9 visits). Edit: 196 s, 19 training shots, 94.7 % with ≥ 3 reps.
- Member B (at risk): coming back after a drop, plan ends in two weeks. Edit: 82.5 s, 7 training
  shots, 100 % with ≥ 3 reps.

The footage, the source library, the renders and the ERP exports are private customer data
and are not in this repository.

## Layout

| Path | What |
|---|---|
| `pipeline/entrance/` | Turnstile camera: person detection, DVR clock OCR, passage direction, one card per access-log entry with candidate crops. |
| `pipeline/epic/` | Floor cameras: track → ReID rank and review → library → timeline → pose sets/reps → hole rescue → labels → shot selection → SAM 3 masks → SAM 3D Body finale → edit → QA. |
| `pipeline/epic/assets/brand/` | Rikuy design tokens, logos and open fonts. The title font (Grift) is commercially licensed and not included; install it locally to render. |
| `pipeline/page/` | Owner page builder, asset encoder (web + WhatsApp), ES/EN language checker. Needs a private `members.json` (see `members.example.json`). |

Stage-by-stage commands: `skills/gym-epic-video/references/pipeline.md`.
Models: `skills/gym-epic-video/references/models.md`. QA gates: `skills/gym-epic-video/references/qa-gates.md`.

## What was measured

| Check | Target | Result |
|---|---|---|
| Rep count vs. manual count | ±1 on 80 % of ≥ 10 sets | 8/10 |
| Training shots with real sets | ≥ 70 % | 94.7 % and 100 % |
| Cuts on the beat | ≤ 0.03 s | ≤ 0.027 s |
| Flashes / black frames | ≤ 1/s / 0 | pass on all 8 renders |
| Mixed-language text | 0 | 0 on page and all video texts |
| Hole rescue | minutes recovered | Member A 97.0 → 81.2 min unmatched; Member B 23.0 → 12.3 min |

## Status

- Code is the exact code that produced the published result, with private paths, ERP member
  ids and secrets removed (model paths come from `SAM3D_BODY_REPO` / `SAM3D_BODY_CKPT`).
- It expects the private `source/`, `work/` and `edit/` trees; it is not runnable from this
  repo alone.
- Identity is by access-log minute, reference photo review and clothing continuity, never face
  recognition. Bystanders are visible in the v008 renders; they are shared only with each member.
