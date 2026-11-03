---
name: package-at-door
description: Check whether a package is at the door. Use when the user asks if a delivery arrived, a package was left, or what is at the entrance now or earlier.
---

# Package at the door

1. Get the bridge id and the door channel. The door channel defaults to 1 when the user does not name one.
2. Follow `skills/rikuy-video/SKILL.md`, live image, for that bridge and channel.
3. When the user also asks about earlier (a delivery window, "this morning", a time range), follow the historical-clip section of that skill for the same camera and that range.
4. Done when the reply contains the live-image URL and, if you fetched history, each clip URL. Describe a package only from a frame you opened.
