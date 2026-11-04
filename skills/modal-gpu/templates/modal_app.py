"""Modal app template for one heavy pipeline step. Copy next to the pipeline and edit the marked lines.

    modal run modal_app.py::run --sample 60     # calibration: first 60 s only, prints frames/s
    modal run modal_app.py::run                 # full run
    modal volume get rikuy-work <out_path> work/
Inputs go in first: modal volume put rikuy-work work/clips /clips
"""
import time

import modal

GPU = "L4"                                   # EDIT: from references/budget.md
TIMEOUT_S = 2 * 60 * 60                      # EDIT: 2x the quoted ETA

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install("torch", "opencv-python-headless", "numpy")      # EDIT: the step's extras
    .add_local_dir(".", "/pipeline")                               # EDIT: the pipeline package
)
work = modal.Volume.from_name("rikuy-work", create_if_missing=True)
models = modal.Volume.from_name("rikuy-models", create_if_missing=True)
app = modal.App("rikuy-step", image=image)


@app.function(gpu=GPU, timeout=TIMEOUT_S, volumes={"/work": work, "/root/.cache": models},
              secrets=[modal.Secret.from_name("hf-token")])
def step(sample: int = 0) -> dict:
    import sys
    sys.path.insert(0, "/pipeline/src")
    t0 = time.time()
    # EDIT: call the pipeline stage, e.g.
    # from rikuy_gym import segment, recordings
    # segs = recordings.read(Path("/work/segments.json"))
    # frames = segment.run(Path("/work/clips"), segs, Path("/work/sam.json"), fps=2, max_seconds=sample or None)
    frames = 0
    work.commit(); models.commit()
    secs = time.time() - t0
    return {"gpu": GPU, "frames": frames, "seconds": round(secs, 1), "fps": round(frames / secs, 2) if secs else 0}


@app.local_entrypoint()
def run(sample: int = 0):
    r = step.remote(sample)
    print(r)
    print(f"calibrate: python3 scripts/estimate.py --model <key> --gpu {r['gpu']} --fps {r['fps']} --frames <N>")
