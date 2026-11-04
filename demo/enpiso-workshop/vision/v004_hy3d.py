#!/usr/bin/env python3
"""Hunyuan3D-2 (shape only) from an RGBA image: v004_hy3d.py IN_RGBA.png OUT.glb [model] [subfolder]"""
import sys, time, json, torch
from PIL import Image
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline, FloaterRemover, DegenerateFaceRemover, FaceReducer
src, out = sys.argv[1], sys.argv[2]
model = sys.argv[3] if len(sys.argv) > 3 else "tencent/Hunyuan3D-2mini"
sub = sys.argv[4] if len(sys.argv) > 4 else "hunyuan3d-dit-v2-mini"
t0 = time.time()
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(model, subfolder=sub, use_safetensors=True, device="cuda")
img = Image.open(src).convert("RGBA")
mesh = pipe(image=img, num_inference_steps=30, octree_resolution=380, num_chunks=20000, generator=torch.manual_seed(42), output_type="trimesh")[0]
for f in (FloaterRemover(), DegenerateFaceRemover(), FaceReducer()):
    mesh = f(mesh)
mesh.export(out)
print(json.dumps(dict(model=model, sub=sub, seconds=round(time.time() - t0, 1), faces=len(mesh.faces), peak_gib=round(torch.cuda.max_memory_allocated() / 2**30, 2))))
