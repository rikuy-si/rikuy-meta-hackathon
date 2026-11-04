# Answer prompt (muse-spark-1.3)

The prompt lives in `demo/animalx-gym/inference/src/rikuy_gym/report.py` (`PROMPT`).
Change it there; this file states the rules it must keep.

- Input is only `stats` plus a short list of event ids. Never send frames, names or member ids.
- One call per language (English, Spanish), max 90 words each.
- Must state: entries and exits, the rush window with its entry count in **bold**,
  access records and how many pair to entries, unrecorded entries in the validated
  window, phantom records.
- Cite 3–4 events as `[E07]`, `[R05]`, `[X07]`; only ids present in the input.
  The viewer turns them into jump links.
- Neutral tone. End with "these findings await the owner's review".

Reference answer from the recorded Animal X run:

> Camera counted 26 entries and 20 exits this morning, with the rush concentrated
> 05:55–06:05 with **19** entries including [E05] and heavy counterflow like [X07].
> The access log shows 39 granted records, of which 16 pair to entries such as [E03].
> The remaining gap to reconcile is 8 unrecorded entries in the validated window,
> for example [E07], plus 23 early records around [R05] with no entries seen.
> These findings await the owner's review.
