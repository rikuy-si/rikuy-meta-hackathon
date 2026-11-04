#!/usr/bin/env python3
"""Quick multi-view preview of a GLB (vertex/face colors) with matplotlib: v004_preview.py IN.glb OUT.png"""
import sys, numpy as np, trimesh, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
m = trimesh.load(sys.argv[1], force="mesh")
if len(m.faces) > 40000: m = m.simplify_quadric_decimation(face_count=40000) if hasattr(m, "simplify_quadric_decimation") else m
v = m.vertices - m.bounds.mean(0); v /= np.abs(v).max()
try: fc = m.visual.face_colors[:, :3] / 255.0
except Exception: fc = np.full((len(m.faces), 3), .8)
fig = plt.figure(figsize=(16, 4.4))
for i, (el, az, t) in enumerate([(10, -90, "front"), (10, -45, "3/4"), (10, 0, "side"), (10, 90, "back")]):
    ax = fig.add_subplot(1, 4, i + 1, projection="3d")
    pc = Poly3DCollection(v[m.faces][:, :, [0, 2, 1]], facecolors=fc, linewidths=0); ax.add_collection3d(pc)
    ax.set_xlim(-1, 1); ax.set_ylim(-1, 1); ax.set_zlim(-1, 1); ax.view_init(el, az); ax.set_axis_off(); ax.set_title(t)
plt.tight_layout(); plt.savefig(sys.argv[2], dpi=80); print(len(m.vertices), len(m.faces), m.bounds.tolist())
