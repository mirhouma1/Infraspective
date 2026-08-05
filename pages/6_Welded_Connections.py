from __future__ import annotations

# 6_Welded_Connections.py
# CSA S16 Cl. 13.13 - welded connection solver.
#
# Presentation follows 4_Beam_Column_Members.py: numbered sections, a
# clause on every step, the formula, the substitution with numbers in it,
# a summary block, then a verdict. The joint model at the bottom of the
# page maps each of those calculations onto the steel.
#
# ASCII only. Straight quotes only.

import math
from typing import Any, Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as st_html

from _theme import (apply_theme, render_sidebar_logo, render_footer,
                    gate_disclaimer)

try:
    import viewer_3d_welded
    HAS_VIEWER = True
except Exception:
    HAS_VIEWER = False


# ============================================================
# CONFIG
# ============================================================

PHI_W = 0.67   # weld resistance factor, Cl. 13.13.1
PHI = 0.90     # base metal yielding
PHI_U = 0.75   # base metal fracture

APP_TITLE = "CSA S16 - Welded Connection Solver"

# Table 4, matching electrodes for G40.21 steels
STEEL_GRADES: Dict[int, tuple] = {
    260: (260, 410, 490),
    300: (300, 440, 490),
    350: (350, 450, 490),
    380: (380, 480, 490),
    400: (400, 490, 550),
    480: (480, 550, 620),
    700: (700, 700, 820),
}


# ============================================================
# FORMATTING
# ============================================================

DASH = "-"


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


def tx(x: Any, nd: int = 2) -> str:
    return num(x, nd).replace(",", r"\,")


def uc(v) -> str:
    if v is None:
        return "n/a"
    return "{:.3f}".format(v)


def verdict(v) -> str:
    if v is None:
        return "INCOMPLETE"
    return "OK" if v <= 1.0 else "NG"


def step_head(n: int, title: str, clause: str) -> None:
    st.markdown("#### Step " + str(n) + " - " + title)
    st.caption(clause)


# ============================================================
# DETAILING LIMITS, Cl. 6.2.3
# ============================================================


def min_fillet_size(t_thicker: float) -> int:
    if t_thicker <= 6:
        return 3
    if t_thicker <= 12:
        return 5
    if t_thicker <= 20:
        return 6
    return 8


def max_fillet_size(t_thinner: float) -> float:
    return t_thinner if t_thinner < 6 else t_thinner - 2


def min_eff_length(D: float) -> float:
    return max(38.0, 4.0 * D)


def lap_min_overlap(t1: float, t2: float) -> float:
    t_thin = min(t1, t2)
    return max(5 * t_thin, 25.0)


# ============================================================
# CORE CALCULATIONS
# ============================================================


def effective_throat(D: float) -> float:
    """Fillet weld effective throat, aw = D / sqrt(2)."""
    return D / math.sqrt(2)


def fillet_Aw(D: float, L: float) -> float:
    """Effective throat area, throat x length, mm2."""
    return effective_throat(D) * L


def orientation_factor(theta_deg: float) -> float:
    """1.00 + 0.50 sin^1.5(theta), the load angle factor."""
    t = math.radians(theta_deg)
    return 1.0 + 0.50 * (math.sin(t) ** 1.5)


def Mw_factor(theta1: float, theta2_nearest90: float) -> float:
    """Multi-orientation strength reduction factor."""
    return (0.85 + theta1 / 600) / (0.85 + theta2_nearest90 / 600)


def vr_fillet_N(D: float, L: float, theta: float, Xu: float,
                Mw: float = 1.0) -> dict:
    """Fillet weld factored shear resistance, Cl. 13.13.2.2."""
    throat = effective_throat(D)
    Aw = fillet_Aw(D, L)
    of_ = orientation_factor(theta)
    Vr = 0.67 * PHI_W * Aw * Xu * of_ * Mw
    return {"throat_mm": throat, "Aw_mm2": Aw, "theta": theta,
            "orient_factor": of_, "Mw": Mw, "Vr_N": Vr, "Vr_kN": Vr / 1000}


def vr_base_metal_N(Am_mm2: float, Fu: float) -> float:
    """Base metal shear on the fusion face, Vr = 0.67 phi_w Am Fu, N."""
    return 0.67 * PHI_W * Am_mm2 * Fu


def vr_groove_N(Am_mm2: float, Aw_mm2: float, Fu: float,
                Xu: float) -> dict:
    """Groove weld shear resistance, Cl. 13.13.2.1."""
    Vr_base = 0.67 * PHI_W * Am_mm2 * Fu
    Vr_weld = 0.67 * PHI_W * Aw_mm2 * Xu
    gov = min(Vr_base, Vr_weld)
    return {"Vr_base_N": Vr_base, "Vr_base_kN": Vr_base / 1000,
            "Vr_weld_N": Vr_weld, "Vr_weld_kN": Vr_weld / 1000,
            "Vr_N": gov, "Vr_kN": gov / 1000,
            "governs": "base metal" if Vr_base <= Vr_weld else "weld metal"}


def tr_pjp_N(An_mm2: float, Fu: float, Ag_mm2: float, Fy: float) -> dict:
    """PJP groove weld tension, Cl. 13.13.3.2."""
    Tr_weld = PHI_W * An_mm2 * Fu
    Tr_cap = PHI * Ag_mm2 * Fy
    Tr = min(Tr_weld, Tr_cap)
    return {"Tr_weld_kN": Tr_weld / 1000, "Tr_cap_kN": Tr_cap / 1000,
            "Tr_kN": Tr / 1000,
            "governs": "weld" if Tr_weld <= Tr_cap else "base metal capacity"}


def tr_pjp_combined_N(An_mm2: float, Aw_mm2: float, Fu: float, Xu: float,
                      Ag_mm2: float, Fy: float) -> dict:
    """PJP plus fillet combined tension, Cl. 13.13.3.3."""
    Tr_weld = PHI_W * math.sqrt((An_mm2 * Fu) ** 2 + (Aw_mm2 * Xu) ** 2)
    Tr_cap = PHI * Ag_mm2 * Fy
    Tr = min(Tr_weld, Tr_cap)
    return {"Tr_weld_kN": Tr_weld / 1000, "Tr_cap_kN": Tr_cap / 1000,
            "Tr_kN": Tr / 1000,
            "governs": "weld" if Tr_weld <= Tr_cap else "base metal capacity"}


def vr_flare_bevel_N(wf_mm: float, L_mm: float, Fu: float) -> dict:
    """Flare bevel groove weld shear, Cl. 13.13.2.3."""
    Aw = 0.50 * wf_mm * L_mm
    Vr = 0.67 * PHI_W * Aw * Fu
    return {"Aw_mm2": Aw, "Vr_N": Vr, "Vr_kN": Vr / 1000}


# ============================================================
# SVG DIAGRAMS
# ============================================================


def _svg_html(svg: str, height: int = 280) -> None:
    """Render an SVG string through st_html so Streamlit's HTML
    sanitiser does not strip it."""
    st_html.html(
        "<!DOCTYPE html><html><body style='margin:0;padding:0;"
        "background:transparent;'>" + svg + "</body></html>",
        height=height)


def svg_fillet_cross_section(D: float, theta: float) -> str:
    W, H = 380, 260
    cx, cy = 140, 130
    fl_w, fl_h, web_h, web_w = 100, 14, 80, 10
    weld_size = max(12, min(D * 3, 28))

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="' + str(W)
        + '" height="' + str(H) + '" style="font-family:'
        "'Courier New',monospace;background:#1e293b;border-radius:10px;\">"
        '<text x="' + str(W // 2) + '" y="20" fill="#e2e8f0" font-size="12" '
        'font-weight="bold" text-anchor="middle">Fillet weld - cross '
        'section</text>'
        '<rect x="' + str(cx - fl_w // 2) + '" y="' + str(cy + web_h // 2)
        + '" width="' + str(fl_w) + '" height="' + str(fl_h)
        + '" fill="#475569" stroke="#94a3b8" stroke-width="1.5"/>'
        '<rect x="' + str(cx - web_w // 2) + '" y="' + str(cy - web_h // 2)
        + '" width="' + str(web_w) + '" height="' + str(web_h)
        + '" fill="#475569" stroke="#94a3b8" stroke-width="1.5"/>'
        '<polygon points="' + str(cx - web_w // 2 - weld_size) + ','
        + str(cy + web_h // 2) + ' ' + str(cx - web_w // 2) + ','
        + str(cy + web_h // 2) + ' ' + str(cx - web_w // 2) + ','
        + str(cy + web_h // 2 - weld_size)
        + '" fill="#f59e0b" stroke="#fbbf24" stroke-width="1"/>'
        '<polygon points="' + str(cx + web_w // 2 + weld_size) + ','
        + str(cy + web_h // 2) + ' ' + str(cx + web_w // 2) + ','
        + str(cy + web_h // 2) + ' ' + str(cx + web_w // 2) + ','
        + str(cy + web_h // 2 - weld_size)
        + '" fill="#f59e0b" stroke="#fbbf24" stroke-width="1"/>'
        '<line x1="' + str(cx - web_w // 2 - weld_size - 4) + '" y1="'
        + str(cy + web_h // 2) + '" x2="' + str(cx - web_w // 2 - 4)
        + '" y2="' + str(cy + web_h // 2)
        + '" stroke="#22c55e" stroke-width="1.5"/>'
        '<text x="' + str(cx - web_w // 2 - weld_size // 2 - 4) + '" y="'
        + str(cy + web_h // 2 + 14) + '" fill="#22c55e" font-size="10" '
        'text-anchor="middle">D=' + ("%.0f" % D) + 'mm</text>'
        '<line x1="' + str(cx - web_w // 2 - 2) + '" y1="'
        + str(cy + web_h // 2) + '" x2="'
        + str(cx - web_w // 2 - weld_size // 2 - 2) + '" y2="'
        + str(cy + web_h // 2 - weld_size // 2)
        + '" stroke="#60a5fa" stroke-width="1.5" stroke-dasharray="3,2"/>'
        '<text x="' + str(cx - web_w // 2 - weld_size - 10) + '" y="'
        + str(cy + web_h // 2 - weld_size // 2 - 4)
        + '" fill="#60a5fa" font-size="9">throat='
        + ("%.1f" % (D / math.sqrt(2))) + 'mm</text>'
        '<text x="280" y="60" fill="#e2e8f0" font-size="11" '
        'font-weight="bold">Load angle</text>'
        '<text x="280" y="78" fill="#f59e0b" font-size="13" '
        'font-weight="bold">theta = ' + ("%.0f" % theta) + ' deg</text>'
        '<text x="280" y="96" fill="#94a3b8" font-size="10">'
        + ("Transverse" if theta == 90 else
           ("Longitudinal" if theta == 0 else "Inclined")) + '</text>'
        '<text x="280" y="124" fill="#e2e8f0" font-size="10">'
        'Orient. factor:</text>'
        '<text x="280" y="140" fill="#22c55e" font-size="12" '
        'font-weight="bold">' + ("%.3f" % orientation_factor(theta))
        + '</text>'
        '<text x="' + str(cx) + '" y="' + str(cy + web_h // 2 + fl_h + 18)
        + '" fill="#94a3b8" font-size="10" text-anchor="middle">'
        'Base plate</text>'
        '<text x="' + str(cx + fl_w // 2 + 8) + '" y="' + str(cy)
        + '" fill="#94a3b8" font-size="10">Web</text>'
        '<text x="' + str(cx - web_w // 2 - weld_size // 2 - 4) + '" y="'
        + str(cy + web_h // 2 - weld_size - 8)
        + '" fill="#f59e0b" font-size="10">Fillet weld</text>'
        "</svg>")
    return svg


def svg_weld_group(segments: List[dict]) -> str:
    W, H = 420, 300
    cx, cy = 160, 150
    plate_w, plate_h = 200, 100
    colors = ["#f59e0b", "#22c55e", "#60a5fa", "#f97316", "#a78bfa"]

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="' + str(W)
        + '" height="' + str(H) + '" style="font-family:'
        "'Courier New',monospace;background:#1e293b;border-radius:10px;\">"
        '<text x="' + str(W // 2) + '" y="20" fill="#e2e8f0" font-size="12" '
        'font-weight="bold" text-anchor="middle">Weld group - '
        + str(len(segments)) + ' segment(s)</text>'
        '<rect x="' + str(cx - plate_w // 2) + '" y="'
        + str(cy - plate_h // 2) + '" width="' + str(plate_w) + '" height="'
        + str(plate_h) + '" fill="#334155" stroke="#64748b" '
        'stroke-width="2" rx="3"/>'
        '<defs><marker id="arrg" markerWidth="8" markerHeight="6" refX="8" '
        'refY="3" orient="auto"><polygon points="0 0,8 3,0 6" '
        'fill="#f59e0b"/></marker></defs>'
        '<line x1="' + str(cx - plate_w // 2 - 35) + '" y1="' + str(cy)
        + '" x2="' + str(cx - plate_w // 2 - 5) + '" y2="' + str(cy)
        + '" stroke="#f59e0b" stroke-width="2.5" marker-end="url(#arrg)"/>'
        '<text x="' + str(cx - plate_w // 2 - 42) + '" y="' + str(cy - 6)
        + '" fill="#f59e0b" font-size="10" text-anchor="middle">Vf</text>')

    for i, seg in enumerate(segments):
        col = colors[i % len(colors)]
        theta = seg.get("theta", 0)
        L = seg.get("L", 100)
        lab = ("Seg " + str(i + 1) + ": theta=" + ("%.0f" % theta)
               + " deg  L=" + ("%.0f" % L) + "mm")

        if abs(theta - 90) < 5:
            x1 = cx + plate_w // 2
            y1 = cy - plate_h // 2
            x2 = cx + plate_w // 2
            y2 = cy + plate_h // 2
        else:
            side = 1 if i % 2 == 0 else -1
            y_pos = cy - side * plate_h // 2
            x1 = cx - plate_w // 4
            y1 = y_pos
            x2 = cx + plate_w // 4
            y2 = y_pos

        svg += ('<line x1="' + str(x1) + '" y1="' + str(y1) + '" x2="'
                + str(x2) + '" y2="' + str(y2) + '" stroke="' + col
                + '" stroke-width="5" opacity="0.85"/>'
                '<rect x="295" y="' + str(50 + i * 22) + '" width="14" '
                'height="10" fill="' + col + '"/>'
                '<text x="313" y="' + str(50 + i * 22 + 9) + '" fill="'
                + col + '" font-size="10">' + lab + '</text>')

    svg += "</svg>"
    return svg


def svg_detailing(D: float, D_min: float, D_max: float, L: float,
                  L_min: float, t_thinner: float, t_thicker: float) -> str:
    W, H = 420, 240
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="' + str(W)
           + '" height="' + str(H) + '" style="font-family:'
           "'Courier New',monospace;background:#1e293b;border-radius:10px;\">"
           '<text x="' + str(W // 2) + '" y="20" fill="#e2e8f0" '
           'font-size="12" font-weight="bold" text-anchor="middle">'
           'Detailing checks</text>')

    checks = [("Min fillet size", D_min, D, ">=", "D_min", "mm"),
              ("Max fillet size", D, D_max, "<=", "D_max", "mm"),
              ("Min eff. length", L_min, L, ">=", "L_min", "mm")]

    bar_x0, bar_w = 200, 170
    for i, (lab, limit, actual, op, lim_label, unit) in enumerate(checks):
        y = 50 + i * 58
        if op == ">=":
            ok = actual >= limit
            fill_ratio = min(actual / max(limit, 0.001), 1.5)
        else:
            ok = actual <= limit
            fill_ratio = min(actual / max(limit, 0.001), 1.0)

        col = "#22c55e" if ok else "#ef4444"
        icon = "PASS" if ok else "FAIL"
        bar_fill = min(fill_ratio * bar_w, bar_w * 1.3)
        ref_x = bar_x0 + bar_w * min(1.0, limit / max(actual, 0.001))

        svg += ('<text x="10" y="' + str(y + 12) + '" fill="#e2e8f0" '
                'font-size="11" font-weight="bold">' + lab + '</text>'
                '<text x="10" y="' + str(y + 26) + '" fill="#94a3b8" '
                'font-size="10">' + lim_label + '=' + ("%.1f" % limit) + ' '
                + unit + ',  actual=' + ("%.1f" % actual) + ' ' + unit
                + '</text>'
                '<rect x="' + str(bar_x0) + '" y="' + str(y) + '" width="'
                + str(bar_w) + '" height="20" fill="#1e293b" rx="3"/>'
                '<rect x="' + str(bar_x0) + '" y="' + str(y) + '" width="'
                + ("%.0f" % bar_fill) + '" height="20" fill="' + col
                + '" opacity="0.75" rx="3"/>'
                '<line x1="' + ("%.0f" % ref_x) + '" y1="' + str(y - 3)
                + '" x2="' + ("%.0f" % ref_x) + '" y2="' + str(y + 23)
                + '" stroke="white" stroke-width="2" stroke-dasharray="3,2"/>'
                '<text x="' + str(bar_x0 + bar_w + 8) + '" y="'
                + str(y + 14) + '" fill="' + col + '" font-size="11" '
                'font-weight="bold">' + icon + '</text>')

    svg += "</svg>"
    return svg


# ============================================================
# STREAMLIT UI
# ============================================================

apply_theme()
render_sidebar_logo()
render_footer()
gate_disclaimer()

# Lock page here ***************
# from _theme import beta_lock_page
# beta_lock_page("Welded Connections")

st.title(APP_TITLE)
st.caption("Cl. 13.13  |  fillet, CJP and PJP groove, flare bevel  |  "
           "phi_w = 0.67  |  detailing per Cl. 6.2.3  |  forces in kN, "
           "geometry in mm")

col_calc, col_model = st.columns([1.15, 1], gap="large")

# these are filled in by the calculation column and read by the model
MODEL: Dict[str, Any] = {"kind": "fillet", "label": "", "clause": "",
                         "dims": {}, "segments": [], "loads": {},
                         "results": {}, "detailing": [], "props": []}

with col_calc:

    # ---- 1. Weld type ----
    st.subheader("1. Weld Type")
    weld_type = st.selectbox(
        "Select weld type",
        ["Fillet Weld",
         "Complete Joint Penetration (CJP) Groove",
         "Partial Joint Penetration (PJP) Groove",
         "Flare Bevel Groove"],
        key="weld_type")

    # ---- 2. Material ----
    st.subheader("2. Material")
    st.caption("Table 4 pairs each G40.21 grade with a matching electrode. "
               "Xu above the matching value is an over-matched electrode, "
               "which is exactly when the base metal starts to govern.")
    mat1, mat2, mat3 = st.columns(3)
    with mat1:
        grade_label = st.selectbox(
            "Steel grade (G40.21)",
            ["G40.21-" + str(g) for g in STEEL_GRADES],
            index=2, key="steel_grade")
        grade_val = int(grade_label.split("-")[1])
        Fy_default, Fu_default, Xu_default = STEEL_GRADES[grade_val]
    with mat2:
        Fy = st.number_input("Fy (MPa)", min_value=200.0,
                             value=float(Fy_default), step=5.0, key="Fy")
        Fu = st.number_input("Fu (MPa)", min_value=200.0,
                             value=float(Fu_default), step=5.0, key="Fu")
    with mat3:
        Xu = st.number_input(
            "Electrode Xu (MPa)  [Table 4 match = " + str(Xu_default) + "]",
            min_value=300.0, value=float(Xu_default), step=10.0, key="Xu")
        st.caption("Xu = 10 x the first two digits of the electrode "
                   "classification, CSA W48.")
    if Xu > Xu_default:
        st.info("Xu = " + num(Xu, 0) + " MPa is above the Table 4 match of "
                + str(Xu_default) + " MPa. With an over-matched electrode "
                "the weld metal is no longer the weak link, so the base "
                "metal check below is the one that matters.")

    # ---- 3. Geometry ----
    st.subheader("3. Geometry")

    segments: List[dict] = []
    check_base = False
    Am_mm2 = 0.0
    Am_mm2_groove = 0.0
    Aw_mm2 = 0.0
    An_mm2 = 0.0
    Ag_mm2 = 0.0
    has_fillet = False
    Aw_fillet_mm2 = 0.0
    wf_mm = 0.0
    L_fb = 0.0
    D = 8.0
    pjp_pen = 0.0

    if weld_type == "Fillet Weld":
        g1, g2 = st.columns(2)
        with g1:
            D = st.number_input("Weld leg size D (mm)", min_value=3.0,
                                value=8.0, step=1.0, key="D")
            n_segs = int(st.number_input("Number of weld segments",
                                         min_value=1, max_value=6, value=1,
                                         step=1, key="n_segs"))
            st.markdown("**Weld segments**  *(each with length L and "
                        "orientation theta)*")
            st.caption("Weld returns not accounted for in the joint "
                       "capacity may be left out of the segment list, "
                       "Cl. 13.13.2.2.")
            seg_cols = st.columns(min(n_segs, 3))
            for i in range(n_segs):
                col_ctx = seg_cols[i % 3] if n_segs <= 3 else st.container()
                with col_ctx:
                    st.markdown("**Segment " + str(i + 1) + "**")
                    L_i = st.number_input("L_" + str(i + 1) + " (mm)",
                                          min_value=1.0, value=100.0,
                                          step=5.0, key="L_" + str(i))
                    theta_i = st.number_input(
                        "theta_" + str(i + 1) + " (deg)  "
                        "[0 = longitudinal, 90 = transverse]",
                        min_value=0.0, max_value=90.0,
                        value=90.0 if i == 0 else 0.0, step=5.0,
                        key="theta_" + str(i))
                    segments.append({"L": L_i, "theta": theta_i})
        with g2:
            check_base = st.checkbox(
                "Check base metal (over-matched electrodes)?",
                key="chk_base")
            if check_base:
                Am_mm2 = st.number_input(
                    "Am - fusion face shear area (mm2)", min_value=0.0,
                    value=1000.0, step=50.0, key="Am_fillet")
                st.caption("Am is the area of the plane where the weld "
                           "meets the parent steel, not the throat.")

    elif weld_type in ("Complete Joint Penetration (CJP) Groove",
                       "Partial Joint Penetration (PJP) Groove"):
        g1, g2 = st.columns(2)
        with g1:
            Am_mm2_groove = st.number_input(
                "Am - shear area of fusion face (mm2)", min_value=0.0,
                value=2000.0, step=50.0, key="Am_groove")
            Aw_mm2 = st.number_input(
                "Aw - effective weld throat area (mm2)", min_value=0.0,
                value=2000.0, step=50.0, key="Aw_groove")
        with g2:
            if "Partial" in weld_type:
                st.markdown("**PJP - tension check**")
                An_mm2 = st.number_input(
                    "An - nominal fusion face area (mm2)", min_value=0.0,
                    value=2000.0, step=50.0, key="An")
                Ag_mm2 = st.number_input(
                    "Ag - gross area of tension member (mm2)",
                    min_value=0.0, value=3000.0, step=50.0, key="Ag")
                has_fillet = st.checkbox(
                    "Combined with fillet weld? (Cl. 13.13.3.3)",
                    key="has_fillet")
                if has_fillet:
                    Aw_fillet_mm2 = st.number_input(
                        "Aw_fillet - fillet throat area (mm2)",
                        min_value=0.0, value=500.0, step=50.0,
                        key="Aw_fillet")
                pjp_pen = st.number_input(
                    "Penetration depth for the model only (mm)",
                    min_value=0.0, value=6.0, step=1.0, key="pjp_pen")

    elif weld_type == "Flare Bevel Groove":
        g1, _g2 = st.columns(2)
        with g1:
            wf_mm = st.number_input(
                "wf - width of flare bevel groove face (mm)",
                min_value=1.0, value=20.0, step=1.0, key="wf")
            L_fb = st.number_input("L - weld length (mm)", min_value=1.0,
                                   value=150.0, step=5.0, key="L_fb")

    # ---- 4. Plate detailing geometry ----
    st.subheader("4. Plate Detailing Geometry")
    det1, det2 = st.columns(2)
    with det1:
        t_thinner = st.number_input("t_thinner - thinner part joined (mm)",
                                    min_value=1.0, value=10.0, step=1.0,
                                    key="t_thin")
        t_thicker = st.number_input("t_thicker - thicker part joined (mm)",
                                    min_value=1.0, value=12.0, step=1.0,
                                    key="t_thick")
    with det2:
        is_lap = st.checkbox("Lap joint?", key="is_lap")
        L_lap = 0.0
        if is_lap:
            L_lap = st.number_input("Lap overlap length L (mm)",
                                    min_value=0.0, value=80.0, step=5.0,
                                    key="L_lap")

    # ---- 5. Applied loads ----
    st.subheader("5. Applied Loads")
    st.caption("Optional. Without a load the page reports resistances "
               "only, and the model has no utilisation to colour.")
    ld1, ld2 = st.columns(2)
    with ld1:
        apply_shear = st.checkbox("Apply a factored shear Vf",
                                  value=False, key="ap_v")
        Vf_kN = 0.0
        if apply_shear:
            Vf_kN = st.number_input("Vf (kN)", 0.0, 1e6, 250.0, 10.0,
                                    key="Vf")
    with ld2:
        apply_tens = st.checkbox("Apply a factored tension Tf",
                                 value=False, key="ap_t")
        Tf_kN = 0.0
        if apply_tens:
            Tf_kN = st.number_input("Tf (kN)", 0.0, 1e6, 250.0, 10.0,
                                    key="Tf")

    st.divider()

    # ================================================================
    # 6. CALCULATIONS
    # ================================================================
    st.subheader("6. Calculations")

    Vr_gov_kN: Optional[float] = None
    Tr_gov_kN: Optional[float] = None
    governs = "weld metal"
    seg_payload: List[dict] = []

    # ---------------- FILLET ----------------
    if weld_type == "Fillet Weld":
        MODEL["kind"] = "fillet"
        MODEL["clause"] = "Cl. 13.13.2.2"

        # Step 1 - throat and area
        step_head(1, "Effective throat and weld area", "Cl. 13.13.2.2")
        st.markdown("*A fillet weld is not checked on its leg. It is "
                    "checked on the throat, the shortest path through the "
                    "bead, which for equal legs lies at 45 degrees.*")
        st.latex(r"a_w = \frac{D}{\sqrt{2}} \qquad A_w = a_w L")
        throat = effective_throat(D)
        st.latex(r"a_w = \frac{" + tx(D, 1) + r"}{\sqrt{2}} = "
                 + tx(throat, 3) + r"\ \mathrm{mm}")
        lines = []
        for i, s in enumerate(segments):
            Aw_i = fillet_Aw(D, s["L"])
            st.latex(r"A_{w," + str(i + 1) + r"} = " + tx(throat, 3)
                     + r" \times " + tx(s["L"], 0) + r" = " + tx(Aw_i, 2)
                     + r"\ \mathrm{mm^2}")
            lines.append("  Seg %d:  L = %6.0f mm   Aw = %9.2f mm2"
                         % (i + 1, s["L"], Aw_i))
        st.code("  Throat  aw = %.1f / sqrt(2) = %.3f mm\n\n%s"
                % (D, throat, "\n".join(lines)), language="text")

        # Step 2 - Mw
        step_head(2, "Multi-orientation factor Mw", "Cl. 13.13.2.2")
        st.markdown("*Segments at different angles do not reach their peak "
                    "together. The segment nearest 90 degrees is the "
                    "stiffest and sheds load first, so every other segment "
                    "is scaled down to the deformation that one can "
                    "actually reach.*")
        st.latex(r"M_w = \frac{0.85 + \theta_1/600}{0.85 + \theta_2/600}")
        st.markdown("- theta_1 is the orientation of the segment being "
                    "considered  \n"
                    "- theta_2 is the orientation of the segment in the "
                    "joint nearest to 90 degrees  \n"
                    "- a single orientation gives Mw = 1.0")

        theta_max = max(s["theta"] for s in segments)
        idx_max = max(range(len(segments)),
                      key=lambda i: segments[i]["theta"])

        if len(segments) == 1:
            st.latex(r"\text{single orientation} \Rightarrow M_w = 1.000")
            mw_values = [1.0]
        else:
            st.caption("theta_2 taken from Seg " + str(idx_max + 1)
                       + " at " + num(theta_max, 0) + " deg, the segment "
                       "nearest 90 deg.")
            mw_values = []
            for i, s in enumerate(segments):
                Mw_i = Mw_factor(s["theta"], theta_max)
                nume = 0.85 + s["theta"] / 600
                deno = 0.85 + theta_max / 600
                mw_values.append(Mw_i)
                st.latex(r"M_{w," + str(i + 1) + r"} = \frac{0.85 + "
                         + tx(s["theta"], 0) + r"/600}{0.85 + "
                         + tx(theta_max, 0) + r"/600} = \frac{"
                         + tx(nume, 5) + r"}{" + tx(deno, 5) + r"} = "
                         + tx(Mw_i, 4))

        # Step 3 - Vr per segment
        step_head(3, "Factored shear resistance of each segment",
                  "Cl. 13.13.2.2")
        st.latex(r"V_r = 0.67\,\phi_w A_w X_u"
                 r"\left(1.00 + 0.50\sin^{1.5}\theta\right) M_w")
        st.caption("phi_w = " + num(PHI_W, 2) + ",  Xu = " + num(Xu, 0)
                   + " MPa")

        total_Vr_kN = 0.0
        seg_results: List[dict] = []
        for i, s in enumerate(segments):
            Mw_i = mw_values[i]
            res = vr_fillet_N(D, s["L"], s["theta"], Xu, Mw_i)
            seg_results.append(res)
            total_Vr_kN += res["Vr_kN"]

            sin_t = math.sin(math.radians(s["theta"]))
            sin15 = sin_t ** 1.5
            of_val = 1.00 + 0.50 * sin15

            st.markdown("**Segment " + str(i + 1) + "**  -  theta = "
                        + num(s["theta"], 0) + " deg, L = "
                        + num(s["L"], 0) + " mm")
            st.latex(r"1.00 + 0.50\sin^{1.5}(" + tx(s["theta"], 0)
                     + r"^\circ) = 1.00 + 0.50(" + tx(sin15, 4) + r") = "
                     + tx(of_val, 4))
            st.latex(r"V_{r," + str(i + 1) + r"} = 0.67 \times "
                     + tx(PHI_W, 2) + r" \times " + tx(res["Aw_mm2"], 2)
                     + r" \times " + tx(Xu, 0) + r" \times "
                     + tx(of_val, 4) + r" \times " + tx(Mw_i, 4)
                     + r" = " + tx(res["Vr_kN"], 2) + r"\ \mathrm{kN}")

        st.code(
            "  seg   theta      L        Aw       orient     Mw       Vr\n"
            "                  mm       mm2                          kN\n"
            "  " + "-" * 62 + "\n"
            + "\n".join(
                "  %-4d %6.0f %8.0f %10.1f %9.4f %8.4f %8.2f"
                % (i + 1, segments[i]["theta"], segments[i]["L"],
                   seg_results[i]["Aw_mm2"], seg_results[i]["orient_factor"],
                   mw_values[i], seg_results[i]["Vr_kN"])
                for i in range(len(segments)))
            + "\n  " + "-" * 62
            + "\n  total weld metal Vr = %.2f kN" % total_Vr_kN,
            language="text")
        st.latex(r"V_{r,\text{weld}} = \sum V_{r,i} = "
                 + r" + ".join(tx(r["Vr_kN"], 2) for r in seg_results)
                 + r" = " + tx(total_Vr_kN, 2) + r"\ \mathrm{kN}")

        # Step 4 - base metal
        Vr_bm = None
        if check_base and Am_mm2 > 0:
            step_head(4, "Base metal on the fusion face", "Cl. 13.13.2.2")
            st.markdown("*This is a different surface from the throat. It "
                        "is the plane where the bead meets the parent "
                        "steel, and it is checked on Fu of the parent, not "
                        "Xu of the electrode. Over-matching the electrode "
                        "does nothing for it.*")
            st.latex(r"V_r = 0.67\,\phi_w A_m F_u")
            Vr_bm = vr_base_metal_N(Am_mm2, Fu) / 1000.0
            st.latex(r"V_r = 0.67 \times " + tx(PHI_W, 2) + r" \times "
                     + tx(Am_mm2, 0) + r" \times " + tx(Fu, 0) + r" = "
                     + tx(Vr_bm, 2) + r"\ \mathrm{kN}")

            step_head(5, "Governing shear resistance", "Cl. 13.13.2.2")
            gov_Vr = min(total_Vr_kN, Vr_bm)
            governs = "weld metal" if total_Vr_kN <= Vr_bm else "base metal"
            st.latex(r"V_r = \min\left(" + tx(total_Vr_kN, 2) + r",\ "
                     + tx(Vr_bm, 2) + r"\right) = " + tx(gov_Vr, 2)
                     + r"\ \mathrm{kN}")
            st.code("  weld metal   Vr = %8.2f kN\n"
                    "  base metal   Vr = %8.2f kN\n"
                    "  %s\n"
                    "  governing (%s): Vr = %.2f kN"
                    % (total_Vr_kN, Vr_bm, "-" * 34, governs, gov_Vr),
                    language="text")
            if governs == "weld metal":
                st.success("Weld metal governs at Vr = " + num(gov_Vr, 2)
                           + " kN. The joint tears through the bead on its "
                           "throat.")
            else:
                st.warning("Base metal governs at Vr = " + num(gov_Vr, 2)
                           + " kN. The joint tears in the parent steel "
                           "beside the bead. A bigger electrode will not "
                           "help; a thicker part or a longer weld will.")
        else:
            gov_Vr = total_Vr_kN
            governs = "weld metal"
            st.info("No base metal check requested, so the weld metal "
                    "result stands. With an over-matched electrode this "
                    "can be unconservative.")

        Vr_gov_kN = gov_Vr

        # segment payload for the model
        for i, s in enumerate(segments):
            share = (seg_results[i]["Vr_kN"] / total_Vr_kN
                     if total_Vr_kN > 0 else 0.0)
            seg_payload.append({
                "L": s["L"], "theta": s["theta"],
                "Aw": seg_results[i]["Aw_mm2"],
                "Vr_kN": seg_results[i]["Vr_kN"],
                "Mw": mw_values[i],
                "orient": seg_results[i]["orient_factor"],
                "share": share})

        MODEL["dims"] = {"t1": t_thinner, "t2": t_thicker, "D": D,
                         "throat": throat}
        MODEL["label"] = ("Fillet weld, " + str(len(segments))
                          + " segment" + ("" if len(segments) == 1 else "s"))
        MODEL["results"]["Vr_weld_kN"] = total_Vr_kN
        MODEL["results"]["Vr_base_kN"] = Vr_bm

    # ---------------- CJP / PJP GROOVE ----------------
    elif weld_type in ("Complete Joint Penetration (CJP) Groove",
                       "Partial Joint Penetration (PJP) Groove"):
        is_cjp = weld_type.startswith("Complete")
        MODEL["kind"] = "cjp" if is_cjp else "pjp"
        MODEL["clause"] = "Cl. 13.13.2.1"

        step_head(1, "Groove weld shear resistance", "Cl. 13.13.2.1")
        st.markdown("*Two surfaces, two materials. The clause takes the "
                    "lesser, because the joint can only be as strong as "
                    "the first plane to let go.*")
        st.latex(r"V_r = \min\begin{cases}"
                 r"0.67\,\phi_w A_m F_u & \text{base metal}\\"
                 r"0.67\,\phi_w A_w X_u & \text{weld metal}"
                 r"\end{cases}")
        res_g = vr_groove_N(Am_mm2_groove, Aw_mm2, Fu, Xu)
        st.latex(r"V_{r,\text{base}} = 0.67 \times " + tx(PHI_W, 2)
                 + r" \times " + tx(Am_mm2_groove, 0) + r" \times "
                 + tx(Fu, 0) + r" = " + tx(res_g["Vr_base_kN"], 2)
                 + r"\ \mathrm{kN}")
        st.latex(r"V_{r,\text{weld}} = 0.67 \times " + tx(PHI_W, 2)
                 + r" \times " + tx(Aw_mm2, 0) + r" \times " + tx(Xu, 0)
                 + r" = " + tx(res_g["Vr_weld_kN"], 2) + r"\ \mathrm{kN}")
        st.code("  case a) base metal:  0.67 x %.2f x %8.0f x %4.0f = "
                "%8.2f kN\n"
                "  case b) weld metal:  0.67 x %.2f x %8.0f x %4.0f = "
                "%8.2f kN\n"
                "  %s\n"
                "  governing (%s): Vr = %.2f kN"
                % (PHI_W, Am_mm2_groove, Fu, res_g["Vr_base_kN"],
                   PHI_W, Aw_mm2, Xu, res_g["Vr_weld_kN"], "-" * 52,
                   res_g["governs"], res_g["Vr_kN"]), language="text")
        st.success("Vr = " + num(res_g["Vr_kN"], 2) + " kN, governed by "
                   + res_g["governs"] + ".")
        Vr_gov_kN = res_g["Vr_kN"]
        governs = res_g["governs"]
        MODEL["results"]["Vr_weld_kN"] = res_g["Vr_weld_kN"]
        MODEL["results"]["Vr_base_kN"] = res_g["Vr_base_kN"]

        if is_cjp:
            step_head(2, "Tension resistance", "Cl. 13.13.3.1")
            st.markdown("*A CJP groove weld made with matching electrodes "
                        "restores the full section. There is no separate "
                        "weld check in tension: the member governs.*")
            st.latex(r"T_r = \phi A_g F_y \quad"
                     r"\text{(full restoration, base metal governs)}")
            st.info("Tr is the base metal tension capacity of the member "
                    "being joined. Enter that member on the Tension "
                    "Members page; there is nothing weld-specific left to "
                    "check here.")
        else:
            step_head(2, "Tension resistance", "Cl. 13.13.3.2 / 13.13.3.3")
            st.markdown("*A PJP groove does not restore the section. Only "
                        "the fused depth carries, and the unfused root is "
                        "a built-in notch that does nothing.*")
            if not has_fillet:
                st.latex(r"T_r = \phi_w A_n F_u \leq \phi A_g F_y")
                res_t = tr_pjp_N(An_mm2, Fu, Ag_mm2, Fy)
                st.latex(r"T_{r,\text{weld}} = " + tx(PHI_W, 2)
                         + r" \times " + tx(An_mm2, 0) + r" \times "
                         + tx(Fu, 0) + r" = " + tx(res_t["Tr_weld_kN"], 2)
                         + r"\ \mathrm{kN}")
                st.latex(r"T_{r,\text{cap}} = " + tx(PHI, 2) + r" \times "
                         + tx(Ag_mm2, 0) + r" \times " + tx(Fy, 0) + r" = "
                         + tx(res_t["Tr_cap_kN"], 2) + r"\ \mathrm{kN}")
                st.code("  Tr_weld = %.2f x %8.0f x %4.0f = %8.2f kN\n"
                        "  Tr_cap  = %.2f x %8.0f x %4.0f = %8.2f kN\n"
                        "  %s\n  governing (%s): Tr = %.2f kN"
                        % (PHI_W, An_mm2, Fu, res_t["Tr_weld_kN"],
                           PHI, Ag_mm2, Fy, res_t["Tr_cap_kN"], "-" * 46,
                           res_t["governs"], res_t["Tr_kN"]),
                        language="text")
                st.success("Tr = " + num(res_t["Tr_kN"], 2) + " kN")
                Tr_gov_kN = res_t["Tr_kN"]
            else:
                st.markdown("*With a reinforcing fillet on top of the "
                            "groove the two throats act on different "
                            "planes, so their resistances add as vectors "
                            "rather than arithmetically.*")
                st.latex(r"T_r = \phi_w\sqrt{(A_n F_u)^2 + (A_w X_u)^2}"
                         r" \leq \phi A_g F_y")
                res_tc = tr_pjp_combined_N(An_mm2, Aw_fillet_mm2, Fu, Xu,
                                           Ag_mm2, Fy)
                st.latex(r"A_n F_u = " + tx(An_mm2, 0) + r" \times "
                         + tx(Fu, 0) + r" = " + tx(An_mm2 * Fu, 0)
                         + r"\ \mathrm{N}")
                st.latex(r"A_w X_u = " + tx(Aw_fillet_mm2, 0) + r" \times "
                         + tx(Xu, 0) + r" = " + tx(Aw_fillet_mm2 * Xu, 0)
                         + r"\ \mathrm{N}")
                st.latex(r"T_{r,\text{weld}} = " + tx(PHI_W, 2)
                         + r"\sqrt{(" + tx(An_mm2 * Fu, 0) + r")^2 + ("
                         + tx(Aw_fillet_mm2 * Xu, 0) + r")^2} = "
                         + tx(res_tc["Tr_weld_kN"], 2) + r"\ \mathrm{kN}")
                st.latex(r"T_{r,\text{cap}} = " + tx(PHI, 2) + r" \times "
                         + tx(Ag_mm2, 0) + r" \times " + tx(Fy, 0) + r" = "
                         + tx(res_tc["Tr_cap_kN"], 2) + r"\ \mathrm{kN}")
                st.code("  Tr_weld = %.2f x sqrt(%.0f^2 + %.0f^2) = "
                        "%8.2f kN\n"
                        "  Tr_cap  = %.2f x %8.0f x %4.0f = %8.2f kN\n"
                        "  %s\n  governing (%s): Tr = %.2f kN"
                        % (PHI_W, An_mm2 * Fu, Aw_fillet_mm2 * Xu,
                           res_tc["Tr_weld_kN"], PHI, Ag_mm2, Fy,
                           res_tc["Tr_cap_kN"], "-" * 50,
                           res_tc["governs"], res_tc["Tr_kN"]),
                        language="text")
                st.success("Tr = " + num(res_tc["Tr_kN"], 2) + " kN")
                Tr_gov_kN = res_tc["Tr_kN"]

        MODEL["dims"] = {"t1": t_thinner, "t2": t_thicker,
                         "D": max(D, 6.0),
                         "gap": max(t_thinner * 0.28, 3.0),
                         "penetration": (max(t_thinner, t_thicker)
                                         if is_cjp else max(pjp_pen, 1.0)),
                         "has_fillet": bool(has_fillet)}
        MODEL["label"] = ("CJP groove weld" if is_cjp
                          else "PJP groove weld")
        seg_payload.append({"L": 100.0, "theta": 90.0, "Aw": Aw_mm2,
                            "Vr_kN": res_g["Vr_kN"], "Mw": 1.0,
                            "orient": 1.5, "share": 1.0})

    # ---------------- FLARE BEVEL ----------------
    elif weld_type == "Flare Bevel Groove":
        MODEL["kind"] = "flare"
        MODEL["clause"] = "Cl. 13.13.2.3"

        step_head(1, "Effective area of a flare bevel groove",
                  "Cl. 13.13.2.3")
        st.markdown("*The groove is formed by a rounded corner against a "
                    "flat face, so the fused throat is only about half the "
                    "width of the groove face. The clause writes that in "
                    "directly.*")
        st.latex(r"A_w = 0.50\,w_f L")
        res_fb = vr_flare_bevel_N(wf_mm, L_fb, Fu)
        st.latex(r"A_w = 0.50 \times " + tx(wf_mm, 0) + r" \times "
                 + tx(L_fb, 0) + r" = " + tx(res_fb["Aw_mm2"], 0)
                 + r"\ \mathrm{mm^2}")

        step_head(2, "Factored shear resistance", "Cl. 13.13.2.3")
        st.markdown("*Note the Fu, not Xu. A flare bevel is checked on the "
                    "parent metal strength.*")
        st.latex(r"V_r = 0.67\,\phi_w A_w F_u")
        st.latex(r"V_r = 0.67 \times " + tx(PHI_W, 2) + r" \times "
                 + tx(res_fb["Aw_mm2"], 0) + r" \times " + tx(Fu, 0)
                 + r" = " + tx(res_fb["Vr_kN"], 2) + r"\ \mathrm{kN}")
        st.code("  Aw = 0.50 x %6.0f x %6.0f = %10.0f mm2\n"
                "  Vr = 0.67 x %.2f x %10.0f x %4.0f = %8.2f kN"
                % (wf_mm, L_fb, res_fb["Aw_mm2"], PHI_W,
                   res_fb["Aw_mm2"], Fu, res_fb["Vr_kN"]), language="text")
        st.success("Vr = " + num(res_fb["Vr_kN"], 2) + " kN")
        Vr_gov_kN = res_fb["Vr_kN"]
        governs = "base metal"
        MODEL["dims"] = {"t1": t_thinner, "t2": t_thicker, "wf": wf_mm,
                         "L_fb": L_fb, "throat": 0.5 * wf_mm}
        MODEL["label"] = "Flare bevel groove weld"
        MODEL["results"]["Vr_weld_kN"] = res_fb["Vr_kN"]
        MODEL["results"]["Vr_base_kN"] = res_fb["Vr_kN"]
        seg_payload.append({"L": L_fb, "theta": 0.0,
                            "Aw": res_fb["Aw_mm2"],
                            "Vr_kN": res_fb["Vr_kN"], "Mw": 1.0,
                            "orient": 1.0, "share": 1.0})

    # ================================================================
    # 7. DETAILING
    # ================================================================
    st.divider()
    st.subheader("7. Detailing Checks")
    st.caption("Cl. 6.2.3. These are buildability rules, not strength "
               "rules. A bead can be strong on paper and still be wrong.")

    det_payload: List[dict] = []
    detail_ok = True

    if weld_type == "Fillet Weld":
        D_min = float(min_fillet_size(t_thicker))
        D_max = max_fillet_size(t_thinner)
        L_det = segments[0]["L"] if segments else 100.0
        L_min = min_eff_length(D)

        st.markdown("**Minimum size**  -  set by the thicker part, because "
                    "a bead too small for the mass beside it cools too "
                    "fast and cracks.")
        st.latex(r"t_{thicker} = " + tx(t_thicker, 0)
                 + r"\ \mathrm{mm} \Rightarrow D_{min} = " + tx(D_min, 0)
                 + r"\ \mathrm{mm}")
        d_min_ok = D >= D_min
        st.latex(r"D = " + tx(D, 0) + (r" \geq " if d_min_ok else r" < ")
                 + tx(D_min, 0)
                 + (r"\qquad\textbf{PASS}" if d_min_ok
                    else r"\qquad\textbf{FAIL}"))

        st.markdown("**Maximum size**  -  set by the thinner part, so the "
                    "bead cannot be laid past the edge it is fusing to.")
        st.latex(r"D_{max} = t_{thinner} - 2 = " + tx(t_thinner, 0)
                 + r" - 2 = " + tx(D_max, 0) + r"\ \mathrm{mm}"
                 r"\quad(t \geq 6\ \mathrm{mm})")
        d_max_ok = D <= D_max
        st.latex(r"D = " + tx(D, 0) + (r" \leq " if d_max_ok else r" > ")
                 + tx(D_max, 0)
                 + (r"\qquad\textbf{PASS}" if d_max_ok
                    else r"\qquad\textbf{FAIL}"))

        st.markdown("**Minimum effective length**  -  a bead shorter than "
                    "this is all start and stop crater, with no sound "
                    "length in the middle to count.")
        st.latex(r"L_{min} = \max(38,\ 4D) = \max(38,\ 4 \times "
                 + tx(D, 0) + r") = " + tx(L_min, 0) + r"\ \mathrm{mm}")
        l_eff_ok = L_det >= L_min
        st.latex(r"L = " + tx(L_det, 0) + (r" \geq " if l_eff_ok else r" < ")
                 + tx(L_min, 0)
                 + (r"\qquad\textbf{PASS}" if l_eff_ok
                    else r"\qquad\textbf{FAIL}"))

        st.code("  D_min (t_thicker = %4.0f mm) = %4.0f mm  ->  D = %4.0f "
                "mm  %s\n"
                "  D_max (t_thinner = %4.0f mm) = %4.0f mm  ->  D = %4.0f "
                "mm  %s\n"
                "  L_min = max(38, 4x%.0f)      = %4.0f mm  ->  L = %4.0f "
                "mm  %s"
                % (t_thicker, D_min, D, "PASS" if d_min_ok else "FAIL",
                   t_thinner, D_max, D, "PASS" if d_max_ok else "FAIL",
                   D, L_min, L_det, "PASS" if l_eff_ok else "FAIL"),
                language="text")

        det_payload = [
            {"label": "Min fillet size", "actual": D, "limit": D_min,
             "op": ">=", "ok": d_min_ok, "unit": "mm"},
            {"label": "Max fillet size", "actual": D, "limit": D_max,
             "op": "<=", "ok": d_max_ok, "unit": "mm"},
            {"label": "Min effective length", "actual": L_det,
             "limit": L_min, "op": ">=", "ok": l_eff_ok, "unit": "mm"}]
        detail_ok = d_min_ok and d_max_ok and l_eff_ok

        if is_lap and L_lap > 0:
            L_lap_min = lap_min_overlap(t_thinner, t_thicker)
            lap_ok = L_lap >= L_lap_min
            st.markdown("**Lap overlap**  -  too little overlap and the "
                        "load path kinks hard enough to pry the joint "
                        "open.")
            st.latex(r"L_{overlap} \geq \max(5 t_{thinner},\ 25) = "
                     r"\max(5 \times " + tx(min(t_thinner, t_thicker), 0)
                     + r",\ 25) = " + tx(L_lap_min, 0) + r"\ \mathrm{mm}")
            st.latex(r"L = " + tx(L_lap, 0)
                     + (r" \geq " if lap_ok else r" < ") + tx(L_lap_min, 0)
                     + (r"\qquad\textbf{PASS}" if lap_ok
                        else r"\qquad\textbf{FAIL}"))
            det_payload.append({"label": "Lap overlap", "actual": L_lap,
                                "limit": L_lap_min, "op": ">=",
                                "ok": lap_ok, "unit": "mm"})
            detail_ok = detail_ok and lap_ok

        if detail_ok:
            st.success("All Cl. 6.2.3 detailing limits satisfied.")
        else:
            st.error("At least one Cl. 6.2.3 limit is not met. The "
                     "resistance above assumes a weld that can actually be "
                     "laid, so fix the detail before relying on it.")
    else:
        st.info("Detailing checks are shown for fillet welds. For groove "
                "and flare welds, refer to the Cl. 6.2.3 partial "
                "penetration groove depth table.")

    # ================================================================
    # 8. GOVERNING CHECK
    # ================================================================
    st.divider()
    st.subheader("8. Governing Check")

    U_shear = None
    U_tens = None
    if Vr_gov_kN and Vf_kN > 0:
        U_shear = Vf_kN / Vr_gov_kN
    if Tr_gov_kN and Tf_kN > 0:
        U_tens = Tf_kN / Tr_gov_kN

    rows = []
    if Vr_gov_kN is not None:
        rows.append(("Shear, Vf / Vr", U_shear))
    if Tr_gov_kN is not None:
        rows.append(("Tension, Tf / Tr", U_tens))

    for name, val in rows:
        if val is None:
            st.markdown("- " + name + "  -  no factored load entered")
        else:
            st.markdown("- " + name + "  =  **" + uc(val) + "**  "
                        + verdict(val))

    live = [v for _n, v in rows if v is not None]
    overall = "INCOMPLETE"
    U_gov = None
    if live:
        U_gov = max(live)
        overall = "OK" if U_gov <= 1.0 else "NG"

    if U_gov is not None:
        st.latex(r"U = " + tx(U_gov, 3))
        st.progress(min(U_gov, 1.0))
        r1, r2, r3 = st.columns(3)
        r1.metric("Utilisation", "{:.1f} %".format(100.0 * U_gov))
        r2.metric("Resistance",
                  "{:,.1f} kN".format(Vr_gov_kN if Vr_gov_kN
                                      else (Tr_gov_kN or 0.0)))
        r3.metric("Governs", governs)
        if U_gov <= 1.0:
            st.success("PASS  -  U = " + uc(U_gov) + " ("
                       + num(100.0 * U_gov, 1) + " percent of capacity "
                       "used). Failure surface would be the "
                       + ("weld throat" if governs == "weld metal"
                          else "fusion face") + ".")
        else:
            st.error("FAIL  -  U = " + uc(U_gov) + " ("
                     + num(100.0 * U_gov - 100.0, 1) + " percent over). "
                     "The joint lets go on the "
                     + ("weld throat" if governs == "weld metal"
                        else "fusion face")
                     + ". Lengthen the weld, increase D, or change the "
                     "governing material.")
    else:
        st.info("Enter a factored load in section 5 to run the demand "
                "check and to colour the model by utilisation.")

    # ---- assemble the model payload ----
    MODEL["segments"] = seg_payload
    MODEL["loads"] = {"Vf_kN": Vf_kN, "Tf_kN": Tf_kN}
    MODEL["detailing"] = det_payload
    MODEL["results"].update({
        "Vr_kN": Vr_gov_kN, "Tr_kN": Tr_gov_kN, "util": U_gov,
        "governs": governs, "overall": overall, "detail_ok": detail_ok})

    props = [{"group": "Material", "symbol": "Fy", "value": num(Fy, 0),
              "unit": "MPa"},
             {"group": "Material", "symbol": "Fu", "value": num(Fu, 0),
              "unit": "MPa"},
             {"group": "Material", "symbol": "Xu", "value": num(Xu, 0),
              "unit": "MPa"},
             {"group": "Factors", "symbol": "phi_w", "value": num(PHI_W, 2),
              "unit": ""},
             {"group": "Geometry", "symbol": "t_thin",
              "value": num(t_thinner, 0), "unit": "mm"},
             {"group": "Geometry", "symbol": "t_thick",
              "value": num(t_thicker, 0), "unit": "mm"}]
    if weld_type == "Fillet Weld":
        props.append({"group": "Geometry", "symbol": "D",
                      "value": num(D, 0), "unit": "mm"})
        props.append({"group": "Geometry", "symbol": "aw",
                      "value": num(effective_throat(D), 2), "unit": "mm"})
    if Vr_gov_kN is not None:
        props.append({"group": "Results", "symbol": "Vr",
                      "value": num(Vr_gov_kN, 1), "unit": "kN"})
    if Tr_gov_kN is not None:
        props.append({"group": "Results", "symbol": "Tr",
                      "value": num(Tr_gov_kN, 1), "unit": "kN"})
    if U_gov is not None:
        props.append({"group": "Results", "symbol": "U",
                      "value": uc(U_gov), "unit": ""})
    MODEL["props"] = props


# ============================================================
# MODEL AND DIAGRAMS
# ============================================================
with col_model:
    st.subheader("Joint Model")

    if not HAS_VIEWER:
        st.info("3D viewer not loaded. Place viewer_3d_welded.py and "
                "viewer_3d_welded.html in the repository root.")
    else:
        viewer_3d_welded.render_joint(
            kind=MODEL["kind"], label=MODEL["label"],
            clause=MODEL["clause"], dims=MODEL["dims"],
            segments=MODEL["segments"], loads=MODEL["loads"],
            results=MODEL["results"], detailing=MODEL["detailing"],
            props=MODEL["props"], height=660, show_diagnostics=False)

        st.caption("The behaviour dropdown maps each calculation onto the "
                   "steel: the throat plane the area is taken on, the "
                   "orientation factor, the Mw reduction, each segment's "
                   "share of Vr, the utilisation, and the surface the "
                   "joint would rupture on. Rupture tears on the throat "
                   "when the weld metal governs and on the fusion face "
                   "when the base metal does.")

    st.markdown("#### Diagrams")
    if weld_type == "Fillet Weld" and segments:
        st.markdown("**Fillet weld cross-section**")
        _svg_html(svg_fillet_cross_section(D, segments[0]["theta"]),
                  height=280)

        st.markdown("**Weld group**")
        _svg_html(svg_weld_group(segments), height=320)

        st.markdown("**Detailing checks**")
        D_min_d = float(min_fillet_size(t_thicker))
        D_max_d = max_fillet_size(t_thinner)
        L_min_d = min_eff_length(D)
        L_det_d = segments[0]["L"] if segments else 100.0
        _svg_html(svg_detailing(D, D_min_d, D_max_d, L_det_d, L_min_d,
                                t_thinner, t_thicker), height=260)
    else:
        st.info("The SVG diagrams are drawn for fillet welds. Select "
                "Fillet Weld to see the cross-section and detailing "
                "visuals; the 3D model above covers every weld type.")
