"""Build source/<client>/index.json + index.html (local viewer) from every day's presence.json/timeline.json.

usage: build_index.py CLIENT
The HTML references clips and sheets with relative paths, so open it from the source/<client>/ folder.
"""
import sys, json, pathlib, html

ROOT = pathlib.Path(__file__).resolve().parent
client = sys.argv[1]
cdir = ROOT / 'source' / client
days = []
for d in sorted(p for p in cdir.iterdir() if p.is_dir() and (p / 'presence.json').exists()):
    pres = json.load(open(d / 'presence.json'))
    tl = json.load(open(d / 'timeline.json')) if (d / 'timeline.json').exists() else {}
    ref = json.load(open(d / 'reference' / 'reference.json')) if (d / 'reference' / 'reference.json').exists() else {}
    items = []
    for cam, ivs in pres.items():
        for iv in ivs:
            items.append({**iv, 'clip': f"{d.name}/clips/{iv['name']}.mp4", 'track': f"{d.name}/clips/{iv['name']}.track.json",
                          'sheet': f"{d.name}/sheets/{iv['name']}.jpg"})
    items.sort(key=lambda x: x['w0'])
    days.append({'day': d.name, 'reference': ref.get('description', ''), 'first_seen': tl.get('first_seen'), 'last_seen': tl.get('last_seen'),
                 'seen_min': tl.get('seen_min'), 'zone_minutes': tl.get('zone_minutes', {}), 'blocks': tl.get('blocks', []),
                 'notes': ref.get('notes', ''), 'intervals': items,
                 'minutes_by_camera': {c: round(sum(i['duration'] for i in v) / 60, 1) for c, v in pres.items()}})
idx = {'client': client, 'days': days}
json.dump(idx, open(cdir / 'index.json', 'w'), indent=1, ensure_ascii=False)

E = html.escape
parts = [f"""<!doctype html><meta charset=utf-8><title>{E(client)} · source library</title>
<style>body{{font-family:system-ui;background:#111;color:#eee;margin:20px}} h2{{border-top:1px solid #444;padding-top:12px}}
table{{border-collapse:collapse;font-size:13px}} td,th{{padding:3px 8px;border-bottom:1px solid #333;text-align:left}}
.v-confirmed{{color:#6f6}} .v-mixed{{color:#fd6}} .v-auto{{color:#f96}} img{{height:120px}} video{{width:640px;display:block;margin:6px 0}}
.bar{{display:flex;height:22px;margin:8px 0;background:#222}} .bar div{{height:100%;font-size:10px;overflow:hidden;white-space:nowrap}}
</style><h1>{E(client)} — source library</h1><p>Private AnimalX footage. Internal use only.</p>"""]
COL = {}
pal = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe', '#008080', '#e6beff', '#9a6324']
for d in days:
    parts.append(f"<h2>{d['day']}</h2><p>{E(d['reference'])}<br>{E(d['notes'])}</p>"
                 f"<p>First seen {d['first_seen']} · last seen {d['last_seen']} · seen {d['seen_min']} min · by camera {d['minutes_by_camera']}</p>")
    if d['blocks']:
        t0 = d['blocks'][0]['t0']; t1 = d['blocks'][-1]['t1']; span = max(1, t1 - t0)
        bar = []
        for b in d['blocks']:
            c = COL.setdefault(b['label'], pal[len(COL) % len(pal)])
            bar.append(f"<div title='{b['start']}-{b['end']} {E(b['label'])}' style='width:{100 * max(b['t1'] - b['t0'], 5) / span:.2f}%;background:{c}'>{E(b['label'])}</div>")
        parts.append("<div class=bar>" + ''.join(bar) + "</div>")
        parts.append("<table><tr><th>start</th><th>end</th><th>s</th><th>zone</th><th>activity</th><th>best cam</th></tr>" + ''.join(
            f"<tr><td>{b['start']}</td><td>{b['end']}</td><td>{b['duration_s']}</td><td>{E(b['label'])}</td><td>{b['activity']}</td><td>{b['best_camera']}</td></tr>" for b in d['blocks']) + "</table>")
    parts.append("<table><tr><th>camera</th><th>start</th><th>end</th><th>s</th><th>verified</th><th>score</th><th>sheet</th><th>clip</th></tr>")
    for i in d['intervals']:
        parts.append(f"<tr><td>{i['camera']}</td><td>{i['start']}</td><td>{i['end']}</td><td>{i['duration']}</td><td class=v-{i['verified']}>{i['verified']}</td>"
                     f"<td>{i['score']}</td><td><img loading=lazy src='{i['sheet']}'></td><td><a href='{i['clip']}'>mp4</a></td></tr>")
    parts.append("</table>")
(cdir / 'index.html').write_text('\n'.join(parts))
print('wrote', cdir / 'index.html', [(d['day'], len(d['intervals'])) for d in days])
