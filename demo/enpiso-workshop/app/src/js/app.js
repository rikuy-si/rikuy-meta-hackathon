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
