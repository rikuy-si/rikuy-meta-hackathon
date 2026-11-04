"""Read the DVR on-screen clock (HH:MM:SS, top-left) from video frames.

The OSD is white text with a dark outline that may turn black over bright
backgrounds, so several binarisations are OCR'd and the value that agrees with
an expected time (`near`) is kept.
"""
import re, subprocess, tempfile, pathlib, collections

FILTERS = [
    'format=gray,negate',
    'format=gray',
    "format=gray,lutyuv=y='if(gt(val,200),0,255)'",
    "format=gray,lutyuv=y='if(lt(val,60),0,255)'",
]

def _grab(video, offset, path):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{offset:.2f}', '-i', str(video), '-frames:v', '1',
                    '-vf', 'crop=150:34:222:30,scale=600:-1', str(path)], timeout=60)

def _ocr(png, vf, d):
    out = pathlib.Path(d) / 'b.png'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(png), '-vf', vf, str(out)], timeout=30)
    return subprocess.run(['tesseract', str(out), '-', '--psm', '7', '-c', 'tessedit_char_whitelist=0123456789:'],
                          capture_output=True, text=True).stdout

def osd_hms(video, offset=0.0, near=None, window=900):
    votes = collections.Counter()
    with tempfile.TemporaryDirectory() as d:
        png = pathlib.Path(d) / 'c.png'
        _grab(video, offset, png)
        if not png.exists():
            return None
        for vf in FILTERS:
            t = _ocr(png, vf, d).replace(' ', '').strip()
            m = re.search(r'(\d{2}):?(\d{2}):?(\d{2})', t)
            if m:
                H, M, S = map(int, m.groups())
                if H < 24 and M < 60 and S < 60:
                    s = H * 3600 + M * 60 + S
                    if near is None or abs(s - near) < window:
                        votes[s] += 1
    return votes.most_common(1)[0][0] if votes else None
