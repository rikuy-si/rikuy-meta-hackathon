# Animal X — gym entrance people count

Field deployment at Animal X (gym, Caldas). Rikuy reached the existing
Hikvision DVR through `rikuy-bridge-hikvision`, pulled the 05:30–06:45 recordings of
Oct 29, 2026 for the turnstile camera, counted people crossing the line, and put the
access-control log on the same clock.

**Finding (awaiting the owner's review):** 26 camera entries and 20 exits; 39 access
records, of which 16 pair to an entry. 23 records between 05:38 and 05:44 have nobody at
the turnstile, and 8 entries in the validated window have no record.

## Layout

| Path | What |
|---|---|
| `inference/` | `rikuy_gym`: the pipeline the skill drives (RF-DETR → line crossing → SAM 3 → reconcile → muse-spark-1.3 → web audit). |
| `inference/gym.json` | Site config: window, turnstile line, clock offset, question. |
| `export/` | The web audit shown in the demo video (static, offline). Client name redacted. |
| `../../skills/gym-entrance-count/` | The skill Muse follows, with the viewer template and data contract. |

The review video (`media/peak_0530_0646.mp4`) is private in R2 and not in this repo, so
`export/` opens without footage; the recorded walkthrough shows it with the video.

## Run

```bash
cd demo/animalx-gym/inference
uv run --with pytest --with-editable . pytest -q      # offline, no GPU
```

Full run on site: see `skills/gym-entrance-count/SKILL.md`.

## Status — evidence vs. pending

- `export/` is the exact web audit recorded for the demo. It was produced on Nov 3, 2026
  by a Muse-internal artifact with YOLOX-s tracks and SAM 3.1 masks.
- `inference/` re-implements that pipeline on the stack we chose (RF-DETR, SAM 3,
  muse-spark-1.3). Tests replay the recorded data: `reconcile` reproduces the shipped
  totals exactly (39 records, 16 confirmed, 23 phantom, 26 entries, 10 unrecorded);
  `crossing` on the recorded tracks gives 22 entries / 20 exits vs. 26 / 20 shipped.
- Not yet run: `detect.py` (RF-DETR) and `segment.py` (SAM 3) on the footage, and
  `report.py` against the live muse-spark-1.3 endpoint.
