"""
Direct reader for the CISC Structural Section Tables SST12.1 workbook
(attached_assets/CISC_StructuralSectionTables_SST12.1_*.xlsx).

Replaces the old scripts/convert_sst12.py + data/*.csv pipeline: the record
dicts produced here are identical in shape to the rows the generated CSVs
used to contain, so every page consumes the same data as before.

Two conventions are produced from the single SST12.1 source:

1. SHARED pipeline (flexure / compression / beam-column) -- bare property
   names ("Designation", "Area", "Ix", "rx", ...) recognised by the alias
   tables in app.py, pages/2_Compression.py and pages/4_Beam_Column_Members.py.
   Used for W and HSS. Values keep SST12.1's 10^x multiplier convention
   (Ix=10^6, Sx/Zx=10^3, J=10^3, Cw=10^9) -- no re-scaling is applied.

2. TENSION pipeline (pages/1_Tension_Members.py) -- exact column names
   (Area_mm2, t_mm, w_mm, b_mm, d_mm, rx_mm, ry_mm / ry_s0_mm). Used for
   channels, WT tees, single angles and double angles.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl

ROOT = Path(__file__).resolve().parent

# Row layout in every sheet: 0=header, 1=multiplier, 2=base-unit, 3+=data
HEADER_ROW = 0
DATA_START = 3
CATEGORY_LABELS = {"Square", "Rectangular", "Round", "Metric Properties"}


def workbook_path() -> Optional[Path]:
    try:
        return next(ROOT.glob("attached_assets/CISC_StructuralSectionTables_SST12.1_*.xlsx"))
    except StopIteration:
        return None


def _has_digit(s: Any) -> bool:
    return any(ch.isdigit() for ch in str(s))


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _read_sheet(wb, name: str) -> List[Dict[str, Any]]:
    """Return list of row-dicts keyed by the SST short column code (Ds_m, D, Ix...)."""
    ws = wb[name]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c).strip() if c is not None else "" for c in rows[HEADER_ROW]]
    out: List[Dict[str, Any]] = []
    for r in rows[DATA_START:]:
        rec = {header[i]: r[i] for i in range(len(header)) if header[i]}
        des = rec.get("Ds_m")
        if des is None:
            continue
        des = str(des).strip()
        if not des or des in CATEGORY_LABELS or not _has_digit(des):
            continue
        rec["Ds_m"] = des
        out.append(rec)
    return out


# ── Shared-pipeline records (W + HSS) ────────────────────────────────────────

def _shared_row_wshape(rec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Designation": rec["Ds_m"],
        "Class": "",
        "ba/t": _f(rec.get("BT")),
        "h/w": _f(rec.get("HW")),
        "Area": _f(rec.get("A_Th")),
        "Ix": _f(rec.get("Ix")),
        "Sx": _f(rec.get("Sx")),
        "rx": _f(rec.get("Rx")),
        "Zx": _f(rec.get("Zx")),
        "Iy": _f(rec.get("Iy")),
        "Sy": _f(rec.get("Sy")),
        "ry": _f(rec.get("Ry")),
        "Zy": _f(rec.get("Zy")),
        "J": _f(rec.get("J")),
        "Cw": _f(rec.get("Cw")),
        "d": _f(rec.get("D")),
        "b": _f(rec.get("B")),
        "t": _f(rec.get("T")),
        "w": _f(rec.get("W")),
        "k": _f(rec.get("K")),
    }


def _shared_row_hss(rec: Dict[str, Any], round_: bool = False) -> Dict[str, Any]:
    des = rec["Ds_m"]
    if des.upper().startswith("HS") and not des.upper().startswith("HSS"):
        des = "HSS" + des[2:]
    tdes = _f(rec.get("Tdes")) or _f(rec.get("T"))
    return {
        "Designation": des,
        "Class": "",
        "ba/t": _f(rec.get("BT")),
        "h/w": _f(rec.get("DT")),
        "Area": _f(rec.get("A_Th")),
        "Ix": _f(rec.get("Ix")),
        "Sx": _f(rec.get("Sx")),
        "rx": _f(rec.get("Rx")),
        "Zx": _f(rec.get("Zx")),
        "Iy": _f(rec.get("Iy")),
        "Sy": _f(rec.get("Sy")),
        "ry": _f(rec.get("Ry")),
        "Zy": _f(rec.get("Zy")),
        "J": _f(rec.get("J")),
        "Cw": "",  # HSS have no warping constant tabulated
        "d": _f(rec.get("D")),
        "b": "" if round_ else _f(rec.get("B")),
        "t": tdes,
        "w": tdes,
        "k": "",
    }


# ── Tension-pipeline records ─────────────────────────────────────────────────

def _channel_rows(wb) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sheet in ("C", "MC"):
        for r in _read_sheet(wb, sheet):
            rows.append({
                "Designation": r["Ds_m"], "Area_mm2": _f(r.get("A_Th")),
                "t_mm": _f(r.get("T")), "w_mm": _f(r.get("W")),
                "d_mm": _f(r.get("D")), "b_mm": _f(r.get("B")),
                "rx_mm": _f(r.get("Rx")), "ry_mm": _f(r.get("Ry")),
            })
    return rows


def _wt_rows(wb) -> List[Dict[str, Any]]:
    return [{
        "Designation": r["Ds_m"], "Area_mm2": _f(r.get("A_Th")),
        "t_mm": _f(r.get("T")), "w_mm": _f(r.get("W")),
        "b_mm": _f(r.get("B")), "d_mm": _f(r.get("D")),
        "rx_mm": _f(r.get("Rx")), "ry_mm": _f(r.get("Ry")),
    } for r in _read_sheet(wb, "WT")]


def _double_angle_rows(wb) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sheet in ("2LE", "2LL", "2LS"):
        for r in _read_sheet(wb, sheet):
            des = str(r["Ds_m"])
            if not des.upper().startswith("2L"):
                des = "2" + des if des.upper().startswith("L") else "2L" + des
            rows.append({
                "Designation": des, "Area_mm2": _f(r.get("A_Th")),
                "rx_mm": _f(r.get("Rx")), "ry_s0_mm": _f(r.get("Ry0")),
            })
    return rows


def _single_angle_rows(wb) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for r in _read_sheet(wb, "L"):
        rz_cands = [v for v in (_f(r.get("Rxp")), _f(r.get("Ryp")),
                                _f(r.get("Rx")), _f(r.get("Ry"))) if v]
        rows.append({
            "Designation": r["Ds_m"], "b (mm)": _f(r.get("B")),
            "d (mm)": _f(r.get("D")), "t (mm)": _f(r.get("T")),
            "Area (mm2)": _f(r.get("A_Th")),
            "rx (mm)": _f(r.get("Rx")), "ry (mm)": _f(r.get("Ry")),
            "rz (mm)": min(rz_cands) if rz_cands else None,
        })
    return rows


# ── Public API ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_all_tables() -> Dict[str, List[Dict[str, Any]]]:
    """Read the SST12.1 workbook once and return every table this app uses.

    Keys: 'w', 'hss_square', 'hss_rect', 'hss_round' (shared convention),
          'channels', 'wt', 'double_angles', 'single_angles' (tension convention).
    Returns empty tables if the workbook is missing.
    """
    src = workbook_path()
    if src is None:
        return {k: [] for k in ("w", "hss_square", "hss_rect", "hss_round",
                                "channels", "wt", "double_angles", "single_angles")}
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    try:
        return {
            "w": [_shared_row_wshape(r) for r in _read_sheet(wb, "W")],
            "hss_square": [_shared_row_hss(r) for r in _read_sheet(wb, "HS_Sq")],
            "hss_rect": [_shared_row_hss(r) for r in _read_sheet(wb, "HS_Re")],
            "hss_round": [_shared_row_hss(r, round_=True) for r in _read_sheet(wb, "HS_Ro")],
            "channels": _channel_rows(wb),
            "wt": _wt_rows(wb),
            "double_angles": _double_angle_rows(wb),
            "single_angles": _single_angle_rows(wb),
        }
    finally:
        wb.close()


def shared_records() -> List[Dict[str, Any]]:
    """All W + HSS records in the shared bare-header convention, in the same
    order the old data/*.csv glob (sorted by lowercase filename) produced:
    Properties Table - HSS - Rectangular, Property Table - HSS - Circle,
    Property Table - HSS - Square, w_sections."""
    t = load_all_tables()
    return t["hss_rect"] + t["hss_round"] + t["hss_square"] + t["w"]


def tension_records() -> List[Dict[str, Any]]:
    """Channel + double-angle + WT records (tension _mm convention), in the
    old filename-sorted glob order: Channel Sections Properties, Double Angle
    Properties, Structural Tees WT Properties."""
    t = load_all_tables()
    return t["channels"] + t["double_angles"] + t["wt"]
