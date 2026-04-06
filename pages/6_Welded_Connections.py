from __future__ import annotations
import math
import streamlit as st
import streamlit.components.v1 as st_html

from _theme import apply_theme, render_sidebar_logo, render_footer

# ============================================================
# CONSTANTS
# ============================================================
PHI_W = 0.67   # weld resistance factor (Cl. 13.13.1)
PHI   = 0.90   # base metal yielding
PHI_U = 0.75   # base metal fracture

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
    if t_thicker <= 6:  return 3
    if t_thicker <= 12: return 5
    if t_thicker <= 20: return 6
    return 8

def max_fillet_size(t_thinner: float) -> float:
    return t_thinner if t_thinner < 6 else t_thinner - 2

def min_eff_length(D: float) -> float:
    return max(38.0, 4.0 * D)

def lap_min_overlap(t1: float, t2: float) -> float:
    return max(5 * min(t1, t2), 25.0)

# ============================================================
# CORE CALCULATIONS
# ============================================================
def effective_throat(D: float) -> float:
    return D / math.sqrt(2)

def fillet_Aw(D: float, L: float) -> float:
    return effective_throat(D) * L

def orientation_factor(theta_deg: float) -> float:
    t = math.radians(theta_deg)
    return 1.0 + 0.50 * (math.sin(t) ** 1.5)

def Mw_factor(theta1: float, theta2_nearest90: float) -> float:
    return (0.85 + theta1 / 600) / (0.85 + theta2_nearest90 / 600)

def vr_fillet_N(D: float, L: float, theta: float, Xu: float, Mw: float = 1.0) -> dict:
    throat = effective_throat(D)
    Aw     = fillet_Aw(D, L)
    of_    = orientation_factor(theta)
    Vr     = 0.67 * PHI_W * Aw * Xu * of_ * Mw
    return {
        "throat_mm": throat, "Aw_mm2": Aw, "theta": theta,
        "orient_factor": of_, "Mw": Mw, "Vr_N": Vr, "Vr_kN": Vr / 1000,
    }

def vr_base_metal_N(Am_mm2: float, Fu: float) -> float:
    return 0.67 * PHI_W * Am_mm2 * Fu

def vr_groove_N(Am_mm2: float, Aw_mm2: float, Fu: float, Xu: float) -> dict:
    Vr_base = 0.67 * PHI_W * Am_mm2 * Fu
    Vr_weld = 0.67 * PHI_W * Aw_mm2 * Xu
    gov = min(Vr_base, Vr_weld)
    return {
        "Vr_base_kN": Vr_base / 1000, "Vr_weld_kN": Vr_weld / 1000,
        "Vr_kN": gov / 1000, "governs": "base metal" if Vr_base <= Vr_weld else "weld metal",
    }

def tr_pjp_N(An_mm2: float, Fu: float, Ag_mm2: float, Fy: float) -> dict:
    Tr_weld = PHI_W * An_mm2 * Fu
    Tr_cap  = PHI   * Ag_mm2 * Fy
    Tr      = min(Tr_weld, Tr_cap)
    return {
        "Tr_weld_kN": Tr_weld / 1000, "Tr_cap_kN": Tr_cap / 1000,
        "Tr_kN": Tr / 1000, "governs": "weld" if Tr_weld <= Tr_cap else "base metal",
    }

def tr_pjp_combined_N(An_mm2: float, Aw_mm2: float, Fu: float, Xu: float,
                      Ag_mm2: float, Fy: float) -> dict:
    Tr_weld = PHI_W * math.sqrt((An_mm2 * Fu) ** 2 + (Aw_mm2 * Xu) ** 2)
    Tr_cap  = PHI   * Ag_mm2 * Fy
    Tr      = min(Tr_weld, Tr_cap)
    return {
        "Tr_weld_kN": Tr_weld / 1000, "Tr_cap_kN": Tr_cap / 1000,
        "Tr_kN": Tr / 1000, "governs": "weld" if Tr_weld <= Tr_cap else "base metal",
    }

def vr_flare_bevel_N(wf_mm: float, L_mm: float, Fu: float) -> dict:
    Aw = 0.50 * wf_mm * L_mm
    Vr = 0.67 * PHI_W * Aw * Fu
    return {"Aw_mm2": Aw, "Vr_kN": Vr / 1000}

# ============================================================
# SVG ENGINE — shared helpers
# ============================================================
_DEFS = (
    '<defs>'
    '<marker id="ah" markerWidth="7" markerHeight="6" refX="7" refY="3" orient="auto">'
    '<polygon points="0 0,7 3,0 6" fill="#22c55e"/></marker>'
    '<marker id="ah2" markerWidth="7" markerHeight="6" refX="0" refY="3" orient="auto">'
    '<polygon points="7 0,0 3,7 6" fill="#22c55e"/></marker>'
    '<marker id="bl" markerWidth="7" markerHeight="6" refX="7" refY="3" orient="auto">'
    '<polygon points="0 0,7 3,0 6" fill="#60a5fa"/></marker>'
    '<marker id="bl2" markerWidth="7" markerHeight="6" refX="0" refY="3" orient="auto">'
    '<polygon points="7 0,0 3,7 6" fill="#60a5fa"/></marker>'
    '<marker id="vio" markerWidth="7" markerHeight="6" refX="7" refY="3" orient="auto">'
    '<polygon points="0 0,7 3,0 6" fill="#a78bfa"/></marker>'
    '<marker id="vio2" markerWidth="7" markerHeight="6" refX="0" refY="3" orient="auto">'
    '<polygon points="7 0,0 3,7 6" fill="#a78bfa"/></marker>'
    '</defs>'
)

def _wrap(content: str, W: int = 460, H: int = 300) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'style="font-family:\'Courier New\',monospace;background:#0f172a;border-radius:10px;">'
        + _DEFS + content + '</svg>'
    )

def _dim_h(x1, x2, y, label, col="green"):
    """Horizontal dimension line."""
    mk = {"green": ("ah", "ah2", "#22c55e"), "blue": ("bl", "bl2", "#60a5fa"),
          "violet": ("vio", "vio2", "#a78bfa")}
    me, ms, c = mk.get(col, mk["green"])
    mx = (x1 + x2) / 2
    return (
        f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{c}" stroke-width="1.4" '
        f'marker-start="url(#{ms})" marker-end="url(#{me})"/>'
        f'<text x="{mx:.1f}" y="{y - 4}" fill="{c}" font-size="10" text-anchor="middle">{label}</text>'
    )

def _dim_v(x, y1, y2, label, col="green", side="right"):
    """Vertical dimension line."""
    mk = {"green": ("ah", "ah2", "#22c55e"), "blue": ("bl", "bl2", "#60a5fa"),
          "violet": ("vio", "vio2", "#a78bfa")}
    me, ms, c = mk.get(col, mk["green"])
    my = (y1 + y2) / 2
    tx = x + 4 if side == "right" else x - 4
    anc = "start" if side == "right" else "end"
    return (
        f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="{c}" stroke-width="1.4" '
        f'marker-start="url(#{ms})" marker-end="url(#{me})"/>'
        f'<text x="{tx}" y="{my + 4}" fill="{c}" font-size="10" text-anchor="{anc}">{label}</text>'
    )

def _svg_html(svg: str, height: int = 300) -> None:
    st_html.html(
        "<!DOCTYPE html><html><body style='margin:0;padding:0;background:transparent;'>"
        + svg + "</body></html>",
        height=height,
    )

# ============================================================
# SVG — FILLET WELD JOINT CROSS-SECTIONS
# ============================================================
def _weld_scale(t_thin: float, t_thick: float, D: float) -> float:
    """px per mm — normalize so the largest dimension ≈ 90px."""
    ref = max(t_thick, t_thin, D * 3, 1.0)
    return min(7.0, 90.0 / ref)

def svg_tee_joint(D: float, t_web: float, t_flange: float) -> str:
    W, H = 460, 300
    s = _weld_scale(t_web, t_flange, D)
    D_px    = max(10.0, D * s)
    tw_px   = max(8.0,  t_web * s)
    tf_px   = max(8.0,  t_flange * s)
    throat  = D / math.sqrt(2)
    cx      = W // 2
    fl_y    = H - 65          # top of flange
    fl_x0, fl_x1 = 30, W - 30
    web_y0  = 50
    wx0     = cx - tw_px / 2
    wx1     = cx + tw_px / 2

    # Fillet weld triangles
    lw = f"{wx0:.1f},{fl_y} {wx0-D_px:.1f},{fl_y} {wx0:.1f},{fl_y-D_px:.1f}"
    rw = f"{wx1:.1f},{fl_y} {wx1+D_px:.1f},{fl_y} {wx1:.1f},{fl_y-D_px:.1f}"
    # Throat dashed
    lt_x2 = wx0 - D_px * 0.5
    lt_y2 = fl_y - D_px * 0.5

    c = (
        f'<text x="{W//2}" y="22" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">T-Joint — Fillet Weld Cross-Section</text>'
        # Flange
        f'<rect x="{fl_x0}" y="{fl_y}" width="{fl_x1-fl_x0}" height="{tf_px:.1f}" '
        f'fill="#334155" stroke="#64748b" stroke-width="2"/>'
        # Web
        f'<rect x="{wx0:.1f}" y="{web_y0}" width="{tw_px:.1f}" height="{fl_y - web_y0}" '
        f'fill="#475569" stroke="#94a3b8" stroke-width="1.5"/>'
        # Welds
        f'<polygon points="{lw}" fill="#f59e0b" stroke="#fbbf24" stroke-width="1.2"/>'
        f'<polygon points="{rw}" fill="#f59e0b" stroke="#fbbf24" stroke-width="1.2"/>'
        # Throat dashed (left weld)
        f'<line x1="{wx0:.1f}" y1="{fl_y}" x2="{lt_x2:.1f}" y2="{lt_y2:.1f}" '
        f'stroke="#f97316" stroke-width="1.4" stroke-dasharray="4,2"/>'
        # Labels
        f'<text x="{fl_x0+10}" y="{fl_y + tf_px/2 + 5}" fill="#94a3b8" font-size="10">Flange</text>'
        f'<text x="{wx1+4}" y="{(web_y0+fl_y)//2+4}" fill="#94a3b8" font-size="10">Web</text>'
        f'<text x="{wx0-D_px/2:.1f}" y="{fl_y-D_px-6:.1f}" fill="#f59e0b" font-size="10" '
        f'text-anchor="middle">Fillet weld</text>'
        f'<text x="{lt_x2-8:.1f}" y="{lt_y2-8:.1f}" fill="#f97316" font-size="9">throat</text>'
        # Dimensions
        + _dim_h(wx0 - D_px, wx0, fl_y + tf_px + 20, f"D={D:.0f}mm", "green")
        + _dim_v(fl_x1 + 14, fl_y, fl_y + tf_px, f"t={t_flange:.0f}mm", "violet")
        + _dim_v(wx1 + 14, web_y0, fl_y, f"t={t_web:.0f}mm", "blue")
        + _dim_h(wx0, wx0 + tw_px, fl_y - D_px - 22, f"t_web={t_web:.0f}mm", "blue")
        + f'<text x="{lt_x2-32:.1f}" y="{lt_y2+14:.1f}" fill="#f97316" font-size="9">'
        f'={throat:.1f}mm</text>'
    )
    return _wrap(c, W, H)


def svg_lap_joint(D: float, t1: float, t2: float, L_lap: float) -> str:
    W, H = 460, 280
    s = _weld_scale(t1, t2, D)
    D_px  = max(10.0, D * s)
    t1_px = max(8.0,  t1 * s)
    t2_px = max(8.0,  t2 * s)
    L_px  = min(200.0, max(60.0, L_lap * s * 0.5))

    # Layout: plate 2 (bottom), plate 1 (top, overlapping)
    cx      = W // 2
    p2_y    = H - 60          # top of bottom plate (t2)
    p1_y    = p2_y - t1_px   # top of top plate
    p2_x0   = 40
    p2_x1   = W - 40
    p1_x0   = cx - L_px / 2  # top plate starts here
    p1_x1   = p2_x1          # shares right edge

    # Left fillet (top plate left edge on top of bottom plate)
    lw = (f"{p1_x0:.1f},{p2_y} {p1_x0-D_px:.1f},{p2_y} "
          f"{p1_x0:.1f},{p2_y-D_px:.1f}")
    # Right side: vertical (top plate right edge to top of bottom plate) — not commonly shown;
    # typically there's a weld at the LEFT free edge only for standard lap. Show both.
    rw = (f"{p1_x1:.1f},{p2_y} {p1_x1+D_px:.1f},{p2_y} "
          f"{p1_x1:.1f},{p2_y-D_px:.1f}")

    c = (
        f'<text x="{W//2}" y="22" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">Lap Joint — Fillet Weld Cross-Section</text>'
        # Bottom plate (t2)
        f'<rect x="{p2_x0}" y="{p2_y}" width="{p2_x1-p2_x0}" height="{t2_px:.1f}" '
        f'fill="#334155" stroke="#64748b" stroke-width="2"/>'
        # Top plate (t1) — overlaps right portion of bottom plate
        f'<rect x="{p1_x0:.1f}" y="{p1_y:.1f}" width="{p1_x1-p1_x0:.1f}" height="{t1_px:.1f}" '
        f'fill="#475569" stroke="#94a3b8" stroke-width="1.5"/>'
        # Fillet welds
        f'<polygon points="{lw}" fill="#f59e0b" stroke="#fbbf24" stroke-width="1.2"/>'
        f'<polygon points="{rw}" fill="#f59e0b" stroke="#fbbf24" stroke-width="1.2"/>'
        # Labels
        f'<text x="{(p2_x0+p1_x0)/2:.1f}" y="{p2_y+t2_px/2+4:.1f}" '
        f'fill="#94a3b8" font-size="10" text-anchor="middle">Plate 2</text>'
        f'<text x="{(p1_x0+p1_x1)/2:.1f}" y="{p1_y+t1_px/2+4:.1f}" '
        f'fill="#94a3b8" font-size="10" text-anchor="middle">Plate 1</text>'
        f'<text x="{p1_x0-D_px/2:.1f}" y="{p2_y-D_px-6:.1f}" fill="#f59e0b" font-size="10" '
        f'text-anchor="middle">Fillet weld</text>'
        # Lap overlap dimension
        + _dim_h(p1_x0, p1_x1, p2_y + t2_px + 22, f"L_lap={L_lap:.0f}mm", "green")
        + _dim_v(p2_x0 - 14, p2_y, p2_y + t2_px, f"t2={t2:.0f}mm", "blue", "left")
        + _dim_v(p1_x1 + 14, p1_y, p2_y, f"t1={t1:.0f}mm", "violet")
        + _dim_h(p1_x0 - D_px, p1_x0, p2_y + t2_px + 40, f"D={D:.0f}mm", "green")
    )
    return _wrap(c, W, H)


def svg_corner_joint(D: float, t1: float, t2: float) -> str:
    W, H = 460, 280
    s = _weld_scale(t1, t2, D)
    D_px  = max(10.0, D * s)
    t1_px = max(8.0, t1 * s)
    t2_px = max(8.0, t2 * s)

    cx = W // 2
    # Horizontal plate (t2) at bottom
    hp_y = H - 60
    hp_x0, hp_x1 = 80, W - 80
    # Vertical plate (t1) on right side, aligned with right edge of horizontal plate
    vp_x0 = hp_x1 - t1_px
    vp_x1 = hp_x1
    vp_y0  = 50
    vp_y1  = hp_y

    # Corner fillet at outer right corner (inside corner)
    # weld at inner corner: where vertical plate meets horizontal plate top
    iw = (f"{vp_x0:.1f},{hp_y} {vp_x0-D_px:.1f},{hp_y} "
          f"{vp_x0:.1f},{hp_y-D_px:.1f}")

    c = (
        f'<text x="{W//2}" y="22" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">Corner Joint — Fillet Weld Cross-Section</text>'
        # Horizontal plate
        f'<rect x="{hp_x0}" y="{hp_y}" width="{hp_x1-hp_x0}" height="{t2_px:.1f}" '
        f'fill="#334155" stroke="#64748b" stroke-width="2"/>'
        # Vertical plate
        f'<rect x="{vp_x0:.1f}" y="{vp_y0}" width="{t1_px:.1f}" height="{vp_y1-vp_y0}" '
        f'fill="#475569" stroke="#94a3b8" stroke-width="1.5"/>'
        # Inner fillet weld
        f'<polygon points="{iw}" fill="#f59e0b" stroke="#fbbf24" stroke-width="1.2"/>'
        # Outer corner (no weld shown — user can add note)
        f'<text x="{hp_x0+10}" y="{hp_y+t2_px/2+4:.1f}" fill="#94a3b8" font-size="10">Plate H</text>'
        f'<text x="{vp_x0-30:.1f}" y="{(vp_y0+hp_y)//2+4}" fill="#94a3b8" font-size="10">Plate V</text>'
        f'<text x="{vp_x0-D_px/2:.1f}" y="{hp_y-D_px-6:.1f}" fill="#f59e0b" font-size="10" '
        f'text-anchor="middle">Fillet</text>'
        + _dim_h(vp_x0 - D_px, vp_x0, hp_y + t2_px + 22, f"D={D:.0f}mm", "green")
        + _dim_v(hp_x1 + 14, hp_y, hp_y + t2_px, f"t2={t2:.0f}mm", "blue")
        + _dim_v(vp_x0 - 16, vp_y0, hp_y, f"t1={t1:.0f}mm", "violet", "left")
    )
    return _wrap(c, W, H)


# ============================================================
# SVG — THETA ORIENTATION DIAGRAM
# ============================================================
def svg_theta_diagram(segments: list[dict], theta2_idx: int) -> str:
    """
    Plan view of weld group showing load direction, weld axis for each
    segment, and theta_1 / theta_2 labels.
    """
    W, H = 460, 260
    SEG_COLORS = ["#f59e0b", "#22c55e", "#60a5fa", "#f97316", "#a78bfa", "#fb7185"]

    cx, cy = 160, 130   # plate center
    pw, ph = 180, 100   # plate size

    # Load arrow (comes from left, horizontal)
    c = (
        f'<text x="{W//2}" y="20" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">Weld Orientation — Plan View</text>'
        # Plate rectangle
        f'<rect x="{cx-pw//2}" y="{cy-ph//2}" width="{pw}" height="{ph}" '
        f'fill="#1e293b" stroke="#475569" stroke-width="2" rx="3"/>'
        # Load arrow
        f'<defs><marker id="ldarr" markerWidth="9" markerHeight="7" refX="9" refY="3.5" orient="auto">'
        f'<polygon points="0 0,9 3.5,0 7" fill="#f87171"/></marker></defs>'
        f'<line x1="{cx-pw//2-60}" y1="{cy}" x2="{cx-pw//2-4}" y2="{cy}" '
        f'stroke="#f87171" stroke-width="2.5" marker-end="url(#ldarr)"/>'
        f'<text x="{cx-pw//2-62}" y="{cy-8}" fill="#f87171" font-size="11" '
        f'font-weight="bold" text-anchor="middle">Vf</text>'
        f'<text x="{cx-pw//2-62}" y="{cy+18}" fill="#f87171" font-size="9" '
        f'text-anchor="middle">(load)</text>'
    )

    # Draw each weld segment on the plate
    for i, seg in enumerate(segments):
        col   = SEG_COLORS[i % len(SEG_COLORS)]
        theta = seg.get("theta", 0)
        L     = seg.get("L", 100)
        rad   = math.radians(theta)

        # Weld positioned along the plate edges
        # Distribute segments evenly along top/bottom edges
        offset = (i - (len(segments) - 1) / 2) * 25
        if theta == 90 or abs(theta - 90) < 5:
            # Transverse weld — draw on right face, vertical
            wx, wy = cx + pw // 2, cy + offset
            dx, dy = 0, ph // 2 - 5
        elif theta == 0 or theta < 15:
            # Longitudinal weld — draw along top
            wx, wy = cx + offset, cy - ph // 2
            dx, dy = L * 0.3, 0
            dx, dy = min(dx, pw // 2 - 5), 0
        else:
            # Inclined — draw along bottom with angle
            wx, wy = cx + offset, cy + ph // 2
            dx = math.cos(math.radians(90 - theta)) * 40
            dy = -math.sin(math.radians(90 - theta)) * 40

        lx1, ly1 = wx - dx, wy - dy
        lx2, ly2 = wx + dx, wy + dy

        # Angle arc (small arc near start of weld)
        arc_r = 20
        # Arc from 0 to theta (measured from horizontal load direction)
        arc_start_x = lx1 + arc_r
        arc_start_y = ly1
        arc_end_x   = lx1 + arc_r * math.cos(rad)
        arc_end_y   = ly1 - arc_r * math.sin(rad)
        large_flag  = 1 if theta > 180 else 0
        sweep       = 0  # counter-clockwise

        label = "theta_2 (governs Mw)" if i == theta2_idx and len(segments) > 1 else f"theta_1 = {theta:.0f} deg"
        label_short = f"theta={theta:.0f}d"

        c += (
            # Weld line (thick colored line)
            f'<line x1="{lx1:.1f}" y1="{ly1:.1f}" x2="{lx2:.1f}" y2="{ly2:.1f}" '
            f'stroke="{col}" stroke-width="5" stroke-linecap="round" opacity="0.9"/>'
            # Angle arc
            f'<path d="M {lx1+arc_r:.1f} {ly1:.1f} A {arc_r} {arc_r} 0 {large_flag} {sweep} '
            f'{arc_end_x:.1f} {arc_end_y:.1f}" stroke="{col}" fill="none" stroke-width="1.2" '
            f'stroke-dasharray="3,2"/>'
            # Angle label
            f'<text x="{lx1+arc_r+6:.1f}" y="{ly1-arc_r/2:.1f}" fill="{col}" font-size="10">'
            f'{label_short}</text>'
        )

    # Legend on the right
    leg_x = cx + pw // 2 + 20
    c += f'<text x="{leg_x}" y="40" fill="#e2e8f0" font-size="10" font-weight="bold">Legend</text>'
    for i, seg in enumerate(segments):
        col   = SEG_COLORS[i % len(SEG_COLORS)]
        ly_   = 55 + i * 20
        star  = "  [theta_2]" if i == theta2_idx and len(segments) > 1 else ""
        c += (
            f'<rect x="{leg_x}" y="{ly_-8}" width="14" height="10" fill="{col}"/>'
            f'<text x="{leg_x+18}" y="{ly_}" fill="{col}" font-size="10">'
            f'Seg {i+1}: theta={seg["theta"]:.0f} deg  L={seg["L"]:.0f}mm{star}</text>'
        )

    if len(segments) > 1:
        c += (
            f'<text x="{leg_x}" y="{55 + len(segments)*20 + 16}" fill="#94a3b8" font-size="9">'
            f'theta_2 auto-identified</text>'
            f'<text x="{leg_x}" y="{55 + len(segments)*20 + 28}" fill="#94a3b8" font-size="9">'
            f'as segment nearest 90 deg</text>'
        )

    return _wrap(c, W, H)


# ============================================================
# SVG — CJP GROOVE WELD (Single-V)
# ============================================================
def svg_cjp_butt(t1: float, t2: float) -> str:
    W, H = 460, 300
    ref   = max(t1, t2, 1.0)
    s     = min(6.0, 100.0 / ref)
    t1_px = max(12.0, t1 * s)
    t2_px = max(12.0, t2 * s)
    p_h   = min(120.0, max(60.0, (t1_px + t2_px) / 2))

    cx = W // 2
    py = (H - p_h) // 2   # top of plate

    # groove angle ≈ 60 degrees total opening (30 deg each side from vertical)
    groove_half = 30  # degrees
    g_rad = math.radians(groove_half)
    g_offset = p_h * math.tan(g_rad) * 0.5  # horizontal offset at top of groove

    # Left plate (t1)
    lp_x0 = cx - 120
    lp_x1 = cx - 4
    # Right plate (t2)
    rp_x0 = cx + 4
    rp_x1 = cx + 120

    # Groove: V shape filled with weld
    # Left plate right face: angled at +30 deg (opens left)
    # Right plate left face: angled at -30 deg (opens right)
    # Weld fills the V
    weld_pts = (
        f"{cx:.1f},{py+p_h} "
        f"{lp_x1-g_offset:.1f},{py} "
        f"{rp_x0+g_offset:.1f},{py}"
    )
    weld_pts_r = weld_pts  # same points for the closed polygon
    weld_poly = (
        f"{cx:.1f},{py+p_h} "
        f"{lp_x1-g_offset:.1f},{py} "
        f"{rp_x0+g_offset:.1f},{py} "
        f"{cx:.1f},{py+p_h}"
    )

    # Reinforcement bead at top
    ry = py - 6
    rx_l = lp_x1 - g_offset - 8
    rx_r = rp_x0 + g_offset + 8

    c = (
        f'<text x="{W//2}" y="22" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">CJP Groove Weld — Single-V Butt Joint</text>'
        f'<text x="{W//2}" y="38" fill="#60a5fa" font-size="10" text-anchor="middle">'
        f'Complete Joint Penetration — Full Strength Restored</text>'
        # Left plate
        f'<rect x="{lp_x0}" y="{py}" width="{lp_x1-lp_x0-g_offset:.1f}" height="{p_h:.1f}" '
        f'fill="#334155" stroke="#64748b" stroke-width="2"/>'
        # Bevel on left plate right edge (angled face)
        f'<polygon points="{lp_x1-g_offset:.1f},{py} {lp_x1:.1f},{py+p_h} {lp_x1:.1f},{py}" '
        f'fill="#1e293b" stroke="none"/>'
        # Right plate
        f'<rect x="{rp_x0+g_offset:.1f}" y="{py}" width="{rp_x1-rp_x0-g_offset:.1f}" height="{p_h:.1f}" '
        f'fill="#334155" stroke="#64748b" stroke-width="2"/>'
        # Bevel on right plate left edge
        f'<polygon points="{rp_x0+g_offset:.1f},{py} {rp_x0:.1f},{py+p_h} {rp_x0:.1f},{py}" '
        f'fill="#1e293b" stroke="none"/>'
        # Weld fill (amber)
        f'<polygon points="{weld_poly}" fill="#f59e0b" opacity="0.85" stroke="#fbbf24" stroke-width="1"/>'
        # Weld reinforcement bead
        f'<ellipse cx="{cx:.1f}" cy="{ry:.1f}" rx="{(rx_r-rx_l)/2:.1f}" ry="6" '
        f'fill="#f59e0b" opacity="0.7"/>'
        # Root symbol (small dot at root)
        f'<circle cx="{cx:.1f}" cy="{py+p_h:.1f}" r="4" fill="#fbbf24"/>'
        # Groove angle label
        f'<line x1="{lp_x1-g_offset:.1f}" y1="{py}" x2="{lp_x1-g_offset-20:.1f}" y2="{py-20}" '
        f'stroke="#94a3b8" stroke-width="1" stroke-dasharray="3,2"/>'
        f'<text x="{lp_x1-g_offset-22:.1f}" y="{py-22}" fill="#94a3b8" font-size="9" '
        f'text-anchor="end">60 deg groove</text>'
        # Labels
        f'<text x="{(lp_x0+lp_x1)/2:.1f}" y="{py+p_h/2+4:.1f}" fill="#94a3b8" '
        f'font-size="10" text-anchor="middle">Plate 1</text>'
        f'<text x="{(rp_x0+rp_x1)/2+g_offset/2:.1f}" y="{py+p_h/2+4:.1f}" fill="#94a3b8" '
        f'font-size="10" text-anchor="middle">Plate 2</text>'
        f'<text x="{cx:.1f}" y="{py+p_h/2+4:.1f}" fill="#fbbf24" '
        f'font-size="10" text-anchor="middle">Weld</text>'
        f'<text x="{cx:.1f}" y="{ry-10}" fill="#f59e0b" font-size="9" '
        f'text-anchor="middle">Reinforcement</text>'
        f'<text x="{cx+8:.1f}" y="{py+p_h+14:.1f}" fill="#fbbf24" font-size="9">Root</text>'
        # Dimension lines
        + _dim_v(lp_x0 - 14, py, py + p_h, f"t1={t1:.0f}mm", "blue", "left")
        + _dim_v(rp_x1 + 14, py, py + p_h, f"t2={t2:.0f}mm", "violet")
        # Am label
        + f'<text x="{W//2}" y="{H-14}" fill="#22c55e" font-size="10" text-anchor="middle">'
        f'Am = fusion face area = t1 x L  (or t2 x L if t2 &lt; t1)</text>'
    )
    return _wrap(c, W, H)


# ============================================================
# SVG — PJP GROOVE WELD (Single-V)
# ============================================================
def svg_pjp_butt(t1: float, t2: float) -> str:
    W, H = 460, 300
    ref   = max(t1, t2, 1.0)
    s     = min(6.0, 100.0 / ref)
    t1_px = max(12.0, t1 * s)
    t2_px = max(12.0, t2 * s)
    p_h   = min(120.0, max(60.0, (t1_px + t2_px) / 2))
    eff_frac = 0.60   # effective penetration depth as fraction of plate thickness

    cx = W // 2
    py = (H - p_h) // 2

    g_rad    = math.radians(30)  # half groove angle
    g_off_top = p_h * 0.35 * math.tan(g_rad)  # offset at top of weld (partial depth)
    weld_h   = p_h * eff_frac   # weld only penetrates partway

    weld_py_bot = py + p_h           # bottom of plate
    weld_py_top = weld_py_bot - weld_h  # top of weld

    lp_x0 = cx - 120
    lp_x1 = cx - 4
    rp_x0 = cx + 4
    rp_x1 = cx + 120

    g_off_top2 = g_off_top * 0.7  # partial — narrower opening at top

    weld_poly = (
        f"{cx:.1f},{weld_py_bot} "
        f"{lp_x1-g_off_top2:.1f},{weld_py_top} "
        f"{rp_x0+g_off_top2:.1f},{weld_py_top}"
    )

    c = (
        f'<text x="{W//2}" y="22" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">PJP Groove Weld — Single-V Butt Joint</text>'
        f'<text x="{W//2}" y="38" fill="#f97316" font-size="10" text-anchor="middle">'
        f'Partial Joint Penetration — Effective Throat (a) governs</text>'
        # Left plate
        f'<rect x="{lp_x0}" y="{py}" width="{lp_x1-lp_x0:.1f}" height="{p_h:.1f}" '
        f'fill="#334155" stroke="#64748b" stroke-width="2"/>'
        # Right plate
        f'<rect x="{rp_x0}" y="{py}" width="{rp_x1-rp_x0:.1f}" height="{p_h:.1f}" '
        f'fill="#334155" stroke="#64748b" stroke-width="2"/>'
        # Gap between plates (unfilled root)
        f'<rect x="{lp_x1:.1f}" y="{py}" width="{rp_x0-lp_x1:.1f}" height="{p_h:.1f}" '
        f'fill="#0f172a"/>'
        # Unpenetrated root (darker region at bottom)
        f'<rect x="{lp_x1:.1f}" y="{weld_py_top:.1f}" width="{rp_x0-lp_x1:.1f}" '
        f'height="{weld_h:.1f}" fill="#1e293b" stroke="#475569" stroke-dasharray="3,2"/>'
        # Weld fill (partial — amber)
        f'<polygon points="{weld_poly}" fill="#f59e0b" opacity="0.85" stroke="#fbbf24" stroke-width="1"/>'
        # Effective throat line (dashed)
        f'<line x1="{lp_x1:.1f}" y1="{weld_py_top:.1f}" x2="{rp_x0:.1f}" y2="{weld_py_top:.1f}" '
        f'stroke="#f97316" stroke-width="1.5" stroke-dasharray="5,3"/>'
        f'<text x="{rp_x0+6}" y="{weld_py_top+4:.1f}" fill="#f97316" font-size="9">'
        f'effective throat (a = Aw/L)</text>'
        # Unpenetrated depth indicator
        f'<line x1="{rp_x0+6}" y1="{weld_py_top:.1f}" x2="{rp_x0+6}" y2="{py+p_h:.1f}" '
        f'stroke="#475569" stroke-width="1" stroke-dasharray="2,2"/>'
        f'<text x="{rp_x0+10}" y="{(weld_py_top+py+p_h)/2+4:.1f}" fill="#475569" font-size="9">'
        f'unfused root</text>'
        # Labels
        f'<text x="{(lp_x0+lp_x1)/2:.1f}" y="{py+p_h/2+4:.1f}" fill="#94a3b8" '
        f'font-size="10" text-anchor="middle">Plate 1</text>'
        f'<text x="{(rp_x0+rp_x1)/2:.1f}" y="{py+p_h/2+4:.1f}" fill="#94a3b8" '
        f'font-size="10" text-anchor="middle">Plate 2</text>'
        f'<text x="{cx:.1f}" y="{(weld_py_top+weld_py_bot)/2+4:.1f}" fill="#fbbf24" '
        f'font-size="9" text-anchor="middle">Weld metal</text>'
        + _dim_v(lp_x0 - 14, py, py + p_h, f"t1={t1:.0f}mm", "blue", "left")
        + _dim_v(rp_x1 + 14, py, py + p_h, f"t2={t2:.0f}mm", "violet")
        + _dim_v(cx + 40, weld_py_top, weld_py_bot, f"weld={weld_h:.0f}px", "green")
        # An / Am notes
        + f'<text x="{W//2}" y="{H-18}" fill="#22c55e" font-size="9" text-anchor="middle">'
        f'An = fusion face area (governs tension)   |   Am = shear area</text>'
        + f'<text x="{W//2}" y="{H-6}" fill="#f97316" font-size="9" text-anchor="middle">'
        f'Aw (throat area) = effective throat x L</text>'
    )
    return _wrap(c, W, H)


# ============================================================
# SVG — FLARE BEVEL CROSS-SECTION
# ============================================================
def svg_flare_bevel_xsec(wf: float) -> str:
    W, H = 460, 280
    cx = W // 2
    # Round bar on the right (radius r)
    r = min(80, max(30, wf * 3))
    bar_cx = cx + 80
    bar_cy = H // 2
    # Flat plate on the left
    fp_x0, fp_x1 = 30, bar_cx - r + 2
    fp_y0, fp_y1 = bar_cy - 20, bar_cy + 20
    # Flare groove: the gap between flat plate and round bar
    # Weld fills from flat plate face to tangent point on bar
    tang_y_top = bar_cy - r * 0.7
    tang_y_bot = bar_cy + r * 0.7
    wf_px = min(50, max(15, wf * 3))

    c = (
        f'<text x="{W//2}" y="20" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">Flare Bevel Groove — Cross-Section</text>'
        # Flat plate
        f'<rect x="{fp_x0}" y="{fp_y0}" width="{fp_x1-fp_x0:.1f}" height="{fp_y1-fp_y0}" '
        f'fill="#334155" stroke="#64748b" stroke-width="2"/>'
        # Round bar
        f'<circle cx="{bar_cx}" cy="{bar_cy}" r="{r:.1f}" '
        f'fill="#475569" stroke="#94a3b8" stroke-width="2"/>'
        # Weld fill (flare bevel groove)
        f'<path d="M {fp_x1:.1f} {tang_y_top:.1f} '
        f'Q {bar_cx-r-10:.1f} {bar_cy:.1f} {fp_x1:.1f} {tang_y_bot:.1f}" '
        f'fill="#f59e0b" opacity="0.8" stroke="#fbbf24" stroke-width="1"/>'
        # wf dimension (width of groove face)
        f'<line x1="{fp_x1:.1f}" y1="{tang_y_top:.1f}" x2="{fp_x1:.1f}" y2="{tang_y_bot:.1f}" '
        f'stroke="#22c55e" stroke-width="1.5" stroke-dasharray="3,2"/>'
        + _dim_v(fp_x1 + 14, tang_y_top, tang_y_bot, f"wf={wf:.0f}mm", "green")
        # Labels
        + f'<text x="{(fp_x0+fp_x1)/2:.1f}" y="{bar_cy+4}" fill="#94a3b8" font-size="10" '
        f'text-anchor="middle">Flat plate</text>'
        f'<text x="{bar_cx:.1f}" y="{bar_cy+4}" fill="#94a3b8" font-size="10" '
        f'text-anchor="middle">Round bar</text>'
        f'<text x="{fp_x1-20:.1f}" y="{bar_cy+4}" fill="#fbbf24" font-size="10" '
        f'text-anchor="middle">Weld</text>'
        f'<text x="{W//2}" y="{H-10}" fill="#22c55e" font-size="10" text-anchor="middle">'
        f'Aw = 0.50 x wf x L</text>'
    )
    return _wrap(c, W, H)


# ============================================================
# SVG — DETAILING CHECKS (bar chart)
# ============================================================
def svg_detailing(D: float, D_min: float, D_max: float,
                  L: float, L_min: float,
                  t_thinner: float, t_thicker: float) -> str:
    W, H = 460, 200
    checks = [
        ("Min weld size", D_min, D,    ">="),
        ("Max weld size", D,     D_max, "<="),
        ("Min eff. length", L_min, L,  ">="),
    ]
    bar_x0, bar_w = 180, 240
    c = (
        f'<text x="{W//2}" y="20" fill="#e2e8f0" font-size="12" font-weight="bold" '
        f'text-anchor="middle">Detailing Checks  (Cl. 6.2.3)</text>'
    )
    for i, (label, limit, actual, op) in enumerate(checks):
        y  = 42 + i * 52
        ok = actual >= limit if op == ">=" else actual <= limit
        fill_ratio = min(actual / max(limit, 0.001), 1.5) if op == ">=" else min(actual / max(limit, 0.001), 1.0)
        col  = "#22c55e" if ok else "#ef4444"
        icon = "PASS" if ok else "FAIL"
        bar_fill = min(fill_ratio * bar_w, bar_w * 1.3)
        ref_x = bar_x0 + bar_w * min(1.0, limit / max(actual, 0.001))
        c += (
            f'<text x="10" y="{y+12}" fill="#e2e8f0" font-size="11" font-weight="bold">{label}</text>'
            f'<text x="10" y="{y+25}" fill="#94a3b8" font-size="9">'
            f'limit={limit:.1f}mm  actual={actual:.1f}mm  {op}</text>'
            f'<rect x="{bar_x0}" y="{y}" width="{bar_w}" height="18" fill="#1e293b" rx="3"/>'
            f'<rect x="{bar_x0}" y="{y}" width="{bar_fill:.0f}" height="18" '
            f'fill="{col}" opacity="0.7" rx="3"/>'
            f'<line x1="{ref_x:.0f}" y1="{y-3}" x2="{ref_x:.0f}" y2="{y+21}" '
            f'stroke="white" stroke-width="2" stroke-dasharray="3,2"/>'
            f'<text x="{bar_x0+bar_w+8}" y="{y+13}" fill="{col}" font-size="11" '
            f'font-weight="bold">{icon}</text>'
        )
    return _wrap(c, W, H)


# ============================================================
# STREAMLIT UI
# ============================================================
apply_theme()
render_sidebar_logo()
render_footer()

st.title("CSA S16 — Welded Connection Solver")
st.caption(
    "Cl. 13.13  |  Fillet, CJP/PJP Groove, Flare Bevel  |  "
    "phi_w = 0.67  |  Detailing per Cl. 6.2.3"
)
st.markdown("---")

# ── Weld type (top row, full width) ──────────────────────────────────────────
weld_type = st.selectbox(
    "Weld type",
    [
        "Fillet Weld",
        "Complete Joint Penetration (CJP) Groove",
        "Partial Joint Penetration (PJP) Groove",
        "Flare Bevel Groove",
    ],
    key="weld_type",
)

# Fillet sub-selector
joint_config = "T-joint (web-to-flange)"
if weld_type == "Fillet Weld":
    joint_config = st.selectbox(
        "Joint configuration",
        ["T-joint (web-to-flange)", "Lap Joint", "Corner Joint"],
        key="joint_cfg",
    )

st.markdown("---")

# ── Two-column layout: inputs (left) | cross-section diagram (right) ─────────
inp_col, dia_col = st.columns([3, 3], gap="large")

# ── Safe defaults (overwritten by widgets below) ─────────────────────────────
D:             float = 8.0
t_thinner:     float = 10.0
t_thicker:     float = 12.0
L_lap:         float = 0.0
segments:      list  = []
check_base:    bool  = False
Am_mm2:        float = 0.0
Am_mm2_groove: float = 0.0
Aw_mm2:        float = 0.0
An_mm2:        float = 0.0
Ag_mm2:        float = 0.0
has_fillet:    bool  = False
Aw_fillet_mm2: float = 0.0
wf_mm:         float = 20.0
L_fb:          float = 150.0
Fy:            float = 350.0
Fu:            float = 450.0
Xu:            float = 490.0
is_lap:        bool  = False

with inp_col:

    # ── Material ──────────────────────────────────────────────────────────────
    st.markdown("#### Material")
    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        grade_label = st.selectbox(
            "Steel grade (G40.21)",
            [f"G40.21-{g}" for g in STEEL_GRADES],
            index=2, key="steel_grade",
        )
        grade_val                          = int(grade_label.split("-")[1])
        Fy_def, Fu_def, Xu_def             = STEEL_GRADES[grade_val]
    with mc2:
        Fy = st.number_input("Fy (MPa)", min_value=200.0, value=float(Fy_def), step=5.0,  key="Fy")
        Fu = st.number_input("Fu (MPa)", min_value=200.0, value=float(Fu_def), step=5.0,  key="Fu")
    with mc3:
        Xu = st.number_input(
            f"Electrode Xu (MPa)  [match={Xu_def}]",
            min_value=300.0, value=float(Xu_def), step=10.0, key="Xu",
        )
        st.caption("Xu = 10 x first two digits of electrode class (CSA W48)")

    st.markdown("---")

    # ── Plate Geometry (all types) ────────────────────────────────────────────
    st.markdown("#### Plate Geometry")
    pg1, pg2 = st.columns(2)
    with pg1:
        t_thinner = st.number_input(
            "t_thinner (mm) — thinner plate", min_value=1.0, value=10.0, step=1.0, key="t_thin"
        )
        t_thicker = st.number_input(
            "t_thicker (mm) — thicker plate", min_value=1.0, value=12.0, step=1.0, key="t_thick"
        )
    with pg2:
        if weld_type == "Fillet Weld":
            is_lap = joint_config == "Lap Joint"
            if is_lap:
                L_lap = st.number_input(
                    "Lap overlap L_lap (mm)", min_value=10.0, value=80.0, step=5.0, key="L_lap"
                )

    # ── Weld Geometry ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Weld Geometry")

    if weld_type == "Fillet Weld":
        wg1, wg2 = st.columns(2)
        with wg1:
            D = st.number_input(
                "Weld leg size D (mm)", min_value=3.0, value=8.0, step=1.0, key="D"
            )
        with wg2:
            check_base = st.checkbox("Check base metal (Cl. 13.13.2.2)?", key="chk_base")
            if check_base:
                Am_mm2 = st.number_input(
                    "Am — fusion face shear area (mm2)", min_value=0.0, value=1000.0,
                    step=50.0, key="Am_fillet"
                )

        # ── Weld Segments (fillet) ────────────────────────────────────────────
        st.markdown("---")

        # Theta_1 / Theta_2 explanation
        with st.expander("Understanding theta_1 and theta_2  (Cl. 13.13.2.2)", expanded=True):
            st.markdown(
                r"""
**theta_1** is the angle between the weld axis and the line of action of the applied force for the segment being checked.

**theta_2** is the angle of the weld segment in the group that is **nearest to 90°** (most transverse). It is **automatically identified** — you do not enter it separately.

The multi-orientation factor is:

$$M_w = \frac{0.85 + \theta_1/600}{0.85 + \theta_2/600}$$

- For a **single-segment** group: theta_1 = theta_2, so **Mw = 1.0** always.
- For a **multi-segment** group: the segment nearest to 90° is identified as theta_2; all others use that as the denominator.
- **Longitudinal weld** (parallel to load): theta = 0°, orientation factor = 1.00
- **Transverse weld** (perpendicular to load): theta = 90°, orientation factor = 1.50

The orientation diagram (right panel) highlights which segment is theta_2.
                """
            )

        st.markdown("**Weld Segments**")
        st.caption(
            "Enter the length L and orientation theta for each weld segment. "
            "theta = 0° = longitudinal (parallel to load). theta = 90° = transverse."
        )

        n_segs = int(st.number_input(
            "Number of segments", min_value=1, max_value=6, value=1, step=1, key="n_segs"
        ))

        seg_cols = st.columns(min(n_segs, 3))
        for i in range(n_segs):
            ctx = seg_cols[i % 3] if n_segs <= 3 else st.container()
            with ctx:
                st.markdown(f"**Seg {i+1}**")
                L_i = st.number_input(
                    f"L_{i+1} (mm)", min_value=1.0, value=100.0, step=5.0, key=f"L_{i}"
                )
                th_i = st.number_input(
                    f"theta_{i+1} (deg)",
                    min_value=0.0, max_value=90.0,
                    value=90.0 if i == 0 else 0.0,
                    step=5.0, key=f"theta_{i}",
                )
                segments.append({"L": L_i, "theta": th_i})

    elif weld_type in ("Complete Joint Penetration (CJP) Groove",
                       "Partial Joint Penetration (PJP) Groove"):
        gg1, gg2 = st.columns(2)
        with gg1:
            Am_mm2_groove = st.number_input(
                "Am — fusion face shear area (mm2)", min_value=0.0, value=2000.0,
                step=50.0, key="Am_groove"
            )
            Aw_mm2 = st.number_input(
                "Aw — effective weld throat area (mm2)", min_value=0.0, value=2000.0,
                step=50.0, key="Aw_groove"
            )
        with gg2:
            if "Partial" in weld_type:
                An_mm2 = st.number_input(
                    "An — nominal fusion face area (mm2)", min_value=0.0, value=2000.0,
                    step=50.0, key="An"
                )
                Ag_mm2 = st.number_input(
                    "Ag — gross tension member area (mm2)", min_value=0.0, value=3000.0,
                    step=50.0, key="Ag"
                )
                has_fillet = st.checkbox(
                    "Combined with fillet weld? (Cl. 13.13.3.3)", key="has_fillet"
                )
                if has_fillet:
                    Aw_fillet_mm2 = st.number_input(
                        "Aw_fillet — fillet throat area (mm2)", min_value=0.0,
                        value=500.0, step=50.0, key="Aw_fillet"
                    )

    elif weld_type == "Flare Bevel Groove":
        fb1, _ = st.columns(2)
        with fb1:
            wf_mm = st.number_input(
                "wf — groove face width (mm)", min_value=1.0, value=20.0, step=1.0, key="wf"
            )
            L_fb = st.number_input(
                "L — weld length (mm)", min_value=1.0, value=150.0, step=5.0, key="L_fb"
            )

# ── Right column: diagrams (update with inputs) ───────────────────────────────
with dia_col:
    st.markdown("#### Connection Diagram")

    if weld_type == "Fillet Weld":
        if joint_config == "T-joint (web-to-flange)":
            _svg_html(svg_tee_joint(D, t_thinner, t_thicker), 300)
        elif joint_config == "Lap Joint":
            _svg_html(svg_lap_joint(D, t_thinner, t_thicker, L_lap if L_lap > 0 else 80.0), 280)
        else:  # Corner
            _svg_html(svg_corner_joint(D, t_thinner, t_thicker), 280)

        if segments:
            st.markdown("##### Weld Orientation Plan View")
            theta2_idx = max(range(len(segments)), key=lambda i: segments[i]["theta"])
            _svg_html(svg_theta_diagram(segments, theta2_idx), 270)

    elif "CJP" in weld_type:
        _svg_html(svg_cjp_butt(t_thinner, t_thicker), 300)
        st.info(
            "CJP groove welds with matching electrodes restore full base metal strength. "
            "Am = fusion face area (shear); full Tr from base metal (Cl. 13.13.3.1)."
        )

    elif "PJP" in weld_type:
        _svg_html(svg_pjp_butt(t_thinner, t_thicker), 300)
        st.info(
            "PJP groove welds do not fully restore strength. "
            "Effective throat area Aw governs shear. "
            "Nominal fusion face area An governs tension (Cl. 13.13.3.2)."
        )

    elif weld_type == "Flare Bevel Groove":
        _svg_html(svg_flare_bevel_xsec(wf_mm), 280)
        st.info("Aw = 0.50 x wf x L  (Cl. 13.13.2.3)")

# ── STEP-BY-STEP CALCULATIONS ─────────────────────────────────────────────────
st.markdown("---")
st.subheader("Step-by-Step Calculations")

calc_col, summ_col = st.columns([3, 1], gap="large")

with calc_col:

    # ══════════════════════════════════════════════════════════════════════════
    # FILLET WELD
    # ══════════════════════════════════════════════════════════════════════════
    if weld_type == "Fillet Weld" and segments:
        throat = effective_throat(D)

        # ── Step 1: Effective Throat & Area ──────────────────────────────────
        st.markdown("##### Step 1 — Effective Throat & Weld Area  *(Cl. 13.13.2.2)*")
        st.latex(r"a_w = \frac{D}{\sqrt{2}} \qquad A_{w,i} = a_w \times L_i")
        lines = [f"  Throat  aw = {D:.1f} / sqrt(2) = {throat:.3f} mm", ""]
        for i, s in enumerate(segments):
            lines.append(f"  Seg {i+1}: Aw = {throat:.3f} x {s['L']:.0f} = {fillet_Aw(D, s['L']):.2f} mm2")
        st.code("\n".join(lines), language="text")

        # ── Step 2: Orientation Factor ────────────────────────────────────────
        st.markdown("##### Step 2 — Orientation Factor  *(Cl. 13.13.2.2)*")
        st.latex(r"(1 + 0.50 \sin^{1.5}\!\theta)")
        st.markdown(
            "- theta = 0° (longitudinal): factor = **1.00**  \n"
            "- theta = 90° (transverse): factor = **1.50**"
        )
        for i, s in enumerate(segments):
            of_ = orientation_factor(s["theta"])
            sin_t = math.sin(math.radians(s["theta"]))
            st.code(
                f"  Seg {i+1}:  theta = {s['theta']:.0f} deg\n"
                f"          sin(theta) = {sin_t:.4f}   sin^1.5 = {sin_t**1.5:.4f}\n"
                f"          Factor = 1.00 + 0.50 x {sin_t**1.5:.4f} = {of_:.4f}",
                language="text",
            )

        # ── Step 3: Multi-Orientation Factor Mw ──────────────────────────────
        st.markdown("##### Step 3 — Multi-Orientation Factor Mw  *(Cl. 13.13.2.2)*")
        st.latex(r"M_w = \frac{0.85 + \theta_1/600}{0.85 + \theta_2/600}")

        theta_max = max(s["theta"] for s in segments)
        theta2_idx = max(range(len(segments)), key=lambda i: segments[i]["theta"])

        if len(segments) == 1:
            mw_values = [1.0]
            st.code(
                f"  Single segment: theta_1 = theta_2 = {segments[0]['theta']:.0f} deg\n"
                f"  => Mw = 1.0 (no multi-orientation reduction)",
                language="text",
            )
        else:
            mw_values = []
            st.code(
                f"  theta_2 = Seg {theta2_idx+1}  (theta = {theta_max:.0f} deg — nearest to 90 deg)",
                language="text",
            )
            for i, s in enumerate(segments):
                Mw_i  = Mw_factor(s["theta"], theta_max)
                mw_values.append(Mw_i)
                num   = 0.85 + s["theta"] / 600
                denom = 0.85 + theta_max  / 600
                note  = "  [theta_2 segment]" if i == theta2_idx else ""
                st.code(
                    f"  Seg {i+1}:  theta_1 = {s['theta']:.0f} deg   theta_2 = {theta_max:.0f} deg{note}\n"
                    f"          Mw = (0.85 + {s['theta']:.0f}/600) / (0.85 + {theta_max:.0f}/600)\n"
                    f"             = {num:.5f} / {denom:.5f} = {Mw_i:.4f}",
                    language="text",
                )

        # ── Step 4: Factored Shear Resistance Vr ─────────────────────────────
        st.markdown("##### Step 4 — Factored Shear Resistance Vr  *(Cl. 13.13.2.2)*")
        st.latex(r"V_r = 0.67\,\phi_w\,A_w\,X_u\,(1 + 0.50\sin^{1.5}\!\theta)\,M_w")
        st.markdown(
            f"- phi_w = {PHI_W}  |  Xu = {Xu:.0f} MPa  |  "
            "Aw = throat x L  |  theta = angle to load  |  Mw = multi-orient. factor"
        )

        total_Vr_kN = 0.0
        for i, s in enumerate(segments):
            Mw_i = mw_values[i]
            res  = vr_fillet_N(D, s["L"], s["theta"], Xu, Mw_i)
            total_Vr_kN += res["Vr_kN"]
            st.code(
                f"  Seg {i+1}: theta={s['theta']:.0f} deg  L={s['L']:.0f}mm  D={D:.0f}mm\n"
                f"\n"
                f"  Throat: aw  = {D:.1f} / sqrt(2)          = {res['throat_mm']:.3f} mm\n"
                f"  Area:   Aw  = {res['throat_mm']:.3f} x {s['L']:.0f}    = {res['Aw_mm2']:.2f} mm2\n"
                f"\n"
                f"  Orient. factor = 1.00 + 0.50 x sin^1.5({s['theta']:.0f} deg)\n"
                f"                 = {res['orient_factor']:.4f}\n"
                f"\n"
                f"  Mw             = {Mw_i:.4f}\n"
                f"\n"
                f"  Vr = 0.67 x {PHI_W} x {res['Aw_mm2']:.2f} x {Xu:.0f}"
                f" x {res['orient_factor']:.4f} x {Mw_i:.4f}\n"
                f"     = {res['Vr_kN']:.2f} kN",
                language="text",
            )

        st.markdown(f"**Total Vr (all segments) = {total_Vr_kN:.2f} kN**")

        # ── Step 5: Base metal check ──────────────────────────────────────────
        gov_Vr = total_Vr_kN
        if check_base and Am_mm2 > 0:
            st.markdown("##### Step 5 — Base Metal Check  *(Cl. 13.13.2.2)*")
            st.latex(r"V_r^{bm} = 0.67\,\phi_w\,A_m\,F_u")
            Vr_bm = vr_base_metal_N(Am_mm2, Fu) / 1000
            st.code(
                f"  Vr_bm = 0.67 x {PHI_W} x {Am_mm2:.0f} x {Fu:.0f}\n"
                f"        = {Vr_bm:.2f} kN",
                language="text",
            )
            gov_Vr = min(total_Vr_kN, Vr_bm)
            if Vr_bm < total_Vr_kN:
                st.warning(f"Base metal governs: Vr = {Vr_bm:.2f} kN (weld = {total_Vr_kN:.2f} kN)")
            else:
                st.success(f"Weld governs: Vr = {total_Vr_kN:.2f} kN (base metal = {Vr_bm:.2f} kN)")

        # ── Step 6: Detailing ─────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("##### Step 6 — Detailing Checks  *(Cl. 6.2.3)*")
        st.latex(
            r"D \geq D_{min}\ \text{(Table)} \qquad "
            r"D \leq D_{max} = t_{thin}-2 \qquad "
            r"L_{eff} \geq \max(38,\,4D)"
        )
        D_min = float(min_fillet_size(t_thicker))
        D_max = max_fillet_size(t_thinner)
        L_det = segments[0]["L"]
        L_min = min_eff_length(D)

        st.code(
            f"  t_thicker = {t_thicker:.0f} mm  =>  D_min (Table) = {D_min:.0f} mm\n"
            f"  t_thinner = {t_thinner:.0f} mm  =>  D_max = {t_thinner:.0f} - 2 = {D_max:.0f} mm\n"
            f"\n"
            f"  Weld D = {D:.0f} mm:\n"
            f"    D >= D_min:  {D:.0f} >= {D_min:.0f}  =>  {'PASS' if D >= D_min else 'FAIL'}\n"
            f"    D <= D_max:  {D:.0f} <= {D_max:.0f}  =>  {'PASS' if D <= D_max else 'FAIL'}\n"
            f"\n"
            f"  L_eff_min = max(38, 4 x {D:.0f}) = {L_min:.0f} mm\n"
            f"  L (Seg 1) = {L_det:.0f} mm  =>  {'PASS' if L_det >= L_min else 'FAIL'}",
            language="text",
        )

        if is_lap and L_lap > 0:
            L_lap_min = lap_min_overlap(t_thinner, t_thicker)
            st.code(
                f"  Lap overlap min = max(5 x {min(t_thinner,t_thicker):.0f}, 25) = {L_lap_min:.0f} mm\n"
                f"  L_lap = {L_lap:.0f} mm  =>  {'PASS' if L_lap >= L_lap_min else 'FAIL'}",
                language="text",
            )
        _svg_html(svg_detailing(D, D_min, D_max, L_det, L_min, t_thinner, t_thicker), 210)

    # ══════════════════════════════════════════════════════════════════════════
    # CJP / PJP GROOVE
    # ══════════════════════════════════════════════════════════════════════════
    elif weld_type in ("Complete Joint Penetration (CJP) Groove",
                       "Partial Joint Penetration (PJP) Groove"):

        # Step 1: Groove weld shear
        st.markdown("##### Step 1 — Groove Weld Shear Resistance  *(Cl. 13.13.2.1)*")
        st.latex(
            r"V_r = \min\!\begin{cases}"
            r"0.67\,\phi_w\,A_m\,F_u & \text{base metal}\\"
            r"0.67\,\phi_w\,A_w\,X_u & \text{weld metal}"
            r"\end{cases}"
        )
        res_g = vr_groove_N(Am_mm2_groove, Aw_mm2, Fu, Xu)
        st.code(
            f"  (a) Base metal:  0.67 x {PHI_W} x {Am_mm2_groove:.0f} x {Fu:.0f}"
            f" = {res_g['Vr_base_kN']:.2f} kN\n"
            f"  (b) Weld metal:  0.67 x {PHI_W} x {Aw_mm2:.0f} x {Xu:.0f}"
            f"       = {res_g['Vr_weld_kN']:.2f} kN\n"
            f"  ─────────────────────────────────────────────\n"
            f"  Governing ({res_g['governs']}): Vr = {res_g['Vr_kN']:.2f} kN",
            language="text",
        )
        st.success(f"Vr = {res_g['Vr_kN']:.2f} kN — governed by {res_g['governs']}")
        st.markdown("---")

        if weld_type == "Complete Joint Penetration (CJP) Groove":
            # Step 2: Tension
            st.markdown("##### Step 2 — Tension Resistance  *(Cl. 13.13.3.1)*")
            st.latex(r"T_r = \phi\,A_g\,F_y \quad \text{(CJP with matching electrode: full restoration)}")
            st.info(
                "For a CJP groove weld made with matching electrode (or over-matching), "
                "the weld restores the full base metal tension capacity. "
                "Tr is governed by the base metal cross-section."
            )
        else:
            # Step 2: Tension (PJP)
            st.markdown("##### Step 2 — Tension Resistance  *(Cl. 13.13.3.2 / 13.13.3.3)*")
            if not has_fillet:
                st.latex(r"T_r = \min(\phi_w A_n F_u,\ \phi A_g F_y)")
                res_t = tr_pjp_N(An_mm2, Fu, Ag_mm2, Fy)
                st.code(
                    f"  Tr_weld = {PHI_W} x {An_mm2:.0f} x {Fu:.0f} = {res_t['Tr_weld_kN']:.2f} kN\n"
                    f"  Tr_cap  = {PHI}   x {Ag_mm2:.0f} x {Fy:.0f}  = {res_t['Tr_cap_kN']:.2f} kN\n"
                    f"  Governing ({res_t['governs']}): Tr = {res_t['Tr_kN']:.2f} kN",
                    language="text",
                )
                st.success(f"Tr = {res_t['Tr_kN']:.2f} kN")
            else:
                st.markdown("**Combined PJP + fillet (Cl. 13.13.3.3)**")
                st.latex(
                    r"T_r = \min\!\left(\phi_w\sqrt{(A_n F_u)^2+(A_w X_u)^2},\ \phi A_g F_y\right)"
                )
                res_tc = tr_pjp_combined_N(An_mm2, Aw_fillet_mm2, Fu, Xu, Ag_mm2, Fy)
                st.code(
                    f"  An x Fu      = {An_mm2:.0f} x {Fu:.0f} = {An_mm2*Fu:.0f} N\n"
                    f"  Aw x Xu      = {Aw_fillet_mm2:.0f} x {Xu:.0f} = {Aw_fillet_mm2*Xu:.0f} N\n"
                    f"\n"
                    f"  Tr_weld = {PHI_W} x sqrt({An_mm2*Fu:.0f}^2 + {Aw_fillet_mm2*Xu:.0f}^2)\n"
                    f"          = {res_tc['Tr_weld_kN']:.2f} kN\n"
                    f"  Tr_cap  = {PHI} x {Ag_mm2:.0f} x {Fy:.0f} = {res_tc['Tr_cap_kN']:.2f} kN\n"
                    f"  Governing ({res_tc['governs']}): Tr = {res_tc['Tr_kN']:.2f} kN",
                    language="text",
                )
                st.success(f"Tr = {res_tc['Tr_kN']:.2f} kN")

    # ══════════════════════════════════════════════════════════════════════════
    # FLARE BEVEL GROOVE
    # ══════════════════════════════════════════════════════════════════════════
    elif weld_type == "Flare Bevel Groove":
        st.markdown("##### Step 1 — Shear Resistance  *(Cl. 13.13.2.3)*")
        st.latex(r"V_r = 0.67\,\phi_w\,A_w\,F_u \qquad A_w = 0.50\,w_f\,L")
        res_fb = vr_flare_bevel_N(wf_mm, L_fb, Fu)
        st.code(
            f"  Aw = 0.50 x {wf_mm:.0f} x {L_fb:.0f} = {res_fb['Aw_mm2']:.0f} mm2\n"
            f"  Vr = 0.67 x {PHI_W} x {res_fb['Aw_mm2']:.0f} x {Fu:.0f}\n"
            f"     = {res_fb['Vr_kN']:.2f} kN",
            language="text",
        )
        st.success(f"Vr = {res_fb['Vr_kN']:.2f} kN")

# ── Summary metrics ───────────────────────────────────────────────────────────
with summ_col:
    st.markdown("#### Summary")

    if weld_type == "Fillet Weld" and segments:
        throat = effective_throat(D)
        total_Aw = sum(fillet_Aw(D, s["L"]) for s in segments)
        total_L  = sum(s["L"] for s in segments)
        theta_max = max(s["theta"] for s in segments)
        theta2_idx = max(range(len(segments)), key=lambda i: segments[i]["theta"])
        mw_vals = []
        for i, s in enumerate(segments):
            mw_vals.append(1.0 if len(segments) == 1 else Mw_factor(s["theta"], theta_max))
        total_Vr_kN = sum(vr_fillet_N(D, s["L"], s["theta"], Xu, mw_vals[i])["Vr_kN"]
                         for i, s in enumerate(segments))
        D_min2 = float(min_fillet_size(t_thicker))
        D_max2 = max_fillet_size(t_thinner)
        detail_ok = D >= D_min2 and D <= D_max2

        st.metric("Throat (mm)", f"{throat:.2f}")
        st.metric("Total Aw (mm2)", f"{total_Aw:.0f}")
        st.metric("Total Vr (kN)", f"{total_Vr_kN:.2f}")
        st.metric("theta_2 (deg)", f"{theta_max:.0f}  [Seg {theta2_idx+1}]")
        st.metric("Detailing", "PASS" if detail_ok else "FAIL")

        # Optional demand check
        st.markdown("---")
        st.markdown("**Demand Check**")
        Vf = st.number_input(
            "Vf (kN)", min_value=0.0, value=0.0, step=5.0, key="Vf_demand"
        )
        if Vf > 0:
            dc = Vf / total_Vr_kN if total_Vr_kN > 0 else float("inf")
            ok = dc <= 1.0
            st.metric("Vf / Vr", f"{dc:.3f}", delta=f"{'PASS' if ok else 'FAIL'}")
            if ok:
                st.success("PASS")
            else:
                st.error("FAIL — Vf exceeds Vr")

    elif "CJP" in weld_type:
        res_g2 = vr_groove_N(Am_mm2_groove, Aw_mm2, Fu, Xu)
        st.metric("Vr (kN)", f"{res_g2['Vr_kN']:.2f}")
        st.metric("Governs", res_g2["governs"])
        st.success("Full strength restored (CJP)")

    elif "PJP" in weld_type:
        res_g2 = vr_groove_N(Am_mm2_groove, Aw_mm2, Fu, Xu)
        st.metric("Vr shear (kN)", f"{res_g2['Vr_kN']:.2f}")
        st.metric("Governs shear", res_g2["governs"])
        if not has_fillet:
            res_t2 = tr_pjp_N(An_mm2, Fu, Ag_mm2, Fy)
            st.metric("Tr tension (kN)", f"{res_t2['Tr_kN']:.2f}")

    elif weld_type == "Flare Bevel Groove":
        res_fb2 = vr_flare_bevel_N(wf_mm, L_fb, Fu)
        st.metric("Aw (mm2)", f"{res_fb2['Aw_mm2']:.0f}")
        st.metric("Vr (kN)", f"{res_fb2['Vr_kN']:.2f}")
