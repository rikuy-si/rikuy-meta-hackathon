"""Rikuy design system for video (source: https://rikuy.si/design-system/ v2.1.0, brand kit in assets/brand/).

Colors, fonts (Grift 600 titles and numbers, Onest body, JetBrains Mono data), radius 8/12/18/24/32, motion ease
cubic-bezier(.2,.7,.2,1), viewfinder corners, navy duotone + dotted veil for camera stills.
Hard checks enforced at draw time (LayoutError stops the render): no em or en dash in any text, every text box
inside the title-safe area, no text below 12 px. Every drawn text is logged for the QA report.
"""
import math, pathlib
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BR = pathlib.Path(__file__).resolve().parent / 'assets' / 'brand'


def _hx(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


C = {k: _hx(v) for k, v in {
    'noche': '#14133F', 'noche2': '#263962', 'menta': '#7FCCB4', 'teal': '#2E7D7C', 'blanco': '#F6F9F8',
    'amarillo': '#DCE064', 'gris': '#5B5B74', 'hielo': '#A9B6D3', 'bruma': '#CDD6E8', 'menta_palida': '#BFE6DA',
    'tint_hi': '#EAF0F8'}.items()}                                   # RGB


def bgr(c):
    return (c[2], c[1], c[0])


FONT_FILES = {'grift': ('grift/Grift-SemiBold.ttf', None), 'grift5': ('grift/Grift-Medium.ttf', None),
              'onest': ('onest/Onest-Variable.ttf', 400), 'onest5': ('onest/Onest-Variable.ttf', 500),
              'mono': ('jetbrains-mono/JetBrainsMono-Variable.ttf', 500)}
TRACK = {'grift': -0.04, 'grift5': -0.02}                              # em, titles only (size >= 40)
_F = {}


def font(kind, size):
    k = (kind, size)
    if k not in _F:
        f, wgt = FONT_FILES[kind]
        ft = ImageFont.truetype(str(BR / 'fonts' / f), size)
        if wgt:
            ft.set_variation_by_axes([wgt])
        _F[k] = ft
    return _F[k]


class LayoutError(Exception):
    pass


_CMAP = {}


def _missing_glyphs(kind, t):
    if kind not in _CMAP:
        from fontTools.ttLib import TTFont
        _CMAP[kind] = set(TTFont(str(BR / 'fonts' / FONT_FILES[kind][0])).getBestCmap())
    return [c for c in t if c != ' ' and ord(c) not in _CMAP[kind]]


CTX = {'seg': '', 'safe': (96, 54, 1824, 1026)}                         # 90 % title-safe of 1920x1080


def set_canvas(w, h):
    """Switch the canvas (1920x1080 or 1080x1920); the title-safe area is the central 90 %."""
    global W, H
    W, H = w, h
    CTX['safe'] = (round(w * 0.05), round(h * 0.05), round(w * 0.95), round(h * 0.95))


def fit(t, kind, size, max_w, min_size=20):
    """Largest size <= size at which t fits in max_w (never below min_size; the safe-area guard still applies)."""
    while size > min_size and text_w(t, kind, size) > max_w:
        size -= 2
    return size
LOG = {}


def _track(kind, size):
    return TRACK.get(kind, 0) * size if size >= 40 else 0


def text_w(t, kind, size):
    f, tr = font(kind, size), _track(kind, size)
    return sum(f.getlength(ch) for ch in t) + tr * max(0, len(t) - 1) if tr else f.getlength(t)


def text(d, xy, t, kind, size, fill, anchor='la'):
    """Draw text with brand tracking. anchor: (l|m|r)(a|t|m|s|b|d) like PIL. Returns the box."""
    if any(c in t for c in '\u2013\u2014'):
        raise LayoutError(f'dash in text: {t!r}')
    if size < 12:
        raise LayoutError(f'text below 12 px: {t!r}')
    miss = _missing_glyphs(kind, t)
    if miss:
        raise LayoutError(f'font {kind} has no glyph for {miss} in {t!r}')
    f, w, tr = font(kind, size), text_w(t, kind, size), _track(kind, size)
    x, y = xy
    x0 = x - (w / 2 if anchor[0] == 'm' else w if anchor[0] == 'r' else 0)
    bb = f.getbbox(t, anchor='l' + anchor[1])
    box = (x0 + bb[0], y + bb[1], x0 + w, y + bb[3])
    if tr:                                                            # per-glyph tracking on one shared baseline
        yb = y + f.getbbox(t, anchor='l' + anchor[1])[1] - f.getbbox(t, anchor='ls')[1]
        cx = x0
        for ch in t:
            d.text((cx, yb), ch, font=f, fill=fill, anchor='ls'); cx += f.getlength(ch) + tr
    else:
        d.text((x0, y), t, font=f, fill=fill, anchor='l' + anchor[1])
    s = CTX['safe']
    key = (CTX['seg'], t)
    LOG.setdefault(key, [round(v) for v in box])
    if box[0] < s[0] - 1 or box[2] > s[2] + 1 or box[1] < s[1] - 1 or box[3] > s[3] + 1:
        raise LayoutError(f'text outside safe area {s}: {t!r} {[round(v) for v in box]} (segment {CTX["seg"]})')
    return box


def layer(w=None, h=None):
    return Image.new('RGBA', (w or W, h or H), (0, 0, 0, 0))


def compose(base_bgr, lay):
    im = Image.fromarray(cv2.cvtColor(base_bgr, cv2.COLOR_BGR2RGB)).convert('RGBA'); im.alpha_composite(lay)
    return cv2.cvtColor(np.array(im.convert('RGB')), cv2.COLOR_RGB2BGR)


def solid(c, w=None, h=None):
    img = np.empty((h or H, w or W, 3), np.uint8); img[:] = bgr(c); return img


def fade_to(img, c, al):
    """al = 1 shows img, 0 shows the solid brand color c (fades go through Noche, never pure black)."""
    if al >= 1: return img
    return (img.astype(np.float32) * al + np.array(bgr(c), np.float32) * (1 - al)).astype(np.uint8)


def ease(t, p=(.2, .7, .2, 1)):
    t = min(1.0, max(0.0, t)); x1, y1, x2, y2 = p; lo, hi = 0.0, 1.0
    for _ in range(28):
        s = (lo + hi) / 2; x = 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s ** 2 * x2 + s ** 3
        lo, hi = (s, hi) if x < t else (lo, s)
    s = (lo + hi) / 2
    return 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s ** 2 * y2 + s ** 3


def back_out(t, k=1.9):
    t = min(1.0, max(0.0, t)) - 1
    return 1 + (k + 1) * t ** 3 + k * t ** 2


def with_alpha(c, a):
    return (*c[:3], int(max(0, min(1, a)) * 255))


def corners(d, box, color, L=44, w=6):
    x0, y0, x1, y1 = box
    for x, y, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line([(x, y + sy * L), (x, y), (x + sx * L, y)], fill=color, width=w, joint='curve')


def duotone(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)[..., None] / 255
    lo, hi = np.array(bgr(C['noche']), np.float32), np.array(bgr(C['tint_hi']), np.float32)
    return (lo * (1 - g) + hi * g).astype(np.uint8)


_DOTS = {}


def dotted_veil(img, step=12, r=1, alpha=0.35):
    h, w = img.shape[:2]
    if (h, w) not in _DOTS:
        m = np.zeros((h, w), np.uint8)
        for y in range(step // 2, h, step):
            for x in range(step // 2, w, step):
                cv2.circle(m, (x, y), r, 255, -1)
        _DOTS[(h, w)] = (m.astype(np.float32) / 255)[..., None]
    m = _DOTS[(h, w)] * alpha
    return (img * (1 - m) + np.array(bgr(C['noche']), np.float32) * m).astype(np.uint8)


def icon(d, kind, c, r, color, hole=None):
    hole = hole or C['noche2']
    x, y = c; lw = max(3, int(r * 0.09))
    if kind == 'sun':                                                 # rising sun on a horizon
        cy = y + r * 0.25
        d.pieslice([x - r * .5, cy - r * .5, x + r * .5, cy + r * .5], 180, 360, fill=color)
        d.line([x - r * .85, cy + lw / 2, x + r * .85, cy + lw / 2], fill=color, width=lw)
        for a in (200, 235, 270, 305, 340):
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            d.line([x + ca * r * .65, cy + sa * r * .65, x + ca * r * .9, cy + sa * r * .9], fill=color, width=lw)
    elif kind == 'team':                                              # two people side by side
        for dx, s in ((-.3, .9), (.3, 1.0)):
            px = x + dx * r
            d.ellipse([px - .17 * r * s, y - .55 * r, px + .17 * r * s, y - .21 * r], fill=color)
            d.pieslice([px - .33 * r * s, y - .1 * r, px + .33 * r * s, y + .56 * r], 180, 360, fill=color)
        d.rectangle([x - .65 * r, y + .23 * r, x + .65 * r, y + .3 * r], fill=color)
    elif kind == 'barbell':
        d.line([x - .9 * r, y, x + .9 * r, y], fill=color, width=lw)
        for s in (-1, 1):
            d.rounded_rectangle([x + s * .52 * r - .08 * r, y - .42 * r, x + s * .52 * r + .08 * r, y + .42 * r], int(.04 * r) + 1, fill=color)
            d.rounded_rectangle([x + s * .7 * r - .06 * r, y - .28 * r, x + s * .7 * r + .06 * r, y + .28 * r], int(.03 * r) + 1, fill=color)
    elif kind == 'flame':                                             # round base, tapering lean tip, inner core
        def tear(cx, cy, rr, lean, k=60):
            def wd(u):
                return rr * .5 * math.sqrt(max(0, 1 - ((u - .32) / .32) ** 2)) if u < .32 else rr * .5 * ((1 - u) / .68) ** 1.25
            L = [(cx + lean * rr * u ** 2 + s * wd(u), cy + rr * .62 - u * rr * 1.6)
                 for s, rng in ((1, range(k + 1)), (-1, range(k, -1, -1))) for u in (j / k for j in rng)]
            return L
        d.polygon(tear(x + .05 * r, y, r, -0.15), fill=color)
        d.polygon(tear(x - .3 * r, y + .2 * r, .6 * r, -0.3), fill=color)
        d.polygon(tear(x + .03 * r, y + .25 * r, .48 * r, 0.12), fill=hole)
    else:
        raise ValueError(kind)


def medal(lay, c, r, flip=0.0, shine=-1.0):
    """Amarillo medal with Teal and Menta ribbon; flip: rotation about the vertical axis (rad); shine: 0..1 band."""
    S = 3
    w, h = int(2.4 * r), int(3.3 * r)
    m = Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0)); dm = ImageDraw.Draw(m)
    R = r * S; cx, cy = w * S / 2, h * S - 1.15 * R
    dm.polygon([(cx - .85 * R, 0), (cx - .3 * R, 0), (cx + .2 * R, cy - .7 * R), (cx - .35 * R, cy - .55 * R)], fill=C['teal'])
    dm.polygon([(cx + .85 * R, 0), (cx + .3 * R, 0), (cx - .2 * R, cy - .7 * R), (cx + .35 * R, cy - .55 * R)], fill=C['menta'])
    disc = Image.new('RGBA', m.size, (0, 0, 0, 0)); dd = ImageDraw.Draw(disc)
    dd.ellipse([cx - R, cy - R, cx + R, cy + R], fill=C['amarillo'])
    dd.ellipse([cx - .8 * R, cy - .8 * R, cx + .8 * R, cy + .8 * R], outline=C['noche2'], width=int(.05 * R))
    icon(dd, 'barbell', (cx, cy), .55 * R, C['noche'])
    if 0 <= shine <= 1:
        band = Image.new('L', m.size, 0); db = ImageDraw.Draw(band)
        bx = cx - 1.6 * R + 3.2 * R * shine
        db.polygon([(bx, cy - R), (bx + .35 * R, cy - R), (bx - .25 * R, cy + R), (bx - .6 * R, cy + R)], fill=150)
        dmask = Image.new('L', m.size, 0); ImageDraw.Draw(dmask).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
        from PIL import ImageChops
        band = ImageChops.multiply(band, dmask)
        white = Image.new('RGBA', m.size, (*C['blanco'], 0)); white.putalpha(band)
        disc.alpha_composite(white)
    m.alpha_composite(disc)
    sx = max(0.04, abs(math.cos(flip)))
    m = m.resize((max(1, int(w * sx)), h), Image.LANCZOS)
    lay.alpha_composite(m, (int(c[0] - m.width / 2), int(c[1] - cy / S)))


class Burst:
    """Confetti in brand colors; draw(img, t) with t seconds since the burst."""
    COLS = ['menta', 'amarillo', 'teal', 'blanco', 'menta_palida']

    def __init__(self, origin, n=150, seed=7, speed=(500, 1300), spread=(-165, -15), size=1.0):
        g = np.random.default_rng(seed); a = np.radians(g.uniform(*spread, n)); v = g.uniform(*speed, n)
        self.o = np.array(origin, np.float32); self.v = np.stack([np.cos(a) * v, np.sin(a) * v], 1)
        self.c = [bgr(C[self.COLS[i % len(self.COLS)]]) for i in g.integers(0, 5, n)]
        self.s = g.uniform(7, 13, n) * size; self.w = g.uniform(-12, 12, n); self.ph = g.uniform(0, 6.28, n)

    def draw(self, img, t):
        if t < 0 or t > 2.2: return img
        k = math.exp(-1.6 * t)
        pos = self.o + self.v * (1 - k) / 1.6 + np.array([0, 900]) * (t ** 2) / 2
        sc = 1.0 if t < 1.5 else max(0, 1 - (t - 1.5) / 0.7)
        for p, c, s, w, ph in zip(pos, self.c, self.s, self.w, self.ph):
            ang = ph + w * t; L, Wd = s * sc, s * 0.55 * sc * abs(math.cos(ph + 3 * t))
            ca, sa = math.cos(ang), math.sin(ang)
            pts = np.array([[-L, -Wd], [L, -Wd], [L, Wd], [-L, Wd]]) @ np.array([[ca, sa], [-sa, ca]]) + p
            cv2.fillConvexPoly(img, pts.astype(np.int32), c, lineType=cv2.LINE_AA)
        return img


def logo(lay, xy, width, variant='negative', anchor='mm'):
    im = Image.open(BR / 'logo' / f'rikuy-logo-{variant}.png').convert('RGBA')
    hh = int(im.height * width / im.width); im = im.resize((width, hh), Image.LANCZOS)
    x, y = xy; x -= width / 2 if anchor[0] == 'm' else 0; y -= hh / 2 if anchor[1] == 'm' else 0
    lay.alpha_composite(im, (int(x), int(y)))
