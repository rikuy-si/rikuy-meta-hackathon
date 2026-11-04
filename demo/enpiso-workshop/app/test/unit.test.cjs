// Unit checks for EnPiso Visión v0.1.3: pure helpers (ES and EN formatting), the numbers shipped in dist/app-data.json,
// the ES/EN copy (catalog parity, both languages everywhere, no Spanish left in the English copy), privacy and copy
// rules in both languages, and bundle self-containment. Run after `python3 build.py`:  node test/unit.test.cjs
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const PRIVATE_PII = (() => { const f = process.env.PII_PATTERNS || require('node:path').join(__dirname, '..', 'private', 'pii.json'); try { return JSON.parse(require('node:fs').readFileSync(f, 'utf8')).map(s => new RegExp(s, 'i')); } catch { return []; } })();
const H = path.resolve(__dirname, '..'), DIST = path.join(H, 'dist');
const Core = require(path.join(H, 'src/js/core.js'));
let n = 0, failed = 0;
function t(name, fn) { n++; try { fn(); console.log('PASS ', name); } catch (e) { failed++; console.log('FAIL ', name, '\n   ', e.message); } }

const D = JSON.parse(fs.readFileSync(path.join(DIST, 'app-data.json'), 'utf8'));
const recs = D.playlist.recordings;
const texts = fs.readdirSync(DIST).filter((f) => /\.(html|js|json|svg|txt)$/.test(f)).map((f) => [f, fs.readFileSync(path.join(DIST, f), 'utf8')]);
const CAT = Object.fromEntries(['es', 'en'].map((l) => [l, JSON.parse(fs.readFileSync(path.join(H, `src/i18n/${l}.json`), 'utf8'))]));
const tr = (lang) => (k, v) => (CAT[lang][k] || k).replace(/\{(\w+)\}/g, (m, x) => (v && v[x] != null ? v[x] : m));
// Every bilingual {es, en} pair in the data.
const PAIRS = []; (function walk(o, p) { if (o && typeof o === 'object') { if (!Array.isArray(o) && Object.keys(o).sort().join() === 'en,es') PAIRS.push([p, o]); else for (const [k, v] of Object.entries(o)) walk(v, `${p}.${k}`); } })(D, 'D');
const pick = (o, lang) => JSON.parse(JSON.stringify(o), (k, v) => (v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).sort().join() === 'en,es' ? v[lang] : v));
// Client copy in each language: the catalog plus every generated string.
const COPY = { es: [...Object.values(CAT.es), ...PAIRS.map(([, p]) => p.es)], en: [...Object.values(CAT.en), ...PAIRS.map(([, p]) => p.en)] };
// Common Spanish words that must not appear in the English copy (proper names are allowed: EnPiso Visión, [PLANT], [MODULE]).
const SPANISH = /\b(el|la|los|las|del|de|que|con|por|para|una|puesto|pieza|piezas|minutos|hora|horas|ciclo|ciclos|cola|registro|registros|fuente|confianza|ejemplo|próximamente|ver|video de|módulo|eficiencia|esperando|cosiendo)\b|[ñ¿¡áéíóú]/i;
const ALLOWED = /EnPiso Visión|[PLANT]|[MODULE]/g;
const BANNED = { es: [/vigil/i, /castig/i, /monitore/i, /esp[ií]a[rn ]/i, /sanci[oó]n/i, /surveil/i, /big brother/i], en: [/monitor/i, /\bwatch/i, /punish/i, /\bspy/i, /surveil/i, /sanction/i, /disciplin/i, /penal/i, /snoop/i, /big brother/i] };

t('playlist: six contiguous recordings, 0..5760 s, public R2 URLs reused', () => {
  assert.equal(recs.length, 6); assert.equal(D.playlist.end, 5760); assert.equal(D.playlist.offset, 3603);
  for (let i = 1; i < recs.length; i++) assert.ok(Math.abs(recs[i].start - (recs[i - 1].start + recs[i - 1].duration)) < 0.5);
  assert.ok(recs.every((r) => /^https:\/\/ve\.rikuy\.si\/tmp\/.+\/module-full-0[1-6]\.mp4$/.test(r.url)));
});
t('clock: plant time = camera time minus 3603 s', () => {
  assert.equal(Core.plantClock(recs, 0), '13:09:21');
  assert.equal(Core.plantClock(recs, 56), '13:10:17');           // first module-28 capture, CP 13:10:17
  assert.equal(Core.plantClock(recs, 4202.9), '14:19:24');          // CP capture at 14:19:24
  assert.equal(Math.round(Core.plantToT(recs, '13:10:17', 5760)), 56);
  assert.equal(Core.plantToT(recs, '16:00:00', 5760), null);
  assert.equal(Core.locate(recs, 2048.5).i, 2);
});
t('routes: deep links round-trip and reject junk', () => {
  const h = Core.videoHash({ t: 2455, clip: [2455, 2530], from: 'restriccion', capas: ['zonas', 'esqueletos'] });
  assert.equal(h, '#/video?t=2455&clip=2455-2530&from=restriccion&capas=zonas,esqueletos');
  assert.deepEqual(Core.parseHash(h), { route: 'video', id: null, t: 2455, clip: [2455, 2530], from: 'restriccion', capas: ['zonas', 'esqueletos'], lang: null });
  assert.equal(Core.parseHash('#/panel/minutos').id, 'minutos');
  assert.equal(Core.parseHash('').route, 'panel');
  const bad = Core.parseHash('#/video?t=-4&clip=9-3&from=<x>&capas=foo');
  assert.equal(bad.t, null); assert.equal(bad.clip, null); assert.equal(bad.from, null); assert.deepEqual(bad.capas, []);
  assert.deepEqual(Core.parseHash('#/video?t=5').capas, ['zonas', 'puestos', 'esqueletos']); // v0.1.3: on by default
  assert.deepEqual(Core.parseHash('#/video?t=5&capas=ninguna').capas, []);
  assert.equal(Core.videoHash({ t: 5, capas: [] }), '#/video?t=5&capas=ninguna');
});
t('helpers: lanes, windows, numbers, clip labels', () => {
  assert.equal(Core.laneAt(D.lanes.B, 100), 'cose');
  assert.equal(Core.laneAt([[0, 5], [9, 12]], 10), true); assert.equal(Core.laneAt([[0, 5]], 7), null);
  assert.deepEqual(Core.viewWindow(100, 5760, 600), [0, 600]); assert.deepEqual(Core.viewWindow(5700, 5760, 600), [5160, 5760]); assert.deepEqual(Core.viewWindow(3000, 5760, 0), [0, 5760]);
  assert.equal(Core.num(1.25, 1), '1,3'); assert.equal(Core.num(11, 1), '11'); assert.equal(Core.dur(382), '6 min 22 s');
  assert.equal(Core.clipLabel('13:10:11', '13:10:33'), '13:10:11 a 13:10:33'); assert.equal(Core.clipLabel('13:50:15', '13:51:30'), '13:50 a 13:51');
});
t('locale formatting: ES 59 %, 3,8 min, vie 30 oct 2026; EN 59%, 3.8 min, Fri Oct 30 2026; 24 h clock in both', () => {
  assert.equal(Core.getLang(), 'es');
  assert.equal(Core.pct(58.8), '59\u00a0%'); assert.equal(Core.num(3.8), '3,8'); assert.equal(Core.num(0.95, 2), '0,95'); assert.equal(Core.num(128.57), '128,6');
  // 2026-10-30 (the recording day) is a Friday; v0.1.1 hard-coded "jueves" by mistake
  assert.equal(Core.date('2026-10-30'), 'vie 30 oct 2026'); assert.equal(Core.date('2026-10-30', true), 'viernes 30 de octubre de 2026'); assert.equal(Core.date('2026-11-03'), 'mar 3 nov 2026');
  Core.setLang('en');
  try {
    assert.equal(Core.pct(58.8), '59%'); assert.equal(Core.num(3.8), '3.8'); assert.equal(Core.num(11, 1), '11'); assert.equal(Core.num(1.25, 1), '1.3');
    assert.equal(Core.date('2026-10-30'), 'Fri Oct 30 2026'); assert.equal(Core.date('2026-10-30', true), 'Friday, October 30, 2026'); assert.equal(Core.date('2026-10-29'), 'Thu Oct 29 2026');
    assert.equal(Core.clipLabel('13:50:15', '13:51:30'), '13:50 to 13:51');
    assert.equal(Core.plantClock(recs, 4202.9), '14:19:24');
    assert.equal(Core.setLang('fr'), 'en');
  } finally { Core.setLang('es'); }
});
t('language choice and deep links: lang param, then saved, then browser (en* is EN), otherwise ES', () => {
  assert.equal(Core.pickLang({ param: 'en', saved: 'es', browser: ['es-CO'] }), 'en');
  assert.equal(Core.pickLang({ param: null, saved: 'en', browser: ['es-CO'] }), 'en');
  assert.equal(Core.pickLang({ param: 'xx', saved: null, browser: ['en-GB', 'es'] }), 'en');
  assert.equal(Core.pickLang({ browser: ['de-DE'] }), 'es'); assert.equal(Core.pickLang({}), 'es'); assert.equal(Core.pickLang({ browser: ['eng'] }), 'es');
  assert.equal(Core.parseHash('#/video?t=4202&lang=en').lang, 'en'); assert.equal(Core.parseHash('#/panel?lang=fr').lang, null);
  assert.equal(Core.parseHash('#/panel/minutos?lang=en').id, 'minutos');
  assert.equal(Core.videoHash({ t: 10, capas: ['zonas'], lang: 'en' }), '#/video?t=10&capas=zonas&lang=en');
  assert.equal(Core.withLang('#/panel', 'en'), '#/panel?lang=en'); assert.equal(Core.withLang('', 'es'), '#/panel?lang=es');
  assert.equal(Core.withLang('#/video?t=5&capas=zonas,puestos&lang=es', 'en'), '#/video?t=5&capas=zonas,puestos&lang=en');
});
t('catalog: ES and EN have the same keys and placeholders; moments read from it in both languages', () => {
  assert.deepEqual(Object.keys(CAT.en).sort(), Object.keys(CAT.es).sort());
  for (const k of Object.keys(CAT.es)) assert.deepEqual((CAT.en[k].match(/\{\w+\}/g) || []).sort(), (CAT.es[k].match(/\{\w+\}/g) || []).sort(), k);
  const es = Core.moments(pick(D, 'es'), tr('es')), en = Core.moments(pick(D, 'en'), tr('en'));
  assert.equal(es.length, en.length);
  const h = (l) => l.filter((m) => m.kind === 'hallazgo').map((m) => m.label);
  assert.equal(h(es)[0], 'La eficiencia del módulo cambió mucho durante el día'); assert.equal(h(en)[0], 'Module efficiency swung a lot during the day');
  assert.ok(en.some((m) => m.label === 'Station B cycle 1') && es.some((m) => m.label === 'Ciclo 1 del Puesto B'));
  for (const m of en) assert.ok(!SPANISH.test(`${m.label} ${m.sub}`), `${m.label} ${m.sub}`);
});
t('copy in both languages: every generated string has ES and EN, with the same numbers, and no Spanish left in EN', () => {
  assert.ok(PAIRS.length > 100, PAIRS.length);
  const nums = (s) => (s.match(/\d+(?:[.,]\d+)?/g) || []).map((x) => x.replace(',', '.')).sort();
  for (const [p, o] of PAIRS) {
    assert.ok(o.es.trim() && o.en.trim() && o.es !== o.en || /^(Video|CP)/.test(o.es), p);
    assert.deepEqual(nums(o.en), nums(o.es), p);
  }
  for (const s of COPY.en) assert.ok(!SPANISH.test(s.replace(ALLOWED, '').replace(/<[^>]+>/g, ' ')), `Spanish in EN copy: ${s}`);
  for (const s of COPY.en) assert.ok(!/\d\u00a0%|\d,\d/.test(s), `ES number format in EN copy: ${s}`);
  for (const s of COPY.es) assert.ok(!/\d\.\d/.test(s), `EN number format in ES copy: ${s}`);
  assert.deepEqual(D.insights.filter((i) => i.kind === 'top').map((i) => i.headline.en), ['Station B sets the pace for the module', 'Module efficiency swung a lot during the day', 'Station B sewed 74 of 96 minutes and barely waited']);
});
t('efficiency per hour = CP pieces × 3.8 min / (2 × 60 min)', () => {
  const rows = D.hourly.rows;
  assert.deepEqual(rows.map((r) => r.pieces), [13, 18, 18, 10, 10, 41, 20, 23, 14]);
  for (const r of rows) assert.ok(Math.abs(r.eff - (r.pieces * 3.8) / 120 * 100) < 0.06, r.label);
  assert.equal(D.hourly.total, 167); assert.ok(Math.abs(D.hourly.avg - 58.8) < 0.05);
  assert.ok(rows.find((r) => r.label === '11:00').flags.includes('burst'));
  assert.ok(rows.find((r) => r.label === '06:00').flags.includes('partial') && rows.find((r) => r.label === '14:00').flags.includes('partial'));
});
t('key facts match the experiment (B 127/111/12/3 s, 28.4/h, queue 36 s, 34 of 35, −1.2 s)', () => {
  const k = D.kpis;
  assert.deepEqual([k.bCycle, k.bWork, k.bFront, k.bWait, k.perHour, k.queue], [127, 111, 12, 3, 28.4, 36]);
  assert.deepEqual([k.keypad.hits, k.keypad.n, k.keypad.median], [34, 35, -1.2]);
  assert.equal(D.cycles.length, 45); assert.equal(D.cycles.filter((c) => c.clean).length, 19); assert.equal(D.captures.length, 35);
  assert.equal(D.meta.module.id, 28); assert.equal(D.meta.product, '[PRODUCT]'); assert.equal(D.meta.sam, 3.8); assert.equal(D.meta.operators, 2);
});
t('insights: top three first, each with number, source, confidence, a moment inside the video and proof stills', () => {
  const top = D.insights.filter((i) => i.kind === 'top');
  assert.deepEqual(top.map((i) => i.id), ['restriccion', 'eficiencia-hora', 'minutos']);
  assert.deepEqual(top.map((i) => i.number + i.unit), ['127s', '59%', '77%']);
  for (const i of D.insights) {
    assert.ok(i.headline.es && i.headline.en && i.number && i.source.label && ['alta', 'media', 'baja'].includes(i.confidence.level), i.id);
    const [a, b] = i.moment.clip; assert.ok(a >= 0 && b <= 5760 && b > a && i.moment.t >= 0, i.id);
    for (const f of i.proof) assert.ok(fs.existsSync(path.join(DIST, f.src)) && f.alt.es && f.alt.en && f.caption.es && f.caption.en, f.src);
    if (i.kind !== 'review') assert.equal(i.proof.length, 3, i.id);
  }
  assert.equal(D.insights.find((i) => i.id === 'cp-video').number, '34/35');
});
t('mock panel is labelled as an example and consistent with the CP SAM', () => {
  assert.match(D.mock.label.es, /Ejemplo/); assert.match(D.mock.label.es, /No son datos de su planta/);
  assert.match(D.mock.label.en, /Example/); assert.match(D.mock.label.en, /not data from your plant/);
  assert.equal(CAT.es['mock.chip'], 'Ejemplo'); assert.equal(CAT.en['mock.chip'], 'Example'); assert.equal(CAT.es.soon, 'Próximamente'); assert.equal(CAT.en.soon, 'Coming soon');
  assert.ok(Math.abs(D.mock.zones.reduce((s, z) => s + z.sew, 0) - 3.8) < 1e-9);
  assert.equal(D.mock.restriction.id, 'OP06');
});
t('privacy: no names, employee codes, client name or identity fields anywhere in the bundle', () => {
  for (const [f, s] of texts) for (const re of [...PRIVATE_PII, /Worker-\d/, /identit/i]) assert.ok(!re.test(s), `${f} contains ${re}`);
  const keys = new Set(); (function walk(o) { if (o && typeof o === 'object') for (const [k, v] of Object.entries(o)) { keys.add(k); walk(v); } })(D);
  for (const k of ['identities', 'code', 'workers', 'employee']) assert.ok(!keys.has(k), k);
});
t('copy rules: ES and EN client copy without banned words or dashes; Spanish shell by default', () => {
  for (const [f, s] of texts.filter(([f]) => ['index.html', 'app.js', 'app-data.json'].includes(f))) {
    for (const re of [...BANNED.es, ...BANNED.en, /\u2014/, /\u2013/]) assert.ok(!re.test(s), `${f} contains ${re}`);
  }
  for (const lang of ['es', 'en']) for (const s of COPY[lang]) {
    assert.ok(!/\s-\s|\u2014|\u2013/.test(s), `${lang} dash: ${s}`);
    for (const re of [...BANNED.es, ...BANNED.en]) assert.ok(!re.test(s), `${lang} ${re}: ${s}`);
  }
  assert.ok(!/\bwatch|monitor/i.test(CAT.en['ins.see'] + CAT.en['clip.clear'] + CAT.en['video.showing']));
  assert.match(CAT.en['head.powered'], /^powered by$/);
  const html = texts.find(([f]) => f === 'index.html')[1];
  assert.match(html, /<html lang="es-CO">/); assert.match(html, /<title>EnPiso Visión · Módulo 28<\/title>/); assert.match(html, /id="lang-switch"/);
  assert.ok(!/\{\{|\{[a-z]\w*\}/.test(html.replace(/<script[\s\S]*?<\/script>|<style>[\s\S]*?<\/style>/g, '')), 'unfilled token in the HTML');
});
t('self-contained: flat bundle, relative paths, no runtime URLs except the R2 recordings', () => {
  assert.ok(fs.readdirSync(DIST).every((f) => fs.statSync(path.join(DIST, f)).isFile()));
  for (const [f, s] of texts) {
    const urls = (s.match(/https?:\/\/[^\s"'<>)]+/g) || []).filter((u) => !/^https:\/\/ve\.rikuy\.si\/tmp\/.+\.mp4$/.test(u) && !/^http:\/\/www\.w3\.org\//.test(u));
    assert.deepEqual(urls, [], f);
  }
  const html = texts.find(([f]) => f === 'index.html')[1];
  for (const ref of html.match(/(?:src|href)="([^"#?]+)/g).map((m) => m.split('"')[1])) assert.ok(fs.existsSync(path.join(DIST, ref)), ref);
});
t('pose binaries: manifest offsets fit the files', () => {
  const m = JSON.parse(fs.readFileSync(path.join(DIST, 'pose-manifest.json'), 'utf8'));
  for (const [rec, info] of Object.entries(m.recs)) {
    const size = fs.statSync(path.join(DIST, info.file)).size;
    for (const lab of ['A', 'B']) { const { offset, n } = info.labels[lab]; assert.ok(n > 1000 && offset + n * 2 * (1 + m.joints * 2) <= size, `${rec} ${lab}`); }
  }
});

console.log(`\n${n - failed}/${n} unit checks passed`);
process.exit(failed ? 1 : 0);
