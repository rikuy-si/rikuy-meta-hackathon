"""Synthesize a royalty-free 120 BPM training track and detect its beat grid with librosa.

usage: make_music.py OUT.wav SECONDS [--bpm 120] [--drop SECONDS]
Kick on every beat, clap on 2 and 4, closed hats on 8ths, a sub-bass riff over a 4-chord loop, a white-noise
riser into --drop and an impact at --drop (the epic moment). Writes OUT.wav and OUT.beats.json (librosa beats).
"""
import sys, json, argparse
import numpy as np, soundfile as sf, librosa

ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('secs', type=float)
ap.add_argument('--bpm', type=float, default=120); ap.add_argument('--drop', type=float, default=None)
a = ap.parse_args()
SR = 44100; n = int(a.secs * SR); y = np.zeros(n, np.float32); beat = 60 / a.bpm
rng = np.random.default_rng(7)


def env(length, attack=0.002, decay=0.15):
    t = np.arange(length) / SR
    return np.minimum(1, t / attack) * np.exp(-t / decay)


def add(sig, at):
    i = int(at * SR)
    if i >= n: return
    j = min(n, i + len(sig)); y[i:j] += sig[:j - i]


L = int(0.4 * SR); t = np.arange(L) / SR
kick = np.sin(2 * np.pi * (45 + 90 * np.exp(-t * 30)) * t) * env(L, decay=0.18) * 0.9
clap = rng.standard_normal(int(0.2 * SR)) * env(int(0.2 * SR), decay=0.05) * 0.35
hat = rng.standard_normal(int(0.05 * SR)) * env(int(0.05 * SR), decay=0.012) * 0.12
hat = np.diff(hat, prepend=0)  # crude high-pass
roots = [55.0, 43.65, 49.0, 41.2]  # A1 F1 G1 E1
nb = int(a.secs / beat) + 1
for b in range(nb):
    at = b * beat
    if a.drop and a.drop - 4 * beat <= at < a.drop:  # breakdown before the drop: no kick
        pass
    else:
        add(kick, at)
    if b % 4 in (1, 3): add(clap, at)
    add(hat, at); add(hat * 0.7, at + beat / 2)
    f = roots[(b // 8) % 4]; Lb = int(beat * 0.9 * SR); tb = np.arange(Lb) / SR
    bass = (np.sin(2 * np.pi * f * tb) + 0.3 * np.sin(2 * np.pi * 2 * f * tb)) * env(Lb, 0.01, 0.35) * 0.35
    add(bass, at)
    if b % 8 == 0:  # pad chord
        Lp = int(8 * beat * SR); tp = np.arange(Lp) / SR
        pad = sum(np.sin(2 * np.pi * f * 4 * r * tp) for r in (1, 1.25, 1.5)) * 0.03 * np.minimum(1, tp / 0.5) * np.minimum(1, (tp[-1] - tp) / 0.5)
        add(pad.astype(np.float32), at)
if a.drop:
    Lr = int(4 * beat * SR); tr = np.arange(Lr) / SR
    riser = rng.standard_normal(Lr) * (tr / tr[-1]) ** 2 * 0.25
    add(riser.astype(np.float32), a.drop - 4 * beat)
    Li = int(1.5 * SR); ti = np.arange(Li) / SR
    impact = (np.sin(2 * np.pi * 38 * ti) * 1.2 + rng.standard_normal(Li) * 0.3) * np.exp(-ti / 0.5)
    add(impact.astype(np.float32), a.drop)
fade = int(2.5 * SR); y[-fade:] *= np.linspace(1, 0, fade)
y = (y / max(1e-6, np.abs(y).max()) * 0.89).astype(np.float32)
sf.write(a.out, y, SR)
tempo, frames = librosa.beat.beat_track(y=y, sr=SR, start_bpm=a.bpm, tightness=200)
beats = librosa.frames_to_time(frames, sr=SR).tolist()
json.dump({'bpm_target': a.bpm, 'tempo_librosa': float(np.atleast_1d(tempo)[0]), 'beats': beats, 'drop': a.drop},
          open(a.out[:-4] + '.beats.json', 'w'), indent=1)
print('wrote', a.out, 'tempo', float(np.atleast_1d(tempo)[0]), 'beats', len(beats))
