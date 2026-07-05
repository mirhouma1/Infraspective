# app.py
import csv
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from _theme import apply_theme, render_sidebar_logo, render_footer, disclaimer_page
from flexure_diagrams import (
    i_section_stress_svg,
    beam_elevation_svg,
    ltb_curve_svg,
    shear_fs_curve_svg,
)

# ----------------------------
# CONFIG
# ----------------------------
DATA_DIR = Path(__file__).resolve().parent / "data"

WI_SECTION_CSV = DATA_DIR / "CISC 11th Edition (CSA S16-14) - WiSection Tables (Revised).csv"
CLASS_BENDING_CSV = DATA_DIR / "CISC 11th Edition - Class of Sections in Bending.csv"

PHI_B = 0.9
PHI_V_DEFAULT = 0.9

APP_TITLE = "CSA S16 - Beam Flexure Calculator"
DISCLAIMER_VERSION = "2026-01-01_v2"

DISCLAIMER_MD = """
# INSFRASPECTIVE – USER ACCESS AGREEMENT

---

**1. BETA EVALUATION & OPTIMIZATION**

Insfraspective provides this application for testing and optimization purposes. By using the App, you agree to provide technical feedback and usage data to assist in the refinement of the calculation engine.

---

**2. PROFESSIONAL VERIFICATION**

This tool is a calculation aid and does not replace professional engineering judgment. Under the Engineering and Geoscience Professions Act (Alberta), the User is responsible for the independent verification of all outputs.

All results must be validated by a licensed Professional Engineer (P.Eng) prior to any project application.

The User agrees not to rely on any App output for any project purpose unless and until that output has been independently verified.

The User acknowledges that any use of App outputs without independent verification is done entirely at their own risk.

Use of this App does not create an engineer-client relationship between the User and Insfraspective.

---

**3. DATA USAGE**

In exchange for access to the Beta platform, Insfraspective collects technical input parameters and interaction patterns. This data is used exclusively to optimize the software's logic and performance. Personal information is managed in accordance with the Alberta Personal Information Protection Act (PIPA).

---

**4. LIMITATION OF LIABILITY**

This software is provided "AS IS" and is in a Beta state, meaning it may contain errors, incomplete features, or incorrect calculations.

Insfraspective disclaims all warranties regarding the accuracy of the Beta calculations.

The User assumes all risk associated with the use of the App's outputs. Use of this App is entirely at the User's own risk.

To the maximum extent permitted by law, Insfraspective shall not be liable for any direct, indirect, incidental, or consequential damages arising from use of the App.

This limitation of liability applies even if the App fails its essential purpose or is found to be in fundamental breach of contract.

No compensation or damages of any kind are payable for errors, omissions, or inaccuracies in the App or its outputs.

---

**5. INDEMNITY**

The User agrees to indemnify, defend, and hold harmless Insfraspective from any and all claims, demands, losses, or legal fees (including solicitor-client costs) arising from the User's use of, misuse of, or reliance on the App, whether the claim is made by the User or a third party.

---

**6. GOVERNING LAW & JURISDICTION**

This agreement is governed by the laws of the Province of Alberta and the federal laws of Canada applicable therein. Any dispute shall be resolved exclusively in the courts of Calgary, Alberta.

---

**7. SEVERABILITY**

If any provision of this Agreement is found unenforceable, the remaining provisions shall remain in full force and effect.

---

**8. VERIFICATION ACKNOWLEDGMENT**

Before each use of the App, the User shall affirmatively confirm their agreement below.

The User acknowledges that failure to verify does not transfer liability to Insfraspective.

---

*BY USING THIS APP, YOU ACKNOWLEDGE THAT YOU HAVE READ, UNDERSTOOD, AND AGREE TO ALL TERMS ABOVE.*
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
  <b>Insfraspective — Beta Software:</b> All outputs must be independently verified by a licensed P.Eng before any project reliance. Results do not constitute professional engineering advice.
</div>
"""

# ----------------------------
# OPTIONAL IMPORT (stiffened web shear lives in main.py)
# ----------------------------
try:
    from main import stiffened_web_shear_CSA13_4  # type: ignore
except Exception:
    stiffened_web_shear_CSA13_4 = None  # type: ignore


# ----------------------------
# DISCLAIMER GATE
# ----------------------------
def require_disclaimer_acceptance() -> None:
    st.set_page_config(page_title="Beam Flexure — CSA S16", page_icon=":wrench:", layout="wide")

    if st.session_state.get("disclaimer_version") != DISCLAIMER_VERSION:
        st.session_state["accepted_disclaimer"] = False
        st.session_state["disclaimer_version"] = DISCLAIMER_VERSION

    if not st.session_state.get("accepted_disclaimer", False):
        disclaimer_page()
        st.stop()


# ============================================================
# CSV NORMALIZATION (map whatever CSV calls it → Table-2 symbols)
# Table-2 symbols we will use everywhere after loading:
#   designation, d, b, t, w, Zx, Sx, k
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
    # Remove corrupted unicode chars (e.g., ? from mm³ → mm?)
    return "".join(c for c in out if c.isalnum() or c == "_")


# NOTE: This is only for CSV column-name matching.
# It does NOT change the symbols used in calculations/UI.
CANON_SYNONYMS: Dict[str, List[str]] = {
    "designation": ["designation", "Designation", "shape", "section", "name", "w_shape"],

    # Table-2 symbols
    "d": ["d", "D", "depth", "depth_d", "depth_d_mm", "overall_depth"],
    "b": ["b", "B", "bf", "flange_width", "flange_width_b", "flange_width_b_mm"],
    "t": ["t", "T", "tf", "flange_thickness", "flange_thickness_t", "flange_thickness_t_mm"],
    "w": ["w", "W", "tw", "web_thickness", "web_thickness_w", "web_thickness_w_mm"],

    # Section properties (IMPORTANT: include exact CSA headers too)
    # Note: _norm() strips parentheses + non-ascii, so "Iy (10^6 mm?)" → "iy_106_mm"
    "Zx": ["Zx", "zx", "z_x", "plastic_modulus_zx", "plastic_modulus_zx_mm3", "zx_mm3", "zx_103_mm"],
    "Sx": ["Sx", "sx", "s_x", "elastic_modulus_sx", "elastic_modulus_sx_mm3", "sx_mm3", "sx_103_mm"],
    "Ix": ["Ix", "ix", "i_x", "ix_106_mm4", "ix_106_mm"],
    "Zy": ["Zy", "zy", "z_y", "zy_mm3", "zy_103_mm"],
    "Sy": ["Sy", "sy", "s_y", "sy_mm3", "sy_103_mm"],
    "Iy": ["Iy", "iy", "i_y", "iy_106_mm4", "iy_106_mm"],
    "J":  ["J", "j", "torsion_constant_j", "j_103_mm4", "j_103_mm"],
    "Cw": ["Cw", "cw", "c_w", "warping_constant_cw", "cw_109_mm6", "cw_109_mm"],
    "rx": ["rx", "r_x", "radius_of_gyration_rx", "rx_mm"],
    "ry": ["ry", "r_y", "radius_of_gyration_ry", "ry_mm"],
    "k":  ["k", "K", "distance_k", "distance_k_mm", "fillet_distance"],
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

    for sym in ("d", "b", "t", "w"):
        v = _pick(rec, CANON_SYNONYMS[sym])
        if v is not None:
            out[sym] = v

    for sym in ("Zx", "Sx", "Ix", "Zy", "Sy", "Iy", "J", "Cw", "rx", "ry", "k"):
        v = _pick(rec, CANON_SYNONYMS[sym])
        if v is not None:
            try:
                out[sym] = float(str(v).replace(",", "").strip())
            except (ValueError, TypeError):
                out[sym] = v

    return out


def _load_csv(path: Path) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
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


@st.cache_data(ttl=60)
def load_shapes() -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    # 1) Load the WI Section CSV if it exists
    if WI_SECTION_CSV.exists():
        data, csv_order = _load_csv(WI_SECTION_CSV)
        merged.update(data)
        order.extend(csv_order)

    # 2) Load the Class Bending CSV if it exists
    if CLASS_BENDING_CSV.exists():
        data, csv_order = _load_csv(CLASS_BENDING_CSV)
        merged.update(data)
        order.extend(csv_order)

    # 3) Load any additional CSVs inside data/
    if DATA_DIR.exists():
        for p in sorted(DATA_DIR.iterdir(), key=lambda x: x.name.lower()):
            if p.suffix.lower() == ".csv" and p not in (WI_SECTION_CSV, CLASS_BENDING_CSV):
                data, csv_order = _load_csv(p)
                merged.update(data)
                order.extend(csv_order)

    # Remove duplicates while preserving order, then sort ascending (natural)
    seen: set[str] = set()
    order_unique: List[str] = []
    for k in order:
        if k not in seen:
            seen.add(k)
            order_unique.append(k)

    def _nat(s: str):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", s)]

    order_unique.sort(key=_nat)
    # Beam Flexure page uses W-sections only — filter out HSS and other types
    order_unique = [
        k for k in order_unique
        if k.upper().startswith("W") and len(k) > 1 and k[1].isdigit()
    ]
    return merged, order_unique


def get_shape(designation: str) -> Optional[Dict[str, Any]]:
    shapes, _ = load_shapes()
    return shapes.get(designation)


def fnum(x: Any, field_name: str) -> float:
    try:
        return float(x)
    except Exception as e:
        raise ValueError(f"Field '{field_name}' is not numeric: {x!r}") from e


def to_kNm_from_Nmm(M_Nmm: float) -> float:
    return M_Nmm * 1e-6


# ----------------------------
# TABLE 2 LIMIT HELPERS (major-axis W-shape)
# ----------------------------
def class_limits_flange(Fy: float) -> tuple:
    """Returns (Class 1, Class 2, Class 3) limits for flange."""
    r = 1.0 / math.sqrt(Fy)
    return 145*r, 170*r, 200*r


def class_limits_web(Fy: float) -> tuple:
    """Returns (Class 1, Class 2, Class 3) limits for web."""
    r = 1.0 / math.sqrt(Fy)
    return 420*r, 525*r, 670*r


def classify_table2_W_major(shape: Dict[str, Any], Fy: float) -> Dict[str, Any]:
    """Alternative classification function with cleaner output format."""
    d = float(shape["d"]); b = float(shape["b"]); t = float(shape["t"]); w = float(shape["w"])
    h = d - 2*t
    lam_f = (b/2)/t
    lam_w = h/w

    f1, f2, f3 = class_limits_flange(Fy)
    w1, w2, w3 = class_limits_web(Fy)

    def c(lam: float, a: float, b: float, c: float) -> int:
        return 1 if lam <= a else 2 if lam <= b else 3 if lam <= c else 4

    cf = c(lam_f, f1, f2, f3)
    cw = c(lam_w, w1, w2, w3)
    cs = max(cf, cw)
    gov = "Flange & Web (tie)" if (cs == cf == cw) else ("Flange" if cs == cf else "Web")

    return {
        "ratios": {"Flange (b/2t)": lam_f, "Web (h/w)": lam_w},
        "limits": {
            "Flange (b/2t)": {"Class 1": f1, "Class 2": f2, "Class 3": f3},
            "Web (h/w)": {"Class 1": w1, "Class 2": w2, "Class 3": w3},
        },
        "element_class": {"Flange": cf, "Web": cw},
        "section_class": cs,
        "governed_by": gov,
        "h": h
    }


def flange_lambda_r(Fy: float) -> float:
    return 170.0 / math.sqrt(Fy)


def web_lambda_r(Fy: float) -> float:
    return 525.0 / math.sqrt(Fy)


# ----------------------------
# CLASS 4 EFFECTIVE SECTION MODULUS (simple method)
# Uses Table-2 symbols ONLY: d, b, t, w, h
# ----------------------------
def effective_flange_width(b: float, t: float, Fy: float) -> float:
    lam = (b / 2.0) / t  # b/2t
    lam_r = flange_lambda_r(Fy)
    if lam <= lam_r:
        return b
    be = b * (lam_r / lam)
    return min(be, b)


def effective_web_height(h: float, w: float, Fy: float) -> float:
    lam = h / w  # h/w
    lam_r = web_lambda_r(Fy)
    if lam <= lam_r:
        return h
    he = h * (lam_r / lam)
    return min(he, h)


def effective_Ix(b_eff: float, t: float, h_eff: float, w: float) -> float:
    Af = b_eff * t
    y = (h_eff / 2.0) + (t / 2.0)

    If_local = (b_eff * t**3) / 12.0
    If_total = 2.0 * (If_local + Af * y**2)

    Iw = (w * h_eff**3) / 12.0
    return If_total + Iw


def effective_section_modulus(d: float, Ix_eff: float) -> float:
    return Ix_eff / (d / 2.0)


def compute_Se_CSA(d: float, b: float, t: float, w: float, Fy: float) -> Dict[str, Any]:
    h = d - 2.0 * t
    b_eff = effective_flange_width(b, t, Fy)
    h_eff = effective_web_height(h, w, Fy)
    Ix_eff = effective_Ix(b_eff, t, h_eff, w)
    Se = effective_section_modulus(d, Ix_eff)
    return {"h": h, "b_eff": b_eff, "h_eff": h_eff, "Ix_eff": Ix_eff, "Se": Se}


def Mr_class4(Se: float, Fy: float, phi_b: float = PHI_B) -> float:
    Mr_Nmm = phi_b * Se * Fy
    return Mr_Nmm / 1e6  # kN·m


def compute_se_with_steps(geom: Dict[str, float], Fy: float) -> Dict[str, Any]:
    d = float(geom["d"])
    b = float(geom["b"])
    t = float(geom["t"])
    w = float(geom["w"])

    h = d - 2.0 * t
    lam_f = (b / 2.0) / t
    lam_w = h / w

    b_eff = effective_flange_width(b, t, Fy)
    h_eff = effective_web_height(h, w, Fy)
    Ix_eff = effective_Ix(b_eff, t, h_eff, w)
    Se = effective_section_modulus(d, Ix_eff)

    steps = [
        {"label": "Given geometry (mm)", "text": f"d={d:.1f}, b={b:.1f}, t={t:.1f}, w={w:.1f}"},
        {"label": "Clear web height", "latex": rf"h = d - 2t = {d:.1f} - 2({t:.1f}) = {h:.1f}\ \mathrm{{mm}}"},
        {
            "label": "Slenderness ratios",
            "latex": rf"\lambda_f = \frac{{b/2}}{{t}} = \frac{{{b/2:.1f}}}{{{t:.1f}}} = {lam_f:.2f},\quad "
                     rf"\lambda_w = \frac{{h}}{{w}} = \frac{{{h:.1f}}}{{{w:.1f}}} = {lam_w:.2f}",
        },
        {"label": "Effective elements (simple)", "text": f"b_eff = {b_eff:.1f} mm,  h_eff = {h_eff:.1f} mm"},
        {"label": "Effective section properties", "text": f"Ix_eff = {Ix_eff:.3e} mm⁴"},
        {
            "label": "Effective section modulus",
            "latex": rf"S_e = \frac{{I_{{x,eff}}}}{{d/2}} = \frac{{{Ix_eff:.3e}}}{{{d/2:.1f}}} = {Se:.3e}\ \mathrm{{mm^3}}",
        },
    ]

    return {"Se": Se, "Ix_eff": Ix_eff, "b_eff": b_eff, "h_eff": h_eff, "lam_f": lam_f, "lam_w": lam_w, "h": h, "steps": steps}


# ----------------------------
# TABLE 2 CLASSIFICATION (major axis)
# Returns ratio keys EXACTLY as UI expects: "b/2t" and "h/w"
# ----------------------------
def table2_class_major_axis(shape: Dict[str, Any], Fy: float) -> Dict[str, Any]:
    d = fnum(shape.get("d"), "d")
    b = fnum(shape.get("b"), "b")
    t = fnum(shape.get("t"), "t")
    w = fnum(shape.get("w"), "w")

    if Fy <= 0:
        raise ValueError("Fy must be > 0")

    h = d - 2.0 * t

    lam_f = (b / 2.0) / t  # b/2t
    lam_w = h / w          # h/w

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

    geom = {"d": d, "b": b, "t": t, "w": w, "h": h}

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


# ----------------------------
# LATERALLY SUPPORTED FLEXURE Mr
# Uses Zx / Sx exactly (from tables)
# ----------------------------
def Mr_laterally_supported(shape: Dict[str, Any], Fy: float, class_section: int) -> Dict[str, Any]:
    Zx_raw = shape.get("Zx")
    Sx_raw = shape.get("Sx")

    if class_section in (1, 2):
        if Zx_raw is None:
            return {"mr_kNm": None, "mode": "Missing Zx data", "error": True}
        Zx = fnum(Zx_raw, "Zx") * 1000  # (10^3 mm^3) → (mm^3)
        Mr_Nmm = PHI_B * Zx * Fy
        return {
            "mr_kNm": round(to_kNm_from_Nmm(Mr_Nmm), 1),
            "mode": f"Plastic (Zx = {Zx/1000:.0f} × 10³ mm³)",
            "error": False,
        }

    if class_section == 3:
        if Sx_raw is None:
            return {"mr_kNm": None, "mode": "Missing Sx data", "error": True}
        Sx = fnum(Sx_raw, "Sx") * 1000
        Mr_Nmm = PHI_B * Sx * Fy
        return {
            "mr_kNm": round(to_kNm_from_Nmm(Mr_Nmm), 1),
            "mode": f"Elastic (Sx = {Sx/1000:.0f} × 10³ mm³)",
            "error": False,
        }

    # Class 4
    d = fnum(shape.get("d"), "d")
    b = fnum(shape.get("b"), "b")
    t = fnum(shape.get("t"), "t")
    w = fnum(shape.get("w"), "w")

    se_result = compute_Se_CSA(d, b, t, w, Fy)
    Se = se_result["Se"]
    Mr_kNm = Mr_class4(Se, Fy, PHI_B)

    return {
        "mr_kNm": round(Mr_kNm, 1),
        "mode": f"Effective (Se = {Se/1000:.0f} × 10³ mm³)",
        "error": False,
        "class4_details": se_result,
    }


# ============================================================
# SHEAR (CSA S16 Clause 13.4.1.1) — keep Table-2 symbols: h/w
#   Unstiffened: implemented here
#   Stiffened: delegated to main.py stiffened_web_shear_CSA13_4
# ============================================================
def _is_finite_pos(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x)) and float(x) > 0.0


def _fmt(x: float, nd: int = 2) -> str:
    return f"{x:,.{nd}f}"


@dataclass
class TraceLine:
    kind: str      # "text" | "latex"
    content: str
    bullet: bool = True


class TraceBuilder:
    def __init__(self) -> None:
        self.lines: List[TraceLine] = []
        self.warnings: List[str] = []

    def text(self, s: str, bullet: bool = True) -> None:
        self.lines.append(TraceLine(kind="text", content=s, bullet=bullet))

    def latex(self, s: str, bullet: bool = True) -> None:
        self.lines.append(TraceLine(kind="latex", content=s, bullet=bullet))

    def warn(self, s: str) -> None:
        self.warnings.append(s)

    def render(self) -> None:
        for ln in self.lines:
            if ln.kind == "text":
                st.write(("• " if ln.bullet else "") + ln.content)
            else:
                if ln.bullet:
                    st.write("•")
                st.latex(ln.content)

        if self.warnings:
            st.markdown("**Warnings / scope:**")
            for w in self.warnings:
                st.write("⚠️ " + w)


def shear_elastic_unstiffened_13_4_1_1a(
    *,
    Fy_MPa: float,
    h_mm: float,
    w_mm: float,
    phi_v: float = PHI_V_DEFAULT,
    trace: Optional[TraceBuilder] = None,
) -> Dict[str, Any]:
    tb = trace or TraceBuilder()

    if not _is_finite_pos(Fy_MPa):
        raise ValueError("Fy must be > 0")
    if not _is_finite_pos(h_mm):
        raise ValueError("h must be > 0")
    if not _is_finite_pos(w_mm):
        raise ValueError("w must be > 0")

    Fy = float(Fy_MPa)
    h = float(h_mm)
    w = float(w_mm)
    phi = float(phi_v)

    if not (0.0 < phi <= 1.0) or not math.isfinite(phi):
        tb.warn("φv was invalid; defaulted to 0.90")
        phi = 0.90

    Aw = h * w
    lam = h / w  # h/w

    tb.text(f"Aw = h·w = {_fmt(h,2)}×{_fmt(w,2)} = {_fmt(Aw,2)} mm²")
    tb.latex(rf"A_w = h\,w = ({_fmt(h,2)})( {_fmt(w,2)} ) = {_fmt(Aw,2)}\ \mathrm{{mm^2}}")

    tb.text(f"λ = h/w = {_fmt(h,2)}/{_fmt(w,2)} = {_fmt(lam,3)}")
    tb.latex(rf"\lambda = \frac{{h}}{{w}} = \frac{{{_fmt(h,2)}}}{{{_fmt(w,2)}}} = {_fmt(lam,3)}")

    sqrtFy = math.sqrt(Fy)
    lam1 = 1014.0 / sqrtFy
    lam2 = 1435.0 / sqrtFy

    tb.latex(rf"\lambda_1 = \frac{{1014}}{{\sqrt{{F_y}}}} = {_fmt(lam1,3)}")
    tb.latex(rf"\lambda_2 = \frac{{1435}}{{\sqrt{{F_y}}}} = {_fmt(lam2,3)}")

    if lam <= lam1:
        Fs = 0.66 * Fy
        branch = "13.4.1.1(a)(i)"
    elif lam <= lam2:
        Fs = (670.0 * sqrtFy) / lam
        branch = "13.4.1.1(a)(ii)"
    else:
        Fs = 961200.0 / (lam * lam)
        branch = "13.4.1.1(a)(iii)"

    tb.text(f"Branch used: {branch}")
    tb.latex(rf"F_s = {_fmt(Fs,2)}\ \mathrm{{MPa}}")

    Vr_kN = (phi * Aw * Fs) / 1000.0
    tb.latex(rf"V_r = \phi_v A_w F_s = ({phi:.2f})({_fmt(Aw,0)})({_fmt(Fs,2)})/1000 = {_fmt(Vr_kN,2)}\ \mathrm{{kN}}")

    return {
        "ok": True,
        "branchUsed": branch,
        "Aw_mm2": Aw,
        "lambda_h_over_w": lam,
        "Fs_MPa": Fs,
        "Vr_kN": Vr_kN,
        "phi_v": phi,
        "trace": tb,
        "warnings": tb.warnings,
    }


def shear_demand_check(Vu_kN: float, Vr_kN: float) -> Dict[str, Any]:
    Vu = float(Vu_kN)
    Vr = float(Vr_kN)
    if not (Vu >= 0 and math.isfinite(Vu)):
        raise ValueError("Vu must be ≥ 0")
    if not (Vr > 0 and math.isfinite(Vr)):
        raise ValueError("Vr must be > 0")
    util = Vu / Vr
    return {"utilization": util, "pass": Vu <= Vr}


# ============================================================
# LATERAL TORSIONAL BUCKLING (LTB) — CSA S16 13.6
# ============================================================
E_MPA_DEFAULT = 200000.0  # MPa = N/mm²

def omega2_from_case(case: str) -> float:
    """ω2 moment gradient factor for common loading cases."""
    m = {
        "uniform_moment": 1.00,
        "midspan_point": 1.13,
        "udl": 1.30,
        "triangular": 1.40,
        "cantilever_point": 1.00,
    }
    return float(m.get(case, 1.00))

OMEGA2_CASES = [
    ("uniform_moment", "Uniform moment (ω₂ = 1.00)"),
    ("midspan_point", "Midspan point load (ω₂ = 1.13)"),
    ("udl", "UDL (ω₂ = 1.30)"),
    ("triangular", "Triangular moment (ω₂ = 1.40)"),
    ("cantilever_point", "Cantilever point load (ω₂ = 1.00)"),
]

# ── Additional ω₂ formulas (CSA S16 Cl. 13.6 Eq. 2 & Eq. 3) ──────────────────
G_MPA_DEFAULT = 77000.0  # shear modulus of steel (MPa)


def omega2_general(M_max: float, M_a: float, M_b: float, M_c: float) -> float:
    """4-point ω₂ for any moment distribution (Cl. 13.6, Eq. 2):
       ω₂ = 4·M_max / sqrt(M_max² + 4·M_a² + 7·M_b² + 4·M_c²) ≤ 2.5
       Moments are absolute values at L/4 (M_a), L/2 (M_b), 3L/4 (M_c)."""
    Mm = abs(M_max); Ma = abs(M_a); Mb = abs(M_b); Mc = abs(M_c)
    denom = math.sqrt(Mm * Mm + 4.0 * Ma * Ma + 7.0 * Mb * Mb + 4.0 * Mc * Mc)
    if denom <= 0:
        return 1.0
    return min(4.0 * Mm / denom, 2.5)


def omega2_linear(kappa: float) -> float:
    """Linear-gradient ω₂ (Cl. 13.6, Eq. 3):
       ω₂ = 1.75 + 1.05·κ + 0.3·κ²  ≤ 2.5
       κ = ratio of smaller to larger end moment (+ double curvature, − single curvature)."""
    k = max(-1.0, min(1.0, float(kappa)))
    return min(1.75 + 1.05 * k + 0.3 * k * k, 2.5)


def critical_elastic_moment_kNm(L_mm: float, Iy_mm4: float, J_mm4: float,
                                Cw_mm6: float, omega2: float,
                                E_MPa: float = E_MPA_DEFAULT,
                                G_MPa: float = G_MPA_DEFAULT) -> float:
    """Critical elastic LTB moment Mu (Cl. 13.6, Eq. 1) in kN·m."""
    if L_mm <= 0:
        return 0.0
    term1 = E_MPa * Iy_mm4 * G_MPa * J_mm4
    term2 = (math.pi * E_MPa / L_mm) ** 2 * Iy_mm4 * Cw_mm6
    Mu_Nmm = (omega2 * math.pi / L_mm) * math.sqrt(max(term1 + term2, 0.0))
    return Mu_Nmm / 1e6


# ── CSA S16 Table D.1 — Serviceability deflection limits ─────────────────────
TABLE_D1_LIMITS = [
    ("custom",                       "Custom L / n  (use selector below)",                  None),
    ("industrial_floor",             "Industrial — floor",                                  300),
    ("industrial_inelastic_roof",    "Industrial — inelastic roof",                         240),
    ("industrial_elastic_roof",      "Industrial — elastic roof",                           180),
    ("crane_girder_heavy",           "Crane girder ≥ 225 kN  (L/800)",                      800),
    ("crane_girder_light",           "Crane girder < 225 kN  (L/600)",                      600),
    ("crane_lateral",                "Crane runway — lateral  (L/600)",                     600),
    ("other_floor_crack_susceptible","Other — floors, crack-susceptible finish (L/360)",   360),
    ("other_floor_no_crack",         "Other — floors, not susceptible (L/300)",             300),
    ("wind_drift_building",          "Wind drift — building  (h/400)",                      400),
    ("storey_drift_cladding",        "Storey drift — cladding  (h/500)",                    500),
]


def residual_stress_factor(section_class: int, Fy: float, Lb_mm: float, rts_mm: float) -> float:
    """Residual stress / inelastic transition factor in (0,1]."""
    if rts_mm <= 0:
        return 1.0
    lam = (Lb_mm / rts_mm) * math.sqrt(max(Fy, 1.0) / 350.0)

    if section_class in (1, 2):
        if lam <= 60:
            return 1.0
        return max(0.75, 1.0 - 0.003 * (lam - 60))
    if section_class == 3:
        if lam <= 50:
            return 0.95
        return max(0.65, 0.95 - 0.004 * (lam - 50))
    return 0.60


def Mr_LTB_core(
    shape: Dict[str, Any],
    Fy: float,
    section_class: int,
    Lb_mm: float,
    omega2: float,
    phi_b: float = PHI_B,
) -> Dict[str, Any]:
    """
    LTB core calculation:
    - Uses Zx or Sx (or Se for Class 4) as base moment
    - Applies length-dependent elastic cap using Ix
    - Applies ω2 + residual stress factor
    """
    tr = TraceBuilder()

    if Fy <= 0 or Lb_mm <= 0 or omega2 <= 0:
        return {"ok": False, "error": "Fy, Lb, ω2 must be > 0", "trace": tr}

    Zx_raw = shape.get("Zx")
    Sx_raw = shape.get("Sx")
    Ix_raw = shape.get("Ix")

    if section_class in (1, 2):
        if Zx_raw is None:
            return {"ok": False, "error": "Missing Zx for Class 1/2", "trace": tr}
        Zx = float(Zx_raw) * 1000.0
        Mbase = Zx * Fy
        tr.text(f"Base: Mp = Zx×Fy = {Zx/1000:.0f}×10³ × {Fy:.1f} MPa")
    elif section_class == 3:
        if Sx_raw is None:
            return {"ok": False, "error": "Missing Sx for Class 3", "trace": tr}
        Sx = float(Sx_raw) * 1000.0
        Mbase = Sx * Fy
        tr.text(f"Base: My = Sx×Fy = {Sx/1000:.0f}×10³ × {Fy:.1f} MPa")
    else:
        d = fnum(shape.get("d"), "d")
        b = fnum(shape.get("b"), "b")
        t = fnum(shape.get("t"), "t")
        w = fnum(shape.get("w"), "w")
        se_result = compute_Se_CSA(d, b, t, w, Fy)
        Se = se_result["Se"]
        Mbase = Se * Fy
        tr.text(f"Base (Class 4): Me = Se×Fy = {Se/1000:.0f}×10³ × {Fy:.1f} MPa")

    if Ix_raw is None:
        Mcap = float("inf")
        tr.warn("Ix missing → no Lb-dependent cap applied.")
        rts = 0.0
    else:
        Ix = float(Ix_raw) * 1e6
        A_raw = shape.get("Area") or shape.get("area")
        if A_raw is None:
            A = 1.0
            tr.warn("Area missing → rts proxy is rough.")
        else:
            A = float(A_raw)

        rx = math.sqrt(max(Ix / max(A, 1e-6), 1e-6))
        rts = rx

        E = E_MPA_DEFAULT
        Mcap = (math.pi**2) * E * Ix / (Lb_mm**2)
        tr.text(f"Cap proxy: Mcap = π²EI/Lb² = {Mcap/1e6:.1f} kN·m")

    k_rs = residual_stress_factor(section_class, Fy, Lb_mm, max(rts, 1e-6))
    k_om = min(max(omega2, 0.4), 2.0)

    tr.text(f"k_rs = {k_rs:.3f}, ω2 = {omega2:.3f} (used {k_om:.3f})")

    Mnom = min(Mbase, Mcap) * k_rs * k_om
    Mr = phi_b * Mnom
    Mr_kNm = Mr / 1e6

    return {
        "ok": True,
        "Mr_kNm": Mr_kNm,
        "phi_b": phi_b,
        "k_rs": k_rs,
        "omega2_used": k_om,
        "trace": tr,
    }


# ============================================================
# DEFLECTION CALCULATIONS (Simply Supported Beams)
# ============================================================
def defl_ss_udl_mm(w_kN_per_m: float, L_m: float, E_MPa: float, Ix_10e6_mm4: float) -> float:
    """δmax = 5 w L^4 / (384 E I) for simply supported beam with UDL."""
    w_N_per_mm = (w_kN_per_m * 1000.0) / 1000.0  # kN/m -> N/mm
    L_mm = L_m * 1000.0
    I = Ix_10e6_mm4 * 1e6
    return (5.0 * w_N_per_mm * (L_mm**4)) / (384.0 * E_MPa * I)


def defl_ss_midspan_point_mm(P_kN: float, L_m: float, E_MPa: float, Ix_10e6_mm4: float) -> float:
    """δmax = P L^3 / (48 E I) for simply supported beam with midspan point load."""
    P_N = P_kN * 1000.0
    L_mm = L_m * 1000.0
    I = Ix_10e6_mm4 * 1e6
    return (P_N * (L_mm**3)) / (48.0 * E_MPa * I)


DEFLECTION_CASES = [
    ("udl", "UDL (w kN/m)"),
    ("midspan_point", "Midspan Point Load (P kN)"),
]


# ----------------------------
# STREAMLIT APP
# ----------------------------
require_disclaimer_acceptance()
apply_theme()
render_sidebar_logo()
render_footer()

st.title(APP_TITLE)

shapes, designations = load_shapes()
if not shapes:
    st.error("No section data found. Add CSV files to the data/ folder.")
    st.stop()

st.markdown("---")

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
    Fy = st.number_input("Fy (MPa)", min_value=200.0, max_value=700.0, value=345.0, step=5.0)

with input_col3:
    st.markdown("### Demand Check")
    check_demand = st.checkbox("Check against Mu")
    Mu = st.number_input("Mu (kN·m)", min_value=0.0, value=100.0, step=10.0) if check_demand else None

st.markdown("---")

if selected_section:
    shape = get_shape(selected_section)
    if shape is None:
        st.error(f"Section {selected_section} not found.")
        st.stop()

    # ── Raw CSV record (mirrors Compression page's "Raw CSV Record" tab) ──
    with st.expander(f"🗃️ Raw CSV record — {selected_section}", expanded=False):
        st.caption("All properties for this section as loaded from the CISC W-section table. "
                   "Canonical keys (Zx, Sx, Ix, Iy, J, Cw, Sy, Zy, rx, ry, k, d, b, t, w) are "
                   "what the calculation engine consumes; remaining keys are the original CSV headers.")
        _canonical_keys = ("designation", "d", "b", "t", "w", "k",
                           "Ix", "Sx", "Zx", "rx", "Iy", "Sy", "Zy", "ry", "J", "Cw")
        _canon_rows = [(k, shape.get(k)) for k in _canonical_keys if shape.get(k) is not None]
        if _canon_rows:
            st.markdown("**Canonical properties (used by calculations)**")
            st.table(pd.DataFrame(_canon_rows, columns=["Property", "Value"]).set_index("Property"))
        _raw_rows = [(k, v) for k, v in shape.items() if k not in _canonical_keys]
        if _raw_rows:
            st.markdown("**All other CSV columns**")
            st.table(pd.DataFrame(_raw_rows, columns=["CSV Column", "Value"]).set_index("CSV Column"))
        if st.checkbox("Show full record as JSON", value=False, key="raw_json_toggle"):
            st.json(shape)

    try:
        class_info = table2_class_major_axis(shape, float(Fy))
        mr_info = Mr_laterally_supported(shape, float(Fy), class_info["class_section"])
    except Exception as e:
        st.error(f"Calculation error: {e}")
        st.stop()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"Section: {selected_section}")
        geom = class_info["geometry_used"]

        st.markdown("**Section Properties**")
        section_geometry_display = {
            "Depth (d)": f"{geom['d']:.1f} mm",
            "Flange Width (b)": f"{geom['b']:.1f} mm",
            "Flange Thickness (t)": f"{geom['t']:.1f} mm",
            "Web Thickness (w)": f"{geom['w']:.1f} mm",
            "Clear Web Height (h = d − 2t)": f"{geom['h']:.1f} mm",
        }
        st.table(pd.DataFrame.from_dict(section_geometry_display, orient="index", columns=["Value"]))

    with col2:
        st.subheader("Classification Results")
        section_class = class_info["class_section"]
        class_desc = {1: "Plastic", 2: "Compact", 3: "Non-Compact", 4: "Slender"}[section_class]

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

        # ── Cross-section diagram with stress block overlay (Class 1/2 plastic, 3/4 elastic) ──
        st.markdown("**Cross-Section & Stress Distribution**")
        st.markdown(
            i_section_stress_svg(int(class_info["class_section"]), mode="stress"),
            unsafe_allow_html=True,
        )

    st.divider()

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

    st.divider()

    # ----------------------------
    # SHEAR RESISTANCE (ALWAYS VISIBLE)
    # ----------------------------
    st.subheader("Shear Resistance (CSA S16 Clause 13.4.1.1 — Elastic Shear)")

    shear_enable = st.checkbox("Enable Shear Check (13.4.1.1)", value=False)
    if shear_enable:
        web_type = st.radio(
            "Web type (13.4.1.1)",
            ["Unstiffened web (13.4.1.1(a))", "Stiffened web (13.4.1.1(b))"],
            index=0,
            horizontal=True,
        )

        shear_col1, shear_col2, shear_col3 = st.columns([1, 1, 2])

        with shear_col1:
            phi_v = st.number_input("φv", min_value=0.50, max_value=1.00, value=float(PHI_V_DEFAULT), step=0.05)

        with shear_col2:
            check_Vu = st.checkbox("Check against Vu")
            Vu_shear = st.number_input("Vu (kN)", min_value=0.0, value=100.0, step=10.0) if check_Vu else None

        h = float(class_info["geometry_used"]["h"])
        w = float(class_info["geometry_used"]["w"])
        Aw = h * w

        a_mm = None
        if web_type.startswith("Stiffened"):
            with shear_col2:
                a_mm = st.number_input("Stiffener spacing a (mm)", min_value=1.0, value=800.0, step=50.0)

        try:
            tb = TraceBuilder()

            if web_type.startswith("Unstiffened"):
                shear_res = shear_elastic_unstiffened_13_4_1_1a(
                    Fy_MPa=float(Fy),
                    h_mm=h,
                    w_mm=w,
                    phi_v=float(phi_v),
                    trace=tb,
                )
                Vr_kN = float(shear_res["Vr_kN"])
                Fs_MPa = float(shear_res["Fs_MPa"])
                lam = float(shear_res["lambda_h_over_w"])
                branch = shear_res["branchUsed"]
                warnings = shear_res.get("warnings", [])

            else:
                if stiffened_web_shear_CSA13_4 is None:
                    raise ValueError("Stiffened web function not available (main.py missing stiffened_web_shear_CSA13_4).")

                if a_mm is None:
                    raise ValueError("Stiffener spacing a is required for stiffened web (13.4.1.1(b)).")

                h_over_w = h / w
                a_over_h = float(a_mm) / h

                res = stiffened_web_shear_CSA13_4(
                    Fy_MPa=float(Fy),
                    hw_over_tw=h_over_w,
                    a_over_h=a_over_h,
                    Aw_mm2=Aw,
                    phi_v=float(phi_v),
                    h_mm=h,
                    tw_mm=w,
                    a_mm=float(a_mm),
                )

                Vr_kN = float(res["Vr_kN"])
                Fs_MPa = float(res["Fs_MPa"])
                lam = h_over_w
                branch = f"13.4.1.1(b) {res.get('region','')}".strip()
                warnings = res.get("warnings", [])
                for wmsg in warnings:
                    tb.warn(str(wmsg))

                for item in res.get("trace", []):
                    s = str(item).strip()
                    if s.startswith("$$") and s.endswith("$$"):
                        tb.latex(s[2:-2].strip())
                    else:
                        tb.text(s)

            with shear_col3:
                st.metric("Factored Shear Resistance (Vr)", f"{Vr_kN:,.1f} kN")
                st.caption(f"Case: {web_type}  |  Branch used: {branch}  |  λ = {lam:.2f}")
                st.caption(f"Aw = {Aw:.0f} mm²,  Fs = {Fs_MPa:.1f} MPa,  φv = {float(phi_v):.2f}")

                if check_Vu and Vu_shear is not None:
                    chk = shear_demand_check(float(Vu_shear), float(Vr_kN))
                    ratio_v = chk["utilization"]
                    if chk["pass"]:
                        st.success(f"✅ **PASS** — Vu/Vr = {ratio_v:.2f} ≤ 1.0")
                    else:
                        st.error(f"❌ **FAIL** — Vu/Vr = {ratio_v:.2f} > 1.0")

            with st.expander("Shear calculation trace (show steps)", expanded=False):
                tb.render()

            # ── Shear curve: Fs vs h/w with operating point ────────────────
            with st.expander("Shear curve diagram — Fs vs h/w", expanded=False):
                _kv_for_plot = None
                if web_type.startswith("Stiffened") and a_mm is not None and h > 0:
                    _aspect = float(a_mm) / float(h)
                    _kv_for_plot = (4.0 + 5.34 / _aspect**2) if _aspect < 1.0 else (5.34 + 4.0 / _aspect**2)
                st.markdown(
                    shear_fs_curve_svg(
                        Fy=float(Fy),
                        h_over_w_actual=float(h) / float(w) if w > 0 else 0.0,
                        Fs_actual=float(Fs_MPa),
                        stiffened=web_type.startswith("Stiffened"),
                        kv=_kv_for_plot,
                    ),
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Curve traces CSA S16 Cl. 13.4.1.1 branches (yield plateau \u2192 inelastic "
                    "buckling \u2192 elastic buckling). Red dot = current section operating point."
                )

        except Exception as e:
            st.error(f"Shear calculation error: {e}")

    st.divider()

    # ----------------------------
    # LATERAL TORSIONAL BUCKLING (LTB)
    # ----------------------------
    st.subheader("Lateral Torsional Buckling (CSA S16 13.6)")

    ltb_enable = st.checkbox("Enable LTB Check", value=False)
    if ltb_enable:
        ltb_col1, ltb_col2, ltb_col3 = st.columns([1, 1, 2])

        with ltb_col1:
            Lb_m = st.number_input("Unbraced length Lb (m)", min_value=0.1, value=3.0, step=0.5)
            Lb_mm = Lb_m * 1000.0

        with ltb_col2:
            omega2_case = st.selectbox(
                "Loading case (ω₂)",
                options=[c[0] for c in OMEGA2_CASES],
                format_func=lambda x: dict(OMEGA2_CASES)[x],
                index=0,
            )
            omega2 = omega2_from_case(omega2_case)

        try:
            ltb_res = Mr_LTB_core(
                shape=shape,
                Fy=float(Fy),
                section_class=class_info["class_section"],
                Lb_mm=Lb_mm,
                omega2=omega2,
            )

            with ltb_col3:
                if ltb_res["ok"]:
                    st.metric("LTB Moment Resistance (Mr,LTB)", f"{ltb_res['Mr_kNm']:,.1f} kN·m")
                    st.caption(f"φb = {ltb_res['phi_b']}, k_rs = {ltb_res['k_rs']:.3f}, ω₂ = {ltb_res['omega2_used']:.2f}")

                    # Compare with laterally supported
                    Mr_lat = mr_info.get("mr_kNm")
                    if Mr_lat and not mr_info.get("error"):
                        if ltb_res['Mr_kNm'] < Mr_lat:
                            st.warning(f"LTB governs: {ltb_res['Mr_kNm']:.1f} < {Mr_lat:.1f} kN·m (laterally supported)")
                        else:
                            st.info(f"Laterally supported governs: {Mr_lat:.1f} ≤ {ltb_res['Mr_kNm']:.1f} kN·m")
                else:
                    st.warning(f"LTB error: {ltb_res.get('error', 'Unknown error')}")

            with st.expander("LTB calculation trace (show steps)", expanded=False):
                if ltb_res.get("trace"):
                    ltb_res["trace"].render()

            # ── Beam elevation diagram (with brace marks + moment shape) ──
            st.markdown("**Beam Elevation Diagram**")
            _ltb_load_type = "udl" if omega2_case in ("udl", "triangular") else (
                "point" if omega2_case == "midspan_point" else "udl"
            )
            st.markdown(
                beam_elevation_svg(braced=False, load_type=_ltb_load_type),
                unsafe_allow_html=True,
            )

            # ── Mr vs Lb curve ─────────────────────────────────────────────
            try:
                _Iy_raw = shape.get("Iy"); _J_raw = shape.get("J"); _Cw_raw = shape.get("Cw")
                _Zx_raw = shape.get("Zx"); _Sx_raw = shape.get("Sx")
                if all(x is not None for x in (_Iy_raw, _J_raw, _Cw_raw, _Zx_raw, _Sx_raw)):
                    _Iy = float(_Iy_raw) * 1e6
                    _J  = float(_J_raw)  * 1e3
                    _Cw = float(_Cw_raw) * 1e9
                    _Zx = float(_Zx_raw) * 1e3
                    _Sx = float(_Sx_raw) * 1e3
                    _cls = int(class_info["class_section"])
                    _Mp_kNm = _Zx * float(Fy) / 1e6
                    _My_kNm = _Sx * float(Fy) / 1e6
                    _Mref = _Mp_kNm if _cls <= 2 else _My_kNm

                    _L_pts: List[float] = []
                    _Mr_pts: List[float] = []
                    _L_step = 250.0
                    _Lmax_plot = max(15000.0, Lb_mm * 1.5)
                    _Li = 500.0
                    while _Li <= _Lmax_plot:
                        _Mu_i = critical_elastic_moment_kNm(_Li, _Iy, _J, _Cw, omega2)
                        if _Mu_i > 0.67 * _Mref:
                            _Mr_i = min(1.15 * PHI_B * _Mref * (1.0 - 0.28 * _Mref / _Mu_i),
                                        PHI_B * _Mref)
                        else:
                            _Mr_i = PHI_B * _Mu_i
                        _L_pts.append(_Li); _Mr_pts.append(_Mr_i)
                        _Li += _L_step

                    _Mu_now = critical_elastic_moment_kNm(Lb_mm, _Iy, _J, _Cw, omega2)
                    if _Mu_now > 0.67 * _Mref:
                        _Mr_now = min(1.15 * PHI_B * _Mref * (1.0 - 0.28 * _Mref / _Mu_now),
                                      PHI_B * _Mref)
                    else:
                        _Mr_now = PHI_B * _Mu_now

                    st.markdown("**Mr vs Unbraced Length Lb  (CSA S16 Cl. 13.6 textbook curve)**")
                    st.markdown(
                        ltb_curve_svg(
                            L_list=_L_pts, Mr_list=_Mr_pts,
                            phiMp=PHI_B * _Mp_kNm, phiMy=PHI_B * _My_kNm,
                            section_class=_cls,
                            L_current_mm=Lb_mm, Mr_current=_Mr_now,
                        ),
                        unsafe_allow_html=True,
                    )
                    st.caption(f"Mu (current) = {_Mu_now:,.1f} kN·m  |  "
                               f"Mr (curve, current) = {_Mr_now:,.1f} kN·m  |  "
                               f"ω₂ = {omega2:.2f}")
                else:
                    st.info("Mr-vs-Lb curve unavailable — Iy, J, Cw, Zx or Sx missing for this section.")
            except Exception as _e:
                st.info(f"Mr-vs-Lb curve unavailable: {_e}")

            # ── Advanced ω₂ formulas (Cl. 13.6 Eq. 2 & Eq. 3) ──────────────
            with st.expander("Advanced ω₂ — general 4-point or linear-gradient formula", expanded=False):
                _adv_mode = st.radio(
                    "ω₂ formula",
                    ["Preset case (above)",
                     "Linear gradient — Eq. 3:  ω₂ = 1.75 + 1.05κ + 0.3κ²",
                     "General 4-point — Eq. 2:  ω₂ = 4·M_max / √(M²_max + 4M²_a + 7M²_b + 4M²_c)"],
                    index=0,
                    horizontal=False,
                    key="adv_omega2_mode",
                )
                _omega2_alt = None
                if _adv_mode.startswith("Linear"):
                    _kappa = st.slider(
                        "κ = M_small / M_large  (+ double curvature, − single curvature)",
                        min_value=-1.0, max_value=1.0, value=0.0, step=0.05, key="kappa_input",
                    )
                    _omega2_alt = omega2_linear(_kappa)
                    st.latex(r"\omega_2 = 1.75 + 1.05\,\kappa + 0.3\,\kappa^2 \le 2.5")
                    st.write(f"κ = {_kappa:.2f}  →  ω₂ = {_omega2_alt:.3f}")
                elif _adv_mode.startswith("General"):
                    _c1, _c2, _c3, _c4 = st.columns(4)
                    with _c1:
                        _Mmax = st.number_input("M_max", min_value=0.0, value=100.0, step=10.0, key="Mmax_in")
                    with _c2:
                        _Ma   = st.number_input("M_a (¼·L)", min_value=0.0, value=50.0, step=10.0, key="Ma_in")
                    with _c3:
                        _Mb   = st.number_input("M_b (½·L)", min_value=0.0, value=80.0, step=10.0, key="Mb_in")
                    with _c4:
                        _Mc   = st.number_input("M_c (¾·L)", min_value=0.0, value=50.0, step=10.0, key="Mc_in")
                    _omega2_alt = omega2_general(_Mmax, _Ma, _Mb, _Mc)
                    st.latex(r"\omega_2 = \frac{4\,M_{max}}{\sqrt{M_{max}^2 + 4M_a^2 + 7M_b^2 + 4M_c^2}} \le 2.5")
                    st.write(f"ω₂ = {_omega2_alt:.3f}")

                if _omega2_alt is not None:
                    try:
                        _Iy_raw = shape.get("Iy"); _J_raw = shape.get("J"); _Cw_raw = shape.get("Cw")
                        _Zx_raw = shape.get("Zx"); _Sx_raw = shape.get("Sx")
                        if all(x is not None for x in (_Iy_raw, _J_raw, _Cw_raw, _Zx_raw, _Sx_raw)):
                            _Iy = float(_Iy_raw) * 1e6
                            _J  = float(_J_raw)  * 1e3
                            _Cw = float(_Cw_raw) * 1e9
                            _Zx = float(_Zx_raw) * 1e3
                            _Sx = float(_Sx_raw) * 1e3
                            _cls = int(class_info["class_section"])
                            _Mp = _Zx * float(Fy) / 1e6
                            _My = _Sx * float(Fy) / 1e6
                            _Mu_alt = critical_elastic_moment_kNm(Lb_mm, _Iy, _J, _Cw, _omega2_alt)
                            _Mref = _Mp if _cls <= 2 else _My
                            if _Mu_alt > 0.67 * _Mref:
                                _Mr_alt = min(1.15 * PHI_B * _Mref * (1.0 - 0.28 * _Mref / _Mu_alt),
                                              PHI_B * _Mref)
                                _branch = "Inelastic LTB:  Mr = 1.15·φ·M_ref·(1 − 0.28·M_ref/Mu) ≤ φ·M_ref"
                            else:
                                _Mr_alt = PHI_B * _Mu_alt
                                _branch = "Elastic LTB:  Mr = φ·Mu"
                            st.write(f"**Mu (Cl. 13.6 Eq. 1)** = {_Mu_alt:,.1f} kN·m")
                            st.write(f"**Mr (Cl. 13.6)** = {_Mr_alt:,.1f} kN·m   _({_branch})_")
                            if ltb_res.get("ok"):
                                _delta = _Mr_alt - float(ltb_res["Mr_kNm"])
                                st.caption(f"Difference vs preset-ω₂ result above: "
                                           f"{_delta:+,.1f} kN·m "
                                           f"({100.0*_delta/max(float(ltb_res['Mr_kNm']),1e-6):+.1f}%)")
                        else:
                            st.info("Iy / J / Cw / Zx / Sx missing — alternate Mr cannot be computed.")
                    except Exception as _e2:
                        st.info(f"Alt-ω₂ Mr unavailable: {_e2}")

        except Exception as e:
            st.error(f"LTB calculation error: {e}")

    st.divider()

    # ----------------------------
    # DEFLECTION CHECK
    # ----------------------------
    st.subheader("Deflection Check (Simply Supported)")

    defl_enable = st.checkbox("Enable Deflection Check", value=False)
    if defl_enable:
        Ix_raw = shape.get("Ix")
        if Ix_raw is None:
            st.warning("Missing Ix data for deflection calculation.")
        else:
            Ix_val = float(Ix_raw)  # Already in 10^6 mm^4

            defl_col1, defl_col2, defl_col3 = st.columns([1, 1, 2])

            with defl_col1:
                defl_case = st.selectbox(
                    "Loading case",
                    options=[c[0] for c in DEFLECTION_CASES],
                    format_func=lambda x: dict(DEFLECTION_CASES)[x],
                    index=0,
                )
                L_defl = st.number_input("Span L (m)", min_value=0.5, value=6.0, step=0.5)

            with defl_col2:
                if defl_case == "udl":
                    w_load = st.number_input("w (kN/m)", min_value=0.1, value=10.0, step=1.0)
                else:
                    P_load = st.number_input("P (kN)", min_value=0.1, value=50.0, step=5.0)

                _td1_key = st.selectbox(
                    "Deflection limit  (CSA S16 Table D.1)",
                    options=[k for k, _, _ in TABLE_D1_LIMITS],
                    format_func=lambda k: dict((kk, ll) for kk, ll, _ in TABLE_D1_LIMITS)[k],
                    index=0,
                )
                _td1_div = dict((kk, dv) for kk, _, dv in TABLE_D1_LIMITS).get(_td1_key)
                if _td1_div is None:
                    defl_limit_ratio = st.selectbox(
                        "Custom L / n",
                        options=[180, 240, 360, 480],
                        format_func=lambda x: f"L/{x}",
                        index=1,
                    )
                else:
                    defl_limit_ratio = _td1_div
                    st.caption(f"Using Table D.1 limit: L / {_td1_div}")

            try:
                E = E_MPA_DEFAULT

                if defl_case == "udl":
                    delta_mm = defl_ss_udl_mm(w_load, L_defl, E, Ix_val)
                    load_desc = f"w = {w_load:.1f} kN/m"
                else:
                    delta_mm = defl_ss_midspan_point_mm(P_load, L_defl, E, Ix_val)
                    load_desc = f"P = {P_load:.1f} kN"

                L_mm = L_defl * 1000.0
                delta_limit = L_mm / defl_limit_ratio
                ratio = delta_mm / delta_limit if delta_limit > 0 else float("inf")

                with defl_col3:
                    st.metric("Maximum Deflection (δmax)", f"{delta_mm:.2f} mm")
                    st.caption(f"Load: {load_desc}, Span: {L_defl:.1f} m, Ix = {Ix_val:.1f} × 10⁶ mm⁴")

                    if delta_mm <= delta_limit:
                        st.success(f"✅ **PASS** — δ = {delta_mm:.2f} mm ≤ L/{defl_limit_ratio} = {delta_limit:.2f} mm")
                    else:
                        st.error(f"❌ **FAIL** — δ = {delta_mm:.2f} mm > L/{defl_limit_ratio} = {delta_limit:.2f} mm")

                    st.caption(f"Utilization: {ratio:.1%}")

            except Exception as e:
                st.error(f"Deflection calculation error: {e}")

    st.divider()

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

    with st.expander("Raw Section Data"):
        st.json(shape)