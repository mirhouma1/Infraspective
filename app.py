import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# ----------------------------
# CONFIG
# ----------------------------
DATA_DIR = Path(__file__).resolve().parent / "data"
PHI_B = 0.9
PHI_V_DEFAULT = 0.9  # set to your project standard

# ----------------------------
# KEY NORMALIZATION + CANONICAL FIELD MAP
# ----------------------------
def _norm(s: str) -> str:
    return (
        str(s).strip().lower()
        .replace("(", "").replace(")", "")
        .replace("[", "").replace("]", "")
        .replace("/", "_").replace("-", "_")
        .replace(" ", "_")
        .replace("^", "")
    )


CANON_SYNONYMS = {
    "designation": {"designation", "shape", "section", "name", "w_shape"},
    "d": {"d", "depth", "depth_d", "depth_d_mm", "overall_depth"},
    "b": {"b", "bf", "flange_width", "flange_width_b", "flange_width_b_mm"},
    "tf": {"tf", "t", "flange_thickness", "flange_thickness_t", "flange_thickness_t_mm"},
    "tw": {"tw", "w", "web_thickness", "web_thickness_w", "web_thickness_w_mm"},
    "zx": {"zx", "z_x", "plastic_modulus_zx", "plastic_modulus_zx_mm3", "zx_mm3", "zx_103_mm"},
    "sx": {"sx", "s_x", "elastic_modulus_sx", "elastic_modulus_sx_mm3", "sx_mm3", "sx_103_mm"},
    "k": {"k", "distance_k", "distance_k_mm", "fillet_distance"},
}


def _canonicalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    norm_map = {_norm(k): v for k, v in rec.items()}
    out = dict(rec)

    def pick(field: str) -> Optional[Any]:
        for cand in CANON_SYNONYMS[field]:
            ck = _norm(cand)
            if ck in norm_map and norm_map[ck] not in (None, ""):
                return norm_map[ck]
        return None

    def pick_by_prefix(prefix: str) -> Optional[Any]:
        for k, v in rec.items():
            k_lower = k.lower().strip()
            if k_lower.startswith(prefix) and v not in (None, ""):
                return v
        return None

    for f in ("designation", "d", "b", "tf", "tw", "zx", "sx", "k"):
        v = pick(f)
        if v is not None:
            out[f] = v

    # Fallback: try prefix matching for Zx and Sx columns (e.g., "Zx (10^3 mm³)")
    if out.get("zx") is None:
        v = pick_by_prefix("zx")
        if v is not None:
            out["zx"] = v
    if out.get("sx") is None:
        v = pick_by_prefix("sx")
        if v is not None:
            out["sx"] = v

    # Also match some common patterns
    if out.get("d") is None:
        v = pick_by_prefix("depth d")
        if v is not None:
            out["d"] = v
    if out.get("b") is None:
        v = pick_by_prefix("flange width")
        if v is not None:
            out["b"] = v
    if out.get("tf") is None:
        v = pick_by_prefix("flange thickness")
        if v is not None:
            out["tf"] = v
    if out.get("tw") is None:
        v = pick_by_prefix("web thickness")
        if v is not None:
            out["tw"] = v
    if out.get("k") is None:
        v = pick_by_prefix("distance k")
        if v is not None:
            out["k"] = v

    return out


def _load_csv(path: Path) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    out: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for rec in reader:
            rec2 = _canonicalize_record(rec)
            des = rec2.get("designation") or rec2.get("Designation") or rec2.get("name")
            if des:
                out[str(des)] = rec2
                order.append(str(des))
    return out, order


@st.cache_data(ttl=60)
def load_shapes() -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    if not DATA_DIR.exists():
        st.error(f"Missing data directory: {DATA_DIR}")
        return {}, []

    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for p in sorted(DATA_DIR.iterdir(), key=lambda x: x.name.lower()):
        if p.suffix.lower() == ".csv":
            data, csv_order = _load_csv(p)
            merged.update(data)
            order.extend(csv_order)

    return merged, order


def get_shape(designation: str) -> Optional[Dict[str, Any]]:
    shapes, _ = load_shapes()
    return shapes.get(designation)


def fnum(x: Any, field_name: str) -> float:
    try:
        return float(x)
    except Exception:
        raise ValueError(f"Field '{field_name}' is not numeric: {x!r}")


def to_kNm_from_Nmm(M_Nmm: float) -> float:
    return M_Nmm * 1e-6


# ----------------------------
# CSA TABLE 2 HELPERS (CLASSIFICATION)
# ----------------------------
def flange_lambda_r(Fy: float) -> float:
    # Class 3 limit for flange outstand in compression (your earlier helper)
    return 170.0 / math.sqrt(Fy)


def web_lambda_r(Fy: float) -> float:
    # Class 2 limit for web in flexure (your earlier helper)
    return 525.0 / math.sqrt(Fy)


# ----------------------------
# CLASS 4 EFFECTIVE SECTION MODULUS (your method)
# ----------------------------
def effective_flange_width(b: float, tf: float, Fy: float) -> float:
    lambda_flange = b / (2.0 * tf)
    lambda_r = flange_lambda_r(Fy)
    if lambda_flange <= lambda_r:
        return b
    be = b * (lambda_r / lambda_flange)
    return min(be, b)


def effective_web_height(h: float, tw: float, Fy: float) -> float:
    lambda_web = h / tw
    lambda_r = web_lambda_r(Fy)
    if lambda_web <= lambda_r:
        return h
    he = h * (lambda_r / lambda_web)
    return min(he, h)


def effective_Ix(b_eff: float, tf: float, h_eff: float, tw: float) -> float:
    Af = b_eff * tf
    y = (h_eff / 2.0) + (tf / 2.0)
    If_local = (b_eff * tf**3) / 12.0
    If_total = 2.0 * (If_local + Af * y**2)
    Iw = (tw * h_eff**3) / 12.0
    return If_total + Iw


def effective_section_modulus(d: float, Ix_eff: float) -> float:
    c = d / 2.0
    return Ix_eff / c


def compute_Se_CSA(d: float, b: float, tf: float, tw: float, Fy: float) -> dict:
    h = d - 2.0 * tf
    b_eff = effective_flange_width(b, tf, Fy)
    h_eff = effective_web_height(h, tw, Fy)
    Ix_eff = effective_Ix(b_eff, tf, h_eff, tw)
    Se = effective_section_modulus(d, Ix_eff)
    return {"b_eff": b_eff, "h_eff": h_eff, "Ix_eff": Ix_eff, "Se": Se}


def Mr_class4(Se: float, Fy: float, phi_b: float = PHI_B) -> float:
    Mr_Nmm = phi_b * Se * Fy
    return Mr_Nmm / 1e6  # kN·m


def compute_se_with_steps(geom: dict, Fy: float) -> dict:
    d = geom["d"]
    b = geom["b"]
    tf = geom["tf"]
    tw = geom["tw"]

    h = d - 2.0 * tf
    lam_f = (b / 2.0) / tf
    lam_w = h / tw

    b_eff = effective_flange_width(b, tf, Fy)
    h_eff = effective_web_height(h, tw, Fy)
    Ix_eff = effective_Ix(b_eff, tf, h_eff, tw)
    Se = effective_section_modulus(d, Ix_eff)

    steps = [
        {"label": "Given geometry (mm)", "text": f"d={d:.1f}, b={b:.1f}, tf={tf:.1f}, tw={tw:.1f}"},
        {"label": "Clear web height", "latex": rf"h = d - 2t_f = {d:.1f} - 2({tf:.1f}) = {h:.1f}\ \mathrm{{mm}}"},
        {
            "label": "Slenderness ratios",
            "latex": rf"\lambda_f = \frac{{b/2}}{{t_f}} = \frac{{{b/2:.1f}}}{{{tf:.1f}}} = {lam_f:.2f},\quad "
                     rf"\lambda_w = \frac{{h}}{{t_w}} = \frac{{{h:.1f}}}{{{tw:.1f}}} = {lam_w:.2f}",
        },
        {"label": "Effective elements (CSA)", "text": f"b_eff = {b_eff:.1f} mm,  h_eff = {h_eff:.1f} mm"},
        {"label": "Effective section properties", "text": f"Ix_eff = {Ix_eff:.3e} mm⁴"},
        {
            "label": "Effective section modulus",
            "latex": rf"S_e = \frac{{I_{{x,eff}}}}{{d/2}} = \frac{{{Ix_eff:.3e}}}{{{d/2:.1f}}} = {Se:.3e}\ \mathrm{{mm^3}}",
        },
    ]

    return {"Se": Se, "Ix_eff": Ix_eff, "b_eff": b_eff, "h_eff": h_eff, "lam_f": lam_f, "lam_w": lam_w, "h": h, "steps": steps}


# ----------------------------
# TABLE 2 CLASSIFICATION (your existing logic)
# ----------------------------
def table2_class_major_axis(shape: Dict[str, Any], Fy: float) -> Dict[str, Any]:
    d = fnum(shape.get("d"), "d")
    b = fnum(shape.get("b"), "b")
    tf = fnum(shape.get("tf"), "tf")
    tw = fnum(shape.get("tw"), "tw")

    hw = d - 2.0 * tf
    if Fy <= 0:
        raise ValueError("Fy must be > 0")

    be = 0.5 * b
    lam_f = be / tf
    lam_w = hw / tw

    r = 1.0 / math.sqrt(Fy)
    f1, f2, f3 = 145 * r, 170 * r, 200 * r
    w1, w2, w3 = 420 * r, 525 * r, 670 * r

    def classify(lam: float, lim1: float, lim2: float, lim3: float) -> int:
        if lam <= lim1:
            return 1
        if lam <= lim2:
            return 2
        if lam <= lim3:
            return 3
        return 4

    class_flange = classify(lam_f, f1, f2, f3)
    class_web = classify(lam_w, w1, w2, w3)
    section_class = max(class_flange, class_web)

    if section_class == class_flange and section_class == class_web:
        governing = "Flange & Web (tie)"
    elif section_class == class_flange:
        governing = "Flange"
    else:
        governing = "Web"

    geom = {"d": d, "b": b, "tf": tf, "tw": tw, "h": d - 2 * tf}

    se_info = None
    if section_class == 4:
        se_info = compute_se_with_steps(geom, Fy)

    return {
        "class_flange": class_flange,
        "class_web": class_web,
        "class_section": section_class,
        "governing": governing,
        "ratios": {"b/2t": round(lam_f, 2), "h/w": round(lam_w, 2)},
        "limits": {
            "flange": {"Class 1": round(f1, 2), "Class 2": round(f2, 2), "Class 3": round(f3, 2)},
            "web": {"Class 1": round(w1, 2), "Class 2": round(w2, 2), "Class 3": round(w3, 2)},
        },
        "geometry_used": geom,
        "se_info": se_info,
    }


def Mr_laterally_supported(shape: Dict[str, Any], Fy: float, class_section: int) -> Dict[str, Any]:
    zx = shape.get("zx")
    sx = shape.get("sx")

    if class_section in (1, 2):
        if zx is None:
            return {"mr_kNm": None, "mode": "Missing Zx data", "error": True}
        Zx = fnum(zx, "Zx") * 1000  # CSV in 10^3 mm^3 -> mm^3
        Mr_Nmm = PHI_B * Zx * Fy
        return {"mr_kNm": round(to_kNm_from_Nmm(Mr_Nmm), 1), "mode": f"Plastic (Zx = {Zx/1000:.0f} × 10³ mm³)", "error": False}

    if class_section == 3:
        if sx is None:
            return {"mr_kNm": None, "mode": "Missing Sx data", "error": True}
        Sx = fnum(sx, "Sx") * 1000
        Mr_Nmm = PHI_B * Sx * Fy
        return {"mr_kNm": round(to_kNm_from_Nmm(Mr_Nmm), 1), "mode": f"Elastic (Sx = {Sx/1000:.0f} × 10³ mm³)", "error": False}

    # Class 4
    d = fnum(shape.get("d"), "d")
    b = fnum(shape.get("b"), "b")
    tf = fnum(shape.get("tf"), "tf")
    tw = fnum(shape.get("tw"), "tw")

    se_result = compute_Se_CSA(d, b, tf, tw, Fy)
    Se = se_result["Se"]
    Mr_kNm = Mr_class4(Se, Fy, PHI_B)

    return {"mr_kNm": round(Mr_kNm, 1), "mode": f"Effective (Se = {Se/1000:.0f} × 10³ mm³)", "error": False, "class4_details": se_result}


# ----------------------------
# CSA S16 CLAUSE 13.4 — SHEAR (ELASTIC, UNSTIFFENED WEB, W-SHAPES)
# ----------------------------
def shear13_4_unstiffened_Wshape_elastic(
    d_mm: float,
    tw_mm: float,
    Fy_MPa: float,
    h_mm: Optional[float] = None,
    tf_mm: Optional[float] = None,
    phi_v: float = PHI_V_DEFAULT,
) -> Dict[str, Any]:
    warnings: List[str] = []
    trace: List[str] = []

    if Fy_MPa <= 0:
        raise ValueError("Fy_MPa must be > 0")
    if d_mm <= 0:
        raise ValueError("d_mm must be > 0")
    if tw_mm <= 0:
        raise ValueError("tw_mm must be > 0")

    if not (isinstance(phi_v, (int, float)) and math.isfinite(phi_v) and phi_v > 0):
        phi_v = PHI_V_DEFAULT

    # clear web depth
    if h_mm is not None and h_mm > 0:
        h = float(h_mm)
        trace.append(f"Given: h = {h:.2f} mm (clear web depth)")
    else:
        if tf_mm is None or tf_mm <= 0:
            raise ValueError("Need either h_mm OR tf_mm to compute h = d - 2tf")
        h = float(d_mm) - 2.0 * float(tf_mm)
        trace.append(f"Computed: h = d - 2tf = {d_mm:.2f} - 2({tf_mm:.2f}) = {h:.2f} mm")

    if h <= 0:
        raise ValueError("Computed/Provided h must be > 0")
    if h > d_mm:
        warnings.append("h_mm > d_mm (unexpected). Check section properties.")

    Aw_mm2 = float(d_mm) * float(tw_mm)
    trace.append(f"Aw = d*tw = {d_mm:.2f}*{tw_mm:.2f} = {Aw_mm2:.2f} mm²")

    lam = h / float(tw_mm)
    trace.append(f"λ = h/tw = {h:.2f}/{tw_mm:.2f} = {lam:.3f}")

    sqrtFy = math.sqrt(float(Fy_MPa))
    lambda1 = 1014.0 / sqrtFy
    lambda2 = 1435.0 / sqrtFy
    trace.append(f"λ1 = 1014/√Fy = {lambda1:.3f}")
    trace.append(f"λ2 = 1435/√Fy = {lambda2:.3f}")

    if lam <= lambda1:
        Fs = 0.66 * float(Fy_MPa)
        branch = "A"
        trace.append(f"Branch A (λ ≤ λ1): Fs = 0.66Fy = {Fs:.2f} MPa")
    elif lam <= lambda2:
        Fs = (670.0 * sqrtFy) / lam
        branch = "B"
        trace.append(f"Branch B (λ1 < λ ≤ λ2): Fs = 670√Fy/λ = {Fs:.2f} MPa")
    else:
        Fs = 961200.0 / (lam * lam)
        branch = "C"
        trace.append(f"Branch C (λ > λ2): Fs = 961200/λ² = {Fs:.2f} MPa")

    Vr_kN = (float(phi_v) * Aw_mm2 * Fs) / 1000.0
    trace.append(f"Vr = φ Aw Fs /1000 = {Vr_kN:.2f} kN")

    warnings.append("Scope: CSA S16 13.4 elastic shear, unstiffened web only (no tension-field action / stiffened web).")
    warnings.append("Aw assumed as d*tw for rolled W-shapes (confirm with your office convention).")

    return {
        "ok": True,
        "scope": "CSA S16 13.4 — elastic shear, unstiffened web, W-shapes",
        "warnings": warnings,
        "trace": trace,
        "d_mm": d_mm,
        "tw_mm": tw_mm,
        "h_mm": h,
        "Aw_mm2": Aw_mm2,
        "lambda_h_over_tw": lam,
        "lambda1": lambda1,
        "lambda2": lambda2,
        "Fy_MPa": Fy_MPa,
        "Fs_MPa": Fs,
        "phi_v": float(phi_v),
        "Vr_kN": Vr_kN,
        "branchUsed": branch,
    }


def shearDemandCheck(Vu_kN: float, Vr_kN: float) -> Dict[str, Any]:
    if not (isinstance(Vu_kN, (int, float)) and math.isfinite(Vu_kN) and Vu_kN >= 0):
        raise ValueError("Vu_kN must be a finite number ≥ 0")
    if not (isinstance(Vr_kN, (int, float)) and math.isfinite(Vr_kN) and Vr_kN > 0):
        raise ValueError("Vr_kN must be a finite number > 0")

    utilization = Vu_kN / Vr_kN
    pass_ok = Vu_kN <= Vr_kN

    return {
        "Vu_kN": Vu_kN,
        "Vr_kN": Vr_kN,
        "utilization": utilization,
        "pass": pass_ok,
        "summary": "PASS (Vu ≤ Vr)" if pass_ok else "FAIL (Vu > Vr)",
    }


# ----------------------------
# DISCLAIMER CONFIG
# ----------------------------
DISCLAIMER_VERSION = "2025-12-25_v1"
APP_TITLE = "CSA S16 Flexure Calculator"

DISCLAIMER_MD = """
### Structural Steel Calculator — Disclaimer & Terms of Use

This application is provided **for simulation, educational, and preliminary verification purposes only**.

The calculations and results generated by this tool are **not intended to be used directly for final design, construction, or permitting**.

All outputs **must be independently checked, verified, and approved** by a qualified professional engineer in accordance with applicable codes, standards, and professional judgment.

The developers and authors:
- Do **not** guarantee the accuracy or completeness of the results
- Assume **no responsibility or liability** for errors, omissions, or misuse
- Are **not responsible** for any calculations that have not been independently verified

This tool does **not** replace formal structural analysis, detailed design, peer review, or professional engineering services.

By clicking **"I Accept"**, you acknowledge that:
- You understand this tool is for simulation and verification only
- You are solely responsible for checking and validating all results
- You will not rely on this tool as the sole basis for engineering decisions
"""

FOOTER_HTML = """
<style>
.footer-disclaimer {
  position: fixed;
  left: 0;
  bottom: 0;
  width: 100%;
  background: rgba(250,250,250,0.95);
  border-top: 1px solid #ddd;
  padding: 8px 14px;
  font-size: 12px;
  color: #444;
  z-index: 9999;
}
.footer-disclaimer b { color: #111; }
.block-container { padding-bottom: 3.5rem; }
</style>
<div class="footer-disclaimer">
  <b>Disclaimer:</b> Results are for simulation/preliminary verification only and must be independently verified by a qualified professional engineer.
</div>
"""


def require_disclaimer_acceptance():
    st.set_page_config(page_title=APP_TITLE, page_icon="🔧", layout="wide")

    if st.session_state.get("disclaimer_version") != DISCLAIMER_VERSION:
        st.session_state["accepted_disclaimer"] = False
        st.session_state["disclaimer_version"] = DISCLAIMER_VERSION

    if not st.session_state.get("accepted_disclaimer", False):
        st.title(APP_TITLE)
        st.warning("⚠️ Beta / Testing Mode")
        st.markdown(DISCLAIMER_MD)

        accept = st.checkbox("I Accept and Understand My Responsibility")
        col1, col2 = st.columns([1, 3])
        with col1:
            enter = st.button("Enter Application", type="primary", disabled=not accept)
        with col2:
            st.caption("You must accept the disclaimer to proceed.")

        if enter and accept:
            st.session_state["accepted_disclaimer"] = True
            st.rerun()

        st.stop()


def render_footer_disclaimer():
    st.markdown(FOOTER_HTML, unsafe_allow_html=True)


# ----------------------------
# STREAMLIT APP
# ----------------------------
require_disclaimer_acceptance()
render_footer_disclaimer()

st.title("CSA S16 Flexure Calculator")
st.markdown("**Laterally Supported W-Section Bending Check per CSA S16**")

# Load shapes
shapes, designations = load_shapes()
if not shapes:
    st.error("No section data found. Please add CSV files to the data/ directory.")
    st.stop()

st.markdown("---")

# Inputs
input_col1, input_col2, input_col3 = st.columns([2, 1, 1])

with input_col1:
    st.markdown("### Choose a W-section")
    search_query = st.text_input("Search sections", placeholder="e.g., W410", label_visibility="collapsed")
    if search_query:
        qq = search_query.lower().strip()
        filtered = [k for k in designations if qq in k.lower()]
    else:
        filtered = designations

    if not filtered:
        st.warning("No sections match your search.")
        st.stop()

    selected_section = st.selectbox("Select section", options=filtered, index=0, label_visibility="collapsed")

with input_col2:
    st.markdown("### Yield Strength")
    Fy = st.number_input(
        "Fy (MPa)",
        min_value=200.0,
        max_value=700.0,
        value=345.0,
        step=5.0,
        help="Typical values: 300 MPa (Grade 300W), 345 MPa (Grade 350W)",
    )

with input_col3:
    st.markdown("### Demand Check")
    check_demand = st.checkbox("Check against Mu")
    Mu = None
    if check_demand:
        Mu = st.number_input("Mu (kN·m)", min_value=0.0, value=100.0, step=10.0)

st.markdown("---")

if selected_section:
    shape = get_shape(selected_section)
    if shape is None:
        st.error(f"Section {selected_section} not found.")
        st.stop()

    try:
        class_info = table2_class_major_axis(shape, float(Fy))
        mr_info = Mr_laterally_supported(shape, float(Fy), class_info["class_section"])
    except Exception as e:
        st.error(f"Calculation error: {e}")
        st.stop()

    # Results
    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"Section: {selected_section}")
        geom = class_info["geometry_used"]
        st.markdown("**Section Properties**")
        section_geometry_display = {
            "Depth (d)": f"{geom['d']:.1f} mm",
            "Flange Width (b)": f"{geom['b']:.1f} mm",
            "Flange Thickness (tf)": f"{geom['tf']:.1f} mm",
            "Web Thickness (tw)": f"{geom['tw']:.1f} mm",
            "Clear Web Height (h = d − 2tf)": f"{(geom['d'] - 2*geom['tf']):.1f} mm",
        }
        section_df = pd.DataFrame.from_dict(section_geometry_display, orient="index", columns=["Value"])
        st.table(section_df)

    with col2:
        st.subheader("Classification Results")
        section_class = class_info["class_section"]
        if section_class == 1:
            class_desc = "Plastic"
        elif section_class == 2:
            class_desc = "Compact"
        elif section_class == 3:
            class_desc = "Non-Compact"
        else:
            class_desc = "Slender"

        st.markdown(
            f"### Section Class: :{'green' if section_class <= 2 else 'orange' if section_class == 3 else 'red'}[**{section_class}**] ({class_desc})"
        )
        st.markdown(f"*Governed by: {class_info['governing']}*")

        st.markdown("**Slenderness Ratios**")
        ratio_data = {
            "Element": ["Flange (b/2t)", "Web (h/w)"],
            "Actual": [class_info["ratios"]["b/2t"], class_info["ratios"]["h/w"]],
            "Class 1 Limit": [class_info["limits"]["flange"]["Class 1"], class_info["limits"]["web"]["Class 1"]],
            "Class 2 Limit": [class_info["limits"]["flange"]["Class 2"], class_info["limits"]["web"]["Class 2"]],
            "Class 3 Limit": [class_info["limits"]["flange"]["Class 3"], class_info["limits"]["web"]["Class 3"]],
            "Element Class": [class_info["class_flange"], class_info["class_web"]],
        }
        st.table(ratio_data)

    st.divider()

    # Moment Resistance
    st.subheader("Moment Resistance (Laterally Supported)")
    if mr_info.get("error"):
        st.warning(mr_info["mode"])
    else:
        mr_col1, mr_col2 = st.columns(2)

        with mr_col1:
            st.metric("Factored Moment Resistance (Mr)", f"{mr_info['mr_kNm']:,.1f} kN·m")
            st.caption(f"Mode: {mr_info['mode']}")
            st.caption(f"φb = {PHI_B}")

        with mr_col2:
            if check_demand and Mu is not None:
                Mr_val = float(mr_info["mr_kNm"])
                ratio = float(Mu) / Mr_val if Mr_val > 0 else float("inf")
                if ratio <= 1.0:
                    st.success(f"✅ **PASS** — Mu/Mr = {ratio:.2f} ≤ 1.0")
                else:
                    st.error(f"❌ **FAIL** — Mu/Mr = {ratio:.2f} > 1.0")
                st.metric("Demand/Capacity Ratio", f"{ratio:.2%}")

    # ----------------------------
    # SHEAR UI (THIS IS THE CORRECT INSERTION POINT)
    # ----------------------------
    st.divider()
    st.subheader("Shear Resistance (CSA S16 Clause 13.4 — Elastic, Unstiffened Web)")

    shear_enable = st.checkbox("Enable Shear Check (13.4)", value=False)
    if shear_enable:
        shear_col1, shear_col2, shear_col3 = st.columns([1, 1, 2])

        with shear_col1:
            phi_v = st.number_input("φv", min_value=0.50, max_value=1.00, value=float(PHI_V_DEFAULT), step=0.05)

        with shear_col2:
            check_Vu = st.checkbox("Check against Vu")
            Vu = None
            if check_Vu:
                Vu = st.number_input("Vu (kN)", min_value=0.0, value=100.0, step=10.0)

        # single source of truth for geometry
        geom2 = class_info["geometry_used"]
        d_val2 = float(geom2["d"])
        tw_val2 = float(geom2["tw"])
        tf_val2 = float(geom2["tf"])
        h_clear2 = d_val2 - 2.0 * tf_val2

        try:
            shear_res = shear13_4_unstiffened_Wshape_elastic(
                d_mm=d_val2,
                tw_mm=tw_val2,
                Fy_MPa=float(Fy),
                h_mm=h_clear2,
                tf_mm=tf_val2,
                phi_v=float(phi_v),
            )

            Vr = float(shear_res["Vr_kN"])
            branch = shear_res["branchUsed"]

            with shear_col3:
                st.metric("Factored Shear Resistance (Vr)", f"{Vr:,.1f} kN")
                st.caption(f"Branch used: {branch}  |  λ = {shear_res['lambda_h_over_tw']:.2f}")
                st.caption(f"Aw = {shear_res['Aw_mm2']:.0f} mm²,  Fs = {shear_res['Fs_MPa']:.1f} MPa")

                if check_Vu and Vu is not None:
                    chk = shearDemandCheck(float(Vu), float(Vr))
                    ratio_v = chk["utilization"]
                    if chk["pass"]:
                        st.success(f"✅ **PASS** — Vu/Vr = {ratio_v:.2f} ≤ 1.0")
                    else:
                        st.error(f"❌ **FAIL** — Vu/Vr = {ratio_v:.2f} > 1.0")

            with st.expander("Shear calculation trace (show steps)", expanded=False):
                for line in shear_res["trace"]:
                    st.write("• " + line)
                if shear_res["warnings"]:
                    st.markdown("**Warnings / scope:**")
                    for w in shear_res["warnings"]:
                        st.write("⚠️ " + w)

        except Exception as e:
            st.error(f"Shear calculation error: {e}")

    # Class 4 derivation
    if class_info["class_section"] == 4:
        with st.expander("Class 4 – Effective Section Modulus (Se) derivation", expanded=False):
            se_info = class_info.get("se_info")
            if not se_info or se_info.get("Se") is None:
                st.warning("Se derivation not available.")
            else:
                for s in se_info["steps"]:
                    st.markdown(f"**{s['label']}**")
                    if "latex" in s:
                        st.latex(s["latex"])
                    if "text" in s:
                        st.write(s["text"])
                    st.divider()

    st.divider()

    # Raw data expander
    with st.expander("Raw Section Data"):
        st.json(shape)