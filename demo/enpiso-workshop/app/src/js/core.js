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
