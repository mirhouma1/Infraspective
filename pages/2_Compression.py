# pages/2_Compression.py — CSA S16 Compression Check (Streamlit page)
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal, Tuple

import streamlit as st


# ----------------------------
# CSV LOADER (no Streamlit)
# ----------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
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
    return "".join(c for c in out if (c.isalnum() or c == "_") and ord(c) < 128)


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


def _load_csv(path: Path) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    out: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for rec in reader:
            rec2 = _canonicalize_record(rec)
            des = rec2.get("designation")
            if des:
                key = str(des).strip()
                out[key] = rec2
                order.append(key)
    return out, order


@st.cache_data(ttl=60)
def load_shapes() -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for p in [WI_SECTION_CSV, CLASS_BENDING_CSV]:
        if p.exists():
            data, csv_order = _load_csv(p)
            merged.update(data)
            order.extend(csv_order)

    if DATA_DIR.exists():
        for p in sorted(DATA_DIR.iterdir(), key=lambda x: x.name.lower()):
            if p.suffix.lower() == ".csv" and p not in (WI_SECTION_CSV, CLASS_BENDING_CSV):
                data, csv_order = _load_csv(p)
                merged.update(data)
                order.extend(csv_order)

    seen: set[str] = set()
    order_unique: List[str] = []
    for k in order:
        if k not in seen:
            seen.add(k)
            order_unique.append(k)

    return merged, order_unique


def get_shape(designation: str) -> Optional[Dict[str, Any]]:
    shapes, _ = load_shapes()
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
# STREAMLIT UI
# ----------------------------
st.title("CSA S16 Compression Check")
st.markdown("**Axially Loaded W-Section Column Check per CSA S16**")

shapes, designations = load_shapes()
if not shapes:
    st.error("No section data found. Add CSV files to the data/ folder.")
    st.stop()

st.markdown("---")

input_col1, input_col2, input_col3 = st.columns([2, 1, 1])

with input_col1:
    st.markdown("### Choose a W-section")
    search_query = st.text_input("Search sections", placeholder="e.g., W250", label_visibility="collapsed", key="comp_search")
    if search_query:
        qq = search_query.lower().strip()
        filtered = [k for k in designations if qq in k.lower()]
    else:
        filtered = designations

    if not filtered:
        st.warning("No sections match your search.")
        st.stop()

    selected_section = st.selectbox("Select section", options=filtered, index=0, label_visibility="collapsed", key="comp_select")

with input_col2:
    st.markdown("### Material")
    Fy = st.number_input("Fy (MPa)", min_value=200.0, max_value=700.0, value=345.0, step=5.0, key="comp_fy")
    E = st.number_input("E (MPa)", min_value=100000.0, max_value=300000.0, value=200000.0, step=1000.0, key="comp_E")
    G = st.number_input("G (MPa)", min_value=50000.0, max_value=100000.0, value=77000.0, step=1000.0, key="comp_G")

with input_col3:
    st.markdown("### Demand Check")
    check_demand = st.checkbox("Check against Pu", key="comp_demand")
    Pu = st.number_input("Pu (kN)", min_value=0.0, value=500.0, step=50.0, key="comp_pu") if check_demand else None

st.markdown("---")

if selected_section:
    shape = get_shape(selected_section)
    if shape is None:
        st.error(f"Section {selected_section} not found.")
        st.stop()

    len_col1, len_col2 = st.columns(2)

    with len_col1:
        st.markdown("### Effective Lengths")
        Kx = st.number_input("Kx (effective length factor, strong axis)", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="comp_kx")
        Lx_m = st.number_input("Lx (unbraced length, strong axis) (m)", min_value=0.1, value=3.0, step=0.5, key="comp_lx")

    with len_col2:
        st.markdown("### &nbsp;")
        Ky = st.number_input("Ky (effective length factor, weak axis)", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="comp_ky")
        Ly_m = st.number_input("Ly (unbraced length, weak axis) (m)", min_value=0.1, value=3.0, step=0.5, key="comp_ly")

    phi_c = 0.9
    n_curve = 1.34

    st.markdown("---")

    try:
        props = adapt_wshape_to_column_props(shape)

        db = ColumnDBProps(
            section_name=selected_section,
            section_family="W",
            A_mm2=props["A_mm2"],
            rx_mm=props["rx_mm"],
            ry_mm=props["ry_mm"],
            J_mm4=props["J_mm4"] if props["J_mm4"] > 0 else None,
            Cw_mm6=props["Cw_mm6"] if props["Cw_mm6"] > 0 else None,
        )

        u = ColumnUserInputs(
            Kx=Kx,
            Ky=Ky,
            Lx_mm=Lx_m * 1000.0,
            Ly_mm=Ly_m * 1000.0,
            Fy_MPa=float(Fy),
            E_MPa=float(E),
            G_MPa=float(G),
            phi_c=phi_c,
            n=n_curve,
            Pu_kN=float(Pu) if Pu is not None else None,
        )

        out = compression_csa_v1(db, u)
        buck = out["buckling"]

        res_col1, res_col2 = st.columns(2)

        with res_col1:
            st.subheader(f"Section: {selected_section}")
            st.markdown("**Section Properties**")
            st.markdown(f"- A = {props['A_mm2']:,.0f} mm²")
            st.markdown(f"- rx = {props['rx_mm']:.1f} mm, ry = {props['ry_mm']:.1f} mm")
            if props['J_mm4'] > 0:
                st.markdown(f"- J = {props['J_mm4']:,.0f} mm⁴")
            if props['Cw_mm6'] > 0:
                st.markdown(f"- Cw = {props['Cw_mm6']:,.0f} mm⁶")

        with res_col2:
            st.subheader("Compression Resistance")
            st.metric("Factored Compression Resistance (Cr)", f"{out['Cr_kN']:,.1f} kN")
            st.caption(f"φc = {phi_c}, n = {n_curve}")

        st.divider()

        st.subheader("Buckling Details")
        buck_col1, buck_col2, buck_col3 = st.columns(3)

        with buck_col1:
            st.markdown("**Slenderness Ratios**")
            st.markdown(f"- KL/r (x) = {buck['KLr_x']:.1f}")
            st.markdown(f"- KL/r (y) = {buck['KLr_y']:.1f}")
            st.markdown(f"- Governing KL/r = {buck['KLr_controlling']:.1f}")

        with buck_col2:
            st.markdown("**Euler Stresses**")
            st.markdown(f"- Fex = {buck['Fex_MPa']:,.1f} MPa")
            st.markdown(f"- Fey = {buck['Fey_MPa']:,.1f} MPa")
            if buck['Fez_MPa'] is not None:
                st.markdown(f"- Fez = {buck['Fez_MPa']:,.1f} MPa")
            st.markdown(f"- **Governing: {buck['governing_mode']}** ({buck['Fe_min_MPa']:,.1f} MPa)")

        with buck_col3:
            st.markdown("**CSA Column Curve**")
            st.markdown(f"- λ = {buck['lambda']:.3f}")
            st.markdown(f"- Fcr = {buck['Fcr_MPa']:,.1f} MPa")

        if check_demand and Pu is not None:
            st.divider()
            st.subheader("Demand / Capacity Check")
            util = out.get("utilization")
            if util:
                ratio = util["util_ratio"]
                if util["passes"]:
                    st.success(f"✅ **PASS** — Pu/Cr = {ratio:.2f} ≤ 1.0")
                else:
                    st.error(f"❌ **FAIL** — Pu/Cr = {ratio:.2f} > 1.0")
                st.metric("Utilization", f"{util['util_percent']:.1f}%")

        with st.expander("Raw Section Data"):
            st.json(shape)

    except Exception as e:
        st.error(f"Compression calculation error: {e}")