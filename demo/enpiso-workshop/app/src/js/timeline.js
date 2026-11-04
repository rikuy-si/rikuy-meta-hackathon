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
