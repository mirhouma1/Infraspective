from __future__ import annotations
import math
import streamlit as st
import streamlit.components.v1 as st_html

from _theme import apply_theme, render_sidebar_logo, render_footer, gate_disclaimer

# ============================================================
# CONFIG
# ============================================================

PHI_W = 0.67   # weld resistance factor (Cl. 13.13.1)
PHI   = 0.90   # base metal yielding
PHI_U = 0.75   # base metal fracture

# ============================================================
# TABLE 4 — Matching electrodes for G40.21 steels
# ============================================================

STEEL_GRADES: dict[int, tuple[float, float, int]] = {
    260: (260, 410, 490),
    300: (300, 440, 490),
    350: (350, 450, 490),
    380: (380, 480, 490),
    400: (400, 490, 550),
    480: (480, 550, 620),
    700: (700, 700, 820),
}

# ============================================================
# DETAILING LIMITS (Cl. 6.2.3)
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
    """Fillet weld effective throat = D / sqrt(2)."""
    return D / math.sqrt(2)


def fillet_Aw(D: float, L: float) -> float:
    """Effective throat area = throat × length (mm²)."""
    return effective_throat(D) * L


def orientation_factor(theta_deg: float) -> float:
    """(1 + 0.5 × sin^1.5(theta)) — load angle factor for fillet weld."""
    t = math.radians(theta_deg)
    return 1.0 + 0.50 * (math.sin(t) ** 1.5)


def Mw_factor(theta1: float, theta2_nearest90: float) -> float:
    """Multi-orientation strength reduction factor."""
    return (0.85 + theta1 / 600) / (0.85 + theta2_nearest90 / 600)


def vr_fillet_N(D: float, L: float, theta: float,
                Xu: float, Mw: float = 1.0) -> dict:
    """
    Fillet weld factored shear resistance (Cl. 13.13.2.2).
    Returns dict with intermediate values.
    """
    throat = effective_throat(D)
    Aw     = fillet_Aw(D, L)
    of_    = orientation_factor(theta)
    Vr     = 0.67 * PHI_W * Aw * Xu * of_ * Mw
    return {
        "throat_mm":     throat,
        "Aw_mm2":        Aw,
        "theta":         theta,
        "orient_factor": of_,
        "Mw":            Mw,
        "Vr_N":          Vr,
        "Vr_kN":         Vr / 1000,
    }


def vr_base_metal_N(Am_mm2: float, Fu: float) -> float:
    """Base metal shear check: Vr = 0.67·φw·Am·Fu (N)."""
    return 0.67 * PHI_W * Am_mm2 * Fu


def vr_groove_N(Am_mm2: float, Aw_mm2: float,
                Fu: float, Xu: float) -> dict:
    """
    Groove weld shear resistance (Cl. 13.13.2.1).
    Returns both cases and the governing lesser value.
    """
    Vr_base = 0.67 * PHI_W * Am_mm2 * Fu
    Vr_weld = 0.67 * PHI_W * Aw_mm2 * Xu
    gov     = min(Vr_base, Vr_weld)
    return {
        "Vr_base_N":  Vr_base, "Vr_base_kN": Vr_base / 1000,
        "Vr_weld_N":  Vr_weld, "Vr_weld_kN": Vr_weld / 1000,
        "Vr_N":       gov,     "Vr_kN":      gov / 1000,
        "governs":    "base metal" if Vr_base <= Vr_weld else "weld metal",
    }


def tr_pjp_N(An_mm2: float, Fu: float,
             Ag_mm2: float, Fy: float) -> dict:
    """PJP groove weld tension (Cl. 13.13.3.2)."""
    Tr_weld = PHI_W * An_mm2 * Fu
    Tr_cap  = PHI   * Ag_mm2 * Fy
    Tr      = min(Tr_weld, Tr_cap)
    return {
        "Tr_weld_kN": Tr_weld / 1000,
        "Tr_cap_kN":  Tr_cap  / 1000,
        "Tr_kN":      Tr      / 1000,
        "governs":    "weld" if Tr_weld <= Tr_cap else "base metal capacity",
    }


def tr_pjp_combined_N(An_mm2: float, Aw_mm2: float,
                      Fu: float, Xu: float,
                      Ag_mm2: float, Fy: float) -> dict:
    """PJP + fillet combined tension (Cl. 13.13.3.3)."""
    Tr_weld = PHI_W * math.sqrt((An_mm2 * Fu) ** 2 + (Aw_mm2 * Xu) ** 2)
    Tr_cap  = PHI   * Ag_mm2 * Fy
    Tr      = min(Tr_weld, Tr_cap)
    return {
        "Tr_weld_kN": Tr_weld / 1000,
        "Tr_cap_kN":  Tr_cap  / 1000,
        "Tr_kN":      Tr      / 1000,
        "governs":    "weld" if Tr_weld <= Tr_cap else "base metal capacity",
    }


def vr_flare_bevel_N(wf_mm: float, L_mm: float, Fu: float) -> dict:
    """Flare bevel groove weld shear (Cl. 13.13.2.3)."""
    Aw = 0.50 * wf_mm * L_mm
    Vr = 0.67 * PHI_W * Aw * Fu
    return {"Aw_mm2": Aw, "Vr_N": Vr, "Vr_kN": Vr / 1000}


# ============================================================
# SVG DIAGRAMS
# ============================================================

def _svg_html(svg: str, height: int = 280) -> None:
    """Render an SVG string via st_html to bypass Streamlit's HTML sanitiser."""
    st_html.html(
        f"<!DOCTYPE html><html><body style='margin:0;padding:0;background:transparent;'>"
        f"{svg}</body></html>",
        height=height,
    )


def svg_fillet_cross_section(D: float, theta: float) -> str:
    W, H = 380, 260
    cx, cy = 140, 130
    fl_w, fl_h, web_h, web_w = 100, 14, 80, 10
    weld_size = max(12, min(D * 3, 28))

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'style="font-family:\'Courier New\',monospace;background:#1e293b;border-radius:10px;">'
        f'<text x="{W//2}" y="20" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">Fillet Weld — Cross Section</text>'
        f'<rect x="{cx-fl_w//2}" y="{cy+web_h//2}" width="{fl_w}" height="{fl_h}" '
        f'fill="#475569" stroke="#94a3b8" stroke-width="1.5"/>'
        f'<rect x="{cx-web_w//2}" y="{cy-web_h//2}" width="{web_w}" height="{web_h}" '
        f'fill="#475569" stroke="#94a3b8" stroke-width="1.5"/>'
        f'<polygon points="{cx-web_w//2-weld_size},{cy+web_h//2} {cx-web_w//2},{cy+web_h//2} '
        f'{cx-web_w//2},{cy+web_h//2-weld_size}" fill="#f59e0b" stroke="#fbbf24" stroke-width="1"/>'
        f'<polygon points="{cx+web_w//2+weld_size},{cy+web_h//2} {cx+web_w//2},{cy+web_h//2} '
        f'{cx+web_w//2},{cy+web_h//2-weld_size}" fill="#f59e0b" stroke="#fbbf24" stroke-width="1"/>'
        f'<line x1="{cx-web_w//2-weld_size-4}" y1="{cy+web_h//2}" '
        f'x2="{cx-web_w//2-4}" y2="{cy+web_h//2}" stroke="#22c55e" stroke-width="1.5"/>'
        f'<text x="{cx-web_w//2-weld_size//2-4}" y="{cy+web_h//2+14}" '
        f'fill="#22c55e" font-size="10" text-anchor="middle">D={D:.0f}mm</text>'
        f'<line x1="{cx-web_w//2-2}" y1="{cy+web_h//2}" '
        f'x2="{cx-web_w//2-weld_size//2-2}" y2="{cy+web_h//2-weld_size//2}" '
        f'stroke="#60a5fa" stroke-width="1.5" stroke-dasharray="3,2"/>'
        f'<text x="{cx-web_w//2-weld_size-10}" y="{cy+web_h//2-weld_size//2-4}" '
        f'fill="#60a5fa" font-size="9">throat={D/math.sqrt(2):.1f}mm</text>'
        f'<defs><marker id="arrf" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">'
        f'<polygon points="0 0,8 3,0 6" fill="#f59e0b"/></marker></defs>'
        f'<text x="280" y="60"  fill="#e2e8f0" font-size="11" font-weight="bold">Load angle</text>'
        f'<text x="280" y="78"  fill="#f59e0b" font-size="13" font-weight="bold">theta = {theta:.0f} deg</text>'
        f'<text x="280" y="96"  fill="#94a3b8" font-size="10">'
        f'{"Transverse" if theta == 90 else "Longitudinal" if theta == 0 else "Inclined"}</text>'
        f'<text x="280" y="124" fill="#e2e8f0" font-size="10">Orient. factor:</text>'
        f'<text x="280" y="140" fill="#22c55e" font-size="12" font-weight="bold">'
        f'{orientation_factor(theta):.3f}</text>'
        f'<text x="{cx}" y="{cy+web_h//2+fl_h+18}" fill="#94a3b8" font-size="10" '
        f'text-anchor="middle">Base plate</text>'
        f'<text x="{cx+fl_w//2+8}" y="{cy}" fill="#94a3b8" font-size="10">Web</text>'
        f'<text x="{cx-web_w//2-weld_size//2-4}" y="{cy+web_h//2-weld_size-8}" '
        f'fill="#f59e0b" font-size="10">Fillet weld</text>'
        f'</svg>'
    )
    return svg


def svg_weld_group(segments: list[dict]) -> str:
    W, H = 420, 300
    cx, cy = 160, 150
    plate_w, plate_h = 200, 100
    colors = ["#f59e0b", "#22c55e", "#60a5fa", "#f97316", "#a78bfa"]

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'style="font-family:\'Courier New\',monospace;background:#1e293b;border-radius:10px;">'
        f'<text x="{W//2}" y="20" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">Weld Group — {len(segments)} segment(s)</text>'
        f'<rect x="{cx-plate_w//2}" y="{cy-plate_h//2}" width="{plate_w}" height="{plate_h}" '
        f'fill="#334155" stroke="#64748b" stroke-width="2" rx="3"/>'
        f'<defs><marker id="arrg" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">'
        f'<polygon points="0 0,8 3,0 6" fill="#f59e0b"/></marker></defs>'
        f'<line x1="{cx-plate_w//2-35}" y1="{cy}" x2="{cx-plate_w//2-5}" y2="{cy}" '
        f'stroke="#f59e0b" stroke-width="2.5" marker-end="url(#arrg)"/>'
        f'<text x="{cx-plate_w//2-42}" y="{cy-6}" fill="#f59e0b" font-size="10" '
        f'text-anchor="middle">Vu</text>'
    )

    for i, seg in enumerate(segments):
        col   = colors[i % len(colors)]
        theta = seg.get("theta", 0)
        L     = seg.get("L", 100)
        label = f"Seg {i+1}: theta={theta:.0f} deg  L={L:.0f}mm"

        if abs(theta - 90) < 5:
            x1 = cx + plate_w // 2; y1 = cy - plate_h // 2
            x2 = cx + plate_w // 2; y2 = cy + plate_h // 2
        else:
            side  = 1 if i % 2 == 0 else -1
            y_pos = cy - side * plate_h // 2
            x1 = cx - plate_w // 4; y1 = y_pos
            x2 = cx + plate_w // 4; y2 = y_pos

        svg += (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{col}" stroke-width="5" opacity="0.85"/>'
            f'<rect x="295" y="{50 + i * 22}" width="14" height="10" fill="{col}"/>'
            f'<text x="313" y="{50 + i * 22 + 9}" fill="{col}" font-size="10">{label}</text>'
        )

    svg += '</svg>'
    return svg


def svg_detailing(D: float, D_min: float, D_max: float,
                  L: float, L_min: float,
                  t_thinner: float, t_thicker: float) -> str:
    W, H = 420, 240
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'style="font-family:\'Courier New\',monospace;background:#1e293b;border-radius:10px;">'
        f'<text x="{W//2}" y="20" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">Detailing Checks</text>'
    )

    checks = [
        ("Min fillet size", D_min, D,    ">=", "D_min", "mm"),
        ("Max fillet size", D,     D_max, "<=", "D_max", "mm"),
        ("Min eff. length", L_min, L,    ">=", "L_min", "mm"),
    ]

    bar_x0, bar_w = 200, 170
    for i, (label, limit, actual, op, lim_label, unit) in enumerate(checks):
        y = 50 + i * 58
        if op == ">=":
            ok         = actual >= limit
            fill_ratio = min(actual / max(limit, 0.001), 1.5)
        else:
            ok         = actual <= limit
            fill_ratio = min(actual / max(limit, 0.001), 1.0)

        col      = "#22c55e" if ok else "#ef4444"
        icon     = "PASS" if ok else "FAIL"
        bar_fill = min(fill_ratio * bar_w, bar_w * 1.3)
        ref_x    = bar_x0 + bar_w * min(1.0, limit / max(actual, 0.001))

        svg += (
            f'<text x="10" y="{y+12}" fill="#e2e8f0" font-size="11" font-weight="bold">{label}</text>'
            f'<text x="10" y="{y+26}" fill="#94a3b8" font-size="10">'
            f'{lim_label}={limit:.1f} {unit},  actual={actual:.1f} {unit}</text>'
            f'<rect x="{bar_x0}" y="{y}" width="{bar_w}" height="20" fill="#1e293b" rx="3"/>'
            f'<rect x="{bar_x0}" y="{y}" width="{bar_fill:.0f}" height="20" '
            f'fill="{col}" opacity="0.75" rx="3"/>'
            f'<line x1="{ref_x:.0f}" y1="{y-3}" x2="{ref_x:.0f}" y2="{y+23}" '
            f'stroke="white" stroke-width="2" stroke-dasharray="3,2"/>'
            f'<text x="{bar_x0+bar_w+8}" y="{y+14}" fill="{col}" font-size="11" '
            f'font-weight="bold">{icon}</text>'
        )

    svg += '</svg>'
    return svg


# ============================================================
# STREAMLIT UI
# ============================================================

apply_theme()
render_sidebar_logo()
render_footer()
gate_disclaimer()
from _theme import beta_lock_page
beta_lock_page("Welded Connections")

st.title("CSA S16 — Welded Connection Solver")
st.caption(
    "Cl. 13.13  |  Fillet, CJP/PJP Groove, Flare Bevel  |  "
    "phi_w = 0.67  |  Detailing per Cl. 6.2.3"
)
st.markdown("---")

# ── Section 1: Weld Type ──────────────────────────────────────────────────────

st.subheader("1. Weld Type")
weld_type = st.selectbox(
    "Select weld type",
    [
        "Fillet Weld",
        "Complete Joint Penetration (CJP) Groove",
        "Partial Joint Penetration (PJP) Groove",
        "Flare Bevel Groove",
    ],
    key="weld_type",
)
st.markdown("---")

# ── Section 2: Material ───────────────────────────────────────────────────────

st.subheader("2. Material")
mat1, mat2, mat3 = st.columns(3)

with mat1:
    grade_label = st.selectbox(
        "Steel grade (G40.21)",
        [f"G40.21-{g}" for g in STEEL_GRADES],
        index=2,
        key="steel_grade",
    )
    grade_val                          = int(grade_label.split("-")[1])
    Fy_default, Fu_default, Xu_default = STEEL_GRADES[grade_val]

with mat2:
    Fy = st.number_input("Fy (MPa)", min_value=200.0, value=float(Fy_default), step=5.0, key="Fy")
    Fu = st.number_input("Fu (MPa)", min_value=200.0, value=float(Fu_default), step=5.0, key="Fu")

with mat3:
    Xu = st.number_input(
        f"Electrode Xu (MPa)  [Table 4 match = {Xu_default}]",
        min_value=300.0, value=float(Xu_default), step=10.0, key="Xu",
    )
    st.caption("Xu = 10 x first two digits of electrode classification (CSA W48)")

st.markdown("---")

# ── Section 3: Geometry ───────────────────────────────────────────────────────

st.subheader("3. Geometry")

# Declare variables that may be referenced later so they always exist
segments:      list[dict] = []
check_base:    bool       = False
Am_mm2:        float      = 0.0
Am_mm2_groove: float      = 0.0
Aw_mm2:        float      = 0.0
An_mm2:        float      = 0.0
Ag_mm2:        float      = 0.0
has_fillet:    bool       = False
Aw_fillet_mm2: float      = 0.0
wf_mm:         float      = 0.0
L_fb:          float      = 0.0
D:             float      = 8.0

if weld_type == "Fillet Weld":
    g1, g2 = st.columns(2)
    with g1:
        D      = st.number_input("Weld leg size D (mm)", min_value=3.0, value=8.0, step=1.0, key="D")
        n_segs = int(st.number_input(
            "Number of weld segments", min_value=1, max_value=6, value=1, step=1, key="n_segs"
        ))

        st.markdown("**Weld segments** *(each with length L and orientation theta)*")
        st.caption(
            "Note: Weld returns not accounted for in joint capacity "
            "may be excluded from segment definition (Cl. 13.13.2.2)."
        )
        seg_cols = st.columns(min(n_segs, 3))
        for i in range(n_segs):
            col_ctx = seg_cols[i % 3] if n_segs <= 3 else st.container()
            with col_ctx:
                st.markdown(f"**Segment {i+1}**")
                L_i     = st.number_input(
                    f"L_{i+1} (mm)", min_value=1.0, value=100.0, step=5.0, key=f"L_{i}"
                )
                theta_i = st.number_input(
                    f"theta_{i+1} (deg)  [0 = longitudinal, 90 = transverse]",
                    min_value=0.0, max_value=90.0,
                    value=90.0 if i == 0 else 0.0,
                    step=5.0, key=f"theta_{i}",
                )
                segments.append({"L": L_i, "theta": theta_i})

    with g2:
        check_base = st.checkbox("Check base metal (over-matched electrodes)?", key="chk_base")
        if check_base:
            Am_mm2 = st.number_input(
                "Am — fusion face shear area (mm2)", min_value=0.0, value=1000.0, step=50.0, key="Am_fillet"
            )

elif weld_type in ("Complete Joint Penetration (CJP) Groove",
                   "Partial Joint Penetration (PJP) Groove"):
    g1, g2 = st.columns(2)
    with g1:
        Am_mm2_groove = st.number_input(
            "Am — shear area of fusion face (mm2)", min_value=0.0, value=2000.0, step=50.0, key="Am_groove"
        )
        Aw_mm2 = st.number_input(
            "Aw — effective weld throat area (mm2)", min_value=0.0, value=2000.0, step=50.0, key="Aw_groove"
        )
    with g2:
        if "Partial" in weld_type:
            st.markdown("**PJP — Tension check**")
            An_mm2 = st.number_input(
                "An — nominal fusion face area (mm2)", min_value=0.0, value=2000.0, step=50.0, key="An"
            )
            Ag_mm2 = st.number_input(
                "Ag — gross area of tension member (mm2)", min_value=0.0, value=3000.0, step=50.0, key="Ag"
            )
            has_fillet = st.checkbox("Combined with fillet weld? (Cl. 13.13.3.3)", key="has_fillet")
            if has_fillet:
                Aw_fillet_mm2 = st.number_input(
                    "Aw_fillet — fillet throat area (mm2)", min_value=0.0, value=500.0, step=50.0, key="Aw_fillet"
                )

elif weld_type == "Flare Bevel Groove":
    g1, _ = st.columns(2)
    with g1:
        wf_mm = st.number_input(
            "wf — width of flare bevel groove face (mm)", min_value=1.0, value=20.0, step=1.0, key="wf"
        )
        L_fb  = st.number_input(
            "L — weld length (mm)", min_value=1.0, value=150.0, step=5.0, key="L_fb"
        )

st.markdown("---")

# ── Section 4: Plate detailing geometry ──────────────────────────────────────

st.subheader("4. Plate Detailing Geometry")
det1, det2 = st.columns(2)
with det1:
    t_thinner = st.number_input(
        "t_thinner — thinner part joined (mm)", min_value=1.0, value=10.0, step=1.0, key="t_thin"
    )
    t_thicker = st.number_input(
        "t_thicker — thicker part joined (mm)", min_value=1.0, value=12.0, step=1.0, key="t_thick"
    )
with det2:
    is_lap = st.checkbox("Lap joint?", key="is_lap")
    L_lap  = 0.0
    if is_lap:
        L_lap = st.number_input(
            "Lap overlap length L (mm)", min_value=0.0, value=80.0, step=5.0, key="L_lap"
        )

st.markdown("---")

# ── Section 5: Results ────────────────────────────────────────────────────────

st.subheader("5. Results")
res_col, diag_col = st.columns([3, 2], gap="large")

with res_col:

    # ══════════════════════════════════════════════════════════════════════════
    # FILLET WELD
    # ══════════════════════════════════════════════════════════════════════════
    if weld_type == "Fillet Weld":

        # ── Step 1: Effective Throat & Weld Area ──────────────────────────────
        st.markdown("#### Step 1 — Effective Throat & Weld Area  *(Cl. 13.13.2.2)*")
        st.latex(r"a_w = \frac{D}{\sqrt{2}} \qquad A_w = a_w \times L")

        throat = effective_throat(D)
        lines  = [f"  Throat  aw = {D:.1f} / sqrt(2) = {throat:.3f} mm", ""]
        for i, s in enumerate(segments):
            Aw_i = fillet_Aw(D, s["L"])
            lines.append(
                f"  Seg {i+1}: Aw = {throat:.3f} x {s['L']:.0f} = {Aw_i:.2f} mm2"
            )
        st.code("\n".join(lines), language="text")

        with st.expander("📐 Show calculation steps", expanded=True):
            throat_rows = [
                "**Effective Throat & Weld Area — CSA S16 Cl. 13.13.2.2**",
                "- Formula: aw = D / √2",
                f"- Substitute: aw = {D:.1f} / √2",
                f"- Result: **aw = {throat:.3f} mm**",
            ]
            for i, s in enumerate(segments):
                Aw_i = fillet_Aw(D, s["L"])
                throat_rows.append(f"- Seg {i+1} — Formula: Aw = aw × L")
                throat_rows.append(f"- Seg {i+1} — Substitute: Aw = {throat:.3f} × {s['L']:.0f}")
                throat_rows.append(f"- Seg {i+1} — Result: **Aw = {Aw_i:.2f} mm²**")
            st.markdown("\n".join(throat_rows))

        # ── Step 2: Multi-Orientation Factor Mw ──────────────────────────────
        st.markdown("#### Step 2 — Multi-Orientation Factor Mw  *(Cl. 13.13.2.2)*")
        st.latex(r"M_w = \frac{0.85 + \theta_1/600}{0.85 + \theta_2/600}")
        st.markdown(
            "- **theta_1** = orientation of the weld segment under consideration  \n"
            "- **theta_2** = orientation of the weld segment in the joint nearest to 90 deg  \n"
            "- For a **single weld orientation** — Mw = 1.0"
        )

        theta_max = max(s["theta"] for s in segments)
        idx_max   = max(range(len(segments)), key=lambda i: segments[i]["theta"])

        if len(segments) == 1:
            st.code(
                f"  Single weld orientation\n"
                f"  theta = {segments[0]['theta']:.0f} deg  ->  Mw = 1.0",
                language="text",
            )
            mw_values = [1.0]
        else:
            st.code(
                f"  theta_2 identified as Seg {idx_max+1}  "
                f"(theta = {theta_max:.0f} deg, nearest to 90 deg)",
                language="text",
            )
            mw_values = []
            for i, s in enumerate(segments):
                Mw_i  = Mw_factor(s["theta"], theta_max)
                num   = 0.85 + s["theta"] / 600
                denom = 0.85 + theta_max  / 600
                mw_values.append(Mw_i)
                st.code(
                    f"  Seg {i+1}:  theta_1 = {s['theta']:.0f} deg   theta_2 = {theta_max:.0f} deg\n"
                    f"          Mw = (0.85 + {s['theta']:.0f}/600) / (0.85 + {theta_max:.0f}/600)\n"
                    f"             = {num:.5f} / {denom:.5f}\n"
                    f"             = {Mw_i:.4f}",
                    language="text",
                )

        with st.expander("📐 Show calculation steps", expanded=True):
            mw_rows = [
                "**Multi-Orientation Factor Mw — CSA S16 Cl. 13.13.2.2**",
                "- Formula: Mw = (0.85 + θ₁/600) / (0.85 + θ₂/600)",
            ]
            if len(segments) == 1:
                mw_rows.append(
                    f"- Single weld orientation (θ = {segments[0]['theta']:.0f}°) → Mw = 1.0"
                )
                mw_rows.append("- Result: **Mw = 1.000**")
            else:
                mw_rows.append(f"- θ₂ = {theta_max:.0f}° (Seg {idx_max+1}, nearest to 90°)")
                for i, s in enumerate(segments):
                    num = 0.85 + s["theta"] / 600
                    denom = 0.85 + theta_max / 600
                    mw_rows.append(
                        f"- Seg {i+1} — Substitute: Mw = (0.85 + {s['theta']:.0f}/600) / "
                        f"(0.85 + {theta_max:.0f}/600) = {num:.5f} / {denom:.5f}"
                    )
                    mw_rows.append(f"- Seg {i+1} — Result: **Mw = {mw_values[i]:.4f}**")
            st.markdown("\n".join(mw_rows))

        # ── Step 3: Factored Shear Resistance Vr per segment ──────────────────
        st.markdown("#### Step 3 — Factored Shear Resistance Vr  *(Cl. 13.13.2.2)*")
        st.latex(r"V_r = 0.67\,\phi_w\,A_w\,X_u\,(1.00 + 0.50\sin^{1.5}\!\theta)\,M_w")
        st.markdown(
            f"- **phi_w** = {PHI_W}  \n"
            f"- **Xu** = {Xu:.0f} MPa  \n"
            "- **Aw** = effective throat x length  \n"
            "- **theta** = angle of weld segment to line of action of applied force  \n"
            "- **Mw** = multi-orientation reduction factor"
        )

        total_Vr_kN = 0.0
        seg_results: list[dict] = []

        for i, s in enumerate(segments):
            Mw_i      = mw_values[i]
            res       = vr_fillet_N(D, s["L"], s["theta"], Xu, Mw_i)
            seg_results.append(res)
            total_Vr_kN += res["Vr_kN"]

            sin_t   = math.sin(math.radians(s["theta"]))
            sin15_t = sin_t ** 1.5
            of_val  = 1.00 + 0.50 * sin15_t

            st.code(
                f"  Seg {i+1}:  theta = {s['theta']:.0f} deg   L = {s['L']:.0f} mm   D = {D:.0f} mm\n"
                f"\n"
                f"  Throat:       aw  = {D:.1f} / sqrt(2) = {res['throat_mm']:.3f} mm\n"
                f"  Weld area:    Aw  = {res['throat_mm']:.3f} x {s['L']:.0f} = {res['Aw_mm2']:.2f} mm2\n"
                f"\n"
                f"  sin(theta)         = sin({s['theta']:.0f} deg) = {sin_t:.4f}\n"
                f"  sin^1.5(theta)     = ({sin_t:.4f})^1.5 = {sin15_t:.4f}\n"
                f"  Orient. factor     = 1.00 + 0.50 x {sin15_t:.4f} = {of_val:.4f}\n"
                f"\n"
                f"  Mw                 = {Mw_i:.4f}\n"
                f"\n"
                f"  Vr = 0.67 x {PHI_W} x {res['Aw_mm2']:.2f} x {Xu:.0f} x {of_val:.4f} x {Mw_i:.4f}\n"
                f"     = {res['Vr_kN']:.2f} kN",
                language="text",
            )

            with st.expander("📐 Show calculation steps", expanded=True):
                st.markdown("\n".join([
                    f"**Factored Shear Resistance Vr — Seg {i+1} — CSA S16 Cl. 13.13.2.2**",
                    "- Orientation factor formula: 1.00 + 0.50·sin¹·⁵θ",
                    f"- Substitute: 1.00 + 0.50 × sin¹·⁵({s['theta']:.0f}°) = 1.00 + 0.50 × {sin15_t:.4f}",
                    f"- Result: **orientation factor = {of_val:.4f}**",
                    "- Formula: Vr = 0.67·φw·Aw·Xu·(orientation factor)·Mw",
                    f"- Substitute: Vr = 0.67 × {PHI_W} × {res['Aw_mm2']:.2f} × {Xu:.0f} × {of_val:.4f} × {Mw_i:.4f}",
                    f"- Result: **Vr = {res['Vr_kN']:.2f} kN**",
                ]))

        st.markdown("---")
        st.markdown(f"**Total Vr (all segments) = {total_Vr_kN:.2f} kN**")
        _sub_total_vr = " + ".join(f"{r['Vr_kN']:.2f}" for r in seg_results)
        with st.expander("📐 Show calculation steps", expanded=True):
            st.markdown("\n".join([
                "**Total Factored Shear Resistance — CSA S16 Cl. 13.13.2.2**",
                "- Formula: Vr,total = Σ Vr,i",
                f"- Substitute: Vr,total = {_sub_total_vr}",
                f"- Result: **Vr,total = {total_Vr_kN:.2f} kN**",
            ]))
        st.markdown("---")

        # ── Step 4: Base metal check (optional) ──────────────────────────────
        if check_base and Am_mm2 > 0:
            st.markdown("#### Step 4 — Base Metal Check  *(Cl. 13.13.2.2)*")
            st.latex(r"V_r = 0.67\,\phi_w\,A_m\,F_u")
            Vr_bm = vr_base_metal_N(Am_mm2, Fu) / 1000
            st.code(
                f"  Vr = 0.67 x {PHI_W} x {Am_mm2:.0f} x {Fu:.0f}\n"
                f"     = {Vr_bm:.2f} kN",
                language="text",
            )
            with st.expander("📐 Show calculation steps", expanded=True):
                st.markdown("\n".join([
                    "**Base Metal Shear Check — CSA S16 Cl. 13.13.2.2**",
                    "- Formula: Vr = 0.67·φw·Am·Fu",
                    f"- Substitute: Vr = 0.67 × {PHI_W} × {Am_mm2:.0f} × {Fu:.0f}",
                    f"- Result: **Vr = {Vr_bm:.2f} kN**",
                ]))
            gov_Vr = min(total_Vr_kN, Vr_bm)
            st.markdown("---")
            if gov_Vr == total_Vr_kN:
                st.success(
                    f"PASS — Weld metal governs: **Vr = {total_Vr_kN:.2f} kN** "
                    f"(base metal Vr = {Vr_bm:.2f} kN)"
                )
            else:
                st.warning(
                    f"NOTE — Base metal governs: **Vr = {Vr_bm:.2f} kN** "
                    f"(weld metal Vr = {total_Vr_kN:.2f} kN)"
                )
            with st.expander("📐 Show calculation steps", expanded=True):
                st.markdown("\n".join([
                    "**Governing Factored Shear Resistance — CSA S16 Cl. 13.13.2.2**",
                    "- Formula: Vr = min(weld metal Vr, base metal Vr)",
                    f"- Substitute: Vr = min({total_Vr_kN:.2f} kN, {Vr_bm:.2f} kN)",
                    f"- Result: **Vr = {gov_Vr:.2f} kN**",
                ]))
        else:
            gov_Vr = total_Vr_kN
            st.success(f"**Governing Vr = {gov_Vr:.2f} kN**")
            with st.expander("📐 Show calculation steps", expanded=True):
                st.markdown("\n".join([
                    "**Governing Factored Shear Resistance — CSA S16 Cl. 13.13.2.2**",
                    "- Formula: Vr = Σ Vr,i (weld metal governs — no base-metal check requested)",
                    f"- Substitute: Vr = {total_Vr_kN:.2f} kN",
                    f"- Result: **Vr = {gov_Vr:.2f} kN**",
                ]))

        st.info(
            "Weld returns not accounted for in the joint capacity "
            "need not be considered a weld segment for the purpose of Cl. 13.13.2.2."
        )

    # ══════════════════════════════════════════════════════════════════════════
    # CJP / PJP GROOVE
    # ══════════════════════════════════════════════════════════════════════════
    elif weld_type in ("Complete Joint Penetration (CJP) Groove",
                       "Partial Joint Penetration (PJP) Groove"):

        st.markdown("#### Step 1 — Groove Weld Shear Resistance  *(Cl. 13.13.2.1)*")
        st.latex(
            r"V_r = \min\begin{cases}"
            r"0.67\,\phi_w\,A_m\,F_u & \text{(base metal)}\\"
            r"0.67\,\phi_w\,A_w\,X_u & \text{(weld metal)}"
            r"\end{cases}"
        )
        res_g = vr_groove_N(Am_mm2_groove, Aw_mm2, Fu, Xu)
        st.code(
            f"  Case (a) base metal: 0.67 x {PHI_W} x {Am_mm2_groove:.0f} x {Fu:.0f}"
            f" = {res_g['Vr_base_kN']:.2f} kN\n"
            f"  Case (b) weld metal: 0.67 x {PHI_W} x {Aw_mm2:.0f} x {Xu:.0f}"
            f"       = {res_g['Vr_weld_kN']:.2f} kN\n"
            f"  ──────────────────────────────────────────────────────\n"
            f"  Governing ({res_g['governs']}): Vr = {res_g['Vr_kN']:.2f} kN",
            language="text",
        )
        st.success(
            f"**Vr = {res_g['Vr_kN']:.2f} kN** — governed by {res_g['governs']}"
        )
        with st.expander("📐 Show calculation steps", expanded=True):
            st.markdown("\n".join([
                "**Groove Weld Shear Resistance — CSA S16 Cl. 13.13.2.1**",
                "- Base metal formula: Vr = 0.67·φw·Am·Fu",
                f"- Substitute: Vr = 0.67 × {PHI_W} × {Am_mm2_groove:.0f} × {Fu:.0f}",
                f"- Result: **Vr(base metal) = {res_g['Vr_base_kN']:.2f} kN**",
                "- Weld metal formula: Vr = 0.67·φw·Aw·Xu",
                f"- Substitute: Vr = 0.67 × {PHI_W} × {Aw_mm2:.0f} × {Xu:.0f}",
                f"- Result: **Vr(weld metal) = {res_g['Vr_weld_kN']:.2f} kN**",
                f"- Governing (least): **Vr = {res_g['Vr_kN']:.2f} kN** ({res_g['governs']})",
            ]))
        st.markdown("---")

        if weld_type == "Complete Joint Penetration (CJP) Groove":
            st.markdown("#### Step 2 — Tension Resistance  *(Cl. 13.13.3.1)*")
            st.info(
                "CJP groove weld with matching electrodes: "
                "**Tr = base metal capacity** (full strength restoration)."
            )
            st.latex(
                r"T_r = \phi \cdot A_g \cdot F_y \quad "
                r"\text{(base metal governs — full restoration)}"
            )
            with st.expander("📐 Show calculation steps", expanded=True):
                st.markdown("\n".join([
                    "**CJP Groove Tension Resistance — CSA S16 Cl. 13.13.3.1**",
                    "- Formula: Tr = φ·Ag·Fy",
                    "- Substitute: matching electrodes fully restore the base metal strength",
                    "- Result: **Tr = full base metal tension capacity (φ·Ag·Fy)**",
                ]))

        else:   # PJP
            st.markdown("#### Step 2 — Tension Resistance  *(Cl. 13.13.3.2 / 13.13.3.3)*")
            if not has_fillet:
                st.latex(r"T_r = \phi_w\,A_n\,F_u \leq \phi\,A_g\,F_y")
                res_t = tr_pjp_N(An_mm2, Fu, Ag_mm2, Fy)
                st.code(
                    f"  Tr_weld = {PHI_W} x {An_mm2:.0f} x {Fu:.0f} = {res_t['Tr_weld_kN']:.2f} kN\n"
                    f"  Tr_cap  = {PHI}   x {Ag_mm2:.0f} x {Fy:.0f}  = {res_t['Tr_cap_kN']:.2f} kN\n"
                    f"  Governing ({res_t['governs']}): Tr = {res_t['Tr_kN']:.2f} kN",
                    language="text",
                )
                st.success(f"**Tr = {res_t['Tr_kN']:.2f} kN**")
                with st.expander("📐 Show calculation steps", expanded=True):
                    st.markdown("\n".join([
                        "**PJP Groove Tension Resistance — CSA S16 Cl. 13.13.3.2**",
                        "- Weld formula: Tr = φw·An·Fu",
                        f"- Substitute: Tr = {PHI_W} × {An_mm2:.0f} × {Fu:.0f}",
                        f"- Result: **Tr(weld) = {res_t['Tr_weld_kN']:.2f} kN**",
                        "- Base metal formula: Tr = φ·Ag·Fy",
                        f"- Substitute: Tr = {PHI} × {Ag_mm2:.0f} × {Fy:.0f}",
                        f"- Result: **Tr(base metal capacity) = {res_t['Tr_cap_kN']:.2f} kN**",
                        f"- Governing (least): **Tr = {res_t['Tr_kN']:.2f} kN** ({res_t['governs']})",
                    ]))
            else:
                st.latex(
                    r"T_r = \phi_w\sqrt{(A_n F_u)^2 + (A_w X_u)^2} \leq \phi\,A_g\,F_y"
                )
                res_tc = tr_pjp_combined_N(An_mm2, Aw_fillet_mm2, Fu, Xu, Ag_mm2, Fy)
                st.code(
                    f"  An x Fu       = {An_mm2:.0f} x {Fu:.0f}  = {An_mm2*Fu:.0f} N\n"
                    f"  Aw x Xu       = {Aw_fillet_mm2:.0f} x {Xu:.0f}  = {Aw_fillet_mm2*Xu:.0f} N\n"
                    f"\n"
                    f"  Tr_weld = {PHI_W} x sqrt({An_mm2*Fu:.0f}^2 + {Aw_fillet_mm2*Xu:.0f}^2)\n"
                    f"          = {res_tc['Tr_weld_kN']:.2f} kN\n"
                    f"  Tr_cap  = {PHI} x {Ag_mm2:.0f} x {Fy:.0f} = {res_tc['Tr_cap_kN']:.2f} kN\n"
                    f"  Governing ({res_tc['governs']}): Tr = {res_tc['Tr_kN']:.2f} kN",
                    language="text",
                )
                st.success(f"**Tr = {res_tc['Tr_kN']:.2f} kN**")
                with st.expander("📐 Show calculation steps", expanded=True):
                    st.markdown("\n".join([
                        "**PJP + Fillet Combined Tension — CSA S16 Cl. 13.13.3.3**",
                        "- Weld formula: Tr = φw·√((An·Fu)² + (Aw·Xu)²)",
                        f"- Substitute: Tr = {PHI_W} × √(({An_mm2:.0f}×{Fu:.0f})² + ({Aw_fillet_mm2:.0f}×{Xu:.0f})²)",
                        f"- Result: **Tr(weld) = {res_tc['Tr_weld_kN']:.2f} kN**",
                        "- Base metal formula: Tr = φ·Ag·Fy",
                        f"- Substitute: Tr = {PHI} × {Ag_mm2:.0f} × {Fy:.0f}",
                        f"- Result: **Tr(base metal capacity) = {res_tc['Tr_cap_kN']:.2f} kN**",
                        f"- Governing (least): **Tr = {res_tc['Tr_kN']:.2f} kN** ({res_tc['governs']})",
                    ]))

    # ══════════════════════════════════════════════════════════════════════════
    # FLARE BEVEL GROOVE
    # ══════════════════════════════════════════════════════════════════════════
    elif weld_type == "Flare Bevel Groove":
        st.markdown("#### Step 1 — Flare Bevel Shear Resistance  *(Cl. 13.13.2.3)*")
        st.latex(r"V_r = 0.67\,\phi_w\,A_w\,F_u \qquad A_w = 0.50\,w_f\,L")
        res_fb = vr_flare_bevel_N(wf_mm, L_fb, Fu)
        st.code(
            f"  Aw = 0.50 x {wf_mm:.0f} x {L_fb:.0f} = {res_fb['Aw_mm2']:.0f} mm2\n"
            f"  Vr = 0.67 x {PHI_W} x {res_fb['Aw_mm2']:.0f} x {Fu:.0f}\n"
            f"     = {res_fb['Vr_kN']:.2f} kN",
            language="text",
        )
        st.success(f"**Vr = {res_fb['Vr_kN']:.2f} kN**")
        with st.expander("📐 Show calculation steps", expanded=True):
            st.markdown("\n".join([
                "**Flare Bevel Groove Shear Resistance — CSA S16 Cl. 13.13.2.3**",
                "- Area formula: Aw = 0.50·wf·L",
                f"- Substitute: Aw = 0.50 × {wf_mm:.0f} × {L_fb:.0f}",
                f"- Result: **Aw = {res_fb['Aw_mm2']:.0f} mm²**",
                "- Formula: Vr = 0.67·φw·Aw·Fu",
                f"- Substitute: Vr = 0.67 × {PHI_W} × {res_fb['Aw_mm2']:.0f} × {Fu:.0f}",
                f"- Result: **Vr = {res_fb['Vr_kN']:.2f} kN**",
            ]))

    # ══════════════════════════════════════════════════════════════════════════
    # DETAILING CHECKS (all weld types)
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("#### Detailing Checks  *(Cl. 6.2.3)*")

    if weld_type == "Fillet Weld":
        D_min = min_fillet_size(t_thicker)
        D_max = max_fillet_size(t_thinner)
        L_det = segments[0]["L"] if segments else 100.0
        L_min = min_eff_length(D)

        st.latex(
            r"D_{min}\ \text{(Table)} \qquad "
            r"D_{max} = t_{thinner} - 2\ (t \geq 6\,\text{mm}) \qquad "
            r"L_{eff} \geq \max(38,\,4D)"
        )

        d_min_ok  = D >= D_min
        d_max_ok  = D <= D_max
        l_eff_ok  = L_det >= L_min

        st.code(
            f"  D_min (Table, t_thicker = {t_thicker:.0f} mm) = {D_min} mm  ->  "
            f"D = {D:.0f} mm  {'PASS' if d_min_ok else 'FAIL'}\n"
            f"  D_max (t_thinner = {t_thinner:.0f} mm)        = {D_max:.0f} mm  ->  "
            f"D = {D:.0f} mm  {'PASS' if d_max_ok else 'FAIL'}\n"
            f"  L_eff_min = max(38, 4x{D:.0f})              = {L_min:.0f} mm  ->  "
            f"L = {L_det:.0f} mm  {'PASS' if l_eff_ok else 'FAIL'}",
            language="text",
        )
        with st.expander("📐 Show calculation steps", expanded=True):
            st.markdown("\n".join([
                "**Fillet Weld Detailing Checks — CSA S16 Cl. 6.2.3**",
                f"- Min fillet size (Table, t_thicker = {t_thicker:.0f} mm): D_min = {D_min} mm ; "
                f"D = {D:.0f} mm → **{'PASS' if d_min_ok else 'FAIL'}**",
                f"- Max fillet size: D_max = t_thinner − 2 (t ≥ 6 mm) = {D_max:.0f} mm ; "
                f"D = {D:.0f} mm → **{'PASS' if d_max_ok else 'FAIL'}**",
                f"- Min effective length: L_min = max(38, 4D) = max(38, 4×{D:.0f}) = {L_min:.0f} mm ; "
                f"L = {L_det:.0f} mm → **{'PASS' if l_eff_ok else 'FAIL'}**",
            ]))

        if is_lap and L_lap > 0:
            L_lap_min = lap_min_overlap(t_thinner, t_thicker)
            lap_ok    = L_lap >= L_lap_min
            st.code(
                f"  Lap min overlap = max(5x{min(t_thinner,t_thicker):.0f}, 25)"
                f" = {L_lap_min:.0f} mm  ->  L = {L_lap:.0f} mm  "
                f"{'PASS' if lap_ok else 'FAIL'}",
                language="text",
            )
            with st.expander("📐 Show calculation steps", expanded=True):
                st.markdown("\n".join([
                    "**Lap Joint Minimum Overlap — CSA S16 Cl. 6.2.3**",
                    "- Formula: L_overlap ≥ max(5·t_thinner, 25 mm)",
                    f"- Substitute: max(5 × {min(t_thinner, t_thicker):.0f}, 25) = {L_lap_min:.0f} mm",
                    f"- Result: L = {L_lap:.0f} mm → **{'PASS' if lap_ok else 'FAIL'}**",
                ]))
    else:
        st.info(
            "Detailing checks shown for fillet welds only. "
            "For groove / flare welds, refer to Cl. 6.2.3 partial penetration groove depth table."
        )

# ── Diagrams column ───────────────────────────────────────────────────────────

with diag_col:
    st.markdown("#### Diagrams")

    if weld_type == "Fillet Weld" and segments:
        st.markdown("**Fillet Weld Cross-Section**")
        _svg_html(svg_fillet_cross_section(D, segments[0]["theta"]), height=280)

        st.markdown("")
        st.markdown("**Weld Group**")
        _svg_html(svg_weld_group(segments), height=320)

        st.markdown("")
        st.markdown("**Detailing Checks**")
        D_min_d = float(min_fillet_size(t_thicker))
        D_max_d = max_fillet_size(t_thinner)
        L_min_d = min_eff_length(D)
        L_det_d = segments[0]["L"] if segments else 100.0
        _svg_html(
            svg_detailing(D, D_min_d, D_max_d, L_det_d, L_min_d, t_thinner, t_thicker),
            height=260,
        )
    else:
        st.info(
            "Diagrams shown for fillet weld type. "
            "Select Fillet Weld to see cross-section and detailing visuals."
        )
