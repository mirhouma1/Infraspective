# app.py  (Beam-Column Members — CSV-driven Streamlit app)
from __future__ import annotations
import csv
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# ============================================================
# CONFIG
# ============================================================
APP_TITLE = "CSA S16 Beam-Column (Chapter 5) — CSV-driven"
DATA_DIR = DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PHI_B = 0.9  # used only if you choose to auto-calc Mr from Z/S
E_MPA_DEFAULT = 200000.0  # MPa


# ============================================================
# CSV NORMALIZATION
# - Map arbitrary CSV headers → canonical symbols
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
    "designation": ["designation", "shape", "section", "Section", "name", "w_shape", "member"],

    # geometry (mm)
    "d": ["d", "depth", "overall_depth", "depth_mm"],
    "b": ["b", "bf", "flange_width", "bf_mm"],
    "t": ["t", "tf", "flange_thickness", "tf_mm"],
    "w": ["w", "tw", "web_thickness", "tw_mm"],

    # area and radii
    "Area": ["area", "a", "a_mm2", "area_mm2"],
    "rx": ["rx", "r_x", "rx_mm"],
    "ry": ["ry", "r_y", "ry_mm"],

    # second moments (many CISC tables store Ix/Iy as 10^6 mm^4)
    "Ix": ["ix", "i_x", "ix_106_mm4", "ix_10e6_mm4", "ix_10^6_mm4", "ix_mm4"],
    "Iy": ["iy", "i_y", "iy_106_mm4", "iy_10e6_mm4", "iy_10^6_mm4", "iy_mm4"],

    # section modulus (many CISC tables store Z/S as 10^3 mm^3)
    "Zx": ["zx", "z_x", "zx_103_mm3", "zx_10e3_mm3", "zx_mm3"],
    "Sx": ["sx", "s_x", "sx_103_mm3", "sx_10e3_mm3", "sx_mm3"],
    "Zy": ["zy", "z_y", "zy_103_mm3", "zy_10e3_mm3", "zy_mm3"],
    "Sy": ["sy", "s_y", "sy_103_mm3", "sy_10e3_mm3", "sy_mm3"],
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

    for sym in ("d", "b", "t", "w", "Area", "rx", "ry", "Ix", "Iy", "Zx", "Sx", "Zy", "Sy"):
        v = _pick(rec, CANON_SYNONYMS[sym])
        if v is not None:
            out[sym] = v

    return out


def _load_csv_dictreader(path: Path) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    out: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    # Try UTF-8 first; fall back to latin-1 for files with non-UTF-8 characters
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


def _load_csv_uploaded(uploaded_file) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    df = pd.read_csv(uploaded_file)
    if df.empty:
        return {}, []
    # Convert to dict records
    out: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for rec in df.to_dict(orient="records"):
        rec2 = _canonicalize_record({str(k): v for k, v in rec.items()})
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

    # de-dup order preserving
    seen: set[str] = set()
    uniq: List[str] = []
    for k in order:
        if k not in seen:
            seen.add(k)
            uniq.append(k)

    return merged, uniq


def fnum(x: Any, field: str) -> float:
    try:
        return float(x)
    except Exception as e:
        raise ValueError(f"Field '{field}' is not numeric: {x!r}") from e


# ============================================================
# Beam-column math (mm / MPa / N / N·mm)
# ============================================================
EPS = 1e-12

def safe_div(a: float, b: float) -> float:
    if abs(b) < EPS:
        raise ValueError("Division by ~0 encountered.")
    return a / b

def omega1_from_kappa(kappa: float) -> float:
    # ω1 = 0.6 - 0.4κ but ≥ 0.4
    return max(0.4, 0.6 - 0.4 * kappa)

def omega1_case(case: str, kappa: Optional[float]) -> float:
    if case == "no_transverse_loads":
        if kappa is None:
            raise ValueError("kappa is required for no_transverse_loads.")
        return omega1_from_kappa(float(kappa))
    if case == "distributed_or_series":
        return 1.0
    if case == "concentrated_between_supports":
        return 0.85
    raise ValueError("Unknown ω1 case")

def Ce_euler_N(E_MPa: float, I_mm4: float, L_mm: float) -> float:
    # MPa = N/mm^2 → Ce in N
    return (math.pi**2) * E_MPa * I_mm4 / (L_mm**2)

def lambda_y(L_mm: float, ry_mm: float, Fy_MPa: float, E_MPa: float) -> float:
    # (L/(πry)) * sqrt(Fy/E) ; L and ry both mm so cancel
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

def util_class12_biaxial(Cf: float, Cr: float, U1x: float, Mfx: float, Mrx: float, U1y: float, Mfy: float, Mry: float, beta: float) -> float:
    return safe_div(Cf, Cr) + 0.85 * safe_div(U1x * Mfx, Mrx) + beta * safe_div(U1y * Mfy, Mry)

def util_other_biaxial(Cf: float, Cr: float, U1x: float, Mfx: float, Mrx: float, U1y: float, Mfy: float, Mry: float) -> float:
    return safe_div(Cf, Cr) + safe_div(U1x * Mfx, Mrx) + safe_div(U1y * Mfy, Mry)

def util_braced_extra(Mfx: float, Mrx: float, Mfy: float, Mry: float) -> float:
    return safe_div(Mfx, Mrx) + safe_div(Mfy, Mry)


# ============================================================
# Optional: auto-calc Mr from Z/S if present (simple laterally-supported)
# Assumption: Z/S are stored as 10^3 mm^3 (common in CISC).
# If your CSV is in pure mm^3 already, set MULT_ZS = 1.0.
# ============================================================
MULT_ZS = 1000.0

def Mr_from_ZS_kNm(Z_or_S_10e3_mm3: float, Fy_MPa: float) -> float:
    # Mr = φb * (Z or S) * Fy  → N·mm ; convert to kN·m
    Z_mm3 = float(Z_or_S_10e3_mm3) * MULT_ZS
    Mr_Nmm = PHI_B * Z_mm3 * float(Fy_MPa)
    Mr_kNm = Mr_Nmm / 1e6  # (N·mm) to (kN·m)
    return Mr_kNm


# ============================================================
# UI
# ============================================================
st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)

st.caption("Loads in kN/kN·m, geometry in mm, E/Fy in MPa. CSV supplies section properties.")

left, right = st.columns([2, 1])

with right:
    st.subheader("CSV source")
    st.caption(f"Reading CSVs from: {DATA_DIR}")

shapes, order = load_shapes_from_data_dir()
if not shapes:
    st.error(f"No CSV found in: {DATA_DIR}")
    st.stop()

with left:
    st.subheader("Select section")
    q = st.text_input("Search", placeholder="e.g., W410", label_visibility="collapsed")
    options = order
    if q:
        qq = q.strip().lower()
        options = [s for s in order if qq in s.lower()]

    if not options:
        st.warning("No matches.")
        st.stop()

    designation = st.selectbox("Designation", options=options, index=0)

shape = shapes.get(designation)
if shape is None:
    st.error("Selected section record not found after load.")
    st.stop()

# Extract props (may be missing)
def get_optional_num(key: str) -> Optional[float]:
    v = shape.get(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except Exception:
        return None

Ix_raw = get_optional_num("Ix")
Iy_raw = get_optional_num("Iy")
ry_raw = get_optional_num("ry")
Zx_raw = get_optional_num("Zx")
Sx_raw = get_optional_num("Sx")
Zy_raw = get_optional_num("Zy")
Sy_raw = get_optional_num("Sy")

# Heuristic for Ix/Iy units:
# If your CSV stores Ix as "10^6 mm^4", common values are ~10^2 to 10^4.
# If it stores mm^4 directly, values are huge (~1e8+).
def Ix_to_mm4(val: Optional[float]) -> Optional[float]:
    if val is None:
        return None
    # If it's small-ish, treat it as 10^6 mm^4
    return val * 1e6 if val < 1e6 else val

Ix_mm4_from_csv = Ix_to_mm4(Ix_raw)
Iy_mm4_from_csv = Ix_to_mm4(Iy_raw)

st.divider()

col1, col2, col3 = st.columns([1.2, 1.2, 1.6])

with col1:
    st.subheader("Material / lengths")
    Fy = st.number_input("Fy (MPa)", min_value=200.0, max_value=700.0, value=350.0, step=5.0)
    E = st.number_input("E (MPa)", min_value=100000.0, max_value=300000.0, value=float(E_MPA_DEFAULT), step=10000.0)
    L = st.number_input("Unbraced length L (m)", min_value=0.1, value=4.3, step=0.1)
    L_mm = float(L) * 1000.0

with col2:
    st.subheader("Loads (factored)")
    axial_kN = st.number_input("Axial (kN) (+comp, −tension)", value=1200.0, step=10.0)
    Mx_kNm = st.number_input("Mfx (kN·m)", value=300.0, step=10.0)
    My_kNm = st.number_input("Mfy (kN·m)", value=0.0, step=10.0)

    Cf_N = max(0.0, float(axial_kN) * 1e3)
    Tf_N = max(0.0, -float(axial_kN) * 1e3)
    Mfx_Nmm = abs(float(Mx_kNm) * 1e6)
    Mfy_Nmm = abs(float(My_kNm) * 1e6)

with col3:
    st.subheader("Section properties (auto from CSV; editable)")
    # Defaults from CSV if present; fall back to user entry
    default_Ix = Ix_mm4_from_csv if Ix_mm4_from_csv is not None else 8.0e8
    default_Iy = Iy_mm4_from_csv if Iy_mm4_from_csv is not None else 1.2e8
    default_ry = ry_raw if ry_raw is not None else 55.0

    Ix_mm4 = st.number_input("Ix (mm⁴)", value=float(default_Ix), format="%.3e", step=1.0e7)
    Iy_mm4 = st.number_input("Iy (mm⁴)", value=float(default_Iy), format="%.3e", step=1.0e7)
    ry_mm  = st.number_input("ry (mm)", value=float(default_ry), step=1.0)

    # Show what CSV had
    with st.expander("CSV raw values (debug)", expanded=False):
        st.json({
            "designation": designation,
            "Ix_raw": Ix_raw, "Iy_raw": Iy_raw, "ry_raw": ry_raw,
            "Zx_raw": Zx_raw, "Sx_raw": Sx_raw, "Zy_raw": Zy_raw, "Sy_raw": Sy_raw,
        })

st.divider()

cA, cB, cC = st.columns(3)

with cA:
    st.subheader("Frame")
    frame_type = st.selectbox("Frame type", ["braced", "sway"], index=0)

with cB:
    st.subheader("ω₁ pattern (x)")
    omega1_case_x = st.selectbox("ω₁ case x", ["no_transverse_loads", "distributed_or_series", "concentrated_between_supports"], index=0)
    kappa_x = st.number_input("κx (only for no_transverse_loads)", value=1.0, step=0.1)

with cC:
    st.subheader("ω₁ pattern (y)")
    omega1_case_y = st.selectbox("ω₁ case y", ["no_transverse_loads", "distributed_or_series", "concentrated_between_supports"], index=0)
    kappa_y = st.number_input("κy (only for no_transverse_loads)", value=1.0, step=0.1)

st.divider()

rA, rB = st.columns([1.2, 1.8])

with rA:
    st.subheader("Resistances")
    # Optional auto Mr from Z/S if present
    auto_Mr = st.checkbox("Auto-calc Mrx/Mry from Z/S (if available)", value=True)

    Mrx_default = 600.0
    Mry_default = 250.0

    if auto_Mr and Zx_raw is not None:
        Mrx_default = Mr_from_ZS_kNm(Zx_raw, Fy)
    elif auto_Mr and Sx_raw is not None:
        Mrx_default = Mr_from_ZS_kNm(Sx_raw, Fy)

    if auto_Mr and Zy_raw is not None:
        Mry_default = Mr_from_ZS_kNm(Zy_raw, Fy)
    elif auto_Mr and Sy_raw is not None:
        Mry_default = Mr_from_ZS_kNm(Sy_raw, Fy)

    Mrx_kNm = st.number_input("Mrx (kN·m)", value=float(Mrx_default), step=10.0)
    Mry_kNm = st.number_input("Mry (kN·m)", value=float(Mry_default), step=10.0)

    Cr_kN = st.number_input("Cr (kN)", value=2000.0, step=10.0)
    Tr_kN = st.number_input("Tr (kN) (only if tension)", value=2000.0, step=10.0)

    Mrx_Nmm = float(Mrx_kNm) * 1e6
    Mry_Nmm = float(Mry_kNm) * 1e6
    Cr_N = float(Cr_kN) * 1e3
    Tr_N = float(Tr_kN) * 1e3

with rB:
    st.subheader("Section category (for interaction equation)")
    # You can wire this to your Table-2 classifier later.
    # For now: choose which interaction form to use.
    interaction_form = st.selectbox(
        "Interaction form",
        [
            "Class 1-2 I-shape (0.85*Mx + β*My)",
            "Other classes (Mx + My)",
        ],
        index=0
    )
    use_braced_extra = st.checkbox("Apply extra braced-frame Mx/Mrx + My/Mry ≤ 1", value=True)

if st.button("Run beam-column check", type="primary"):
    # ω1s
    omx = omega1_case(omega1_case_x, kappa_x if omega1_case_x == "no_transverse_loads" else None)
    omy = omega1_case(omega1_case_y, kappa_y if omega1_case_y == "no_transverse_loads" else None)

    # Ce
    Cex = Ce_euler_N(E, Ix_mm4, L_mm)
    Cey = Ce_euler_N(E, Iy_mm4, L_mm)

    # U1
    if frame_type == "sway":
        U1x = U1_sway()
        U1y = U1_sway()
    else:
        U1x = U1_braced(omx, Cf_N, Cex)
        U1y = U1_braced(omy, Cf_N, Cey)

    # beta
    lam = lambda_y(L_mm, ry_mm, Fy, E)
    beta = beta_weak_axis(lam)

    # Utilizations
    utils: Dict[str, float] = {}
    passes: Dict[str, bool] = {}

    # Tension + bending
    if Tf_N > 0:
        util_tx = util_tension_bending(Tf_N, Tr_N, Mfx_Nmm, Mrx_Nmm) if Mfx_Nmm > 0 else Tf_N / Tr_N
        util_ty = util_tension_bending(Tf_N, Tr_N, Mfy_Nmm, Mry_Nmm) if Mfy_Nmm > 0 else Tf_N / Tr_N
        utils["tension_bending_x"] = util_tx
        utils["tension_bending_y"] = util_ty
        passes["tension_bending_x"] = util_tx <= 1.0
        passes["tension_bending_y"] = util_ty <= 1.0

    # Compression + bending
    if Cf_N > 0:
        if "Class 1-2" in interaction_form:
            u = util_class12_biaxial(Cf_N, Cr_N, U1x, Mfx_Nmm, Mrx_Nmm, U1y, Mfy_Nmm, Mry_Nmm, beta)
        else:
            u = util_other_biaxial(Cf_N, Cr_N, U1x, Mfx_Nmm, Mrx_Nmm, U1y, Mfy_Nmm, Mry_Nmm)

        utils["compression_bending_interaction"] = u
        passes["compression_bending_interaction"] = u <= 1.0

        if frame_type == "braced" and use_braced_extra:
            u2 = util_braced_extra(Mfx_Nmm, Mrx_Nmm, Mfy_Nmm, Mry_Nmm)
            utils["braced_extra_M_interaction"] = u2
            passes["braced_extra_M_interaction"] = u2 <= 1.0

    overall = all(passes.values()) if passes else False

    st.divider()
    st.subheader("Results")

    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Overall pass:** {'✅ PASS' if overall else '❌ FAIL'}")
        st.write(f"ω1x = {omx:.4g} | ω1y = {omy:.4g}")
        st.write(f"Cex = {Cex:,.0f} N | Cey = {Cey:,.0f} N")
        st.write(f"U1x = {U1x:.4g} | U1y = {U1y:.4g}")
        st.write(f"λy = {lam:.4g} | β = {beta:.4g}")

    with c2:
        st.markdown("**Utilizations**")
        for k, v in utils.items():
            st.write(f"- **{k}** = {v:.4f} → {'PASS' if v <= 1.0 else 'FAIL'}")

    with st.expander("Selected shape record (canonicalized)", expanded=False):
        # Show canonical keys first
        show = {k: shape.get(k) for k in ["designation","Ix","Iy","ry","Zx","Sx","Zy","Sy","Area","d","b","t","w"] if k in shape}
        st.json(show)
        st.caption("Below is full raw record:")
        st.json(shape)