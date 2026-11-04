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
