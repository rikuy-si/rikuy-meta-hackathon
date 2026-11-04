"""Phase M v008: bilingual (es/en), two formats (16:9 and 9:16), Rikuy design system, gamified record sequence.

usage: edit5.py CLIENT --title VÍCTOR --gender m --erp-doc <ERP_MEMBER_ID> --lang en --aspect 9x16 [--version v008]
Inputs: work/v003/<client>/plan.json, masks/, masks.json, s3db2/ (s3d_replay2.py), source/<client>/<day>/exercises.json,
ERP facts from ../work/tracking.json and ../work/client_history.json (visit days, monthly visits since the first
recorded month). Every on-screen string comes from STR or EX (exercise names); a missing translation stops the render.
ds.text guards stop the render on dashes, off-safe-area text, text below 12 px or a missing glyph.
Outputs edit/<client>/<version>/<client>_<version>_<lang>_<aspect>.mp4 (+ edl/audit/texts json, music, sfx).
"""
import json, math, pathlib, argparse, subprocess, sys, datetime as dt
import numpy as np, cv2, soundfile as sf
from PIL import ImageDraw
import ds
from ds import C

ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser(); ap.add_argument('client'); ap.add_argument('--title', required=True)
ap.add_argument('--gender', choices=['m', 'f'], required=True); ap.add_argument('--erp-doc', required=True)
ap.add_argument('--lang', choices=['es', 'en'], required=True); ap.add_argument('--aspect', choices=['16x9', '9x16'], required=True)
ap.add_argument('--version', default='v008'); ap.add_argument('--bpm', type=float, default=120)
ap.add_argument('--draft', action='store_true', help='footage shots as flat frames (fast layout check of all overlays)')
a = ap.parse_args()
VERT = a.aspect == '9x16'
ds.set_canvas(1080, 1920) if VERT else ds.set_canvas(1920, 1080)
W, H = ds.W, ds.H
SAFE_L, SAFE_T, SAFE_R, SAFE_B = ds.CTX['safe']
FPS = 30; BEAT = 60 / a.bpm; SR = 44100; L = a.lang; F = a.gender == 'f'
wd = ROOT / 'work' / 'v003' / a.client
plan = json.load(open(wd / 'plan.json'))
out_dir = ROOT / 'edit' / a.client / a.version; out_dir.mkdir(parents=True, exist_ok=True)
stem = f'{a.client}_{a.version}_{L}_{a.aspect}'
vid = out_dir / f'{stem}.video.mp4'
enc = subprocess.Popen(['/usr/bin/ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS),
                        '-i', '-', '-c:v', 'h264_nvenc', '-preset', 'p6', '-cq', '20', '-pix_fmt', 'yuv420p', str(vid)], stdin=subprocess.PIPE)

# ------------------------------------------------------------------ strings
STR = {
    'es': {'title_sub': 'ANIMAL X · {span}', 'day_sub': 'Llega {t} · {n} series', 'arrival': 'Llega a entrenar',
           'chip_peak': 'La serie más dura del día', 'chip_spot': 'Con apoyo de un compañero', 'chip_slow': 'Cámara lenta',
           'reps': 'repeticiones', 'moment': 'El momento', 'new': 'NUEVO', 'record': 'RÉCORD',
           'stats_n': 'Tus {n} días en ANIMAL X', 'stats_1': 'Tu día en ANIMAL X', 'sets': 'series', 'minutes': 'minutos de trabajo',
           'counted': 'Contadas a partir del video', 'streak_n': '{n} días seguidos', 'streak_1': '1 día',
           'badges': 'Insignias desbloqueadas', 'early': 'Madrugadora' if F else 'Madrugador', 'early_d': 'llegó a las {t}',
           'team': 'En equipo', 'team_d': '{n} series con compañero', 'team_d1': '1 serie con compañero',
           'chest': 'Pecho de acero', 'chest_d': '{n} series de press de pecho', 'legs': 'Piernas de acero', 'legs_d': '{n} series de pierna',
           'loyal': 'Socia fiel' if F else 'Socio fiel', 'loyal_d': '{v} visitas desde {y}',
           'longest': 'Tu serie más larga', 'in_row': 'repeticiones seguidas', 'level_t': 'Tu nivel en ANIMAL X', 'level': 'Nivel {n}',
           'to_next': '{r} repeticiones para el nivel {n}', 'rule': 'Un nivel cada {s} repeticiones',
           'real': 'Real', 'replay': 'Repetición 3D', 'note_bench_bar': 'SAM 3D Body · barra y banco ilustrativos',
           'note_dumbbells': 'SAM 3D Body · mancuernas ilustrativas', 'made_with': 'Hecho con'},
    'en': {'title_sub': 'ANIMAL X · {span}', 'day_sub': 'Arrives {t} · {n} sets', 'arrival': 'Arrives to train',
           'chip_peak': 'Toughest set of the day', 'chip_spot': 'With a spotter', 'chip_slow': 'Slow motion',
           'reps': 'reps', 'moment': 'The moment', 'new': 'NEW', 'record': 'RECORD',
           'stats_n': 'Your {n} days at ANIMAL X', 'stats_1': 'Your day at ANIMAL X', 'sets': 'sets', 'minutes': 'minutes of work',
           'counted': 'Counted from the video', 'streak_n': '{n} days in a row', 'streak_1': '1 day',
           'badges': 'Badges unlocked', 'early': 'Early bird', 'early_d': 'arrived at {t}',
           'team': 'Team player', 'team_d': '{n} sets with a spotter', 'team_d1': '1 set with a spotter',
           'chest': 'Iron chest', 'chest_d': '{n} chest press sets', 'legs': 'Iron legs', 'legs_d': '{n} leg sets',
           'loyal': 'Loyal member', 'loyal_d': '{v} visits since {y}',
           'longest': 'Your longest set', 'in_row': 'reps in a row', 'level_t': 'Your level at ANIMAL X', 'level': 'Level {n}',
           'to_next': '{r} reps to level {n}', 'rule': 'One level every {s} reps',
           'real': 'Real', 'replay': '3D replay', 'note_bench_bar': 'SAM 3D Body · illustrative bar and bench',
           'note_dumbbells': 'SAM 3D Body · illustrative dumbbells', 'made_with': 'Made with'}}
EX_EN = {'curl de bíceps con mancuernas (clase)': 'Dumbbell biceps curl (class)',
         'extensión de tríceps sobre la cabeza': 'Overhead triceps extension', 'flexiones de pecho': 'Push-ups',
         'flexiones declinadas (pies en el cajón)': 'Decline push-ups (feet on a box)', 'peso muerto con barra': 'Barbell deadlift',
         'peso muerto rumano / remo con mancuernas': 'Romanian deadlift / dumbbell row',
         'press / extensión de tríceps sobre la cabeza': 'Overhead press / triceps extension', 'press de banca con barra': 'Barbell bench press',
         'press de hombros con mancuernas de pie': 'Standing dumbbell shoulder press', 'press de hombros sentada': 'Seated shoulder press',
         'press de pecho con mancuernas en el suelo': 'Dumbbell floor press', 'press inclinado con mancuernas': 'Incline dumbbell press',
         'press inclinado con mancuernas (con compañero de apoyo)': 'Incline dumbbell press (with a spotter)',
         'remo + extensión de tríceps': 'Row + triceps extension', 'remo a una mano apoyado en banco': 'One-arm row on a bench',
         'remo inclinado con mancuernas': 'Bent-over dumbbell row', 'sentadilla con mancuernas al hombro': 'Dumbbell front squat',
         'sentadilla goblet': 'Goblet squat', 'thruster / press': 'Thruster / press', 'thruster con barra (clase)': 'Barbell thruster (class)',
         'thruster con mancuernas (sentadilla + press)': 'Dumbbell thruster (squat + press)', 'zancada con press': 'Lunge with press',
         'zancadas': 'Lunges', 'zancadas con mancuernas': 'Dumbbell lunges', 'Listo para la siguiente': 'Ready for the next one'}
DIAS = {'es': ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'], 'en': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']}
MES = {'es': ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'],
       'en': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']}


def S(k, **kw):
    return STR[L][k].format(**kw)


def ex(name, short=False):
    n = name.split(' (')[0] if short and '(' in name and 'clase' not in name else name
    if L == 'es':
        return n[:1].upper() + n[1:]
    if name in EX_EN:
        return EX_EN[name].split(' (')[0] if short and '(' in name and 'clase' not in name else EX_EN[name]
    raise KeyError(f'no English name for exercise {name!r}')


def num(v):
    return f'{v:,}'.replace(',', '.' if L == 'es' else ',')


def day_label(day):
    d = dt.date.fromisoformat(day)
    return f"{DIAS[L][d.weekday()]} {day[8:10]}·{day[5:7]}" if L == 'es' else f"{DIAS[L][d.weekday()]} {MES[L][d.month - 1]} {d.day}"


edl, T, SFX = [], [0], []


def snap(secs):
    return max(BEAT, round(secs / BEAT) * BEAT)


def nframes(secs):
    return int(round(snap(secs) * FPS))


def put(img):
    enc.stdin.write(np.ascontiguousarray(img).tobytes()); T[0] += 1


def now():
    return T[0] / FPS


def sfx(kind, at=None):
    SFX.append((now() if at is None else at, kind))


def seg(kind):
    ds.CTX['seg'] = kind


def txt(d, xy, t, kind, size, fill, anchor='la', max_w=None):
    """ds.text with automatic shrink-to-fit (default: the safe width)."""
    mw = max_w or (SAFE_R - SAFE_L)
    return ds.text(d, xy, t, kind, ds.fit(t, kind, size, mw), fill, anchor)


# ------------------------------------------------------------------ footage
class Masks:
    def __init__(self, path):
        z = np.load(path); self.t = z['times']; self.m = z['masks']

    def at(self, t):
        i = int(np.argmin(np.abs(self.t - t))); return np.unpackbits(self.m[i], axis=-1)[:, :1280].astype(bool)


RIM = np.array(ds.bgr(C['menta']), np.float32)


def composite(img, m):
    small = cv2.resize(m.astype(np.uint8), (640, 360), interpolation=cv2.INTER_NEAREST)
    ring = cv2.dilate(small, np.ones((7, 7), np.uint8)) - small
    rim = cv2.resize(cv2.GaussianBlur(ring.astype(np.float32), (0, 0), 3), (1280, 720))[..., None]
    return np.clip(img.astype(np.float32) * (1 - 0.8 * np.clip(rim * 1.6, 0, 1)) + rim * RIM * 1.6, 0, 255).astype(np.uint8)


CAM = {}
OSD_H = 62                                                      # burned-in CCTV date/time band at the top
OSD_LABEL = np.zeros((720, 1280), np.uint8); OSD_LABEL[632:670, 914:1070] = 255   # burned-in 'Camera 0X' label (same on all 4 cameras)


def deosd(img):
    """Remove the burned-in camera label so no crop can show it cut in half (e.g. 'Camer')."""
    return cv2.inpaint(img, OSD_LABEL, 5, cv2.INPAINT_TELEA)

ASP = W / H


def camera(img, m):
    ys, xs = np.nonzero(m)
    if len(xs) < 50:
        tx, ty, th = CAM.get('c', (640, 360, 720))
    else:
        x1, x2, y1, y2 = np.percentile(xs, 2), np.percentile(xs, 98), np.percentile(ys, 2), np.percentile(ys, 98)
        k = 1.35 if VERT else 1.7
        tx, ty, th = (x1 + x2) / 2, (y1 + y2) / 2, float(np.clip(max(y2 - y1, (x2 - x1) / ASP) * k, 300, 720 - OSD_H if VERT else 720))
    if 'c' not in CAM: CAM['c'] = (tx, ty, th)
    cx, cy, ch = CAM['c']; cx += 0.12 * (tx - cx); cy += 0.12 * (ty - cy); ch += 0.06 * (th - ch); CAM['c'] = (cx, cy, ch)
    cw = ch * ASP
    if cw > 1280: cw, ch = 1280, 1280 / ASP
    x0 = int(np.clip(cx - cw / 2, 0, 1280 - cw))
    ytop = OSD_H if ch <= 720 - OSD_H else 0                    # a zoomed crop never cuts through the CCTV clock
    y0 = int(np.clip(cy - ch / 2, ytop, 720 - ch))
    return cv2.resize(img[y0:y0 + int(ch), x0:x0 + int(cw)], (W, H), interpolation=cv2.INTER_CUBIC)


def chip(d, x, y, label, fill, ink, size=28):
    w = ds.text_w(label, 'onest5', size) + 44
    d.rounded_rectangle([x, y, x + w, y + 56], 28, fill=fill)
    ds.text(d, (x + 22, y + 28), label, 'onest5', size, ink, 'lm')
    return w


def chips_flow(d, items, x0, y0, x_max):
    x, y = x0, y0
    for label, fill, ink in items:
        w = ds.text_w(label, 'onest5', 28) + 44
        if x > x0 and x + w > x_max:
            x, y = x0, y + 68
        chip(d, x, y, label, fill, ink); x += w + 16


def lower_third(d, title, data):
    maxw = SAFE_R - SAFE_L - 76
    ts = ds.fit(title, 'grift', 52, maxw)
    tw = max(ds.text_w(title, 'grift', ts), ds.text_w(data, 'mono', 28))
    x0, y1 = SAFE_L, SAFE_B; y0 = y1 - 150
    d.rounded_rectangle([x0, y0, x0 + tw + 76, y1], 18, fill=ds.with_alpha(C['noche'], 0.9))
    d.rounded_rectangle([x0 + 20, y0 + 26, x0 + 28, y1 - 26], 4, fill=C['menta'])
    ds.text(d, (x0 + 48, y0 + 30), title, 'grift', ts, C['blanco'], 'lt')
    ds.text(d, (x0 + 48, y0 + 100), data, 'mono', 28, C['hielo'], 'lt')


def rep_tile(d, n, pop):
    s = 1 + 0.08 * max(0.0, 1 - pop / 0.15) if pop is not None else 1.0
    size = 220 * s; x1, y0 = SAFE_R, SAFE_T; x0 = x1 - size
    d.rounded_rectangle([x0, y0, x1, y0 + size], 24, fill=C['amarillo'])
    ds.text(d, ((x0 + x1) / 2, y0 + size * 0.44), str(n), 'grift', int(120 * s), C['noche'], 'mm')
    ds.text(d, ((x0 + x1) / 2, y0 + size * 0.82), S('reps'), 'onest', 24, C['noche2'], 'mm')


SLOW_REP = {'V29-020': -2}                                       # reviewed: pose counts the stand-up as rep 5
MASK_MAX_LOST = 0.2
MASKQ = json.load(open(wd / 'masks.json'))
SKIPPED = []


def render(s, lower, src_times, chips=(), kind=None, slow_from=None):
    k_ = kind or s['kind']
    q = MASKQ.get(f"{s['day']}_{s['clip']}_{s['t_in']:.2f}", {})
    if q.get('iou_lt_0_3', 0) > MASK_MAX_LOST and k_ != 'finale':
        SKIPPED.append({'kind': k_, 'set_id': s.get('set_id'), 'clip': s['clip'], 'iou_lt_0_3': q.get('iou_lt_0_3')}); return
    seg(k_)
    clip = ROOT / 'source' / a.client / s['day'] / 'clips' / f"{s['clip']}.mp4"
    M = Masks(wd / 'masks' / f"{s['day']}_{s['clip']}_{s['t_in']:.2f}.npz")
    cap = cv2.VideoCapture(str(clip)); vf = cap.get(5)
    cur, img = -10, None; t0 = now(); n = len(src_times); CAM.clear()
    R = [s['t_in'] + r for r in s.get('rep_times', [])]
    last_n, pop_at = 0, None
    for i, st in enumerate(src_times):
        if a.draft:
            img = np.full((720, 1280, 3), 60, np.uint8); m = np.zeros((720, 1280), bool); m[200:500, 560:720] = True
        else:
            fi = int(round(st * vf))
            if fi != cur:
                if fi != cur + 1: cap.set(1, fi)
                ok, fr = cap.read()
                if ok: img = deosd(fr)
                cur = fi
            m = M.at(st)
        out = camera(composite(img, m), m)
        lay = ds.layer(); d = ImageDraw.Draw(lay)
        lower_third(d, *lower)
        items = list(chips) + ([(S('chip_slow'), C['noche2'], C['blanco'])] if slow_from is not None and i >= slow_from else [])
        chips_flow(d, items, SAFE_L, SAFE_T, SAFE_R - 240)
        reps = sum(1 for r in R if r <= st)
        if R and reps > 0:
            if reps != last_n:
                pop_at = i; last_n = reps; sfx('tick')
            rep_tile(d, reps, (i - pop_at) / FPS if pop_at is not None else None)
        out = ds.compose(out, lay)
        put(ds.fade_to(out, C['noche'], ds.ease(min(1.0, (i + 1) / 5, (n - i) / 5))))
    cap.release()
    edl.append({'t': round(t0, 2), 'dur': round(n / FPS, 2), 'kind': k_, 'set_id': s.get('set_id'), 'day': s['day'],
                'clip': s['clip'], 'src_in': round(min(src_times), 2), 'src_out': round(max(src_times), 2), 'lower': list(lower),
                'pose_reps_in_shot': sum(1 for r in R if min(src_times) <= r <= max(src_times)), 'exercise': s.get('exercise'),
                'identity': s.get('identity')})


def linear(t_in, secs):
    return [t_in + i / FPS for i in range(int(round(secs * FPS)))]


def slowmo_last(s, secs, slow_secs=3.0, factor=0.5):
    R = [s['t_in'] + r for r in s['rep_times']]
    k = SLOW_REP.get(s.get('set_id'), -1)
    last = R[k] if len(R) >= -k else s['t_in'] + s['dur'] - 1
    s0 = min(last + 0.5, s['t_in'] + s['dur']) - slow_secs * factor
    normal = max(0, int(round((secs - slow_secs) * FPS)))
    ts = [s0 - (normal - i) / FPS for i in range(normal)]
    return ts + [s0 + i * factor / FPS for i in range(int(round(slow_secs * FPS)))], normal


def screen(kind, secs, draw, base=None, fade=True, info=None):
    seg(kind); n = nframes(secs); t0 = now()
    for i in range(n):
        sec = i / FPS
        img = (base(sec) if callable(base) else base.copy()) if base is not None else ds.solid(C['noche'])
        lay = ds.layer(); d = ImageDraw.Draw(lay)
        r_ = draw(d, lay, img, sec); img = img if r_ is None else r_
        out = ds.compose(img, lay)
        if fade:
            al = ds.ease(min(1.0, (n - i) / 5) if fade == 'out' else min(1.0, (i + 1) / 5, (n - i) / 5))
            out = ds.fade_to(out, C['noche'], al)
        put(out)
    edl.append({'t': round(t0, 2), 'dur': round(n / FPS, 2), 'kind': kind, **(info or {})})


# ------------------------------------------------------------------ facts (video + ERP)
name = a.title
days = plan['days']
d0, d1 = dt.date.fromisoformat(days[0]['day']), dt.date.fromisoformat(days[-1]['day'])
if L == 'es':
    span = f"{d0.day} a {d1.day} {MES[L][d1.month - 1]} {d1.year}" if len(days) > 1 else f"{d0.day} {MES[L][d0.month - 1]} {d0.year}"
else:
    span = f"{MES[L][d1.month - 1]} {d0.day} to {d1.day}, {d1.year}" if len(days) > 1 else f"{MES[L][d0.month - 1]} {d0.day}, {d0.year}"
ALL = []
for d in days:
    for e in json.load(open(ROOT / 'source' / a.client / d['day'] / 'exercises.json'))['sets']:
        if e['is_exercise'] and e['t0'] is not None:
            e['day'] = d['day']; ALL.append(e)
reps_of = lambda e: e['reps_agent'] or e['reps_pose'] or 0
TOT = {'sets': len(ALL), 'reps': sum(reps_of(e) for e in ALL), 'minutes': round(sum((e['t1'] - e['t0']) / 60 for e in ALL))}
_trk = json.load(open(ROOT.parent / 'work' / 'tracking.json'))
TRK = next(v for v in (_trk.values() if isinstance(_trk, dict) else _trk) if v['doc'] == a.erp_doc)
HIST = json.load(open(ROOT.parent / 'work' / 'client_history.json'))[a.erp_doc]
ERP_DAYS = sorted(dt.date.fromisoformat(x.replace('/', '-')) for x in TRK['dias'])
streak, run = 1, 1
for p_, q_ in zip(ERP_DAYS, ERP_DAYS[1:]):
    run = run + 1 if (q_ - p_).days == 1 else 1; streak = max(streak, run)
visits_total = sum(HIST['mensual'].values()); first_year = min(HIST['mensual'])[:4]
earliest = min(d['first_seen'][:5] for d in days)
spotter_sets = sum(1 for e in ALL if e.get('spotter'))
SURE = [e for e in ALL if e.get('confidence') in ('high', 'med')]                     # badge counts use reviewed labels only
chest = sum(1 for e in SURE if 'press' in e['exercise'] and any(k in e['exercise'] for k in ('banca', 'pecho', 'inclinado')) and 'preparación' not in e['exercise'])
legs = sum(1 for e in SURE if any(k in e['exercise'] for k in ('sentadilla', 'zancada', 'thruster', 'peso muerto', 'subida al banco')))
WARM = ('calentamiento', 'estiramiento', 'clase', 'caminata', 'movilidad', 'preparación')
strong = [e for e in ALL if e.get('confidence') == 'high' and not any(k in e['exercise'].lower() for k in WARM)]
longest = max(strong, key=reps_of) if strong else None
LEVEL_STEP = 250
BADGES = []
if earliest < '06:00': BADGES.append(('sun', S('early'), S('early_d', t=earliest)))
if spotter_sets: BADGES.append(('team', S('team'), S('team_d', n=spotter_sets) if spotter_sets > 1 else S('team_d1')))
if chest >= 3: BADGES.append(('barbell', S('chest'), S('chest_d', n=chest)))
if legs >= 5 and len(BADGES) < 3: BADGES.append(('barbell', S('legs'), S('legs_d', n=legs)))
BADGES = BADGES[:3] + [('flame', S('loyal'), S('loyal_d', v=num(visits_total), y=first_year))]
DAYP = [day_label(x.isoformat()) for x in ERP_DAYS]
FACTS = {'totals': TOT, 'streak_days_erp': streak, 'erp_days': [x.isoformat() for x in ERP_DAYS], 'earliest_arrival': earliest,
         'spotter_sets': spotter_sets, 'chest_press_sets': chest, 'leg_sets': legs, 'visits_since_first_month': visits_total,
         'first_month': min(HIST['mensual']), 'badges': BADGES,
         'longest_high_conf_set': {'exercise': longest['exercise'], 'day': longest['day'], 'reps': reps_of(longest)} if longest else None,
         'level_rule': f'video only: 1 level per {LEVEL_STEP} detected reps', 'level': TOT['reps'] // LEVEL_STEP}

# ------------------------------------------------------------------ timeline
CX, CY = W / 2, H / 2
BOXW = min(900, SAFE_R - SAFE_L - 40)


def title_draw(d, lay, img, sec):
    k = ds.ease(sec / 0.6); m = 140 * (1 - k)
    ds.corners(d, (CX - BOXW / 2 - m, CY - 210 - m, CX + BOXW / 2 + m, CY + 210 + m), C['menta'], L=56, w=6)
    txt(d, (CX, CY + 20), name, 'grift', 180, C['blanco'], 'ms', BOXW - 80)
    txt(d, (CX, CY + 130), S('title_sub', span=span), 'onest', 48, C['hielo'], 'ms', BOXW - 60)


screen('title', 8 * BEAT, title_draw)
for d in days:
    n_series = sum(1 for e in ALL if e['day'] == d['day'])

    def day_draw(dd, lay, img, sec, d=d, n_series=n_series):
        txt(dd, (CX, CY + 40), day_label(d['day']), 'grift', 150, C['noche'], 'ms')
        txt(dd, (CX, CY + 140), S('day_sub', t=d['first_seen'][:5], n=n_series), 'onest', 48, C['noche2'], 'ms')
    screen('day', 4 * BEAT, day_draw, base=ds.solid(C['menta']))
    if d['arrival']:
        s = d['arrival']
        render(s, (S('arrival'), f"{d['first_seen'][:5]} · {day_label(d['day'])}"), linear(s['t_in'], snap(s['dur'])), kind='arrival')
    for s in d['sets']:
        render(s, (ex(s['exercise']), f"{s['start'][:5]} · {day_label(s['day'])}"), linear(s['t_in'], snap(s['dur'])))
    if plan.get('hero') and plan['hero']['day'] == d['day']:
        h = plan['hero']; h['rep_times'] = []
        render(h, (ex(h['caption']), day_label(h['day'])), linear(h['t_in'], snap(h['dur'])), kind='hero')
    if d['peak']:
        s = d['peak']
        chips = [(S('chip_peak'), C['amarillo'], C['noche'])]
        if s.get('spotter'): chips.append((S('chip_spot'), C['menta'], C['noche']))
        ts, nslow = slowmo_last(s, snap(min(s['dur'], 8) + 3.0))
        render(s, (ex(s['exercise'], short=True), f"{s['start'][:5]} · {day_label(s['day'])}"), ts, chips=chips, slow_from=nslow)

f = plan['finale']
screen('finale-card', 4 * BEAT, lambda d, lay, img, sec: txt(d, (CX, CY + 40), S('moment'), 'grift', 120, C['blanco'], 'ms') and None)
R = [f['t_in'] + r for r in f['rep_times']]
last = R[-1] if R else f['t_in'] + f['dur'] - 1.5
normal = snap(max(4.0, (last - 1.5) - f['t_in']))
ramp = int(round(snap(1.5 / 0.35) * FPS))
ts = linear(last - 1.5 - normal, normal); nslow = len(ts)
ts += [last - 1.5 + i * 0.35 / FPS for i in range(ramp)]
render(f, (ex(f['exercise']), f"{f['start'][:5]} · {day_label(f['day'])}"), ts, kind='finale', slow_from=nslow)
edl[-1].update({'dramatized': True, 'note': 'record moment is dramatized on the real highest-effort set; no weight is stated'})
DROP_T = now()

# R1: freeze still (navy duotone + dotted veil, clear lens on the client) | medal + title
s2 = wd / 's3db2'; meta2 = json.load(open(s2 / 'meta.json'))
ft = meta2['freeze_t']
cap = cv2.VideoCapture(str(ROOT / 'source' / a.client / f['day'] / 'clips' / f"{f['clip']}.mp4")); cap.set(1, int(round(ft * cap.get(5))))
fimg = deosd(cap.read()[1]); cap.release()
Mf = Masks(wd / 'masks' / f"{f['day']}_{f['clip']}_{f['t_in']:.2f}.npz").at(ft)
ys, xs = np.nonzero(Mf)
bx0, bx1, by0, by1 = np.percentile(xs, 1), np.percentile(xs, 99), np.percentile(ys, 1), np.percentile(ys, 99)
PW, PH = (W, W) if VERT else (1000, H)                          # still panel: top square (9:16) or left (16:9)
pad = 0.06 * max(bx1 - bx0, by1 - by0)
ch = float(np.clip(max(by1 - by0, (bx1 - bx0) * PH / PW) * 2.1, 320, 720)); cw = ch * PW / PH
if cw > 1280: cw, ch = 1280, 1280 * PH / PW
cxx, cyy = (bx0 + bx1) / 2, (by0 + by1) / 2
X0 = int(np.clip(cxx - cw / 2, 0, 1280 - cw)); Y0 = int(np.clip(cyy - ch / 2, 0, 720 - ch))
lens = np.zeros((720, 1280), np.float32)
cv2.rectangle(lens, (int(bx0 - pad), int(by0 - pad)), (int(bx1 + pad), int(by1 + pad)), 1.0, -1)
lens = cv2.GaussianBlur(lens, (0, 0), 1.5)[..., None]
still = (ds.dotted_veil(ds.duotone(fimg), step=10, r=1, alpha=0.55) * (1 - lens) + fimg * lens).astype(np.uint8)
lens_box = ((bx0 - pad - X0) * PW / cw, (by0 - pad - Y0) * PH / ch, (bx1 + pad - X0) * PW / cw, (by1 + pad - Y0) * PH / ch)
if VERT:
    MED, MR, TX = (CX, PH + 220), 120, CX
    Y_NEW, Y_REC, Y_EX, Y_DATE = PH + 470, PH + 580, PH + 650, PH + 705
else:
    MED, MR, TX = (1460, 330), 140, 1460
    Y_NEW, Y_REC, Y_EX, Y_DATE = 640, 760, 850, 905
RW_ = (SAFE_R - SAFE_L) if VERT else (SAFE_R - PW - 60)


def r1_base(sec):
    z = 1 + 0.06 * sec / 4; cw2, ch2 = cw / z, ch / z
    x0 = X0 + (cw - cw2) / 2; y0 = Y0 + (ch - ch2) / 2
    panel = cv2.resize(still[int(y0):int(y0 + ch2), int(x0):int(x0 + cw2)], (PW, PH), interpolation=cv2.INTER_CUBIC)
    img = ds.solid(C['noche']); img[:PH, :PW] = panel
    return img


burst = ds.Burst((MED[0], MED[1] + 40), n=110, spread=(-170, -10), speed=(600, 1400))


def r1_draw(d, lay, img, sec):
    z = 1 + 0.06 * sec / 4
    bx = [(v - c) * z + c for v, c in zip(lens_box, (PW / 2, PH / 2, PW / 2, PH / 2))]
    k = ds.ease(sec / 0.3); g = 8 + 30 * (1 - k)
    ds.corners(d, (max(4, bx[0] - g), max(4, bx[1] - g), min(PW - 4, bx[2] + g), min(PH - 4, bx[3] + g)), C['menta'], L=44, w=6)
    if sec >= 0.25:
        u = (sec - 0.25) / 0.45; y = MED[1] - 500 * (1 - ds.back_out(u, 1.3))
        flip = 2 * math.pi * ds.ease((sec - 0.8) / 0.7) if sec > 0.8 else 0
        shine = (sec - 1.6) / 0.6 if 1.6 <= sec <= 2.2 else -1
        ds.medal(lay, (MED[0], y), MR, flip=flip, shine=shine)
    if sec >= 1.0:
        u = ds.back_out((sec - 1.0) / 0.3)
        txt(d, (TX, Y_NEW), S('new'), 'grift', int(110 * max(0.2, u)), C['blanco'], 'ms', RW_)
    if sec >= 1.5:
        u = ds.back_out((sec - 1.5) / 0.3)
        txt(d, (TX, Y_REC), S('record'), 'grift', int(110 * max(0.2, u)), C['amarillo'], 'ms', RW_)
    if sec >= 2.0:
        txt(d, (TX, Y_EX), ex(f['exercise'], short=True), 'onest', 40, C['bruma'], 'ms', RW_)
        txt(d, (TX, Y_DATE), f"{day_label(f['day'])} · {f['start'][:5]}", 'mono', 30, C['hielo'], 'ms', RW_)
    if sec < 0.2:
        img = cv2.addWeighted(img, sec / 0.2, ds.solid(C['blanco']), 1 - sec / 0.2, 0)
    return burst.draw(img, sec - 0.7)


sfx('impact'); sfx('whoosh', now() + 0.25); sfx('clang', now() + 0.7); sfx('pop', now() + 0.7)
sfx('hit', now() + 1.0); sfx('hit', now() + 1.5); sfx('shine', now() + 1.6)
screen('record-medal', 8 * BEAT, r1_draw, base=r1_base, fade='out', info={'freeze_t': ft, 'dramatized': True})

# R2: stat tiles count up
TILES = [(TOT['reps'], S('reps'), True), (TOT['sets'], S('sets'), False), (TOT['minutes'], S('minutes'), False)]
if VERT:
    TPOS = [(CX - 400, 560 + k * 340, 800, 300) for k in range(3)]; Y_T2, Y_NOTE = 420, 1620
else:
    TPOS = [((W - 3 * 500 - 80) / 2 + k * 540, 360, 500, 340) for k in range(3)]; Y_T2, Y_NOTE = 230, 800


def r2_draw(d, lay, img, sec):
    txt(d, (CX, Y_T2), S('stats_n', n=len(days)) if len(days) > 1 else S('stats_1'), 'grift', 72, C['blanco'], 'ms')
    for k, ((val, lab, hl), (x, y, tw, th)) in enumerate(zip(TILES, TPOS)):
        st = k * BEAT
        if sec < st: continue
        u = ds.ease((sec - st) / 0.3); y = y + 40 * (1 - u)
        d.rounded_rectangle([x, y, x + tw, y + th], 24, fill=ds.with_alpha(C['amarillo'] if hl else C['noche2'], u))
        cnt = int(round(val * ds.ease((sec - st) / 1.2)))
        txt(d, (x + tw / 2, y + th * 0.58), num(cnt), 'grift', 170, ds.with_alpha(C['noche'] if hl else C['blanco'], u), 'ms', tw - 40)
        txt(d, (x + tw / 2, y + th * 0.82), lab, 'onest', 36, ds.with_alpha(C['noche2'] if hl else C['hielo'], u), 'ms', tw - 40)
    if sec >= 3 * BEAT + 1.2:
        txt(d, (CX, Y_NOTE), S('counted'), 'onest', 32, C['hielo'], 'ms')


t2 = now()
for k in range(3):
    for j in range(12): sfx('tick', t2 + k * BEAT + j * 0.1)
    sfx('ding', t2 + k * BEAT + 1.2)
screen('record-stats', 8 * BEAT, r2_draw, info={'values': TILES})

# R3: streak (ERP visit days; nothing is said about other days)
Y_FL, Y_ST, Y_PL = (640, 980, 1140) if VERT else (300, 610, 760)


def r3_draw(d, lay, img, sec):
    u = ds.back_out(sec / 0.4)
    if sec > 0:
        ds.icon(d, 'flame', (CX, Y_FL), 150 * max(0.05, u), C['amarillo'], hole=C['noche'])
    txt(d, (CX, Y_ST), S('streak_n', n=streak) if streak > 1 else S('streak_1'), 'grift', 110, C['blanco'], 'ms')
    pw, gap = 260, 32; x0 = CX - (len(DAYP) * pw + (len(DAYP) - 1) * gap) / 2
    for k, lab in enumerate(DAYP):
        on = sec >= (k + 1) * BEAT; v = ds.back_out((sec - (k + 1) * BEAT) / 0.3) if on else 0
        s_ = 1 + 0.08 * (1 - min(1, v)) if on else 1
        cx = x0 + k * (pw + gap) + pw / 2
        d.rounded_rectangle([cx - pw / 2 * s_, Y_PL - 46 * s_, cx + pw / 2 * s_, Y_PL + 46 * s_], 999, fill=C['amarillo'] if on else C['noche2'])
        txt(d, (cx, Y_PL), lab, 'onest5', 36, C['noche'] if on else C['hielo'], 'mm', pw - 30)


t3 = now()
for k in range(len(DAYP)): sfx('pluck%d' % k, t3 + (k + 1) * BEAT)
screen('record-streak', (len(DAYP) + 5) * BEAT, r3_draw, info={'streak_days': streak, 'days': DAYP})


# R4: badges, one per beat
def r4_draw(d, lay, img, sec):
    nb = len(BADGES)
    txt(d, (CX, 380 if VERT else 210), S('badges'), 'grift', 72, C['blanco'], 'ms')
    for k, (ic, title, detail) in enumerate(BADGES):
        st = (k + 1) * BEAT
        if VERT:
            x, y, r0 = SAFE_L + 140, 600 + k * 300, 110; tx, tmax = SAFE_L + 300, SAFE_R - SAFE_L - 300
        else:
            sp = min(480, (SAFE_R - SAFE_L) / nb); x, y, r0 = CX + (k - (nb - 1) / 2) * sp, 470, 120; tmax = sp - 30
        if sec < st:
            d.ellipse([x - r0, y - r0, x + r0, y + r0], outline=C['noche2'], width=6); continue
        u = ds.back_out((sec - st) / 0.35); r = r0 * u
        d.ellipse([x - r, y - r, x + r, y + r], fill=C['noche2'], outline=C['menta'], width=8)
        ds.icon(d, ic, (x, y), r0 * 0.6 * u, C['menta'], hole=C['noche2'])
        al = ds.ease((sec - st - 0.15) / 0.3)
        if al > 0:
            if VERT:
                txt(d, (tx, y - 14), title, 'grift', 56, ds.with_alpha(C['blanco'], al), 'ls', tmax)
                txt(d, (tx, y + 46), detail, 'onest', 36, ds.with_alpha(C['hielo'], al), 'ls', tmax)
            else:
                txt(d, (x, 690), title, 'grift', 50, ds.with_alpha(C['blanco'], al), 'ms', tmax)
                txt(d, (x, 750), detail, 'onest', 32, ds.with_alpha(C['hielo'], al), 'ms', tmax)


t4 = now()
for k in range(len(BADGES)): sfx('badge', t4 + (k + 1) * BEAT)
screen('record-badges', (len(BADGES) + 5) * BEAT, r4_draw, info={'badges': BADGES})

# R5: surprise stat
if longest:
    LV = reps_of(longest)
    Y5 = (620, 1000, 1110, 1190, 1250) if VERT else (270, 600, 700, 770, 820)

    def r5_draw(d, lay, img, sec):
        txt(d, (CX, Y5[0]), S('longest'), 'grift', 72, C['blanco'], 'ms')
        cnt = int(round(LV * ds.ease((sec - 0.3) / 0.8))) if sec > 0.3 else 0
        u = ds.back_out((sec - 1.1) / 0.3) if sec > 1.1 else 0
        txt(d, (CX, Y5[1]), str(cnt), 'grift', int(300 * (1 + 0.06 * (1 - min(1, u)) if u else 1)), C['amarillo'], 'ms')
        txt(d, (CX, Y5[2]), S('in_row'), 'onest', 44, C['bruma'], 'ms')
        txt(d, (CX, Y5[3]), ex(longest['exercise']), 'onest', 36, C['hielo'], 'ms')
        txt(d, (CX, Y5[4]), day_label(longest['day']), 'mono', 30, C['hielo'], 'ms')
    t5 = now()
    for j in range(8): sfx('tick', t5 + 0.3 + j * 0.1)
    sfx('ding', t5 + 1.1)
    screen('record-longest', 6 * BEAT, r5_draw, info={'longest': FACTS['longest_high_conf_set']})

# R6: level bar
LVL = TOT['reps'] // LEVEL_STEP; MAXL = LVL + 1
BX0, BX1 = (SAFE_L + 70, SAFE_R - 70) if VERT else (260, 1660)
Y6 = (640, 820, 1000, 1180, 1250) if VERT else (200, 400, 560, 760, 830)


def r6_draw(d, lay, img, sec):
    fill = TOT['reps'] * ds.ease((sec - 0.3) / 2.2) if sec > 0.3 else 0
    cur = int(fill // LEVEL_STEP)
    txt(d, (CX, Y6[0]), S('level_t'), 'grift', 64, C['blanco'], 'ms')
    if cur:
        u = ds.back_out((fill - cur * LEVEL_STEP) / TOT['reps'] * 2.2 / 0.25)
        txt(d, (CX, Y6[1]), S('level', n=cur), 'grift', int(140 * (1 + 0.08 * (1 - min(1, u)))), C['amarillo'], 'ms')
    by = Y6[2]
    d.rounded_rectangle([BX0, by - 24, BX1, by + 24], 24, fill=C['noche2'])
    fx = BX0 + (BX1 - BX0) * fill / (MAXL * LEVEL_STEP)
    if fx > BX0 + 48: d.rounded_rectangle([BX0, by - 24, fx, by + 24], 24, fill=C['menta'])
    for k in range(1, MAXL + 1):
        x = BX0 + (BX1 - BX0) * k / MAXL; on = fill >= k * LEVEL_STEP
        d.ellipse([x - 18, by - 18, x + 18, by + 18], fill=C['amarillo'] if on else C['noche'], outline=C['amarillo'] if on else C['blanco'], width=4)
        txt(d, (x, by + 80), S('level', n=k), 'mono', 26, C['blanco'] if on else C['hielo'], 'ms', (BX1 - BX0) / MAXL - 10)
    if sec > 2.7:
        al = ds.ease((sec - 2.7) / 0.3)
        txt(d, (CX, Y6[3]), S('to_next', r=(LVL + 1) * LEVEL_STEP - TOT['reps'], n=LVL + 1), 'onest', 40, ds.with_alpha(C['bruma'], al), 'ms')
        txt(d, (CX, Y6[4]), S('rule', s=LEVEL_STEP), 'mono', 26, ds.with_alpha(C['hielo'], al), 'ms')


t6 = now()
grid = np.linspace(0, 1, 2001); ev = np.array([ds.ease(g) for g in grid])
for k in range(1, LVL + 1):
    g = grid[min(len(grid) - 1, np.searchsorted(ev, k * LEVEL_STEP / TOT['reps']))]; sfx('level', t6 + 0.3 + 2.2 * g)
sfx('fanfare', t6 + 2.6)
screen('record-level', 8 * BEAT, r6_draw, info={'level': LVL, 'rule': FACTS['level_rule']})

# 3D replay
rl = sorted(s2.glob('rl_*.png')); st = sorted(s2.glob('st_*.png'))
seg('3d-replay'); n = nframes(max(len(st) / 15, 6.0)); t0 = now()


def fitpanel(p, w, h, top_room=False):
    im = cv2.imread(str(p)); s_ = max(w / im.shape[1], h / im.shape[0])
    im = cv2.resize(im, (int(round(im.shape[1] * s_)), int(round(im.shape[0] * s_))), interpolation=cv2.INTER_CUBIC)
    y0 = 0 if top_room else (im.shape[0] - h) // 2; x0 = (im.shape[1] - w) // 2   # top_room: keep the headroom, crop the floor
    return im[y0:y0 + h, x0:x0 + w]


for i in range(n):
    j = min(len(st) - 1, int(i * len(st) / n))
    if VERT:
        img = np.vstack([fitpanel(rl[j], W, H // 2), fitpanel(st[j], W, H // 2, top_room=meta2.get('props') == 'dumbbells')])
    else:
        img = np.hstack([fitpanel(rl[j], W // 2, H), fitpanel(st[j], W // 2, H)])
    lay = ds.layer(); d = ImageDraw.Draw(lay)
    if VERT:
        d.rectangle([0, H // 2 - 2, W, H // 2 + 1], fill=C['menta'])
        chip(d, SAFE_L, SAFE_T, S('real'), C['noche'], C['blanco'])
        cx_, cy_ = SAFE_L, H // 2 + 40
    else:
        d.rectangle([W // 2 - 2, 0, W // 2 + 1, H], fill=C['menta'])
        chip(d, SAFE_L, SAFE_T, S('real'), C['noche'], C['blanco'])
        cx_, cy_ = W // 2 + 40, SAFE_T
    cwid = chip(d, cx_, cy_, S('replay'), C['amarillo'], C['noche'])
    note = S('note_' + meta2.get('props', 'bench_bar'))                         # beside the chip, never over the body
    txt(d, (cx_ + cwid + 20, cy_ + 28), note, 'mono', 24, C['bruma'], 'lm', SAFE_R - (cx_ + cwid + 20))
    put(ds.fade_to(ds.compose(img, lay), C['noche'], ds.ease(min(1.0, (i + 1) / 5, (n - i) / 5))))
edl.append({'t': round(t0, 2), 'dur': n / FPS, 'kind': '3d-replay', 'frames': len(st), 'stability': meta2.get('stability')})


def end_draw(d, lay, img, sec):
    ds.corners(d, (CX - BOXW / 2, CY - 260, CX + BOXW / 2, CY + 140), C['menta'], L=56, w=6)
    txt(d, (CX, CY - 60), name, 'grift', 160, C['blanco'], 'ms', BOXW - 80)
    txt(d, (CX, CY + 50), S('title_sub', span=span), 'onest', 44, C['hielo'], 'ms', BOXW - 60)
    yl = CY + (480 if VERT else 360)
    ds.text(d, (CX - 20, yl), S('made_with'), 'onest', 30, C['hielo'], 'rm')
    ds.logo(lay, (CX + 10, yl), 200, 'negative', anchor='lm')


screen('end', 8 * BEAT, end_draw)
enc.stdin.close(); enc.wait()
total = now()

# ------------------------------------------------------------------ audio
music = out_dir / f'{stem}.music.wav'
subprocess.run([sys.executable, str(ROOT / 'make_music.py'), str(music), f'{total + 0.5:.2f}', '--bpm', str(a.bpm),
                '--drop', f'{DROP_T:.3f}'], check=True, capture_output=True)
nS = int((total + 0.5) * SR); fxw = np.zeros(nS, np.float32); rng = np.random.default_rng(3)


def tone(freqs, dur, decay, amp, attack=0.003):
    t = np.arange(int(dur * SR)) / SR
    s = sum(np.sin(2 * np.pi * fq * t) * (0.6 ** k) for k, fq in enumerate(freqs))
    return (s * np.minimum(1, t / attack) * np.exp(-t / decay) * amp).astype(np.float32)


NOTE = lambda m: 440 * 2 ** ((m - 69) / 12)
BANK = {'tick': tone([2400], 0.03, 0.008, 0.12), 'ding': tone([NOTE(88), NOTE(95)], 0.6, 0.18, 0.22),
        'badge': tone([NOTE(84), NOTE(91), NOTE(96)], 0.7, 0.22, 0.22),
        'clang': tone([523, 1347, 2113, 2950], 1.2, 0.35, 0.2), 'shine': tone([NOTE(100)], 0.5, 0.15, 0.08),
        'hit': tone([NOTE(43), NOTE(55)], 0.4, 0.12, 0.35), 'impact': tone([40, 80], 1.2, 0.4, 0.5),
        'fanfare': np.concatenate([tone([NOTE(m)], 0.12, 0.2, 0.2)[:int(0.11 * SR)] for m in (72, 76, 79)] + [tone([NOTE(84), NOTE(88)], 0.9, 0.35, 0.25)]),
        'level': tone([NOTE(79), NOTE(86)], 0.5, 0.15, 0.2)}
for k in range(6): BANK[f'pluck{k}'] = tone([NOTE(72 + [0, 4, 7, 12, 16, 19][k])], 0.5, 0.18, 0.25)
wn = rng.standard_normal(int(0.45 * SR)).astype(np.float32); wt = np.arange(len(wn)) / SR
BANK['whoosh'] = (np.convolve(wn, np.ones(40) / 40, 'same') * np.sin(np.pi * wt / wt[-1]) * 0.25).astype(np.float32)
pn = rng.standard_normal(int(0.25 * SR)).astype(np.float32); BANK['pop'] = (pn * np.exp(-np.arange(len(pn)) / SR / 0.03) * 0.3).astype(np.float32)
last_tick = -1
for t_, k in sorted(SFX):
    if k == 'tick':
        if t_ - last_tick < 0.06: continue
        last_tick = t_
    s = BANK[k]; i = int(t_ * SR); j = min(nS, i + len(s))
    if i < nS: fxw[i:j] += s[:j - i]
sfx_path = out_dir / f'{stem}.sfx.wav'; sf.write(sfx_path, fxw, SR)
final = out_dir / f'{stem}.mp4'
subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-y', '-i', str(vid), '-i', str(music), '-i', str(sfx_path), '-filter_complex',
                '[1:a]volume=0.8[m];[2:a]volume=1.0[s];[m][s]amix=inputs=2:normalize=0,alimiter=limit=0.7:level=false[a]', '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(final)], check=True)
vid.unlink()
beats = np.array(json.load(open(str(music)[:-4] + '.beats.json'))['beats'])
cuts = np.array([e['t'] for e in edl[1:]]); err = np.array([np.min(np.abs(beats - c)) for c in cuts])
train = [e for e in edl if e['kind'] in ('set', 'peak', 'finale')]
audit = {'video': final.name, 'lang': L, 'aspect': a.aspect, 'canvas': [W, H], 'duration_s': round(total, 2), 'segments': len(edl),
         'training_shots': len(train), 'share_real_sets': round(sum(1 for e in train if e['pose_reps_in_shot'] >= 3) / max(1, len(train)), 3),
         'cuts_on_beat_median_err_s': round(float(np.median(err)), 3), 'cuts_on_beat_max_err_s': round(float(err.max()), 3),
         'drop_t': round(DROP_T, 2), 'facts': FACTS, 'sfx_events': len(SFX), 'skipped_shots': SKIPPED, 'slow_rep_overrides': SLOW_REP,
         'design_system': 'rikuy.si/design-system v2.1.0 (ds.py)', 'privacy': 'background not blurred (user request): bystanders are visible'}
json.dump(edl, open(out_dir / f'{stem}.edl.json', 'w'), indent=1, ensure_ascii=False)
json.dump(audit, open(out_dir / f'{stem}.audit.json', 'w'), indent=1, ensure_ascii=False)
json.dump([{'segment': k[0], 'text': k[1], 'box': v} for k, v in ds.LOG.items()], open(out_dir / f'{stem}.texts.json', 'w'), indent=1, ensure_ascii=False)
print(final, json.dumps({k: audit[k] for k in ('duration_s', 'share_real_sets', 'cuts_on_beat_max_err_s', 'skipped_shots', 'drop_t')}, ensure_ascii=False))
