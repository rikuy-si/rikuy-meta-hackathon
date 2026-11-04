"""Build the bilingual visual-explainer page (dashboard + videos) for the two members.

usage: build_page.py [--out ~/.agent/diagrams] [--version v008]
Reads ERP facts (../work/client_history.json, ../work/tracking.json) and the v008 edit audits, writes
<out>/animalx-socios.src.html and links the assets it references (axs-*) into <out>. Every number on the page
comes from those files. First names only; no document numbers, phones, emails or addresses.
"""
import json, pathlib, argparse, datetime as dt, html, os

ROOT = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser(); ap.add_argument('--out', default=os.path.expanduser('~/.agent/diagrams'))
ap.add_argument('--version', default='v008')
a = ap.parse_args()
OUT = pathlib.Path(a.out); OUT.mkdir(parents=True, exist_ok=True)
H = json.load(open(ROOT.parent / 'work' / 'client_history.json'))
_t = json.load(open(ROOT.parent / 'work' / 'tracking.json')); TRK = {v['doc']: v for v in (_t.values() if isinstance(_t, dict) else _t)}
ASOF = dt.date(2026, 11, 2)
MES = {'es': ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'],
       'en': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']}
# members.json is private (git-ignored): [{"key", "name" (first name only), "doc" (ERP member id), "g"}].
CL = json.load(open(ROOT / 'members.json'))


def e(s):
    return html.escape(str(s), quote=True)


def aria(es, en):
    """aria-label in the page's start language (es) plus both versions; setLang() swaps it."""
    return f'aria-label="{e(es)}" data-aria-es="{e(es)}" data-aria-en="{e(en)}"'


def bi(es, en, tag='span'):
    return f'<{tag} lang="es">{es}</{tag}><{tag} lang="en">{en}</{tag}>'


def n_es(v):
    return f'{v:,}'.replace(',', '.')


def n_en(v):
    return f'{v:,}'


def pct(a, b):
    return round((a - b) / b * 100)


def dlabel(d, L):
    return f'{d.day} {MES["es"][d.month - 1]} {d.year}' if L == 'es' else f'{MES["en"][d.month - 1]} {d.day}, {d.year}'


# ------------------------------------------------------------------ facts
for c in CL:
    m = H[c['doc']]['mensual']; t = TRK[c['doc']]
    months = []
    y, mo = 2020, 1
    while (y, mo) <= (2026, 10):
        months.append((f'{y}-{mo:02d}', m.get(f'{y}-{mo:02d}', 0))); mo += 1
        if mo == 13: y, mo = y + 1, 1
    c['months'] = months
    c['first'] = min(m); c['total'] = sum(m.values())
    c['l12'] = [v for k, v in months[-12:]]; c['l12_keys'] = [k for k, v in months[-12:]]
    c['act12'] = sum(1 for v in c['l12'] if v > 0)
    c['a3'], c['p3'] = sum(c['l12'][-3:]), sum(c['l12'][-6:-3])
    c['trend'] = pct(c['a3'], c['p3'])
    c['vence'] = dt.date.fromisoformat(t['vence'].replace('/', '-')); c['dias'] = (c['vence'] - ASOF).days
    c['compra'] = dt.date.fromisoformat(t['ult_compra'].replace('/', '-'))
    c['creado'] = t['creado'][:4]
    by = {}
    for k, v in m.items(): by[k[:4]] = by.get(k[:4], 0) + v
    c['by_year'] = by
    au = json.load(open(ROOT / 'edit' / c['key'] / a.version / f"{c['key']}_{a.version}_es_16x9.audit.json"))
    c['facts'] = au['facts']; c['dur'] = au['duration_s']
    au_en = json.load(open(ROOT / 'edit' / c['key'] / a.version / f"{c['key']}_{a.version}_en_16x9.audit.json"))
    assert len(au_en['facts']['badges']) == len(au['facts']['badges'])
    c['badges'] = [(b_es[1], b_en[1]) for b_es, b_en in zip(au['facts']['badges'], au_en['facts']['badges'])]
    c['ytd26'], c['ytd25'] = sum(v for k, v in months if k.startswith('2026')), sum(v for k, v in months if '2025-01' <= k <= '2025-10')
V, M = CL
v_min = min(((k, x) for k, x in V['months'] if k >= '2021-05'), key=lambda kv: kv[1])
assert v_min[0] == '2026-09', v_min
M['peak_year'] = max(M['by_year'], key=M['by_year'].get)


# ------------------------------------------------------------------ figures
def history_svg():
    W_, top, rowh, gap = 1000, 34, 150, 46
    n = len(V['months']); bw = (W_ - 80) / n; ymax = 65
    al_es = 'Visitas por mes desde enero de 2020. Víctor se mantiene cerca de 20 al mes; Manuela tuvo su pico en 2023 y bajó a unas 6 al mes.'
    al_en = 'Monthly visits since January 2020. Víctor stays near 20 a month; Manuela peaked in 2023 and fell to about 6 a month.'
    out = [f'<svg class="ve-svg" viewBox="0 0 {W_} {top + 2 * rowh + gap + 40}" role="img" {aria(al_es, al_en)}>']
    for r, c in enumerate(CL):
        y0 = top + r * (rowh + gap); base = y0 + rowh
        out.append(f'<text x="62" y="{y0 - 12}" text-anchor="start" style="font-size:16px;font-weight:600;fill:var(--text)">{e(c["name"])}</text>')
        out.append(f'<path class="ve-axis" d="M60 {base}H{W_ - 20}"/>')
        for tick in (0, 20, 40, 60):
            yy = base - tick / ymax * rowh
            out.append(f'<text class="ve-axis-t" x="50" y="{yy + 4:.1f}" text-anchor="end">{tick}</text>')
        for i, (k, v) in enumerate(c['months']):
            x = 62 + i * bw; h = v / ymax * rowh
            recent = k >= '2026-08'
            fill = 'var(--accent)' if recent else 'var(--text-dim)'
            op = '1' if recent else '.55'
            if v: out.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{bw - 2:.1f}" height="{h:.1f}" fill="{fill}" opacity="{op}"><title>{k}: {v}</title></rect>')
        for yr in range(2020, 2027):
            i = [k for k, _ in c['months']].index(f'{yr}-01'); x = 62 + i * bw
            out.append(f'<path class="ve-axis" d="M{x:.1f} {base}V{base + 6}"/><text class="ve-axis-t" x="{x + 2:.1f}" y="{base + 20}">{yr}</text>')
    i = [k for k, _ in V['months']].index('2026-09'); x = 62 + i * bw + bw / 2; base = top + rowh; yb = base - 9 / ymax * rowh
    out.append(f'<path class="ann" d="M{x:.1f} {yb - 4:.1f}V{top + 18}H{x - 30:.1f}" fill="none" stroke="var(--risk)" stroke-width="1.5"/>')
    out.append(f'<text x="{x - 36:.1f}" y="{top + 22}" text-anchor="end" style="fill:var(--risk);font-size:15px" lang="es">sep 2026: 9 visitas, su mes más bajo desde abr 2021</text>')
    out.append(f'<text x="{x - 36:.1f}" y="{top + 22}" text-anchor="end" style="fill:var(--risk);font-size:15px" lang="en">Sep 2026: 9 visits, his lowest month since Apr 2021</text>')
    y0 = top + rowh + gap; pk = M['peak_year']; b45 = M["by_year"]["2024"] + M["by_year"]["2025"]
    out.append(f'<text x="180" y="{y0 - 12}" style="fill:var(--text);font-size:15px" lang="es">{pk}: {n_es(M["by_year"][pk])} visitas</text>')
    out.append(f'<text x="180" y="{y0 - 12}" style="fill:var(--text);font-size:15px" lang="en">{pk}: {n_en(M["by_year"][pk])} visits</text>')
    out.append(f'<text x="420" y="{y0 - 12}" style="fill:var(--risk);font-size:15px" lang="es">2024 y 2025: {b45} visitas en total</text>')
    out.append(f'<text x="420" y="{y0 - 12}" style="fill:var(--risk);font-size:15px" lang="en">2024 and 2025: {b45} visits in total</text>')
    out.append('</svg>')
    return '\n'.join(out)


def year_svg(c):
    """Last 12 months as bars, then Nov and Dec on the same axis with the data cut and the plan's end date."""
    W_, h, base = 800, 130, 200
    cols = 14; cw = (W_ - 60) / cols; ymax = max(30, max(c['l12']) + 4)
    out = [f'<svg class="ve-svg" viewBox="0 0 {W_} 290" role="img" '
           f'{aria(c["name"] + ": visitas por mes en los últimos 12 meses y días que le quedan al plan", c["name"] + ": visits per month for the last 12 months and the days left on the plan")}>']
    fx0 = 44 + 12 * cw - 4
    out.append(f'<rect x="{fx0:.1f}" y="{base - h - 10}" width="{W_ - 10 - fx0:.1f}" height="{h + 10}" fill="var(--border)"/>')
    out.append(f'<path class="ve-axis" d="M40 {base}H{W_ - 10}"/>')
    for i, (k, v) in enumerate(zip(c['l12_keys'], c['l12'])):
        x = 44 + i * cw; bh = v / ymax * h; recent = i >= 9
        out.append(f'<rect x="{x:.1f}" y="{base - bh:.1f}" width="{cw - 8:.1f}" height="{bh:.1f}" fill="{"var(--accent)" if recent else "var(--text-dim)"}" opacity="{1 if recent else .55}"/>')
        out.append(f'<text x="{x + (cw - 8) / 2:.1f}" y="{base - bh - 6:.1f}" text-anchor="middle" style="font-size:14px;fill:var(--text);font-variant-numeric:tabular-nums">{v}</text>')
    for i in range(14):
        x = 44 + i * cw; mo = (10 + i) % 12
        out.append(f'<text class="ve-axis-t" x="{x + (cw - 8) / 2:.1f}" y="{base + 18}" text-anchor="middle" lang="es">{MES["es"][mo]}</text>')
        out.append(f'<text class="ve-axis-t" x="{x + (cw - 8) / 2:.1f}" y="{base + 18}" text-anchor="middle" lang="en">{MES["en"][mo]}</text>')
    xnow = 44 + 12 * cw + (ASOF.day - 1) / 30 * (cw - 8)
    xend = 44 + (12 + (c['vence'].month - 11)) * cw + (c['vence'].day - 1) / 31 * (cw - 8)
    top = base - h - 10
    out.append(f'<path d="M{xnow:.1f} {top}V{base}" stroke="var(--text)" stroke-width="1.5"/>')
    out.append(f'<path d="M{xend:.1f} {top}V{base}" stroke="var(--risk)" stroke-width="2.5"/>')
    out.append(f'<text x="{xnow - 6:.1f}" y="{top - 26}" text-anchor="end" style="font-size:15px;fill:var(--text-dim)" lang="es">datos al 2 nov</text>')
    out.append(f'<text x="{xnow - 6:.1f}" y="{top - 26}" text-anchor="end" style="font-size:15px;fill:var(--text-dim)" lang="en">data as of Nov 2</text>')
    anchor, lx = ('end', xend + 6) if xend > W_ - 120 else ('start', xend + 6)
    if anchor == 'end': lx = W_ - 10
    out.append(f'<text x="{lx:.1f}" y="{top - 6}" text-anchor="{anchor}" style="font-size:14px;fill:var(--risk);font-weight:600" lang="es">vence {c["vence"].day} {MES["es"][c["vence"].month - 1]}</text>')
    out.append(f'<text x="{lx:.1f}" y="{top - 6}" text-anchor="{anchor}" style="font-size:14px;fill:var(--risk);font-weight:600" lang="en">ends {MES["en"][c["vence"].month - 1]} {c["vence"].day}</text>')
    yd = base + 50
    tx, ta = (xnow + xend) / 2, 'middle'
    out.append(f'<g class="ve-dim is-key"><path class="ext" d="M{xnow:.1f} {base + 26}V{yd + 6}M{xend:.1f} {base + 26}V{yd + 6}"/>'
               f'<path class="ln" d="M{xnow:.1f} {yd}H{xend:.1f}M{xnow - 4:.1f} {yd + 4}l8-8M{xend - 4:.1f} {yd + 4}l8-8"/>'
               f'<text x="{tx:.1f}" y="{yd + 22}" text-anchor="{ta}" lang="es">{c["dias"]} días</text>'
               f'<text x="{tx:.1f}" y="{yd + 22}" text-anchor="{ta}" lang="en">{c["dias"]} days</text></g>')
    out.append('</svg>')
    return '\n'.join(out)


def kpis(c):
    f = c['facts']; tr = c['trend']
    rows = [
        (bi('Visitas desde ' + c['first'][:4], 'Visits since ' + c['first'][:4]), bi(n_es(c['total']), n_en(c['total'])), ''),
        (bi('Últimos 12 meses', 'Last 12 months'), str(sum(c['l12'])), bi(f'{c["act12"]} de 12 meses con visitas', f'{c["act12"]} of 12 months with visits')),
        (bi('Ago a oct frente a may a jul', 'Aug to Oct vs May to Jul'), f'<span class="tr-risk">{"+" if tr > 0 else "−"}{abs(tr)}<span class="unit">%</span></span>',
         bi(f'{c["a3"]} visitas, antes {c["p3"]}', f'{c["a3"]} visits, before {c["p3"]}')),
        (bi('Su plan vence', 'Plan ends'), bi(dlabel(c['vence'], 'es'), dlabel(c['vence'], 'en')), bi(f'en {c["dias"]} días (al 2 nov)', f'in {c["dias"]} days (as of Nov 2)')),
    ]
    out = ['<div class="kpis">']
    for lab, val, sub in rows:
        out.append(f'<div class="kpi"><span class="ve-label">{lab}</span><span class="val">{val}</span><span class="kpi-sub">{sub}</span></div>')
    out.append('</div>')
    return '\n'.join(out)


def session(c):
    f = c['facts']; t = f['totals']
    days = len(set(x for x in [1])) and (3 if c['key'] == 'victor' else 1)
    badges = ''.join(f'<li>{e(b[1])} <small>{e(b[2])}</small></li>' for b in f['badges'])
    return days, t


def video_block(c):
    k = c['key']; mins, secs = divmod(int(round(c['dur'])), 60)
    return f'''<figure class="vid">
  <div class="vid-row">
    <div class="vid-wide">
      <video controls preload="none" playsinline width="1920" height="1080" data-src-es="axs-{k}-es-16x9.mp4" data-src-en="axs-{k}-en-16x9.mp4" poster="axs-{k}-es-poster.jpg" data-poster-es="axs-{k}-es-poster.jpg" data-poster-en="axs-{k}-en-poster.jpg" src="axs-{k}-es-16x9.mp4"></video>
    </div>
    <div class="vid-phone">
      <video controls preload="none" playsinline width="720" height="1280" data-src-es="axs-{k}-es-movil.mp4" data-src-en="axs-{k}-en-movil.mp4" poster="axs-{k}-es-poster-movil.jpg" data-poster-es="axs-{k}-es-poster-movil.jpg" data-poster-en="axs-{k}-en-poster-movil.jpg" src="axs-{k}-es-movil.mp4"></video>
      <div class="vid-actions">
        <button type="button" class="btn-wa" data-share="{k}">{bi("Compartir por WhatsApp", "Share on WhatsApp")}</button>
        <a class="btn-dl" data-dl="{k}" href="axs-{k}-es-movil.mp4" download>{bi("Descargar versión móvil", "Download mobile version")}</a>
      </div>
    </div>
  </div>
  <figcaption>{bi(f"El video de {e(c['name'])}: {mins}:{secs:02d} min en 16:9 y en vertical para WhatsApp, con el récord dramatizado al final.",
                    f"{e(c['name'])}'s video: {mins}:{secs:02d} min in 16:9 and vertical for WhatsApp, with the dramatized record at the end.")}</figcaption>
</figure>'''


def lists(c):
    if c['key'] == 'victor':
        keep = [bi('Socio desde 2018: la cuenta se creó el 31 dic 2018.', 'Member since 2018: the account was created on Dec 31, 2018.'),
                bi(f'{n_es(c["total"])} visitas desde 2020, unas 22 al mes de 2021 a 2025.', f'{n_en(c["total"])} visits since 2020, about 22 a month from 2021 to 2025.'),
                bi('Vino los 12 de los últimos 12 meses.', 'He came in all of the last 12 months.'),
                bi('Llega antes de las 5:00: 04:59 el jueves y 04:58 el viernes.', 'He arrives before 5:00: 04:59 on Thursday and 04:58 on Friday.'),
                bi(f'En 3 días de video: {c["facts"]["totals"]["sets"]} series y {n_es(c["facts"]["totals"]["reps"])} repeticiones, con press de banca y press inclinado con compañero.',
                   f'In 3 days of video: {c["facts"]["totals"]["sets"]} sets and {n_en(c["facts"]["totals"]["reps"])} reps, with barbell bench press and an incline press with a spotter.')]
        risk = [bi('Septiembre 2026: 9 visitas, su mes más bajo desde abril de 2021.', 'September 2026: 9 visits, his lowest month since April 2021.'),
                bi(f'Agosto a octubre: {c["a3"]} visitas, frente a {c["p3"]} de mayo a julio ({c["trend"]}%).'.replace('(-', '(−'), f'August to October: {c["a3"]} visits, against {c["p3"]} from May to July ({c["trend"]}%).'.replace('(-', '(−')),
                bi(f'Enero a octubre 2026: {c["ytd26"]} visitas, frente a {c["ytd25"]} en 2025 ({pct(c["ytd26"], c["ytd25"])}%).'.replace('(-', '(−'), f'January to October 2026: {c["ytd26"]} visits, against {c["ytd25"]} in 2025 ({pct(c["ytd26"], c["ytd25"])}%).'.replace('(-', '(−')),
                bi(f'Su plan vence el {dlabel(c["vence"], "es")}; la última compra de plan fue el {dlabel(c["compra"], "es")}.', f'His plan ends on {dlabel(c["vence"], "en")}; the last plan purchase was on {dlabel(c["compra"], "en")}.')]
        act = bi('Enviarle su video ahora, reconocer en el gimnasio su constancia de madrugada y ofrecerle la renovación antes del 13 de diciembre.',
                 'Send him his video now, recognize his early-morning consistency at the gym, and offer the renewal before December 13.')
    else:
        keep = [bi('Socia desde 2018: la cuenta se creó el 27 ago 2018.', 'Member since 2018: the account was created on Aug 27, 2018.'),
                bi(f'{n_es(c["total"])} visitas desde 2021; en 2023 vino {c["by_year"]["2023"]} veces.', f'{n_en(c["total"])} visits since 2021; in 2023 she came {c["by_year"]["2023"]} times.'),
                bi(f'Está volviendo: 2026 ya suma {c["ytd26"]} visitas, más que 2024 y 2025 juntos ({c["by_year"]["2024"] + c["by_year"]["2025"]}).', f'She is coming back: 2026 already has {c["ytd26"]} visits, more than 2024 and 2025 together ({c["by_year"]["2024"] + c["by_year"]["2025"]}).'),
                bi(f'En su día de video: {c["facts"]["totals"]["sets"]} series y {c["facts"]["totals"]["reps"]} repeticiones, casi todo pierna (thrusters, zancadas, sentadillas).', f'In her day of video: {c["facts"]["totals"]["sets"]} sets and {c["facts"]["totals"]["reps"]} reps, mostly legs (thrusters, lunges, squats).')]
        risk = [bi(f'Su plan vence el {dlabel(c["vence"], "es")}, en {c["dias"]} días (al 2 nov).', f'Her plan ends on {dlabel(c["vence"], "en")}, in {c["dias"]} days (as of Nov 2).'),
                bi(f'Agosto a octubre: {c["a3"]} visitas, frente a {c["p3"]} de mayo a julio ({c["trend"]}%).'.replace('(-', '(−'), f'August to October: {c["a3"]} visits, against {c["p3"]} from May to July ({c["trend"]}%).'.replace('(-', '(−')),
                bi('Ya dejó de venir antes: de 229 visitas en 2023 pasó a 22 en 2024.', 'She stopped coming before: from 229 visits in 2023 to 22 in 2024.'),
                bi(f'Compró su último plan el {dlabel(c["compra"], "es")}, pocas semanas antes del vencimiento.', f'She bought her last plan on {dlabel(c["compra"], "en")}, a few weeks before it ends.')]
        act = bi('Enviarle su video antes del 16 de noviembre y proponerle un plan más largo, con una meta de pierna para el próximo mes.',
                 'Send her the video before November 16 and offer a longer plan, with a leg goal for next month.')
    keep_html = ''.join(f'<li>{x}</li>' for x in keep); risk_html = ''.join(f'<li>{x}</li>' for x in risk)
    return keep_html, risk_html, act


def member(c, idx):
    k = c['key']; f = c['facts']; t = f['totals']
    keep_html, risk_html, act = lists(c)
    days = 3 if k == 'victor' else 1
    badges = ' '.join(f'<span class="chip">{bi(e(b_es), e(b_en))}</span>' for b_es, b_en in c['badges'])
    if k == 'victor':
        head = bi('Víctor: el socio más constante, con su peor mes en cinco años', 'Víctor: the most consistent member, with his worst month in five years')
        cap = bi('Víctor vino cada mes del año, pero septiembre bajó a 9 visitas; su plan vence el 13 de diciembre.', 'Víctor came every month of the year, but September fell to 9 visits; his plan ends on December 13.')
    else:
        head = bi('Manuela: está volviendo, y su plan vence en dos semanas', 'Manuela: she is coming back, and her plan ends in two weeks')
        cap = bi('Manuela viene unas 6 veces al mes y bajó en agosto a octubre; su plan vence el 16 de noviembre.', 'Manuela comes about 6 times a month and dropped from August to October; her plan ends on November 16.')
    return f'''<section id="{k}" class="member">
  <h2>{head}</h2>
  {kpis(c)}
  <figure>
    <div class="frame">{year_svg(c)}</div>
    <figcaption><span class="fig-n">Fig. {idx}</span>{cap}</figcaption>
  </figure>
  <div class="two">
    <div><h3>{bi("Por qué fidelizar" + ("lo" if c["g"] == "m" else "la"), "Why keep " + ("him" if c["g"] == "m" else "her"))}</h3><ul class="checks">{keep_html}</ul></div>
    <div><h3>{bi("Por qué está en riesgo", "Why " + ("he" if c["g"] == "m" else "she") + " is at risk")}</h3><ul class="risks">{risk_html}</ul></div>
  </div>
  <div class="callout"><span class="chip warn">{bi("Acción sugerida", "Suggested action")}</span><p>{act}</p></div>
  <h3>{bi("Lo que vieron las cámaras", "What the cameras saw")}</h3>
  <div class="kpis kpis-s">
    <div class="kpi"><span class="ve-label">{bi("Días con video", "Days with video")}</span><span class="val">{days}</span></div>
    <div class="kpi"><span class="ve-label">{bi("Series", "Sets")}</span><span class="val">{t["sets"]}</span></div>
    <div class="kpi"><span class="ve-label">{bi("Repeticiones", "Reps")}</span><span class="val">{bi(n_es(t["reps"]), n_en(t["reps"]))}</span></div>
    <div class="kpi"><span class="ve-label">{bi("Minutos de trabajo", "Minutes of work")}</span><span class="val">{t["minutes"]}</span></div>
  </div>
  <p class="badges">{bi("Insignias en el video:", "Badges in the video:")} {badges}</p>
  {video_block(c)}
</section>'''


page = f'''<!doctype html>
<html lang="es" data-lang="es" data-register="instrument">
<head>
<title>AnimalX Caldas: Víctor y Manuela, por qué fidelizarlos</title>
<meta name="robots" content="noindex, nofollow">
<link rel="stylesheet" href="https://rikuy.si/corporate/assets/fonts/rikuy-fonts.css">
<link rel="stylesheet" href="kit.css" data-ve-kit>
<style>
:root {{ color-scheme: light; --bg:#F6F9F8; --surface:#FFFFFF; --text:#14133F; --text-dim:#5B5B74; --accent:#2E7D7C; --accent-dim:#2E7D7C1f;
  --border:rgba(20,19,63,.10); --border-bright:#5B5B74; --ok:#2E7D7C; --warn:#5B5B74; --risk:#B42318; --info:#263962;
  --font-display:"Grift","Onest",system-ui,sans-serif; --font-body:"Onest",system-ui,sans-serif; --font-mono:"JetBrains Mono",ui-monospace,monospace; --display-weight:600; }}
html[data-lang="es"] [lang="en"], html[data-lang="en"] [lang="es"] {{ display:none !important; }}
.topbar {{ display:flex; align-items:center; gap:var(--s-5); padding:var(--s-4) 0; border-bottom:1px solid var(--border); margin-bottom:var(--s-6); flex-wrap:wrap; }}
.topbar img {{ height:36px; width:auto; }}
.topbar .ax {{ height:40px; }}
.topbar nav {{ display:flex; gap:var(--s-4); margin-left:auto; flex-wrap:wrap; }}
.topbar nav a {{ color:var(--text); text-decoration:none; font-size:var(--t-small); }}
.lang {{ display:flex; border:1px solid var(--border-bright); border-radius:999px; overflow:hidden; }}
.lang button {{ font:inherit; font-size:var(--t-small); padding:6px 14px; border:0; background:transparent; color:var(--text); cursor:pointer; min-height:36px; }}
.lang button[aria-pressed="true"] {{ background:#14133F; color:#F6F9F8; }}
.kpi-sub {{ display:block; font-size:var(--t-small); color:var(--text-dim); margin-top:var(--s-1); }}
.tr-risk {{ color:var(--risk); }}
.member {{ padding-top:var(--s-8); border-top:1px solid var(--border); margin-top:var(--s-8); scroll-margin-top:24px; }}
.two {{ display:grid; grid-template-columns:1fr; gap:var(--s-6); margin:var(--s-6) 0; }}
@media (min-width:900px) {{ .two {{ grid-template-columns:1fr 1fr; }} }}
.checks, .risks {{ list-style:none; padding:0; margin:var(--s-3) 0 0; }}
.checks li, .risks li {{ padding:var(--s-2) 0 var(--s-2) 28px; border-bottom:1px solid var(--border); position:relative; }}
.checks li::before {{ content:"✓"; position:absolute; left:0; color:var(--accent); font-weight:700; }}
.risks li::before {{ content:"!"; position:absolute; left:6px; color:var(--risk); font-weight:700; }}
.callout {{ background:var(--surface); border-radius:var(--r-2); padding:var(--s-4); margin:var(--s-5) 0; border:1px solid var(--border); }}
.callout .chip.warn {{ background:#DCE064; color:#14133F; }}
.callout p {{ margin-top:var(--s-2); }}
.badges .chip {{ margin-right:var(--s-2); }}
.vid-row {{ display:grid; grid-template-columns:1fr; gap:var(--s-5); align-items:start; }}
@media (min-width:900px) {{ .vid-row {{ grid-template-columns:3fr 1fr; }} }}
.vid video {{ width:100%; height:auto; border-radius:var(--r-2); background:#14133F; display:block; }}
.vid-phone video {{ max-width:320px; }}
.vid-actions {{ display:flex; flex-direction:column; gap:var(--s-2); margin-top:var(--s-3); max-width:320px; }}
.btn-wa, .btn-dl {{ font:inherit; font-weight:600; font-size:var(--t-small); min-height:48px; border-radius:999px; display:flex; align-items:center; justify-content:center; text-decoration:none; cursor:pointer; padding:0 var(--s-4); }}
.btn-wa {{ background:#DCE064; color:#14133F; border:0; }}
.btn-dl {{ background:transparent; color:#14133F; border:1px solid #14133F; }}
.kpis-s .val {{ font-size:var(--t-h2); }}
.note {{ font-size:var(--t-small); color:var(--text-dim); }}
</style>
</head>
<body><main>
<div class="topbar">
  <img src="axs-rikuy-logo.svg" alt="Rikuy" width="148" height="72">
  <img class="ax" src="axs-animalx-logo.png" alt="AnimalX" width="152" height="40">
  <nav><a href="#victor">Víctor</a><a href="#manuela">Manuela</a><a href="#metodo">{bi("Cómo se midió", "How it was measured")}</a></nav>
  <div class="lang" role="group" {aria("Idioma", "Language")}><button type="button" data-set-lang="es" aria-pressed="true">ES</button><button type="button" data-set-lang="en" aria-pressed="false">EN</button></div>
</div>
<header>
  <h1>{bi("Dos socios valiosos, dos riesgos distintos", "Two valuable members, two different risks")}</h1>
  <p class="lead">{bi(f"Víctor vino los 12 meses del año, pero septiembre fue su peor mes desde 2021. Manuela está volviendo, y <b>su plan vence el 16 de noviembre</b>.",
                      f"Víctor came every month of the year, but September was his worst month since 2021. Manuela is coming back, and <b>her plan ends on November 16</b>.")}</p>
  <p class="meta">AnimalX Caldas · {bi("historial del ERP al 2 nov 2026 · video del 29 al 31 oct 2026", "ERP history as of Nov 2, 2026 · video from Oct 29 to 31, 2026")}</p>
</header>
<figure>
  <div class="frame">{history_svg()}</div>
  <figcaption><span class="fig-n">Fig. 1</span>{bi("Visitas por mes desde 2020: Víctor se mantiene cerca de 20; Manuela tuvo su pico en 2023 y hoy viene unas 6 veces al mes.",
                                                  "Visits per month since 2020: Víctor stays near 20; Manuela peaked in 2023 and now comes about 6 times a month.")}</figcaption>
</figure>
{member(V, 2)}
{member(M, 3)}
<section id="metodo" class="member">
  <h2>{bi("Cómo se midió", "How it was measured")}</h2>
  <ul class="checks">
    <li>{bi("Visitas, vencimiento y compras: ficha de cada socio en el ERP del gimnasio (control de acceso), consultada el 2 nov 2026. El ERP tiene registros desde enero de 2020.", "Visits, plan end and purchases: each member's profile in the gym ERP (access control), read on Nov 2, 2026. The ERP has records from January 2020.")}</li>
    <li>{bi("Series, repeticiones y ejercicios: video de las cámaras 1 a 4 del 29 al 31 oct. El conteo automático de repeticiones acertó con ±1 en 8 de 10 series revisadas a mano.", "Sets, reps and exercises: video from cameras 1 to 4, Oct 29 to 31. The automatic rep count was within ±1 on 8 of 10 sets checked by hand.")}</li>
    <li>{bi("El récord del video es dramatizado: se muestra la serie de mayor esfuerzo y no se afirma ningún peso. Los niveles (uno cada 250 repeticiones) son una regla del video.", "The record in the video is dramatized: it shows the highest-effort set and states no weight. The levels (one every 250 reps) are a rule of the video.")}</li>
    <li>{bi("La figura 3D es SAM 3D Body sobre el video; la barra, el banco y las mancuernas son ilustrativos.", "The 3D figure is SAM 3D Body on the video; the bar, bench and dumbbells are illustrative.")}</li>
    <li>{bi("Privacidad: solo nombres de pila. Los videos muestran a otras personas del gimnasio; compártelos solo con cada socio. Esta página no está indexada y vence a los 30 días.", "Privacy: first names only. The videos show other people in the gym; share them only with each member. This page is not indexed and expires after 30 days.")}</li>
  </ul>
</section>
<section class="sources" {aria("Fuentes", "Sources")}><p class="ve-label caps">{bi("Fuentes", "Sources")}</p>
  <p><code>{bi("ERP AnimalX Caldas · control de acceso · 2026-11-02", "AnimalX Caldas ERP · access control · 2026-11-02")}</code> · <code>{bi("DVR, cámaras 1 a 4 · 2026-10-29 a 2026-10-31", "DVR, cameras 1 to 4 · 2026-10-29 to 2026-10-31")}</code> · <code>Rikuy · animalx-epic-video {a.version}</code></p>
</section>
</main>
<script>
(function(){{
  var root=document.documentElement;
  var titles={{es:"AnimalX Caldas: Víctor y Manuela, por qué fidelizarlos",en:"AnimalX Caldas: Víctor and Manuela, why keep them"}};
  function setLang(l){{
    root.setAttribute('data-lang',l); root.setAttribute('lang',l); document.title=titles[l];
    document.querySelectorAll('[data-aria-'+l+']').forEach(function(x){{x.setAttribute('aria-label',x.getAttribute('data-aria-'+l));}});
    document.querySelectorAll('[data-set-lang]').forEach(function(b){{b.setAttribute('aria-pressed',b.getAttribute('data-set-lang')===l?'true':'false');}});
    document.querySelectorAll('video[data-src-'+l+']').forEach(function(v){{
      var s=v.getAttribute('data-src-'+l); if(v.getAttribute('src')!==s){{v.pause(); v.setAttribute('src',s); v.setAttribute('poster',v.getAttribute('data-poster-'+l)); v.load();}}
    }});
    document.querySelectorAll('[data-dl]').forEach(function(a){{a.setAttribute('href','axs-'+a.getAttribute('data-dl')+'-'+l+'-movil.mp4');}});
    try{{localStorage.setItem('axs-lang',l);}}catch(e){{}}
  }}
  document.querySelectorAll('[data-set-lang]').forEach(function(b){{b.addEventListener('click',function(){{setLang(b.getAttribute('data-set-lang'));}});}});
  var start='es'; try{{start=localStorage.getItem('axs-lang')||((navigator.language||'es').slice(0,2)==='en'?'en':'es');}}catch(e){{}}
  setLang(start);
  document.querySelectorAll('[data-share]').forEach(function(b){{
    b.addEventListener('click',function(){{
      var l=root.getAttribute('data-lang'), k=b.getAttribute('data-share');
      var url=new URL('axs-'+k+'-'+l+'-movil.mp4',location.href).href;
      var text=l==='es'?'Tu video de entrenamiento en AnimalX':'Your training video at AnimalX';
      fetch(url).then(function(r){{return r.blob();}}).then(function(bl){{
        var file=new File([bl],'animalx-'+k+'.mp4',{{type:'video/mp4'}});
        if(navigator.canShare&&navigator.canShare({{files:[file]}})){{return navigator.share({{files:[file],text:text}});}}
        throw new Error('no file share');
      }}).catch(function(){{window.open('https://wa.me/?text='+encodeURIComponent(text+': '+url),'_blank','noopener');}});
    }});
  }});
}})();
</script>
</body>
</html>'''
assert '\u2013' not in page and '\u2014' not in page, 'dash in page text'
(OUT / 'animalx-socios.src.html').write_text(page)
print(OUT / 'animalx-socios.src.html', len(page))
