# CSA S16 Structural Calculator

## Overview
A multi-page Streamlit app for checking steel members per CSA S16 (Canadian steel design standard).

## Project Structure
```
├── app.py                                          # Page 1 — Flexure Calculator (W sections)
├── _theme.py                                       # Global UI theme (CSS, logo, footer, disclaimer page)
├── connection_diagram.py                           # SVG connection diagram generator
├── static/
│   └── logo.png                                    # Infraspective Solutions brand logo
├── pages/
│   ├── 2_Compression.py                            # Page 2 — Compression (W + HSS)
│   ├── 3_Bolted_Connections.py                     # Page 3 — Bolted Connections
│   ├── 4_Beam_Column_Members.py                    # Page 4 — Beam-Column Check (Cl. 13.8)
│   ├── 5_Tension_Members.py                        # Page 5 — Tension Member (Angle, one-leg)
│   └── 6_Welded_Connections.py                     # Page 6 — Welded Connection Solver
├── data/
│   ├── w_sections.csv                              # 285 Canadian W-sections (UTF-8)
│   ├── Properties Table - HSS - Rectangular.csv   # HSS Rectangular (UTF-8)
│   ├── Property Table - HSS - Circle.csv           # HSS Circular (latin-1)
│   └── Property Table - HSS - Square.csv           # HSS Square (latin-1)
└── .streamlit/config.toml
```

## Logo Assets
- `static/logo.png` — sidebar logo (original)
- `static/logo_brand.jpg` — high-res brand logo (JPEG, white background) used in page headers

## Branding & Theme (_theme.py)
- `apply_theme()` — injects global CSS; call once per page before any UI
- `render_sidebar_logo()` — displays logo at sidebar top via `st.sidebar.image()`
- `render_footer()` — sticky dark footer bar with "INFRASPECTIVE SOLUTIONS" text
- `render_page_header(title, subtitle)` — full-width branded card at top of each page: logo (white bg panel) + blue divider + title/subtitle text; replaces `st.title()` on all pages
- `render_page_banner(title, subtitle)` — dark blue banner below page title
- `disclaimer_page()` — full styled disclaimer gate (logo + scrollable agreement + checkbox/button)
- Logo loaded from `static/logo.png`, base64-encoded at runtime for HTML embeds

### Theme Palette
- Dark: `#0F172A`, Nav: `#1E3A8A`, Mid: `#1E40AF`, Blue: `#2563EB`
- Sidebar: dark navy → blue gradient with blueprint grid overlay
- Metrics: blue-tinted cards with top accent border
- Code blocks: dark terminal style with monospace font
- Sticky footer: fixed bottom, dark with blue top border

## Pages

### Page 1 — Flexure (app.py)
- Section classification per CSA S16 Table 2 (Class 1–4)
- Flange/web slenderness using clear web depth h = d − 2k
- Laterally supported Mr using Zx (Class 1/2) or Sx (Class 3)
- Optional demand/capacity check

### Page 2 — Compression (pages/2_Compression.py)
- W sections and circular/rectangular/square HSS
- CSA S16 Cl. 13.3 column curve: Fcr = Fy / (1 + λ^(2n))^(1/n), n=1.34
- KL/r, λ, Fe, Cr calculations

### Page 3 — Bolted Connections (pages/3_Bolted_Connections.py)
- Bolt shear, bearing, block shear, net section checks per CSA S16

### Page 4 — Beam-Column Members (pages/4_Beam_Column_Members.py)
- W sections + HSS, section type filter, search box
- Material inputs: Fy, E
- Axial condition: TENSION or COMPRESSION
- **Tension + Bending** (CSA S16 Cl. 13.9):
  - Tr = φ·Fy·A; Mrx = φ·Fy·Zx; Mry = φ·Fy·Zy
  - Interaction: Tf/Tr + Mfx/Mrx + Mfy/Mry ≤ 1.0
- **Compression + Bending** (CSA S16 Cl. 13.8.2):
  - CSA S16 column curve for Cr (n = 1.34)
  - ω₁ moment gradient via κ-method or code defaults
  - Amplified moments: U1 = ω₁ / (1 − Cf/Ce) ≥ 1.0
  - β = min(0.85, 0.6 + 0.4λy)
  - Interaction: Cf/Cr + 0.85·U1x·Mfx/Mrx + β·U1y·Mfy/Mry ≤ 1.0
  - Additional moment check: Mfx/Mrx + Mfy/Mry ≤ 1.0

## Technical Notes

### CSV Encoding
- w_sections.csv and HSS Rectangular: UTF-8 (columns contain garbled `ý`, `?` for ², ⁴)
- HSS Circle and Square: latin-1 fallback
- `_norm()` strips all non-ASCII chars so garbled headers resolve correctly

### Column Alias System
Each page uses a `_norm()` + `_ALIASES` lookup to map raw CSV header variants to canonical property names. Multipliers are always applied unconditionally: Ix/Iy×1e6, Zx/Zy/Sx/Sy×1e3, J×1e3, Cw×1e9.

### CSA S16 Constants
- φ = 0.9 for all resistance factors
- n = 1.34 (hot-rolled column curve exponent)

## Running
```bash
streamlit run app.py --server.port 5000
```
