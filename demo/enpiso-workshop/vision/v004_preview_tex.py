#!/usr/bin/env python3
import sys, numpy as np, trimesh, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
m = trimesh.load(sys.argv[1], force="mesh"); col = np.load(sys.argv[1].replace(".glb", "-facecolors.npy")) / 255.0
v = m.vertices - m.bounds.mean(0); v /= np.abs(v).max()
idx = np.random.default_rng(0).permutation(len(m.faces))[:30000]
fig = plt.figure(figsize=(16, 4.4))
for i, (el, az, t) in enumerate([(5, -90, "front"), (15, -55, "3/4"), (5, 0, "side"), (5, 90, "back")]):
    ax = fig.add_subplot(1, 4, i + 1, projection="3d")
    ax.add_collection3d(Poly3DCollection(v[m.faces[idx]][:, :, [0, 2, 1]], facecolors=col[idx], linewidths=0))
    ax.set_xlim(-1, 1); ax.set_ylim(-1, 1); ax.set_zlim(-1, 1); ax.view_init(el, az); ax.set_axis_off(); ax.set_title(t)
plt.tight_layout(); plt.savefig(sys.argv[2], dpi=80)
