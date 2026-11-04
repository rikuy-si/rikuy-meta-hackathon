# EnPiso Visión v0.1.0: plan

(Written for v0.1.0; still the plan for v0.1.3, which adds English (§7, written for v0.1.2) and turns the layers on by default.)

First client-facing version of the EnPiso × Rikuy camera app. The reader is a garment plant owner or manager who already uses EnPiso. They should understand the screen in seconds, trust each number, and check it in the video with one tap.

## 1. Audience and job

- **Who:** plant owner or module supervisor. They know SAM, efficiency and modules, but they are not data people. They use a phone on the floor and a laptop in the office.
- **Job:** "Tell me where my module is losing time, and show me the proof."
- **Tone:** balance and support. The app talks about **stations (Puesto A, Puesto B) and the module**, never about people. No names, codes or rankings of people. Waiting time is kept separate from sewing time, so the person who waits for work is never read as slow.

## 2. Insight selection

Sources: the expert interview (`wiki/garment-floor-control.md`, transcript 00:17:53 to 00:21:47) and the POC findings (`wiki/enpiso-zoe-vision-poc.md`, `poc-enpiso-zoe-v0.0.2/validation.md`, `ZOE-V003-README.md`).

The expert asked for five things. Each maps to what the data can honestly support today:

| Expert asked for | What v0.1.0 shows | Source | Confidence |
|---|---|---|---|
| Module efficiency per hour | Hourly bars 06:00 to 14:00, CP pieces × 3.8 min ÷ (2 × 60 min). Average 59 %, best 13:00 (73 %). The 130 % at 11:00 is flagged as catch-up keying (12 pieces in 20 s at 11:01). | CP | Media (headcount and SAM scope are assumptions) |
| Efficiency by zone or station | Real: time split per station (B sews 77 %; A "en su puesto" 85 %, low confidence). Per-station efficiency against SAM: **ejemplo** with the v0.0.5 mock sheet. | Video; Ejemplo | Media; Ejemplo |
| Restriction operation | Real: **Puesto B paces the module** (pieces wait about 36 s for B; B waits 3 s). The exact operation inside B: **próximamente**; the mock shows OP06 as the example restriction. | Video; Ejemplo | Media (queue: Baja) |
| Effective vs waiting minutes | Puesto B in 96 recorded minutes: 74 min sewing, 14 min fetching the piece, 1.5 min delivering, 1.3 min waiting, 4.7 min out of view. | Video | Media |
| Sewing-only ranking | Ranking **by station, not by person**: B sews one piece every 111 s (32 pieces/h sewing only) against 28/h with transfers. A: próximamente (A hides her own table from this camera). | Video | Media |

**Top three (landing cards), in this order:**

1. **"El Puesto B marca el ritmo del módulo", 127 s por pieza.** First because it is the one thing EnPiso cannot show today (the expert: "te va a especificar dónde está la ineficiencia dentro de un módulo"), it is actionable (rebalance work towards A), and it is backed by 19 clean cycles plus visible video proof (pieces stacked in the queue while B sews). Source video, confidence media.
2. **"La eficiencia del módulo cambió mucho durante el día", 59 % promedio.** The expert's first request and the owner's familiar language. It uses CP data the owner already has, plus the SAM, so it anchors the rest. Stated assumptions: 2 operators, CP SAM covers sewing only. Source CP, confidence media.
3. **"El Puesto B cosió 74 de 96 minutos y casi no esperó", 77 %.** The effective-vs-waiting view the expert called "una belleza". It also corrects a hunch from the meeting ("always waiting"): B barely waits; the lost time is fetching pieces (14 min). Source video, confidence media.

**Trust builder (dark band right under the cards):** "34 de 35 registros de CP se ven en el video". The keypad hand is on the CP keypad within about 1.2 s of 34 of 35 captures; chance would give 43 %. Source CP + video, confidence alta. This answers "why should I believe the camera?" before the owner scrolls into the data.

**Para revisar (review cards):** 13 of 45 cycles have no CP capture (12 of them are low-confidence cycles, often detector splits; one clean cycle at 13:37), and the longest clean cycle (6 min 22 s at 14:32). Both are framed as "worth a look", not as faults.

**Left out on purpose:** per-person efficiency, any person ranking, names, the 3D scene, queue-dwell as a headline (low confidence), and the video-cycle count as an output figure (28.4/h from video differs from 22.1/h in CP; both are shown only where the difference is explained).

## 3. Information architecture

```
Header (Noche): EnPiso logo + "Visión" · [Panel | Video] · "con tecnología" Rikuy
│
├─ #/panel  (default landing)
│   ├─ Hero (Menta band): context chips, H1 "Lo que vimos en el Módulo 28", 3 insight cards (glass)
│   │    card = rank · source chip · confidence meter · headline · big number · one line · 3 proof stills
│   │           · idea para conversar · [Ver en video] + clip time · ¿Cómo lo medimos?
│   ├─ Trust (Noche band): 34 de 35, 4 facts, [Ver un registro en video], 3 stills
│   ├─ Los datos (Blanco band, solid cards)
│   │    eficiencia por hora (bars, 13:00/14:00 open the video) · minutos efectivos y de espera
│   │    · operación restricción · por puesto, solo costura · para revisar en video (2 cards)
│   ├─ Ejemplo (Papel band, striped "Ejemplo" banner): carga por puesto vs takt, operaciones por SAM,
│   │    eficiencia por puesto y hora, animación 3D de la ficha simulada
│   ├─ Cómo leer estos datos (Menta band): principles + glossary
│   └─ Footer (Teal)
│
└─ #/video?t=<s>&clip=<a>-<b>&from=<insight>&capas=zonas,puestos,esqueletos
    ├─ Back bar: "← Volver al panel" (returns to #/panel/<insight>, scrolls and flashes the card) + "Viendo: ..."
    ├─ Player (Noche panel): 6 recordings stitched into one 96-min timeline, plant clock, ±10 s, 1×/2×/4×
    ├─ Timeline: lanes Hallazgos · Ciclos del Puesto B · Registros CP · Esperas y cola; all or 10-minute zoom;
    │    keyboard slider; prev/next moment
    ├─ Clip bar: "Repetir clip" / "Seguir viendo"
    ├─ Live chips: Puesto B state, Puesto A state, cola, ciclo
    └─ Side: Capas (Zonas, Puestos, Esqueletos; ON by default since v0.1.3) · Momentos list with filters · Copiar enlace
```

Deep links are hash routes, so they work on any static host without server rewrites. The video module does not touch the network until it is first opened.

## 4. Brand decisions

- **Hierarchy:** the product is EnPiso's ("EnPiso Visión"); Rikuy is the ingredient brand ("con tecnología Rikuy"). The EnPiso logo leads at the top left; the Rikuy wordmark (negative on Noche, Blanco on Teal) is secondary, at 72 px, the minimum width.
- **Header on Noche:** the EnPiso logo's lime and sage read well on Noche and poorly on Blanco.
- **Rikuy kit:** Blanco and Menta bands, glass only on the insight cards (the owner's "product" surface), solid surfaces for tables and numbers, Noche for the trust band and the player, Teal footer, Amarillo for the single highlighted number, the active nav pill and the play controls. Grift for titles and numbers, Onest for text, JetBrains Mono for times and data. The camera viewfinder corners frame the player.
- **Deviation:** camera footage is shown in natural colour, not the navy duotone. Here the footage is evidence: the owner must recognise the garment and the keypad.
- **Copy:** Spanish (Colombia), plain words, no dashes, never below 12 px; banned words are checked by the build.

## 5. Copy deck (Spanish UI)

| Place | Copy |
|---|---|
| Nav | Panel · Video |
| Co-brand | EnPiso Visión · con tecnología Rikuy |
| H1 / lead | Lo que vimos en el Módulo 28 / Tres hallazgos para equilibrar el módulo, cada uno con su prueba en video. Toque **Ver en video** para revisarlo usted mismo. |
| Card 1 | El Puesto B marca el ritmo del módulo · **127 s** por pieza en el Puesto B · Las piezas lo esperan en la cola unos 36 s. El Puesto B espera pieza solo 3 s. · Idea para conversar: Pasar una parte del trabajo del Puesto B al Puesto A podría subir las piezas por hora del módulo. Vale la pena probarlo con la ficha técnica en mano. |
| Card 2 | La eficiencia del módulo cambió mucho durante el día · **59 %** promedio de las 9 horas · La mejor hora fue las 13:00 con 73 %. Las más bajas, 09:00 y 10:00 con 32 %. · Idea: Revisar con la supervisora qué pasó entre las 09:00 y las 11:00, cuando bajaron los registros. |
| Card 3 | El Puesto B cosió 74 de 96 minutos y casi no esperó · **77 %** del tiempo grabado, cosiendo · Esperó pieza solo 1,3 min. Lo que no cose se va sobre todo en ir por la pieza: 14 min. · Idea: Dejar la pieza al alcance del Puesto B podría convertir parte de esos minutos de traslado en costura. |
| Card actions | Ver en video · Clip de 13:50 a 13:51 (hora planta) · ¿Cómo lo medimos? · Prueba en video. Toque una imagen para abrir ese momento. |
| Trust | ¿Se puede confiar en estos números? · **34** de 35 registros de CP se ven en el video · En cada registro, la mano del Puesto B está en el teclado CP. Diferencia típica: 1,2 s. Si fuera al azar, coincidirían solo 43 de cada 100. · Ver un registro en video |
| Data | Los datos · Eficiencia del módulo por hora · Minutos efectivos y de espera · Operación restricción ("Hoy, el puesto que pone el ritmo: Puesto B · fileteadora") · Por puesto, solo costura ("Comparamos puestos, no personas.") · Para revisar en video |
| Assumptions | Cómo se calcula: piezas registradas en CP × 3,8 min ÷ (2 personas × 60 min). Supuestos: 2 personas en el módulo toda la hora, y el SAM de CP (3,8 min) cubre solo costura. |
| Labels | Fuente: Video · Fuente: CP (EnPiso) · Fuente: CP + Video · Confianza alta / media / baja · Próximamente · Ejemplo |
| Mock | Ejemplo con una ficha técnica simulada. No son datos de su planta. · Eficiencia contra SAM, por puesto y por operación · Para hacerlo con datos reales necesitamos: la ficha técnica con el SAM de cada operación; qué operaciones hace cada puesto; cuántas personas hubo cada hora. |
| Principles | Hablamos de puestos y del módulo, no de personas. Sin nombres ni rankings de personas. · Es para equilibrar el trabajo y apoyar al equipo: separamos el tiempo de costura del tiempo de espera y de traslado. · Cada número dice de dónde sale (video, CP o ejemplo) y qué tan seguros estamos. · Todo está en hora de planta. El reloj dentro del video va una hora adelantado. |
| Tooltips | SAM: Minutos estándar que debería tomar la prenda a ritmo normal. · Eficiencia: Minutos estándar producidos ÷ minutos disponibles de las personas. 100 % es trabajar justo al estándar. · Takt: Cada cuánto debe salir una pieza para cumplir la meta. Para 28 piezas por hora: 3600 s ÷ 28 = 128,6 s. |
| Video | Volver al panel · Viendo: … · hora planta · Toda la grabación / 10 minutos · Capas sobre el video (Zonas, Puestos, Esqueletos: "Postura estimada, no identifica a nadie") · Momentos (Hallazgos, Ciclos, Registros CP, Esperas) · Copiar enlace · Repetir clip / Seguir viendo |
| Live chips | Puesto B: Cosiendo / Buscando la pieza / Entregando la pieza / Esperando pieza / Fuera de cámara · Puesto A: En su puesto / De pie (confianza baja) · Cola: con pieza / vacía (confianza baja) · Ciclo N: duración, con o sin registro CP |

## 6. Acceptance

- Landing is the panel with the 3 cards; each card's **Ver en video** opens the clip at its moment and plays it; **Volver al panel** returns to that card.
- Overlays are ON by default (v0.1.3); each toggle draws and clears; layers survive in the deep link.
- No console errors, no requests outside the bundle except the R2 recordings, no names or codes in any shipped file.
- 390 px and 1280 px screenshots reviewed and iterated (see `shots/`).

## 7. v0.1.2: Spanish and English

- **Switch:** a compact `ES | EN` pill pair in the header. On a phone it shares the nav row (pinned right, the nav leaves it room); from 768 px it sits between the nav and "powered by Rikuy". Blanco marks the active language so Amarillo stays the single highlight (the active nav pill).
- **Choice:** `?lang=` or `#/…&lang=`, then the saved choice (`localStorage`), then the browser (`en*` is English), otherwise Spanish. Deep links and "Copy link" carry `lang`.
- **English voice:** plain US English for a plant owner, not a literal translation. Brand names stay; "con tecnología Rikuy" is "powered by Rikuy". SAM, takt and CP stay. "Puesto A/B" is "Station A/B", "cola" is "queue", "operación restricción" is "bottleneck operation", "registro CP" is "CP capture", "Ver en video" is "See it on video", "Idea para conversar" is "An idea to discuss", "Para revisar" is "Worth a look", "Ejemplo" is "Example", "Próximamente" is "Coming soon".
- **Same tone rules in both languages:** stations, never people; no rankings of people; no surveillance or punishment words ("monitor", "watch", "punish", "spy" are banned by the build alongside the Spanish list).

| Place | Spanish | English |
|---|---|---|
| H1 | Lo que vimos en el Módulo 28 | What we saw in Module 28 |
| Card 1 | El Puesto B marca el ritmo del módulo | Station B sets the pace for the module |
| Card 2 | La eficiencia del módulo cambió mucho durante el día | Module efficiency swung a lot during the day |
| Card 3 | El Puesto B cosió 74 de 96 minutos y casi no esperó | Station B sewed 74 of 96 minutes and barely waited |
| Trust | ¿Se puede confiar en estos números? | Can you trust these numbers? |
| Mock | Ejemplo con una ficha técnica simulada. No son datos de su planta. | Example built on a simulated technical sheet. This is not data from your plant. |

