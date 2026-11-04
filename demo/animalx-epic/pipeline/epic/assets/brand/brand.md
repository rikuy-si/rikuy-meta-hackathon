# Rikuy look

Source of truth: https://rikuy.si/design.md and https://rikuy.si/design/tokens.json (copies in `assets/`).

## Color

| Name | Hex | Use |
|---|---|---|
| Noche | `#14133F` | Dark panels, text on light, buttons on light |
| Noche 2 | `#263962` | Surfaces on Noche, secondary text on light and on Menta |
| Menta | `#7FCCB4` | Protagonist: alternating bands. Text on it is Noche |
| Teal | `#2E7D7C` | Accents, links on light, footer, success |
| Blanco | `#F6F9F8` | Page background, text on dark |
| Amarillo | `#DCE064` | Highlight and primary call to action, 5 to 7 percent of a piece. Never text on Teal |
| Gris tinta | `#5B5B74` | Secondary text on light |
| Hielo | `#A9B6D3` | Secondary text on Noche |
| Bruma | `#CDD6E8` | Body text on Noche, hairlines on light |
| Menta pálida | `#BFE6DA` | Soft tints and blobs |
| Papel | `#FBFBF7` | Long reading, editorial pages |

Rules: no pure black; no white on Menta (contrast 1.8); on dark surfaces the highlight is Amarillo, on light it is Teal.

## Type

- Titles and big numbers: **Grift**, weight 600, tracking about -0.04em, tight line height (about 1.0 to 1.1).
- Body: **Onest**, 400, 16 to 17 px on screen, line height 1.55.
- Code, tool names, data: **JetBrains Mono**, 14 px, 500.
- Never set titles in Onest when Grift is available. Never below 12 px for readable text.
- Fonts: `assets/fonts/` (TTF for desktop apps, WOFF2 and `rikuy-fonts.css` for the web). Web: `<link rel="stylesheet" href="https://rikuy.si/corporate/assets/fonts/rikuy-fonts.css">`. Never load from Google Fonts.

## Logo

Files in `assets/logo/`, each as SVG, PNG (transparent) and PDF:
- `rikuy-logo-color`: on Blanco, Menta or light photos. Default.
- `rikuy-logo-negative`: on Noche and dark photos.
- `rikuy-logo-noche` and `rikuy-logo-blanco`: one color, for print or when color is not possible.
- `rikuy-icon`: app tile, favicon, avatar.

Clear space: half the height of the letter k on every side. Minimum width: 72 px on screen, 20 mm in print. Do not retype the name in any font, rotate, outline, add effects or change colors. The wordmark is a drawing, not a font.

## Shape and space

- Unit 4 px. Radius: 8, 12, 18, 24, 32 px; pills 999. Cards 18 or 24.
- Bands alternate Blanco and Menta; dark panels are Noche; footers Teal.
- Signature motif: viewfinder corners (four small L marks at the corners) in Menta on dark, Noche on Menta. A dotted veil over a camera still with one clear lens where the agent looks.
- Glass (frosted white, light blur) only for things the owner controls: the product, choices. Forms, tables and numbers sit on solid surfaces.
- Camera stills carry the navy tint (black to Noche, white to `#EAF0F8`).
- Motion (video, web): ease `cubic-bezier(.2,.7,.2,1)`, 150, 300, 600 ms. Respect reduced motion.
