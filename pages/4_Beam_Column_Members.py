from __future__ import annotations
import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# ============================================================
# CONFIG
# ============================================================
APP_TITLE = "CSA S16 Beam-Column Check (Chapter 13)"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PHI = 0.9     # resistance factor for tension, compression, flexure
N_CSA = 1.34  # CSA S16 column curve exponent (hot-rolled)


# ============================================================
# CSV LOADING
# ============================================================
def _norm(s: str) -> str:
    out = (
        str(s).strip().lower()
        .replace("(", "").replace(")", "")
        .replace("[", "").replace("]", "")
        .replace("/", "_").replace("-", "_")
        .replace(" ", "_").replace("^", "")
    )
    return "".join(c for c in out if (c.isalnum() or c == "_") and ord(c) < 128)


def _pick(rec: Dict[str, Any], candidates: List[str]) -> Optional[Any]:
    norm_map = {_norm(k): v for k, v in rec.items()}
    for cand in candidates:
        ck = _norm(cand)
        if ck in norm_map and norm_map[ck] not in (None, "", " "):
            return norm_map[ck]
    return None


def _flt(x: Any) -> Optional[float]:
    if x in (None, ""):
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None


# Column alias lists — covers w_sections.csv, HSS Rectangular (UTF-8), HSS Circle/Square (latin-1)
_ALIASES: Dict[str, List[str]] = {
    "designation": [
        "Designation", "designation", "Section", "section", "shape", "name",
    ],
    "Area": [
        "Area (mm2)", "Area (mmý)", "Area (mm²)", "Area",
    ],
    "Ix": [
        "Ix (10^6 mm4)", "Ix (10^6 mm?)", "Ix (10^6 mm4)", "Ix (10e6 mm4)",
        "Ix (10^6 mm?)", "Ix (106 mm?)", "Ix (10 mm)", "Ix",
        "I (10? mm?)", "I (10^4 mm4)", "I",
    ],
    "Iy": [
        "Iy (10^6 mm4)", "Iy (10^6 mm?)", "Iy (10e6 mm4)",
        "Iy (10 mm)", "Iy",
    ],
    "Sx": [
        "Sx (10^3 mm3)", "Sx (10^3 mm?)", "Sx (10e3 mm3)",
        "Sx (10 mm)", "Sx",
        "S (10? mm?)", "S (10^3 mm3)", "S",
    ],
    "Sy": [
        "Sy (10^3 mm3)", "Sy (10^3 mm?)", "Sy (10e3 mm3)",
        "Sy (10 mm)", "Sy",
    ],
    "Zx": [
        "Zx (10^3 mm3)", "Zx (10^3 mm?)", "Zx (10e3 mm3)",
        "Zx (10 mm)", "Zx",
        "Z (10? mm?)", "Z (10^3 mm3)", "Z",
    ],
    "Zy": [
        "Zy (10^3 mm3)", "Zy (10^3 mm?)", "Zy (10e3 mm3)",
        "Zy (10 mm)", "Zy",
    ],
    "rx": ["rx (mm)", "rx", "r (mm)", "r"],
    "ry": ["ry (mm)", "ry", "r (mm)", "r"],
    "J":  ["J (10^3 mm4)", "J (10^3 mm?)", "J (10e3 mm4)", "J"],
    "Cw": ["Cw (10^9 mm6)", "Cw (10^9 mm?)", "Cw (10e9 mm6)", "Cw"],
    "d":  ["Depth d (mm)", "Depth (mm)", "d (mm)", "Outside Diameter (mm)", "d"],
    "b":  ["Flange Width b (mm)", "Width (mm)", "b (mm)", "b"],
    "t":  ["Flange Thickness t (mm)", "Wall Thickness (mm)", "tf (mm)", "t"],
    "w":  ["Web Thickness w (mm)", "tw (mm)", "w"],
}

# Multipliers to convert from table units to base SI (mm)
_MULT: Dict[str, float] = {
    "Ix": 1e6, "Iy": 1e6,
    "Sx": 1e3, "Sy": 1e3,
    "Zx": 1e3, "Zy": 1e3,
    "J": 1e3,
    "Cw": 1e9,
}


def _canonicalize(rec: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for sym, aliases in _ALIASES.items():
        v = _pick(rec, aliases)
        if v is not None:
            out[sym] = v
    return out


def _load_csv(path: Path) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    shapes: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    try:
        fh = path.open("r", encoding="utf-8", newline="")
        fh.read(512); fh.seek(0)
    except UnicodeDecodeError:
        fh = path.open("r", encoding="latin-1", newline="")
    with fh as f:
        for rec in csv.DictReader(f):
            c = _canonicalize(rec)
            des = c.get("designation")
            if des:
                key = str(des).strip()
                shapes[key] = c
                order.append(key)
    return shapes, order


@st.cache_data(ttl=120)
def load_all_shapes() -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    if DATA_DIR.exists():
        for p in sorted(DATA_DIR.glob("*.csv"), key=lambda x: x.name.lower()):
            data, csv_order = _load_csv(p)
            merged.update(data)
            order.extend(csv_order)
    seen: set = set()
    uniq = [k for k in order if not (k in seen or seen.add(k))]
    return merged, uniq


def get_prop(shape: Dict[str, Any], sym: str) -> Optional[float]:
    v = _flt(shape.get(sym))
    if v is None:
        return None
    # CSV tables always store values in scaled units (e.g. 10^6 mm^4, 10^3 mm^3)
    # Always apply the defined multiplier unconditionally
    return v * _MULT.get(sym, 1.0)


# ============================================================
# CSA S16 ENGINEERING CALCULATIONS
# ============================================================

def calc_Tr(A_mm2: float, Fy_MPa: float) -> float:
    return PHI * Fy_MPa * A_mm2 / 1000.0  # kN


def calc_Mr(Z_mm3: float, Fy_MPa: float) -> float:
    return PHI * Fy_MPa * Z_mm3 / 1e6  # kN·m


def calc_Cr(A_mm2: float, Fy_MPa: float, E_MPa: float,
            KLr: float) -> Tuple[float, float, float]:
    """Returns (Cr_kN, Fe_MPa, Fcr_MPa) using CSA S16 column curve."""
    if KLr <= 0:
        return PHI * A_mm2 * Fy_MPa / 1000.0, float("inf"), Fy_MPa
    Fe = (math.pi ** 2) * E_MPa / (KLr ** 2)
    lam = KLr * math.sqrt(Fy_MPa / ((math.pi ** 2) * E_MPa))
    Fcr = Fy_MPa / ((1.0 + lam ** (2.0 * N_CSA)) ** (1.0 / N_CSA))
    Cr = PHI * A_mm2 * Fcr / 1000.0
    return Cr, Fe, Fcr


def calc_U1(omega1: float, Cf_kN: float, Ce_kN: float) -> float:
    denom = 1.0 - Cf_kN / Ce_kN if Ce_kN > 0 else 0.0
    if denom <= 0:
        return float("inf")
    return max(1.0, omega1 / denom)


def Ce_euler(E_MPa: float, I_mm4: float, L_mm: float) -> float:
    if L_mm <= 0 or I_mm4 <= 0:
        return float("inf")
    return (math.pi ** 2) * E_MPa * I_mm4 / (L_mm ** 2) / 1000.0  # kN


# ============================================================
# STREAMLIT UI
# ============================================================
st.title(APP_TITLE)
st.caption("W-section and HSS beam-column checks per CSA S16 Clause 13.8 | Loads in kN / kN·m, geometry in mm")

shapes, order = load_all_shapes()
if not shapes:
    st.error(f"No section data found. Add CSV files to: {DATA_DIR}")
    st.stop()

st.markdown("---")

# ── 1. Section selection ──────────────────────────────────────────────────────
st.subheader("1. Section Selection")
sel_col1, sel_col2, sel_col3 = st.columns([1, 1.5, 2])

with sel_col1:
    section_type = st.selectbox(
        "Section type",
        ["All sections", "W sections", "HSS sections"],
        key="bc4_type",
    )

with sel_col2:
    if section_type == "W sections":
        filtered = [s for s in order if s.upper().startswith("W") and len(s) > 1 and s[1].isdigit()]
    elif section_type == "HSS sections":
        filtered = [s for s in order if s.upper().startswith("HSS")]
    else:
        filtered = order

    search = st.text_input("Search", placeholder="e.g. W310 or HSS 203", key="bc4_search")
    if search:
        filtered = [s for s in filtered if search.strip().lower() in s.lower()]

with sel_col3:
    if not filtered:
        st.warning("No sections match.")
        st.stop()
    designation = st.selectbox("Designation", filtered, index=0, key="bc4_des")

shape = shapes[designation]

# Pull raw properties
A    = get_prop(shape, "Area")
Ix   = get_prop(shape, "Ix")
Iy   = get_prop(shape, "Iy")
rx   = get_prop(shape, "rx")
ry   = get_prop(shape, "ry")
Zx   = get_prop(shape, "Zx")
Zy   = get_prop(shape, "Zy")
Sx   = get_prop(shape, "Sx")
Sy   = get_prop(shape, "Sy")
J    = get_prop(shape, "J")
Cw   = get_prop(shape, "Cw")

# Show section properties
with st.expander(f"Section properties — {designation}", expanded=True):
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("A (mm²)",  f"{A:,.0f}"   if A  else "—")
    p1.metric("Ix (mm⁴)", f"{Ix:.3e}"   if Ix else "—")
    p1.metric("Iy (mm⁴)", f"{Iy:.3e}"   if Iy else "—")
    p2.metric("rx (mm)",  f"{rx:.1f}"   if rx else "—")
    p2.metric("ry (mm)",  f"{ry:.1f}"   if ry else "—")
    p3.metric("Zx (mm³)", f"{Zx:.3e}"   if Zx else "—")
    p3.metric("Zy (mm³)", f"{Zy:.3e}"   if Zy else "—")
    p4.metric("Sx (mm³)", f"{Sx:.3e}"   if Sx else "—")
    p4.metric("Sy (mm³)", f"{Sy:.3e}"   if Sy else "—")
    if J:
        p1.metric("J (mm⁴)",  f"{J:.3e}")
    if Cw:
        p2.metric("Cw (mm⁶)", f"{Cw:.3e}")

st.markdown("---")

# ── 2. Material ───────────────────────────────────────────────────────────────
st.subheader("2. Material Properties")
mat1, mat2 = st.columns(2)
with mat1:
    Fy = st.number_input("Fy (MPa)", min_value=200.0, max_value=700.0, value=350.0, step=5.0, key="bc4_fy")
with mat2:
    E  = st.number_input("E (MPa)",  min_value=100000.0, max_value=300000.0, value=200000.0, step=1000.0, key="bc4_e")

st.markdown("---")

# ── 3. Axial case ─────────────────────────────────────────────────────────────
st.subheader("3. Member Axial Condition")
axial_case_label = st.selectbox(
    "Axial condition",
    ["— Select —", "Member in Axial Tension", "Member in Axial Compression"],
    key="bc4_case_dd",
)

if axial_case_label == "— Select —":
    st.info("Select an axial condition above to continue.")
    st.stop()

axial_case = "TENSION" if axial_case_label == "Member in Axial Tension" else "COMPRESSION"
st.markdown("---")

# ── 4. Inputs ─────────────────────────────────────────────────────────────────
if axial_case == "TENSION":
    st.subheader("4. Tension + Bending Inputs")
    t1, t2 = st.columns(2)
    with t1:
        Tf  = st.number_input("Factored Tension Tf (kN)",         min_value=0.0, value=500.0,  step=10.0, key="bc4_tf")
        Mfx = st.number_input("Factored Moment Mfx (kN·m)",       min_value=0.0, value=100.0,  step=10.0, key="bc4_mfx_t")
    with t2:
        Mfy = st.number_input("Factored Moment Mfy (kN·m)",       min_value=0.0, value=0.0,    step=10.0, key="bc4_mfy_t")

else:  # COMPRESSION
    st.subheader("4. Compression + Bending Inputs")
    c1, c2, c3 = st.columns(3)
    with c1:
        Cf  = st.number_input("Factored Compression Cf (kN)",     min_value=0.0, value=1200.0, step=50.0,  key="bc4_cf")
        Mfx = st.number_input("Factored Moment Mfx (kN·m)",       min_value=0.0, value=200.0,  step=10.0,  key="bc4_mfx_c")
        Mfy = st.number_input("Factored Moment Mfy (kN·m)",       min_value=0.0, value=0.0,    step=10.0,  key="bc4_mfy_c")
    with c2:
        Kx  = st.number_input("Kx (eff. length factor, x-axis)", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="bc4_kx")
        Lx  = st.number_input("Lx — unbraced length x (m)",      min_value=0.1, value=4.0,    step=0.5,  key="bc4_lx")
    with c3:
        Ky  = st.number_input("Ky (eff. length factor, y-axis)", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="bc4_ky")
        Ly  = st.number_input("Ly — unbraced length y (m)",      min_value=0.1, value=4.0,    step=0.5,  key="bc4_ly")

    st.markdown("**Moment gradient factor ω₁** (per CSA S16 Clause 13.8)")
    w1_col1, w1_col2 = st.columns(2)
    with w1_col1:
        omega1_case_x = st.selectbox(
            "ω₁ case — x-axis",
            ["No transverse loads (κ-based)", "Distributed / series moments", "Concentrated between supports"],
            key="bc4_w1x_case",
        )
        if omega1_case_x == "No transverse loads (κ-based)":
            kappa_x = st.number_input("κx (ratio of smaller/larger end moment, −1 to 1)", min_value=-1.0, max_value=1.0, value=1.0, step=0.1, key="bc4_kx_kappa")
            omega1_x = max(0.4, 0.6 - 0.4 * kappa_x)
        elif omega1_case_x == "Distributed / series moments":
            omega1_x = 1.0
        else:
            omega1_x = 0.85
    with w1_col2:
        omega1_case_y = st.selectbox(
            "ω₁ case — y-axis",
            ["No transverse loads (κ-based)", "Distributed / series moments", "Concentrated between supports"],
            key="bc4_w1y_case",
        )
        if omega1_case_y == "No transverse loads (κ-based)":
            kappa_y = st.number_input("κy (ratio of smaller/larger end moment, −1 to 1)", min_value=-1.0, max_value=1.0, value=1.0, step=0.1, key="bc4_ky_kappa")
            omega1_y = max(0.4, 0.6 - 0.4 * kappa_y)
        elif omega1_case_y == "Distributed / series moments":
            omega1_y = 1.0
        else:
            omega1_y = 0.85

st.markdown("---")

# ── 5. Calculate & display results ────────────────────────────────────────────
st.subheader("5. Results")

try:
    if axial_case == "TENSION":
        if A is None:
            st.error("Area (A) not found in section data.")
            st.stop()

        Tr_kN  = calc_Tr(A, Fy)
        Mrx_kNm = calc_Mr(Zx, Fy) if Zx else None
        Mry_kNm = calc_Mr(Zy, Fy) if Zy else None

        ratio_T  = Tf / Tr_kN if Tr_kN > 0 else 0.0
        ratio_Mx = Mfx / Mrx_kNm if (Mrx_kNm and Mrx_kNm > 0) else 0.0
        ratio_My = Mfy / Mry_kNm if (Mry_kNm and Mry_kNm > 0) else 0.0
        interaction = ratio_T + ratio_Mx + ratio_My

        res1, res2 = st.columns(2)
        with res1:
            st.markdown("**Resistances**")
            st.metric("φTr (kN)",    f"{Tr_kN:.1f}")
            st.metric("φMrx (kN·m)", f"{Mrx_kNm:.1f}" if Mrx_kNm else "—")
            st.metric("φMry (kN·m)", f"{Mry_kNm:.1f}" if Mry_kNm else "—")
        with res2:
            st.markdown("**Interaction Check — CSA S16 Cl. 13.9**")
            st.latex(r"\frac{T_f}{\phi T_r} + \frac{M_{fx}}{\phi M_{rx}} + \frac{M_{fy}}{\phi M_{ry}} \leq 1.0")
            st.code(
                f"= {ratio_T:.4f} + {ratio_Mx:.4f} + {ratio_My:.4f} = {interaction:.4f}",
                language="text",
            )
            if interaction <= 1.0:
                st.success(f"PASS   Interaction = {interaction:.3f} ≤ 1.0")
            else:
                st.error(f"FAIL   Interaction = {interaction:.3f} > 1.0")

    else:  # COMPRESSION
        missing = [s for s, v in [("A", A), ("rx", rx), ("ry", ry), ("Ix", Ix), ("Iy", Iy)] if v is None]
        if missing:
            st.error(f"Missing required section properties: {', '.join(missing)}")
            st.stop()

        Lx_mm = Lx * 1000.0
        Ly_mm = Ly * 1000.0
        KLr_x = (Kx * Lx_mm) / rx
        KLr_y = (Ky * Ly_mm) / ry
        KLr   = max(KLr_x, KLr_y)
        gov_axis = "x" if KLr_x >= KLr_y else "y"

        Cr_kN, Fe_MPa, Fcr_MPa = calc_Cr(A, Fy, E, KLr)
        lam = KLr * math.sqrt(Fy / ((math.pi ** 2) * E))

        Mrx_kNm = calc_Mr(Zx, Fy) if Zx else None
        Mry_kNm = calc_Mr(Zy, Fy) if Zy else None

        Ce_x = Ce_euler(E, Ix, Lx_mm)
        Ce_y = Ce_euler(E, Iy, Ly_mm)

        U1x = calc_U1(omega1_x, Cf, Ce_x)
        U1y = calc_U1(omega1_y, Cf, Ce_y)

        lam_y = (Ly_mm / (math.pi * ry)) * math.sqrt(Fy / E)
        beta  = min(0.85, 0.6 + 0.4 * lam_y)

        ratio_C  = Cf / Cr_kN if Cr_kN > 0 else float("inf")
        ratio_Mx = (0.85 * U1x * Mfx / Mrx_kNm) if (Mrx_kNm and Mrx_kNm > 0) else 0.0
        ratio_My = (beta * U1y * Mfy / Mry_kNm)  if (Mry_kNm and Mry_kNm > 0) else 0.0
        interaction = ratio_C + ratio_Mx + ratio_My

        # Braced-frame extra moment check
        extra_mx = Mfx / Mrx_kNm if (Mrx_kNm and Mrx_kNm > 0) else 0.0
        extra_my = Mfy / Mry_kNm if (Mry_kNm and Mry_kNm > 0) else 0.0
        extra_interaction = extra_mx + extra_my

        r1, r2 = st.columns(2)
        with r1:
            st.markdown("**Column Buckling**")
            st.markdown(f"- KL/r (x) = {KLr_x:.2f}")
            st.markdown(f"- KL/r (y) = {KLr_y:.2f}")
            st.markdown(f"- Governing KL/r = **{KLr:.2f}** ({gov_axis}-axis)")
            st.markdown(f"- λ = {lam:.4f}")
            st.markdown(f"- Fe = {Fe_MPa:.1f} MPa")
            st.markdown(f"- Fcr = {Fcr_MPa:.1f} MPa")
            st.metric("φCr (kN)", f"{Cr_kN:.1f}")

            st.markdown("**Moment Resistances**")
            st.metric("φMrx (kN·m)", f"{Mrx_kNm:.1f}" if Mrx_kNm else "—")
            st.metric("φMry (kN·m)", f"{Mry_kNm:.1f}" if Mry_kNm else "—")

        with r2:
            st.markdown("**Amplification Factors**")
            st.markdown(f"- Ce,x = {Ce_x:,.0f} kN  |  ω₁x = {omega1_x:.3f}  →  U1x = {U1x:.4f}")
            st.markdown(f"- Ce,y = {Ce_y:,.0f} kN  |  ω₁y = {omega1_y:.3f}  →  U1y = {U1y:.4f}")
            st.markdown(f"- λy = {lam_y:.4f}  →  β = {beta:.4f}")

            st.markdown("**Interaction Check — CSA S16 Cl. 13.8.2 (Class 1/2)**")
            st.latex(r"\frac{C_f}{C_r} + 0.85\frac{U_{1x}M_{fx}}{M_{rx}} + \beta\frac{U_{1y}M_{fy}}{M_{ry}} \leq 1.0")
            st.code(
                f"= {ratio_C:.4f} + {ratio_Mx:.4f} + {ratio_My:.4f} = {interaction:.4f}",
                language="text",
            )
            if interaction <= 1.0:
                st.success(f"PASS   Interaction = {interaction:.3f} ≤ 1.0")
            else:
                st.error(f"FAIL   Interaction = {interaction:.3f} > 1.0")

            if Mfx > 0 or Mfy > 0:
                st.markdown("**Additional braced-frame moment check (Cl. 13.8.2)**")
                st.latex(r"\frac{M_{fx}}{M_{rx}} + \frac{M_{fy}}{M_{ry}} \leq 1.0")
                st.code(
                    f"= {extra_mx:.4f} + {extra_my:.4f} = {extra_interaction:.4f}",
                    language="text",
                )
                if extra_interaction <= 1.0:
                    st.success(f"PASS   {extra_interaction:.3f} ≤ 1.0")
                else:
                    st.error(f"FAIL   {extra_interaction:.3f} > 1.0")

except Exception as e:
    st.error(f"Calculation error: {e}")
    import traceback
    with st.expander("Full traceback"):
        st.code(traceback.format_exc())
