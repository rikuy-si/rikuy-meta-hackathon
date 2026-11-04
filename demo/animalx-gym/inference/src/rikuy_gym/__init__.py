"""Gym entrance people count for Rikuy.

Pipeline (one module per stage, each writes JSON the next one reads):

    recordings.py  recorder clips (from rikuy-video) -> segment timeline
    detect.py      RF-DETR person detection + ByteTrack, 5 fps   -> tracks
    crossing.py    net crossing of the turnstile line            -> entries / exits
    segment.py     SAM 3 'person' masks, evidence layer           -> overlay
    reconcile.py   access-control log vs. camera entries          -> audit
    report.py      muse-spark-1.3 answer over the audit           -> audit.muse
    build.py       audit + overlay -> static web demo (viewer template)
"""

__version__ = "0.1.0"
