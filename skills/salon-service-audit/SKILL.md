---
name: salon-service-audit
description: Match services seen on a salon or spa camera with the POS tickets for the same provider and time: who was served, for how long, and which services have no ticket. Use when an owner asks whether every service was billed, how long a provider's services take, or wants proof of a disputed ticket.
---

# Salon service audit

Every look-and-analyze step (contact sheets, ReID candidates, mask drift checks) is evidence the
agent reads; each decision cites the sheet or frame it came from.
Reference implementation: `demo/rostro-perfecto/pipeline/` (Rostro Perfecto, Nov 3, 2026);
the client page is `demo/rostro-perfecto/export/`. GPU steps run through `skills/modal-gpu/SKILL.md`.

## Inputs to collect

- Bridge id and the channel that sees the station(s).
- The window (date, start, end) and the provider to audit.
- POS read-only access: orders and invoices for the branch and day, with the provider assignment.
- The owner's consent, and whether the provider's name may appear on the page.

## Procedure

1. **Fetch.** Follow `skills/rikuy-video/SKILL.md`, historical clips, for the window, and read the
   POS day (`pos-read.py`, `pos-day.py`; env `RPP_POS_USER`, `RPP_POS_PASS`, `POS_BRANCH`).
   Note which POS fields are local time with a `Z` suffix and which are real UTC.
   Done when the clip covers the window and every POS order of the provider that day is on disk.
2. **Detect and track.** RF-DETR + ByteTrack over the clip (`detect-day.py`), then Deep OC-SORT
   with ReID and CLIP-ReID stitching of short tracks (`appearance-trackers.py`, `clipreid-stitch.py`).
   Done when `tracker-compare.py` shows the stitched tracks cover the window with fewer ID switches.
3. **Find the provider and each client.** Group tracks into entities with positive and negative
   CLIP-ReID galleries and the station ROI (`group-entities-v2.py`, `apply-entity-rules.py`,
   `track-entity.py`, `stabilize-provider.py`). Seat alone never decides the role: the client
   lies in the station ROI too.
   Done when the provider and each client have a reviewed track with start and end times.
4. **Masks.** SAM 3 video masks for the provider and each client, prompted from those tracks
   (`sam-provider.py`, `sam-demo.py`); check drift with `sam-drift-check.py`.
   Done when the drift check passes on every entity.
5. **Reconcile with the POS.** For each service on camera, find the provider's ticket that
   covers it (creation or payment inside the service ± 5 min).
   Done when every service is `billed` (with turn, invoice, amount, payment time) or
   `no ticket` (a flag to check).
6. **Build the page.** `render-demo-video.py` (time-lapse with masks, virtual camera, face blur
   for clients and bystanders, no burned-in text), then `build-demo-data.py` (env `POS_PROVIDER`).
   Upload the video with `upload_to_r2`; publish unlisted.
   Done when chips on the page show their source (POS / camera / camera vs. POS) in sync with the
   video, in ES and EN.

## Rules

- Identity comes from the POS assignment and the reviewed tracks; face recognition stays out.
- Clients appear by initials only; blur client and bystander faces in every rendered frame.
- A service with no ticket is "a flag to check": it may sit under another ticket or be a courtesy.
- Footage and POS exports stay private (R2, git-ignored).

## Done when

The reply has the page link, each service (who, start, end, duration) with its ticket or flag,
and the POS-vs-camera timing caveats.
