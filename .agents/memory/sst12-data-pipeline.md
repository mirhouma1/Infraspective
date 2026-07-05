---
name: SST12.1 data pipeline
description: How the steel-section database is generated and the two header conventions consumers require
---
# Steel-section database (CISC SST12.1)

All `data/` files are generated from the SST12.1 xlsx by `scripts/convert_sst12.py`. SST12.1
already uses the app's 10^x property convention, so no re-scaling on conversion.

## Two consumer conventions (do NOT unify carelessly)
- **Shared pipeline** — `app.py` (flexure, W only), `pages/2_Compression.py`, `pages/4_Beam_Column_Members.py`
  all glob `data/*.csv` (non-recursive) and canonicalize via per-page alias tables. W + HSS CSVs must
  use **simple bare headers** (`Ix`, `Sx`, `Zx`, `Area`, `d`, `b`, `t`, `w`, `k`, `ba/t`, `h/w`).
  **Why:** flexure's alias for Zx/Sx/Zy/Sy only lists the `zx_103_mm` form (trailing garbled ³ stripped);
  rich headers like `Zx (10^3 mm^3)` normalize to `zx_103_mm3` and silently return None in flexure,
  while compression/beam-column DO match the rich form. Bare names match all three — that's the safe union.
- **Tension pipeline** — `pages/1_Tension_Members.py` reads FOUR fixed filenames with bespoke exact
  column names (`Area_mm2`, `t_mm`, `w_mm`, `b_mm`, `d_mm`, `rx_mm`, `ry_mm`) via pandas, plus the
  single-angle `Angle Properties Table.xlsx`. These are NOT aliased — names must be exact.

## Gotchas
- HSS designations: SST12.1 codes them `HS…`; rename to `HSS…` or `section_family()`/`parse_hss_designation()` break.
- WWF is not in SST12.1 (separate welded-wide-flange table) — no WWF data exists.
- Pre-existing quirk: compression/beam-column glob the tension CSVs too; WT (starts with "W") shows in the
  compression dropdown and errors on selection because its headers are `Area_mm2` not `Area`. Not a regression.
- Backup of originals lives in `data/_legacy_sst_backup/` (subdir → not globbed).
