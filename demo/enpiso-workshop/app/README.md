# EnPiso Visión v0.1.3

> **v0.1.3 (2026-11-03): layers on by default.** Zones, stations and skeletons (with fingers) are switched on when the video opens. Each can still be switched off. A link without `capas` opens with all layers on; `capas=ninguna` opens the plain video, and Copy link writes that when everything is off.

> **v0.1.2 (2026-11-03): Spanish and English.** The only change from v0.1.1 is an **ES | EN** switch in the header. Every client string now exists in both languages: the page shell, the panel, the video module (moments, live chips, overlay labels, status text, aria-labels, tooltips) and the copy that `build.py` generates (insights, proof captions, review cards, chart notes, the mock panel). Numbers and dates follow the language (ES `59 %`, `3,8 min`, `vie 30 oct 2026`; EN `59%`, `3.8 min`, `Fri Oct 30 2026`); the plant clock stays 24 h. The choice comes from `?lang=` or `#/…&lang=`, then `localStorage`, then the browser language (`en*` is English), otherwise Spanish; it is kept in deep links and in **Copiar enlace / Copy link**, and switching never reloads the video. Two small layout fixes came with it, because the English text is longer: the header nav on phones and the live chips under the player (on phones the state now sits under the station name instead of after a stray colon). The privacy and copy guards now cover both languages. One data fix: 30 October 2026 is a Friday, so the date label is now "vie" / "Fri" (v0.1.1 said "jueves").
>
> **v0.1.1 (2026-11-03):** the only change from v0.1.0 is the skeleton overlay. It again draws the hands (21 keypoints each, i.e. the fingers) and the feet, as in v0.0.1. The pose binaries now keep all 65 RTMW keypoints, which raises their total from about 3.6 MB to about 13.5 MB; each recording's pose file still loads only when skeletons are switched on.

The first **client-facing** version of the EnPiso × Rikuy camera app, for a garment plant owner or manager who uses EnPiso. It has two modules:

- **Panel** (the landing page): the three best findings first, each with its number, source, confidence and a **Ver en video** button with proof stills. Then a trust band (CP against video), the data the industry expert asked for, a clearly labelled **ejemplo** panel built on the mock technical sheet, and a glossary.
- **Video**: the whole module recording (96 minutes, 13:09 to 14:45 plant time, six `module-full-NN.mp4` files stitched into one timeline). The timeline has lanes for findings, B's cycles, CP captures, and waits or queue. Overlays for zones, stations and skeletons are ON by default (since v0.1.3). Deep links open the app at any time *t*, and **Volver al panel** returns to the card you came from.

UI copy is Spanish (Colombia) and plain US English, switchable at any time (see "Languages" below). Code and docs are English. The insight choice, information architecture and full copy deck are in [`plan.md`](plan.md).

## What it shows

| Card | Number | Source · confidence |
|---|---|---|
| 1 · El Puesto B marca el ritmo del módulo | 127 s per piece at B (19 clean cycles); pieces wait about 36 s in the queue, B waits 3 s | Video · media (queue: baja) |
| 2 · La eficiencia del módulo cambió mucho durante el día | 59 % average over 9 hours; best 13:00 at 73 %, lowest 09:00 and 10:00 at 32 %; 11:00 shows 130 % from catch-up keying (12 pieces in 20 s) | CP · media (assumes 2 operators; the CP SAM of 3.8 min covers sewing only) |
| 3 · El Puesto B cosió 74 de 96 minutos y casi no esperó | 77 % sewing; 14 min fetching, 1.5 min delivering, 1.3 min waiting, 4.7 min out of view | Video · media |
| Trust band | 34 of 35 CP captures match B's hand on the keypad, median −1.2 s (chance: 43 %) | CP + Video · alta |
| Para revisar | 13 of 45 cycles have no CP capture (one clean, at 13:37); the longest clean cycle was 6 min 22 s (14:32) | CP + Video · media |

Data section: efficiency per hour (CP pieces × 3.8 min ÷ 120 operator-minutes, with flags for partial hours, pauses, gaps and the burst), effective against waiting minutes per station, the restriction (Puesto B, the overlock), and a sewing-only comparison **by station, never by person** (B: 32 pieces/h sewing only, 28/h with transfers; A: próximamente).

The **ejemplo** panel (`poc-enpiso-zoe-v0.0.5/ficha-tecnica/`) shows the format of efficiency against SAM per station and per operation: load against takt (A 132 s, B 138 s, takt 128.6 s for 28/h), operations sorted by SAM (OP06 "Cerrar costados y mangas" as the example restriction), per-station efficiency per hour (CP pieces × the mock station SAM), and the 33 s 3D assembly animation. Every element carries an "Ejemplo" label.

## Data sources (read only)

| Data | Path under `EXP/` |
|---|---|
| Cycles, lanes, KPIs, CP rows, zones | `enpiso/video-review/media/vision-analysis/web/v003/zoe-v003.json` |
| Per-capture keypad residuals | `enpiso/video-review/media/vision-analysis/analysis/v003-cp-alignment-rows.json` |
| Pose (compacted to 17 body joints, uint16) | `enpiso/video-review/media/vision-analysis/web/pose-rec01..06.json` |
| Public video URLs (reused, not re-uploaded) | `enpiso/video-review/full-playlist-public.json` |
| Proof stills (cut locally with CPU ffmpeg) | `enpiso/video-review/media/full-playlist-v1/module-full-01..06.mp4` |
| Mock technical sheet and balance | `poc-enpiso-zoe-v0.0.5/ficha-tecnica/{ficha-tecnica,simulation}.json`, `out/ficha-3d-16x9.mp4`, `out/end-card-16x9.jpg` |
| Brand | `poc-enpiso-zoe-v0.1.0/context/` (Rikuy fonts and logos, EnPiso logo and favicon, `design.md`) |

**Privacy:** the build keeps no names, employee codes, identity fields, client name or work order. `build.py` scans every shipped text file for them, and for banned copy words (Spanish and English) and dashes, and fails if any appear; it also checks every ES and EN string on its own. `test/unit.test.cjs` repeats the scan. People appear only as **Puesto A** and **Puesto B**. Faces are not blurred in this private version.

## Build

```bash
cd EXP/poc-enpiso-zoe-v0.1.3
python3 build.py              # full build (cuts 13 stills with ffmpeg, compacts pose), about 5 s
python3 build.py --skip-media # reuse cached stills from .build-cache/
python3 build.py --blur-faces # placeholder: exits with an error (future work, see below)
```

Requirements: Python 3.12+ (stdlib only), `ffmpeg` on PATH, and the local recordings for the stills. The output is `dist/`: a **flat**, self-contained static bundle (35 files, about 16.5 MB, of which 13.5 MB are the on-demand pose files) with relative paths.

| File | Role |
|---|---|
| `index.html` | Page with the CSS, the ES/EN string catalog and the data inlined for a fast first paint (about 120 kB); the HTML text is Spanish until the script applies the chosen language |
| `app.js` | Vanilla JS: `core`, `i18n`, `player`, `timeline`, `overlays`, `dashboard`, `app` (no framework, no CDN, no i18n library) |
| `app-data.json` | The same data as a separate file, for reuse and review; every client string is an `{"es", "en"}` pair |
| `font-*.woff2`, `logo-*`, `favicon-enpiso.png` | Vendored Grift, Onest and JetBrains Mono; Rikuy and EnPiso logos |
| `proof-*.jpg`, `poster.jpg` | Proof stills (480 px crops) and the player poster |
| `pose-manifest.json`, `pose-rec01..06.bin` | Skeleton data, fetched only when **Esqueletos** is turned on |
| `mock-ficha-3d.mp4`, `mock-ficha-poster.jpg` | Ejemplo animation (1.9 MB, `preload="none"`) |
| `robots.txt` | Disallow all (the page also carries `noindex`) |

At runtime the page requests only its own files plus the six public R2 recordings (`ve.rikuy.si/tmp/.../module-full-0N.mp4`).

## Languages

- **Catalog:** `src/i18n/es.json` and `src/i18n/en.json` hold the UI strings (flat `key → string`, `{placeholders}`, keys ending in `_html` carry markup). `build.py` fills the Spanish text into `index.html` (`{{t:key}}`), inlines both catalogs, and writes the generated copy as `{"es", "en"}` pairs. At runtime `I18n` (`src/js/i18n.js`) picks the strings, localizes the data, and updates elements marked `data-i18n` / `data-i18n-attr`; the two CSS "Ejemplo" badges read catalog strings through custom properties.
- **Build checks (`check_copy`):** both catalogs have the same keys and placeholders; every generated string exists in both languages with the **same numbers**; no dashes, banned words or names in either language.
- **Switching:** re-renders the panel text (open "How did we measure this?" panels, the reading position and a playing mock animation are kept) and relabels the video module in place. The `<video>` elements, playback position, clip, layers and filters are untouched.
- **English copy:** plain US English for a plant owner. Brand names stay ("EnPiso Visión", "powered by Rikuy"); SAM, takt and CP stay; "Puesto A/B" is "Station A/B", "cola" is "queue", "operación restricción" is "bottleneck operation", "registro CP" is "CP capture", "Panel" is "Dashboard". The same tone rules apply: stations, never people; no surveillance or punishment words (the build bans e.g. "monitor", "watch", "punish", "spy" in shipped files, so even code names avoid them).

## Run and test locally

```bash
node serve.cjs 8790                                   # serves dist/ on http://127.0.0.1:8790/
# open http://127.0.0.1:8790/?src=local#/panel        (?src=local streams the recordings from disk; localhost only)
test/run.sh                                           # syntax, build, unit checks, browser checks (local recordings)
test/run.sh --r2                                      # same, streaming the public R2 recordings
```

- `test/unit.test.cjs`: helpers (clock, deep links, lanes, windows, ES and EN number and date formatting, language choice, `lang` in links), catalog parity, both languages in every generated string with matching numbers, no Spanish words left in the English copy, the shipped numbers (hourly efficiency, B 127/111/12/3 s, 34 of 35, −1.2 s), insight structure, the mock label, privacy and copy scans, self-containment and pose offsets.
- `test/browser.test.cjs`: Playwright with the cached `chromium_headless_shell-1243` and the experiment's existing `playwright-core` (nothing installed). At 390×844 and 1280×800, **once in Spanish and once in English** (opened from the browser language), it checks: the language, no words of the other language in the visible text, accessible names, CSS badges and overlay labels, the header switch fits without overflow, three cards first, every card links to a moment, fonts load, no names in the DOM, no sideways scroll, first paint, proof stills, the SAM tooltip, **Ver en video** seeks to the insight and plays the clip, the way back is shown, overlays start off and each toggle draws then clears, layers kept in the link, the timeline slider responds to the keyboard, the moment filters, the 10-minute zoom, a deep link at `t=4202`, **Volver al panel** returns to the same card, **no console errors**, and no requests outside the bundle and R2.
  Then a switch suite per viewport: `?lang=en` beats a Spanish browser and is saved; the saved choice applies without a parameter; toggling switches every string (the toggled panel text equals a fresh load in that language, both ways) and updates `<html lang>`, the title, the hash and storage; open panels and the reading position survive; during playback a switch keeps the same `<video>` element, source, time, playback, clip and layers while the back bar, moments, live chips, play button and overlay labels change; **Copiar enlace / Copy link** carries `lang`; a `#/video?…&lang=en` link opens in English over a saved Spanish choice; with nothing saved, `en-GB` opens English and `de-DE` and `es-CO` open Spanish.
- Screenshots: `shots/<view>-<es|en>-<mobile|desktop>.png` for `panel`, `data`, `mock`, `video`, `video-overlays` (the `*-full.png` page captures are regenerated and not committed).

Last run (2026-11-03): 16/16 unit checks and 172/172 browser checks passed, with local video (`test/run.sh`) and with R2 video (`test/run.sh --r2`).

## Publish (not done; for the reviewer)

The bundle is flat, so the existing R2 uploader can publish it to one `tmp/` prefix (30-day lifecycle, the same as v0.0.1 to v0.0.4; the reused recordings expire around 2026-12-01 anyway):

```bash
cd EXP/poc-enpiso-zoe-v0.1.3
python3 build.py && test/run.sh --r2
VE_R2_ACCOUNT_ID=<R2_ACCOUNT_ID> VE_R2_BUCKET=visual-explainer VE_R2_PUBLIC_URL=<VE_PUBLIC_URL> VE_HARNESS=pi \
CLOUDFLARE_API_TOKEN="<token with R2 write>" \
  uv run ~/.agents/skills/visual-explainer/scripts/upload.py dist/*
# then check the published copy:
BASE_URL=<VE_PUBLIC_URL>/tmp/<user>/<host>/pi/<uuid>/index.html node test/browser.test.cjs --r2
```

Any static host works: upload the 35 files of `dist/` side by side, as they are. `.build-cache/dist-manifest.json` lists every file with its size and sha256.

## Known gaps

1. **Faces are visible.** `--blur-faces` is a placeholder that fails on purpose. Blurring needs a per-frame face pass over the six recordings and new video files, plus re-cut stills. Until then, share only with the plant and EnPiso.
2. **Hosting is public but unguessable**, with no login. Workers appear in the video. The recordings live on temporary R2 and **expire around 2026-12-01**; after that the video module shows a load error.
3. **Heavy video on phones.** Each recording is about 330 MB at 1440×810; seeking uses range requests. A low-bitrate proxy (or HLS) would make plant-floor phones much faster.
4. **Efficiency rests on assumptions:** 2 operators for every hour, the CP SAM (3.8 min) covers sewing only, pauses counted as available minutes, and the 11:00 burst left in place (flagged). There is no attendance data.
5. **One afternoon, one camera.** The video covers 96 minutes; CP covers the whole day. Puesto A and the queue have low confidence because A hides her own table from this viewpoint. Station efficiency against SAM and the exact restriction operation are **ejemplo** until the real technical sheet and line balance exist.
6. **Overlays are simple:** zones and stations are fixed polygons (the camera does not move); skeletons hold the nearest 5 fps pose; stations are not tracked boxes.
7. **Browser coverage:** tested in headless Chromium only. Safari and iOS are untested (the videos are H.264, so they should play). There has been no screen-reader audit, only keyboard, labels and contrast checks.
8. **Brand approvals pending:** the EnPiso logo comes from enpiso.co and needs EnPiso's approval for this co-brand. Grift is licensed to Rikuy (Envato); it is embedded the same way rikuy.si serves it.
9. **Footage colour:** footage is shown in natural colour, not the Rikuy navy duotone, because here it is evidence (see `plan.md` §4).
10. **Language gaps:** the mock 3D animation (`mock-ficha-3d.mp4`, from v0.0.5) has Spanish text baked into the video; the EN caption says so. The camera's own on-screen clock and the module name ("[MODULE]") stay as they are. The HTML is Spanish until `app.js` runs, so an English reader on a slow connection may briefly see Spanish. The English copy was written and checked by the agent, not yet by a native-speaking garment manager.

## Future work

- `--blur-faces`: detect faces per frame (the pose head joints already locate heads), blur, re-encode the recordings and stills, and publish the blurred copies.
- Load the real technical sheet (operation list with SAM and the A/B assignment) and attendance, so the per-station efficiency and the restriction operation stop being ejemplo.
- Add a second viewpoint for Puesto A and the queue.
- Use a lower-bitrate video proxy for mobile, and access-controlled hosting.

## Files

```
plan.md                 insight selection, information architecture, copy deck
build.py                data derivation, privacy scan, stills, pose compaction, bundle
serve.cjs               loopback static server with Range support (+ /_local-video/ for tests)
src/index.html          page shell ({{t:key}} tokens, filled with Spanish by the build)
src/i18n/{es,en}.json   UI string catalog
src/styles/kit.css      vendored subset of the Rikuy design system v2.0.0
src/styles/app.css      app layout and components
src/js/*.js             core (UMD, unit-tested), i18n, player, timeline, overlays, dashboard, app
test/                   unit.test.cjs, browser.test.cjs, run.sh
shots/                  390 px and 1280 px screenshots
context/                brand inputs supplied for this version (read only)
```

Nothing in v0.0.1 to v0.1.1 or `enpiso/video-review/` was modified; the reused logic (seek hand-off, Range server, skeleton edges) was copied into new files.
