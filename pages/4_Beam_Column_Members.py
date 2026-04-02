from __future__ import annotations
import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# ============================================================
# CONFIG
# ============================================================
APP_TITLE = "Beam-Column Check — W Sections (CSA S16 Cl. 13.8)"
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
    "section_class": ["Class", "class", "Section Class", "section class"],
    "ba_t": ["ba/t", "b_a/t", "ba_t", "b_a_over_t"],
    "h_w":  ["h/w", "h_w", "h_over_w"],
}

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


# ============================================================
# SAFE PROPERTY READERS
# ============================================================
def get_raw_prop(shape: Dict[str, Any], sym: str) -> Optional[float]:
    return _flt(shape.get(sym))


def get_prop(shape: Dict[str, Any], sym: str) -> Optional[float]:
    v = _flt(shape.get(sym))
    if v is None:
        return None
    return v * _MULT.get(sym, 1.0)


# ============================================================
# CSA S16 CLAUSE 13.5 — MOMENT RESISTANCE (LATERALLY SUPPORTED)
# ============================================================
def calc_Mr_clause_13_5(
    shape: Dict[str, Any],
    Fy_MPa: float,
    axis: str = "x",
) -> Dict[str, Any]:
    designation = str(shape.get("designation", "Unknown")).strip()
    cls_raw = get_raw_prop(shape, "section_class")
    if cls_raw is None:
        raise ValueError(f"{designation}: 'Class' column not found in CSV.")
    section_class = int(cls_raw)

    axis = axis.lower()
    if axis == "x":
        Z = get_prop(shape, "Zx")
        S = get_prop(shape, "Sx")
        axis_label = "x"
    elif axis == "y":
        Z = get_prop(shape, "Zy")
        S = get_prop(shape, "Sy")
        axis_label = "y"
    else:
        raise ValueError("axis must be 'x' or 'y'")

    result: Dict[str, Any] = {
        "designation":   designation,
        "section_class": section_class,
        "axis":          axis_label,
        "Mr_kNm":        None,
        "formula":       None,
        "modulus_used":  None,
        "warning":       None,
    }

    if section_class in (1, 2):
        if Z is None:
            raise ValueError(f"{designation}: Z{axis_label} missing — required for Class {section_class}.")
        result.update({
            "Mr_kNm":       PHI * Fy_MPa * Z / 1e6,
            "formula":      f"Mr = φ · Z{axis_label} · Fy",
            "modulus_used": f"Z{axis_label}",
        })
        return result

    if section_class == 3:
        if S is None:
            raise ValueError(f"{designation}: S{axis_label} missing — required for Class 3.")
        result.update({
            "Mr_kNm":       PHI * Fy_MPa * S / 1e6,
            "formula":      f"Mr = φ · S{axis_label} · Fy",
            "modulus_used": f"S{axis_label}",
        })
        return result

    if section_class == 4:
        result.update({
            "warning": (
                "Class 4 section — Cl. 13.5 requires effective section modulus. "
                "Mr not computed in this version."
            ),
            "ba_t": get_raw_prop(shape, "ba_t"),
            "h_w":  get_raw_prop(shape, "h_w"),
        })
        return result

    raise ValueError(f"{designation}: unrecognised section class value '{section_class}'.")


# ============================================================
# CSA S16 CLAUSE 13.6 — MOMENT RESISTANCE (LATERALLY UNSUPPORTED)
# ============================================================
G_STEEL = 77_000.0  # MPa

def calc_Mu(
    omega2: float,
    L_mm: float,
    E_MPa: float,
    Iy_mm4: float,
    G_MPa: float,
    J_mm4: float,
    Cw_mm6: float,
) -> float:
    term1 = E_MPa * Iy_mm4 * G_MPa * J_mm4
    term2 = ((math.pi * E_MPa / L_mm) ** 2) * Iy_mm4 * Cw_mm6
    return (omega2 * math.pi / L_mm) * math.sqrt(term1 + term2)


def calc_Mr_clause_13_6(
    shape: Dict[str, Any],
    Fy_MPa: float,
    omega2: float,
    L_mm: float,
    E_MPa: float,
    G_MPa: float,
    Cw_override: Optional[float] = None,
) -> Dict[str, Any]:
    designation = str(shape.get("designation", "Unknown")).strip()
    cls_raw = get_raw_prop(shape, "section_class")
    if cls_raw is None:
        raise ValueError(f"{designation}: 'Class' column not found in CSV.")
    section_class = int(cls_raw)

    Zx  = get_prop(shape, "Zx")
    Iy  = get_prop(shape, "Iy")
    J   = get_prop(shape, "J")
    Cw  = Cw_override if Cw_override is not None else get_prop(shape, "Cw")

    missing = [n for n, v in [("Zx", Zx), ("Iy", Iy), ("J", J), ("Cw", Cw)] if v is None]
    if missing:
        raise ValueError(f"{designation}: missing properties for Cl. 13.6 — {', '.join(missing)}")

    assert Zx is not None and Iy is not None and J is not None and Cw is not None

    Mp_Nmm = Fy_MPa * Zx
    Mp_kNm = Mp_Nmm / 1e6
    Mu_Nmm = calc_Mu(omega2, L_mm, E_MPa, Iy, G_MPa, J, Cw)
    Mu_kNm = Mu_Nmm / 1e6
    phi_Mp_kNm = PHI * Mp_kNm
    threshold  = 0.67 * Mp_kNm

    if Mu_kNm > threshold:
        Mr_kNm_raw = 1.15 * PHI * Mp_kNm * (1.0 - 0.28 * Mp_kNm / Mu_kNm)
        Mr_kNm     = min(Mr_kNm_raw, phi_Mp_kNm)
        branch     = "Mu > 0.67·Mp"
        formula    = r"M_r = 1.15\,\phi M_p\!\left(1 - \frac{0.28\,M_p}{M_u}\right) \leq \phi M_p"
    else:
        Mr_kNm  = PHI * Mu_kNm
        branch  = "Mu ≤ 0.67·Mp"
        formula = r"M_r = \phi M_u"

    return {
        "designation":   designation,
        "section_class": section_class,
        "omega2":        omega2,
        "L_mm":          L_mm,
        "Iy_mm4":        Iy,
        "J_mm4":         J,
        "Cw_mm6":        Cw,
        "Mp_kNm":        Mp_kNm,
        "Mu_kNm":        Mu_kNm,
        "phi_Mp_kNm":    phi_Mp_kNm,
        "threshold_kNm": threshold,
        "branch":        branch,
        "formula":       formula,
        "Mr_kNm":        Mr_kNm,
        "warning":       None if section_class in (1, 2) else
                         f"Cl. 13.6 branch (a) applies to Class 1 & 2 only. "
                         f"This section is Class {section_class} — review applicable sub-clause.",
    }


# ============================================================
# CSA S16 ENGINEERING CALCULATIONS
# ============================================================
def calc_Tr(A_mm2: float, Fy_MPa: float) -> float:
    return PHI * float(Fy_MPa) * float(A_mm2) / 1000.0  # kN


def calc_Mr(Z_mm3: float, Fy_MPa: float) -> float:
    return PHI * float(Fy_MPa) * float(Z_mm3) / 1e6  # kN·m


def calc_Cr(
    A_mm2: float,
    Fy_MPa: float,
    E_MPa: float,
    KLr: float,
) -> Tuple[float, float, float]:
    A_mm2  = float(A_mm2)
    Fy_MPa = float(Fy_MPa)
    E_MPa  = float(E_MPa)
    KLr    = float(KLr)

    if KLr <= 0:
        return PHI * A_mm2 * Fy_MPa / 1000.0, float("inf"), Fy_MPa
    Fe  = (math.pi ** 2) * E_MPa / (KLr ** 2)
    lam = KLr * math.sqrt(Fy_MPa / ((math.pi ** 2) * E_MPa))
    Fcr = Fy_MPa / ((1.0 + lam ** (2.0 * N_CSA)) ** (1.0 / N_CSA))
    Cr  = PHI * A_mm2 * Fcr / 1000.0
    return Cr, Fe, Fcr


def calc_U1(omega1: float, Cf_kN: float, Ce_kN: float) -> float:
    denom = 1.0 - float(Cf_kN) / float(Ce_kN) if Ce_kN > 0 else 0.0
    if denom <= 0:
        return float("inf")
    return max(1.0, float(omega1) / denom)


def Ce_euler(E_MPa: float, I_mm4: float, L_mm: float) -> float:
    E_MPa = float(E_MPa)
    I_mm4 = float(I_mm4)
    L_mm  = float(L_mm)
    if L_mm <= 0 or I_mm4 <= 0:
        return float("inf")
    return (math.pi ** 2) * E_MPa * I_mm4 / (L_mm ** 2) / 1000.0  # kN


# ============================================================
# STREAMLIT UI
# ============================================================
st.title(APP_TITLE)
st.caption("W-section beam-column checks per CSA S16 Clause 13.8 | Loads in kN / kN·m, geometry in mm")

shapes, order = load_all_shapes()
if not shapes:
    st.error(f"No section data found. Add CSV files to: {DATA_DIR}")
    st.stop()

# W sections only, sorted ascending (by depth then by weight)
def _w_sort_key(s: str):
    try:
        parts = s.upper().lstrip("W").split("X")
        return (int(parts[0]), float(parts[1]))
    except Exception:
        return (9999, 9999)

w_sections = sorted(
    [s for s in order if s.upper().startswith("W") and len(s) > 1 and s[1].isdigit()],
    key=_w_sort_key,
)

st.markdown("---")

# ── 1. Section selection ──────────────────────────────────────────────────────
st.subheader("1. Section Selection")
sel_col1, sel_col2 = st.columns([1.5, 2])

with sel_col1:
    search = st.text_input("Search", placeholder="e.g. W310 or W200x52", key="bc4_search")
    filtered = [s for s in w_sections if search.strip().lower() in s.lower()] if search else w_sections

with sel_col2:
    if not filtered:
        st.warning("No sections match.")
        st.stop()
    designation = st.selectbox("Designation", filtered, index=0, key="bc4_des")

shape = shapes[designation]

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

sec_class = get_raw_prop(shape, "section_class")
ba_t      = get_raw_prop(shape, "ba_t")
h_w       = get_raw_prop(shape, "h_w")

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
    cl1, cl2, cl3 = st.columns(3)
    cl1.metric("Section Class (CSA S16)",  str(int(sec_class)) if sec_class is not None else "—")
    cl2.metric("b_a / t  (flange slend.)", f"{ba_t:.2f}" if ba_t is not None else "—")
    cl3.metric("h / w  (web slend.)",      f"{h_w:.2f}"  if h_w  is not None else "—")

    _class_labels = {1: "Class 1 — Plastic", 2: "Class 2 — Compact",
                     3: "Class 3 — Non-compact", 4: "Class 4 — Slender"}
    if sec_class is not None:
        label = _class_labels.get(int(sec_class), f"Class {int(sec_class)}")
        if int(sec_class) == 4:
            st.warning(f"⚠️ {label} — effective section treatment required for Mr (Cl. 13.5c).")
        else:
            st.info(f"ℹ️ {label}")

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
        Tf  = st.number_input("Factored Tension Tf (kN)",   min_value=0.0, value=500.0,  step=10.0, key="bc4_tf")
        Mfx = st.number_input("Factored Moment Mfx (kN·m)", min_value=0.0, value=100.0,  step=10.0, key="bc4_mfx_t")
    with t2:
        Mfy = st.number_input("Factored Moment Mfy (kN·m)", min_value=0.0, value=0.0,    step=10.0, key="bc4_mfy_t")

    st.markdown("---")
    st.markdown("**Laterally Unsupported Check — Cl. 13.9.2 / Cl. 13.6** *(optional)*")
    run_136 = st.checkbox(
        "Include Cl. 13.9.2 check (laterally unsupported member)",
        value=False, key="bc4_run136",
    )

    if run_136:
        u1, u2, u3 = st.columns(3)
        with u1:
            L_unsup = st.number_input(
                "Unbraced length L (m)", min_value=0.1, value=4.0, step=0.5, key="bc4_L136"
            )
            Cw_csv = get_prop(shape, "Cw")
            cw_default = round(Cw_csv / 1e9, 4) if Cw_csv else 0.0
            Cw_user = st.number_input(
                f"Cw (×10⁹ mm⁶)  [CSV = {cw_default}]",
                min_value=0.0, value=cw_default, format="%.4f", key="bc4_cw136",
            )
        with u2:
            omega2_method = st.selectbox(
                "ω₂ method",
                ["Linear approximation (κ-based)", "Quarter-point moments"],
                key="bc4_w2_method",
            )
        with u3:
            if omega2_method == "Linear approximation (κ-based)":
                kappa_136 = st.number_input(
                    "κ  (M_smaller / M_larger, +ve = double curvature)",
                    min_value=-1.0, max_value=1.0, value=1.0, step=0.1, key="bc4_kappa136",
                )
                omega2_val = min(2.5, 1.75 + 1.05 * kappa_136 + 0.3 * kappa_136 ** 2)
                st.info(f"ω₂ = 1.75 + 1.05κ + 0.3κ²  =  **{omega2_val:.3f}**")
            else:
                st.markdown("**Quarter-point moments (kN·m)**")
                Mmax_qp = st.number_input("M_max (maximum in segment)", min_value=0.01, value=200.0, step=10.0, key="bc4_mmax")
                Ma_qp   = st.number_input("M_a   (at ¼ point)",         min_value=0.0,  value=150.0, step=10.0, key="bc4_ma")
                Mb_qp   = st.number_input("M_b   (at midpoint)",        min_value=0.0,  value=180.0, step=10.0, key="bc4_mb")
                Mc_qp   = st.number_input("M_c   (at ¾ point)",         min_value=0.0,  value=160.0, step=10.0, key="bc4_mc")
                denom_qp = math.sqrt(Mmax_qp**2 + 4*Ma_qp**2 + 7*Mb_qp**2 + 4*Mc_qp**2)
                omega2_val = min(2.5, 4 * Mmax_qp / denom_qp) if denom_qp > 0 else 1.0
                st.info(f"ω₂ = 4·Mmax / √(Mmax² + 4Ma² + 7Mb² + 4Mc²)  =  **{omega2_val:.3f}**")

else:  # COMPRESSION — Section 4 inputs
    st.subheader("4. Compression + Bending Inputs")

    # ── Row 1: loads and lengths ──────────────────────────────────────────────
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

    st.markdown("---")

    # ── ω₁ inputs (Cl. 13.8.4 / 13.8.5) — used for U₁ in all three checks ──
    st.markdown("**Moment gradient factor ω₁** *(Cl. 13.8.5 — used for U₁ in all three checks)*")
    w1_col1, w1_col2 = st.columns(2)

    with w1_col1:
        omega1_case_x = st.selectbox(
            "ω₁ case — x-axis",
            ["No transverse loads (κ-based)", "Distributed / series moments", "Concentrated between supports"],
            key="bc4_w1x_case",
        )
        if omega1_case_x == "No transverse loads (κ-based)":
            kappa_x  = st.number_input("κx (−1 to 1, +ve = double curvature)", min_value=-1.0, max_value=1.0, value=1.0, step=0.1, key="bc4_kx_kappa")
            omega1_x = max(0.4, 0.6 - 0.4 * kappa_x)
            st.info(f"ω₁x = 0.6 − 0.4κx = **{omega1_x:.3f}**")
        elif omega1_case_x == "Distributed / series moments":
            omega1_x = 1.0
            st.info("ω₁x = 1.0")
        else:
            omega1_x = 0.85
            st.info("ω₁x = 0.85")

    with w1_col2:
        omega1_case_y = st.selectbox(
            "ω₁ case — y-axis",
            ["No transverse loads (κ-based)", "Distributed / series moments", "Concentrated between supports"],
            key="bc4_w1y_case",
        )
        if omega1_case_y == "No transverse loads (κ-based)":
            kappa_y  = st.number_input("κy (−1 to 1, +ve = double curvature)", min_value=-1.0, max_value=1.0, value=1.0, step=0.1, key="bc4_ky_kappa")
            omega1_y = max(0.4, 0.6 - 0.4 * kappa_y)
            st.info(f"ω₁y = 0.6 − 0.4κy = **{omega1_y:.3f}**")
        elif omega1_case_y == "Distributed / series moments":
            omega1_y = 1.0
            st.info("ω₁y = 1.0")
        else:
            omega1_y = 0.85
            st.info("ω₁y = 0.85")

    st.markdown("---")

    # ── ω₂ / Cw inputs for Check (c) Cl. 13.6 ───────────────────────────────
    st.markdown("**Check (c) — Lateral Torsional Buckling inputs** *(Cl. 13.6, uses Ly as unbraced length)*")

    ltb1, ltb2, ltb3 = st.columns(3)

    with ltb1:
        Cw_csv_disp = get_prop(shape, "Cw")
        cw_def_disp = round(Cw_csv_disp / 1e9, 4) if Cw_csv_disp else 0.0
        Cw_user_c   = st.number_input(
            f"Cw (×10⁹ mm⁶)  [CSV = {cw_def_disp}]",
            min_value=0.0, value=cw_def_disp, format="%.4f", key="bc4_cw_c",
        )

    with ltb2:
        omega2_method_c = st.selectbox(
            "ω₂ method",
            ["Linear approximation (κ-based)", "Quarter-point moments"],
            key="bc4_w2_method_c",
        )

    with ltb3:
        if omega2_method_c == "Linear approximation (κ-based)":
            kappa_c  = st.number_input(
                "κ (+ve = double curvature)",
                min_value=-1.0, max_value=1.0, value=1.0, step=0.1, key="bc4_kappa_c",
            )
            omega2_c = min(2.5, 1.75 + 1.05 * kappa_c + 0.3 * kappa_c ** 2)
            st.info(f"ω₂ = 1.75 + 1.05κ + 0.3κ² = **{omega2_c:.3f}**")
        else:
            st.markdown("**Quarter-point moments (kN·m)**")
            Mmax_c = st.number_input("M_max", min_value=0.01, value=200.0, step=10.0, key="bc4_mmax_c")
            Ma_c   = st.number_input("M_a (¼ pt)", min_value=0.0, value=150.0, step=10.0, key="bc4_ma_c")
            Mb_c   = st.number_input("M_b (mid)",  min_value=0.0, value=180.0, step=10.0, key="bc4_mb_c")
            Mc_c   = st.number_input("M_c (¾ pt)", min_value=0.0, value=160.0, step=10.0, key="bc4_mc_c")
            denom_c = math.sqrt(Mmax_c**2 + 4*Ma_c**2 + 7*Mb_c**2 + 4*Mc_c**2)
            omega2_c = min(2.5, 4 * Mmax_c / denom_c) if denom_c > 0 else 1.0
            st.info(f"ω₂ = 4·Mmax / √(...) = **{omega2_c:.3f}**")

st.markdown("---")

# ── 5. Calculate & display results ────────────────────────────────────────────
st.subheader("5. Results")

try:
    if axial_case == "TENSION":
        # ── Compute Mrx and Mry via Clause 13.5 ──────────────────────────────
        res_x = calc_Mr_clause_13_5(shape, Fy, axis="x")
        res_y = calc_Mr_clause_13_5(shape, Fy, axis="y")
        Mrx_kNm: Optional[float] = res_x["Mr_kNm"]
        Mry_kNm: Optional[float] = res_y["Mr_kNm"]

        if res_x["warning"]:
            st.warning(f"x-axis: {res_x['warning']}")
        if res_y["warning"]:
            st.warning(f"y-axis: {res_y['warning']}")

        if A is None:
            st.error("Area (A) not found in section data.")
            st.stop()

        assert A is not None

        Tr_kN = calc_Tr(A, Fy)

        ratio_T  = Tf / Tr_kN    if Tr_kN  > 0                  else 0.0
        ratio_Mx = Mfx / Mrx_kNm if (Mrx_kNm and Mrx_kNm > 0)  else 0.0
        ratio_My = Mfy / Mry_kNm if (Mry_kNm and Mry_kNm > 0)  else 0.0
        interaction = ratio_T + ratio_Mx + ratio_My

        sc        = res_x["section_class"]
        mod_x     = res_x.get("modulus_used") or "Zx"
        mod_y     = res_y.get("modulus_used") or "Zy"
        mod_x_val = get_prop(shape, mod_x)
        mod_y_val = get_prop(shape, mod_y)

        # ── Step 1 : Cl. 13.5 ─────────────────────────────────────────────
        st.markdown("#### Step 1 — Moment Resistance  *(CSA S16 Cl. 13.5)*")
        st.markdown(
            f"Section **Class {sc}** → "
            + ("use **plastic modulus Z**" if sc in (1, 2) else "use **elastic modulus S**")
        )

        col_x, col_y = st.columns(2)
        with col_x:
            st.markdown("**x-axis  (Mrx)**")
            if sc in (1, 2):
                st.latex(r"M_{rx} = \phi \cdot Z_x \cdot F_y")
            else:
                st.latex(r"M_{rx} = \phi \cdot S_x \cdot F_y")
            if mod_x_val is not None and Mrx_kNm is not None:
                st.code(
                    f"= {PHI} × {mod_x_val:,.0f} mm³ × {Fy:.0f} MPa\n"
                    f"= {Mrx_kNm * 1e6:,.0f} N·mm\n"
                    f"= {Mrx_kNm:.1f} kN·m",
                    language="text",
                )
            else:
                st.warning("Mrx could not be computed (Class 4 or missing modulus).")

        with col_y:
            st.markdown("**y-axis  (Mry)**")
            if sc in (1, 2):
                st.latex(r"M_{ry} = \phi \cdot Z_y \cdot F_y")
            else:
                st.latex(r"M_{ry} = \phi \cdot S_y \cdot F_y")
            if mod_y_val is not None and Mry_kNm is not None:
                st.code(
                    f"= {PHI} × {mod_y_val:,.0f} mm³ × {Fy:.0f} MPa\n"
                    f"= {Mry_kNm * 1e6:,.0f} N·mm\n"
                    f"= {Mry_kNm:.1f} kN·m",
                    language="text",
                )
            else:
                st.warning("Mry could not be computed (Class 4 or missing modulus).")

        st.markdown("---")

        # ── Step 2 : Tension resistance Tr ────────────────────────────────
        st.markdown("#### Step 2 — Tension Resistance  *(CSA S16 Cl. 13.2)*")
        st.latex(r"T_r = \phi \cdot A \cdot F_y")
        st.code(
            f"= {PHI} × {A:,.0f} mm² × {Fy:.0f} MPa\n"
            f"= {Tr_kN * 1000:,.0f} N\n"
            f"= {Tr_kN:.1f} kN",
            language="text",
        )

        st.markdown("---")

        # ── Step 3 : Cl. 13.9 interaction check ───────────────────────────
        st.markdown("#### Step 3 — Tension + Bending Interaction  *(CSA S16 Cl. 13.9)*")
        st.latex(
            r"\frac{T_f}{\phi T_r} + \frac{M_{fx}}{\phi M_{rx}} "
            r"+ \frac{M_{fy}}{\phi M_{ry}} \leq 1.0"
        )
        mrx_str = f"{Mrx_kNm:.1f}" if Mrx_kNm else "—"
        mry_str = f"{Mry_kNm:.1f}" if Mry_kNm else "—"
        st.code(
            f"  Tf / φTr   = {Tf:.1f} / {Tr_kN:.1f}   = {ratio_T:.4f}\n"
            f"  Mfx / φMrx = {Mfx:.1f} / {mrx_str}  = {ratio_Mx:.4f}\n"
            f"  Mfy / φMry = {Mfy:.1f} / {mry_str}  = {ratio_My:.4f}\n"
            f"  ─────────────────────────────────────────\n"
            f"  Total       = {ratio_T:.4f} + {ratio_Mx:.4f} + {ratio_My:.4f} = {interaction:.4f}",
            language="text",
        )
        if interaction <= 1.0:
            st.success(f"✅  PASS   Interaction = {interaction:.3f} ≤ 1.0")
        else:
            st.error(f"❌  FAIL   Interaction = {interaction:.3f} > 1.0")

        # ── Step 4 : Cl. 13.9.2 — Laterally unsupported check ────────────
        if run_136:
            st.markdown("---")
            st.markdown("#### Step 4 — Laterally Unsupported Check  *(CSA S16 Cl. 13.9.2 / Cl. 13.6)*")

            L_mm_136 = L_unsup * 1000.0
            Cw_mm6   = Cw_user * 1e9

            res_136 = calc_Mr_clause_13_6(
                shape       = shape,
                Fy_MPa      = Fy,
                omega2      = omega2_val,
                L_mm        = L_mm_136,
                E_MPa       = E,
                G_MPa       = G_STEEL,
                Cw_override = Cw_mm6,
            )

            if res_136["warning"]:
                st.warning(res_136["warning"])

            Mp_kNm    = res_136["Mp_kNm"]
            Mu_kNm    = res_136["Mu_kNm"]
            Mr136_kNm = res_136["Mr_kNm"]
            branch    = res_136["branch"]
            Iy_val    = res_136["Iy_mm4"]
            J_val     = res_136["J_mm4"]

            st.markdown("**4a — Critical Elastic Moment Mu  (Cl. 13.6)**")
            st.latex(
                r"M_u = \frac{\omega_2 \pi}{L}"
                r"\sqrt{EI_y GJ + \left(\frac{\pi E}{L}\right)^2 I_y C_w}"
            )
            st.code(
                f"  ω₂  = {omega2_val:.3f}\n"
                f"  L   = {L_mm_136:,.0f} mm\n"
                f"  E   = {E:,.0f} MPa\n"
                f"  Iy  = {Iy_val:.3e} mm⁴\n"
                f"  G   = {G_STEEL:,.0f} MPa\n"
                f"  J   = {J_val:.3e} mm⁴\n"
                f"  Cw  = {Cw_mm6:.3e} mm⁶\n"
                f"  ─────────────────────────────────────\n"
                f"  Mu  = {Mu_kNm:.1f} kN·m",
                language="text",
            )

            st.markdown("**4b — Plastic Moment Mp and branch selection**")
            Zx_val = get_prop(shape, "Zx")
            st.code(
                f"  Mp = Fy × Zx = {Fy:.0f} × {Zx_val:,.0f} = {Mp_kNm*1e6:,.0f} N·mm = {Mp_kNm:.1f} kN·m\n"
                f"  0.67·Mp = {0.67*Mp_kNm:.1f} kN·m\n"
                f"  Mu = {Mu_kNm:.1f} kN·m  →  {branch}",
                language="text",
            )

            st.markdown("**4c — Factored Moment Resistance Mr  (Cl. 13.6)**")
            st.latex(res_136["formula"])
            if branch.startswith("Mu >"):
                st.code(
                    f"  = 1.15 × {PHI} × {Mp_kNm:.1f} × (1 − 0.28 × {Mp_kNm:.1f} / {Mu_kNm:.1f})\n"
                    f"  = {1.15*PHI*Mp_kNm*(1-0.28*Mp_kNm/Mu_kNm):.1f} kN·m\n"
                    f"  ≤ φMp = {PHI*Mp_kNm:.1f} kN·m\n"
                    f"  Mr = {Mr136_kNm:.1f} kN·m",
                    language="text",
                )
            else:
                st.code(
                    f"  = {PHI} × {Mu_kNm:.1f}\n"
                    f"  Mr = {Mr136_kNm:.1f} kN·m",
                    language="text",
                )

            st.markdown("**4d — Interaction Check  (Cl. 13.9.2)**")
            if sc in (1, 2):
                Zx_v = get_prop(shape, "Zx")
                assert Zx_v is not None and A is not None and Mr136_kNm > 0
                interact_136 = Mfx / Mr136_kNm - (Tf * Zx_v) / (Mr136_kNm * 1e3 * A)
                st.latex(r"\frac{M_f}{M_r} - \frac{T_f Z}{M_r A} \leq 1.0 \quad \text{(Class 1 \& 2)}")
                st.code(
                    f"  Mfx / Mr    = {Mfx:.1f} / {Mr136_kNm:.1f}           = {Mfx/Mr136_kNm:.4f}\n"
                    f"  Tf·Z/(Mr·A) = {Tf:.1f}×{Zx_v:.3e} / ({Mr136_kNm:.1f}×10³×{A:.0f})\n"
                    f"             = {(Tf*Zx_v)/(Mr136_kNm*1e3*A):.4f}\n"
                    f"  ─────────────────────────────────────────\n"
                    f"  Interaction = {interact_136:.4f}",
                    language="text",
                )
            else:
                Sx_v = get_prop(shape, "Sx")
                assert Sx_v is not None and A is not None and Mr136_kNm > 0
                interact_136 = Mfx / Mr136_kNm - (Tf * Sx_v) / (Mr136_kNm * 1e3 * A)
                st.latex(r"\frac{M_f}{M_r} - \frac{T_f S}{M_r A} \leq 1.0 \quad \text{(Class 3 \& 4)}")
                st.code(
                    f"  Mfx / Mr    = {Mfx:.1f} / {Mr136_kNm:.1f}          = {Mfx/Mr136_kNm:.4f}\n"
                    f"  Tf·S/(Mr·A) = {Tf:.1f}×{Sx_v:.3e} / ({Mr136_kNm:.1f}×10³×{A:.0f})\n"
                    f"             = {(Tf*Sx_v)/(Mr136_kNm*1e3*A):.4f}\n"
                    f"  ─────────────────────────────────────────\n"
                    f"  Interaction = {interact_136:.4f}",
                    language="text",
                )

            if interact_136 <= 1.0:
                st.success(f"✅  PASS   Cl. 13.9.2 Interaction = {interact_136:.3f} ≤ 1.0")
            else:
                st.error(f"❌  FAIL   Cl. 13.9.2 Interaction = {interact_136:.3f} > 1.0")

    else:  # COMPRESSION — Results
        missing = [s for s, v in [("A", A), ("rx", rx), ("ry", ry), ("Ix", Ix), ("Iy", Iy)] if v is None]
        if missing:
            st.error(f"Missing required section properties: {', '.join(missing)}")
            st.stop()

        assert A is not None and rx is not None and ry is not None
        assert Ix is not None and Iy is not None

        # ── Geometry ─────────────────────────────────────────────────────────
        Lx_mm = Lx * 1000.0
        Ly_mm = Ly * 1000.0
        KLr_x = (Kx * Lx_mm) / rx
        KLr_y = (Ky * Ly_mm) / ry

        # ── Ce (Euler buckling loads) for U1 ─────────────────────────────────
        Ce_x = Ce_euler(E, Ix, Lx_mm)
        Ce_y = Ce_euler(E, Iy, Ly_mm)

        # ── λ variants ───────────────────────────────────────────────────────
        # K=1 slenderness for checks (b) and (c)
        KLr_x_K1 = Lx_mm / rx
        KLr_y_K1 = Ly_mm / ry
        KLr_b    = max(KLr_x_K1, KLr_y_K1)   # Check (b) — governing axis
        KLr_c    = KLr_y_K1                    # Check (c) — weak axis only

        lam_b    = KLr_b * math.sqrt(Fy / ((math.pi ** 2) * E))
        lam_c    = KLr_c * math.sqrt(Fy / ((math.pi ** 2) * E))

        # β uses λy with K=1 (same for checks b and c)
        lam_y_K1 = KLr_y_K1 * math.sqrt(Fy / ((math.pi ** 2) * E))
        beta_bc  = min(0.85, 0.6 + 0.4 * lam_y_K1)

        # ── Cr variants ──────────────────────────────────────────────────────
        Cr_a              = PHI * A * Fy / 1000.0              # Check (a): λ=0
        Cr_b, Fe_b, Fcr_b = calc_Cr(A, Fy, E, KLr_b)          # Check (b): K=1, governing
        Cr_c, Fe_c, Fcr_c = calc_Cr(A, Fy, E, KLr_c)          # Check (c): K=1, weak-axis

        # ── U1 — braced frame: always computed, enforced ≥ 1.0 ──────────────
        U1x = max(1.0, calc_U1(omega1_x, Cf, Ce_x))
        U1y = max(1.0, calc_U1(omega1_y, Cf, Ce_y))

        # ── Mr from Cl. 13.5 ─────────────────────────────────────────────────
        res_x_135 = calc_Mr_clause_13_5(shape, Fy, axis="x")
        res_y_135 = calc_Mr_clause_13_5(shape, Fy, axis="y")
        Mrx_135   = res_x_135["Mr_kNm"]
        Mry_135   = res_y_135["Mr_kNm"]

        if res_x_135["warning"]:
            st.warning(f"Mrx (Cl. 13.5): {res_x_135['warning']}")
        if res_y_135["warning"]:
            st.warning(f"Mry (Cl. 13.5): {res_y_135['warning']}")

        sc    = res_x_135["section_class"]
        mod_x = res_x_135.get("modulus_used") or "Zx"
        mod_y = res_y_135.get("modulus_used") or "Zy"

        # =====================================================================
        # STEP 1 — Section & Member Summary
        # =====================================================================
        st.markdown("#### Step 1 — Member Summary")
        s1a, s1b, s1c, s1d = st.columns(4)
        s1a.metric("KL/r (x)",        f"{KLr_x:.2f}")
        s1b.metric("KL/r (y)",        f"{KLr_y:.2f}")
        s1c.metric("Ce,x (kN)",       f"{Ce_x:,.0f}")
        s1d.metric("Ce,y (kN)",       f"{Ce_y:,.0f}")

        s2a, s2b, s2c, s2d = st.columns(4)
        s2a.metric("U₁x (Cl.13.8.4)", f"{U1x:.4f}")
        s2b.metric("U₁y (Cl.13.8.4)", f"{U1y:.4f}")
        s2c.metric("ω₁x",             f"{omega1_x:.3f}")
        s2d.metric("ω₁y",             f"{omega1_y:.3f}")

        st.markdown("---")

        # =====================================================================
        # STEP 2 — Moment Resistances (Cl. 13.5)
        # =====================================================================
        st.markdown("#### Step 2 — Moment Resistance  *(CSA S16 Cl. 13.5)*")
        st.markdown(
            f"Section **Class {sc}** → "
            + ("use **plastic modulus Z**" if sc in (1, 2) else "use **elastic modulus S**")
        )

        col_mrx, col_mry = st.columns(2)
        with col_mrx:
            st.markdown("**x-axis — Mrx**")
            st.latex(r"M_{rx} = \phi \cdot Z_x \cdot F_y" if sc in (1, 2) else r"M_{rx} = \phi \cdot S_x \cdot F_y")
            mod_x_val = get_prop(shape, mod_x)
            if mod_x_val is not None and Mrx_135 is not None:
                st.code(
                    f"= {PHI} × {mod_x_val:,.0f} mm³ × {Fy:.0f} MPa\n"
                    f"= {Mrx_135 * 1e6:,.0f} N·mm\n"
                    f"= {Mrx_135:.1f} kN·m",
                    language="text",
                )
            else:
                st.warning("Mrx could not be computed (Class 4 or missing modulus).")

        with col_mry:
            st.markdown("**y-axis — Mry**")
            st.latex(r"M_{ry} = \phi \cdot Z_y \cdot F_y" if sc in (1, 2) else r"M_{ry} = \phi \cdot S_y \cdot F_y")
            mod_y_val = get_prop(shape, mod_y)
            if mod_y_val is not None and Mry_135 is not None:
                st.code(
                    f"= {PHI} × {mod_y_val:,.0f} mm³ × {Fy:.0f} MPa\n"
                    f"= {Mry_135 * 1e6:,.0f} N·mm\n"
                    f"= {Mry_135:.1f} kN·m",
                    language="text",
                )
            else:
                st.warning("Mry could not be computed (Class 4 or missing modulus).")

        st.markdown("---")

        # =====================================================================
        # STEP 3 — CHECK (a): Cross-Sectional Strength
        #          λ=0 | β=0.6 | U1 per Cl.13.8.4 ≥ 1.0 | braced only
        # =====================================================================
        st.markdown("#### Step 3 — Check (a): Cross-Sectional Strength  *(Cl. 13.8.2a)*")
        st.caption("Braced frame · λ = 0 → Cr = φAFy · β = 0.6 · U₁ per Cl. 13.8.4 ≥ 1.0")
        st.latex(
            r"\frac{C_f}{C_r} + \frac{0.85\,U_{1x}M_{fx}}{M_{rx}}"
            r"+ \frac{0.6\,U_{1y}M_{fy}}{M_{ry}} \leq 1.0"
        )

        st.markdown("**Cr — with λ = 0:**")
        st.latex(r"C_r = \phi A F_y")
        st.code(
            f"= {PHI} × {A:,.0f} mm² × {Fy:.0f} MPa\n"
            f"= {Cr_a:.1f} kN",
            language="text",
        )

        ra_C  = Cf / Cr_a if Cr_a > 0 else float("inf")
        ra_Mx = (0.85 * U1x * Mfx / Mrx_135) if (Mrx_135 and Mrx_135 > 0) else 0.0
        ra_My = (0.6  * U1y * Mfy / Mry_135) if (Mry_135 and Mry_135 > 0) else 0.0
        int_a = ra_C + ra_Mx + ra_My

        st.code(
            f"  Cf / Cr              = {Cf:.1f} / {Cr_a:.1f}             = {ra_C:.4f}\n"
            f"  0.85·U1x·Mfx / Mrx  = 0.85 × {U1x:.4f} × {Mfx:.1f} / {Mrx_135:.1f}  = {ra_Mx:.4f}\n"
            f"  0.6·U1y·Mfy  / Mry  = 0.60 × {U1y:.4f} × {Mfy:.1f} / {Mry_135:.1f}  = {ra_My:.4f}\n"
            f"  ──────────────────────────────────────────────────────────\n"
            f"  Total                = {ra_C:.4f} + {ra_Mx:.4f} + {ra_My:.4f} = {int_a:.4f}",
            language="text",
        )
        if int_a <= 1.0:
            st.success(f"✅  PASS   Check (a) = {int_a:.3f} ≤ 1.0")
        else:
            st.error(f"❌  FAIL   Check (a) = {int_a:.3f} > 1.0")

        st.markdown("---")

        # =====================================================================
        # STEP 4 — CHECK (b): Overall Member Strength
        #          K=1, governing KL/r | β=0.6+0.4λy | U1 per Cl.13.8.4
        # =====================================================================
        st.markdown("#### Step 4 — Check (b): Overall Member Strength  *(Cl. 13.8.2b)*")
        st.caption("K = 1 · governing KL/r · β = 0.6 + 0.4λy ≤ 0.85 · U₁ per Cl. 13.8.4")
        gov_axis_b = "x" if KLr_x_K1 >= KLr_y_K1 else "y"
        st.latex(
            r"\frac{C_f}{C_r} + \frac{0.85\,U_{1x}M_{fx}}{M_{rx}}"
            r"+ \frac{\beta\,U_{1y}M_{fy}}{M_{ry}} \leq 1.0"
        )

        st.markdown("**Cr — K = 1, governing KL/r:**")
        st.latex(
            r"C_r = \frac{\phi A F_y}{(1 + \lambda^{2n})^{1/n}}"
            r"\qquad \lambda = \frac{KL}{r}\sqrt{\frac{F_y}{\pi^2 E}}"
        )
        st.code(
            f"  KL/r (x, K=1) = {KLr_x_K1:.2f}\n"
            f"  KL/r (y, K=1) = {KLr_y_K1:.2f}\n"
            f"  Governing     = {KLr_b:.2f}  ({gov_axis_b}-axis)\n"
            f"  λ             = {lam_b:.4f}\n"
            f"  Fe            = {Fe_b:.1f} MPa\n"
            f"  Fcr           = {Fcr_b:.1f} MPa\n"
            f"  Cr            = {Cr_b:.1f} kN",
            language="text",
        )

        st.markdown("**β:**")
        st.latex(r"\beta = 0.6 + 0.4\lambda_y \leq 0.85")
        st.code(
            f"  λy (K=1) = {lam_y_K1:.4f}\n"
            f"  β        = 0.6 + 0.4 × {lam_y_K1:.4f} = {0.6 + 0.4*lam_y_K1:.4f}  →  capped at {beta_bc:.4f}",
            language="text",
        )

        rb_C  = Cf / Cr_b if Cr_b > 0 else float("inf")
        rb_Mx = (0.85 * U1x * Mfx / Mrx_135) if (Mrx_135 and Mrx_135 > 0) else 0.0
        rb_My = (beta_bc * U1y * Mfy / Mry_135) if (Mry_135 and Mry_135 > 0) else 0.0
        int_b = rb_C + rb_Mx + rb_My

        st.code(
            f"  Cf / Cr              = {Cf:.1f} / {Cr_b:.1f}              = {rb_C:.4f}\n"
            f"  0.85·U1x·Mfx / Mrx  = 0.85 × {U1x:.4f} × {Mfx:.1f} / {Mrx_135:.1f}  = {rb_Mx:.4f}\n"
            f"  β·U1y·Mfy   / Mry   = {beta_bc:.4f} × {U1y:.4f} × {Mfy:.1f} / {Mry_135:.1f}  = {rb_My:.4f}\n"
            f"  ──────────────────────────────────────────────────────────\n"
            f"  Total                = {rb_C:.4f} + {rb_Mx:.4f} + {rb_My:.4f} = {int_b:.4f}",
            language="text",
        )
        if int_b <= 1.0:
            st.success(f"✅  PASS   Check (b) = {int_b:.3f} ≤ 1.0")
        else:
            st.error(f"❌  FAIL   Check (b) = {int_b:.3f} > 1.0")

        # ── Additional moment-only check ──────────────────────────────────────
        st.markdown("**Additional moment-only check  (Cl. 13.8.2b):**")
        st.latex(r"\frac{M_{fx}}{M_{rx}} + \frac{M_{fy}}{M_{ry}} \leq 1.0")
        rb_add_x  = Mfx / Mrx_135 if (Mrx_135 and Mrx_135 > 0) else 0.0
        rb_add_y  = Mfy / Mry_135 if (Mry_135 and Mry_135 > 0) else 0.0
        int_b_add = rb_add_x + rb_add_y
        st.code(
            f"  Mfx / Mrx = {Mfx:.1f} / {Mrx_135:.1f} = {rb_add_x:.4f}\n"
            f"  Mfy / Mry = {Mfy:.1f} / {Mry_135:.1f} = {rb_add_y:.4f}\n"
            f"  ──────────────────────────────────\n"
            f"  Total     = {int_b_add:.4f}",
            language="text",
        )
        if int_b_add <= 1.0:
            st.success(f"✅  PASS   Moment check = {int_b_add:.3f} ≤ 1.0")
        else:
            st.error(f"❌  FAIL   Moment check = {int_b_add:.3f} > 1.0")

        st.markdown("---")

        # =====================================================================
        # STEP 5 — CHECK (c): Lateral Torsional Buckling
        #          Cr: weak-axis K=1 | Mrx: Cl.13.6 (L=Ly) | Mry: Cl.13.5
        #          U1x ≥ 1.0 | β = 0.6+0.4λy
        # =====================================================================
        st.markdown("#### Step 5 — Check (c): Lateral Torsional Buckling  *(Cl. 13.8.2c)*")
        st.caption("Cr: weak-axis KL/r (K=1) · Mrx per Cl. 13.6 (L = Ly) · Mry per Cl. 13.5 · U₁x ≥ 1.0")
        st.latex(
            r"\frac{C_f}{C_r} + \frac{0.85\,U_{1x}M_{fx}}{M_{rx}^{(13.6)}}"
            r"+ \frac{\beta\,U_{1y}M_{fy}}{M_{ry}} \leq 1.0"
        )

        st.markdown("**Cr — weak-axis KL/r (K = 1):**")
        st.code(
            f"  KL/r (y, K=1) = {KLr_c:.2f}\n"
            f"  λ             = {lam_c:.4f}\n"
            f"  Fe            = {Fe_c:.1f} MPa\n"
            f"  Fcr           = {Fcr_c:.1f} MPa\n"
            f"  Cr            = {Cr_c:.1f} kN",
            language="text",
        )

        st.markdown("**Mrx — Cl. 13.6  (unbraced length = Ly):**")
        Cw_mm6_c  = Cw_user_c * 1e9
        Ly_mm_ltb = Ly_mm

        try:
            res_136_c = calc_Mr_clause_13_6(
                shape       = shape,
                Fy_MPa      = Fy,
                omega2      = omega2_c,
                L_mm        = Ly_mm_ltb,
                E_MPa       = E,
                G_MPa       = G_STEEL,
                Cw_override = Cw_mm6_c,
            )

            if res_136_c["warning"]:
                st.warning(res_136_c["warning"])

            Mp_c     = res_136_c["Mp_kNm"]
            Mu_c     = res_136_c["Mu_kNm"]
            Mrx_c    = res_136_c["Mr_kNm"]
            branch_c = res_136_c["branch"]

            st.latex(
                r"M_u = \frac{\omega_2 \pi}{L}"
                r"\sqrt{EI_y GJ + \left(\frac{\pi E}{L}\right)^2 I_y C_w}"
            )
            st.code(
                f"  ω₂  = {omega2_c:.3f}\n"
                f"  L   = {Ly_mm_ltb:,.0f} mm  (= Ly)\n"
                f"  Iy  = {res_136_c['Iy_mm4']:.3e} mm⁴\n"
                f"  J   = {res_136_c['J_mm4']:.3e} mm⁴\n"
                f"  Cw  = {Cw_mm6_c:.3e} mm⁶\n"
                f"  ─────────────────────────────────────\n"
                f"  Mu  = {Mu_c:.1f} kN·m\n"
                f"  Mp  = Fy·Zx = {Mp_c:.1f} kN·m\n"
                f"  0.67·Mp = {0.67*Mp_c:.1f} kN·m  →  {branch_c}",
                language="text",
            )
            st.latex(res_136_c["formula"])
            if branch_c.startswith("Mu >"):
                st.code(
                    f"  = 1.15 × {PHI} × {Mp_c:.1f} × (1 − 0.28 × {Mp_c:.1f} / {Mu_c:.1f})\n"
                    f"  = {1.15*PHI*Mp_c*(1-0.28*Mp_c/Mu_c):.1f} kN·m\n"
                    f"  ≤ φMp = {PHI*Mp_c:.1f} kN·m\n"
                    f"  Mrx (Cl.13.6) = {Mrx_c:.1f} kN·m",
                    language="text",
                )
            else:
                st.code(
                    f"  = {PHI} × {Mu_c:.1f}\n"
                    f"  Mrx (Cl.13.6) = {Mrx_c:.1f} kN·m",
                    language="text",
                )

            rc_C  = Cf / Cr_c if Cr_c > 0 else float("inf")
            rc_Mx = (0.85 * U1x * Mfx / Mrx_c)    if Mrx_c  > 0              else 0.0
            rc_My = (beta_bc * U1y * Mfy / Mry_135) if (Mry_135 and Mry_135 > 0) else 0.0
            int_c = rc_C + rc_Mx + rc_My

            st.code(
                f"  Cf / Cr              = {Cf:.1f} / {Cr_c:.1f}               = {rc_C:.4f}\n"
                f"  0.85·U1x·Mfx / Mrx  = 0.85 × {U1x:.4f} × {Mfx:.1f} / {Mrx_c:.1f}   = {rc_Mx:.4f}\n"
                f"  β·U1y·Mfy   / Mry   = {beta_bc:.4f} × {U1y:.4f} × {Mfy:.1f} / {Mry_135:.1f}  = {rc_My:.4f}\n"
                f"  ──────────────────────────────────────────────────────────\n"
                f"  Total                = {rc_C:.4f} + {rc_Mx:.4f} + {rc_My:.4f} = {int_c:.4f}",
                language="text",
            )
            if int_c <= 1.0:
                st.success(f"✅  PASS   Check (c) = {int_c:.3f} ≤ 1.0")
            else:
                st.error(f"❌  FAIL   Check (c) = {int_c:.3f} > 1.0")

        except Exception as e_ltb:
            st.error(f"Check (c) could not be computed: {e_ltb}")
            int_c = float("nan")

        st.markdown("---")

        # =====================================================================
        # STEP 6 — Governing Summary
        # =====================================================================
        st.markdown("#### Step 6 — Governing Check Summary  *(Cl. 13.8.2)*")

        summary_data = {
            "Check (a) — Cross-section":  int_a,
            "Check (b) — Overall member": int_b,
            "Check (b) — Moment-only":    int_b_add,
            "Check (c) — LTB":            int_c,
        }

        for label, val in summary_data.items():
            if math.isnan(val):
                st.warning(f"⚠️  {label}  — could not be computed")
                continue
            icon   = "✅" if val <= 1.0 else "❌"
            status = "PASS" if val <= 1.0 else "FAIL"
            st.markdown(f"{icon} **{label}** → {val:.3f}  *({status})*")

        valid_vals = [v for v in summary_data.values() if not math.isnan(v)]
        if valid_vals:
            gov_label = max(
                (k for k in summary_data if not math.isnan(summary_data[k])),
                key=lambda k: summary_data[k],
            )
            gov_val = summary_data[gov_label]
            st.markdown("---")
            if gov_val <= 1.0:
                st.success(f"✅  **OVERALL PASS** — Governing: {gov_label} = {gov_val:.3f} ≤ 1.0")
            else:
                st.error(f"❌  **OVERALL FAIL** — Governing: {gov_label} = {gov_val:.3f} > 1.0")

except Exception as e:
    st.error(f"Calculation error: {e}")
    import traceback
    with st.expander("Full traceback"):
        st.code(traceback.format_exc())
