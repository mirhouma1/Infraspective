# compression_cli.py
from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal


# ----------------------------
# CSV LOADER (no Streamlit)
# ----------------------------
DATA_DIR = Path(__file__).resolve().parent / "data"
WI_SECTION_CSV = DATA_DIR / "CISC 11th Edition (CSA S16-14) - WiSection Tables (Revised).csv"
CLASS_BENDING_CSV = DATA_DIR / "CISC 11th Edition - Class of Sections in Bending.csv"


def _norm(s: str) -> str:
    out = (
        str(s).strip().lower()
        .replace("(", "").replace(")", "")
        .replace("[", "").replace("]", "")
        .replace("/", "_").replace("-", "_")
        .replace(" ", "_")
        .replace("^", "")
    )
    return "".join(c for c in out if c.isalnum() or c == "_")


CANON_SYNONYMS: Dict[str, List[str]] = {
    "designation": ["designation", "Designation", "shape", "section", "name", "w_shape"],
    # Geometry
    "d": ["d", "D", "depth", "overall_depth", "depth_d", "depth_d_mm"],
    "b": ["b", "B", "bf", "flange_width", "flange_width_b", "flange_width_b_mm"],
    "t": ["t", "T", "tf", "flange_thickness", "flange_thickness_t", "flange_thickness_t_mm"],
    "w": ["w", "W", "tw", "web_thickness", "web_thickness_w", "web_thickness_w_mm"],
    # Compression-needed props
    "Area": ["Area", "area", "A", "A_mm2", "Area (mm²)", "Area (mm2)", "Area mm²", "Area mm2"],
    "rx": ["rx", "rx_mm", "rx (mm)", "r_x", "r_x_mm"],
    "ry": ["ry", "ry_mm", "ry (mm)", "r_y", "r_y_mm"],
    "Ix": ["Ix", "ix", "i_x", "Ix_10e6", "ix_106_mm4", "ix_106_mm"],
    "Iy": ["Iy", "iy", "i_y", "Iy_10e6", "iy_106_mm4", "iy_106_mm"],
    "J":  ["J", "j", "J_10e3", "j_103_mm4", "j_103_mm"],
    "Cw": ["Cw", "cw", "Cw_10e9", "cw_109_mm6", "cw_109_mm"],
}


def _pick(rec: Dict[str, Any], candidates: List[str]) -> Optional[Any]:
    norm_map = {_norm(k): v for k, v in rec.items()}
    for cand in candidates:
        ck = _norm(cand)
        if ck in norm_map and norm_map[ck] not in (None, ""):
            return norm_map[ck]
    return None


def _canonicalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)

    des = _pick(rec, CANON_SYNONYMS["designation"])
    if des is not None:
        out["designation"] = des

    for sym in ("d", "b", "t", "w", "Area", "rx", "ry", "Ix", "Iy", "J", "Cw"):
        v = _pick(rec, CANON_SYNONYMS[sym])
        if v is not None:
            out[sym] = v

    return out


def _load_csv(path: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for rec in reader:
            rec2 = _canonicalize_record(rec)
            des = rec2.get("designation")
            if des:
                key = str(des).strip()
                out[key] = rec2
    return out


def load_shapes() -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for p in [WI_SECTION_CSV, CLASS_BENDING_CSV]:
        if p.exists():
            merged.update(_load_csv(p))

    if DATA_DIR.exists():
        for p in sorted(DATA_DIR.iterdir(), key=lambda x: x.name.lower()):
            if p.suffix.lower() == ".csv" and p not in (WI_SECTION_CSV, CLASS_BENDING_CSV):
                merged.update(_load_csv(p))

    return merged


def get_shape(designation: str) -> Optional[Dict[str, Any]]:
    shapes = load_shapes()
    return shapes.get(designation)


# ----------------------------
# COMPRESSION SOLVER (pure python)
# ----------------------------
def _to_float(x: Any, field: str) -> float:
    if x is None:
        raise ValueError(f"Missing required field: {field}")
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    if s == "":
        raise ValueError(f"Missing required field: {field}")
    try:
        return float(s)
    except Exception as e:
        raise ValueError(f"Field '{field}' not numeric: {x!r}") from e


def _pick_shape(shape: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in shape and shape[k] not in (None, "", " "):
            return shape[k]
    return None


def adapt_wshape_to_column_props(shape: Dict[str, Any]) -> Dict[str, float]:
    # Area in mm^2
    A_raw = _pick_shape(shape, ["Area", "area", "A", "Area (mm²)", "Area (mm2)", "Area mm²", "Area mm2"])
    A_mm2 = _to_float(A_raw, "Area")

    # rx, ry in mm
    rx_raw = _pick_shape(shape, ["rx", "rx (mm)", "rx_mm"])
    ry_raw = _pick_shape(shape, ["ry", "ry (mm)", "ry_mm"])
    rx_mm = _to_float(rx_raw, "rx")
    ry_mm = _to_float(ry_raw, "ry")

    # Ix, Iy often in 10^6 mm^4 in tables -> mm^4 (if present)
    Ix_raw = _pick_shape(shape, ["Ix", "Ix_10e6"])
    Iy_raw = _pick_shape(shape, ["Iy", "Iy_10e6"])
    Ix_mm4 = _to_float(Ix_raw, "Ix") * 1e6 if Ix_raw is not None else 0.0
    Iy_mm4 = _to_float(Iy_raw, "Iy") * 1e6 if Iy_raw is not None else 0.0

    # J in 10^3 mm^4 -> mm^4 (if present)
    J_raw = _pick_shape(shape, ["J", "J_10e3"])
    J_mm4 = _to_float(J_raw, "J") * 1e3 if J_raw is not None else 0.0

    # Cw in 10^9 mm^6 -> mm^6 (if present)
    Cw_raw = _pick_shape(shape, ["Cw", "Cw_10e9"])
    Cw_mm6 = _to_float(Cw_raw, "Cw") * 1e9 if Cw_raw is not None else 0.0

    if A_mm2 <= 0 or rx_mm <= 0 or ry_mm <= 0:
        raise ValueError(f"Bad section props: A={A_mm2}, rx={rx_mm}, ry={ry_mm} (must be > 0)")

    return {
        "A_mm2": A_mm2,
        "rx_mm": rx_mm,
        "ry_mm": ry_mm,
        "Ix_mm4": Ix_mm4,
        "Iy_mm4": Iy_mm4,
        "J_mm4": J_mm4 if J_mm4 > 0 else 0.0,
        "Cw_mm6": Cw_mm6 if Cw_mm6 > 0 else 0.0,
    }


class InputError(ValueError):
    pass


Symmetry = Literal["doubly_symmetric_or_axisymmetric", "singly_symmetric"]


def normalize_family(raw: str) -> str:
    if raw is None:
        raise InputError("section_family is required")
    s = raw.strip().upper()
    if s in {"RHS", "SHS", "CHS", "PIPE"}:
        return "HSS"
    return s


FAMILY_TO_SYMMETRY: Dict[str, Symmetry] = {
    "W": "doubly_symmetric_or_axisymmetric",
    "WWF": "doubly_symmetric_or_axisymmetric",
    "HSS": "doubly_symmetric_or_axisymmetric",
    "BOX": "doubly_symmetric_or_axisymmetric",
    "C": "singly_symmetric",
    "MC": "singly_symmetric",
    "WT": "singly_symmetric",
    "ST": "singly_symmetric",
    "MT": "singly_symmetric",
    "L": "singly_symmetric",
    "2L": "singly_symmetric",
}


@dataclass(frozen=True)
class ColumnDBProps:
    section_name: str
    section_family: str
    A_mm2: float
    rx_mm: float
    ry_mm: float
    J_mm4: Optional[float] = None
    Cw_mm6: Optional[float] = None


@dataclass(frozen=True)
class ColumnUserInputs:
    Kx: float = 1.0
    Ky: float = 1.0
    Lx_mm: float = 3000.0
    Ly_mm: float = 3000.0

    Fy_MPa: float = 350.0
    E_MPa: float = 200000.0
    G_MPa: float = 77000.0

    phi_c: float = 0.9
    n: float = 1.34

    Pu_kN: Optional[float] = None

    Kz: float = 1.0
    Lz_mm: Optional[float] = None


def _req_pos(name: str, x: float) -> None:
    if not (isinstance(x, (int, float)) and math.isfinite(x) and x > 0.0):
        raise InputError(f"{name} must be a finite positive number; got {x!r}")


def _sanity_db(db: ColumnDBProps) -> None:
    _req_pos("A_mm2", db.A_mm2)
    _req_pos("rx_mm", db.rx_mm)
    _req_pos("ry_mm", db.ry_mm)
    if db.A_mm2 < 100:
        raise InputError(f"A_mm2 too small (A={db.A_mm2}). Units wrong?")
    if db.rx_mm < 5 or db.ry_mm < 5:
        raise InputError(f"rx/ry too small (rx={db.rx_mm}, ry={db.ry_mm}). Units wrong?")
    if db.J_mm4 is not None and db.J_mm4 > 0:
        _req_pos("J_mm4", db.J_mm4)
    if db.Cw_mm6 is not None and db.Cw_mm6 > 0:
        _req_pos("Cw_mm6", db.Cw_mm6)


def _sanity_user(u: ColumnUserInputs) -> None:
    for k in ("Kx", "Ky", "Lx_mm", "Ly_mm", "Fy_MPa", "E_MPa", "G_MPa", "phi_c", "n"):
        _req_pos(k, float(getattr(u, k)))
    if u.E_MPa > 1e7:
        raise InputError(f"E_MPa too large (E={u.E_MPa}). Did you pass Pa?")
    if u.Pu_kN is not None:
        if not (math.isfinite(u.Pu_kN) and u.Pu_kN >= 0):
            raise InputError(f"Pu_kN must be finite and ≥ 0; got {u.Pu_kN!r}")


def euler_F_e(E_MPa: float, KL_over_r: float) -> float:
    _req_pos("E_MPa", E_MPa)
    _req_pos("KL_over_r", KL_over_r)
    return (math.pi ** 2) * E_MPa / (KL_over_r ** 2)


def csa_lambda(KL_over_r: float, Fy_MPa: float, E_MPa: float) -> float:
    _req_pos("KL_over_r", KL_over_r)
    _req_pos("Fy_MPa", Fy_MPa)
    _req_pos("E_MPa", E_MPa)
    return KL_over_r * math.sqrt(Fy_MPa / ((math.pi ** 2) * E_MPa))


def csa_Fcr(Fy_MPa: float, E_MPa: float, KL_over_r: float, n: float) -> float:
    lam = csa_lambda(KL_over_r, Fy_MPa, E_MPa)
    _req_pos("n", n)
    return Fy_MPa / ((1.0 + (lam ** (2.0 * n))) ** (1.0 / n))


def compute_Fe_candidates(db: ColumnDBProps, u: ColumnUserInputs) -> Dict[str, Any]:
    KLr_x = (u.Kx * u.Lx_mm) / db.rx_mm
    KLr_y = (u.Ky * u.Ly_mm) / db.ry_mm
    Fex = euler_F_e(u.E_MPa, KLr_x)
    Fey = euler_F_e(u.E_MPa, KLr_y)

    candidates: Dict[str, float] = {"Fex": Fex, "Fey": Fey}

    Fez = None
    if db.J_mm4 and db.Cw_mm6 and db.J_mm4 > 0 and db.Cw_mm6 > 0:
        Lz = u.Lz_mm if u.Lz_mm is not None else max(u.Lx_mm, u.Ly_mm)
        _req_pos("Kz", u.Kz)
        _req_pos("Lz_mm", Lz)
        r0_sq = (db.rx_mm ** 2) + (db.ry_mm ** 2)
        _req_pos("r0_sq", r0_sq)

        term_warp = (math.pi ** 2) * u.E_MPa * db.Cw_mm6 / ((u.Kz * Lz) ** 2)
        term_stv = u.G_MPa * db.J_mm4
        Fez = (term_warp + term_stv) / (db.A_mm2 * r0_sq)
        candidates["Fez"] = Fez

    governing_mode = min(candidates, key=candidates.get)
    Fe_min = candidates[governing_mode]

    if governing_mode == "Fex":
        KLr_ctrl = KLr_x
    elif governing_mode == "Fey":
        KLr_ctrl = KLr_y
    else:
        KLr_ctrl = math.pi * math.sqrt(u.E_MPa / Fe_min)

    return {
        "KLr_x": KLr_x,
        "KLr_y": KLr_y,
        "Fex_MPa": Fex,
        "Fey_MPa": Fey,
        "Fez_MPa": Fez,
        "governing_mode": governing_mode,
        "Fe_min_MPa": Fe_min,
        "KLr_controlling": KLr_ctrl,
    }


def compression_csa_v1(db: ColumnDBProps, u: ColumnUserInputs) -> Dict[str, Any]:
    _sanity_db(db)
    _sanity_user(u)

    fam = normalize_family(db.section_family)
    symmetry = FAMILY_TO_SYMMETRY.get(fam)
    if symmetry is None:
        raise InputError(f"Unknown section_family={db.section_family!r} (normalized={fam!r}).")

    if symmetry != "doubly_symmetric_or_axisymmetric":
        raise InputError("Singly-symmetric families not supported in this v1 CLI.")

    FE = compute_Fe_candidates(db, u)
    KLr = FE["KLr_controlling"]
    lam = csa_lambda(KLr, u.Fy_MPa, u.E_MPa)
    Fcr = csa_Fcr(u.Fy_MPa, u.E_MPa, KLr, u.n)

    Cr_N = u.phi_c * db.A_mm2 * Fcr
    Cr_kN = Cr_N / 1000.0

    util = None
    if u.Pu_kN is not None:
        Pu_N = u.Pu_kN * 1000.0
        util_ratio = Pu_N / Cr_N if Cr_N > 0 else None
        util = {
            "Pu_kN": u.Pu_kN,
            "util_ratio": util_ratio,
            "util_percent": (util_ratio * 100.0) if util_ratio is not None else None,
            "passes": (util_ratio <= 1.0) if util_ratio is not None else None,
        }

    return {
        "section_name": db.section_name,
        "section_family_normalized": fam,
        "buckling": {**FE, "lambda": lam, "Fcr_MPa": Fcr},
        "Cr_kN": Cr_kN,
        "utilization": util,
    }


# ----------------------------
# CLI
# ----------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="CSA S16 Compression (CLI) — W-shapes only (v1)")
    ap.add_argument("--section", default="W250x73", help="e.g., W250x73")
    ap.add_argument("--Fy", type=float, default=350.0, help="MPa")
    ap.add_argument("--E", type=float, default=200000.0, help="MPa")
    ap.add_argument("--G", type=float, default=77000.0, help="MPa")
    ap.add_argument("--Kx", type=float, default=1.0)
    ap.add_argument("--Ky", type=float, default=1.0)
    ap.add_argument("--Lx", type=float, default=3000.0, help="mm")
    ap.add_argument("--Ly", type=float, default=3000.0, help="mm")
    ap.add_argument("--phi_c", type=float, default=0.9)
    ap.add_argument("--n", type=float, default=1.34)
    ap.add_argument("--Pu", type=float, default=None, help="kN (optional demand)")
    args = ap.parse_args()

    shape = get_shape(args.section)
    if shape is None:
        print(f"ERROR: Section not found: {args.section}")
        return 2

    props = adapt_wshape_to_column_props(shape)

    db = ColumnDBProps(
        section_name=args.section,
        section_family="W",
        A_mm2=props["A_mm2"],
        rx_mm=props["rx_mm"],
        ry_mm=props["ry_mm"],
        J_mm4=props["J_mm4"] if props["J_mm4"] > 0 else None,
        Cw_mm6=props["Cw_mm6"] if props["Cw_mm6"] > 0 else None,
    )

    u = ColumnUserInputs(
        Kx=args.Kx,
        Ky=args.Ky,
        Lx_mm=args.Lx,
        Ly_mm=args.Ly,
        Fy_MPa=args.Fy,
        E_MPa=args.E,
        G_MPa=args.G,
        phi_c=args.phi_c,
        n=args.n,
        Pu_kN=args.Pu,
    )

    out = compression_csa_v1(db, u)

    print(f"Section: {out['section_name']}")
    print(f"Cr = {out['Cr_kN']:.1f} kN")
    b = out["buckling"]
    print(f"Governing: {b['governing_mode']}  Fe_min={b['Fe_min_MPa']:.1f} MPa  Fcr={b['Fcr_MPa']:.1f} MPa  λ={b['lambda']:.3f}")

    if out["utilization"]:
        uo = out["utilization"]
        print(f"Pu = {uo['Pu_kN']:.1f} kN  Util = {uo['util_percent']:.1f}%  Pass = {uo['passes']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())