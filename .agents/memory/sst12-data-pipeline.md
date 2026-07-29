---
name: SST12.1 data pipeline
description: How the steel-section database is read directly from the SST12.1 workbook and the two column conventions consumers require
---
# Steel-section database (CISC SST12.1)

All pages read the SST12.1 xlsx in `attached_assets/` directly via the root module `sst12.py`
(lru_cache + per-page `st.cache_data`). The old `data/` CSVs and `scripts/convert_sst12.py`
were removed. SST12.1 already uses the app's 10^x property convention, so no re-scaling.

## Two consumer conventions (do NOT unify carelessly)
- **Shared pipeline** — `app.py` (flexure, W only), `pages/2_Compression.py`, `pages/4_Beam_Column_Members.py`
  consume `sst12.shared_records()` (W + HSS) and canonicalize via per-page alias tables. Records must
  use **simple bare property names** (`Ix`, `Sx`, `Zx`, `Area`, `d`, `b`, `t`, `w`, `k`, `ba/t`, `h/w`).
  **Why:** flexure's alias for Zx/Sx/Zy/Sy only lists the `zx_103_mm` form (trailing garbled ³ stripped);
  rich headers like `Zx (10^3 mm^3)` normalize to `zx_103_mm3` and silently return None in flexure,
  while compression/beam-column DO match the rich form. Bare names match all three — that's the safe union.
- **Tension pipeline** — `pages/1_Tension_Members.py` builds DataFrames from `sst12.load_all_tables()`
  keys `channels`/`wt`/`double_angles` (exact `Area_mm2`, `t_mm`, `w_mm`, `b_mm`, `d_mm`, `rx_mm`,
  `ry_mm`/`ry_s0_mm` names — NOT aliased) and `single_angles` (`b (mm)`, `Area (mm2)` style names).

## Gotchas
- SST sheet layout: row 0=header (short codes Ds_m, A_Th, Rx…), rows 1-2=multiplier/units, data from row 3.
- HSS designations: SST12.1 codes them `HS…`; rename to `HSS…` or `section_family()`/`parse_hss_designation()` break.
- WWF is not in SST12.1 (separate welded-wide-flange table) — no WWF data exists.
- Compression/beam-column now only see W+HSS (tension shapes no longer globbed at all); their A/rx/ry
  gate remains as a safety net.
- Direct-read parity vs the old generated CSVs was verified value-for-value at cutover (all 8 tables).
