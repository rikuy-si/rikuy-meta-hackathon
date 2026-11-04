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
