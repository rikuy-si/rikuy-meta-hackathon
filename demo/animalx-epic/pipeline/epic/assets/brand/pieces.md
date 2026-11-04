# Recipes by piece

Always: logo from `assets/logo/`, colors and type from `brand.md`, copy rules from `voice.md`. One idea and one primary action per piece. The primary action says what happens ("Start free", "Check your cameras"), never "Request a demo".

## Slide deck (16:9, 13.333 x 7.5 in)
Use the template (`assets/slides/`) or `scripts/make_deck.js`. Cover, contents (5 items at most), chapter covers, content slides, closing. One idea per slide, title says the point. Numbers in Grift, tool names and code in JetBrains Mono. Footer: wordmark left, rikuy.si and slide number right. Investor decks may use the investor descriptor.

## One-pager or PDF (US Letter, 8.5 x 11 in)
Blanco background. Header: logo color, left. Title in Grift (about 34 pt), lead in Onest (13 pt). Two or three blocks on a 12 column grid. One Noche panel for the key fact or code sample. Footer: rikuy.si and contact. Margins 0.6 in.

## Social post
- Square 1080 x 1080 or portrait 1080 x 1350; story 1080 x 1920 (keep text inside the middle 1080 x 1420).
- One short headline in Grift (at most 8 words), one line of Onest support, logo small in a corner. Noche or Menta background; Amarillo only for the one word or number that matters.
- No stock photos. A camera still, if used, gets the navy tint and the viewfinder corners.
- LinkedIn banner 1584 x 396. Open Graph image 1200 x 630 (Noche, wordmark, one line).

## Email (HTML, 600 px wide)
Blanco background, logo color at the top (width 96 px), Onest 16 px, one Grift headline, one Amarillo button on a Noche or Menta block. System fonts fallback: Onest, Arial. Subject under 50 characters, no all caps, no exclamation marks.

## Web section
Use the site classes if you are in the site repository (see https://rikuy.si/design-system). Otherwise: a band (Blanco or Menta), 1240 px content width, Grift title, Onest body, 24 px cards with 18 px radius, one primary button. Mobile first (375 px), tap targets 44 px.

## Document (Word, Google Docs)
Onest 11 pt body, Grift for headings if installed (otherwise Onest 600), Noche text on white, Teal links. Title block with the logo color. Tables on solid surfaces with Bruma hairlines.

## Diagrams
Noche lines, Menta and Teal fills, Amarillo for the single step that matters, labels in Onest, tool names in JetBrains Mono. Camera on the left, Rikuy in the middle, agent on the right is the standard flow. Never draw Rikuy as a box or a device: it is software, shown on the computer the business already has or as the Rikuy pill.

## Checklist before delivering
- Logo is a file from `assets/logo/`, right variant for the background, clear space respected.
- Only brand colors; no white on Menta; Amarillo under about 7 percent.
- Titles Grift (or Onest as fallback), body Onest, code mono; nothing under 12 px.
- No dashes, no forbidden words, no invented facts; unknown facts marked `[sin dato]`.
- One idea, one primary action.
- Contrast: Noche on Blanco or Menta, Blanco or Bruma on Noche.
