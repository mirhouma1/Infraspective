"""
Convert CISC Structural Section Tables SST12.1 (metric) into the CSV/XLSX files
consumed by this app's data pipelines.

Two output conventions are produced from the single SST12.1 source:

1. SHARED pipeline (flexure / compression / beam-column) -- rich aliased headers
   (e.g. "Ix (10^6 mm^4)", "Area (mm2)", "Depth d (mm)"). Used for W and HSS.

2. TENSION pipeline (pages/1_Tension_Members.py) -- bespoke exact column names
   (Area_mm2, t_mm, w_mm, b_mm, d_mm, rx_mm, ry_mm) in fixed filenames. Used for
   channels, WT tees, single angles (xlsx) and double angles.

SST12.1 already stores properties in the 10^x multiplier convention the app
expects (Ix=10^6, Sx/Zx=10^3, J=10^3, Cw=10^9), so no re-scaling is applied.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SRC = next(ROOT.glob("attached_assets/CISC_StructuralSectionTables_SST12.1_*.xlsx"))

# Row layout in every sheet: 0=header, 1=multiplier, 2=base-unit, 3+=data
HEADER_ROW = 0
DATA_START = 3
CATEGORY_LABELS = {"Square", "Rectangular", "Round", "Metric Properties"}


def _has_digit(s: Any) -> bool:
    return any(ch.isdigit() for ch in str(s))


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def read_sheet(wb, name: str) -> List[Dict[str, Any]]:
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


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"  wrote {path.name:45s} {len(rows):4d} rows")


# ── Shared-pipeline header (W + HSS) ─────────────────────────────────────────
# Simple bare property names, recognised directly by all three shared consumers'
# alias tables (flexure app.py, compression, beam-column). Values keep SST12.1's
# 10^x multiplier convention (Ix=10^6, Sx/Zx=10^3, J=10^3, Cw=10^9).
SHARED_FIELDS = [
    "Designation", "Class", "ba/t", "h/w", "Area",
    "Ix", "Sx", "rx", "Zx", "Iy", "Sy", "ry", "Zy", "J", "Cw",
    "d", "b", "t", "w", "k",
]


def shared_row_wshape(rec: Dict[str, Any]) -> Dict[str, Any]:
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


def shared_row_hss(rec: Dict[str, Any], round_: bool = False) -> Dict[str, Any]:
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


def main() -> None:
    print(f"Source: {SRC.name}")
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)

    # 1) Back up the ORIGINAL data files once; on reruns just clear generated outputs
    backup = DATA / "_legacy_sst_backup"
    if backup.exists() and any(backup.iterdir()):
        for p in list(DATA.glob("*.csv")) + list(DATA.glob("*.xlsx")):
            p.unlink()
        print("Originals already backed up; cleared generated outputs.")
    else:
        backup.mkdir(exist_ok=True)
        for p in list(DATA.glob("*.csv")) + list(DATA.glob("*.xlsx")):
            p.rename(backup / p.name)
        print(f"Backed up old data files -> {backup.name}/")

    # 2) SHARED pipeline: W + HSS (square/rect/round)
    w_rows = [shared_row_wshape(r) for r in read_sheet(wb, "W")]
    write_csv(DATA / "w_sections.csv", SHARED_FIELDS, w_rows)

    sq = [shared_row_hss(r) for r in read_sheet(wb, "HS_Sq")]
    write_csv(DATA / "Property Table - HSS - Square.csv", SHARED_FIELDS, sq)

    re_ = [shared_row_hss(r) for r in read_sheet(wb, "HS_Re")]
    write_csv(DATA / "Properties Table - HSS - Rectangular.csv", SHARED_FIELDS, re_)

    ro = [shared_row_hss(r, round_=True) for r in read_sheet(wb, "HS_Ro")]
    write_csv(DATA / "Property Table - HSS - Circle.csv", SHARED_FIELDS, ro)

    # 3) TENSION pipeline: channels (C + MC), WT tees, double angles, single angles
    chan_fields = ["Designation", "Area_mm2", "t_mm", "w_mm", "d_mm", "b_mm", "rx_mm", "ry_mm"]
    chan_rows: List[Dict[str, Any]] = []
    for sheet in ("C", "MC"):
        for r in read_sheet(wb, sheet):
            chan_rows.append({
                "Designation": r["Ds_m"], "Area_mm2": _f(r.get("A_Th")),
                "t_mm": _f(r.get("T")), "w_mm": _f(r.get("W")),
                "d_mm": _f(r.get("D")), "b_mm": _f(r.get("B")),
                "rx_mm": _f(r.get("Rx")), "ry_mm": _f(r.get("Ry")),
            })
    write_csv(DATA / "Channel Sections Properties.csv", chan_fields, chan_rows)

    wt_fields = ["Designation", "Area_mm2", "t_mm", "w_mm", "b_mm", "d_mm", "rx_mm", "ry_mm"]
    wt_rows = [{
        "Designation": r["Ds_m"], "Area_mm2": _f(r.get("A_Th")),
        "t_mm": _f(r.get("T")), "w_mm": _f(r.get("W")),
        "b_mm": _f(r.get("B")), "d_mm": _f(r.get("D")),
        "rx_mm": _f(r.get("Rx")), "ry_mm": _f(r.get("Ry")),
    } for r in read_sheet(wb, "WT")]
    write_csv(DATA / "Structural Tees WT Properties.csv", wt_fields, wt_rows)

    da_fields = ["Designation", "Area_mm2", "rx_mm", "ry_s0_mm"]
    da_rows: List[Dict[str, Any]] = []
    for sheet in ("2LE", "2LL", "2LS"):
        for r in read_sheet(wb, sheet):
            des = str(r["Ds_m"])
            if not des.upper().startswith("2L"):
                des = "2" + des if des.upper().startswith("L") else "2L" + des
            da_rows.append({
                "Designation": des, "Area_mm2": _f(r.get("A_Th")),
                "rx_mm": _f(r.get("Rx")), "ry_s0_mm": _f(r.get("Ry0")),
            })
    write_csv(DATA / "Double Angle Properties.csv", da_fields, da_rows)

    # Single angles -> xlsx (tension page reads via openpyxl / pandas)
    ang_rows = read_sheet(wb, "L")
    out_wb = openpyxl.Workbook()
    ws = out_wb.active
    ws.title = "Angles"
    ws.append(["Designation", "b (mm)", "d (mm)", "t (mm)", "Area (mm2)",
               "rx (mm)", "ry (mm)", "rz (mm)"])
    for r in ang_rows:
        rz_cands = [v for v in (_f(r.get("Rxp")), _f(r.get("Ryp")),
                                _f(r.get("Rx")), _f(r.get("Ry"))) if v]
        ws.append([r["Ds_m"], _f(r.get("B")), _f(r.get("D")),
                   _f(r.get("T")), _f(r.get("A_Th")),
                   _f(r.get("Rx")), _f(r.get("Ry")),
                   min(rz_cands) if rz_cands else None])
    out_wb.save(DATA / "Angle Properties Table.xlsx")
    print(f"  wrote {'Angle Properties Table.xlsx':45s} {len(ang_rows):4d} rows")

    print("Done.")


if __name__ == "__main__":
    main()
