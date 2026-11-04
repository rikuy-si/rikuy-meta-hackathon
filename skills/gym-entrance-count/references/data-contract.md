# Viewer data contract

The viewer (`templates/viewer/audit/index.html`) is static. It loads three scripts
from `audit/data/`. `rikuy_gym.build` writes all three.

## `audit.js` → `window.AUDIT`

| Key | Content |
|---|---|
| `site`, `camera`, `date` | Labels. `site` is `[CLIENT]` in anything public. |
| `window` | `{from, to}` ISO, camera clock. |
| `clock_offset_s` | `access_time = camera_time - clock_offset_s`. |
| `tailgate_s` | Max seconds after a recorded entry for an unrecorded one to count as a tailgate. |
| `sources` | `{records, video, measure, masks}` one-line descriptions shown in the method panel. |
| `stats` | `records, confirmed, phantom, phantom_burst{from,to,records,entries_seen}, entries, recorded, unrecorded, tailgates, exits, validated{from,to,entries,recorded,unrecorded,records}, median_gap_s, peak_5min{from,entries}, video_covered_s`. |
| `records[]` | `{id: "R01", minute, access_ts, cam_ts, verdict: confirmed|phantom, entry?}` |
| `entries[]` | `{id: "E01", track, direction: "in", cam, acc, verdict: recorded|unrecorded, validated, gap_s, tailgate, record?}` |
| `exits[]` | `{cam, track}`; the viewer numbers them `X01…`. |
| `minutes` | `{"HH:MM": {records, phantom, entries, unrecorded, exits}}` for every minute of the window. |
| `video` | `{file, total, segments[{recording, cam_start, video_start, duration}]}`. `file` is the private R2 URL. |
| `line` | `{a: [x, y], b: [x, y], inside: "left"|"right"}`, normalized. |
| `muse` | `{question{en,es}, answer{en,es}, model, latency_s, request_id, usage, look}`. |
| `start_at` | ISO time the player opens on. |

## `overlay.js` → `window.OVERLAY`

- `sam[recording] = {start, fps, frames}`; each frame is a list of
  `[obj, score, [x0,y0,x1,y1], [[x,y,x,y,…], …]]`, normalized 0..1.
- `local[recording] = [[t_rel_s, [[track_id, [x0,y0,x1,y1]], …]], …]` — RF-DETR tracks.

## `overlay_hd.js` → `window.OVERLAY_HD`

Same as `sam[recording]` plus `scale: 1000`; coordinates are ints in 0..1000.
Used for the peak recording at 15 fps.
