# QA gates (all must pass before delivery)

| Gate | Target | Tool |
|---|---|---|
| Training shots | ≥ 70 % of shots are real sets with ≥ 3 pose reps | `edl.json` |
| Rep count | pose within ±1 of a manual count on ≥ 80 % of ≥ 10 sets | `epic/repcheck.py` |
| Identity | only `confirmed`, `mixed` or `rescued` intervals in the edit | `epic/select_v003.py` |
| Labels | 5 source-resolution crops per shot confirm the exercise name | `epic/label_check.py` |
| Flashes | ≤ 1 per second (WCAG) | `epic/qa_video.py` |
| Black frames | 0 | `epic/qa_video.py` |
| Frozen runs | only on static cards | `epic/qa_video.py` |
| Audio | peak ≤ −3 dBFS, no unintended silences | `epic/qa_video.py` |
| Cuts on the beat | error ≤ 0.03 s | `epic/qa_video.py` |
| Text | no text outside 90 % title-safe, none below 12 px, no missing glyph | `epic/ds.py` (draw-time) |
| Language | 0 words of the other language on page and video texts | `page/lang_check.py` |
| Privacy | first names only; bystanders blurred or video marked private | manual, every second of one variant |

Animal X results (v008): every gate passed on 8 renders (2 members × es/en × 16:9/9:16);
rep check 8/10; training shots 94.7 % and 100 %; cut error ≤ 0.027 s; audio peak −3.1 dBFS.
