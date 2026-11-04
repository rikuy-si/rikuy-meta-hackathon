#!/usr/bin/env python3
"""Build EnPiso Visión v0.1.3 (client-facing dashboard + video, Spanish and English) into a flat, self-contained static bundle.

    python3 build.py                 # -> dist/ (index.html, app.js, app-data.json, fonts, logos, proof stills, pose data)
    python3 build.py --skip-media    # reuse cached stills (faster; needs a previous full build)
    python3 build.py --blur-faces    # placeholder: fails on purpose (future work, see README)

Inputs are read only, never modified:
  - enpiso/video-review/media/vision-analysis/web/v003/zoe-v003.json   cycles, lanes, KPIs, CP rows, zones
  - enpiso/video-review/media/vision-analysis/analysis/v003-cp-alignment-rows.json   per-capture keypad residuals
  - enpiso/video-review/media/vision-analysis/web/pose-recNN.json      pose (compacted to body joints, uint16)
  - enpiso/video-review/full-playlist-public.json                      public R2 video URLs (reused, not re-uploaded)
  - enpiso/video-review/media/full-playlist-v1/*.mp4                   local recordings, only to cut proof stills (ffmpeg, CPU)
  - poc-enpiso-zoe-v0.0.5/ficha-tecnica/{ficha-tecnica,simulation}.json   mock technical sheet (labelled "ejemplo")
  - context/                                                           Rikuy fonts and logos, EnPiso logo and favicon
  - src/i18n/{es,en}.json                                              UI string catalog (inlined; ES also fills the HTML)

Every generated client string is a bilingual {'es': ..., 'en': ...} pair in app-data.json; the page picks one at runtime.

The bundle is flat (every file at the top level of dist/, unique names) so it uploads as-is to one static prefix.
Names, employee codes and client names never enter the bundle: the build strips them and then scans every output file.
"""
import argparse, datetime, os, hashlib, json, pathlib, re, shutil, subprocess, sys, zipfile
from array import array

sys.dont_write_bytecode = True
VERSION = '0.1.3'
H = pathlib.Path(__file__).resolve().parent
EXP = H.parent
VR = EXP / 'enpiso/video-review'
WEB = VR / 'media/vision-analysis/web'
ANALYSIS = VR / 'media/vision-analysis/analysis'
LOCAL_VIDEO = VR / 'media/full-playlist-v1'
FICHA = EXP / 'poc-enpiso-zoe-v0.0.5/ficha-tecnica'
CTX = H / 'context'
SRC = H / 'src'
CACHE = H / '.build-cache'

WINDOW_END = 5760          # A and B leave about 14:45 plant time; analysis covers 0..5760 s of the playlist
SAM_MIN = 3.8              # CP SAM of [PRODUCT], all in Confección
OPERATORS = 2              # module 28 headcount seen on video and in CP; an assumption for efficiency
JS_ORDER = ['core.js', 'i18n.js', 'player.js', 'timeline.js', 'overlays.js', 'dashboard.js', 'app.js']
BODY = 65                  # all RTMW keypoints kept: 17 body, 6 feet, 2x21 hand (fingers)
MIN_SCORE = 3              # same threshold as the v0.0.1 overlay (vision-core.js)
# Text that must never ship: names and codes of people, a client name, plus words the client copy must not use.
_PII_FILE = pathlib.Path(os.environ.get('PII_PATTERNS', H / 'private/pii.json'))  # private: names, ids
PII = (json.loads(_PII_FILE.read_text()) if _PII_FILE.exists() else []) + [r'Worker-\d', r'identit']
BANNED = [r'vigil', r'castig', r'monitore', r'esp[ií]a[rn ]', r'sanci[oó]n', r'surveil', r'big brother', '\u2014', '\u2013',
          # English copy: no surveillance or punishment words (the code avoids them too, e.g. Overlays.follow)
          r'monitor', r'\bwatch', r'punish', r'\bspy', r'spying', r'sanction', r'disciplin', r'penal', r'snoop', r'\bpolic(e|ing)\b']
LANGS = ('es', 'en')

ROI_TABLE = (210, 240, 900, 570)   # A's table, the queue, B's overlock and the CP keypad (source pixels, 1440x810)
ROI_B = (560, 240, 600, 380)       # B's station and the CP keypad


# ---------------------------------------------------------------- helpers
def es(x, d=1):
    """Spanish decimal comma; drops a trailing ,0."""
    s = f'{x:.{d}f}'.replace('.', ',')
    return s[:-2] if s.endswith(',0') else s


def en(x, d=1):
    """English decimal point; drops a trailing .0."""
    s = f'{x:.{d}f}'
    return s[:-2] if s.endswith('.0') else s


def pct(x, lang='es'):
    return f'{round(x)}\u00a0%' if lang == 'es' else f'{round(x)}%'


def L(es_text, en_text):
    """A bilingual client string."""
    return {'es': es_text, 'en': en_text}


def hms(sec):
    sec = int(round(sec)) % 86400
    return f'{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}'


def secs(clock):
    h, m, s = (int(v) for v in clock.split(':'))
    return h * 3600 + m * 60 + s


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Playlist:
    def __init__(self, full, offset):
        self.offset = offset
        self.recs = []
        for r in full['recordings']:
            if r['timelineStart'] >= WINDOW_END:
                break
            cam = r['cameraStart'][11:19]
            self.recs.append({'id': r['id'], 'file': r['file'], 'url': r['url'], 'start': round(r['timelineStart'], 6),
                              'duration': round(r['duration'], 6), 'cameraStart': cam, 'plantStart': hms(secs(cam) - offset)})
        assert len(self.recs) == 6 and all(r['url'].startswith('<VE_PUBLIC_URL>/') for r in self.recs)

    def locate(self, t):
        for r in reversed(self.recs):
            if t >= r['start']:
                return r, t - r['start']
        return self.recs[0], 0.0

    def plant(self, t):
        r, off = self.locate(t)
        return hms(secs(r['plantStart']) + off)


# ---------------------------------------------------------------- data
def load_inputs():
    z = json.loads((WEB / 'v003/zoe-v003.json').read_text())
    assert z['version'] == '0.0.3' and len(z['cycles']) == 45 and len(z['cp']) == 178 and z['module']['id'] == 28
    rows = json.loads((ANALYSIS / 'v003-cp-alignment-rows.json').read_text())['rows']
    full = json.loads((VR / 'full-playlist-public.json').read_text())
    ficha = json.loads((FICHA / 'ficha-tecnica.json').read_text())
    sim = json.loads((FICHA / 'simulation.json').read_text())
    return z, rows, full, ficha, sim


def hourly(z):
    """CP pieces per plant hour for the module product; efficiency = pieces x SAM / (operators x 60 min)."""
    rows = [r for r in z['cp'] if r['product'] == '[PRODUCT]']
    by = {}
    for r in rows:
        by.setdefault(int(r['cp'][:2]), []).append(r)
    first = min(secs(r['cp']) for r in rows if (r['quantity'] or 0) > 0)
    last = max(secs(r['cp']) for r in rows)
    out = []
    for h in sorted(by):
        rs = sorted(by[h], key=lambda r: r['cp'])
        pieces = sum(r['quantity'] or 0 for r in rs)
        times = [secs(r['cp']) for r in rs if (r['quantity'] or 0) > 0]
        flags, notes = [], []
        if h * 3600 <= first < (h + 1) * 3600:
            s0 = hms(min(secs(r['cp']) for r in rs))[:5]
            flags.append('partial'); notes.append(L(f'Hora incompleta: el turno arrancó a las {s0} y la primera pieza se registró a las {hms(first)[:5]}.',
                                                   f'Partial hour: the shift started at {s0} and the first piece was captured at {hms(first)[:5]}.'))
        if h * 3600 <= last < (h + 1) * 3600 and last < (h + 1) * 3600 - 600:
            flags.append('partial'); notes.append(L(f'Hora incompleta: el módulo terminó hacia las {hms(last)[:5]}.', f'Partial hour: the module finished around {hms(last)[:5]}.'))
        pauses = [r['cp'][:5] for r in rs if r['event'] == 'Pausa']
        if pauses:
            flags.append('pause'); notes.append(L(f'Incluye una pausa registrada en CP a las {", ".join(pauses)}.', f'Includes a break logged in CP at {", ".join(pauses)}.'))
        # Burst: 5 or more pieces registered within 30 s, which a two-person module cannot sew.
        best = (0, 0)
        for i, t in enumerate(times):
            n = sum(1 for u in times[i:] if u - t <= 30)
            if n > best[0]:
                best = (n, t)
        if best[0] >= 5:
            span = max(u for u in times if best[1] <= u <= best[1] + 30) - best[1]
            flags.append('burst'); notes.append(L(f'A las {hms(best[1])[:5]} se registraron {best[0]} piezas en {span} s: probablemente piezas de la hora anterior marcadas tarde.',
                                                 f'At {hms(best[1])[:5]}, {best[0]} pieces were captured in {span} s: most likely pieces from the hour before, keyed in late.'))
        gaps = [(b - a, a, b) for a, b in zip(times, times[1:])]
        if times and times[0] - h * 3600 >= 900 and h * 3600 > first:
            gaps.append((times[0] - h * 3600, h * 3600, times[0]))
        g = max(gaps, default=(0, 0, 0))
        if g[0] >= 900:
            flags.append('gap'); notes.append(L(f'Sin registros entre las {hms(g[1])[:5]} y las {hms(g[2])[:5]}.', f'No captures between {hms(g[1])[:5]} and {hms(g[2])[:5]}.'))
        eff = pieces * SAM_MIN / (OPERATORS * 60) * 100
        out.append({'hour': h, 'label': f'{h:02d}:00', 'pieces': int(pieces), 'eff': round(eff, 1), 'flags': sorted(set(flags)), 'notes': notes})
    assert [r['pieces'] for r in out] == [13, 18, 18, 10, 10, 41, 20, 23, 14], [r['pieces'] for r in out]
    total = sum(r['pieces'] for r in out)
    avg = total * SAM_MIN / (OPERATORS * 60 * len(out)) * 100
    return out, total, avg


def lanes(z):
    codes = {'work': 'cose', 'pickup': 'busca', 'deposit': 'entrega', 'wait': 'espera', 'to_queue': 'busca', 'absent': 'fuera', 'unassigned': 'nd'}
    acodes = {'seat': 'puesto', 'up': 'pie', 'absent': 'fuera'}
    B = [[s, e, codes[st]] for s, e, st in z['lanes']['B']]
    A = [[s, e, acodes[st]] for s, e, st in z['lanes']['A']]
    Q = [[s, e] for s, e, v in z['lanes']['queue'] if v]
    return {'B': B, 'A': A, 'queue': Q}


def build_data(z, rows, full, ficha, sim):
    pl = Playlist(full, z['clock']['offsetSeconds'])
    k = z['kpis']
    hours, total, avg = hourly(z)
    by_t = {r['t']: r for r in rows}
    caps = []
    for f in z['cp']:
        if f['abOnVideo'] and (f['quantity'] or 0) > 0 and f['timeline'] is not None:
            r = by_t.get(f['timeline'], {})
            caps.append({'id': f'R{len(caps) + 1:02d}', 't': f['timeline'], 'plant': f['cp'], 'keypad': r.get('keypad'), 'cycle': r.get('cycle')})
    assert len(caps) == 35
    cycles = []
    for c in z['cycles']:
        cycles.append({'n': c['n'], 'start': c['handoff_start'], 'back': c['handoff_end'], 'deposit': c['b_deposit'], 'end': c['next_handoff'] or WINDOW_END,
                       'work': c['b_work'], 'cycle': c['b_cycle'], 'queue': c['queue_dwell'], 'wait': c['b_wait'], 'clean': c['confidence'] == 'medium',
                       'cp': [m['timeline'] for m in c['cpMarks']], 'plant': pl.plant(c['handoff_start'])})
    assert sum(c['clean'] for c in cycles) == k['cycles_clean'] == 19
    L_ = lanes(z)
    waits = [{'s': s, 'e': e} for s, e, st in L_['B'] if st == 'espera']
    queue_eps = [{'s': s, 'e': e} for s, e in L_['queue'] if e - s >= 30]
    no_cp = [c for c in cycles if not c['cp']]
    no_cp_clean = [c for c in no_cp if c['clean']]
    longest = max((c for c in cycles if c['clean']), key=lambda c: c['cycle'])
    assert round(longest['cycle'] / k['b_cycle']['median']) == 3  # the copy says "tres veces la mediana"
    window_min = WINDOW_END / 60
    ts = k['b_time_share']
    b_time = [
        {'key': 'cose', 'label': L('Cosiendo', 'Sewing'), 'share': ts['work']},
        {'key': 'busca', 'label': L('Buscando la pieza', 'Getting the piece'), 'share': ts['pickup'] + ts['to_queue']},
        {'key': 'entrega', 'label': L('Entregando la pieza', 'Handing off the piece'), 'share': ts['deposit']},
        {'key': 'espera', 'label': L('Esperando pieza', 'Waiting for a piece'), 'share': ts['wait']},
        {'key': 'fuera', 'label': L('Fuera de cámara', 'Off camera'), 'share': ts['absent'] + ts['unassigned']},
    ]
    for b in b_time:
        b['min'] = round(b['share'] * window_min, 1)
    a_ts = k['a_time_share']
    a_time = [{'key': 'puesto', 'label': L('En su puesto', 'At the station'), 'share': a_ts['seat']}, {'key': 'pie', 'label': L('De pie', 'Standing'), 'share': a_ts['up']},
              {'key': 'fuera', 'label': L('Fuera de cámara', 'Off camera'), 'share': a_ts['absent']}]
    for a in a_time:
        a['min'] = round(a['share'] * window_min, 1)
    kp = z['cpAlignment']['keypad']
    best = max((r for r in hours if 'burst' not in r['flags']), key=lambda r: r['eff'])
    low = min(r['eff'] for r in hours)
    worst = [r for r in hours if r['eff'] == low]
    sew_rate = 3600 / k['b_work']['median']
    cyc_rate = 3600 / k['b_cycle']['median']
    plant_start, plant_end = pl.plant(0), pl.plant(WINDOW_END)

    def frame(t, roi, caption, alt):
        return {'t': t, 'roi': roi, 'caption': caption, 'alt': alt, 'plant': pl.plant(t)}

    burst_notes = [L(f'{r["label"]}: {n["es"]}', f'{r["label"]}: {n["en"]}') for r in hours if 'burst' in r['flags'] for n in r['notes'] if 'piezas en' in n['es']]
    q_med, w_med, c_med = round(k['queue_dwell']['median']), round(k['b_wait']['median']), round(k['b_cycle']['median'])
    win = round(window_min)
    worst_es, worst_en = ' y '.join(r['label'] for r in worst), ' and '.join(r['label'] for r in worst)
    hit, n_kp, gap_s, chance = kp['n_with_B_hand_within_15s'], kp['n'], abs(kp['median_residual_s']), round(kp['null_fraction'] * 100)
    insights = [
        {'id': 'restriccion', 'kind': 'top', 'rank': 1,
         'headline': L('El Puesto B marca el ritmo del módulo', 'Station B sets the pace for the module'),
         'number': f'{c_med}', 'unit': 's', 'numberLabel': L('por pieza en el Puesto B', 'per piece at Station B'),
         'context': L(f'Las piezas lo esperan en la cola unos {q_med} s. El Puesto B espera pieza solo {w_med} s.',
                      f'Pieces wait about {q_med} s for it in the queue. Station B waits only {w_med} s for a piece.'),
         'source': {'kind': 'video', 'label': 'Video', 'detail': L(f'{k["cycles_clean"]} ciclos claros de {k["cycles_detected"]}', f'{k["cycles_clean"]} clear cycles out of {k["cycles_detected"]}')},
         'confidence': {'level': 'media', 'note': L('Media para el Puesto B. Baja para la cola, que a ratos el Puesto A tapa con los brazos.',
                                                    'Medium for Station B. Low for the queue, which Station A’s arms sometimes hide.')},
         'moment': {'t': 2455, 'clip': [2455, 2530]},
         'proof': [frame(2470, ROI_TABLE, L('Hay piezas en la cola', 'Pieces in the queue'),
                         L('Piezas blancas esperan en la mesa del Puesto A mientras el Puesto B cose', 'White pieces wait on Station A’s table while Station B sews')),
                   frame(2500, ROI_TABLE, L('El Puesto B sigue cosiendo', 'Station B is still sewing'),
                         L('El Puesto B sigue cosiendo la pieza anterior; las piezas siguen en la mesa', 'Station B is still sewing the previous piece; the pieces are still on the table')),
                   frame(2518, ROI_TABLE, L('Toma la siguiente', 'Takes the next one'),
                         L('El Puesto B va a la mesa del Puesto A y toma la siguiente pieza', 'Station B goes to Station A’s table and takes the next piece'))],
         'method': L('Con la cámara medimos cada ciclo del Puesto B: ir por la pieza a la mesa del Puesto A, volver, coser y entregar. Luego comparamos cuánto espera la pieza en la cola con cuánto espera el Puesto B. Si la pieza espera más, quien pone el ritmo es el Puesto B.',
                     'With the camera we timed every Station B cycle: going to Station A’s table for the piece, coming back, sewing and handing it off. Then we compared how long the piece waits in the queue with how long Station B waits. If the piece waits longer, Station B is the one setting the pace.'),
         'caveats': [L(f'Es una tarde de grabación ({win} minutos), no un estudio de tiempos.', f'This is one afternoon of video ({win} minutes), not a time study.'),
                     L('Las esperas en la cola son aproximadas: desde este ángulo la cola se ve a ratos.', 'Queue waits are approximate: from this angle the queue is only visible part of the time.')],
         'idea': L('Pasar una parte del trabajo del Puesto B al Puesto A podría subir las piezas por hora del módulo. Vale la pena probarlo con la ficha técnica en mano.',
                   'Moving part of Station B’s work to Station A could raise the module’s pieces per hour. It is worth trying with the technical sheet in hand.')},
        {'id': 'eficiencia-hora', 'kind': 'top', 'rank': 2,
         'headline': L('La eficiencia del módulo cambió mucho durante el día', 'Module efficiency swung a lot during the day'),
         'number': f'{round(avg)}', 'unit': '%', 'numberLabel': L(f'promedio de las {len(hours)} horas', f'average over the {len(hours)} hours'),
         'context': L(f'La mejor hora fue las {best["label"]} con {pct(best["eff"])}. Las más bajas, {worst_es} con {pct(low)}.',
                      f'The best hour was {best["label"]} at {pct(best["eff"], "en")}. The lowest were {worst_en} at {pct(low, "en")}.'),
         'source': {'kind': 'cp', 'label': 'CP (EnPiso)', 'detail': L(f'{total} piezas registradas en el día', f'{total} pieces captured during the day')},
         'confidence': {'level': 'media', 'note': L('Las piezas vienen de CP. La eficiencia supone 2 personas y que el SAM de CP cubre solo costura.',
                                                    'The pieces come from CP. Efficiency assumes 2 people and that the CP SAM covers sewing only.')},
         'moment': {'t': 50, 'clip': [50, 72]},
         'proof': [frame(caps[0]['t'] - 1, ROI_B, L('Registra una pieza', 'Keys in a piece'), L('El Puesto B marca una pieza en el teclado CP', 'Station B keys in a piece on the CP keypad')),
                   frame(caps[1]['t'] - 1, ROI_B, L('Registra la siguiente', 'Keys in the next one'), L('El Puesto B marca otra pieza en el teclado CP', 'Station B keys in another piece on the CP keypad')),
                   frame(caps[2]['t'] - 1, ROI_B, L('Y la siguiente', 'And the next'), L('El Puesto B marca una tercera pieza en el teclado CP', 'Station B keys in a third piece on the CP keypad'))],
         'method': L(f'Eficiencia de cada hora = piezas registradas en CP × SAM de la camiseta ({es(SAM_MIN)} min) ÷ minutos disponibles ({OPERATORS} personas × 60 min). En video se ven las horas 13:00 y 14:00.',
                     f'Efficiency for each hour = pieces captured in CP × T-shirt SAM ({en(SAM_MIN)} min) ÷ available minutes ({OPERATORS} people × 60 min). The video covers the 13:00 and 14:00 hours.'),
         'caveats': burst_notes + [L('06:00 y 14:00 son horas incompletas; 09:00 y 12:00 tienen pausa registrada.', '06:00 and 14:00 are partial hours; 09:00 and 12:00 have a break logged.'),
                                   L('Si el módulo tuvo otra cantidad de personas, el resultado cambia.', 'If the module had a different number of people, the result changes.')],
         'idea': L('Revisar con la supervisora qué pasó entre las 09:00 y las 11:00, cuando bajaron los registros.',
                   'Go over with the supervisor what happened between 09:00 and 11:00, when captures dropped.')},
        {'id': 'minutos', 'kind': 'top', 'rank': 3,
         'headline': L(f'El Puesto B cosió {round(b_time[0]["min"])} de {win} minutos y casi no esperó', f'Station B sewed {round(b_time[0]["min"])} of {win} minutes and barely waited'),
         'number': f'{round(ts["work"] * 100)}', 'unit': '%', 'numberLabel': L('del tiempo grabado, cosiendo', 'of the recorded time, sewing'),
         'context': L(f'Esperó pieza solo {es(b_time[3]["min"])} min. Lo que no cose se va sobre todo en ir por la pieza: {round(b_time[1]["min"])} min.',
                      f'It waited for a piece only {en(b_time[3]["min"])} min. Most of its time away from sewing went to getting the piece: {round(b_time[1]["min"])} min.'),
         'source': {'kind': 'video', 'label': 'Video', 'detail': L(f'{win} min grabados, de {plant_start[:5]} a {plant_end[:5]}', f'{win} min recorded, {plant_start[:5]} to {plant_end[:5]}')},
         'confidence': {'level': 'media', 'note': L('Cada segundo se clasifica por postura y posición. Error típico de unos 2 s por evento.',
                                                    'Every second is classified by posture and position. Typical error is about 2 s per event.')},
         'moment': {'t': 1378, 'clip': [1378, 1440]},
         'proof': [frame(1386, ROI_TABLE, L('Va por la pieza', 'Goes for the piece'), L('El Puesto B camina hasta la mesa del Puesto A', 'Station B walks over to Station A’s table')),
                   frame(1397, ROI_TABLE, L('Vuelve y la registra', 'Comes back and keys it in'), L('El Puesto B vuelve a su máquina con la pieza', 'Station B returns to its machine with the piece')),
                   frame(1425, ROI_TABLE, L('Cose', 'Sews'), L('El Puesto B cose la pieza en la fileteadora', 'Station B sews the piece on the overlock'))],
         'method': L('Clasificamos cada segundo del Puesto B con la postura y la posición que ve la cámara: cosiendo, buscando la pieza, entregándola, esperando pieza o fuera de cámara. Sumamos los minutos de cada estado.',
                     'We classified every second of Station B from the posture and position the camera sees: sewing, getting the piece, handing it off, waiting for a piece, or off camera. Then we added up the minutes in each state.'),
         'caveats': [L('Solo cubre la ventana grabada, no el turno completo.', 'It covers only the recorded window, not the full shift.'),
                     L('El Puesto A se ve peor desde este ángulo: sus minutos tienen confianza baja.', 'Station A is harder to see from this angle: its minutes have low confidence.')],
         'idea': L('Dejar la pieza al alcance del Puesto B podría convertir parte de esos minutos de traslado en costura.',
                   'Keeping the next piece within Station B’s reach could turn part of those walking minutes into sewing.')},
        {'id': 'cp-video', 'kind': 'trust', 'rank': 4,
         'headline': L(f'{hit} de {n_kp} registros de CP se ven en el video', f'{hit} of {n_kp} CP captures show up on the video'),
         'number': f'{hit}/{n_kp}', 'unit': '', 'numberLabel': L('registros que coinciden', 'captures that match'),
         'context': L(f'En cada registro, la mano del Puesto B está en el teclado CP. Diferencia típica: {es(gap_s)} s. Si fuera al azar, coincidirían solo {chance} de cada 100.',
                      f'At each capture, Station B’s hand is on the CP keypad. Typical gap: {en(gap_s)} s. By chance, only {chance} out of 100 would match.'),
         'source': {'kind': 'cp+video', 'label': 'CP + Video', 'detail': L(f'{n_kp} registros del Módulo 28 durante la grabación', f'{n_kp} Module 28 captures during the recording')},
         'confidence': {'level': 'alta', 'note': L('Comprobado registro por registro contra el video.', 'Checked capture by capture against the video.')},
         'moment': {'t': 558, 'clip': [558, 578]},
         'proof': [frame(563, ROI_B, L('Vuelve con la pieza', 'Comes back with the piece'), L('El Puesto B vuelve a su máquina con una pieza', 'Station B returns to its machine with a piece')),
                   frame(566, ROI_B, L('Marca en el teclado', 'Keys it in'), L('El Puesto B marca la pieza en el teclado CP', 'Station B keys in the piece on the CP keypad')),
                   frame(571, ROI_B, L('Empieza a coser', 'Starts sewing'), L('El Puesto B empieza a coser', 'Station B starts sewing'))],
         'method': L('Para cada registro de CP buscamos en el video la mano del Puesto B sobre el teclado, 15 s antes o después. Cada registro llega unos 3 s después de que el Puesto B vuelve con la pieza: CP marca el inicio de la pieza.',
                     'For each CP capture we looked on the video for Station B’s hand on the keypad, within 15 s before or after. Each capture comes about 3 s after Station B gets back with the piece: CP marks the start of the piece.'),
         'caveats': [L('El reloj de la cámara va una hora adelantado; aquí todo está en hora de planta.', 'The camera clock runs one hour ahead; everything here is in plant time.')],
         'idea': ''},
        {'id': 'sin-registro', 'kind': 'review', 'rank': 5,
         'headline': L(f'La cámara vio {len(cycles)} ciclos del Puesto B y CP tiene {len(caps)} registros', f'The camera saw {len(cycles)} Station B cycles and CP has {len(caps)} captures'),
         'number': f'{len(no_cp)}', 'unit': '', 'numberLabel': L('ciclos sin registro en CP', 'cycles with no CP capture'),
         'context': L(f'{len(no_cp) - len(no_cp_clean)} de los {len(no_cp)} son ciclos de confianza baja, a menudo cortes de la detección. '
                      + (f'Un ciclo claro no tiene registro: el de las {no_cp_clean[0]["plant"][:5]}.' if len(no_cp_clean) == 1 else f'{len(no_cp_clean)} ciclos claros no tienen registro.'),
                      f'{len(no_cp) - len(no_cp_clean)} of the {len(no_cp)} are low-confidence cycles, often where the detection split a cycle. '
                      + (f'One clear cycle has no capture: the one at {no_cp_clean[0]["plant"][:5]}.' if len(no_cp_clean) == 1 else f'{len(no_cp_clean)} clear cycles have no capture.')),
         'source': {'kind': 'cp+video', 'label': 'CP + Video', 'detail': L(f'{len(no_cp)} de {len(cycles)} ciclos', f'{len(no_cp)} of {len(cycles)} cycles')},
         'confidence': {'level': 'media', 'note': L('La cámara y CP no cuentan lo mismo: CP marca el inicio de la pieza.', 'The camera and CP do not count the same thing: CP marks the start of the piece.')},
         'moment': {'t': no_cp_clean[0]['start'] - 4, 'clip': [no_cp_clean[0]['start'] - 4, no_cp_clean[0]['back'] + 20]},
         'proof': [], 'method': L('Cruzamos cada ciclo del Puesto B con los registros de CP.', 'We matched each Station B cycle against the CP captures.'), 'caveats': [],
         'idea': L('Revise el ciclo en video y confirme si la pieza se registró.', 'Check the cycle on video and confirm whether the piece was keyed in.')},
        {'id': 'ciclo-largo', 'kind': 'review', 'rank': 6,
         'headline': L(f'El ciclo más largo tomó {longest["cycle"] // 60} min {longest["cycle"] % 60} s', f'The longest cycle took {longest["cycle"] // 60} min {longest["cycle"] % 60} s'),
         'number': f'{longest["cycle"] // 60}:{longest["cycle"] % 60:02d}', 'unit': 'min', 'numberLabel': L(f'ciclo de las {longest["plant"][:5]}', f'cycle at {longest["plant"][:5]}'),
         'context': L(f'Es tres veces la mediana ({c_med} s). Mientras tanto, la pieza siguiente esperó en la cola.',
                      f'That is three times the median ({c_med} s). Meanwhile, the next piece waited in the queue.'),
         'source': {'kind': 'video', 'label': 'Video', 'detail': L(f'Ciclo {longest["n"]}', f'Cycle {longest["n"]}')},
         'confidence': {'level': 'media', 'note': L('El ciclo se ve completo; el motivo hay que verlo en el video.', 'The whole cycle is in view; the video shows why it ran long.')},
         'moment': {'t': longest['start'] - 4, 'clip': [longest['start'] - 4, longest['end'] + 4]},
         'proof': [], 'method': L('Ordenamos los ciclos claros por duración.', 'We sorted the clear cycles by length.'), 'caveats': [],
         'idea': L('Una pieza difícil o un ajuste de máquina se ven aquí: vale la pena mirarlo.', 'A tricky piece or a machine adjustment would show up here: worth a look.')},
    ]
    for i in insights:
        a, b = i['moment']['clip']
        i['moment']['plant'] = [pl.plant(a), pl.plant(b)]

    stations = [
        {'id': 'B', 'name': L('Puesto B', 'Station B'), 'machine': L('Fileteadora', 'Overlock'), 'cycle': k['b_cycle']['median'], 'sew': k['b_work']['median'], 'wait': k['b_wait']['median'],
         'perHourCycle': round(cyc_rate, 1), 'perHourSew': round(sew_rate, 1), 'busy': ts['work'], 'confidence': 'media'},
        {'id': 'A', 'name': L('Puesto A', 'Station A'), 'machine': L('Mesa delantera', 'Front table'), 'cycle': None, 'sew': None, 'wait': None, 'supply': k['a_interval']['median'],
         'busy': a_ts['seat'], 'confidence': 'baja'},
    ]

    # Mock technical sheet (v0.0.5): clearly an example, never plant data.
    ops = ficha['operations']
    sew_ops = sorted((o for o in ops if o['stage'] == 'Confección'), key=lambda o: -o['sam_min'])
    zone_sew = {zn: round(sum(o['sam_min'] for o in sew_ops if o['zone'] == zn), 2) for zn in ('A', 'B')}
    assert abs(sum(zone_sew.values()) - SAM_MIN) < 1e-9 and sim['bottleneck_zone'] == 'B'
    machine_en = {'4-thread overlock': 'Overlock, 4 thread', '2-needle coverstitch': 'Coverstitch, 2 needle', 'Single-needle lockstitch': 'Lockstitch, 1 needle', 'Manual': 'Table, by hand'}
    mock = {
        'label': L('Ejemplo con una ficha técnica simulada. No son datos de su planta.', 'Example built on a simulated technical sheet. This is not data from your plant.'),
        'zones': [{'id': zn, 'name': L(f'Puesto {zn}', f'Station {zn}'), 'sam': sim['zone_sam_min'][zn], 'sec': sim['zone_cycle_sec'][zn], 'sew': zone_sew[zn],
                   'extra': round(sim['zone_sam_min'][zn] - zone_sew[zn], 2)} for zn in ('A', 'B')],
        'takt': round(sim['target_takt_sec'], 1), 'target': sim['target_pieces_per_hour'], 'theoretical': round(sim['theoretical_pieces_per_hour'], 1),
        'balance': round(sim['line_balance_efficiency_pct'], 1), 'minOperators': sim['minimum_operators_at_target_100pct'],
        'ops': [{'id': o['id'], 'name': L(o['name_es'], o['name_en']), 'machine': L(o['machine_es'], machine_en[o['machine']]), 'zone': o['zone'], 'sam': o['sam_min'], 'sec': round(o['sam_min'] * 60)} for o in sew_ops],
        'hourly': [{'label': r['label'], 'A': round(r['pieces'] * zone_sew['A'] / 60 * 100), 'B': round(r['pieces'] * zone_sew['B'] / 60 * 100),
                    'module': round(r['eff']), 'flags': r['flags']} for r in hours],
        'restriction': {'id': sew_ops[0]['id'], 'name': L(sew_ops[0]['name_es'], sew_ops[0]['name_en']), 'sam': sew_ops[0]['sam_min'], 'zone': sew_ops[0]['zone']},
    }

    data = {
        'version': VERSION,
        'meta': {'module': {'id': 28, 'name': z['module']['name']}, 'plant': '[PLANT]', 'date': '2026-10-30',
                 'product': z['module']['product'], 'sam': SAM_MIN, 'operators': OPERATORS, 'plantStart': plant_start, 'plantEnd': plant_end,
                 'windowMin': round(window_min), 'videoUntil': '2026-12-01',
                 'clockNote': L('El reloj que aparece dentro del video va una hora adelantado. Aquí todo está en hora de planta.',
                                'The clock shown inside the video runs one hour ahead. Everything here is in plant time.')},
        'playlist': {'end': WINDOW_END, 'offset': pl.offset, 'recordings': pl.recs},
        'zones': {'cola': z['zones']['queue'], 'teclado': z['zones']['keypad'], 'A': z['zones']['a_seat'], 'B': z['zones']['b_station']},
        'lanes': L_, 'cycles': cycles, 'captures': caps, 'waits': waits, 'queueEpisodes': queue_eps,
        'hourly': {'rows': hours, 'total': total, 'avg': round(avg, 1), 'sam': SAM_MIN, 'operators': OPERATORS},
        'kpis': {'bCycle': k['b_cycle']['median'], 'bCycleIqr': [k['b_cycle']['p25'], k['b_cycle']['p75']], 'bWork': k['b_work']['median'], 'bWait': k['b_wait']['median'],
                 'bFront': k['b_at_front']['median'], 'queue': k['queue_dwell']['median'], 'aInterval': k['a_interval']['median'], 'perHour': k['pieces_per_hour'],
                 'cpPerHour': k['cp_per_hour'], 'cycles': k['cycles_detected'], 'clean': k['cycles_clean'], 'captures': len(caps),
                 'keypad': {'hits': kp['n_with_B_hand_within_15s'], 'n': kp['n'], 'median': kp['median_residual_s'], 'chance': kp['null_fraction']}},
        'bTime': b_time, 'aTime': a_time, 'stations': stations, 'insights': insights, 'mock': mock,
    }
    return data, pl


# ---------------------------------------------------------------- media
def stills(data, pl, out, skip):
    """Proof stills cut from the local recordings (CPU ffmpeg), cached by time, crop and width."""
    cache = CACHE / 'stills'; cache.mkdir(parents=True, exist_ok=True)
    jobs = []
    for ins in data['insights']:
        for j, f in enumerate(ins['proof'], 1):
            name = f'proof-{ins["id"]}-{j}.jpg'
            f['src'] = name
            jobs.append((f['t'], f.pop('roi'), name, 480))
    jobs.append((data['insights'][0]['moment']['t'] + 8, (0, 0, 1440, 810), 'poster.jpg', 960))
    for t, roi, name, width in jobs:
        key = cache / f'{t:.1f}-{"-".join(map(str, roi))}-{width}.jpg'
        if not key.is_file():
            assert not skip, f'--skip-media but {key.name} is not cached'
            rec, off = pl.locate(t)
            src = LOCAL_VIDEO / rec['file']
            assert src.is_file(), f'local recording missing: {src}'
            x, y, w, h = roi
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{off:.3f}', '-i', str(src), '-frames:v', '1',
                            '-vf', f'crop={w}:{h}:{x}:{y},scale={width}:-2', '-q:v', '5', str(key)], check=True)
        shutil.copyfile(key, out / name)


def pose(out):
    """Compact pose-recNN.json (65 joints, 2D+3D, yaw) into uint16 (body, feet and hands) binaries for the skeleton overlay."""
    assert sys.byteorder == 'little'
    manifest = {'fps': 15, 'joints': BODY, 'missing': 65535, 'scale': 10000, 'recs': {}}
    for rec in range(1, 7):
        name = f'pose-rec{rec:02d}.bin'
        cached, meta_p, src = CACHE / name, CACHE / f'{name}.json', WEB / f'pose-rec{rec:02d}.json'
        digest = sha(src)
        if not (cached.is_file() and meta_p.is_file() and json.loads(meta_p.read_text()).get('src') == digest):
            d = json.loads(src.read_text())
            buf, meta = array('H'), {'src': digest, 'labels': {}}
            for lab in ('A', 'B'):
                P = d[lab]
                frames = array('H', P['frame'])
                pts = array('H')
                for k2, s in zip(P['k2'], P['s']):
                    for j in range(BODY):
                        ok = s[j] is not None and s[j] >= MIN_SCORE and k2[2 * j] is not None
                        pts.append(max(0, min(10000, int(k2[2 * j]))) if ok else 65535)
                        pts.append(max(0, min(10000, int(k2[2 * j + 1]))) if ok else 65535)
                meta['labels'][lab] = {'offset': len(buf) * 2, 'n': len(frames)}
                buf.extend(frames); buf.extend(pts)
            CACHE.mkdir(exist_ok=True)
            cached.write_bytes(buf.tobytes()); meta_p.write_text(json.dumps(meta))
        meta = json.loads(meta_p.read_text())
        manifest['recs'][str(rec)] = {'file': name, 'labels': meta['labels']}
        shutil.copyfile(cached, out / name)
    (out / 'pose-manifest.json').write_text(json.dumps(manifest, separators=(',', ':')))


def brand(out):
    with zipfile.ZipFile(CTX / 'rikuy-fonts.zip') as zf:
        for member, name in [('rikuy-fonts/grift/grift-500.woff2', 'font-grift-500.woff2'), ('rikuy-fonts/grift/grift-600.woff2', 'font-grift-600.woff2'),
                             ('rikuy-fonts/onest/onest-latin-wght-normal.woff2', 'font-onest-latin.woff2'),
                             ('rikuy-fonts/onest/onest-latin-ext-wght-normal.woff2', 'font-onest-latin-ext.woff2'),
                             ('rikuy-fonts/jetbrains-mono/jetbrains-mono-latin-wght-normal.woff2', 'font-jetbrains-mono.woff2')]:
            (out / name).write_bytes(zf.read(member))
    with zipfile.ZipFile(CTX / 'rikuy-logo-kit.zip') as zf:
        for member, name in [('rikuy-logo-kit/rikuy-logo-negative.svg', 'logo-rikuy-negative.svg'), ('rikuy-logo-kit/rikuy-logo-blanco.svg', 'logo-rikuy-blanco.svg')]:
            (out / name).write_bytes(zf.read(member))
    shutil.copyfile(CTX / 'Enpiso-Logo.png', out / 'logo-enpiso.png')
    shutil.copyfile(CTX / 'cropped-en-piso-favicon-192x192.png', out / 'favicon-enpiso.png')
    mp4 = (FICHA / 'out/ficha-3d-16x9.mp4').resolve()
    if mp4.is_file():
        shutil.copyfile(mp4, out / 'mock-ficha-3d.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(FICHA / 'out/end-card-16x9.jpg'), '-vf', 'scale=640:-2', '-q:v', '5', str(out / 'mock-ficha-poster.jpg')], check=True)
    return (out / 'mock-ficha-3d.mp4').is_file()


# ---------------------------------------------------------------- copy (ES / EN)
def catalogs():
    return {lang: json.loads((SRC / 'i18n' / f'{lang}.json').read_text()) for lang in LANGS}


def numbers(s):
    """Numbers in a string, decimal comma or point normalised, for comparing the ES and EN versions of one string."""
    return sorted(m.replace(',', '.') for m in re.findall(r'\d+(?:[.,]\d+)?', s))


def pairs(o, path='data'):
    """Every bilingual {'es', 'en'} pair in the data, with its path."""
    if isinstance(o, dict) and set(o) == set(LANGS):
        yield path, o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from pairs(v, f'{path}.{k}')
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from pairs(v, f'{path}[{i}]')


def check_copy(data, cat):
    """Both languages complete and consistent: same catalog keys and placeholders, every generated string in both
    languages, the same numbers in both versions, no dashes used as punctuation."""
    bad = []
    if set(cat['es']) != set(cat['en']):
        bad.append(('catalog keys differ', sorted(set(cat['es']) ^ set(cat['en']))))
    items = [(f'i18n:{k}', {lang: cat[lang].get(k, '') for lang in LANGS}) for k in cat['es']] + list(pairs(data))
    for where, p in items:
        if not all(isinstance(p[lang], str) and p[lang].strip() for lang in LANGS):
            bad.append((where, 'missing a language'))
            continue
        if sorted(re.findall(r'\{\w+\}', p['es'])) != sorted(re.findall(r'\{\w+\}', p['en'])):
            bad.append((where, 'placeholders differ'))
        if numbers(p['es']) != numbers(p['en']):
            bad.append((where, f'numbers differ: {numbers(p["es"])} vs {numbers(p["en"])}'))
        for lang in LANGS:
            if re.search(r'\s-\s|\u2014|\u2013', p[lang]):
                bad.append((where, f'{lang}: dash'))
            bad += [(where, f'{lang}: {pat}') for pat in BANNED + PII if re.search(pat, p[lang], re.I)]
    assert not bad, f'copy check failed: {bad}'
    return len(items)


def fill(html, cat):
    """{{t:key}} tokens in the page shell get the Spanish string, so the HTML reads well before (or without) JS."""
    def rep(m):
        key = m.group(1)
        assert key in cat, f'unknown i18n key {key}'
        s = cat[key]
        return s if key.endswith('_html') else s.replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')
    return re.sub(r'\{\{t:([\w.]+)\}\}', rep, html)


# ---------------------------------------------------------------- page
def page(data, out, has_mock_video):
    css = (SRC / 'styles/kit.css').read_text() + '\n' + (SRC / 'styles/app.css').read_text()
    js = '\n'.join(f'/* ---- {n} */\n' + (SRC / 'js' / n).read_text() for n in JS_ORDER)
    (out / 'app.js').write_text(js)
    data['meta']['mockVideo'] = 'mock-ficha-3d.mp4' if has_mock_video else None
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    (out / 'app-data.json').write_text(blob)
    cat = catalogs()
    n_copy = check_copy(data, cat)
    built = datetime.date.today().isoformat()
    html = fill((SRC / 'index.html').read_text(), cat['es'])
    # the footer line also has {version}, {built} and {date}; the page re-renders it per language
    html = html.replace('{version}', VERSION).replace('{built}', built).replace('{date}', 'viernes 30 de octubre de 2026')  # 2026-10-30 is a Friday
    js_v = hashlib.sha256((js + json.dumps(cat)).encode()).hexdigest()[:10]
    i18n_blob = json.dumps(cat, ensure_ascii=False, separators=(',', ':'))
    for key, val in {'{{CSS}}': css, '{{VERSION}}': VERSION, '{{JSV}}': js_v, '{{I18N}}': i18n_blob.replace('</', '<\\/'),
                     '{{BUILT}}': built, '{{DATA}}': blob.replace('</', '<\\/')}.items():
        assert key in html, key
        html = html.replace(key, val)
    assert '{{' not in html, 'unfilled token'
    assert not re.search(r'\{[a-z]\w*\}', re.sub(r'<script.*?</script>|<style>.*?</style>', '', html, flags=re.S)), 'unfilled placeholder in the HTML'
    print(f'copy: {len(cat["es"])} catalog keys and {n_copy - len(cat["es"])} generated strings checked in ES and EN')
    (out / 'index.html').write_text(html)


def scan(out):
    """Fail the build if a name, an employee code, a client name or a banned word reaches the bundle."""
    bad = []
    for p in sorted(out.iterdir()):
        if p.suffix not in ('.html', '.js', '.json', '.svg', '.css', '.txt'):
            continue
        text = p.read_text(errors='ignore')
        bad += [(p.name, pat) for pat in PII if re.search(pat, text, re.I)]
        if p.name in ('index.html', 'app-data.json', 'app.js'):
            bad += [(p.name, pat) for pat in BANNED if re.search(pat, text, re.I)]
    assert not bad, f'privacy/copy scan failed: {bad}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(H / 'dist'))
    ap.add_argument('--skip-media', action='store_true', help='reuse cached stills; fail if one is missing')
    ap.add_argument('--blur-faces', action='store_true', help='future work: blur faces in stills and video (not implemented)')
    a = ap.parse_args()
    if a.blur_faces:
        sys.exit('--blur-faces is not implemented yet. Blurring needs a per-frame face pass over the recordings and new video files; '
                 'see README "Future work". This private build shows faces unblurred.')
    out = pathlib.Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    CACHE.mkdir(exist_ok=True)
    z, rows, full, ficha, sim = load_inputs()
    data, pl = build_data(z, rows, full, ficha, sim)
    stills(data, pl, out, a.skip_media)
    pose(out)
    has_mock = brand(out)
    page(data, out, has_mock)
    (out / 'robots.txt').write_text('User-agent: *\nDisallow: /\n')
    scan(out)
    files = sorted(p for p in out.iterdir() if p.is_file())
    manifest = [{'file': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files]
    (CACHE / 'dist-manifest.json').write_text(json.dumps(manifest, indent=1))
    total = sum(m['bytes'] for m in manifest)
    print(f'BUILT {out} · {len(files)} files · {total / 1e6:.1f} MB · index.html {(out / "index.html").stat().st_size / 1e3:.0f} kB')


if __name__ == '__main__':
    main()
