# CSA S16 Structural Calculator

## Overview
A multi-page Streamlit app for checking steel members per CSA S16 (Canadian steel design standard).

## Project Structure
```
├── app.py                                          # Page 1 — Flexure Calculator (W sections)
├── _theme.py                                       # Global UI theme (CSS, logo, footer, disclaimer page)
├── connection_diagram.py                           # SVG connection diagram generator (Page 3)
├── flexure_diagrams.py                             # SVG diagrams for Page 1 (cross-section, beam, LTB & shear curves)
├── static/
│   └── logo.png                                    # Infraspective Solutions brand logo
├── pages/
│   ├── 2_Compression.py                            # Page 2 — Compression (W + HSS)
│   ├── 3_Bolted_Connections.py                     # Page 3 — Bolted Connections
│   ├── 4_Beam_Column_Members.py                    # Page 4 — Beam-Column Check (Cl. 13.8)
│   ├── 5_Tension_Members.py                        # Page 5 — Tension Member (Angle, one-leg)
│   └── 6_Welded_Connections.py                     # Page 6 — Welded Connection Solver
├── data/                                           # ALL regenerated from CISC SST12.1 (see scripts/convert_sst12.py)
│   ├── w_sections.csv                              # 289 W-sections (shared pipeline, simple headers)
│   ├── Property Table - HSS - Square.csv           # 82 square HSS
│   ├── Properties Table - HSS - Rectangular.csv   # 99 rectangular HSS
│   ├── Property Table - HSS - Circle.csv           # 80 round HSS
│   ├── Channel Sections Properties.csv            # 72 C + MC channels (tension pipeline)
│   ├── Structural Tees WT Properties.csv          # 188 WT tees (tension pipeline)
│   ├── Double Angle Properties.csv                # 228 double angles (tension pipeline)
│   ├── Angle Properties Table.xlsx                # 149 single angles (tension pipeline)
│   └── _legacy_sst_backup/                         # original pre-SST12.1 data files (not globbed)
├── scripts/
│   └── convert_sst12.py                            # regenerates all data/ files from SST12.1 xlsx
└── .streamlit/config.toml
```

## Logo Assets
- `static/logo_mark.png` — single brand mark (transparent PNG); the ONLY logo shown in the app. Rendered in the sidebar only.
- `static/logo.jpg` — high-res source brand logo (opaque). Kept as source; not embedded directly.
- `static/logo.png` — legacy original logo (retained; `_logo_b64()` prefers `logo_mark.png`).

## Branding & Theme (_theme.py)
- **Single-logo rule:** exactly ONE logo appears in the UI — a WHITE wordmark in the sidebar. There is NO top-bar/header logo overlay (it caused mobile hamburger overlap). Do not reintroduce a second logo.
- `apply_theme()` — injects global CSS (Inter font, refined radii/shadows, hover/focus animations, responsive `@media(max-width:640px)`, `overflow-x:hidden`, styled mobile hamburger, sidebar nav styling + active-page highlight via `aria-current`); call once per page before any UI.
- `render_sidebar_logo()` — renders the transparent brand mark recolored to white via CSS `filter: brightness(0) invert(1)` (blends onto the navy sidebar, no white plate), a small tagline, a divider, a "Calculators" label, and the six-page nav via `st.sidebar.page_link()` with Material icons.
- `render_footer()` — sticky dark footer bar with "INFRASPECTIVE SOLUTIONS" text.
- `render_page_header(title, subtitle)` / `render_page_banner(title, subtitle)` — defined but not currently called by any page.
- `disclaimer_page()` — full styled disclaimer gate (logo + scrollable agreement + checkbox/button).
- Logo loaded from `static/logo_mark.png`, base64-encoded at runtime for HTML embeds.
- Pre-existing console noise: `Invalid color ... widgetBackgroundColor in theme.sidebar` warnings come from empty sidebar theme keys in `.streamlit/config.toml`; harmless.

### Theme Palette
- Dark: `#0F172A`, Nav: `#1E3A8A`, Mid: `#1E40AF`, Blue: `#2563EB`
- Sidebar: dark navy → blue gradient with blueprint grid overlay
- Metrics: blue-tinted cards with top accent border
- Code blocks: dark terminal style with monospace font
- Sticky footer: fixed bottom, dark with blue top border

## Pages

### Page 1 — Flexure (app.py)
- Section classification per CSA S16 Table 2 (Class 1–4) + cross-section SVG with plastic/elastic stress overlay
- Flange/web slenderness using clear web depth h = d − 2k
- Laterally supported Mr using Zx (Class 1/2) or Sx (Class 3); Class 4 via Se
- Shear (Cl. 13.4.1.1) unstiffened/stiffened webs + Fs-vs-h/w SVG curve
- LTB (Cl. 13.6) with preset ω₂ cases + advanced ω₂ formulas (linear-gradient κ Eq. 3, general 4-point Eq. 2); beam-elevation SVG + Mr-vs-Lb curve SVG
- Deflection check with CSA S16 Table D.1 limits (industrial floor/roof, crane girders, wind/storey drift, etc.) plus custom L/n
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

### Data Source (CISC SST12.1)
- All `data/` files are regenerated from `attached_assets/CISC_StructuralSectionTables_SST12.1_*.xlsx` via `scripts/convert_sst12.py`.
- SST12.1 already stores properties in the app's 10^x convention (Ix=10^6, Sx/Zx=10^3, J=10^3, Cw=10^9) — no re-scaling on conversion.
- Two output conventions from one source:
  - **Shared pipeline** (flexure/compression/beam-column) — W + HSS CSVs use **simple bare headers** (`Ix`, `Sx`, `Zx`, `Area`, `d`, `b`, `t`, `w`, `k`, `ba/t`, `h/w`) which every page's alias table matches directly.
  - **Tension pipeline** — channel/WT/double-angle CSVs + single-angle xlsx use bespoke exact names (`Area_mm2`, `t_mm`, `w_mm`, `b_mm`, `d_mm`, `rx_mm`, `ry_mm`).
- HSS designations are renamed from SST12.1's `HS…` prefix to `HSS…` so `section_family()` (`"HSS" in n`) and `parse_hss_designation()` keep working.
- WWF sections are NOT in SST12.1 (separate CISC welded-wide-flange table); no WWF data is generated.
- To regenerate: `python3 scripts/convert_sst12.py` (backs up originals to `data/_legacy_sst_backup/` on first run only).

### Column Alias System
Each shared page uses a `_norm()` + alias lookup to map CSV header variants to canonical property names. Multipliers are applied unconditionally in calc: Ix/Iy×1e6, Zx/Zy/Sx/Sy×1e3, J×1e3, Cw×1e9.

### CSA S16 Constants
- φ = 0.9 for all resistance factors
- n = 1.34 (hot-rolled column curve exponent)

## Running
```bash
streamlit run app.py --server.port 5000
```
