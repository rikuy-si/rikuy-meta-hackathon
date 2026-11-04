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
