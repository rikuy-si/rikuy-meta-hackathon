/* ---- core.js */
/* Pure helpers shared by the page and the Node unit tests (UMD: window.Core or module.exports). */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Core = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const pad = (n) => String(n).padStart(2, '0');
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

  function secs(clock) { const [h, m, s] = String(clock).split(':').map(Number); return h * 3600 + m * 60 + (s || 0); }
  function hms(sec) { sec = ((Math.floor(sec) % 86400) + 86400) % 86400; return `${pad(Math.floor(sec / 3600))}:${pad(Math.floor(sec / 60) % 60)}:${pad(sec % 60)}`; }

  // Playlist index and offset for timeline second t (recordings are contiguous and sorted by start).
  function locate(recs, t, end) {
    t = clamp(t, 0, (end || Infinity) - 0.001);
    let i = 0;
    for (let j = 1; j < recs.length; j++) { if (t + 1e-7 >= recs[j].start) i = j; else break; }
    return { i, offset: clamp(t - recs[i].start, 0, recs[i].duration - 0.001) };
  }
  function plantClock(recs, t) { const p = locate(recs, t); return hms(secs(recs[p.i].plantStart) + p.offset); }
  function plantToT(recs, clock, end) {
    const want = secs(clock);
    for (const r of recs) { const s = secs(r.plantStart); if (want >= s && want < s + r.duration) { const t = r.start + want - s; return t <= end ? t : null; } }
    return null;
  }

  // Locale: 'es' (decimal comma, "59 %", "jue 30 oct 2026") or 'en' (decimal point, "59%", "Thu Oct 30 2026").
  // The plant clock stays 24 h in both languages.
  let LANG = 'es';
  const LANGS = ['es', 'en'];
  function setLang(l) { if (LANGS.includes(l)) LANG = l; return LANG; }
  const getLang = () => LANG;
  // Number formatting: a trailing ",0" / ".0" dropped.
  function num(x, d = 1, lang = LANG) { if (x == null || !Number.isFinite(x)) return '·'; let s = x.toFixed(d); if (lang === 'es') s = s.replace('.', ','); return /[.,]0+$/.test(s) ? s.replace(/[.,]0+$/, '') : s; }
  const pct = (x, lang = LANG) => (lang === 'es' ? `${Math.round(x)}\u00a0%` : `${Math.round(x)}%`);
  const DAYS = { es: ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'], en: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'] };
  const MONTHS = { es: ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
    en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'] };
  // ISO date (YYYY-MM-DD) to a short ("jue 30 oct 2026" / "Thu Oct 30 2026") or long label.
  function date(iso, long = false, lang = LANG) {
    const [y, m, d] = String(iso).split('-').map(Number), wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
    const day = DAYS[lang][wd], mon = MONTHS[lang][m - 1];
    if (lang === 'en') return long ? `${day}, ${mon} ${d}, ${y}` : `${day.slice(0, 3)} ${mon.slice(0, 3)} ${d} ${y}`;
    return long ? `${day} ${d} de ${mon} de ${y}` : `${day.slice(0, 3)} ${d} ${mon.slice(0, 3)} ${y}`;
  }
  function dur(sec) { sec = Math.round(sec); if (sec < 60) return `${sec} s`; const m = Math.floor(sec / 60), s = sec % 60; return s ? `${m} min ${s} s` : `${m} min`; }

  // Routes: #/panel, #/panel/<insight>, #/video?t=..&clip=a-b&from=<insight>&capas=zonas,puestos,esqueletos (default: all on; capas=ninguna for none); any of them may add &lang=es|en
  function parseHash(hash) {
    const h = String(hash || '').replace(/^#/, '');
    const [path, query = ''] = h.split('?');
    const parts = path.split('/').filter(Boolean);
    const route = parts[0] === 'video' ? 'video' : 'panel';
    const q = new URLSearchParams(query), out = { route, id: parts[1] || null, t: null, clip: null, from: null, capas: [], lang: LANGS.includes(q.get('lang')) ? q.get('lang') : null };
    const t = Number(q.get('t'));
    if (q.has('t') && Number.isFinite(t) && t >= 0) out.t = t;
    const c = (q.get('clip') || '').split('-').map(Number);
    if (c.length === 2 && c.every(Number.isFinite) && c[1] > c[0]) out.clip = c;
    if (q.get('from') && /^[a-z0-9-]{1,40}$/.test(q.get('from'))) out.from = q.get('from');
    // v0.1.3: every layer is ON unless the link says otherwise (capas=ninguna turns them all off).
    out.capas = q.has('capas') ? q.get('capas').split(',').filter((x) => ['zonas', 'puestos', 'esqueletos'].includes(x)) : ['zonas', 'puestos', 'esqueletos'];
    return out;
  }
  function videoHash({ t, clip, from, capas, lang } = {}) {
    const q = [];
    if (t != null) q.push(`t=${Math.round(t * 10) / 10}`);
    if (clip) q.push(`clip=${clip[0]}-${clip[1]}`);
    if (from) q.push(`from=${from}`);
    if (capas) q.push(`capas=${capas.length ? capas.join(',') : 'ninguna'}`);
    if (lang) q.push(`lang=${lang}`);
    return '#/video' + (q.length ? '?' + q.join('&') : '');
  }
  const insightHash = (ins, lang) => videoHash({ t: ins.moment.clip[0], clip: ins.moment.clip, from: ins.id, lang });
  // Set (or replace) the lang parameter of any hash route, keeping its other parameters.
  function withLang(hash, lang) {
    const h = String(hash || '#/panel').replace(/^#?/, '#');
    const [path, query = ''] = h.split('?'), q = new URLSearchParams(query);
    q.delete('lang'); if (lang) q.set('lang', lang);
    const s = q.toString().replace(/%2C/g, ',');
    return (path === '#' || path === '#/' ? '#/panel' : path) + (s ? '?' + s : '');
  }

  // Lane value at t; lanes are sorted [start, end, code] segments (a missing code means "occupied").
  function laneAt(lane, t) {
    let lo = 0, hi = lane.length - 1;
    while (lo <= hi) { const m = (lo + hi) >> 1, s = lane[m]; if (t < s[0]) hi = m - 1; else if (t >= s[1]) lo = m + 1; else return s[2] === undefined ? true : s[2]; }
    return null;
  }

  // Every marker the video module lists or draws, sorted by time. `tr(key, vars)` is the string catalog lookup (I18n.t);
  // D is the localized data (headlines already in the current language).
  function moments(D, tr) {
    const out = [];
    for (const i of D.insights) out.push({ t: i.moment.t, kind: 'hallazgo', id: i.id, label: i.headline, sub: i.kind === 'review' ? tr('m.review') : i.kind === 'trust' ? tr('m.trust') : tr('m.finding', { n: i.rank }) });
    for (const c of D.cycles) out.push({ t: c.start, kind: 'ciclo', id: `c${c.n}`, label: tr('m.cycle', { n: c.n }), sub: c.cycle ? `${dur(c.cycle)}${c.clean ? '' : tr('m.lowConf')}${c.cp.length ? '' : tr('m.noCp')}` : tr('m.incomplete') });
    for (const r of D.captures) out.push({ t: Math.max(0, r.t - 4), kind: 'cp', id: r.id, label: tr('m.capture', { n: r.id.slice(1) }), sub: r.keypad != null ? tr('m.hand', { s: num(Math.abs(r.keypad)) }) : tr('m.noHand') });
    for (const w of D.waits) out.push({ t: Math.max(0, w.s - 3), kind: 'espera', id: `w${w.s}`, label: tr('m.wait'), sub: dur(w.e - w.s) });
    for (const q of D.queueEpisodes) out.push({ t: q.s, kind: 'espera', id: `q${q.s}`, label: tr('m.queue'), sub: `${dur(q.e - q.s)}${tr('m.lowConf')}` });
    return out.sort((a, b) => a.t - b.t || a.kind.localeCompare(b.kind));
  }
  function nextMoment(list, t, dir, kinds) {
    const ok = list.filter((m) => !kinds || kinds.has(m.kind));
    if (dir > 0) return ok.find((m) => m.t > t + 0.5) || null;
    for (let i = ok.length - 1; i >= 0; i--) if (ok[i].t < t - 1.5) return ok[i];
    return null;
  }

  // Visible window for the timeline: everything, or `span` seconds centred on t.
  function viewWindow(t, end, span) {
    if (!span || span >= end) return [0, end];
    const a = clamp(t - span / 2, 0, end - span);
    return [a, a + span];
  }

  // "13:50 a 13:51" / "13:50 to 13:51", or with seconds when both ends fall in the same minute.
  function clipLabel(a, b, lang = LANG) { const w = lang === 'en' ? 'to' : 'a'; return a.slice(0, 5) === b.slice(0, 5) ? `${a} ${w} ${b}` : `${a.slice(0, 5)} ${w} ${b.slice(0, 5)}`; }
  const CONF = { alta: 3, media: 2, baja: 1 };
  // Pick the language: ?lang / #…&lang, then the saved choice, then the browser (en* is English), otherwise Spanish.
  function pickLang({ param, saved, browser } = {}) {
    for (const v of [param, saved]) if (LANGS.includes(v)) return v;
    const b = [].concat(browser || []).find(Boolean);
    return b && /^en\b/i.test(b) ? 'en' : 'es';
  }
  return { pad, clamp, secs, hms, locate, plantClock, plantToT, num, pct, dur, date, setLang, getLang, LANGS, pickLang, parseHash, videoHash, insightHash, withLang, laneAt, moments, nextMoment, viewWindow, clipLabel, CONF };
});

/* ---- i18n.js */
/* I18n: the ES/EN string catalog (src/i18n/{es,en}.json, inlined by build.py as #i18n), lookups with {placeholders},
   localization of the bilingual {es, en} fields in app-data.json, and the static page strings marked with
     data-i18n="key"            text content       (keys ending in _html are inserted as markup)
     data-i18n-attr="a:key,b:k"  attributes (aria-label, title, alt, content)
     CSS_TEXT                    custom properties read by CSS content: (the "Ejemplo" badges)
   No library: the catalog is a flat key -> string map per language. */
const I18n = (function () {
  'use strict';
  const CAT = JSON.parse(document.getElementById('i18n').textContent);
  const HTML_LANG = { es: 'es-CO', en: 'en-US' };
  const KEY = 'enpiso-vision-lang';
  const CSS_TEXT = { '--t-mock-chip': 'mock.chip', '--t-op-bottleneck': 'mock.opBottleneck' };
  let lang = 'es';

  function t(key, vars) {
    let s = CAT[lang][key];
    if (s == null) { s = CAT.es[key]; if (s == null) return key; }
    return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? String(vars[k]) : m)) : s;
  }
  const isPair = (v) => v && typeof v === 'object' && !Array.isArray(v) && 'es' in v && 'en' in v && Object.keys(v).length === 2;
  // Deep copy of the data with every {es, en} pair replaced by the current language's string.
  function localize(v) {
    if (isPair(v)) return v[lang];
    if (Array.isArray(v)) return v.map(localize);
    if (v && typeof v === 'object') { const o = {}; for (const k in v) o[k] = localize(v[k]); return o; }
    return v;
  }
  function apply(root) {
    for (const e of (root || document).querySelectorAll('[data-i18n]')) {
      const k = e.dataset.i18n;
      if (k.endsWith('_html')) e.innerHTML = t(k); else e.textContent = t(k);
    }
    for (const e of (root || document).querySelectorAll('[data-i18n-attr]')) {
      for (const pair of e.dataset.i18nAttr.split(',')) { const [a, k] = pair.split(':'); e.setAttribute(a.trim(), t(k.trim())); }
    }
    for (const b of document.querySelectorAll('[data-lang]')) b.setAttribute('aria-pressed', String(b.dataset.lang === lang));
    // text drawn by CSS (::after badges) comes from custom properties holding catalog strings
    for (const [prop, k] of Object.entries(CSS_TEXT)) document.documentElement.style.setProperty(prop, JSON.stringify(t(k)));
  }
  function saved() { try { return localStorage.getItem(KEY); } catch { return null; } }
  function save(l) { try { localStorage.setItem(KEY, l); } catch { /* private mode: the URL still carries the choice */ } }
  // Language from the URL (?lang= or #...&lang=), then the saved choice, then the browser.
  function initial() {
    const param = Core.parseHash(location.hash).lang || new URLSearchParams(location.search).get('lang');
    const l = Core.pickLang({ param, saved: saved(), browser: navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language] });
    return { lang: l, fromParam: Core.LANGS.includes(param) };
  }
  function set(l, { persist = true } = {}) {
    lang = Core.setLang(l);
    document.documentElement.lang = HTML_LANG[lang];
    if (persist) save(lang);
    apply();
    return lang;
  }
  return { t, localize, apply, set, initial, get lang() { return lang; }, KEY, CAT };
})();

/* ---- player.js */
/* Continuous player over the module recordings: two <video> buffers, seamless hand-off at file boundaries,
   optional clip [a, b] that pauses at b. Seek logic adapted from enpiso/video-review/vision-player.js (v0.0.1). */
const Player = (function () {
  'use strict';
  function create({ videos, recs, end, onTime, onLoading, onClipEnd, onPlayState, onError }) {
    const S = { active: 0, rec: -1, token: 0, loading: false, rate: 1, clip: null, pending: null };
    const active = () => videos[S.active];
    const position = () => (S.rec < 0 ? (S.pending ?? 0) : recs[S.rec].start + active().currentTime);

    function setLoading(v) { S.loading = v; onLoading && onLoading(v); }
    function prefetch() {
      const other = videos[1 - S.active], i = S.rec + 1;
      if (i >= recs.length || other.dataset.rec === String(i)) return;
      other.pause(); other.dataset.rec = String(i); other.preload = 'metadata'; other.src = recs[i].url; other.load();
    }
    function seek(t, play = false) {
      t = Core.clamp(t, 0, end - 0.05);
      const p = Core.locate(recs, t, end), token = ++S.token;
      S.pending = t;
      if (p.i === S.rec && !S.loading) {
        active().currentTime = p.offset;
        if (play) doPlay();
        onTime && onTime(t);
        return;
      }
      setLoading(true);
      const slot = S.rec < 0 ? S.active : 1 - S.active, v = videos[slot];
      if (slot !== S.active) v.pause();
      v.preload = 'auto';
      const finish = () => {
        if (token !== S.token || v.readyState < 2 || Math.abs(v.currentTime - p.offset) > 0.35) return;
        v.removeEventListener('seeked', finish); v.removeEventListener('loadeddata', finish);
        if (slot !== S.active) { active().pause(); active().classList.remove('active'); }
        S.active = slot; S.rec = p.i; S.pending = null;
        v.classList.add('active'); v.playbackRate = S.rate; v.removeAttribute('aria-hidden');
        videos[1 - slot].setAttribute('aria-hidden', 'true');
        setLoading(false);
        onTime && onTime(position());
        if (play) doPlay();
        prefetch();
      };
      const ready = () => { if (token !== S.token) return; v.addEventListener('seeked', finish); v.addEventListener('loadeddata', finish); v.currentTime = p.offset; finish(); };
      if (v.dataset.rec === String(p.i) && v.readyState >= 1) ready();
      else { v.dataset.rec = String(p.i); v.addEventListener('loadedmetadata', ready, { once: true }); v.src = recs[p.i].url; v.load(); }
    }
    function doPlay() {
      const v = active();
      if (S.clip && position() >= S.clip[1] - 0.2) seek(S.clip[0]);
      const pr = v.play();
      if (pr && pr.catch) pr.catch(() => onPlayState && onPlayState(false));
    }
    function play() { if (S.rec < 0) { seek(S.pending ?? 0, true); return; } doPlay(); }
    function pause() { active().pause(); }
    function toggle() { if (S.loading) return; if (active().paused) play(); else pause(); }
    function setRate(r) { S.rate = r; for (const v of videos) v.playbackRate = r; }
    function setClip(c) { S.clip = c ? [c[0], c[1]] : null; }

    for (const v of videos) {
      v.addEventListener('timeupdate', () => {
        if (v !== active() || S.loading) return;
        const t = position();
        if (S.clip && t >= S.clip[1]) { v.pause(); onClipEnd && onClipEnd(); }
        if (t >= end - 0.05) v.pause();
        onTime && onTime(t);
      });
      v.addEventListener('play', () => { if (v === active()) onPlayState && onPlayState(true); });
      v.addEventListener('pause', () => { if (v === active()) onPlayState && onPlayState(false); });
      v.addEventListener('ended', () => { if (v !== active() || S.loading) return; if (S.rec + 1 < recs.length) seek(recs[S.rec + 1].start, true); });
      v.addEventListener('error', () => { if (v.getAttribute('src')) onError && onError(); });
    }
    return { seek, play, pause, toggle, setRate, setClip, position, active, state: S, isLoading: () => S.loading, paused: () => S.rec < 0 || active().paused, recording: () => S.rec };
  }
  return { create };
})();

/* ---- timeline.js */
/* Timeline: four marker lanes (hallazgos, ciclos, registros CP, esperas y cola) over the module recording, plant-time axis,
   cursor and clip range. Canvas drawing; the element itself is an ARIA slider driven by pointer and keyboard. */
const Timeline = (function () {
  'use strict';
  const C = { bg: '#1b1a4c', lane: '#ffffff0d', menta: '#7fccb4', mentaLow: '#7fccb466', blanco: '#f6f9f8', amarillo: '#dce064', hielo: '#a9b6d3', noche: '#14133f' };
  function create({ el, canvas, data, onSeek, onScrub }) {
    const D = data, end = D.playlist.end, recs = D.playlist.recordings;
    const S = { t: 0, span: 0, clip: null, drag: false, w: 0, h: 0, dpr: 1 };
    const g = canvas.getContext('2d');
    const insights = D.insights.map((i) => ({ t: i.moment.t, rank: i.rank, kind: i.kind }));
    const win = () => Core.viewWindow(S.t, end, S.span);
    const LAYOUT = { ins: [2, 20], cyc: [24, 18], cp: [46, 14], wait: [64, 12], axis: 84 };

    function size() {
      const r = el.getBoundingClientRect(); S.dpr = Math.min(2, window.devicePixelRatio || 1);
      S.w = Math.max(10, r.width); S.h = Math.max(10, r.height);
      canvas.width = Math.round(S.w * S.dpr); canvas.height = Math.round(S.h * S.dpr);
      draw();
    }
    function draw() {
      const [a, b] = win(), W = S.w, H = S.h, X = (t) => ((t - a) / (b - a)) * W;
      g.setTransform(S.dpr, 0, 0, S.dpr, 0, 0); g.clearRect(0, 0, W, H);
      for (const k of ['cyc', 'cp', 'wait']) { const [y, h] = LAYOUT[k]; g.fillStyle = C.lane; g.fillRect(0, y, W, h); }
      if (S.clip) { const x0 = X(S.clip[0]), x1 = X(S.clip[1]); g.fillStyle = '#dce06433'; g.fillRect(x0, 0, Math.max(2, x1 - x0), LAYOUT.axis); g.fillStyle = C.amarillo; g.fillRect(x0, 0, 2, LAYOUT.axis); g.fillRect(x1 - 2, 0, 2, LAYOUT.axis); }
      // cycles: alternating shades, low-confidence cycles dimmed
      const [cy, ch] = LAYOUT.cyc;
      D.cycles.forEach((c, i) => { if (c.end < a || c.start > b) return; g.fillStyle = c.clean ? (i % 2 ? C.menta : '#9fd9c7') : C.mentaLow; const x0 = X(c.start), x1 = X(c.end); g.fillRect(x0 + 0.5, cy, Math.max(1, x1 - x0 - 1), ch); });
      // CP captures
      const [py, ph] = LAYOUT.cp; g.fillStyle = C.blanco;
      for (const r of D.captures) { if (r.t < a || r.t > b) continue; g.fillRect(Math.round(X(r.t)) - 1, py, 2, ph); }
      // waits (amarillo) and queue episodes (hielo, low confidence)
      const [wy, wh] = LAYOUT.wait;
      g.fillStyle = C.hielo; g.globalAlpha = 0.55;
      for (const q of D.lanes.queue) { if (q[1] < a || q[0] > b) continue; const x0 = X(q[0]); g.fillRect(x0, wy + wh / 2, Math.max(1, X(q[1]) - x0), wh / 2); }
      g.globalAlpha = 1; g.fillStyle = C.amarillo;
      for (const w of D.waits) { if (w.e < a || w.s > b) continue; const x0 = X(w.s); g.fillRect(x0, wy, Math.max(2, X(w.e) - x0), wh / 2 + 1); }
      // insight pins
      const [iy, ih] = LAYOUT.ins, r = ih / 2;
      for (const p of insights) {
        if (p.t < a || p.t > b) continue; const x = X(p.t), y = iy + r;
        g.beginPath(); g.moveTo(x, y - r); g.lineTo(x + r, y); g.lineTo(x, y + r); g.lineTo(x - r, y); g.closePath();
        g.fillStyle = p.kind === 'top' ? C.amarillo : '#ffffff'; g.fill(); g.strokeStyle = C.noche; g.lineWidth = 1; g.stroke();
        if (p.kind === 'top') { g.fillStyle = C.noche; g.font = '600 12px Onest, system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(String(p.rank), x, y + 0.5); }
      }
      // axis: plant-time ticks
      const span = b - a, step = span > 3600 ? 900 : span > 1500 ? 300 : 120;
      g.fillStyle = C.hielo; g.font = '500 12px "JetBrains Mono", ui-monospace, monospace'; g.textBaseline = 'top'; g.textAlign = 'center';
      const p0 = Core.secs(recs[0].plantStart);
      for (let s = Math.ceil((p0 + a) / step) * step; s <= p0 + b; s += step) {
        const x = X(s - p0); if (x < 18 || x > W - 18) continue;
        g.fillRect(Math.round(x), LAYOUT.axis - 2, 1, 4); g.fillText(Core.hms(s).slice(0, 5), x, LAYOUT.axis + 4);
      }
      // cursor
      const x = X(S.t);
      g.fillStyle = C.blanco; g.fillRect(Math.round(x) - 1, 0, 2, LAYOUT.axis);
      g.beginPath(); g.arc(x, LAYOUT.axis, 5, 0, 6.2832); g.fillStyle = C.amarillo; g.fill(); g.strokeStyle = C.noche; g.lineWidth = 1.5; g.stroke();
    }
    function set(t) {
      S.t = t; const v = Math.round(t);
      el.setAttribute('aria-valuenow', String(v));
      el.setAttribute('aria-valuetext', `${Core.plantClock(recs, t)} ${I18n.t('video.plantTime')}`);
      draw();
    }
    function tAt(clientX) { const r = el.getBoundingClientRect(), [a, b] = win(); return Core.clamp(a + ((clientX - r.left) / r.width) * (b - a), 0, end - 0.1); }
    let frozen = null;
    el.addEventListener('pointerdown', (e) => { S.drag = true; frozen = win(); el.setPointerCapture(e.pointerId); const t = tAt(e.clientX); set(t); onScrub && onScrub(t); });
    el.addEventListener('pointermove', (e) => { if (!S.drag) return; const r = el.getBoundingClientRect(), [a, b] = frozen; const t = Core.clamp(a + ((e.clientX - r.left) / r.width) * (b - a), 0, end - 0.1); S.t = t; draw(); onScrub && onScrub(t); });
    const up = (e) => { if (!S.drag) return; S.drag = false; const r = el.getBoundingClientRect(), [a, b] = frozen; const t = Core.clamp(a + ((e.clientX - r.left) / r.width) * (b - a), 0, end - 0.1); frozen = null; set(t); onSeek(t); };
    el.addEventListener('pointerup', up); el.addEventListener('pointercancel', () => { S.drag = false; frozen = null; });
    el.addEventListener('keydown', (e) => {
      const step = { ArrowLeft: -5, ArrowRight: 5, ArrowDown: -5, ArrowUp: 5, PageDown: -60, PageUp: 60 }[e.key];
      let t = null;
      if (step != null) t = S.t + step * (e.shiftKey ? 6 : 1);
      else if (e.key === 'Home') t = 0; else if (e.key === 'End') t = end - 1;
      if (t == null) return;
      e.preventDefault(); t = Core.clamp(t, 0, end - 0.1); set(t); onSeek(t);
    });
    new ResizeObserver(size).observe(el);
    return { set, draw, size, setSpan(s) { S.span = s; draw(); }, setClip(c) { S.clip = c; draw(); }, get dragging() { return S.drag; }, window: win };
  }
  return { create };
})();

/* ---- overlays.js */
/* Optional overlays drawn over the video: zones (cola, teclado CP), stations (Puesto A, Puesto B with live state) and
   skeletons (body pose, loaded on demand from pose-recNN.bin). All ON by default since v0.1.3. Skeleton edges follow vision-core.js. */
const Overlays = (function () {
  'use strict';
  const VW = 1440, VH = 810, FPS = 15, TOL = 3; // pose sampled at 5 fps, frame numbers at 15 fps; hold nearest within 0.2 s
  const EDGES = [[15, 13], [13, 11], [16, 14], [14, 12], [11, 12], [5, 11], [6, 12], [5, 6], [5, 7], [6, 8], [7, 9], [8, 10], [0, 1], [0, 2], [1, 3], [2, 4], [3, 5], [4, 6],
    [15, 17], [15, 18], [15, 19], [16, 20], [16, 21], [16, 22]]; // body + feet (v0.0.1 BODY_EDGES)
  // Hands: 21 keypoints each (wrist, then 4 joints per finger), left at 23, right at 44; joined to the wrists 9 and 10.
  const CHAINS = [[0, 1, 2, 3, 4], [0, 5, 6, 7, 8], [0, 9, 10, 11, 12], [0, 13, 14, 15, 16], [0, 17, 18, 19, 20]];
  const handEdges = (base) => CHAINS.flatMap((c) => c.slice(1).map((k, i) => [base + c[i], base + k]));
  const HAND_EDGES = [...handEdges(23), ...handEdges(44), [9, 23], [10, 44]];
  const COL = { A: '#7fccb4', B: '#dce064', cola: '#bfe6da', teclado: '#dce064' };
  const tr = (k, v) => I18n.t(k, v);
  const bState = (s) => (s ? tr(`state.b.${s}`) : null), aState = (s) => (s ? tr(`state.a.${s}`) : null);
  function create({ canvas, stage, data, player, onStatus }) {
    const D = data, g = canvas.getContext('2d');
    const L = { zonas: true, puestos: true, esqueletos: true };
    const pose = { manifest: undefined, recs: new Map() };
    let dpr = 1, W = 0, H = 0, pending = false;

    function resize() { const r = stage.getBoundingClientRect(); dpr = Math.min(2, window.devicePixelRatio || 1); W = r.width; H = r.height; canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); request(); }
    function rect() { const s = Math.min(W / VW, H / VH); return { x: (W - VW * s) / 2, y: (H - VH * s) / 2, s }; }
    const P = (R, nx, ny) => [R.x + nx * VW * R.s, R.y + ny * VH * R.s];
    function request() { if (pending) return; pending = true; requestAnimationFrame(() => { pending = false; draw(); }); }

    function label(text, x, y, color, sub) {
      const fs = W < 560 ? 11 : 13, h = W < 560 ? 20 : 24;
      g.font = `600 ${fs}px Onest, system-ui, sans-serif`;
      const w1 = g.measureText(text).width; let w2 = 0;
      if (sub) { g.font = '500 12px Onest, system-ui, sans-serif'; w2 = g.measureText(sub).width + 8; }
      const w = w1 + w2 + 18; x = Core.clamp(x, 4, W - w - 4); y = Core.clamp(y, 4, H - h - 4);
      g.fillStyle = '#14133fe6'; roundRect(x, y, w, h, h / 2); g.fill();
      g.fillStyle = color; g.beginPath(); g.arc(x + 10, y + h / 2, 4, 0, 6.2832); g.fill();
      g.fillStyle = '#f6f9f8'; g.font = `600 ${fs}px Onest, system-ui, sans-serif`; g.textBaseline = 'middle'; g.textAlign = 'left'; g.fillText(text, x + 18, y + h / 2 + 0.5);
      if (sub) { g.fillStyle = '#cdd6e8'; g.font = '500 12px Onest, system-ui, sans-serif'; g.fillText(sub, x + 18 + w1 + 8, y + h / 2 + 0.5); }
    }
    function roundRect(x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
    function poly(R, pts, fill, stroke, dash) {
      g.beginPath();
      for (let k = 0; k < pts.length; k += 2) { const [x, y] = P(R, pts[k], pts[k + 1]); if (k) g.lineTo(x, y); else g.moveTo(x, y); }
      g.closePath(); if (fill) { g.fillStyle = fill; g.fill(); }
      g.setLineDash(dash || []); g.strokeStyle = stroke; g.lineWidth = 2; g.stroke(); g.setLineDash([]);
      const xs = [], ys = []; for (let k = 0; k < pts.length; k += 2) { const [x, y] = P(R, pts[k], pts[k + 1]); xs.push(x); ys.push(y); }
      return { x: Math.min(...xs), y: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
    }

    function draw() {
      g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, canvas.width, canvas.height);
      if (!L.zonas && !L.puestos && !L.esqueletos) return;
      if (player.isLoading() || player.recording() < 0) return;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const R = rect(), t = player.position(), small = W < 560;
      if (L.puestos) {
        const bs = Core.laneAt(D.lanes.B, t), as = Core.laneAt(D.lanes.A, t);
        const b = poly(R, D.zones.B, '#dce06414', COL.B, [8, 6]);
        const a = poly(R, D.zones.A, '#7fccb414', COL.A, [8, 6]);
        label(tr('station', { id: 'B' }), b.x + 8, b.y + 8, COL.B, small ? null : bState(bs));
        label(tr('station', { id: 'A' }), a.x + 8, a.y - 32, COL.A, small ? null : aState(as));
      }
      if (L.zonas) {
        const q = Core.laneAt(D.lanes.queue, t);
        const c = poly(R, D.zones.cola, q ? '#bfe6da59' : '#bfe6da1f', COL.cola);
        const k = poly(R, D.zones.teclado, '#dce06433', COL.teclado);
        label(tr('live.queue'), c.x + 8, c.y2 - 32, COL.cola, small ? null : (q ? tr('live.queueOn') : tr('live.queueOff')));
        label(tr('ov.keypad'), k.x2 + 6, k.y + 4, COL.teclado);
      }
      if (L.esqueletos) drawPose(R, t);
    }

    // ---- pose
    async function manifest() {
      if (pose.manifest !== undefined) return pose.manifest;
      try { const r = await fetch('pose-manifest.json'); pose.manifest = r.ok ? await r.json() : null; } catch { pose.manifest = null; }
      return pose.manifest;
    }
    function recPose(rec) {
      if (pose.recs.has(rec)) return pose.recs.get(rec);
      const e = { ready: false, A: null, B: null };
      pose.recs.set(rec, e);
      manifest().then(async (m) => {
        const info = m && m.recs[String(rec)];
        if (!info) { e.error = true; status(); return; }
        try {
          const buf = await (await fetch(info.file)).arrayBuffer();
          for (const lab of ['A', 'B']) {
            const { offset, n } = info.labels[lab];
            e[lab] = { frames: new Uint16Array(buf, offset, n), pts: new Uint16Array(buf, offset + n * 2, n * m.joints * 2) };
          }
          e.ready = true;
        } catch { e.error = true; }
        status(); request();
      });
      return e;
    }
    function nearest(frames, f) {
      let lo = 0, hi = frames.length;
      while (lo < hi) { const m = (lo + hi) >> 1; if (frames[m] < f) lo = m + 1; else hi = m; }
      let best = -1, bd = TOL + 1;
      for (const j of [lo - 1, lo]) if (j >= 0 && j < frames.length && Math.abs(frames[j] - f) < bd) { bd = Math.abs(frames[j] - f); best = j; }
      return best;
    }
    function drawPose(R, t) {
      const rec = player.recording() + 1, e = recPose(rec);
      if (!e.ready) return;
      const v = player.active(), f = Math.round(v.currentTime * FPS), J = pose.manifest.joints, hands = J >= 65;
      for (const lab of ['A', 'B']) {
        const P2 = e[lab]; const j = nearest(P2.frames, f); if (j < 0) continue;
        const base = j * J * 2, pt = (k) => { const x = P2.pts[base + 2 * k], y = P2.pts[base + 2 * k + 1]; return x === 65535 ? null : P(R, x / 10000, y / 10000); };
        g.strokeStyle = COL[lab]; g.lineWidth = Math.max(2, R.s * 3.2); g.lineCap = 'round'; g.globalAlpha = 0.95;
        g.beginPath();
        for (const [a, b] of EDGES) { const p = pt(a), q = pt(b); if (p && q) { g.moveTo(p[0], p[1]); g.lineTo(q[0], q[1]); } }
        g.stroke();
        if (hands) {
          g.lineWidth = Math.max(1.6, R.s * 2.2); g.beginPath();
          for (const [a, b] of HAND_EDGES) { const p = pt(a), q = pt(b); if (p && q) { g.moveTo(p[0], p[1]); g.lineTo(q[0], q[1]); } }
          g.stroke();
          g.fillStyle = COL[lab];
          for (let k = 23; k < 65; k++) { const p = pt(k); if (p) { g.beginPath(); g.arc(p[0], p[1], Math.max(1.5, R.s * 2), 0, 6.2832); g.fill(); } }
          g.lineWidth = Math.max(2, R.s * 3.2);
        }
        g.fillStyle = '#14133f';
        for (let k = 0; k < 17; k++) { const p = pt(k); if (p) { g.beginPath(); g.arc(p[0], p[1], Math.max(2.5, R.s * 4), 0, 6.2832); g.fill(); g.stroke(); } }
        g.globalAlpha = 1;
      }
    }
    function status() {
      const parts = [];
      if (L.esqueletos) { const e = pose.recs.get(player.recording() + 1); parts.push(!e || (!e.ready && !e.error) ? tr('ov.loading') : e.error ? tr('ov.error') : tr('ov.ready')); }
      if (L.zonas || L.puestos) parts.push(tr('ov.fixed'));
      onStatus && onStatus(parts.join(' '));
    }
    function set(name, on) { L[name] = !!on; if (name === 'esqueletos' && on && player.recording() >= 0) recPose(player.recording() + 1); status(); request(); }

    // Redraw on every presented frame while any layer is on.
    const hasRVFC = 'requestVideoFrameCallback' in HTMLVideoElement.prototype;
    function follow(v) {
      if (hasRVFC) { const cb = () => { if ((L.zonas || L.puestos || L.esqueletos) && v === player.active()) draw(); v.requestVideoFrameCallback(cb); }; v.requestVideoFrameCallback(cb); }
      v.addEventListener('seeked', request); v.addEventListener('timeupdate', request);
    }
    new ResizeObserver(resize).observe(stage);
    return { set, draw: request, follow, status, layers: L, resize, poseState: (rec) => pose.recs.get(rec) || null };
  }
  return { create };
})();

/* ---- dashboard.js */
/* Dashboard (Panel): top insights, trust band, data cards, mock (ejemplo) panel, glossary and tooltips.
   render(D) takes the localized data (I18n.localize) and may run again on a language switch: listeners bind once,
   open "How did we measure this?" panels and a playing mock animation are kept. */
const Dashboard = (function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const t = (k, v) => I18n.t(k, v);
  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v; else if (k === 'html') e.innerHTML = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? '' : v);
    }
    for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
    return e;
  }
  const ICON = {
    video: '<svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true"><path d="M2 5.5A1.5 1.5 0 0 1 3.5 4h9A1.5 1.5 0 0 1 14 5.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 14.5zM15 8l3.2-2v8L15 12z" fill="currentColor"/></svg>',
    cp: '<svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true"><path d="M4 3h12a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm2 3v2h2V6zm3 0v2h2V6zm3 0v2h2V6zM6 9v2h2V9zm3 0v2h2V9zm3 0v2h2V9zm-6 3v2h8v-2z" fill="currentColor"/></svg>',
    play: '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>',
  };
  const TIP_KEYS = ['sam', 'eficiencia', 'takt', 'restriccion', 'ciclo', 'cola', 'registro', 'confianza'];
  let DATA = null;
  function gloss(key) {
    if (!TIP_KEYS.includes(key)) return null;
    const M = DATA.mock, vars = { product: DATA.meta.product, sam: Core.num(DATA.meta.sam), p: Core.pct(100), target: M.target, takt: Core.num(M.takt) };
    return [t(`tip.${key}.t`), t(`tip.${key}.d`, vars)];
  }

  function sourceChip(src) {
    const icon = src.kind === 'cp' ? ICON.cp : ICON.video;
    return el('span', { class: 'chip src', title: src.detail }, el('span', { html: icon, class: 'row', style: 'display:inline-flex' }), t('src', { label: src.label }));
  }
  function confMeter(c) {
    const n = Core.CONF[c.level] || 1;
    return el('span', { class: 'conf', title: c.note || null },
      el('span', { class: 'bars', 'aria-hidden': 'true' }, [1, 2, 3].map((k) => el('i', { class: k <= n ? 'on' : '' }))),
      t(`conf.${c.level}`));
  }
  function bigNumber(ins) {
    return el('p', { class: 'big' }, el('span', { class: 'n' }, ins.number, ins.unit && ins.unit !== 'min' ? el('span', { class: 'u' }, ins.unit === '%' ? (Core.getLang() === 'es' ? '\u00a0%' : '%') : `\u00a0${ins.unit}`) : null), el('span', { class: 'lbl' }, ins.numberLabel));
  }
  function proofStrip(ins) {
    if (!ins.proof.length) return null;
    return el('figure', { class: 'stack gap-2', style: 'margin:0' },
      el('div', { class: 'proof' }, ins.proof.map((f) => el('button', { type: 'button', 'aria-label': t('proof.aria', { alt: f.alt, time: f.plant }), onclick: () => go(Core.videoHash({ t: f.t - 2, from: ins.id, lang: Core.getLang() })) },
        el('img', { src: f.src, alt: '', width: 480, height: 304, loading: 'lazy', decoding: 'async' }),
        el('span', { class: 'pt' }, f.plant), el('span', { class: 'pc' }, f.caption)))),
      el('figcaption', { class: 'proof-cap' }, t('proof.cap')));
  }
  function howDetails(ins) {
    return el('details', { class: 'how', 'data-how': ins.id }, el('summary', {}, t('ins.how')),
      el('div', { class: 'body' }, el('p', { style: 'margin:0' }, ins.method), el('p', { style: 'margin:0' }, el('b', {}, t('src.k')), `${ins.source.label}, ${ins.source.detail}. `, el('b', {}, t('conf.k')), ins.confidence.note),
        ins.caveats.length ? el('ul', {}, ins.caveats.map((c) => el('li', {}, c))) : null));
  }
  function videoButton(ins, cls) {
    const [a, b] = ins.moment.plant;
    return el('div', { class: 'ins-actions' },
      el('a', { class: `btn ${cls || 'btn-ink'}`, href: Core.insightHash(ins, Core.getLang()), 'data-insight': ins.id }, el('span', { html: ICON.play, style: 'display:inline-flex' }), t('ins.see')),
      el('p', { class: 'cap' }, t('ins.clip', { range: Core.clipLabel(a, b) })));
  }
  function insightCard(ins) {
    return el('article', { class: 'glass card insight', id: `hallazgo-${ins.id}`, 'aria-labelledby': `t-${ins.id}` },
      el('div', { class: 'ins-top' }, el('span', { class: 'rank', 'aria-label': t('ins.rankAria', { n: ins.rank }) }, String(ins.rank)), sourceChip(ins.source), confMeter(ins.confidence)),
      el('h3', { class: 'h3', id: `t-${ins.id}` }, ins.headline),
      bigNumber(ins), el('p', { class: 'p' }, ins.context), proofStrip(ins),
      ins.idea ? el('p', { class: 'idea' }, el('b', {}, t('ins.idea')), ins.idea) : null, videoButton(ins), howDetails(ins));
  }

  function renderContext(D) {
    const m = D.meta;
    $('ctx').replaceChildren(...[
      el('li', {}, el('b', {}, t('ctx.module', { id: m.module.id })), ` · ${m.module.name}`), el('li', {}, `${m.plant} · ${Core.date(m.date)}`),
      el('li', {}, t('ctx.video', { a: m.plantStart.slice(0, 5), b: m.plantEnd.slice(0, 5) })), el('li', {}, `${m.product} · `, tipBtn('sam', `SAM ${Core.num(m.sam)} min`))]);
  }
  function renderTop(D) { $('top-insights').replaceChildren(...D.insights.filter((i) => i.kind === 'top').map(insightCard)); }
  function renderTrust(D) {
    const ins = D.insights.find((i) => i.kind === 'trust'), k = D.kpis.keypad;
    const [hits, n] = ins.number.split('/');
    $('trust').replaceChildren(
      el('div', { class: 'stack gap-4', id: `hallazgo-${ins.id}` },
        el('div', { class: 'row gap-2' }, sourceChip(ins.source), confMeter(ins.confidence)),
        el('h2', { class: 'h2', id: 'trust-title' }, t('trust.title')),
        el('p', { class: 'trust-num' }, el('span', { class: 'num' }, hits), el('span', { class: 'num-of' }, t('trust.of', { n }))),
        el('p', { class: 'lead' }, ins.context),
        el('ul', { class: 'trust-facts' },
          el('li', {}, el('b', {}, `${Core.num(Math.abs(k.median))} s`), el('span', {}, t('trust.f1'))),
          el('li', {}, el('b', {}, Core.pct(k.chance * 100)), el('span', {}, t('trust.f2'))),
          el('li', {}, el('b', {}, '3 s'), el('span', {}, t('trust.f3'))),
          el('li', {}, el('b', {}, `${D.kpis.cycles}`), el('span', {}, t('trust.f4', { n: D.kpis.captures })))),
        el('div', { class: 'btn-row' }, el('a', { class: 'btn btn-glow', href: Core.insightHash(ins, Core.getLang()) }, el('span', { html: ICON.play, style: 'display:inline-flex' }), t('trust.see')))),
      el('div', { class: 'stack gap-3' }, proofStrip(ins), howDetails(ins)));
    for (const d of $('trust').querySelectorAll('.how')) d.classList.add('how-dark');
  }

  function renderEfficiency(D) {
    const H = D.hourly, max = 140, video = new Set(['13:00', '14:00']);
    const bestEff = Math.max(...H.rows.filter((r) => !r.flags.includes('burst')).map((r) => r.eff));
    $('eff-chips').replaceChildren(sourceChip({ kind: 'cp', label: 'CP (EnPiso)', detail: t('eff.srcDetail', { n: H.total }) }), confMeter({ level: 'media', note: t('eff.confNote') }));
    const cols = H.rows.map((r) => {
      const h = Math.min(r.eff, max) / max * 100, onVideo = video.has(r.label);
      const flags = r.flags.includes('burst') ? '*' : '';
      const attrs = { class: `bcol ${r.flags.map((f) => 'f-' + f).join(' ')} ${r.eff === bestEff ? 'best' : ''}`, 'aria-label': `${t('eff.barAria', { h: r.label, pct: Core.pct(r.eff), n: r.pieces })}${r.notes.length ? '. ' + r.notes.join(' ') : ''}${onVideo ? '. ' + t('eff.barOpen') : ''}` };
      const kids = [el('span', { class: 'v', 'aria-hidden': 'true' }, String(Math.round(r.eff)), el('small', {}, '%'), flags ? el('sup', {}, flags) : null), el('span', { class: 'bar', style: `height:calc(var(--h) * ${(h / 100).toFixed(4)})`, 'aria-hidden': 'true' }), el('span', { class: 'hr', 'aria-hidden': 'true' }, r.label.slice(0, 2) + 'h'),
        el('span', { class: 'fl', 'aria-hidden': 'true' }, onVideo ? el('span', { class: 'cam', html: ICON.video + `<span class="t">${t('eff.cam')}</span>` }) : `${r.pieces}`)];
      if (onVideo) {
        const tt = Math.max(0, Core.plantToT(D.playlist.recordings, r.label + ':00', D.playlist.end) ?? 0);
        return el('a', { ...attrs, href: Core.videoHash({ t: tt + 2, from: 'eficiencia-hora', lang: Core.getLang() }) }, kids);
      }
      return el('div', { ...attrs, role: 'img' }, kids);
    });
    const avgY = (H.avg / max) * 100, stdY = (100 / max) * 100;
    const chart = el('div', { class: 'bars-h', style: `--n:${H.rows.length}`, role: 'group', 'aria-label': t('eff.chartAria', { pct: Core.pct(H.avg) }) }, ...cols);
    $('eff-chart').replaceChildren(chart);
    // reference lines are positioned in px against the bar area height
    const place = () => {
      chart.querySelectorAll('.ref').forEach((r) => r.remove());
      const bar = chart.querySelector('.bar'); if (!bar || !chart.offsetHeight) return;
      const hpx = parseFloat(getComputedStyle(chart).getPropertyValue('--h')) || 220, base = chart.getBoundingClientRect().bottom - bar.getBoundingClientRect().bottom;
      chart.prepend(el('div', { class: 'ref std', style: `bottom:${base + hpx * stdY / 100}px`, 'aria-hidden': 'true' }),
        el('div', { class: 'ref', style: `bottom:${base + hpx * avgY / 100}px`, 'aria-hidden': 'true' }));
    };
    Dashboard._placeRefs = place;
    requestAnimationFrame(place);
    $('eff-legend').replaceChildren(
      el('li', {}, el('i', { class: 'std' }), t('eff.lgStd', { p: Core.pct(100) })), el('li', {}, el('i'), t('eff.lgAvg', { pct: Core.pct(H.avg) })),
      el('li', {}, el('i', { class: 'sw be' }), t('eff.lgBest')), el('li', {}, el('i', { class: 'sw lt' }), t('eff.lgLight')),
      el('li', {}, el('i', { class: 'sw bu' }), t('eff.lgBurst')), el('li', {}, t('eff.lgPieces')));
    $('eff-notes').replaceChildren(...H.rows.filter((r) => r.notes.length).map((r) => el('li', {}, el('span', { class: 'k' }, r.label), r.notes.join(' '))));
    const v = { sam: Core.num(H.sam), ops: H.operators };
    $('eff-assume').replaceChildren(el('span', {}, el('b', {}, t('eff.howK')), t('eff.how', v), el('b', {}, t('eff.assumeK')), t('eff.assume', v)));
  }

  function renderMinutes(D) {
    $('min-chips').replaceChildren(sourceChip({ kind: 'video', label: 'Video', detail: t('min.srcDetail', { n: D.meta.windowMin }) }), confMeter({ level: 'media', note: t('min.confNote') }));
    $('min-lead').textContent = t('min.lead', { n: D.meta.windowMin, a: D.meta.plantStart.slice(0, 5), b: D.meta.plantEnd.slice(0, 5) });
    const row = (title, conf, parts, note) => el('div', { class: `hb-row ${conf === 'baja' ? 'lowconf' : ''}` },
      el('div', { class: 'row-between' }, el('h4', {}, title), el('span', { class: 'cap' }, t(`conf.${conf}`))),
      el('div', { class: 'hbar', role: 'img', 'aria-label': `${title}: ` + parts.map((p) => `${p.label} ${Core.num(p.min)} min`).join(', ') }, parts.map((p) => el('span', { class: `k-${p.key}`, style: `width:${p.share * 100}%` }))),
      el('ul', { class: 'legend' }, parts.map((p) => el('li', {}, el('i', { class: `k-${p.key}` }), p.label, el('b', {}, `${Core.num(p.min)} min`)))),
      note ? el('p', { class: 'cap', style: 'margin-top:6px' }, note) : null);
    $('min-bars').replaceChildren(row(t('station', { id: 'B' }), 'media', D.bTime), row(t('station', { id: 'A' }), 'baja', D.aTime, t('min.aNote')));
  }

  function renderRestriction(D) {
    const k = D.kpis, max = Math.max(k.queue, k.bWait, 1);
    $('res-chips').replaceChildren(sourceChip({ kind: 'video', label: 'Video', detail: t('res.srcDetail', { n: k.clean }) }), confMeter({ level: 'media', note: t('res.confNote') }));
    $('res-body').replaceChildren(
      el('p', { class: 'cap', style: 'margin:0' }, t('res.pre')),
      el('p', { class: 'res-big' }, t('res.big')),
      el('p', { class: 'p' }, t('res.p')),
      el('div', { class: 'cmp' },
        el('div', { class: 'r' }, el('span', { class: 't' }, t('res.r1')), el('b', {}, `${Math.round(k.queue)} s`), el('span', { class: 'track' }, el('span', { style: `width:${k.queue / max * 100}%` }))),
        el('div', { class: 'r b2' }, el('span', { class: 't' }, t('res.r2')), el('b', {}, `${Math.round(k.bWait)} s`), el('span', { class: 'track' }, el('span', { style: `width:${Math.max(2, k.bWait / max * 100)}%` })))),
      el('p', { class: 'cap' }, t('res.cap')),
      el('div', { class: 'soon' }, el('span', { class: 'st-next' }, t('soon')), el('span', {}, t('res.soonText'), el('a', { class: 'link', href: '#ejemplo', onclick: (e) => { e.preventDefault(); $('ejemplo').scrollIntoView({ behavior: 'smooth' }); } }, t('res.seeExample')))));
  }

  function renderStations(D) {
    const [B, A] = D.stations;
    $('st-chips').replaceChildren(sourceChip({ kind: 'video', label: 'Video', detail: t('st.srcDetail') }), confMeter({ level: 'media', note: t('min.confNote') }));
    const soon = () => el('span', { class: 'st-next' }, t('soon'));
    const card = (s, conf, rows) => el('section', { class: `station ${conf === 'baja' ? 'low' : ''}`, 'aria-label': s.name },
      el('div', { class: 'row-between' }, el('h4', {}, s.name, el('small', {}, s.machine)), confMeter({ level: conf, note: '' })),
      el('dl', {}, rows.map(([k, v, sub]) => el('div', {}, el('dt', {}, k), el('dd', {}, v, sub ? el('small', {}, sub) : null)))));
    $('st-cards').replaceChildren(
      card(B, 'media', [[t('st.sewPace'), t('st.perHour', { n: Math.round(B.perHourSew) }), t('st.sewEach', { n: Math.round(B.sew) })], [t('st.realPace'), t('st.perHour', { n: Math.round(B.perHourCycle) }), t('st.cycleWith', { n: Math.round(B.cycle) })],
        [t('st.busy'), Core.pct(B.busy * 100), t('st.ofRecorded')], [t('st.wait'), `${Math.round(B.wait)} s`, t('st.perPiece')]]),
      card(A, 'baja', [[t('st.sewPace'), soon()], [t('st.supply'), `${Math.round(A.supply)} s`, t('st.between')], [t('st.seat'), Core.pct(A.busy * 100), t('st.notAlways')], [t('st.wait'), soon()]]));
    $('st-note').textContent = t('st.note', { n: D.kpis.clean });
  }

  function renderReview(D) {
    $('review').replaceChildren(...D.insights.filter((i) => i.kind === 'review').map((ins) => el('article', { class: 'solid card review-card', id: `hallazgo-${ins.id}` },
      el('div', { class: 'ins-top' }, sourceChip(ins.source), confMeter(ins.confidence)), el('h4', { class: 'h3', style: 'margin:0' }, ins.headline), bigNumber(ins), el('p', { class: 'p' }, ins.context),
      ins.idea ? el('p', { class: 'cap' }, ins.idea) : null, videoButton(ins, 'btn-soft'))));
  }

  function renderMock(D) {
    const M = D.mock;
    $('mock-label').textContent = M.label + t('mock.labelExtra');
    const maxSec = Math.max(...M.zones.map((z) => z.sec), M.takt) * 1.12, bott = M.zones.reduce((a, b) => (b.sec > a.sec ? b : a));
    $('mock-zones').replaceChildren(
      el('div', { class: 'zbars' }, M.zones.map((z) => el('div', { class: `zbar ${z === bott ? 'bott' : ''}` },
        el('div', { class: 'row-between' }, el('span', {}, el('b', {}, z.name), z === bott ? el('span', { class: 'chip chip-hl', style: 'margin-left:8px' }, t('mock.bottleneck')) : null), el('span', { class: 'data' }, t('mock.zoneData', { sec: z.sec, sam: Core.num(z.sam, 2) }))),
        el('div', { class: 'trk', role: 'img', 'aria-label': t('mock.zoneAria', { name: z.name, sec: z.sec, takt: Core.num(M.takt) }) },
          el('div', { class: 'fill', style: `width:${z.sec / maxSec * 100}%` }, el('span', { class: 'sew', style: `width:${z.sew / z.sam * 100}%` }), z.extra ? el('span', { class: 'ext', style: `width:${z.extra / z.sam * 100}%` }) : null),
          el('div', { class: 'takt', style: `left:${M.takt / maxSec * 100}%` })),
        z.extra ? el('p', { class: 'cap', style: 'margin-top:4px' }, t('mock.zoneExtra', { sew: Core.num(z.sew, 2), extra: Core.num(z.extra, 2) })) : null))),
      el('p', { class: 'p', style: 'margin-top:14px' }, t('mock.taktNote', { takt: Core.num(M.takt), target: M.target, th: Core.num(M.theoretical), bal: Core.pct(M.balance) })),
      el('div', { class: 'stack gap-3', style: 'margin-top:18px' }, el('h4', { class: 'need-h' }, t('mock.needTitle')),
        el('ul', { class: 'checks' }, el('li', {}, t('mock.need1')), el('li', {}, t('mock.need2')), el('li', {}, t('mock.need3')))));
    const maxSam = M.ops[0].sam;
    $('mock-ops').replaceChildren(...M.ops.map((o, i) => el('li', { class: i === 0 ? 'top' : '' },
      el('span', { class: 'nm' }, o.name, el('small', {}, `${o.machine} · ${t('station', { id: o.zone })}`)), el('span', { class: 's' }, `${Core.num(o.sam, 2)} min`),
      el('span', { class: 'tr', 'aria-hidden': 'true' }, el('span', { style: `width:${o.sam / maxSam * 100}%` })))));
    $('pl-a').textContent = t('station', { id: 'A' }); $('pl-b').textContent = t('station', { id: 'B' }); $('pl-100').textContent = Core.pct(100);
    const top = 160, x100 = `${100 / top * 100}%`;
    $('mock-hourly').replaceChildren(...M.hourly.map((r) => el('li', { class: r.flags.includes('burst') ? 'burst' : '', style: `--x100:${x100}`, 'aria-label': t('mock.hourAria', { h: r.label, a: Core.pct(r.A), b: Core.pct(r.B), m: Core.pct(r.module) }) },
      el('span', { class: 'h', 'aria-hidden': 'true' }, r.label + (r.flags.includes('burst') ? '*' : '')),
      el('span', { class: 'a', 'aria-hidden': 'true' }, el('span', { style: `width:${Math.min(r.A, top) / top * 100}%` })), el('span', { class: 'va', 'aria-hidden': 'true' }, Core.pct(r.A)),
      el('span', { class: 'b', 'aria-hidden': 'true' }, el('span', { style: `width:${Math.min(r.B, top) / top * 100}%` })), el('span', { class: 'vb', 'aria-hidden': 'true' }, Core.pct(r.B)))));
    $('mock-hourly-note').textContent = t('mock.hourlyNote', { a: Core.num(M.zones[0].sew, 2), b: Core.num(M.zones[1].sew, 2) });
    const box = $('mock-video-box'), old = box.querySelector('video');
    // keep the animation element (and its playback position) when only the language changes
    if (D.meta.mockVideo && old) old.setAttribute('aria-label', t('mock.videoAria'));
    else if (D.meta.mockVideo) box.replaceChildren(el('video', { src: D.meta.mockVideo, poster: 'mock-ficha-poster.jpg', controls: true, muted: true, playsinline: true, preload: 'none', 'aria-label': t('mock.videoAria') }));
    else box.replaceChildren(el('img', { src: 'mock-ficha-poster.jpg', alt: t('mock.posterAlt'), loading: 'lazy' }));
  }

  function renderGlossary() {
    $('glossary').replaceChildren(...TIP_KEYS.map((k) => { const g = gloss(k); return el('div', {}, el('dt', {}, g[0]), el('dd', {}, g[1])); }));
  }
  function renderFooter(D) {
    const m = $('ft-meta');
    m.textContent = t('ft.meta', { version: m.dataset.version, built: m.dataset.built, date: Core.date(D.meta.date, true) });
    $('ft-note').textContent = t('ft.note', { clock: D.meta.clockNote });
  }

  // ---- tooltips: one-line definitions on tap, hover or focus
  function tipBtn(key, text) { return el('button', { type: 'button', class: 'tip', 'data-tip': key }, text); }
  let tips = null;
  function initTips() {
    if (tips) { tips.hide(); return; }
    const pop = $('tip-pop'); let owner = null, shownAt = 0;
    const hide = () => { if (!owner) return; owner.removeAttribute('aria-describedby'); owner.setAttribute('aria-expanded', 'false'); owner = null; pop.hidden = true; };
    const show = (b) => {
      const g = gloss(b.dataset.tip); if (!g) return;
      if (owner && owner !== b) hide();
      if (owner !== b) shownAt = performance.now();
      owner = b; pop.replaceChildren(el('b', {}, g[0] + ': '), g[1]); pop.hidden = false;
      b.setAttribute('aria-describedby', 'tip-pop'); b.setAttribute('aria-expanded', 'true');
      place(b);
    };
    const place = (b) => {
      const r = b.getBoundingClientRect(), pw = pop.offsetWidth, x = Core.clamp(r.left + window.scrollX + r.width / 2 - pw / 2, 8 + window.scrollX, window.scrollX + document.documentElement.clientWidth - pw - 8);
      pop.style.left = `${x}px`; pop.style.top = `${r.bottom + window.scrollY + 8}px`;
    };
    document.addEventListener('click', (e) => { const b = e.target.closest('.tip'); if (b) { e.preventDefault(); if (owner === b && performance.now() - shownAt > 500) hide(); else show(b); } else if (!e.target.closest('#tip-pop')) hide(); });
    document.addEventListener('mouseover', (e) => { const b = e.target.closest('.tip'); if (b && matchMedia('(hover:hover)').matches) show(b); });
    document.addEventListener('mouseout', (e) => { const b = e.target.closest('.tip'); if (b && b === owner && matchMedia('(hover:hover)').matches) hide(); });
    document.addEventListener('focusin', (e) => { const b = e.target.closest && e.target.closest('.tip'); if (b) show(b); else hide(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
    window.addEventListener('resize', () => { owner && place(owner); Dashboard._placeRefs && Dashboard._placeRefs(); });
    tips = { hide };
  }

  let go = (h) => { location.hash = h; };
  function render(D, opts) {
    if (opts && opts.go) go = opts.go;
    DATA = D;
    const open = [...document.querySelectorAll('details.how[open]')].map((d) => d.dataset.how);
    renderContext(D); renderTop(D); renderTrust(D); renderEfficiency(D); renderMinutes(D); renderRestriction(D); renderStations(D); renderReview(D); renderMock(D); renderGlossary(); renderFooter(D);
    for (const id of open) { const d = document.querySelector(`details.how[data-how="${id}"]`); if (d) d.open = true; }
    initTips();
  }
  return { render, el };
})();

/* ---- app.js */
/* App: hash router (#/panel, #/video?t=..), video module wiring, moments list, deep links, the way back and the
   ES/EN switch. Switching language re-renders the panel text and relabels the video module in place: the <video>
   elements, the playback position, the clip, the layers and the filters are untouched. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const D = JSON.parse($('app-data').textContent);
  const t = (k, v) => I18n.t(k, v);
  const el = Dashboard.el;
  const recs = D.playlist.recordings.map((r) => ({ ...r }));
  const END = D.playlist.end;
  // Local test hook: on localhost, ?src=local serves the same recordings from the test server instead of R2.
  if (/^(127\.0\.0\.1|localhost)$/.test(location.hostname) && new URLSearchParams(location.search).get('src') === 'local') for (const r of recs) r.url = `/_local-video/${r.file}`;
  const errors = [];
  window.addEventListener('error', (e) => errors.push(String(e.message)));

  // ------------------------------------------------------------ language: URL, then saved choice, then browser
  let DL = null, byId = {};
  function localizeData() { DL = I18n.localize(D); byId = Object.fromEntries(DL.insights.map((i) => [i.id, i])); }
  const first = I18n.initial();
  I18n.set(first.lang, { persist: first.fromParam });
  localizeData();

  const go = (hash) => { if (location.hash === hash) route(); else location.hash = hash; };
  Dashboard.render(DL, { go });

  // ------------------------------------------------------------ video module (created on first visit)
  let V = null;
  function videoModule() {
    if (V) return V;
    const videos = [$('video0'), $('video1')];
    const S = { clip: null, from: null, lastHash: 0, span: 0, scrubbing: false, clipEnded: false, error: false };
    const kinds = new Set(['hallazgo']);
    let list = Core.moments(DL, t);
    let nowId = null;

    const player = Player.create({
      videos, recs, end: END,
      onTime: (tt) => tick(tt),
      onLoading: (v) => { $('loading').hidden = !v; },
      onClipEnd: () => { S.clipEnded = true; clipEndText(); },
      onPlayState: (playing) => { $('play').classList.toggle('playing', playing); playLabel(); if (playing) $('big-play').hidden = true; if (!playing) syncHash(true); },
      onError: () => { S.error = true; $('loading').hidden = false; $('loading').textContent = t('video.error'); },
    });
    const tl = Timeline.create({ el: $('timeline'), canvas: $('tl-canvas'), data: D, onSeek: (tt) => { S.scrubbing = false; player.seek(tt, !player.paused()); }, onScrub: (tt) => { S.scrubbing = true; showClock(tt); } });
    const ov = Overlays.create({ canvas: $('overlay'), stage: $('stage'), data: D, player, onStatus: (s) => { $('layer-status').textContent = s; } });
    videos.forEach((v) => ov.follow(v));
    $('loading').textContent = t('video.loading');

    function playLabel() { $('play').setAttribute('aria-label', t(player.paused() ? 'video.play' : 'video.pause')); }
    function clipEndText() { const p = document.createElement('span'); p.innerHTML = t('clip.end_html'); $('clip-txt').replaceChildren(...p.childNodes); }
    function showClock(tt) { const c = Core.plantClock(recs, tt); $('clock-now').textContent = c; $('time-badge').textContent = c; }
    function tick(tt) {
      if (!S.scrubbing && !tl.dragging) { tl.set(tt); showClock(tt); }
      live(tt); highlight(tt); syncHash(false);
    }
    function live(tt) {
      const b = Core.laneAt(D.lanes.B, tt), a = Core.laneAt(D.lanes.A, tt), q = Core.laneAt(D.lanes.queue, tt);
      const cyc = D.cycles.find((c) => tt >= c.start && tt < c.end);
      const items = [
        ['#dce064', t('station', { id: 'B' }), b ? t(`state.b.${b}`) : t('state.nd'), null],
        ['#7fccb4', t('station', { id: 'A' }), a ? t(`state.a.${a}`) : t('state.nd'), t('conf.low')],
        ['#bfe6da', t('live.queue'), q ? t('live.queueOn') : t('live.queueOff'), t('conf.low')],
      ];
      if (cyc) items.push(['#2e7d7c', t('live.cycle', { n: cyc.n }), cyc.cycle ? Core.dur(cyc.cycle) : t('live.incomplete'), cyc.cp.length ? t('live.withCp') : t('live.noCp')]);
      const key = items.map((i) => i.join('|')).join('/');
      if ($('live').dataset.key === key) return;
      $('live').dataset.key = key;
      $('live').replaceChildren(...items.map(([c, k, v, s]) => el('li', {}, el('i', { style: `background:${c}` }), el('span', {}, el('b', {}, k), el('span', { class: 'v' }, v)), s ? el('small', {}, s) : null)));
    }
    function renderMoments() {
      const ol = $('moments'), shown = list.filter((m) => kinds.has(m.kind)), scroll = ol.scrollTop;
      ol.replaceChildren(...(shown.length ? shown.map((m) => el('li', {}, el('button', { type: 'button', 'data-t': m.t, 'data-id': m.id, onclick: () => { clearClip(); player.seek(m.t, true); } },
        el('span', { class: 'mt' }, Core.plantClock(recs, m.t)), el('span', { class: 'ml' }, el('span', { class: `k ${m.kind}`, 'aria-hidden': 'true' }), m.label, el('small', {}, m.sub))))) : [el('li', { class: 'empty' }, t('moments.empty'))]));
      ol.scrollTop = scroll;
      nowId = null; highlight(player.position());
    }
    function highlight(tt) {
      const shown = list.filter((m) => kinds.has(m.kind));
      let cur = null; for (const m of shown) { if (m.t <= tt + 0.5) cur = m; else break; }
      const id = cur ? cur.id : null; if (id === nowId) return; nowId = id;
      for (const b of $('moments').querySelectorAll('button')) { const on = b.dataset.id === id; b.classList.toggle('now', on); if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); }
    }
    function layersParam() { return ['zonas', 'puestos', 'esqueletos'].filter((k) => ov.layers[k]); }
    const hash = () => Core.videoHash({ t: player.position(), clip: S.clip, from: S.from, capas: layersParam(), lang: I18n.lang });
    function syncHash(force) {
      if (currentRoute() !== 'video') return;
      const now = performance.now(); if (!force && now - S.lastHash < 2500) return; S.lastHash = now;
      history.replaceState(null, '', hash());
    }
    function clipText() {
      if (!S.clip) return;
      const ins = S.from && byId[S.from];
      $('clip-txt').replaceChildren(t('clip.label'), el('b', {}, Core.clipLabel(Core.plantClock(recs, S.clip[0]), Core.plantClock(recs, S.clip[1]))), ins ? ` · ${ins.headline}` : '');
    }
    function setClip(c) {
      S.clip = c; S.clipEnded = false; player.setClip(c); tl.setClip(c);
      $('clip-bar').hidden = !c;
      clipText();
    }
    function clearClip() { if (S.clip) { setClip(null); syncHash(true); } }
    function backCtx() {
      const ins = S.from ? byId[S.from] : null;
      if (ins) { $('back-ctx').replaceChildren(t('video.showing'), el('b', {}, ins.headline)); return; }
      const p = document.createElement('span');
      p.innerHTML = t('video.full_html', { a: D.meta.plantStart.slice(0, 5), b: D.meta.plantEnd.slice(0, 5) });
      $('back-ctx').replaceChildren(...p.childNodes);
    }

    $('play').onclick = () => player.toggle();
    $('big-play').onclick = () => player.play();
    $('stage').addEventListener('click', (e) => { if (e.target.closest('button')) return; player.toggle(); });
    $('back10').onclick = () => player.seek(player.position() - 10, !player.paused());
    $('fwd10').onclick = () => player.seek(player.position() + 10, !player.paused());
    for (const b of document.querySelectorAll('[data-speed]')) b.onclick = () => { player.setRate(Number(b.dataset.speed)); for (const o of document.querySelectorAll('[data-speed]')) o.setAttribute('aria-pressed', String(o === b)); };
    for (const b of document.querySelectorAll('[data-zoom]')) b.onclick = () => { S.span = b.dataset.zoom === '10' ? 600 : 0; tl.setSpan(S.span); for (const o of document.querySelectorAll('[data-zoom]')) o.setAttribute('aria-pressed', String(o === b)); };
    const jump = (dir) => { const m = Core.nextMoment(list, player.position(), dir, kinds.size ? kinds : null); if (m) { clearClip(); player.seek(m.t, !player.paused()); } };
    $('prev-mark').onclick = () => jump(-1); $('next-mark').onclick = () => jump(1);
    $('clip-replay').onclick = () => { if (S.clip) player.seek(S.clip[0], true); };
    $('clip-clear').onclick = () => { clearClip(); player.play(); };
    for (const b of document.querySelectorAll('.fchip')) b.onclick = () => { const k = b.dataset.kind; if (kinds.has(k)) kinds.delete(k); else kinds.add(k); b.setAttribute('aria-pressed', String(kinds.has(k))); renderMoments(); };
    for (const inp of document.querySelectorAll('[data-layer]')) inp.onchange = () => { ov.set(inp.dataset.layer, inp.checked); syncHash(true); };
    $('copy-link').onclick = async () => {
      const url = location.href.split('#')[0] + Core.videoHash({ t: player.position(), capas: layersParam(), lang: I18n.lang });
      try { await navigator.clipboard.writeText(url); $('copy-status').textContent = t('moments.copied', { time: Core.plantClock(recs, player.position()) }); }
      catch { $('copy-status').textContent = url; }
    };
    document.addEventListener('keydown', (e) => {
      if (currentRoute() !== 'video' || e.target.closest('input,textarea,select,[role=slider]') || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === ' ' && !e.target.closest('button,a')) { e.preventDefault(); player.toggle(); }
      else if (e.key === 'k' || e.key === 'K') player.toggle();
      else if (e.key === 'j' || e.key === 'J') player.seek(player.position() - 10, !player.paused());
      else if (e.key === 'l' || e.key === 'L') player.seek(player.position() + 10, !player.paused());
    });
    renderMoments();
    V = { player, tl, ov, setClip, S, hash, open(p) {
      S.from = p.from && byId[p.from] ? p.from : null;
      const ins = S.from ? byId[S.from] : null;
      $('back-bar').hidden = false;
      $('back-link').setAttribute('href', ins ? `#/panel/${ins.id}` : '#/panel');
      backCtx();
      for (const inp of document.querySelectorAll('[data-layer]')) { const on = p.capas.includes(inp.dataset.layer); inp.checked = on; ov.set(inp.dataset.layer, on); }
      setClip(p.clip);
      const tt = p.t ?? (p.clip ? p.clip[0] : 0);
      tl.set(tt); showClock(tt); live(tt);
      player.seek(tt, !!p.clip);
    },
    // New language: only text changes. Nothing here touches the <video> elements or the player state.
    relabel() {
      list = Core.moments(DL, t); window.App.moments = list;
      renderMoments();
      $('live').dataset.key = ''; live(player.position());
      if (S.clipEnded) clipEndText(); else clipText();
      backCtx(); playLabel();
      $('loading').textContent = t(S.error ? 'video.error' : 'video.loading');
      if (!S.scrubbing && !tl.dragging) tl.set(player.position());
      ov.status(); ov.draw();
      $('copy-status').textContent = '';
    } };
    Object.assign(window.App, { player, tl, ov, moments: list, V });
    return V;
  }

  // ------------------------------------------------------------ ES / EN switch
  // Keep the reader's place on the panel: the first block under the header stays put while the text reflows.
  function panelAnchor() {
    if (routeName !== 'panel' || window.scrollY < 40) return null;
    const y = 8;
    let best = null;
    for (const e of document.querySelectorAll('#view-panel [id]')) { const r = e.getBoundingClientRect(); if (r.top <= y && r.bottom > y && r.height > 0) best = { id: e.id, top: r.top }; }
    return best;
  }
  function reflectLang() {
    const u = new URL(location.href);
    u.searchParams.delete('lang');                    // the hash carries the language from now on
    const h = routeName === 'video' && V ? V.hash() : Core.withLang(location.hash, I18n.lang);
    history.replaceState(null, '', u.pathname + u.search + h);
  }
  function setLang(l, { updateUrl = true } = {}) {
    if (!Core.LANGS.includes(l)) return;
    if (l !== I18n.lang) {
      const anchor = panelAnchor();
      I18n.set(l);
      localizeData();
      Dashboard.render(DL, { go });
      if (V) V.relabel();
      document.title = t(routeName === 'video' ? 'meta.titleVideo' : 'meta.title');
      if (anchor) { const e = $(anchor.id); if (e) window.scrollBy(0, e.getBoundingClientRect().top - anchor.top); }
      requestAnimationFrame(() => Dashboard._placeRefs && Dashboard._placeRefs());
    }
    if (updateUrl) reflectLang();
  }
  for (const b of document.querySelectorAll('[data-lang]')) b.addEventListener('click', () => setLang(b.dataset.lang));

  // ------------------------------------------------------------ router
  let routeName = null;
  const currentRoute = () => routeName;
  function route() {
    const p = Core.parseHash(location.hash);
    const firstRoute = routeName === null;
    if (p.lang && p.lang !== I18n.lang) setLang(p.lang, { updateUrl: false });
    routeName = p.route;
    $('view-panel').hidden = p.route !== 'panel';
    $('view-video').hidden = p.route !== 'video';
    for (const a of document.querySelectorAll('[data-route]')) { if (a.dataset.route === p.route) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); }
    if (p.route === 'video') {
      document.title = t('meta.titleVideo');
      const v = videoModule(); v.open(p);
      requestAnimationFrame(() => { v.tl.size(); v.ov.resize(); });
      window.scrollTo(0, 0);
      if (!firstRoute) $('main').focus({ preventScroll: true });
    } else {
      document.title = t('meta.title');
      if (V) V.player.pause();
      requestAnimationFrame(() => {
        Dashboard._placeRefs && Dashboard._placeRefs();
        const target = p.id && document.getElementById(`hallazgo-${p.id}`);
        if (target) { target.scrollIntoView({ block: 'center' }); target.classList.remove('flash'); void target.offsetWidth; target.classList.add('flash'); const a = target.querySelector('a.btn'); if (a) a.focus({ preventScroll: true }); }
        else if (!firstRoute) { window.scrollTo(0, 0); $('main').focus({ preventScroll: true }); }
      });
    }
  }
  window.addEventListener('hashchange', route);
  window.App = { D, get DL() { return DL; }, errors, route, setLang };
  route();
})();
