# Reverse-engineering notes: iVMS-4200 client

| | |
|---|---|
| Date | 2026-11-02 |
| Target | Hikvision iVMS-4200 desktop client (a local Wine install) |
| Scope | Read-only static pass, about 10 minutes of a 90-minute timebox |
| Method | `strings -a -n 8` over all 617 `.dll`/`.exe` files (1.4 GB install), filtered for `/ISAPI/` |
| Not used | `morluto/rea` and Ghidra are not installed on this machine. Nothing was executed or decompiled, and no media was opened. |
| Raw output | `tmp/re/isapi-strings.tsv` (4,119 lines, gitignored, regenerable) |

Static strings show which endpoints and formats the vendor client knows. They do
not show which ones it actually calls, in what order, or for which firmware.
Everything below is evidence for or against a hypothesis, not a verified behavior.

## Confirms the bridge's ISAPI reference

| Bridge assumption | Evidence in the client |
|---|---|
| Search is `POST /ISAPI/ContentMgmt/search` | `"POST /ISAPI/ContentMgmt/search"` appears literally in `DAG.dll` and others. The client also probes `GET /ISAPI/ContentMgmt/search/capabilities` and `.../search/profile`. |
| Download is `/ISAPI/ContentMgmt/download` | 21 references across 10 modules, including `PlaybackPlugin.dll`, `PlaybackLogical.dll` and `MainViewPlugin.dll`. |
| Snapshot is `GET /ISAPI/Streaming/channels/<id>/picture` | `/ISAPI/Streaming/channels/%d/picture`, plus the variants `?snapShotImageType=%s` and `?Accept=%s`. |
| Channel id = camera, `0`, stream (`101` = camera 1 main) | Format strings `/ISAPI/Streaming/channels/%d0%d/...` and the literals `/channels/101` and `/channels/102`. |
| Recording track = camera × 100 + 1 | Playback URIs are built as `.../tracks/%d01/?starttime=%s&end...`, with a `%d02` sub-stream variant. |
| Digest auth | A log format string `[uri=/ISAPI/Security/userCheck,WWW-Au...` shows that the client handles the `WWW-Authenticate` challenge. |

## New leads (hypotheses, not implemented)

1. **GET download with a query string.** Several modules contain
   `/ISAPI/ContentMgmt/download?playbackURI=`. On the firmware the bridge
   targets, the GET form returns 400, which is why the bridge uses POST with an
   XML body. Other firmware may accept only the GET form. If a device answers
   POST with 400 or 405, a fallback could try GET once. That has to be tested on
   a second firmware first.
2. **Sub-stream recordings (`tracks/<n>02`).** Some recorders also record the
   sub stream. Then `search` without `--track` returns both, and downloads
   double. A job option such as `stream: main|sub` may be needed. For now the
   bridge relies on the enabled tracks reported by the device.
3. **`/ISAPI/Security/userCheck`** is a cheap way to check a credential. A
   `check` command, or a daemon pre-flight, could validate a newly provisioned
   credential once before any bulk work. It still costs one attempt against the
   lockout counter, so the "never resend a rejected credential" rule still applies.
4. **`/ISAPI/ContentMgmt/download/capabilities` and `/search/capabilities`**
   could tell the bridge, per device, which download form and search limits are
   supported. That would replace guesses with a capability probe.
5. **Ezviz lead.** The client ships `EzvizOpenSDKComm.dll`, which itself
   references `/ISAPI/Security/userCheck`. Ezviz is a Hikvision brand, so some
   Ezviz cameras may expose a LAN ISAPI subset. If they do, the Ezviz connector
   could reuse much of the Hikvision client. Test this on a real Ezviz camera
   before designing `ezviz/src/client.rs`.

## Not found

- `/ISAPI/ContentMgmt/record/tracks` does not appear in the client. The client
  probably learns channels another way, for example through the proprietary SDK
  on port 8000 or `/ISAPI/ContentMgmt/InputProxy/channels` for NVRs with IP
  cameras. The bridge still uses `record/tracks`. **For NVRs**,
  `InputProxy/channels` (9 references) may be the better discovery call.

## Reproduce

```
D=".../drive_c/Program Files (x86)/iVMS-4200 Site/iVMS-4200 Client"
find "$D" -type f \( -iname '*.dll' -o -iname '*.exe' \) -print0 \
  | xargs -0 -P8 -I{} sh -c 'strings -a -n 8 "{}" | grep -E "/ISAPI/[A-Za-z]" | sed "s|^|$(basename "{}")\t|"' \
  > tmp/re/isapi-strings.tsv
```

A deeper pass, for example with Ghidra on `PlaybackLogical.dll` and
`HCOTAPDCM.dll`, would show whether the client calls download with GET or POST
and what body it sends. That was outside this timebox.
