from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt, isfinite
from typing import Optional, Dict, Any, Literal


# ----------------------------
# COMPRESSION ADAPTER (W-table row -> base-unit props)
# Put this AFTER imports, BEFORE dataclasses/solvers
# ----------------------------

def _to_float(x: Any, field: str) -> float:
    """Robust float parse for CSV strings (handles commas/spaces)."""
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


def _pick(shape: Dict[str, Any], keys: list[str]) -> Optional[Any]:
    """Return first non-empty value from shape for any of the keys."""
    for k in keys:
        if k in shape and shape[k] not in (None, "", " "):
            return shape[k]
    return None


def adapt_wshape_to_column_props(shape: Dict[str, Any]) -> Dict[str, float]:
    """
    Converts your W-table row (shape dict) into BASE-UNIT properties.

    Base units used downstream:
      - A in mm^2
      - r in mm
      - Ix, Iy, J in mm^4
      - Cw in mm^6
      - Sx, Zx in mm^3

    This adapter is localized: no CSV edits, no flexure edits.
    """

    # --- Area (mm^2) : appears as "Area (mm²)" in your W CSV screenshot
    A_raw = _pick(shape, [
        "A", "Area", "area",
        "Area (mm²)", "Area (mm2)", "Area (mm^2)", "Area mm2",
        "Area mm²",
    ])
    A_mm2 = _to_float(A_raw, "Area")  # already mm^2

    # --- rx, ry (mm) : appears as "rx (mm)" / "ry (mm)"
    rx_raw = _pick(shape, ["rx", "rx (mm)", "rx_mm", "r_x", "r_x_mm"])
    ry_raw = _pick(shape, ["ry", "ry (mm)", "ry_mm", "r_y", "r_y_mm"])
    rx_mm = _to_float(rx_raw, "rx")
    ry_mm = _to_float(ry_raw, "ry")

    # --- Ix, Iy (10^6 mm^4 in your table) -> mm^4
    Ix_raw = _pick(shape, ["Ix", "Ix (10^6 mm?)", "Ix (10^6 mm4)", "Ix (10^6 mm^4)", "Ix_10e6"])
    Iy_raw = _pick(shape, ["Iy", "Iy (10^6 mm?)", "Iy (10^6 mm4)", "Iy (10^6 mm^4)", "Iy_10e6"])
    Ix_mm4 = _to_float(Ix_raw, "Ix") * 1e6 if Ix_raw is not None else 0.0
    Iy_mm4 = _to_float(Iy_raw, "Iy") * 1e6 if Iy_raw is not None else 0.0

    # --- Sx, Sy, Zx, Zy (10^3 mm^3) -> mm^3 (optional for compression, but useful)
    Sx_raw = _pick(shape, ["Sx", "Sx (10^3 mm?)", "Sx (10^3 mm3)", "Sx (10^3 mm^3)", "Sx_10e3"])
    Zx_raw = _pick(shape, ["Zx", "Zx (10^3 mm?)", "Zx (10^3 mm3)", "Zx (10^3 mm^3)", "Zx_10e3"])
    Sx_mm3 = _to_float(Sx_raw, "Sx") * 1e3 if Sx_raw is not None else 0.0
    Zx_mm3 = _to_float(Zx_raw, "Zx") * 1e3 if Zx_raw is not None else 0.0

    # --- J (10^3 mm^4) -> mm^4, Cw (10^9 mm^6) -> mm^6 (Stage 2 FT buckling)
    J_raw = _pick(shape, ["J", "J (10^3 mm?)", "J (10^3 mm4)", "J (10^3 mm^4)", "J_10e3"])
    Cw_raw = _pick(shape, ["Cw", "Cw (10^9 mm?)", "Cw (10^9 mm6)", "Cw (10^9 mm^6)", "Cw_10e9"])
    J_mm4 = _to_float(J_raw, "J") * 1e3 if J_raw is not None else 0.0
    Cw_mm6 = _to_float(Cw_raw, "Cw") * 1e9 if Cw_raw is not None else 0.0

    # Hard guardrails (avoid silent garbage)
    if A_mm2 <= 0 or rx_mm <= 0 or ry_mm <= 0:
        raise ValueError(f"Bad section props: A={A_mm2}, rx={rx_mm}, ry={ry_mm} (must be > 0)")

    return {
        "A_mm2": A_mm2,
        "rx_mm": rx_mm,
        "ry_mm": ry_mm,
        "Ix_mm4": Ix_mm4,
        "Iy_mm4": Iy_mm4,
        "Sx_mm3": Sx_mm3,
        "Zx_mm3": Zx_mm3,
        "J_mm4": J_mm4,
        "Cw_mm6": Cw_mm6,
    }


class InputError(ValueError):
    pass


Symmetry = Literal["doubly_symmetric_or_axisymmetric", "singly_symmetric"]


# --- 1) SECTION FAMILY NORMALIZATION (JSON labels -> solver labels) ---

def normalize_family(raw: str) -> str:
    """
    Normalize your JSON/DB family labels into the solver’s expected buckets.
    Adjust this as you finalize your DB naming conventions.

    Examples:
    - "W" -> "W"
    - "HSS", "RHS", "SHS", "CHS" -> "HSS"
    - "PIPE" -> "HSS" (optional choice; you said you may skip PIPE for now)
    """
    if raw is None:
        raise InputError("section_family is required")
    s = raw.strip().upper()

    # Common HSS aliases
    if s in {"RHS", "SHS", "CHS"}:
        return "HSS"

    # Optional: treat PIPE as HSS for symmetry purposes (axisymmetric)
    # If you truly want to exclude PIPE for now, delete this mapping.
    if s == "PIPE":
        return "HSS"

    return s


FAMILY_TO_SYMMETRY: dict[str, Symmetry] = {
    # Supported
    "W": "doubly_symmetric_or_axisymmetric",
    "WWF": "doubly_symmetric_or_axisymmetric",
    "HSS": "doubly_symmetric_or_axisymmetric",
    "BOX": "doubly_symmetric_or_axisymmetric",

    # Not yet supported (FT / TF buckling not implemented)
    "C": "singly_symmetric",
    "MC": "singly_symmetric",
    "WT": "singly_symmetric",
    "ST": "singly_symmetric",
    "MT": "singly_symmetric",
    "L": "singly_symmetric",
    "2L": "singly_symmetric",
}


# --- 2) INPUT CONTRACTS (DB vs User) ---

@dataclass(frozen=True)
class ColumnDBProps:
    """These come from your section database (JSON)."""
    section_name: str           # e.g., "W250x73"
    section_family: str         # e.g., "W", "HSS", "RHS" etc. (will be normalized)
    A_mm2: float
    rx_mm: float
    ry_mm: float
    J_mm4: Optional[float] = None
    Cw_mm6: Optional[float] = None


@dataclass(frozen=True)
class ColumnUserInputs:
    """These come from the UI (project-specific)."""
    Kx: float = 1.0
    Ky: float = 1.0
    Lx_mm: float = 3000.0
    Ly_mm: float = 3000.0

    Fy_MPa: float = 350.0       # meter in steps (e.g., 5 MPa)
    E_MPa: float = 200000.0
    G_MPa: float = 77000.0

    phi_c: float = 0.9
    n: float = 1.34             # keep as parameter until you lock per-CSA edition

    # Optional: checkbox + meter/textbox
    Pu_kN: Optional[float] = None

    # Optional torsional-buckling length factorization (rarely needed in V1 UI)
    Kz: float = 1.0
    Lz_mm: Optional[float] = None


# --- 3) VALIDATION HELPERS ---

def _req_pos(name: str, x: float) -> None:
    if not (isfinite(x) and x > 0.0):
        raise InputError(f"{name} must be a finite positive number; got {x!r}")


def _sanity_db(db: ColumnDBProps) -> None:
    _req_pos("A_mm2", db.A_mm2)
    _req_pos("rx_mm", db.rx_mm)
    _req_pos("ry_mm", db.ry_mm)

    # heuristics to catch unit mistakes early
    if db.A_mm2 < 100:
        raise InputError(f"A_mm2 too small (A={db.A_mm2}). Did you pass m^2?")
    if db.rx_mm < 5 or db.ry_mm < 5:
        raise InputError(f"rx/ry too small (rx={db.rx_mm}, ry={db.ry_mm}). Did you pass meters?")

    if db.J_mm4 is not None:
        _req_pos("J_mm4", db.J_mm4)
    if db.Cw_mm6 is not None:
        _req_pos("Cw_mm6", db.Cw_mm6)


def _sanity_user(u: ColumnUserInputs) -> None:
    _req_pos("Kx", u.Kx)
    _req_pos("Ky", u.Ky)
    _req_pos("Lx_mm", u.Lx_mm)
    _req_pos("Ly_mm", u.Ly_mm)

    _req_pos("Fy_MPa", u.Fy_MPa)
    _req_pos("E_MPa", u.E_MPa)
    _req_pos("G_MPa", u.G_MPa)

    _req_pos("phi_c", u.phi_c)
    _req_pos("n", u.n)

    # catch Pa vs MPa
    if u.E_MPa > 1e7:
        raise InputError(f"E_MPa too large (E={u.E_MPa}). Did you pass Pa?")

    if u.Pu_kN is not None:
        # allow Pu = 0 if user is just checking capacity? up to you
        if not isfinite(u.Pu_kN) or u.Pu_kN < 0:
            raise InputError(f"Pu_kN must be a finite non-negative number; got {u.Pu_kN!r}")


# --- 4) CORE ENGINEERING FUNCTIONS ---

def euler_F_e(E_MPa: float, KL_over_r: float) -> float:
    """Euler elastic buckling stress (MPa)."""
    _req_pos("E_MPa", E_MPa)
    _req_pos("KL_over_r", KL_over_r)
    return (pi ** 2) * E_MPa / (KL_over_r ** 2)


def csa_lambda(KL_over_r: float, Fy_MPa: float, E_MPa: float) -> float:
    """CSA nondimensional slenderness λ."""
    _req_pos("KL_over_r", KL_over_r)
    _req_pos("Fy_MPa", Fy_MPa)
    _req_pos("E_MPa", E_MPa)
    return KL_over_r * sqrt(Fy_MPa / ((pi ** 2) * E_MPa))


def csa_Fcr(Fy_MPa: float, E_MPa: float, KL_over_r: float, n: float) -> float:
    """
    CSA column curve stress (MPa):
      Fcr = Fy / (1 + λ^(2n))^(1/n)
    """
    lam = csa_lambda(KL_over_r, Fy_MPa, E_MPa)
    _req_pos("n", n)
    return Fy_MPa / ((1.0 + (lam ** (2.0 * n))) ** (1.0 / n))


def compute_Fe_candidates(db: ColumnDBProps, u: ColumnUserInputs) -> Dict[str, Any]:
    """
    Computes Fex, Fey, and Fez (if J & Cw available), and returns governing mode explicitly.
    """
    KLr_x = (u.Kx * u.Lx_mm) / db.rx_mm
    KLr_y = (u.Ky * u.Ly_mm) / db.ry_mm

    Fex = euler_F_e(u.E_MPa, KLr_x)
    Fey = euler_F_e(u.E_MPa, KLr_y)

    candidates: Dict[str, float] = {"Fex": Fex, "Fey": Fey}

    # Fez if torsional props available (doubly-symmetric / axisymmetric only)
    Fez = None
    if db.J_mm4 is not None and db.Cw_mm6 is not None:
        Lz = u.Lz_mm if u.Lz_mm is not None else max(u.Lx_mm, u.Ly_mm)
        _req_pos("Kz", u.Kz)
        _req_pos("Lz_mm", Lz)

        r0_sq = (db.rx_mm ** 2) + (db.ry_mm ** 2)
        _req_pos("r0_sq", r0_sq)

        term_warp = (pi ** 2) * u.E_MPa * db.Cw_mm6 / ((u.Kz * Lz) ** 2)
        term_stv = u.G_MPa * db.J_mm4
        Fez = (term_warp + term_stv) / (db.A_mm2 * r0_sq)
        candidates["Fez"] = Fez

    # Explicit governing selection (no float equality checks)
    governing_mode = min(candidates, key=candidates.get)
    Fe_min = candidates[governing_mode]

    # Map governing mode -> controlling KL/r for curve input
    if governing_mode == "Fex":
        KLr_ctrl = KLr_x
    elif governing_mode == "Fey":
        KLr_ctrl = KLr_y
    else:
        # Back-calc an equivalent KL/r so λ can be computed consistently from Euler equivalence
        KLr_ctrl = pi * sqrt(u.E_MPa / Fe_min)

    return {
        "KLr_x": KLr_x,
        "KLr_y": KLr_y,
        "Fex_MPa": Fex,
        "Fey_MPa": Fey,
        "Fez_MPa": Fez,
        "governing_mode": governing_mode,   # "Fex" | "Fey" | "Fez"
        "Fe_min_MPa": Fe_min,
        "KLr_controlling": KLr_ctrl,
    }


# --- 5) MAIN ENTRY POINT ---

def compression_csa_v1(db: ColumnDBProps, u: ColumnUserInputs) -> Dict[str, Any]:
    """
    Returns:
    - capacity Cr (N and kN)
    - optional utilization if Pu_kN is provided
    - full transparency: Fex/Fey/Fez + governing mode
    """
    _sanity_db(db)
    _sanity_user(u)

    fam = normalize_family(db.section_family)
    symmetry = FAMILY_TO_SYMMETRY.get(fam)

    if symmetry is None:
        raise InputError(
            f"Unknown section_family={db.section_family!r} (normalized={fam!r}). "
            f"Known: {sorted(FAMILY_TO_SYMMETRY)}"
        )

    if symmetry != "doubly_symmetric_or_axisymmetric":
        raise InputError(
            f"section_family={db.section_family!r} (normalized={fam!r}) is singly-symmetric. "
            "FT / torsional-flexural buckling not implemented yet for C/WT/L/etc."
        )

    FE = compute_Fe_candidates(db, u)

    KLr = FE["KLr_controlling"]
    lam = csa_lambda(KLr, u.Fy_MPa, u.E_MPa)
    Fcr = csa_Fcr(u.Fy_MPa, u.E_MPa, KLr, u.n)

    # Capacity
    Cr_N = u.phi_c * db.A_mm2 * Fcr          # (mm^2)*(N/mm^2)=N
    Cr_kN = Cr_N / 1000.0

    # Optional utilization
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
        # ID / labeling
        "section_name": db.section_name,
        "section_family_raw": db.section_family,
        "section_family_normalized": fam,
        "symmetry": symmetry,

        # Inputs summary
        "Fy_MPa": u.Fy_MPa,
        "E_MPa": u.E_MPa,
        "G_MPa": u.G_MPa,
        "phi_c": u.phi_c,
        "n": u.n,
        "Kx": u.Kx,
        "Ky": u.Ky,
        "Lx_mm": u.Lx_mm,
        "Ly_mm": u.Ly_mm,

        # DB summary
        "A_mm2": db.A_mm2,
        "rx_mm": db.rx_mm,
        "ry_mm": db.ry_mm,
        "J_mm4": db.J_mm4,
        "Cw_mm6": db.Cw_mm6,

        # Transparency block
        "buckling": {
            **FE,
            "lambda": lam,
            "Fcr_MPa": Fcr,
        },

        # Results
        "Cr_N": Cr_N,
        "Cr_kN": Cr_kN,
        "utilization": util,
    }


# --- 6) JSON -> DB PROPS BUILDER (placeholder) ---

def dbprops_from_record(rec: Dict[str, Any]) -> ColumnDBProps:
    """
    Build DB props from one JSON record.
    Adjust key names to match your dataset once you finalize it.

    Expected (examples):
      rec["name"] or rec["Section"] -> section_name
      rec["family"] or rec["Type"] -> section_family
      rec["A"] -> mm^2
      rec["rx"], rec["ry"] -> mm
      rec["J"], rec["Cw"] -> mm^4, mm^6 (optional)
    """
    # Try multiple key variants (robust early on)
    def pick(*keys: str) -> Any:
        for k in keys:
            if k in rec and rec[k] is not None:
                return rec[k]
        return None

    section_name = pick("name", "Section", "section", "Designation")
    section_family = pick("family", "Family", "Type", "type")
    A = pick("A", "Ag", "Area", "A_mm2")
    rx = pick("rx", "rx_mm", "Rx")
    ry = pick("ry", "ry_mm", "Ry")
    J = pick("J", "J_mm4")
    Cw = pick("Cw", "Cw_mm6", "Iw")  # careful: some DBs name warping constant differently

    if section_name is None or section_family is None:
        raise InputError("JSON record missing section name or family")

    return ColumnDBProps(
        section_name=str(section_name),
        section_family=str(section_family),
        A_mm2=float(A),
        rx_mm=float(rx),
        ry_mm=float(ry),
        J_mm4=float(J) if J is not None else None,
        Cw_mm6=float(Cw) if Cw is not None else None,
    )


# --- 7) SMOKE TEST ---

if __name__ == "__main__":
    rec = {
        "name": "W250x73",
        "family": "W",
        "A": 9280.0,
        "rx": 110.0,
        "ry": 65.0,
        "J": 575000.0,
        "Cw": 553e9,
    }

    db = dbprops_from_record(rec)

    u = ColumnUserInputs(
        Kx=1.0, Ky=1.0,
        Lx_mm=1100.0, Ly_mm=1100.0,
        Fy_MPa=350.0,
        E_MPa=205000.0,
        G_MPa=76920.0,
        phi_c=0.9,
        n=1.34,
        Pu_kN=800.0,   # optional
    )

    out = compression_csa_v1(db, u)
    print(out["section_name"], "Cr_kN=", round(out["Cr_kN"], 1), "Gov=", out["buckling"]["governing_mode"])
    if out["utilization"]:
        print("Util% =", round(out["utilization"]["util_percent"], 1), "Pass=", out["utilization"]["passes"])


