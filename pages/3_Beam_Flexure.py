# pages/3_Beam_Flexure.py
# Beam Flexure Design - CSA S16
#
# Presentation matched to pages/2_Compression.py: numbered sections, a
# stated clause for every check, then Step 1 / Step 2 / Step 3 / Step 4
# with the substitution shown in LaTeX at each step.
#
# ASCII only. Straight quotes only.

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from _theme import (apply_theme, render_sidebar_logo, render_footer,
                    disclaimer_page, render_page_title)
from flexure_diagrams import (
    i_section_stress_svg,
    beam_elevation_svg,
    ltb_curve_svg,
    shear_fs_curve_svg,
)

import sst12  # direct reader for the CISC SST12.1 workbook

try:
    import viewer_3d_flexure
    HAS_VIEWER = True
except Exception:
    HAS_VIEWER = False

# Stiffened web shear lives in main.py
try:
    from main import stiffened_web_shear_CSA13_4  # type: ignore
except Exception:
    stiffened_web_shear_CSA13_4 = None  # type: ignore


# ===========================================================
# CONSTANTS
# ===========================================================

DASH = "-"

PHI_B = 0.9
PHI_V_DEFAULT = 0.9
E_MPA_DEFAULT = 200000.0
G_MPA_DEFAULT = 77000.0

APP_TITLE = "CSA S16 - Beam Flexure"
DISCLAIMER_VERSION = "2026-07-29_v3"

DISCLAIMER_MD = """
# INFRASPECTIVE - USER ACCESS AGREEMENT

---

**1. BETA SOFTWARE NOTICE**

Infraspective provides this application for evaluation and optimization purposes. The App is Beta software: features may be incomplete, may change without notice, and may contain errors, including incorrect calculations. By using the App, you acknowledge these limitations and agree that anonymous usage data may be collected to assist in the refinement of the calculation engine.

---

**2. PROFESSIONAL VERIFICATION**

This tool is a calculation aid and does not replace professional engineering judgment. The User is responsible for the independent verification of all outputs in accordance with the laws and professional-practice requirements of their jurisdiction.

All results must be validated by a licensed Professional Engineer in Canada prior to any project application.

The User agrees not to rely on any App output for any project purpose unless and until that output has been independently verified.

The User acknowledges that any use of App outputs without independent verification is done entirely at their own risk.

Use of this App does not create an engineer-client relationship between the User and Infraspective.

---

**3. DATA USAGE & CONSENT**

By using the App, you consent to the collection of anonymous usage data, including technical input parameters, feature usage, session activity, and error reports. No personal information is collected. This data is used exclusively to optimize the software's logic, reliability, and performance during the Beta period. Providing feedback is welcome but not required.

---

**4. LIMITATION OF LIABILITY**

This software is provided "AS IS" and is in a Beta state, meaning it may contain errors, incomplete features, or incorrect calculations.

Infraspective disclaims all warranties regarding the accuracy of the Beta calculations.

The User assumes all risk associated with the use of the App's outputs. Use of this App is entirely at the User's own risk.

To the maximum extent permitted by law, Infraspective shall not be liable for any direct, indirect, incidental, or consequential damages arising from use of the App.

This limitation of liability applies even if the App fails its essential purpose or is found to be in fundamental breach of contract.

No compensation or damages of any kind are payable for errors, omissions, or inaccuracies in the App or its outputs.

---

**5. INDEMNITY**

The User agrees to indemnify, defend, and hold harmless Infraspective from any and all claims, demands, losses, or legal fees (including solicitor-client costs) arising from the User's use of, misuse of, or reliance on the App, whether the claim is made by the User or a third party.

---

**6. GOVERNING LAW & JURISDICTION**

This agreement is governed by the federal laws of Canada and the laws of the Canadian province or territory in which the User resides or practises. Any dispute shall be resolved exclusively in the courts of that jurisdiction.

---

**7. SEVERABILITY**

If any provision of this Agreement is found unenforceable, the remaining provisions shall remain in full force and effect.

---

**8. VERIFICATION ACKNOWLEDGMENT**

Before each use of the App, the User shall affirmatively confirm their agreement below.

The User acknowledges that failure to verify does not transfer liability to Infraspective.

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
  <b>Infraspective - Beta Software:</b> All outputs must be independently
  verified by a licensed P.Eng before any project reliance. Results do not
  constitute professional engineering advice.
</div>
"""


# ===========================================================
# DISCLAIMER GATE
# ===========================================================


def require_disclaimer_acceptance() -> None:
    st.set_page_config(page_title="Beam Flexure - Infraspective",
                       page_icon=":wrench:", layout="wide")

    if st.session_state.get("disclaimer_version") != DISCLAIMER_VERSION:
        st.session_state["accepted_disclaimer"] = False
        st.session_state["disclaimer_version"] = DISCLAIMER_VERSION

    # gate_disclaimer also enforces the 10-minute inactivity timeout
    from _theme import gate_disclaimer
    gate_disclaimer()


# ===========================================================
# FORMATTING HELPERS (same contract as the compression page)
# ===========================================================


def num(x: Any, nd: int = 2) -> str:
    if x is None:
        return DASH
    try:
        xf = float(x)
    except Exception:
        return str(x)
    if not math.isfinite(xf):
        return "inf"
    if abs(xf) >= 100000:
        return "{:,.0f}".format(xf)
    return "{:,.{}f}".format(xf, nd)


def tex_num(x: Any, nd: int = 2) -> str:
    return num(x, nd).replace(",", r"\,")


def md(text: str) -> None:
    st.markdown(text, unsafe_allow_html=True)


def section_heading(text: str) -> None:
    md("<h3 style='margin-bottom:0.2rem'>" + text + "</h3>")


def sub_heading(text: str) -> None:
    md("<p style='font-weight:600;margin:0.9rem 0 0.25rem 0'>" + text + "</p>")


def note(text: str) -> None:
    md("<p style='margin:0.25rem 0 0.6rem 0;line-height:1.55'>" + text + "</p>")


def indent(text: str) -> None:
    md("<p style='margin:0.15rem 0 0.15rem 1.6rem;line-height:1.6'>"
       + text + "</p>")


def step(title: str, expanded: Optional[bool] = None):
    """Every calculation step lives in its own expander so the page can
    be skimmed collapsed or studied open. The sidebar 'Expand all steps'
    checkbox sets the default."""
    if expanded is None:
        expanded = bool(st.session_state.get("fexpandall", False))
    return st.expander(title, expanded=expanded)


def _f(x: Any) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def _safe_div(a, b) -> Optional[float]:
    try:
        if b is None or float(b) == 0.0:
            return None
        return float(a) / float(b)
    except Exception:
        return None


def fnum(x: Any, field_name: str) -> float:
    try:
        return float(x)
    except Exception as e:
        raise ValueError("Field '" + field_name + "' is not numeric: "
                         + repr(x)) from e


def to_kNm_from_Nmm(M_Nmm: float) -> float:
    return M_Nmm * 1e-6


# ===========================================================
# DIMENSIONED CROSS-SECTION DIAGRAM
# ===========================================================


def dimensioned_section_svg(geom: Dict[str, float]) -> str:
    """An I-section drawn to scale with every symbol the page uses
    dimensioned in place: b across the flange, d overall, h between the
    flanges, and leaders pointing at the flange thickness t and the web
    thickness w. Answers 'which part of the section is b?' at a glance."""
    d = float(geom["d"])
    b = float(geom["b"])
    t = float(geom["t"])
    w = float(geom["w"])
    h = float(geom["h"])

    Wc, Hc = 350.0, 360.0
    mL, mR, mT, mB = 84.0, 104.0, 54.0, 66.0
    availW, availH = Wc - mL - mR, Hc - mT - mB
    s = min(availW / b, availH / d)
    bw, dh, tf, ww = b * s, d * s, t * s, w * s
    cx = mL + availW / 2.0
    cy = mT + availH / 2.0
    x0, x1 = cx - bw / 2.0, cx + bw / 2.0
    y0, y1 = cy - dh / 2.0, cy + dh / 2.0
    wx0, wx1 = cx - ww / 2.0, cx + ww / 2.0
    yi0, yi1 = y0 + tf, y1 - tf

    C_STEEL_F = "#a9bac9"
    C_STEEL_S = "#55606c"
    C_B = "#1f6feb"
    C_D = "#e5534b"
    C_H = "#2da44e"
    C_T = "#b08800"
    C_W = "#8250df"

    def pt(x: float, y: float) -> str:
        return "{:.1f} {:.1f}".format(x, y)

    def line(xa, ya, xb, yb, color, width=1.2, dash=""):
        dd = " stroke-dasharray='" + dash + "'" if dash else ""
        return ("<line x1='{:.1f}' y1='{:.1f}' x2='{:.1f}' y2='{:.1f}' "
                "stroke='{}' stroke-width='{}'{} />"
                ).format(xa, ya, xb, yb, color, width, dd)

    def slash(x, y, color):
        # drafting tick at a dimension-line end
        return line(x - 4, y + 4, x + 4, y - 4, color, 1.4)

    def text(x, y, s_, color, anchor="middle", rot=None, size=12):
        tr = (" transform='rotate({} {:.1f} {:.1f})'"
              .format(rot, x, y)) if rot is not None else ""
        return ("<text x='{:.1f}' y='{:.1f}' fill='{}' font-size='{}' "
                "font-family='-apple-system,Segoe UI,Roboto,sans-serif' "
                "text-anchor='{}'{}>{}</text>"
                ).format(x, y, color, size, anchor, tr, s_)

    p = []
    p.append("<svg viewBox='0 0 {:.0f} {:.0f}' width='{:.0f}' "
             "height='{:.0f}' xmlns='http://www.w3.org/2000/svg'>"
             .format(Wc, Hc, Wc, Hc))

    # section outline
    path = ("M " + pt(x0, y0) + " L " + pt(x1, y0) + " L " + pt(x1, yi0)
            + " L " + pt(wx1, yi0) + " L " + pt(wx1, yi1) + " L "
            + pt(x1, yi1) + " L " + pt(x1, y1) + " L " + pt(x0, y1)
            + " L " + pt(x0, yi1) + " L " + pt(wx0, yi1) + " L "
            + pt(wx0, yi0) + " L " + pt(x0, yi0) + " Z")
    p.append("<path d='" + path + "' fill='" + C_STEEL_F
             + "' fill-opacity='0.55' stroke='" + C_STEEL_S
             + "' stroke-width='1.6' />")

    # ---- b across the top flange ----
    yT = y0 - 22.0
    p.append(line(x0, y0 - 2, x0, yT - 8, C_STEEL_S, 0.8, "3 3"))
    p.append(line(x1, y0 - 2, x1, yT - 8, C_STEEL_S, 0.8, "3 3"))
    p.append(line(x0, yT, x1, yT, C_B, 1.4))
    p.append(slash(x0, yT, C_B))
    p.append(slash(x1, yT, C_B))
    p.append(text(cx, yT - 8, "b = " + "{:.0f}".format(b) + " mm", C_B))

    # ---- d overall, left side ----
    xL = x0 - 26.0
    p.append(line(x0 - 2, y0, xL - 8, y0, C_STEEL_S, 0.8, "3 3"))
    p.append(line(x0 - 2, y1, xL - 8, y1, C_STEEL_S, 0.8, "3 3"))
    p.append(line(xL, y0, xL, y1, C_D, 1.4))
    p.append(slash(xL, y0, C_D))
    p.append(slash(xL, y1, C_D))
    p.append(text(xL - 12, cy, "d = " + "{:.0f}".format(d) + " mm", C_D,
                  "middle", -90))

    # ---- h between the flanges, right side ----
    xR = x1 + 24.0
    p.append(line(wx1 + 2, yi0, xR + 8, yi0, C_STEEL_S, 0.8, "3 3"))
    p.append(line(wx1 + 2, yi1, xR + 8, yi1, C_STEEL_S, 0.8, "3 3"))
    p.append(line(xR, yi0, xR, yi1, C_H, 1.4))
    p.append(slash(xR, yi0, C_H))
    p.append(slash(xR, yi1, C_H))
    p.append(text(xR + 14, cy, "h = " + "{:.1f}".format(h) + " mm", C_H,
                  "middle", -90))

    # ---- t leader into the top flange ----
    ty = y0 + tf / 2.0
    p.append("<circle cx='{:.1f}' cy='{:.1f}' r='2.4' fill='{}' />"
             .format(x1 - bw * 0.16, ty, C_T))
    p.append(line(x1 - bw * 0.16, ty, xR + 20, ty, C_T, 1.1))
    p.append(text(xR + 24, ty + 4, "t = " + "{:.1f}".format(t) + " mm",
                  C_T, "start"))

    # ---- w leader onto the web ----
    wyy = cy + dh * 0.16
    p.append("<circle cx='{:.1f}' cy='{:.1f}' r='2.4' fill='{}' />"
             .format(wx1, wyy, C_W))
    p.append(line(wx1, wyy, x1 + 20, y1 + 30, C_W, 1.1))
    p.append(text(x1 + 24, y1 + 34, "w = " + "{:.1f}".format(w) + " mm",
                  C_W, "start"))

    p.append("</svg>")
    return ("<div style='display:flex;justify-content:center'>"
            + "".join(p) + "</div>")


def render_section_diagrams(section_class: int,
                            geom: Dict[str, float]) -> None:
    """The dimensioned section beside the stress distribution."""
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(dimensioned_section_svg(geom), unsafe_allow_html=True)
        st.caption("Where each symbol lives on the section: b and t on "
                   "the flange, w on the web, d overall, h = d - 2t "
                   "between the flanges.")
    with c2:
        st.markdown(i_section_stress_svg(section_class, mode="stress"),
                    unsafe_allow_html=True)
        st.caption("Class 1 and 2 develop a full plastic block; Class 3 "
                   "and 4 stay on the elastic triangle.")


# ===========================================================
# SECTION SOURCE - CISC SST12.1 through sst12.py
# ===========================================================


def _norm(s: str) -> str:
    out = (str(s).strip().lower()
           .replace("(", "").replace(")", "")
           .replace("[", "").replace("]", "")
           .replace("/", "_").replace("-", "_")
           .replace(" ", "_").replace("^", ""))
    return "".join(c for c in out if c.isalnum() or c == "_")


# Column-name matching only. This does not change the symbols used in
# the calculations or on the page.
CANON_SYNONYMS: Dict[str, List[str]] = {
    "designation": ["designation", "Designation", "shape", "section", "name",
                    "w_shape"],
    "d": ["d", "D", "depth", "depth_d", "depth_d_mm", "overall_depth"],
    "b": ["b", "B", "bf", "flange_width", "flange_width_b",
          "flange_width_b_mm"],
    "t": ["t", "T", "tf", "flange_thickness", "flange_thickness_t",
          "flange_thickness_t_mm"],
    "w": ["w", "W", "tw", "web_thickness", "web_thickness_w",
          "web_thickness_w_mm"],
    "Zx": ["Zx", "zx", "z_x", "plastic_modulus_zx", "plastic_modulus_zx_mm3",
           "zx_mm3", "zx_103_mm"],
    "Sx": ["Sx", "sx", "s_x", "elastic_modulus_sx", "elastic_modulus_sx_mm3",
           "sx_mm3", "sx_103_mm"],
    "Ix": ["Ix", "ix", "i_x", "ix_106_mm4", "ix_106_mm"],
    "Zy": ["Zy", "zy", "z_y", "zy_mm3", "zy_103_mm"],
    "Sy": ["Sy", "sy", "s_y", "sy_mm3", "sy_103_mm"],
    "Iy": ["Iy", "iy", "i_y", "iy_106_mm4", "iy_106_mm"],
    "J": ["J", "j", "torsion_constant_j", "j_103_mm4", "j_103_mm"],
    "Cw": ["Cw", "cw", "c_w", "warping_constant_cw", "cw_109_mm6",
           "cw_109_mm"],
    "rx": ["rx", "r_x", "radius_of_gyration_rx", "rx_mm"],
    "ry": ["ry", "r_y", "radius_of_gyration_ry", "ry_mm"],
    "k": ["k", "K", "distance_k", "distance_k_mm", "fillet_distance"],
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

    for sym in ("Zx", "Sx", "Ix", "Zy", "Sy", "Iy", "J", "Cw", "rx", "ry",
                "k"):
        v = _pick(rec, CANON_SYNONYMS[sym])
        if v is not None:
            try:
                out[sym] = float(str(v).replace(",", "").strip())
            except (ValueError, TypeError):
                out[sym] = v
    return out


@st.cache_data(ttl=60)
def load_shapes() -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for rec in sst12.shared_records():
        rec2 = _canonicalize_record(rec)
        des = rec2.get("designation")
        if des:
            key = str(des).strip()
            merged[key] = rec2
            order.append(key)

    seen = set()
    order_unique: List[str] = []
    for k in order:
        if k not in seen:
            seen.add(k)
            order_unique.append(k)

    def _nat(s: str):
        return [int(c) if c.isdigit() else c.lower()
                for c in re.split(r"(\d+)", s)]

    order_unique.sort(key=_nat)

    # This page is major-axis flexure of W shapes only.
    order_unique = [k for k in order_unique
                    if k.upper().startswith("W") and len(k) > 1
                    and k[1].isdigit()]
    return merged, order_unique


def get_shape(designation: str) -> Optional[Dict[str, Any]]:
    shapes, _ = load_shapes()
    return shapes.get(designation)


# ===========================================================
# TABLE 2 - CLASSIFICATION ENGINE
# ===========================================================


def class_limits_flange(Fy: float) -> tuple:
    r = 1.0 / math.sqrt(Fy)
    return 145 * r, 170 * r, 200 * r


def class_limits_web(Fy: float) -> tuple:
    """Webs of I-sections in flexure: 1100 / 1700 / 1900 over sqrt(Fy),
    each times (1 - k Cf / phi Cy). In pure bending Cf = 0, so the
    reduction term is 1.0."""
    r = 1.0 / math.sqrt(Fy)
    return 1100 * r, 1700 * r, 1900 * r


def flange_lambda_r(Fy: float) -> float:
    # Class 3 / 4 boundary for an I-section flange (one edge supported).
    return 200.0 / math.sqrt(Fy)


def web_lambda_r(Fy: float) -> float:
    # Class 3 / 4 boundary for an I-section web (two edges supported),
    # Cf = 0.
    return 1700.0 / math.sqrt(Fy)


@dataclass
class ElementCheck:
    key: str
    label: str
    condition: str
    elements: str
    why: str
    zone: str
    symbol: str = "b_{el}/t"
    width_clause: str = ""
    width_steps: List[str] = field(default_factory=list)
    ratio_step: str = ""
    ratio: Optional[float] = None
    limits: List[float] = field(default_factory=list)
    limit_formulas: List[str] = field(default_factory=list)
    limit_steps: List[str] = field(default_factory=list)
    narrative: List[str] = field(default_factory=list)
    section_class: Optional[int] = None


def _class_of(ratio: float, limits: List[float]) -> Tuple[int, List[str]]:
    lines = []
    for i, lv in enumerate(limits, start=1):
        if ratio <= lv:
            lines.append(r"\text{Class }" + str(i) + r":\quad "
                         + tex_num(ratio, 2) + r" \leq " + tex_num(lv, 2)
                         + r"\quad\checkmark\ \Rightarrow\ \textbf{Class }"
                         + str(i))
            return i, lines
        lines.append(r"\text{Class }" + str(i) + r":\quad "
                     + tex_num(ratio, 2) + r" > " + tex_num(lv, 2)
                     + r"\quad\times\ \text{not Class }" + str(i))
    lines.append(r"\text{Exceeds every Class 3 limit}\ \Rightarrow\ "
                 r"\textbf{Class 4 (slender)}")
    return 4, lines


def table2_flexure_elements(geom: Dict[str, float],
                            Fy: float) -> List[ElementCheck]:
    """The two plate elements a W shape has in major-axis flexure."""
    sq = math.sqrt(float(Fy))
    d, b, t, w, h = geom["d"], geom["b"], geom["t"], geom["w"], geom["h"]
    out: List[ElementCheck] = []

    # ---- flange, one edge supported ----
    b_el = b / 2.0
    consts_f = [145.0, 170.0, 200.0]
    vals_f = [c / sq for c in consts_f]
    forms_f = [r"\frac{b_{el}}{t} \leq \frac{" + str(int(c))
               + r"}{\sqrt{F_y}}" for c in consts_f]
    steps_f = [r"\text{Class }" + str(i + 1) + r"\text{ limit} = \frac{"
               + str(int(c)) + r"}{\sqrt{" + tex_num(Fy, 0) + r"}} = \frac{"
               + str(int(c)) + r"}{" + tex_num(sq, 3) + r"} = "
               + tex_num(v, 2)
               for i, (c, v) in enumerate(zip(consts_f, vals_f))]
    r_f = b_el / t
    cls_f, narr_f = _class_of(r_f, vals_f)
    out.append(ElementCheck(
        key="t2_flange",
        label="Flange in flexural compression - one edge free",
        condition="Supported along ONE edge, under flexural compression",
        elements="Flanges of I-sections bent about the major axis",
        why=("The compression flange is joined to the web along one edge "
             "only and is free at the tip. How much rotation the section "
             "can sustain before that tip buckles is what separates "
             "Class 1 from Class 2 and Class 3."),
        zone="flange",
        symbol="b_{el}/t",
        width_clause=("Cl. 11.3.1 c) - flanges of beams take one-half the "
                      "nominal width, because the web divides the flange "
                      "into two outstands"),
        width_steps=[r"b_{el} = \frac{b}{2} = \frac{" + tex_num(b, 1)
                     + r"}{2} = " + tex_num(b_el, 1) + r"\ \text{mm}"],
        ratio_step=(r"\frac{b_{el}}{t} = \frac{" + tex_num(b_el, 1)
                    + r"}{" + tex_num(t, 1) + r"} = " + tex_num(r_f, 2)),
        ratio=r_f, limits=vals_f, limit_formulas=forms_f, limit_steps=steps_f,
        narrative=narr_f, section_class=cls_f))

    # ---- web, two edges supported ----
    consts_w = [(1100, 0.39), (1700, 0.61), (1900, 0.65)]
    vals_w = [c / sq for c, _k in consts_w]   # Cf = 0, so the factor is 1.0
    forms_w = [r"\frac{h}{w} \leq \frac{" + str(c)
               + r"}{\sqrt{F_y}}\left(1 - " + str(k)
               + r"\,\frac{C_f}{\phi C_y}\right)" for c, k in consts_w]
    steps_w = []
    for i, ((c, k), v) in enumerate(zip(consts_w, vals_w)):
        steps_w.append(r"\text{Class }" + str(i + 1)
                       + r"\text{ limit} = \frac{" + str(c) + r"}{"
                       + tex_num(sq, 3) + r"}\left(1 - " + str(k)
                       + r"(0)\right) = \frac{" + str(c) + r"}{"
                       + tex_num(sq, 3) + r"} = " + tex_num(v, 2))
    r_w = h / w
    cls_w, narr_w = _class_of(r_w, vals_w)
    out.append(ElementCheck(
        key="t2_web",
        label="Web in flexural compression - both edges supported",
        condition="Supported along TWO edges, major-axis flexure",
        elements="Webs of I-sections",
        why=("The web is joined to a flange at the top edge and again at "
             "the bottom edge. Two supported edges is a far stiffer "
             "boundary than one, so the limits are much higher than the "
             "flange limits. Only half the web depth is in compression, "
             "which relaxes them further."),
        zone="web",
        symbol="h/w",
        width_clause=("Cl. 11.3.2 d) - for webs of hot-rolled sections the "
                      "width is the clear distance between flanges"),
        width_steps=[
            r"h = d - 2t = " + tex_num(d, 1) + r" - 2(" + tex_num(t, 1)
            + r") = " + tex_num(h, 1) + r"\ \text{mm}",
            r"\text{Pure bending: } C_f = 0 \Rightarrow "
            r"\left(1 - k\,\frac{C_f}{\phi C_y}\right) = 1.00"],
        ratio_step=(r"\frac{h}{w} = \frac{" + tex_num(h, 1) + r"}{"
                    + tex_num(w, 1) + r"} = " + tex_num(r_w, 2)),
        ratio=r_w, limits=vals_w, limit_formulas=forms_w, limit_steps=steps_w,
        narrative=narr_w, section_class=cls_w))

    return out


def render_t2(chk: ElementCheck) -> None:
    note("<i>" + chk.condition + " &mdash; " + chk.elements + "</i>")
    note(chk.why)

    with step("Limits from Table 2"):
        for f in chk.limit_formulas:
            st.latex(f)

    with step("Step 1 - establish the element width and inputs"):
        indent(chk.width_clause)
        for s in chk.width_steps:
            st.latex(s)

    with step("Step 2 - form the width-to-thickness ratio"):
        st.latex(chk.ratio_step)

    with step("Step 3 - evaluate each limit"):
        for s in chk.limit_steps:
            st.latex(s)

    with step("Step 4 - find the class"):
        for s in chk.narrative:
            st.latex(s)

    cls = chk.section_class
    if cls == 4:
        st.error("Class 4 - slender. Cl. 13.5 c) requires an effective "
                 "section modulus.")
    elif cls == 3:
        st.warning("Class 3 - the yield moment only, Cl. 13.5 b).")
    else:
        st.success("Class " + str(cls) + " - the plastic moment is "
                   "available, Cl. 13.5 a).")


def classify_section(geom: Dict[str, float], Fy: float) -> Dict[str, Any]:
    checks = table2_flexure_elements(geom, Fy)
    by_key = {c.key: c for c in checks}
    cls_f = by_key["t2_flange"].section_class or 1
    cls_w = by_key["t2_web"].section_class or 1
    cls = max(cls_f, cls_w)
    if cls == cls_f and cls == cls_w:
        gov = "Flange and web (tie)"
    elif cls == cls_f:
        gov = "Flange"
    else:
        gov = "Web"
    return {"checks": checks, "class_flange": cls_f, "class_web": cls_w,
            "class_section": cls, "governing": gov,
            "ratio_flange": by_key["t2_flange"].ratio,
            "ratio_web": by_key["t2_web"].ratio}


# ===========================================================
# CLASS 4 - EFFECTIVE SECTION MODULUS
# ===========================================================


def effective_flange_width(b: float, t: float, Fy: float) -> float:
    lam = (b / 2.0) / t
    lam_r = flange_lambda_r(Fy)
    if lam <= lam_r:
        return b
    return min(b * (lam_r / lam), b)


def effective_web_height(h: float, w: float, Fy: float) -> float:
    lam = h / w
    lam_r = web_lambda_r(Fy)
    if lam <= lam_r:
        return h
    return min(h * (lam_r / lam), h)


def effective_Ix(b_eff: float, t: float, h_eff: float, w: float) -> float:
    Af = b_eff * t
    y = (h_eff / 2.0) + (t / 2.0)
    If_local = (b_eff * t ** 3) / 12.0
    If_total = 2.0 * (If_local + Af * y ** 2)
    Iw = (w * h_eff ** 3) / 12.0
    return If_total + Iw


def compute_Se_CSA(d: float, b: float, t: float, w: float,
                   Fy: float) -> Dict[str, Any]:
    h = d - 2.0 * t
    b_eff = effective_flange_width(b, t, Fy)
    h_eff = effective_web_height(h, w, Fy)
    Ix_eff = effective_Ix(b_eff, t, h_eff, w)
    Se = Ix_eff / (d / 2.0)
    return {"h": h, "b_eff": b_eff, "h_eff": h_eff, "Ix_eff": Ix_eff,
            "Se": Se}


def se_steps(geom: Dict[str, float], Fy: float) -> List[str]:
    d, b, t, w = geom["d"], geom["b"], geom["t"], geom["w"]
    res = compute_Se_CSA(d, b, t, w, Fy)
    lam_f = (b / 2.0) / t
    lam_w = (d - 2.0 * t) / w
    lr_f = flange_lambda_r(Fy)
    lr_w = web_lambda_r(Fy)
    return [
        r"\lambda_{r,f} = \frac{200}{\sqrt{F_y}} = " + tex_num(lr_f, 2)
        + r"\qquad \lambda_f = " + tex_num(lam_f, 2),
        r"b_{eff} = b\,\frac{\lambda_{r,f}}{\lambda_f} = "
        + tex_num(b, 1) + r"\times\frac{" + tex_num(lr_f, 2) + r"}{"
        + tex_num(lam_f, 2) + r"} = " + tex_num(res["b_eff"], 1)
        + r"\ \text{mm}",
        r"\lambda_{r,w} = \frac{1700}{\sqrt{F_y}} = " + tex_num(lr_w, 2)
        + r"\qquad \lambda_w = " + tex_num(lam_w, 2),
        r"h_{eff} = h\,\frac{\lambda_{r,w}}{\lambda_w} = "
        + tex_num(res["h_eff"], 1) + r"\ \text{mm}",
        r"I_{x,eff} = 2\left[\frac{b_{eff}t^3}{12} + b_{eff}t\,y^2\right]"
        r" + \frac{w\,h_{eff}^3}{12} = " + tex_num(res["Ix_eff"], 0)
        + r"\ \text{mm}^4",
        r"S_e = \frac{I_{x,eff}}{d/2} = \frac{" + tex_num(res["Ix_eff"], 0)
        + r"}{" + tex_num(d / 2.0, 1) + r"} = " + tex_num(res["Se"], 0)
        + r"\ \text{mm}^3",
    ]


# ===========================================================
# CLAUSE 13.5 - LATERALLY SUPPORTED MOMENT RESISTANCE
# ===========================================================


def Mr_laterally_supported(shape: Dict[str, Any], geom: Dict[str, float],
                           Fy: float, cls: int,
                           phi_b: float = PHI_B) -> Dict[str, Any]:
    """Returns the modulus used, Mr, and the LaTeX steps behind it."""
    steps: List[str] = []

    if cls in (1, 2):
        raw = shape.get("Zx")
        if raw is None:
            return {"ok": False, "error": "Zx is not carried for this "
                                          "section."}
        Z = float(raw) * 1000.0
        clause = "Cl. 13.5 a)"
        sym = "Z_x"
        formula = r"M_r = \phi\, Z_x F_y"
        steps.append(r"Z_x = " + tex_num(float(raw), 0)
                     + r"\times 10^3 = " + tex_num(Z, 0) + r"\ \text{mm}^3")
        S_used = Z
        mode = "Plastic modulus Zx"
    elif cls == 3:
        raw = shape.get("Sx")
        if raw is None:
            return {"ok": False, "error": "Sx is not carried for this "
                                          "section."}
        S_used = float(raw) * 1000.0
        clause = "Cl. 13.5 b)"
        sym = "S_x"
        formula = r"M_r = \phi\, S_x F_y"
        steps.append(r"S_x = " + tex_num(float(raw), 0)
                     + r"\times 10^3 = " + tex_num(S_used, 0)
                     + r"\ \text{mm}^3")
        mode = "Elastic modulus Sx"
    else:
        res = compute_Se_CSA(geom["d"], geom["b"], geom["t"], geom["w"], Fy)
        S_used = res["Se"]
        clause = "Cl. 13.5 c)"
        sym = "S_e"
        formula = r"M_r = \phi\, S_e F_y"
        steps.append(r"S_e = " + tex_num(S_used, 0) + r"\ \text{mm}^3"
                     r"\quad(\text{derived below})")
        mode = "Effective modulus Se"

    Mr_Nmm = phi_b * S_used * Fy
    Mr_kNm = to_kNm_from_Nmm(Mr_Nmm)

    steps.append(r"M_r = " + tex_num(phi_b, 2) + r" \times "
                 + tex_num(S_used, 0) + r" \times " + tex_num(Fy, 0)
                 + r" = " + tex_num(Mr_Nmm, 0) + r"\ \text{N}\cdot\text{mm}")
    steps.append(r"M_r = " + tex_num(Mr_kNm, 1)
                 + r"\ \text{kN}\cdot\text{m}")

    return {"ok": True, "Mr_kNm": Mr_kNm, "S_used": S_used, "symbol": sym,
            "clause": clause, "formula": formula, "steps": steps,
            "mode": mode}


# ===========================================================
# CLAUSE 13.6 - LATERAL TORSIONAL BUCKLING
# ===========================================================


OMEGA2_CASES = [
    ("uniform_moment", "Uniform moment (omega2 = 1.00)", 1.00),
    ("midspan_point", "Midspan point load (omega2 = 1.13)", 1.13),
    ("udl", "UDL (omega2 = 1.30)", 1.30),
    ("triangular", "Triangular moment (omega2 = 1.40)", 1.40),
    ("cantilever_point", "Cantilever point load (omega2 = 1.00)", 1.00),
]


def omega2_from_case(case: str) -> float:
    for k, _l, v in OMEGA2_CASES:
        if k == case:
            return float(v)
    return 1.0


def omega2_general(M_max: float, M_a: float, M_b: float, M_c: float) -> float:
    """Cl. 13.6 Eq. 2, four-point form."""
    Mm, Ma, Mb, Mc = abs(M_max), abs(M_a), abs(M_b), abs(M_c)
    denom = math.sqrt(Mm * Mm + 4.0 * Ma * Ma + 7.0 * Mb * Mb + 4.0 * Mc * Mc)
    if denom <= 0:
        return 1.0
    return min(4.0 * Mm / denom, 2.5)


def omega2_linear(kappa: float) -> float:
    """Cl. 13.6 Eq. 3, linear moment gradient."""
    k = max(-1.0, min(1.0, float(kappa)))
    return min(1.75 + 1.05 * k + 0.3 * k * k, 2.5)


def critical_elastic_moment_kNm(L_mm: float, Iy_mm4: float, J_mm4: float,
                                Cw_mm6: float, omega2: float,
                                E_MPa: float = E_MPA_DEFAULT,
                                G_MPa: float = G_MPA_DEFAULT) -> float:
    """Mu, Cl. 13.6 Eq. 1, in kN-m."""
    if L_mm <= 0:
        return 0.0
    term1 = E_MPa * Iy_mm4 * G_MPa * J_mm4
    term2 = (math.pi * E_MPa / L_mm) ** 2 * Iy_mm4 * Cw_mm6
    Mu_Nmm = (omega2 * math.pi / L_mm) * math.sqrt(max(term1 + term2, 0.0))
    return Mu_Nmm / 1e6


def ltb_resistance_13_6(shape: Dict[str, Any], geom: Dict[str, float],
                        Fy: float, cls: int, Lb_mm: float, omega2: float,
                        phi_b: float = PHI_B,
                        E_MPa: float = E_MPA_DEFAULT,
                        G_MPa: float = G_MPA_DEFAULT) -> Dict[str, Any]:
    """Full Cl. 13.6 result together with the LaTeX behind each step."""
    Iy_raw = _f(shape.get("Iy"))
    J_raw = _f(shape.get("J"))
    Cw_raw = _f(shape.get("Cw"))
    if None in (Iy_raw, J_raw, Cw_raw):
        return {"ok": False,
                "error": ("Iy, J or Cw is not carried for this section, so "
                          "Cl. 13.6 Eq. 1 cannot be evaluated.")}

    Iy = Iy_raw * 1e6      # 10^6 mm4 -> mm4
    J = J_raw * 1e3        # 10^3 mm4 -> mm4
    Cw = Cw_raw * 1e9      # 10^9 mm6 -> mm6

    # reference moment: Mp for Class 1 and 2, My for Class 3, Me for Class 4
    if cls in (1, 2):
        Zx = _f(shape.get("Zx"))
        if Zx is None:
            return {"ok": False, "error": "Zx is not carried."}
        S_ref = Zx * 1e3
        ref_sym = "M_p"
        ref_note = "Class 1 or 2, so the reference moment is the plastic "\
                   "moment Mp = Zx Fy."
    elif cls == 3:
        Sx = _f(shape.get("Sx"))
        if Sx is None:
            return {"ok": False, "error": "Sx is not carried."}
        S_ref = Sx * 1e3
        ref_sym = "M_y"
        ref_note = "Class 3, so the reference moment is the yield moment "\
                   "My = Sx Fy."
    else:
        S_ref = compute_Se_CSA(geom["d"], geom["b"], geom["t"], geom["w"],
                               Fy)["Se"]
        ref_sym = "M_e"
        ref_note = "Class 4, so the reference moment is built on the "\
                   "effective modulus, Me = Se Fy."

    Mref = S_ref * Fy / 1e6

    term1 = E_MPa * Iy * G_MPa * J
    term2 = (math.pi * E_MPa / Lb_mm) ** 2 * Iy * Cw
    Mu = (omega2 * math.pi / Lb_mm) * math.sqrt(max(term1 + term2, 0.0)) / 1e6

    if Mu > 0.67 * Mref:
        Mr = min(1.15 * phi_b * Mref * (1.0 - 0.28 * Mref / Mu),
                 phi_b * Mref)
        branch = "inelastic"
        branch_clause = "Cl. 13.6 a) ii)"
        capped = abs(Mr - phi_b * Mref) < 1e-9
    else:
        Mr = phi_b * Mu
        branch = "elastic"
        branch_clause = "Cl. 13.6 a) iii)"
        capped = False

    return {"ok": True, "Mu_kNm": Mu, "Mref_kNm": Mref, "Mr_kNm": Mr,
            "ref_sym": ref_sym, "ref_note": ref_note, "branch": branch,
            "branch_clause": branch_clause, "capped": capped,
            "Iy": Iy, "J": J, "Cw": Cw, "term1": term1, "term2": term2,
            "omega2": omega2, "phi_b": phi_b, "E": E_MPa, "G": G_MPa}


# Retained from the earlier build. Not used by the page any more; the
# page now runs the Cl. 13.6 formulation in ltb_resistance_13_6 above.
def residual_stress_factor(section_class: int, Fy: float, Lb_mm: float,
                           rts_mm: float) -> float:
    if rts_mm <= 0:
        return 1.0
    lam = (Lb_mm / rts_mm) * math.sqrt(max(Fy, 1.0) / 350.0)
    if section_class in (1, 2):
        return 1.0 if lam <= 60 else max(0.75, 1.0 - 0.003 * (lam - 60))
    if section_class == 3:
        return 0.95 if lam <= 50 else max(0.65, 0.95 - 0.004 * (lam - 50))
    return 0.60


# ===========================================================
# CLAUSE 13.4.1.1 - SHEAR
# ===========================================================


def shear_unstiffened_13_4_1_1a(Fy: float, h: float, w: float,
                                phi_v: float) -> Dict[str, Any]:
    if Fy <= 0 or h <= 0 or w <= 0:
        raise ValueError("Fy, h and w must all be greater than zero.")

    Aw = h * w
    lam = h / w
    sq = math.sqrt(Fy)
    lam1 = 1014.0 / sq
    lam2 = 1435.0 / sq

    if lam <= lam1:
        Fs = 0.66 * Fy
        branch = "13.4.1.1 a) i)"
        branch_text = "Shear yielding governs."
        fs_form = r"F_s = 0.66\,F_y"
        fs_step = (r"F_s = 0.66(" + tex_num(Fy, 0) + r") = "
                   + tex_num(Fs, 2) + r"\ \text{MPa}")
    elif lam <= lam2:
        Fs = (670.0 * sq) / lam
        branch = "13.4.1.1 a) ii)"
        branch_text = "Inelastic web buckling governs."
        fs_form = r"F_s = \frac{670\sqrt{F_y}}{h/w}"
        fs_step = (r"F_s = \frac{670\times" + tex_num(sq, 3) + r"}{"
                   + tex_num(lam, 3) + r"} = " + tex_num(Fs, 2)
                   + r"\ \text{MPa}")
    else:
        Fs = 961200.0 / (lam * lam)
        branch = "13.4.1.1 a) iii)"
        branch_text = "Elastic web buckling governs."
        fs_form = r"F_s = \frac{961\,200}{(h/w)^2}"
        fs_step = (r"F_s = \frac{961\,200}{(" + tex_num(lam, 3)
                   + r")^2} = " + tex_num(Fs, 2) + r"\ \text{MPa}")

    Vr_kN = (phi_v * Aw * Fs) / 1000.0

    return {"ok": True, "Aw": Aw, "lam": lam, "lam1": lam1, "lam2": lam2,
            "Fs": Fs, "Vr_kN": Vr_kN, "branch": branch,
            "branch_text": branch_text, "fs_form": fs_form,
            "fs_step": fs_step, "phi_v": phi_v}


# ===========================================================
# DEFLECTION
# ===========================================================


def defl_ss_udl_mm(w_kN_per_m: float, L_m: float, E_MPa: float,
                   Ix_10e6_mm4: float) -> float:
    w_N_per_mm = w_kN_per_m           # kN/m is numerically N/mm
    L_mm = L_m * 1000.0
    I = Ix_10e6_mm4 * 1e6
    return (5.0 * w_N_per_mm * (L_mm ** 4)) / (384.0 * E_MPa * I)


def defl_ss_midspan_point_mm(P_kN: float, L_m: float, E_MPa: float,
                             Ix_10e6_mm4: float) -> float:
    P_N = P_kN * 1000.0
    L_mm = L_m * 1000.0
    I = Ix_10e6_mm4 * 1e6
    return (P_N * (L_mm ** 3)) / (48.0 * E_MPa * I)


DEFLECTION_CASES = [
    ("udl", "UDL (w kN/m)"),
    ("midspan_point", "Midspan point load (P kN)"),
]

TABLE_D1_LIMITS = [
    ("custom", "Custom L / n (use the selector below)", None),
    ("industrial_floor", "Industrial - floor (L/300)", 300),
    ("industrial_inelastic_roof", "Industrial - inelastic roof (L/240)", 240),
    ("industrial_elastic_roof", "Industrial - elastic roof (L/180)", 180),
    ("crane_girder_heavy", "Crane girder 225 kN or more (L/800)", 800),
    ("crane_girder_light", "Crane girder under 225 kN (L/600)", 600),
    ("crane_lateral", "Crane runway - lateral (L/600)", 600),
    ("other_floor_crack_susceptible",
     "Other - floors, crack-susceptible finish (L/360)", 360),
    ("other_floor_no_crack", "Other - floors, not susceptible (L/300)", 300),
    ("wind_drift_building", "Wind drift - building (h/400)", 400),
    ("storey_drift_cladding", "Storey drift - cladding (h/500)", 500),
]


# ===========================================================
# MODEL-ONLY END CONDITIONS (3D viewer)
# ===========================================================

END_CASES = [
    ("pin_pin", "Pinned - pinned", "pinned", "roller"),
    ("fix_pin", "Fixed - pinned (propped)", "fixed", "roller"),
    ("fix_fix", "Fixed - fixed", "fixed", "fixed"),
    ("fix_free", "Fixed - free (cantilever)", "fixed", "free"),
]


def peak_moment_kNm(end_key, load_type, w_kN_m, P_kN, L_m):
    """Peak absolute bending moment for the model case, kN-m."""
    if load_type == "udl" and w_kN_m:
        w = float(w_kN_m)
        LL = float(L_m)
        if end_key == "fix_fix":
            return w * LL * LL / 12.0
        if end_key == "fix_free":
            return w * LL * LL / 2.0
        return w * LL * LL / 8.0
    if load_type == "point" and P_kN:
        P = float(P_kN)
        LL = float(L_m)
        if end_key == "fix_fix":
            return P * LL / 8.0
        if end_key == "fix_pin":
            return 3.0 * P * LL / 16.0
        if end_key == "fix_free":
            return P * LL
        return P * LL / 4.0
    return None


@dataclass
class _ViewerSection:
    """Minimal stand-in for the compression page's SectionProps. Only the
    attributes section_geometry.py and viewer_3d.py read."""
    designation: str
    family: str = "W"
    family_label: str = "W shapes"
    kind: str = "I"
    A_mm2: Optional[float] = None
    d_mm: Optional[float] = None
    b_mm: Optional[float] = None
    t_mm: Optional[float] = None
    w_mm: Optional[float] = None
    h_mm: Optional[float] = None
    hss_kind: Optional[str] = None


# ===========================================================
# PAGE
# ===========================================================

require_disclaimer_acceptance()
apply_theme()
render_sidebar_logo()
render_footer()

render_page_title(
    "Beam Flexure Design",
    clauses=("Cl. 11 (classification)  |  Cl. 13.5 (laterally supported)  |  "
             "Cl. 13.6 (lateral torsional buckling)  |  Cl. 13.4.1.1 "
             "(shear)  |  Table D.1 (deflection)"),
    intro=("Factored moment resistance of a W shape in major-axis bending. "
           "Every check states its clause, then shows the work."),
)

shapes, designations = load_shapes()
if not shapes:
    st.error("No section data found. Check that the CISC SST12.1 workbook "
             "is in attached_assets/ at the repository root.")
    st.stop()

# ---- sidebar ----
with st.sidebar:
    st.header("Material")
    Fy = st.number_input("Fy (MPa)", 200.0, 700.0, 345.0, 5.0, key="fFy",
                         help="Specified minimum yield strength of the "
                              "steel. 345 MPa is typical for CSA G40.21 "
                              "350W rolled W shapes.")
    E_MPa = st.number_input("E (MPa)", 150000.0, 250000.0, 200000.0, 1000.0,
                            key="fE",
                            help="Modulus of elasticity. 200 000 MPa for "
                                 "structural steel.")
    G_MPa = st.number_input("G (MPa)", 50000.0, 100000.0, 77000.0, 1000.0,
                            key="fG",
                            help="Shear modulus. 77 000 MPa for structural "
                                 "steel. Used in the LTB check only.")

    st.divider()
    st.header("Resistance factors")
    phi_b = st.number_input("phi (bending)", 0.50, 1.00, float(PHI_B), 0.05,
                            key="fphib",
                            help="Resistance factor for bending. S16 uses "
                                 "phi = 0.90.")
    phi_v = st.number_input("phi_v (shear)", 0.50, 1.00,
                            float(PHI_V_DEFAULT), 0.05, key="fphiv",
                            help="Resistance factor for shear. S16 uses "
                                 "phi_v = 0.90.")

    st.divider()
    st.header("Checks to run")
    run_ltb = st.checkbox("Lateral torsional buckling (Cl. 13.6)",
                          value=False, key="frunltb")
    run_shear = st.checkbox("Shear (Cl. 13.4.1.1)", value=False,
                            key="frunshear")
    run_defl = st.checkbox("Deflection (Table D.1)", value=False,
                           key="frundefl")

    st.divider()
    st.header("Layout")
    side_by_side = st.checkbox("Steps beside the model", value=True,
                               key="flayout",
                               help="Calculation steps in one column with "
                                    "the member model pinned beside them, "
                                    "so the numbers and the picture can be "
                                    "compared without scrolling. Untick "
                                    "for the classic stacked page.")
    if side_by_side:
        model_side = st.radio("Model panel side", ["Right", "Left"],
                              index=0, horizontal=True, key="fmodelside")
    else:
        model_side = "Right"
    viewer_h = st.select_slider("Model height (px)",
                                options=[420, 520, 640, 780, 920],
                                value=640, key="fviewh",
                                help="Height of the 3D viewer. Pick a "
                                     "taller model when the panel has the "
                                     "room.")
    st.checkbox("Expand all calculation steps", value=False,
                key="fexpandall",
                help="Every Step box on the page can also be opened and "
                     "closed individually.")


# ---- layout scaffold ----
# In side-by-side mode the model column is made sticky, so it stays in
# view while the calculation column scrolls. The :has() selector scopes
# the stickiness to the one column that contains the anchor div, leaving
# every other st.columns call on the page alone.
if side_by_side:
    md("<style>"
       "div[data-testid='stColumn']:has(div.ifs-sticky-anchor){"
       "position:sticky;top:3.2rem;align-self:flex-start;"
       "max-height:calc(100vh - 4.5rem);overflow-y:auto;"
       "padding-right:0.25rem;}"
       "</style>")
    if model_side == "Left":
        model_col, calc_col = st.columns([0.44, 0.56], gap="medium")
    else:
        calc_col, model_col = st.columns([0.56, 0.44], gap="medium")
else:
    calc_col = st.container()
    model_col = st.container()


with calc_col:
    # ---- 1. section ----
    section_heading("1. Section")
    note("Major-axis flexure of W shapes. The dimensions below are read at "
         "run time from the CISC SST12.1 workbook through sst12.py.")

    s1, s2 = st.columns([1, 2])
    with s1:
        search_query = st.text_input("Search", placeholder="e.g. W410",
                                     key="fsearch")
    with s2:
        qq = (search_query or "").lower().strip()
        filtered = [k for k in designations if qq in k.lower()] if qq \
            else designations
        if not filtered:
            st.warning("No sections match that search.")
            st.stop()
        selected_section = st.selectbox("Designation", filtered, index=0,
                                        key="fdes")

    shape = get_shape(selected_section)
    if shape is None:
        st.error("Section " + str(selected_section)
                 + " could not be loaded.")
        st.stop()

    try:
        _d = fnum(shape.get("d"), "d")
        _b = fnum(shape.get("b"), "b")
        _t = fnum(shape.get("t"), "t")
        _w = fnum(shape.get("w"), "w")
    except ValueError as exc:
        st.error("Could not read the dimensions of " + str(selected_section)
                 + ": " + str(exc))
        st.stop()

    geom = {"d": _d, "b": _b, "t": _t, "w": _w, "h": _d - 2.0 * _t}

    _area = None
    for _k in ("Area", "area", "A", "Area_mm2"):
        _v = shape.get(_k)
        if _v not in (None, ""):
            try:
                _area = float(str(_v).replace(",", "").strip())
                break
            except (ValueError, TypeError):
                pass

    st.caption("Section properties are read from the CISC SST12.1 workbook "
               "at run time. Turn on Section data on the member model to "
               "see them against the shape they belong to.")

    # ---- 2. demand ----
    section_heading("2. Design Actions")
    note("Enter the factored actions to run the demand checks. Leave them "
         "off to see resistances only.")

    d1, d2 = st.columns(2)
    with d1:
        apply_moment = st.checkbox(
            "Apply a factored moment Mf", value=False, key="fapplym",
            help="Mf is the FACTORED BENDING MOMENT: the bending demand "
                 "at the critical section from the governing factored "
                 "load combination (e.g. 1.25 x dead + 1.5 x live), in "
                 "kN-m. It is compared against the factored moment "
                 "resistance Mr.")
        Mf_kNm = 0.0
        if apply_moment:
            Mf_kNm = st.number_input(
                "Mf (kN-m)", 0.0, 1e6, 100.0, 10.0, key="fMf",
                help="The factored (ultimate) design moment the beam "
                     "must resist. The demand side of Mf / Mr.")
    with d2:
        apply_shear = st.checkbox(
            "Apply a factored shear Vf", value=False, key="fapplyv",
            help="Vf is the FACTORED SHEAR FORCE: the vertical shear "
                 "demand at the critical section from the governing "
                 "factored load combination, in kN. It is carried by the "
                 "web and compared against the factored shear resistance "
                 "Vr.")
        Vf_kN = 0.0
        if apply_shear:
            Vf_kN = st.number_input(
                "Vf (kN)", 0.0, 1e6, 100.0, 10.0, key="fVf",
                help="The factored (ultimate) design shear the web must "
                     "carry. The demand side of Vf / Vr.")

    with st.expander("What do these symbols mean?"):
        md("<p style='line-height:1.7'>"
           "<b>M<sub>f</sub></b> - factored bending moment: the demand, "
           "from factored (ultimate) loads. <b>M<sub>r</sub></b> - "
           "factored moment resistance: the capacity, phi times the "
           "nominal resistance.<br>"
           "<b>V<sub>f</sub></b> - factored shear force: the demand. "
           "<b>V<sub>r</sub></b> - factored shear resistance: the "
           "capacity of the web.<br>"
           "<b>Factored</b> means load factors (e.g. 1.25D + 1.5L) are "
           "already applied - these are ultimate-limit-state numbers, "
           "not service loads.<br>"
           "<b>phi</b> - resistance factor (0.90) covering variability "
           "in material and fabrication.<br>"
           "<b>F<sub>y</sub></b> - yield strength. "
           "<b>L<sub>b</sub></b> - unbraced length between lateral "
           "supports of the compression flange. "
           "<b>omega<sub>2</sub></b> - moment gradient factor for LTB."
           "</p>")

    note("Common term: <i>&radic;F<sub>y</sub></i> = &radic;" + num(Fy, 0)
         + " = <b>" + num(math.sqrt(Fy), 3) + "</b>")

    # ---- 3. Table 2 classification ----
    st.divider()
    section_heading("3. Section Classification &mdash; Table 2 "
                    "(Flexural Compression)")
    note("Cl. 11.2 sends elements in flexural compression to Table 2. Only "
         "the plate elements a W shape actually has are listed. Tick an "
         "element to see the work; ticked elements are also the ones "
         "coloured on the 3D model.")

    cls_info = classify_section(geom, float(Fy))
    for chk in cls_info["checks"]:
        on = st.checkbox(chk.label, value=False, key="fsel_" + chk.key)
        if on:
            render_t2(chk)
            st.markdown("---")

    section_class = int(cls_info["class_section"])
    class_desc = {1: "plastic", 2: "compact", 3: "non-compact",
                  4: "slender"}[section_class]

    sub_heading("Governing class")
    st.latex(r"\text{Class} = \max\left(\text{flange } "
             + str(cls_info["class_flange"]) + r",\ \text{web } "
             + str(cls_info["class_web"]) + r"\right) = \textbf{Class "
             + str(section_class) + r"}")
    note("Governed by: <b>" + cls_info["governing"] + "</b> &nbsp;|&nbsp; "
         "b/2t = <b>" + num(cls_info["ratio_flange"], 2)
         + "</b> &nbsp;|&nbsp; h/w = <b>" + num(cls_info["ratio_web"], 2)
         + "</b>")

    if section_class <= 2:
        st.success("Class " + str(section_class) + " (" + class_desc
                   + "). The full plastic moment is available.")
    elif section_class == 3:
        st.warning("Class 3 (non-compact). The yield moment only.")
    else:
        st.error("Class 4 (slender). An effective section modulus is "
                 "required.")

    if not side_by_side:
        sub_heading("Cross-section and stress distribution")
        render_section_diagrams(section_class, geom)
    else:
        st.caption("The dimensioned cross-section and the stress "
                   "distribution are shown in the model panel, beside "
                   "these steps.")

    if section_class == 4:
        with step("Class 4 - effective section modulus Se"):
            indent("Each slender element is reduced to the width that "
                   "just meets its Class 3 limit, then the section is "
                   "rebuilt from the effective plates.")
            for s in se_steps(geom, float(Fy)):
                st.latex(s)

    # ---- 4. Cl 13.5 ----
    st.divider()
    section_heading("4. Moment Resistance &mdash; Laterally Supported "
                    "(Cl. 13.5)")
    note("This is the resistance of the cross-section itself, with the "
         "compression flange held against lateral movement over its whole "
         "length.")

    mr_lat = Mr_laterally_supported(shape, geom, float(Fy), section_class,
                                    float(phi_b))
    if not mr_lat.get("ok"):
        st.error("Cl. 13.5 could not be evaluated: "
                 + str(mr_lat.get("error")))
        st.stop()

    with step("Step 1 - select the modulus from the class"):
        indent("Class " + str(section_class) + " (" + class_desc
               + ") sends this section to " + mr_lat["clause"] + ".")
        st.latex(mr_lat["formula"])

    with step("Step 2 - convert the tabulated modulus to mm^3"):
        st.latex(mr_lat["steps"][0])

    with step("Step 3 - substitute"):
        st.latex(mr_lat["steps"][1])

    with step("Step 4 - convert to kN-m"):
        st.latex(mr_lat["steps"][2])

    Mr_lat_kNm = float(mr_lat["Mr_kNm"])
    st.success("Mr = " + num(Mr_lat_kNm, 1) + " kN-m  (" + mr_lat["mode"]
               + ", phi = " + num(phi_b, 2) + ")")

    # ---- 5. Cl 13.6 ----
    Mr_ltb_kNm = None
    ltb = None
    omega2_used = None
    Lb_mm = None

    if run_ltb:
        st.divider()
        section_heading("5. Lateral Torsional Buckling (Cl. 13.6)")
        note("Between brace points the compression flange can displace "
             "sideways and twist. Cl. 13.6 first finds the elastic "
             "critical moment Mu, then decides whether the beam reaches "
             "its reference moment before buckling.")

        l1, l2 = st.columns(2)
        with l1:
            Lb_m = st.number_input(
                "Unbraced length Lb (m)", 0.1, 60.0, 3.0, 0.5, key="fLb",
                help="Lb is the distance between points where the "
                     "compression flange is held against sideways "
                     "movement - supports, joists, or discrete braces. "
                     "Turn on Lateral bracing on the model to see them.")
            Lb_mm = Lb_m * 1000.0
        with l2:
            omega_mode = st.selectbox(
                "How to obtain omega2",
                ["Preset loading case",
                 "Eq. 3 - linear moment gradient",
                 "Eq. 2 - general four-point"],
                index=0, key="fom2mode",
                help="omega2 accounts for the shape of the moment "
                     "diagram over the unbraced length. Uniform moment "
                     "is the worst case at 1.00.")

        with step("Step 1 - the moment gradient factor omega2"):
            if omega_mode.startswith("Preset"):
                case_key = st.selectbox(
                    "Loading case", [c[0] for c in OMEGA2_CASES],
                    format_func=lambda k: dict(
                        (a, b) for a, b, _c in OMEGA2_CASES)[k],
                    index=0, key="fom2case")
                omega2_used = omega2_from_case(case_key)
                indent("A uniform moment over the whole unbraced length "
                       "is the worst case, so it takes omega2 = 1.00. "
                       "Any variation in moment along the segment leaves "
                       "part of the flange less stressed and raises "
                       "omega2.")
                st.latex(r"\omega_2 = " + tex_num(omega2_used, 2))
            elif omega_mode.startswith("Eq. 3"):
                kappa = st.slider("kappa = M_small / M_large  "
                                  "(positive = double curvature)",
                                  -1.0, 1.0, 0.0, 0.05, key="fkappa")
                omega2_used = omega2_linear(kappa)
                st.latex(r"\omega_2 = 1.75 + 1.05\,\kappa + "
                         r"0.3\,\kappa^2 \leq 2.5")
                st.latex(r"\omega_2 = 1.75 + 1.05(" + tex_num(kappa, 2)
                         + r") + 0.3(" + tex_num(kappa, 2) + r")^2 = "
                         + tex_num(omega2_used, 3))
            else:
                q1, q2, q3, q4 = st.columns(4)
                with q1:
                    Mmax_in = st.number_input("M_max", 0.0, 1e6, 100.0,
                                              10.0, key="fMmax")
                with q2:
                    Ma_in = st.number_input("M_a (L/4)", 0.0, 1e6, 50.0,
                                            10.0, key="fMa")
                with q3:
                    Mb_in = st.number_input("M_b (L/2)", 0.0, 1e6, 80.0,
                                            10.0, key="fMb")
                with q4:
                    Mc_in = st.number_input("M_c (3L/4)", 0.0, 1e6, 50.0,
                                            10.0, key="fMc")
                omega2_used = omega2_general(Mmax_in, Ma_in, Mb_in, Mc_in)
                st.latex(r"\omega_2 = \frac{4 M_{max}}{\sqrt{M_{max}^2 "
                         r"+ 4M_a^2 + 7M_b^2 + 4M_c^2}} \leq 2.5")
                _den = math.sqrt(Mmax_in ** 2 + 4 * Ma_in ** 2
                                 + 7 * Mb_in ** 2 + 4 * Mc_in ** 2)
                st.latex(r"\omega_2 = \frac{4(" + tex_num(Mmax_in, 1)
                         + r")}{" + tex_num(_den, 2) + r"} = "
                         + tex_num(omega2_used, 3))

        ltb = ltb_resistance_13_6(shape, geom, float(Fy), section_class,
                                  float(Lb_mm), float(omega2_used),
                                  float(phi_b), float(E_MPa), float(G_MPa))

        if not ltb.get("ok"):
            st.warning("Cl. 13.6 could not be evaluated: "
                       + str(ltb.get("error")))
        else:
            with step("Step 2 - the elastic critical moment Mu (Eq. 1)"):
                indent("The first term inside the root is St. Venant "
                       "torsion, the second is warping torsion. A deep, "
                       "thin-flanged beam leans on warping; a stocky one "
                       "leans on GJ.")
                st.latex(r"M_u = \frac{\omega_2 \pi}{L}\sqrt{E I_y G J + "
                         r"\left(\frac{\pi E}{L}\right)^2 I_y C_w}")
                st.latex(r"I_y = " + tex_num(ltb["Iy"], 0)
                         + r"\ \text{mm}^4"
                         r"\qquad J = " + tex_num(ltb["J"], 0)
                         + r"\ \text{mm}^4"
                         r"\qquad C_w = " + tex_num(ltb["Cw"], 0)
                         + r"\ \text{mm}^6")
                st.latex(r"E I_y G J = " + tex_num(ltb["term1"], 0))
                st.latex(r"\left(\frac{\pi E}{L}\right)^2 I_y C_w = "
                         + tex_num(ltb["term2"], 0))
                st.latex(r"M_u = \frac{" + tex_num(ltb["omega2"], 3)
                         + r"\pi}{" + tex_num(Lb_mm, 0) + r"}\sqrt{"
                         + tex_num(ltb["term1"] + ltb["term2"], 0)
                         + r"} = " + tex_num(ltb["Mu_kNm"], 1)
                         + r"\ \text{kN}\cdot\text{m}")

            with step("Step 3 - the reference moment"):
                indent(ltb["ref_note"])
                st.latex(ltb["ref_sym"] + r" = "
                         + tex_num(ltb["Mref_kNm"], 1)
                         + r"\ \text{kN}\cdot\text{m}")

            with step("Step 4 - which branch of Cl. 13.6 applies"):
                st.latex(r"0.67\," + ltb["ref_sym"] + r" = 0.67("
                         + tex_num(ltb["Mref_kNm"], 1) + r") = "
                         + tex_num(0.67 * ltb["Mref_kNm"], 1)
                         + r"\ \text{kN}\cdot\text{m}")
                if ltb["branch"] == "inelastic":
                    st.latex(r"M_u = " + tex_num(ltb["Mu_kNm"], 1)
                             + r" > 0.67\," + ltb["ref_sym"]
                             + r"\ \Rightarrow\ \text{inelastic "
                             r"lateral torsional buckling}")
                    st.latex(r"M_r = 1.15\,\phi\," + ltb["ref_sym"]
                             + r"\left(1 - \frac{0.28\," + ltb["ref_sym"]
                             + r"}{M_u}\right) \leq \phi\,"
                             + ltb["ref_sym"])
                    _inner = 1.0 - 0.28 * ltb["Mref_kNm"] / ltb["Mu_kNm"]
                    _raw = 1.15 * phi_b * ltb["Mref_kNm"] * _inner
                    st.latex(r"M_r = 1.15(" + tex_num(phi_b, 2) + r")("
                             + tex_num(ltb["Mref_kNm"], 1)
                             + r")\left(1 - \frac{0.28("
                             + tex_num(ltb["Mref_kNm"], 1) + r")}{"
                             + tex_num(ltb["Mu_kNm"], 1) + r"}\right) = "
                             + tex_num(_raw, 1)
                             + r"\ \text{kN}\cdot\text{m}")
                    st.latex(r"\phi\," + ltb["ref_sym"] + r" = "
                             + tex_num(phi_b, 2) + r"("
                             + tex_num(ltb["Mref_kNm"], 1) + r") = "
                             + tex_num(phi_b * ltb["Mref_kNm"], 1)
                             + r"\ \text{kN}\cdot\text{m}")
                    if ltb["capped"]:
                        indent("The bracketed expression exceeds the "
                               "cap, so the cross-section limit governs.")
                else:
                    st.latex(r"M_u = " + tex_num(ltb["Mu_kNm"], 1)
                             + r" \leq 0.67\," + ltb["ref_sym"]
                             + r"\ \Rightarrow\ \text{elastic "
                             r"lateral torsional buckling}")
                    st.latex(r"M_r = \phi\,M_u = " + tex_num(phi_b, 2)
                             + r"(" + tex_num(ltb["Mu_kNm"], 1)
                             + r") = " + tex_num(ltb["Mr_kNm"], 1)
                             + r"\ \text{kN}\cdot\text{m}")

            Mr_ltb_kNm = float(ltb["Mr_kNm"])

            with step("Step 5 - compare with the laterally supported "
                      "resistance"):
                st.latex(r"M_r = \min\left(" + tex_num(Mr_lat_kNm, 1)
                         + r"_{\ \text{Cl. }13.5},\ "
                         + tex_num(Mr_ltb_kNm, 1)
                         + r"_{\ \text{Cl. }13.6}\right) = "
                         + tex_num(min(Mr_lat_kNm, Mr_ltb_kNm), 1)
                         + r"\ \text{kN}\cdot\text{m}")
            if Mr_ltb_kNm < Mr_lat_kNm - 1e-9:
                st.warning("Lateral torsional buckling governs at Lb = "
                           + num(Lb_mm / 1000.0, 2) + " m: "
                           + num(Mr_ltb_kNm, 1) + " kN-m against "
                           + num(Mr_lat_kNm, 1) + " kN-m.")
            else:
                st.success("The cross-section governs. The bracing is "
                           "close enough that the full Cl. 13.5 "
                           "resistance is available.")

            with step("Beam elevation"):
                _ltb_load_type = "point" \
                    if omega_mode.startswith("Preset") \
                    and st.session_state.get("fom2case") == "midspan_point" \
                    else "udl"
                st.markdown(beam_elevation_svg(braced=False,
                                               load_type=_ltb_load_type),
                            unsafe_allow_html=True)

            with step("Mr against unbraced length"):
                try:
                    _Zx = _f(shape.get("Zx"))
                    _Sx = _f(shape.get("Sx"))
                    if _Zx is not None and _Sx is not None:
                        _Mp_kNm = _Zx * 1e3 * float(Fy) / 1e6
                        _My_kNm = _Sx * 1e3 * float(Fy) / 1e6
                        _Mref = ltb["Mref_kNm"]
                        _L_pts: List[float] = []
                        _Mr_pts: List[float] = []
                        _Li = 500.0
                        _Lmax = max(15000.0, float(Lb_mm) * 1.5)
                        while _Li <= _Lmax:
                            _Mu_i = critical_elastic_moment_kNm(
                                _Li, ltb["Iy"], ltb["J"], ltb["Cw"],
                                float(omega2_used), float(E_MPa),
                                float(G_MPa))
                            if _Mu_i > 0.67 * _Mref:
                                _Mr_i = min(1.15 * phi_b * _Mref
                                            * (1.0 - 0.28 * _Mref / _Mu_i),
                                            phi_b * _Mref)
                            else:
                                _Mr_i = phi_b * _Mu_i
                            _L_pts.append(_Li)
                            _Mr_pts.append(_Mr_i)
                            _Li += 250.0

                        st.markdown(ltb_curve_svg(
                            L_list=_L_pts, Mr_list=_Mr_pts,
                            phiMp=phi_b * _Mp_kNm,
                            phiMy=phi_b * _My_kNm,
                            section_class=section_class,
                            L_current_mm=float(Lb_mm),
                            Mr_current=float(Mr_ltb_kNm)),
                            unsafe_allow_html=True)
                        st.caption("Plateau on the left, inelastic "
                                   "transition in the middle, elastic "
                                   "branch on the right. The marker is "
                                   "the current unbraced length.")
                    else:
                        st.info("The curve needs Zx and Sx, which are "
                                "not carried for this section.")
                except Exception as _exc:
                    st.info("The Mr against Lb curve is unavailable: "
                            + str(_exc))

    # governing moment resistance
    Mr_gov_kNm = Mr_lat_kNm
    Mr_gov_clause = "Cl. 13.5"
    if Mr_ltb_kNm is not None and Mr_ltb_kNm < Mr_lat_kNm:
        Mr_gov_kNm = Mr_ltb_kNm
        Mr_gov_clause = "Cl. 13.6"

    # ---- 6. shear ----
    Vr_kN = None
    if run_shear:
        st.divider()
        section_heading("6. Shear Resistance (Cl. 13.4.1.1)")
        note("The web carries the shear. Whether it yields or buckles "
             "first depends only on h/w and the yield strength.")

        web_type = st.radio("Web type",
                            ["Unstiffened web - Cl. 13.4.1.1 a)",
                             "Stiffened web - Cl. 13.4.1.1 b)"],
                            index=0, horizontal=True, key="fwebtype")

        a_mm = None
        if web_type.startswith("Stiffened"):
            a_mm = st.number_input("Transverse stiffener spacing a (mm)",
                                   1.0, 20000.0, 800.0, 50.0, key="fa")

        h_v = float(geom["h"])
        w_v = float(geom["w"])

        try:
            if web_type.startswith("Unstiffened"):
                sh = shear_unstiffened_13_4_1_1a(float(Fy), h_v, w_v,
                                                 float(phi_v))

                with step("Step 1 - the shear area"):
                    indent("Cl. 13.4.1.1 takes the web only: the clear "
                           "depth between flanges times the web "
                           "thickness.")
                    st.latex(r"A_w = h\,w = " + tex_num(h_v, 1)
                             + r" \times " + tex_num(w_v, 1) + r" = "
                             + tex_num(sh["Aw"], 0) + r"\ \text{mm}^2")

                with step("Step 2 - the web slenderness"):
                    st.latex(r"\frac{h}{w} = \frac{" + tex_num(h_v, 1)
                             + r"}{" + tex_num(w_v, 1) + r"} = "
                             + tex_num(sh["lam"], 3))

                with step("Step 3 - the two branch boundaries"):
                    st.latex(r"\frac{1014}{\sqrt{F_y}} = \frac{1014}{"
                             + tex_num(math.sqrt(Fy), 3) + r"} = "
                             + tex_num(sh["lam1"], 2))
                    st.latex(r"\frac{1435}{\sqrt{F_y}} = \frac{1435}{"
                             + tex_num(math.sqrt(Fy), 3) + r"} = "
                             + tex_num(sh["lam2"], 2))
                    indent(sh["branch_text"] + "  Branch used: "
                           + sh["branch"] + ".")

                with step("Step 4 - the ultimate shear stress"):
                    st.latex(sh["fs_form"])
                    st.latex(sh["fs_step"])

                with step("Step 5 - the factored shear resistance"):
                    st.latex(r"V_r = \phi_v A_w F_s = " + tex_num(phi_v, 2)
                             + r" \times " + tex_num(sh["Aw"], 0)
                             + r" \times " + tex_num(sh["Fs"], 2)
                             + r" = " + tex_num(sh["Vr_kN"], 1)
                             + r"\ \text{kN}")

                Vr_kN = float(sh["Vr_kN"])
                Fs_MPa = float(sh["Fs"])
                lam_shear = float(sh["lam"])
                st.success("Vr = " + num(Vr_kN, 1) + " kN  (" + sh["branch"]
                           + ", phi_v = " + num(phi_v, 2) + ")")
            else:
                if stiffened_web_shear_CSA13_4 is None:
                    raise ValueError("main.py does not expose "
                                     "stiffened_web_shear_CSA13_4.")
                Aw = h_v * w_v
                res = stiffened_web_shear_CSA13_4(
                    Fy_MPa=float(Fy), hw_over_tw=h_v / w_v,
                    a_over_h=float(a_mm) / h_v, Aw_mm2=Aw,
                    phi_v=float(phi_v), h_mm=h_v, tw_mm=w_v,
                    a_mm=float(a_mm))
                Vr_kN = float(res["Vr_kN"])
                Fs_MPa = float(res["Fs_MPa"])
                lam_shear = h_v / w_v

                with step("Step 1 - the shear area and panel aspect "
                          "ratio"):
                    st.latex(r"A_w = h\,w = " + tex_num(Aw, 0)
                             + r"\ \text{mm}^2"
                             r"\qquad \frac{a}{h} = \frac{"
                             + tex_num(a_mm, 0) + r"}{" + tex_num(h_v, 1)
                             + r"} = " + tex_num(float(a_mm) / h_v, 3))

                with step("Step 2 - the clause trace from main.py"):
                    for item in res.get("trace", []):
                        s = str(item).strip()
                        if s.startswith("$$") and s.endswith("$$"):
                            st.latex(s[2:-2].strip())
                        else:
                            indent(s)

                with step("Step 3 - the factored shear resistance"):
                    st.latex(r"V_r = \phi_v A_w F_s = " + tex_num(phi_v, 2)
                             + r" \times " + tex_num(Aw, 0) + r" \times "
                             + tex_num(Fs_MPa, 2) + r" = "
                             + tex_num(Vr_kN, 1) + r"\ \text{kN}")
                for wmsg in res.get("warnings", []):
                    st.warning(str(wmsg))
                st.success("Vr = " + num(Vr_kN, 1)
                           + " kN  (Cl. 13.4.1.1 b) "
                           + str(res.get("region", "")) + ")")

            with step("Shear curve - Fs against h/w"):
                _kv = None
                if web_type.startswith("Stiffened") and a_mm and h_v > 0:
                    _asp = float(a_mm) / h_v
                    _kv = (4.0 + 5.34 / _asp ** 2) if _asp < 1.0 \
                        else (5.34 + 4.0 / _asp ** 2)
                st.markdown(shear_fs_curve_svg(
                    Fy=float(Fy), h_over_w_actual=lam_shear,
                    Fs_actual=Fs_MPa,
                    stiffened=web_type.startswith("Stiffened"), kv=_kv),
                    unsafe_allow_html=True)
                st.caption("Yield plateau, then inelastic buckling, then "
                           "elastic buckling. The marker is this "
                           "section.")

        except Exception as exc:
            st.error("Shear calculation error: " + str(exc))

    # ---- 7. deflection ----
    delta_mm = None
    delta_limit_mm = None
    if run_defl:
        st.divider()
        section_heading("7. Deflection (Serviceability, Table D.1)")
        note("Serviceability, so unfactored loads and no resistance "
             "factor. Simply supported, elastic, strong axis.")

        Ix_raw = _f(shape.get("Ix"))
        if Ix_raw is None:
            st.warning("Ix is not carried for this section, so the "
                       "deflection check cannot run.")
        else:
            f1, f2 = st.columns(2)
            with f1:
                defl_case = st.selectbox("Loading case",
                                         [c[0] for c in DEFLECTION_CASES],
                                         format_func=lambda k: dict(
                                             DEFLECTION_CASES)[k],
                                         index=0, key="fdeflcase")
                L_defl = st.number_input("Span L (m)", 0.5, 60.0, 6.0, 0.5,
                                         key="fLdefl")
            with f2:
                if defl_case == "udl":
                    w_load = st.number_input("w (kN/m)", 0.0, 1e5, 10.0,
                                             1.0, key="fwload")
                    P_load = 0.0
                else:
                    P_load = st.number_input("P (kN)", 0.0, 1e5, 50.0,
                                             5.0, key="fPload")
                    w_load = 0.0
                _td1_key = st.selectbox(
                    "Limit from Table D.1",
                    [k for k, _l, _d in TABLE_D1_LIMITS],
                    format_func=lambda k: dict(
                        (a, b) for a, b, _c in TABLE_D1_LIMITS)[k],
                    index=0, key="ftd1")
                _td1_div = dict((a, c) for a, _b, c in TABLE_D1_LIMITS
                                ).get(_td1_key)
                if _td1_div is None:
                    defl_div = st.selectbox("Custom L / n",
                                            [180, 240, 360, 480],
                                            format_func=lambda x: "L/"
                                            + str(x),
                                            index=1, key="fdefldiv")
                else:
                    defl_div = _td1_div
                    st.caption("Table D.1 limit: L / " + str(_td1_div))

            L_mm_defl = L_defl * 1000.0
            I_mm4 = Ix_raw * 1e6

            with step("Step 1 - put every input in N and mm"):
                if defl_case == "udl":
                    st.latex(r"w = " + tex_num(w_load, 2)
                             + r"\ \text{kN/m} = " + tex_num(w_load, 2)
                             + r"\ \text{N/mm}")
                else:
                    st.latex(r"P = " + tex_num(P_load, 1)
                             + r"\ \text{kN} = "
                             + tex_num(P_load * 1000.0, 0)
                             + r"\ \text{N}")
                st.latex(r"L = " + tex_num(L_mm_defl, 0) + r"\ \text{mm}"
                         r"\qquad E = " + tex_num(E_MPa, 0)
                         + r"\ \text{MPa}"
                         r"\qquad I_x = " + tex_num(I_mm4, 0)
                         + r"\ \text{mm}^4")

            with step("Step 2 - the elastic deflection"):
                if defl_case == "udl":
                    delta_mm = defl_ss_udl_mm(w_load, L_defl, float(E_MPa),
                                              Ix_raw)
                    st.latex(r"\delta_{max} = \frac{5\,w L^4}{384\,E I}")
                    st.latex(r"\delta_{max} = \frac{5("
                             + tex_num(w_load, 2) + r")("
                             + tex_num(L_mm_defl, 0) + r")^4}{384("
                             + tex_num(E_MPa, 0) + r")("
                             + tex_num(I_mm4, 0) + r")} = "
                             + tex_num(delta_mm, 2) + r"\ \text{mm}")
                else:
                    delta_mm = defl_ss_midspan_point_mm(P_load, L_defl,
                                                        float(E_MPa),
                                                        Ix_raw)
                    st.latex(r"\delta_{max} = \frac{P L^3}{48\,E I}")
                    st.latex(r"\delta_{max} = \frac{("
                             + tex_num(P_load * 1000.0, 0) + r")("
                             + tex_num(L_mm_defl, 0) + r")^3}{48("
                             + tex_num(E_MPa, 0) + r")("
                             + tex_num(I_mm4, 0) + r")} = "
                             + tex_num(delta_mm, 2) + r"\ \text{mm}")

            with step("Step 3 - the allowable limit"):
                delta_limit_mm = L_mm_defl / float(defl_div)
                st.latex(r"\delta_{allow} = \frac{L}{" + str(defl_div)
                         + r"} = \frac{" + tex_num(L_mm_defl, 0) + r"}{"
                         + str(defl_div) + r"} = "
                         + tex_num(delta_limit_mm, 2) + r"\ \text{mm}")

            with step("Step 4 - compare"):
                _u = delta_mm / delta_limit_mm if delta_limit_mm > 0 \
                    else float("inf")
                if delta_mm <= delta_limit_mm:
                    st.latex(r"\delta_{max} = " + tex_num(delta_mm, 2)
                             + r" \leq " + tex_num(delta_limit_mm, 2)
                             + r"\qquad\textbf{PASS}")
                else:
                    st.latex(r"\delta_{max} = " + tex_num(delta_mm, 2)
                             + r" > " + tex_num(delta_limit_mm, 2)
                             + r"\qquad\textbf{FAIL}")
            _u = delta_mm / delta_limit_mm if delta_limit_mm > 0 \
                else float("inf")
            if delta_mm <= delta_limit_mm:
                st.success("Serviceability satisfied at "
                           + num(100.0 * _u, 1) + " percent of the limit.")
            else:
                st.error("Deflection exceeds the limit by "
                         + num(100.0 * _u - 100.0, 1) + " percent. "
                         "Increase Ix or reduce the span.")

    # ---- 8. results ----
    st.divider()
    section_heading("8. Results")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Mr (kN-m)", "{:,.1f}".format(Mr_gov_kNm))
    m2.metric("Section class", str(section_class))
    m3.metric("Vr (kN)", "{:,.1f}".format(Vr_kN) if Vr_kN else DASH)
    m4.metric("Deflection (mm)",
              "{:,.2f}".format(delta_mm) if delta_mm is not None else DASH)
    note("Governing moment clause: <b>" + Mr_gov_clause
         + "</b> &nbsp;|&nbsp; phi = " + num(phi_b, 2) + " &nbsp;|&nbsp; "
         + mr_lat["mode"]
         + (" &nbsp;|&nbsp; Lb = " + num((Lb_mm or 0) / 1000.0, 2) + " m"
            if Lb_mm else ""))

    section_heading("Demand versus capacity")
    if not apply_moment or Mf_kNm <= 0:
        st.info("Enter a factored moment Mf in section 2 to run the "
                "demand check.")
    else:
        U = Mf_kNm / Mr_gov_kNm
        pct = 100.0 * U
        st.latex(r"U = \frac{M_f}{M_r} = \frac{" + tex_num(Mf_kNm, 1)
                 + r"}{" + tex_num(Mr_gov_kNm, 1) + r"} = "
                 + tex_num(U, 3) + r" = " + tex_num(pct, 1) + r"\%")
        st.progress(min(U, 1.0))
        r1, r2, r3 = st.columns(3)
        r1.metric("Utilisation", "{:.1f} %".format(pct))
        r2.metric("Capacity used", "{:,.1f} kN-m".format(Mf_kNm))
        if U <= 1.0:
            r3.metric("Remaining",
                      "{:,.1f} kN-m".format(Mr_gov_kNm - Mf_kNm),
                      delta="{:.1f} % spare".format(100.0 - pct))
            st.success("PASS  -  U = " + num(U, 3) + " (" + num(pct, 1)
                       + " percent of capacity used, " + num(100.0 - pct, 1)
                       + " percent spare).")
        else:
            r3.metric("Shortfall",
                      "{:,.1f} kN-m".format(Mf_kNm - Mr_gov_kNm),
                      delta="{:.1f} % over".format(pct - 100.0),
                      delta_color="inverse")
            st.error("FAIL  -  U = " + num(U, 3) + " (" + num(pct, 1)
                     + " percent of capacity used, " + num(pct - 100.0, 1)
                     + " percent over). Increase the section or reduce "
                     "the unbraced length.")

    if apply_shear and Vf_kN > 0:
        if Vr_kN:
            Uv = Vf_kN / Vr_kN
            st.latex(r"U_v = \frac{V_f}{V_r} = \frac{" + tex_num(Vf_kN, 1)
                     + r"}{" + tex_num(Vr_kN, 1) + r"} = "
                     + tex_num(Uv, 3))
            if Uv <= 1.0:
                st.success("Shear PASS  -  Uv = " + num(Uv, 3) + ".")
            else:
                st.error("Shear FAIL  -  Uv = " + num(Uv, 3) + ".")
        else:
            st.info("Enable the shear check in the sidebar to compare Vf "
                    "against Vr.")


# ===========================================================
# MEMBER MODEL PANEL
#
# Rendered inside a fragment where the Streamlit version has one, so
# changing a model-only control reruns just this panel instead of the
# whole page. The viewer itself also saves its camera, toggles and
# behaviour mode to sessionStorage, so it no longer resets when any
# input changes.
# ===========================================================


def _member_model_body() -> None:
    c1, c2 = st.columns(2)
    with c1:
        _span_m = st.number_input("Span L (m) - model only", 0.5, 60.0,
                                  6.0, 0.5, key="model_span_m")
        _end_key = st.selectbox(
            "End conditions", [c[0] for c in END_CASES],
            format_func=lambda k: dict(
                (a, b) for a, b, _c, _d in END_CASES)[k],
            index=0, key="model_ends",
            help="How the beam is held at each end. A fixed end attracts "
                 "hogging moment; a free end makes a cantilever.")
    with c2:
        _lb_model_m = st.number_input(
            "Unbraced length Lb (m) - model only", 0.1, 60.0,
            float((Lb_mm or 3000.0) / 1000.0), 0.5, key="model_lb_m",
            help="Spacing of the lateral braces drawn on the model. Turn "
                 "on Lateral bracing to see them.")
        _load_type = st.selectbox(
            "Load pattern", ["udl", "point", "none"],
            format_func=lambda k: {
                "udl": "UDL (w kN/m)",
                "point": ("Tip point load (P kN)"
                          if st.session_state.get("model_ends")
                          == "fix_free"
                          else "Midspan point load (P kN)"),
                "none": "Uniform moment"}[k],
            index=0, key="model_load_type")

    _end_bottom = dict((a, c) for a, _b, c, _d in END_CASES)[_end_key]
    _end_top = dict((a, d) for a, _b, _c, d in END_CASES)[_end_key]

    _w_model = None
    _p_model = None
    if _load_type == "udl":
        _w_model = st.number_input("w (kN/m)", 0.0, 1e5, 10.0, 1.0,
                                   key="model_w")
    elif _load_type == "point":
        _p_model = st.number_input("P (kN)", 0.0, 1e5, 50.0, 5.0,
                                   key="model_p")

    _sec = _ViewerSection(designation=str(selected_section), A_mm2=_area,
                          d_mm=float(geom["d"]), b_mm=float(geom["b"]),
                          t_mm=float(geom["t"]), w_mm=float(geom["w"]),
                          h_mm=float(geom["h"]))

    def _row(group, symbol, value, unit, nd=1):
        if value is None:
            return None
        try:
            v = "{:,.{}f}".format(float(value), nd)
        except (ValueError, TypeError):
            v = str(value)
        return {"group": group, "symbol": symbol, "value": v, "unit": unit}

    _props = [
        _row("Geometry", "d", geom["d"], "mm"),
        _row("Geometry", "b", geom["b"], "mm"),
        _row("Geometry", "t", geom["t"], "mm"),
        _row("Geometry", "w", geom["w"], "mm"),
        _row("Geometry", "h", geom["h"], "mm"),
        _row("Geometry", "A", _area, "mm2", 0),
        _row("Table 2 ratios", "b/2t", cls_info["ratio_flange"], "", 2),
        _row("Table 2 ratios", "h/w", cls_info["ratio_web"], "", 2),
        _row("Flexure", "Zx", shape.get("Zx"), "10^3 mm3", 0),
        _row("Flexure", "Sx", shape.get("Sx"), "10^3 mm3", 0),
        _row("Flexure", "Ix", shape.get("Ix"), "10^6 mm4", 1),
        _row("LTB", "Iy", shape.get("Iy"), "10^6 mm4", 1),
        _row("LTB", "J", shape.get("J"), "10^3 mm4", 1),
        _row("LTB", "Cw", shape.get("Cw"), "10^9 mm6", 1),
        _row("Material", "Fy", Fy, "MPa", 0),
    ]
    _props = [p for p in _props if p is not None]

    _L_mm = float(_span_m) * 1000.0
    _Lb_model_mm = min(float(_lb_model_m) * 1000.0, _L_mm)

    # The y entry draws the end symbols and sets the span. The x entry
    # carries Lb, which drives the brace marks and the LTB half-wave.
    _supports = {
        "ends": _end_key,
        "y": {"K": 1.0, "L": _L_mm, "bottom": _end_bottom,
              "top": _end_top},
        "x": {"K": 1.0, "L": _Lb_model_mm, "bottom": _end_bottom,
              "top": _end_top},
    }

    _load = {"type": _load_type, "w_kN_m": _w_model, "P_kN": _p_model}

    _e2 = [{"key": "t2_flange", "label": "Flange b/2t", "zone": "flange",
            "cls": int(cls_info["class_flange"])},
           {"key": "t2_web", "label": "Web h/w", "zone": "web",
            "cls": int(cls_info["class_web"])}]

    _mf = peak_moment_kNm(_end_key, _load_type, _w_model, _p_model,
                          _span_m)
    if apply_moment and Mf_kNm > 0:
        _mf = float(Mf_kNm)

    _util = (_mf / Mr_gov_kNm) if (_mf is not None and Mr_gov_kNm) \
        else None

    _results = {"util": _util, "Mr_kNm": float(Mr_gov_kNm),
                "Mf_kNm": _mf, "section_class": section_class}

    viewer_3d_flexure.render_beam(_sec, length_mm=_L_mm,
                                  height=int(viewer_h),
                                  supports=_supports, load=_load,
                                  elements_t2=_e2, results=_results,
                                  props=_props, show_diagnostics=False)


if hasattr(st, "fragment"):
    _member_model = st.fragment(_member_model_body)
else:
    _member_model = _member_model_body


with model_col:
    md("<div class='ifs-sticky-anchor'></div>")
    if not side_by_side:
        st.divider()
    section_heading("Member Model")
    note("Built from the inputs on this page: the outline from d, b, t, w "
         "and the published area, the supports from the end conditions, "
         "the moment diagram from the load pattern, and the colours from "
         "Table 2. The camera, toggles and behaviour mode are kept when "
         "any input changes.")

    if not HAS_VIEWER:
        st.info("3D viewer not loaded. Place section_geometry.py, "
                "viewer_3d.py, viewer_3d_flexure.py and "
                "viewer_3d_flexure.html in the repository root.")
    else:
        _member_model()

    if side_by_side:
        with st.expander("Cross-section and stress distribution",
                         expanded=True):
            render_section_diagrams(section_class, geom)