# Tratam — bus cabin vs. fare counter

Field deployment with Tratam (urban transport). Rikuy took one stop from the bus cabin camera
(CAM 03, Nov 1, 2026, 06:52:17–06:59:39, 7 min 22 s, bus stopped) and compared the boardings
seen on camera with the fare counter the operator reported for the same stop.

Skill: `skills/bus-boarding-count/`.

## Result

| | |
|---|---|
| Boardings on camera | 9 (B1–B9) |
| Fare counter | 7 |
| To reconcile | 2 (crew, a pass or a fare not collected) |
| Boarding rush | 5 boardings in 32 s right before departure; 5 → 9 people in view |
| Masks | SAM 3.1, 15 fps, 8,079 frames, US$1.62 |

Moments for the video: B1–B9; 06:52:21–06:52:39 and 06:58:43–06:59:15.

## Layout

| Path | What |
|---|---|
| `export/` | The recorded web audit (`index.html` → `audit/bus.html`), ES/EN, with masks and the occupancy curve. Ships without footage; pass `?video=<url>` to play a private copy. |
| `inference/` | `rikuy_bus`: occupancy from SAM 3 masks inside the cabin zone, boarding candidates, fare reconciliation, audit build. Reuses `rikuy_gym.segment`. |

## Status

- The export is the audit that was recorded for the demo; its masks come from SAM 3.1.
- `inference/` re-implements the pipeline with local SAM 3. On the shipped occupancy series it
  finds the same 9 boardings (`tests/test_bus.py`), and the reconciliation gives 9 vs. 7, gap 2.
  The SAM 3 stage has not been run end to end from this package.

```bash
cd inference && uv run --with pytest --with-editable . pytest -q -p no:anyio
```
