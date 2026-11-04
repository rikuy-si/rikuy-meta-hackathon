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
