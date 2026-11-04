"""Language-mixing check for the bilingual page: open it in a real browser in ES and in EN, collect every
visible text node (HTML and SVG), the tab title and the accessible attributes (aria-label, alt, title) of
visible elements, the video sources, posters and download links, and flag words of the other language.

usage: lang_check.py URL_OR_FILE   -> prints flagged items per language; exit 1 if any
Allowed in both languages: proper names, brand and product names, numbers, dates in the page's own format.
"""
import sys, json, re, subprocess

url = sys.argv[1] if '://' in sys.argv[1] else 'file://' + sys.argv[1]
S = ['agent-browser', '--session', 'axs-langcheck']
JS = r"""(() => {
  const vis = el => { for (let e = el; e && e.nodeType === 1; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false; } return true; };
  const out = {title: document.title, lang: document.documentElement.lang, text: [], attrs: [], media: []};
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = w.nextNode());) { const t = n.textContent.replace(/\s+/g, ' ').trim();
    if (t && n.parentElement && !['SCRIPT', 'STYLE'].includes(n.parentElement.tagName) && vis(n.parentElement)) out.text.push(t); }
  document.querySelectorAll('[aria-label],[alt],[title]').forEach(e => { if (!vis(e)) return;
    for (const a of ['aria-label', 'alt', 'title']) if (e.hasAttribute(a)) out.attrs.push(a + '=' + e.getAttribute(a)); });
  document.querySelectorAll('video').forEach(v => out.media.push('video ' + v.getAttribute('src') + ' poster ' + v.getAttribute('poster')));
  document.querySelectorAll('a[download]').forEach(a => out.media.push('download ' + a.getAttribute('href')));
  return JSON.stringify(out);
})()"""
ES_ONLY = set('de la el los las del y en con por para su sus una uno que se al es está están vino viene visitas visita mes meses año años días día '
              'socio socia plan vence venció datos frente antes desde cada hasta sin solo pero más menos ya hoy fue entre cómo se midió fuentes '
              'repeticiones series minutos trabajo insignias descargar compartir versión móvil lo vieron cámaras acción sugerida riesgo fidelizar '
              'fidelizarlo fidelizarla madrugador madrugadora equipo pecho acero piernas fiel cámara historial video ago oct may jul sep nov dic ene feb '
              'mar abr jun'.split())
EN_ONLY = set('the and of to in with for his her he she is are was were came comes visits visit month months year years days day member '
              'plan ends data as before since every until without only but more less already today between how it measured sources reps sets '
              'minutes work badges download share version mobile what saw cameras suggested action risk keep early bird team player iron chest legs '
              'loyal history jan feb mar apr may jun jul aug sep oct nov dec why at on from'.split())
SHARED = {'plan', 'video', 'feb', 'mar', 'jun', 'jul', 'sep', 'oct', 'nov', 'may', 'real', 'fig'}
ALLOW = re.compile(r"^(Víctor|VÍCTOR|Manuela|MANUELA|AnimalX|ANIMAL X|Animal X|Rikuy|Caldas|ERP|DVR|SAM 3D Body|WhatsApp|ES|EN|Fig\. \d|[\d.,:−+%·\s/()]+)$")
ACCENT = re.compile(r'[áéíóúñ¿¡ÁÉÍÓÚÑ]')
NAMES = re.compile(r'Víctor|VÍCTOR')


def flags(items, L):
    bad = []
    for it in items:
        s = it.split('=', 1)[-1] if '=' in it[:12] else it
        if ALLOW.match(s.strip()):
            continue
        words = set(w.lower() for w in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ']+", s))
        other = (ES_ONLY if L == 'en' else EN_ONLY) - SHARED
        hit = sorted(words & other)
        if L == 'en' and ACCENT.search(NAMES.sub('', s)):
            hit.append('<accent>')
        if hit:
            bad.append((hit, it))
    return bad


subprocess.run(S + ['open', url], capture_output=True)
total = 0
for L in ('es', 'en'):
    subprocess.run(S + ['eval', "localStorage.clear(); 1"], capture_output=True)
    subprocess.run(S + ['click', f'[data-set-lang="{L}"]'], capture_output=True)
    raw = subprocess.run(S + ['eval', JS], capture_output=True, text=True).stdout.strip().splitlines()[-1]
    d = json.loads(json.loads(raw))
    items = [d['title']] + d['text'] + d['attrs']
    bad = flags(items, L)
    wrong_media = [m for m in d['media'] if f'-{"en" if L == "es" else "es"}-' in m]
    print(f'== {L.upper()} html lang={d["lang"]} · {len(d["text"])} text nodes, {len(d["attrs"])} attributes, {len(d["media"])} media')
    for hit, it in bad:
        print('   MIX', hit, '|', it[:140])
    for m in wrong_media:
        print('   MEDIA', m)
    if d['lang'] != L:
        print('   LANG attribute', d['lang'])
    total += len(bad) + len(wrong_media) + (d['lang'] != L)
    json.dump(d, open(f'/tmp/lang_check_{L}.json', 'w'), ensure_ascii=False, indent=1)
subprocess.run(S + ['close'], capture_output=True)
print('TOTAL ISSUES', total)
sys.exit(1 if total else 0)
