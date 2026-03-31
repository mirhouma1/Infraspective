# app.py  (Beam-Column Members — CSV-driven Streamlit app)
from __future__ import annotations
import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# ============================================================
# CONFIG
# ============================================================
APP_TITLE = "CSA S16 Beam-Column (Chapter 5) — CSV-driven"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PHI_B = 0.9
E_MPA_DEFAULT = 200000.0  # MPa


# ============================================================
# CSV NORMALIZATION
# ============================================================
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
    "designation": ["designation", "shape", "section", "name", "member"],

    # geometry (mm)
    "d": ["d", "depth", "overall_depth", "depth_mm"],
    "b": ["b", "bf", "flange_width", "bf_mm"],
    "t": ["t", "tf", "flange_thickness", "tf_mm"],
    "w": ["w", "tw", "web_thickness", "tw_mm"],
    "h": ["h", "web_depth", "clear_web_depth", "h_mm"],

    # area and radii
    "Area": ["area", "a", "a_mm2", "area_mm2"],
    "rx": ["rx", "r_x", "rx_mm"],
    "ry": ["ry", "r_y", "ry_mm"],

    # second moments
    "Ix": ["ix", "i_x", "ix_106_mm4", "ix_10e6_mm4", "ix_10^6_mm4", "ix_mm4"],
    "Iy": ["iy", "i_y", "iy_106_mm4", "iy_10e6_mm4", "iy_10^6_mm4", "iy_mm4"],

    # section modulus
    "Zx": ["zx", "z_x", "zx_103_mm3", "zx_10e3_mm3", "zx_mm3"],
    "Sx": ["sx", "s_x", "sx_103_mm3", "sx_10e3_mm3", "sx_mm3"],
    "Zy": ["zy", "z_y", "zy_103_mm3", "zy_10e3_mm3", "zy_mm3"],
    "Sy": ["sy", "s_y", "sy_103_mm3", "sy_10e3_mm3", "sy_mm3"],

    # optional class field if your CSV contains it
    "section_class": ["section_class", "class", "sectionclass", "cls"],
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
        out["designation"] = str(des).strip()

    for sym in (
        "d", "b", "t", "w", "h",
        "Area", "rx", "ry", "Ix", "Iy", "Zx", "Sx", "Zy", "Sy",
        "section_class",
    ):
        v = _pick(rec, CANON_SYNONYMS[sym])
        if v is not None:
            out[sym] = v

    return out


def _load_csv_dictreader(path: Path) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    out: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    try:
        fh = path.open("r", encoding="utf-8", newline="")
        fh.read(512)
        fh.seek(0)
    except UnicodeDecodeError:
        fh = path.open("r", encoding="latin-1", newline="")

    with fh as f:
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
def load_shapes_from_data_dir() -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    if DATA_DIR.exists():
        for p in sorted(DATA_DIR.iterdir(), key=lambda x: x.name.lower()):
            if p.suffix.lower() == ".csv":
                data, csv_order = _load_csv_dictreader(p)
                merged.update(data)
                order.extend(csv_order)

    seen: set[str] = set()
    uniq: List[str] = []
    for k in order:
        if k not in seen:
            seen.add(k)
            uniq.append(k)

    return merged, uniq


# ============================================================
# Numeric helpers
# ============================================================
EPS = 1e-12
MULT_ZS = 1000.0  # assumes Z/S in 10^3 mm^3 if small-table format


def safe_div(a: float, b: float) -> float:
    if abs(b) < EPS:
        raise ValueError("Division by ~0 encountered.")
    return a / b


def opt_float(x: Any) -> Optional[float]:
    if x in (None, ""):
        return None
    try:
        return float(x)
    except Exception:
        return None


def fmt_num(x: Optional[float], digits: int = 4) -> str:
    if x is None or not math.isfinite(x):
        return "—"
    return f"{x:.{digits}f}"


def fmt_sci(x: Optional[float]) -> str:
    if x is None or not math.isfinite(x):
        return "—"
    return f"{x:.3e}"


def to_mm4_from_csv(val: Optional[float]) -> Optional[float]:
    if val is None:
        return None
    # if small, assume 10^6 mm^4 table style
    return val * 1e6 if val < 1e6 else val


def to_mm3_from_csv(val: Optional[float]) -> Optional[float]:
    if val is None:
        return None
    # if small-ish, assume 10^3 mm^3 table style
    return val * MULT_ZS if val < 1e6 else val


# ============================================================
# Beam-column math
# ============================================================
def omega1_from_kappa(kappa: float) -> float:
    return max(0.4, 0.6 - 0.4 * kappa)


def omega1_case(case: str, kappa: Optional[float]) -> float:
    if case == "no_transverse_loads":
        if kappa is None:
            raise ValueError("κ is required for no_transverse_loads.")
        return omega1_from_kappa(float(kappa))
    if case == "distributed_or_series":
        return 1.0
    if case == "concentrated_between_supports":
        return 0.85
    raise ValueError("Unknown ω₁ case")


def Ce_euler_N(E_MPa: float, I_mm4: float, L_mm: float) -> float:
    return (math.pi**2) * E_MPa * I_mm4 / (L_mm**2)


def lambda_y(L_mm: float, ry_mm: float, Fy_MPa: float, E_MPa: float) -> float:
    return safe_div(L_mm, (math.pi * ry_mm)) * math.sqrt(safe_div(Fy_MPa, E_MPa))


def beta_weak_axis(lam_y: float) -> float:
    return min(0.85, 0.6 + 0.4 * lam_y)


def U1_braced(omega1: float, Cf_N: float, Ce_N: float) -> float:
    denom = 1.0 - safe_div(Cf_N, Ce_N)
    if denom <= 0:
        return float("inf")
    return omega1 / denom


def U1_sway() -> float:
    return 1.0


def util_tension_bending(Tf: float, Tr: float, Mf: float, Mr: float) -> float:
    return safe_div(Tf, Tr) + safe_div(Mf, Mr)


def util_class12_biaxial(
    Cf: float, Cr: float,
    U1x: float, Mfx: float, Mrx: float,
    U1y: float, Mfy: float, Mry: float,
    beta: float,
) -> float:
    return safe_div(Cf, Cr) + 0.85 * safe_div(U1x * Mfx, Mrx) + beta * safe_div(U1y * Mfy, Mry)


def util_other_biaxial(
    Cf: float, Cr: float,
    U1x: float, Mfx: float, Mrx: float,
    U1y: float, Mfy: float, Mry: float,
) -> float:
    return safe_div(Cf, Cr) + safe_div(U1x * Mfx, Mrx) + safe_div(U1y * Mfy, Mry)


def util_braced_extra(Mfx: float, Mrx: float, Mfy: float, Mry: float) -> float:
    return safe_div(Mfx, Mrx) + safe_div(Mfy, Mry)


def Mr_from_modulus_kNm(Z_or_S_csv: float, Fy_MPa: float) -> float:
    z_mm3 = to_mm3_from_csv(Z_or_S_csv)
    if z_mm3 is None:
        raise ValueError("Section modulus is missing.")
    Mr_Nmm = PHI_B * z_mm3 * Fy_MPa
    return Mr_Nmm / 1e6


# ============================================================
# Optional section-class helper
# - read from CSV if present
# - otherwise give a light auto-suggestion if geometry exists
# ============================================================
def guess_section_class(shape: Dict[str, Any], Fy: float) -> Tuple[str, List[str]]:
    notes: List[str] = []

    csv_class = shape.get("section_class")
    if csv_class not in (None, ""):
        return str(csv_class), ["Section class taken directly from CSV field."]

    b = opt_float(shape.get("b"))
    t = opt_float(shape.get("t"))
    d = opt_float(shape.get("d"))
    w = opt_float(shape.get("w"))
    h = opt_float(shape.get("h"))

    if h is None and d is not None and t is not None:
        h = max(d - 2.0 * t, 0.0)

    if any(v is None for v in [b, t, h, w]):
        return "Unknown", ["Section class not in CSV and geometry is incomplete, so class could not be auto-suggested."]

    # heuristic only
    flange_sl = b / t if t and t > 0 else float("inf")
    web_sl = h / w if w and w > 0 else float("inf")

    fl_c1 = 145.0 / math.sqrt(Fy)
    fl_c2 = 170.0 / math.sqrt(Fy)
    fl_c3 = 200.0 / math.sqrt(Fy)

    def cls(x: float, c1: float, c2: float, c3: float) -> int:
        if x <= c1:
            return 1
        if x <= c2:
            return 2
        if x <= c3:
            return 3
        return 4

    flange_class = cls(flange_sl, fl_c1, fl_c2, fl_c3)

    # very rough generic web classification placeholder
    web_c1 = 1100.0 / math.sqrt(Fy)
    web_c2 = 1700.0 / math.sqrt(Fy)
    web_c3 = 1900.0 / math.sqrt(Fy)
    web_class = cls(web_sl, web_c1, web_c2, web_c3)

    overall = max(flange_class, web_class)
    notes.append("Section class is auto-suggested from geometry only. Verify manually before relying on it.")
    notes.append(f"Flange slenderness b/t = {flange_sl:.3f} → Class {flange_class}")
    notes.append(f"Web slenderness h/w = {web_sl:.3f} → Class {web_class}")
    return f"Class {overall}", notes


# ============================================================
# Streamlit UI helpers
# ============================================================
def read_or_override_number(
    label: str,
    table_value: Optional[float],
    default_if_missing: float,
    key_base: str,
    format_str: Optional[str] = None,
    help_text: Optional[str] = None,
) -> Tuple[float, str]:
    """
    Returns (value, source) where source is:
    - table
    - override
    - fallback
    """
    use_override = st.checkbox(f"Override {label}", key=f"ovr_{key_base}", value=False)

    if table_value is None and not use_override:
        st.warning(f"{label} is not present in the CSV. Using fallback value unless overridden.")
        val = st.number_input(
            label,
            key=f"fallback_{key_base}",
            value=float(default_if_missing),
            format=format_str if format_str else None,
            help=help_text,
        )
        return float(val), "fallback"

    if use_override:
        base = table_value if table_value is not None else default_if_missing
        val = st.number_input(
            label,
            key=f"val_{key_base}",
            value=float(base),
            format=format_str if format_str else None,
            help=help_text,
        )
        return float(val), "override"

    # default read-only display
    if format_str == "%.3e":
        st.text_input(label, value=fmt_sci(table_value), disabled=True, help=help_text)
    else:
        st.text_input(label, value=str(table_value), disabled=True, help=help_text)

    return float(table_value), "table"


def formula_block(title: str, symbolic: str, substitution: str, result: str):
    st.markdown(f"**{title}**")
    st.latex(symbolic)
    st.caption("Substitution")
    st.code(substitution, language="text")
    st.caption("Result")
    st.code(result, language="text")


# ============================================================
# APP
# ============================================================
st.title(APP_TITLE)
st.caption("Loads in kN / kN·m, geometry in mm, E and Fy in MPa. Section properties come from the CSV by default.")

shapes, order = load_shapes_from_data_dir()
if not shapes:
    st.error(f"No CSVs found in: {DATA_DIR}")
    st.stop()

# -----------------------------
# Section selection
# -----------------------------
st.subheader("1) Select section")

section_type = st.selectbox(
    "Section type",
    ["All sections", "W sections", "HSS sections"],
    index=0,
    key="bc_section_type",
)

if section_type == "W sections":
    type_filtered = [s for s in order if s.upper().startswith("W") and len(s) > 1 and s[1].isdigit()]
elif section_type == "HSS sections":
    type_filtered = [s for s in order if s.upper().startswith("HSS")]
else:
    type_filtered = order

search = st.text_input("Search designation", placeholder="e.g., W310 or HSS 305", key="bc_search")
options = type_filtered
if search:
    qq = search.strip().lower()
    options = [s for s in type_filtered if qq in s.lower()]

if not options:
    st.warning("No matching section found.")
    st.stop()

designation = st.selectbox("Designation", options, index=0, key="bc_designation")
shape = shapes[designation]

# canonical raw pulls
Ix_raw = opt_float(shape.get("Ix"))
Iy_raw = opt_float(shape.get("Iy"))
ry_raw = opt_float(shape.get("ry"))
rx_raw = opt_float(shape.get("rx"))
Zx_raw = opt_float(shape.get("Zx"))
Sx_raw = opt_float(shape.get("Sx"))
Zy_raw = opt_float(shape.get("Zy"))
Sy_raw = opt_float(shape.get("Sy"))
Area_raw = opt_float(shape.get("Area"))
d_raw = opt_float(shape.get("d"))
b_raw = opt_float(shape.get("b"))
t_raw = opt_float(shape.get("t"))
w_raw = opt_float(shape.get("w"))
h_raw = opt_float(shape.get("h"))

Ix_csv_mm4 = to_mm4_from_csv(Ix_raw)
Iy_csv_mm4 = to_mm4_from_csv(Iy_raw)

class_guess, class_notes = guess_section_class(shape, 350.0)

with st.expander("Selected shape record / canonicalized CSV fields", expanded=False):
    st.json({
        "designation": designation,
        "Area": Area_raw,
        "d": d_raw,
        "b": b_raw,
        "t": t_raw,
        "w": w_raw,
        "h": h_raw,
        "rx": rx_raw,
        "ry": ry_raw,
        "Ix_raw": Ix_raw,
        "Iy_raw": Iy_raw,
        "Zx_raw": Zx_raw,
        "Sx_raw": Sx_raw,
        "Zy_raw": Zy_raw,
        "Sy_raw": Sy_raw,
        "section_class_guess": class_guess,
        "section_class_notes": class_notes,
    })

# -----------------------------
# Main inputs
# -----------------------------
st.divider()
c1, c2, c3 = st.columns([1.1, 1.1, 1.8])

with c1:
    st.subheader("2) Material / lengths")
    Fy = st.number_input("Fy (MPa)", min_value=200.0, max_value=700.0, value=350.0, step=5.0)
    E = st.number_input("E (MPa)", min_value=100000.0, max_value=300000.0, value=float(E_MPA_DEFAULT), step=10000.0)
    L = st.number_input("Member / unbraced length L (m)", min_value=0.1, value=4.3, step=0.1)
    L_mm = float(L) * 1000.0

with c2:
    st.subheader("3) Applied loads (factored)")
    axial_kN = st.number_input("Axial (kN) (+compression, −tension)", value=1200.0, step=10.0)
    Mx_kNm = st.number_input("Mfx (kN·m)", value=300.0, step=10.0)
    My_kNm = st.number_input("Mfy (kN·m)", value=0.0, step=10.0)

    Cf_N = max(0.0, float(axial_kN) * 1e3)
    Tf_N = max(0.0, -float(axial_kN) * 1e3)
    Mfx_Nmm = abs(float(Mx_kNm) * 1e6)
    Mfy_Nmm = abs(float(My_kNm) * 1e6)

with c3:
    st.subheader("4) Section properties (from CSV by default)")
    st.caption("These are read from the table immediately. Only override them if needed.")

    Ix_mm4, src_Ix = read_or_override_number(
        "Ix (mm⁴)", Ix_csv_mm4, 8.0e8, "Ix", "%.3e", "Major-axis second moment."
    )
    Iy_mm4, src_Iy = read_or_override_number(
        "Iy (mm⁴)", Iy_csv_mm4, 1.2e8, "Iy", "%.3e", "Minor-axis second moment."
    )
    ry_mm, src_ry = read_or_override_number(
        "ry (mm)", ry_raw, 55.0, "ry", None, "Minor-axis radius of gyration."
    )

    st.markdown("**Property sources**")
    st.write(
        f"Ix: `{src_Ix}`  |  Iy: `{src_Iy}`  |  ry: `{src_ry}`"
    )

st.divider()

f1, f2, f3 = st.columns(3)
with f1:
    st.subheader("5) Frame")
    frame_type = st.selectbox("Frame type", ["braced", "sway"], index=0)

with f2:
    st.subheader("6) ω₁ pattern (x)")
    omega1_case_x = st.selectbox(
        "ω₁ case x",
        ["no_transverse_loads", "distributed_or_series", "concentrated_between_supports"],
        index=0,
    )
    kappa_x = st.number_input("κx", value=1.0, step=0.1)

with f3:
    st.subheader("7) ω₁ pattern (y)")
    omega1_case_y = st.selectbox(
        "ω₁ case y",
        ["no_transverse_loads", "distributed_or_series", "concentrated_between_supports"],
        index=0,
    )
    kappa_y = st.number_input("κy", value=1.0, step=0.1)

st.divider()

r1, r2 = st.columns([1.2, 1.8])

with r1:
    st.subheader("8) Resistances")
    auto_Mr = st.checkbox("Auto-calc Mrx / Mry from table Z or S", value=True)

    Mrx_default = 600.0
    Mry_default = 250.0

    if auto_Mr:
        if Zx_raw is not None:
            Mrx_default = Mr_from_modulus_kNm(Zx_raw, Fy)
        elif Sx_raw is not None:
            Mrx_default = Mr_from_modulus_kNm(Sx_raw, Fy)

        if Zy_raw is not None:
            Mry_default = Mr_from_modulus_kNm(Zy_raw, Fy)
        elif Sy_raw is not None:
            Mry_default = Mr_from_modulus_kNm(Sy_raw, Fy)

    Mrx_kNm = st.number_input("Mrx (kN·m)", value=float(Mrx_default), step=10.0)
    Mry_kNm = st.number_input("Mry (kN·m)", value=float(Mry_default), step=10.0)

    # Keep Cr manual here because it is not a raw table property;
    # it depends on member/system behavior, effective length, etc.
    Cr_kN = st.number_input("Cr (kN)", value=2000.0, step=10.0, help="Project/design resistance input.")
    Tr_kN = st.number_input("Tr (kN)", value=2000.0, step=10.0, help="Only used when axial force is tension.")

    Mrx_Nmm = float(Mrx_kNm) * 1e6
    Mry_Nmm = float(Mry_kNm) * 1e6
    Cr_N = float(Cr_kN) * 1e3
    Tr_N = float(Tr_kN) * 1e3

with r2:
    st.subheader("9) Interaction form")
    st.caption("Use the table/section-class logic in your office standard to confirm this choice.")
    st.info(f"Auto-suggested section class: **{class_guess}**")

    interaction_form = st.selectbox(
        "Compression interaction form",
        [
            "Class 1-2 I-shape (0.85*Mx + β*My)",
            "Other classes (Mx + My)",
        ],
        index=0 if "Class 1" in class_guess or "Class 2" in class_guess else 1,
    )
    use_braced_extra = st.checkbox("Apply extra braced-frame Mx/Mrx + My/Mry ≤ 1", value=True)

    if class_notes:
        with st.expander("Section class notes", expanded=False):
            for n in class_notes:
                st.write(f"- {n}")

# -----------------------------
# Run check
# -----------------------------
if st.button("Run beam-column check", type="primary"):
    try:
        omx = omega1_case(omega1_case_x, kappa_x if omega1_case_x == "no_transverse_loads" else None)
        omy = omega1_case(omega1_case_y, kappa_y if omega1_case_y == "no_transverse_loads" else None)

        Cex = Ce_euler_N(E, Ix_mm4, L_mm)
        Cey = Ce_euler_N(E, Iy_mm4, L_mm)

        if frame_type == "sway":
            U1x = U1_sway()
            U1y = U1_sway()
        else:
            U1x = U1_braced(omx, Cf_N, Cex)
            U1y = U1_braced(omy, Cf_N, Cey)

        lam = lambda_y(L_mm, ry_mm, Fy, E)
        beta = beta_weak_axis(lam)

        utils: Dict[str, float] = {}
        passes: Dict[str, bool] = {}
        details: List[Tuple[str, str, str, str]] = []

        # -----------------------------------
        # Tension + bending
        # -----------------------------------
        if Tf_N > 0:
            if Mfx_Nmm > 0:
                util_tx = util_tension_bending(Tf_N, Tr_N, Mfx_Nmm, Mrx_Nmm)
                utils["tension_bending_x"] = util_tx
                passes["tension_bending_x"] = util_tx <= 1.0
                details.append((
                    "Axial tension + bending (x)",
                    r"\frac{T_f}{T_r} + \frac{M_{fx}}{M_{rx}} \le 1.0",
                    f"({Tf_N:.1f}/{Tr_N:.1f}) + ({Mfx_Nmm:.1f}/{Mrx_Nmm:.1f})",
                    f"{util_tx:.4f} → {'PASS' if util_tx <= 1.0 else 'FAIL'}",
                ))

            if Mfy_Nmm > 0:
                util_ty = util_tension_bending(Tf_N, Tr_N, Mfy_Nmm, Mry_Nmm)
                utils["tension_bending_y"] = util_ty
                passes["tension_bending_y"] = util_ty <= 1.0
                details.append((
                    "Axial tension + bending (y)",
                    r"\frac{T_f}{T_r} + \frac{M_{fy}}{M_{ry}} \le 1.0",
                    f"({Tf_N:.1f}/{Tr_N:.1f}) + ({Mfy_Nmm:.1f}/{Mry_Nmm:.1f})",
                    f"{util_ty:.4f} → {'PASS' if util_ty <= 1.0 else 'FAIL'}",
                ))

        # -----------------------------------
        # Compression + bending
        # -----------------------------------
        if Cf_N > 0:
            if "Class 1-2" in interaction_form:
                u = util_class12_biaxial(Cf_N, Cr_N, U1x, Mfx_Nmm, Mrx_Nmm, U1y, Mfy_Nmm, Mry_Nmm, beta)
                details.append((
                    "Compression + bending interaction",
                    r"\frac{C_f}{C_r} + 0.85\frac{U_{1x}M_{fx}}{M_{rx}} + \beta\frac{U_{1y}M_{fy}}{M_{ry}} \le 1.0",
                    f"({Cf_N:.1f}/{Cr_N:.1f}) + 0.85*({U1x:.4f}*{Mfx_Nmm:.1f}/{Mrx_Nmm:.1f}) + {beta:.4f}*({U1y:.4f}*{Mfy_Nmm:.1f}/{Mry_Nmm:.1f})",
                    f"{u:.4f} → {'PASS' if u <= 1.0 else 'FAIL'}",
                ))
            else:
                u = util_other_biaxial(Cf_N, Cr_N, U1x, Mfx_Nmm, Mrx_Nmm, U1y, Mfy_Nmm, Mry_Nmm)
                details.append((
                    "Compression + bending interaction",
                    r"\frac{C_f}{C_r} + \frac{U_{1x}M_{fx}}{M_{rx}} + \frac{U_{1y}M_{fy}}{M_{ry}} \le 1.0",
                    f"({Cf_N:.1f}/{Cr_N:.1f}) + ({U1x:.4f}*{Mfx_Nmm:.1f}/{Mrx_Nmm:.1f}) + ({U1y:.4f}*{Mfy_Nmm:.1f}/{Mry_Nmm:.1f})",
                    f"{u:.4f} → {'PASS' if u <= 1.0 else 'FAIL'}",
                ))

            utils["compression_bending_interaction"] = u
            passes["compression_bending_interaction"] = u <= 1.0

            if frame_type == "braced" and use_braced_extra:
                u2 = util_braced_extra(Mfx_Nmm, Mrx_Nmm, Mfy_Nmm, Mry_Nmm)
                utils["braced_extra_M_interaction"] = u2
                passes["braced_extra_M_interaction"] = u2 <= 1.0
                details.append((
                    "Additional braced-frame moment check",
                    r"\frac{M_{fx}}{M_{rx}} + \frac{M_{fy}}{M_{ry}} \le 1.0",
                    f"({Mfx_Nmm:.1f}/{Mrx_Nmm:.1f}) + ({Mfy_Nmm:.1f}/{Mry_Nmm:.1f})",
                    f"{u2:.4f} → {'PASS' if u2 <= 1.0 else 'FAIL'}",
                ))

        overall = all(passes.values()) if passes else False

        # -----------------------------
        # Results
        # -----------------------------
        st.divider()
        st.subheader("Results")

        top1, top2 = st.columns(2)
        with top1:
            st.metric("Overall result", "PASS" if overall else "FAIL")
            st.write(f"Selected section: **{designation}**")
            st.write(f"Frame type: **{frame_type}**")
            st.write(f"Interaction form: **{interaction_form}**")

        with top2:
            st.write("**Derived parameters**")
            st.write(f"ω₁x = {omx:.4f}")
            st.write(f"ω₁y = {omy:.4f}")
            st.write(f"Ce,x = {Cex:,.0f} N")
            st.write(f"Ce,y = {Cey:,.0f} N")
            st.write(f"U1x = {U1x:.4f}")
            st.write(f"U1y = {U1y:.4f}")
            st.write(f"λy = {lam:.4f}")
            st.write(f"β = {beta:.4f}")

        st.markdown("### Step-by-step calculation sheet")
        for title, symbolic, substitution, result_text in details:
            formula_block(title, symbolic, substitution, result_text)

        st.markdown("### Utilization summary")
        for k, v in utils.items():
            st.write(f"- **{k}** = {v:.4f} → {'PASS' if v <= 1.0 else 'FAIL'}")

        with st.expander("Property provenance", expanded=False):
            st.write(f"Ix source: `{src_Ix}`")
            st.write(f"Iy source: `{src_Iy}`")
            st.write(f"ry source: `{src_ry}`")
            st.write("Mrx / Mry source: `auto from table` if auto-calc enabled, otherwise `manual design input`.")
            st.write("Cr source: `manual design input` (project/design dependent, not a raw table field).")

    except Exception as e:
        st.error(f"Calculation failed: {e}")