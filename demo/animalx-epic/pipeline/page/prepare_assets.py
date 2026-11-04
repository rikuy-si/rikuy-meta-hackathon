"""Copy the v008 edits into the page folder with web names, make the WhatsApp-ready mobile files and the posters.

usage: prepare_assets.py [--out ~/.agent/diagrams] [--version v008]
  axs-<client>-<lang>-16x9.mp4     the 1080p 16:9 edit re-encoded for the web: H.264 High, CRF 22, <= 4.5 Mb/s, faststart
  axs-<client>-<lang>-movil.mp4    the 9:16 edit re-encoded for WhatsApp: 720x1280, H.264 High, <= 1.6 Mb/s, AAC 128k, faststart
  axs-<client>-<lang>-poster.jpg / -poster-movil.jpg   the "NEW RECORD" frame (drop + 3 s)
"""
import json, pathlib, argparse, subprocess, os, shutil
ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser(); ap.add_argument('--out', default=os.path.expanduser('~/.agent/diagrams')); ap.add_argument('--version', default='v008')
a = ap.parse_args(); OUT = pathlib.Path(a.out)
FF = '/usr/bin/ffmpeg'
for c in ('victor', 'manuela'):
    for L in ('es', 'en'):
        src = ROOT / 'edit' / c / a.version / f'{c}_{a.version}_{L}_16x9.mp4'
        mob = ROOT / 'edit' / c / a.version / f'{c}_{a.version}_{L}_9x16.mp4'
        drop = json.load(open(str(src)[:-4] + '.audit.json'))['drop_t']
        subprocess.run([FF, '-v', 'error', '-y', '-i', str(src), '-c:v', 'libx264', '-profile:v', 'high', '-preset', 'slow', '-crf', '22',
                        '-maxrate', '4500k', '-bufsize', '9000k', '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart',
                        str(OUT / f'axs-{c}-{L}-16x9.mp4')], check=True)
        subprocess.run([FF, '-v', 'error', '-y', '-i', str(mob), '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264', '-profile:v', 'high',
                        '-preset', 'slow', '-crf', '25', '-maxrate', '1600k', '-bufsize', '3200k', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(OUT / f'axs-{c}-{L}-movil.mp4')], check=True)
        for v, name in ((src, 'poster'), (mob, 'poster-movil')):
            subprocess.run([FF, '-v', 'error', '-y', '-ss', f'{drop + 3.0:.2f}', '-i', str(v), '-frames:v', '1', '-vf',
                            'scale=1280:-2' if name == 'poster' else 'scale=720:-2', '-q:v', '3', str(OUT / f'axs-{c}-{L}-{name}.jpg')], check=True)
        print(c, L, {p.name: round(p.stat().st_size / 1e6, 1) for p in OUT.glob(f'axs-{c}-{L}-*')})
