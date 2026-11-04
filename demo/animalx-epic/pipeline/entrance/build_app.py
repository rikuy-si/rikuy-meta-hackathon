"""Build a static local web app: one card per identified ERP entry with turnstile photos.

For each identified entry (minute precision) it lists every turnstile passage on
camera 03 in a window around the ERP minute, shifted by the estimated clock lag,
and saves a person crop, a full frame with the box drawn, and a short MP4.
"""
import json, csv, pathlib, subprocess, html, datetime as dt
import av, cv2

ROOT = pathlib.Path(__file__).resolve().parent
W = ROOT / 'work'
APP = ROOT / 'app'
MEDIA = APP / 'media'
from frames import DVR

PRE, POST = 150, 90          # seconds around the ERP minute (after lag) to list candidates
LIKELY = (-30, 30)            # window considered "most likely" relative to minute start + lag

def fmt(s):
    s = int(round(s)); return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'

def grab(clip, t_rel):
    c = av.open(str(DVR / 'videos' / f'{clip}.dav')); s = c.streams.video[0]
    t0 = None; img = None
    for fr in c.decode(s):
        if fr.pts is None: continue
        t = float(fr.pts * s.time_base)
        if t0 is None:
            t0 = t
            if t_rel > 3:
                c.seek(int((t0 + t_rel - 2) / s.time_base), stream=s, backward=True, any_frame=False)
                continue
        if t - t0 >= t_rel - 0.02:
            img = fr.to_ndarray(format='bgr24'); break
    c.close()
    return img

def clip_mp4(clip, t_rel, out, before=3, after=5):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{max(0, t_rel - before):.2f}', '-i', str(DVR / 'videos' / f'{clip}.dav'),
                    '-t', f'{before + after}', '-an', '-vf', 'scale=640:-2', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '28',
                    '-movflags', '+faststart', str(out)], timeout=120)

def main():
    ev = [e for e in json.load(open(W / 'events_dir.json'))['events'] if e.get('dir') and e['dir'][1] < -40]  # moving up = entering
    al = json.load(open(W / 'alignment.json')); al.update(json.load(open(W / 'alignment_up.json'))); lag = al['lag_s']
    rows = [r for r in csv.DictReader(open(ROOT / 'exports' / 'entradas_2026-10-29.csv')) if r['identificado'] == 'si']
    MEDIA.mkdir(parents=True, exist_ok=True)
    profiles = json.load(open(W / 'profiles.json'))
    cards = []
    for i, r in enumerate(rows):
        m = int(r['hora_local'][:2]) * 60 + int(r['hora_local'][3:])
        base = m * 60 + 30 + lag   # centre of the ERP minute, shifted by the clock lag
        cands = sorted([e for e in ev if base - PRE <= e['start'] <= base + POST], key=lambda e: abs(e['start'] - base))[:8]
        late = False
        if not any(LIKELY[0] <= e['start'] - base <= LIKELY[1] for e in cands):
            # Possibly registered late in the ERP: add the most recent entering passages of the previous 30 min.
            prev = [e for e in ev if base - 1800 <= e['start'] < base - PRE]
            cands += prev[-4:]; late = bool(prev)
        cands.sort(key=lambda e: e['start'])
        items = []
        for j, e in enumerate(cands):
            b = e['best']; key = f'e{i:02d}_{j:02d}'
            crop_p, full_p, mp4_p = MEDIA / f'{key}_crop.jpg', MEDIA / f'{key}_full.jpg', MEDIA / f'{key}.mp4'
            if not crop_p.exists():
                img = grab(b['clip'], b['t_rel'])
                if img is None: continue
                x1, y1, x2, y2 = b['box']; w, h = x2 - x1, y2 - y1
                X1, Y1 = max(0, int(x1 - .25 * w)), max(0, int(y1 - .15 * h)); X2, Y2 = min(img.shape[1], int(x2 + .25 * w)), min(img.shape[0], int(y2 + .15 * h))
                cv2.imwrite(str(crop_p), img[Y1:Y2, X1:X2], [cv2.IMWRITE_JPEG_QUALITY, 88])
                full = img.copy(); cv2.rectangle(full, (x1, y1), (x2, y2), (0, 220, 255), 3)
                cv2.imwrite(str(full_p), full, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if not mp4_p.exists():
                clip_mp4(b['clip'], b['t_rel'], mp4_p)
            rel = e['start'] - m * 60
            items.append({'key': key, 'video_time': fmt(b['day_s']), 'pass_time': fmt(e['start']), 'delta': round(e['start'] - base), 'likely': LIKELY[0] <= e['start'] - base <= LIKELY[1]})
        pr = profiles.get(r['documento'], {})
        cards.append({'i': i, 'erp': r['hora_local'], 'name': r['cliente'], 'doc': r['documento'], 'profile': f"media/profiles/{pr['key']}.jpg" if pr.get('status') == 'photo' else None, 'late': late, 'cands': items})
        print(r['hora_local'], len(items), 'candidates', flush=True)
    data = {'date': '2026-10-29', 'lag_s': lag, 'align': {k: al[k] for k in ('hits', 'entries', 'hits_random_mean', 'up_events', 'note')}, 'cards': cards}
    (APP / 'data.js').write_text('window.DATA = ' + json.dumps(data, ensure_ascii=False) + ';')
    print('cards', len(cards))

if __name__ == '__main__':
    main()
