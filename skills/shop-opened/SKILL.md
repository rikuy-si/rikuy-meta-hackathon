---
name: shop-opened
description: Did a shop, salon, or store open on time? Pulls the camera clip that covers the opening window. Use when the user asks if the place opened on time or whether anyone was there at the scheduled hour.
---

# Shop opened on time

1. Get four facts from the user: bridge id, opening time, the date, and which camera watches the entrance. Ask once for whatever is missing, then stop until they answer.
2. Build the window: 15 minutes before the opening time through 30 minutes after it, as ISO-8601 timestamps with a numeric offset.
3. Follow `skills/rikuy-video/SKILL.md`, historical clip, for that bridge, that camera's track id, and that window.
4. Done when you have handed the user the clip URLs and stated the window in one sentence: from the opening time minus 15 minutes to plus 30 minutes. The clips are the evidence. Describe only frames you actually opened.
