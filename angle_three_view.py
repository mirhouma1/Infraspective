"""
Parametric three-view SVG generator for single angle bolted connections.

Views:
  1. Front (cross-section): true L-profile with root fillet and toe radii,
     leg dimensions, thickness, gauge tick marks.
  2. Side (elevation): vertical leg face with gauge line(s), bolt circles,
     end distance / pitch dimensions; horizontal leg shown edge-on as the
     bottom strip with bolt marks (matches hand-sketch convention).
  3. Top (plan): horizontal leg from above with its gauge line and bolts;
     vertical leg shown edge-on as a strip at the heel side.

All views share one scale. Member length is terminated with a break line.
ASCII-only source. SVG output uses plain text labels (mm).
"""

import math
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# CISC handbook data (Usual Gauges for Angles, mm) - from user's reference
# leg: (g, max_bolt_g, g1, max_bolt_g1, g2)   g1/g2 only for legs >= 125
# ---------------------------------------------------------------------------
USUAL_GAUGES = {
    200: {"g": 115, "bolt_g": "M36", "g1": 80, "bolt_g1": "M30", "g2": 80},
    150: {"g": 90,  "bolt_g": "M36", "g1": 55, "bolt_g1": "M24", "g2": 65},
    125: {"g": 80,  "bolt_g": "M30", "g1": 45, "bolt_g1": "M20", "g2": 54},
    100: {"g": 65,  "bolt_g": "M27"},
    90:  {"g": 60,  "bolt_g": "M24"},
    80:  {"g": 50,  "bolt_g": "M24"},
    75:  {"g": 45,  "bolt_g": "M24"},
    65:  {"g": 35,  "bolt_g": "M24"},
    60:  {"g": 30,  "bolt_g": "M24"},
    55:  {"g": 27,  "bolt_g": "M22"},
    50:  {"g": 28,  "bolt_g": "M16"},
    45:  {"g": 23,  "bolt_g": "M16"},
}

# Minimum edge distance for bolt holes, mm (CISC): dia: (sheared, rolled/gas-cut)
MIN_EDGE_DISTANCE = {
    16: (28, 22), 20: (34, 26), 22: (38, 28), 24: (42, 30),
    27: (48, 34), 30: (52, 38), 36: (64, 46),
}


def usual_gauge_for_leg(leg_mm: float) -> Dict[str, Any]:
    """Nearest tabulated leg size at or below the given leg."""
    sizes = sorted(USUAL_GAUGES.keys())
    pick = sizes[0]
    for s in sizes:
        if s <= leg_mm + 0.5:
            pick = s
    return {"leg_row": pick, **USUAL_GAUGES[pick]}


# ---------------------------------------------------------------------------
# SVG primitives
# ---------------------------------------------------------------------------
STYLE = {
    "outline": 'stroke="#1a1a1a" stroke-width="1.6" fill="#e8edf2"',
    "outline_nofill": 'stroke="#1a1a1a" stroke-width="1.6" fill="none"',
    "hidden": 'stroke="#666" stroke-width="1" stroke-dasharray="6,4" fill="none"',
    "center": 'stroke="#c0392b" stroke-width="0.8" stroke-dasharray="14,4,3,4" fill="none"',
    "dim": 'stroke="#2c5f8a" stroke-width="0.9" fill="none"',
    "bolt": 'stroke="#1a1a1a" stroke-width="1.1" fill="white"',
    "bolt_edge": 'fill="#1a1a1a"',
}
FONT = 'font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#2c5f8a"'
FONT_TITLE = 'font-family="Helvetica, Arial, sans-serif" font-size="14" font-weight="bold" fill="#1a1a1a"'


def _line(x1, y1, x2, y2, style) -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" {style}/>'


def _text(x, y, s, anchor="middle", font=FONT, rot=None) -> str:
    tr = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot is not None else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" {font}{tr}>{s}</text>'


def _arrow_marker_defs() -> str:
    return (
        '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#2c5f8a"/></marker></defs>'
    )


def _dim_h(x1, x2, y, label, ext_y1=None, ext_y2=None, text_above=True) -> str:
    """Horizontal dimension line with extension lines and arrows."""
    parts = []
    if ext_y1 is not None:
        parts.append(_line(x1, ext_y1, x1, y + (4 if y > ext_y1 else -4), STYLE["dim"]))
    if ext_y2 is not None:
        parts.append(_line(x2, ext_y2, x2, y + (4 if y > ext_y2 else -4), STYLE["dim"]))
    parts.append(
        f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
        f'{STYLE["dim"]} marker-start="url(#arr)" marker-end="url(#arr)"/>'
    )
    ty = y - 5 if text_above else y + 14
    parts.append(_text((x1 + x2) / 2.0, ty, label))
    return "".join(parts)


def _dim_v(y1, y2, x, label, ext_x1=None, ext_x2=None, text_left=True) -> str:
    """Vertical dimension line with extension lines and arrows."""
    parts = []
    if ext_x1 is not None:
        parts.append(_line(ext_x1, y1, x + (4 if x > ext_x1 else -4), y1, STYLE["dim"]))
    if ext_x2 is not None:
        parts.append(_line(ext_x2, y2, x + (4 if x > ext_x2 else -4), y2, STYLE["dim"]))
    parts.append(
        f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" '
        f'{STYLE["dim"]} marker-start="url(#arr)" marker-end="url(#arr)"/>'
    )
    tx = x - 7 if text_left else x + 7
    anchor = "end" if text_left else "start"
    parts.append(_text(tx, (y1 + y2) / 2.0 + 4, label, anchor=anchor))
    return "".join(parts)


def _break_line(x, y_top, y_bot, amp=6.0) -> str:
    """Zigzag break line from y_top to y_bot at x."""
    n = max(4, int((y_bot - y_top) / 14))
    pts = [f"{x:.1f},{y_top:.1f}"]
    for i in range(1, n):
        yy = y_top + (y_bot - y_top) * i / n
        xx = x + (amp if i % 2 else -amp)
        pts.append(f"{xx:.1f},{yy:.1f}")
    pts.append(f"{x:.1f},{y_bot:.1f}")
    return f'<polyline points="{" ".join(pts)}" {STYLE["outline_nofill"]}/>'


# ---------------------------------------------------------------------------
# Front view: true cross-section with fillets
# ---------------------------------------------------------------------------
def _front_path(ox, oy, d, b, t, r, rt, s) -> str:
    """
    L-profile path. Origin (ox, oy) = heel outer corner (bottom-left) in px.
    d = vertical leg, b = horizontal leg, t = thickness, r = root radius,
    rt = toe radius. s = scale px/mm. SVG y grows downward.
    """
    def X(v):
        return ox + v * s

    def Y(v):
        return oy - v * s

    p = []
    p.append(f"M {X(0):.1f} {Y(d):.1f}")                       # top-left outer
    p.append(f"L {X(0):.1f} {Y(0):.1f}")                        # down back face
    p.append(f"L {X(b):.1f} {Y(0):.1f}")                        # along bottom
    p.append(f"L {X(b):.1f} {Y(t - rt):.1f}")                   # up toe
    p.append(f"A {rt*s:.1f} {rt*s:.1f} 0 0 1 {X(b - rt):.1f} {Y(t):.1f}")  # toe radius
    p.append(f"L {X(t + r):.1f} {Y(t):.1f}")                    # inner top of horiz leg
    p.append(f"A {r*s:.1f} {r*s:.1f} 0 0 0 {X(t):.1f} {Y(t + r):.1f}")     # root fillet
    p.append(f"L {X(t):.1f} {Y(d - rt):.1f}")                   # up inner face
    p.append(f"A {rt*s:.1f} {rt*s:.1f} 0 0 1 {X(t - rt):.1f} {Y(d):.1f}")  # toe radius
    p.append("Z")
    return f'<path d="{" ".join(p)}" {STYLE["outline"]}/>'


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------
def angle_three_view_svg(
    d_mm: float,                 # vertical (connected) leg
    b_mm: float,                 # horizontal (outstanding) leg
    t_mm: float,
    r_mm: Optional[float] = None,     # root radius (default 1.0*t)
    rt_mm: Optional[float] = None,    # toe radius (default 0.5*t)
    n_bolts: int = 3,
    pitch_mm: float = 80.0,
    end_dist_mm: float = 40.0,
    stagger_mm: float = 0.0,          # offset of second gauge line row
    bolt_dia_mm: float = 20.0,
    designation: str = "",
    scale: float = 2.0,               # px per mm
) -> str:
    r = r_mm if r_mm is not None else 1.0 * t_mm
    rt = rt_mm if rt_mm is not None else 0.5 * t_mm

    gv = usual_gauge_for_leg(d_mm)    # gauges on the connected vertical leg
    gh = usual_gauge_for_leg(b_mm)    # gauge on the outstanding leg (top view)
    two_rows = "g1" in gv

    hole = bolt_dia_mm + 2.0          # standard hole = bolt + 2 mm

    # geometry of the shown member length (connection zone + run-out to break)
    rows_extent = stagger_mm + (n_bolts - 1) * pitch_mm
    L_show = end_dist_mm + rows_extent + 55.0

    s = scale
    M = 70.0                          # outer margin px
    gap = 60.0                        # gap between views px

    front_w = b_mm * s
    front_h = d_mm * s
    elev_w = L_show * s
    elev_h = d_mm * s
    plan_h = b_mm * s

    W = M + front_w + gap + elev_w + M + 40
    H = M + max(front_h, elev_h) + gap + plan_h + M + 30

    # anchors (px). Front and elevation share the same baseline (heel, y=0 mm).
    fx, fy = M + 20, M + front_h                       # front origin: heel bottom-left
    ex, ey = fx + front_w + gap + 40, fy               # elevation left-bottom
    px_, py = ex, ey + gap + plan_h                    # plan left-bottom (below elevation)

    svg: List[str] = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
        f'viewBox="0 0 {W:.0f} {H:.0f}" style="background:white">'
    )
    svg.append(_arrow_marker_defs())
    if designation:
        svg.append(_text(W / 2, 24, f"Single Angle {designation} - Bolted Connection Detail",
                         font=FONT_TITLE))

    # ---------------- FRONT VIEW (cross-section) ----------------
    svg.append(_front_path(fx, fy, d_mm, b_mm, t_mm, r, rt, s))
    svg.append(_text(fx + front_w / 2, fy + 40, "FRONT VIEW (SECTION)", font=FONT_TITLE))

    # gauge tick(s) on vertical leg (measured from heel/back face = bottom here? no:
    # gauges on the connected leg are measured from the heel along the leg)
    if two_rows:
        g1, g2 = gv["g1"], gv["g2"]
        y_g1 = fy - g1 * s
        y_g2 = fy - (g1 + g2) * s
        svg.append(_line(fx - 14, y_g1, fx + t_mm * s + 14, y_g1, STYLE["center"]))
        svg.append(_line(fx - 14, y_g2, fx + t_mm * s + 14, y_g2, STYLE["center"]))
        svg.append(_dim_v(fy, y_g1, fx - 26, f"g1={g1}", text_left=True))
        svg.append(_dim_v(y_g1, y_g2, fx - 26, f"g2={g2}", text_left=True))
    else:
        g = gv["g"]
        y_g = fy - g * s
        svg.append(_line(fx - 14, y_g, fx + t_mm * s + 14, y_g, STYLE["center"]))
        svg.append(_dim_v(fy, y_g, fx - 26, f"g={g}", text_left=True))

    # gauge tick on horizontal leg
    x_gh = fx + gh["g"] * s
    svg.append(_line(x_gh, fy + 14, x_gh, fy - t_mm * s - 14, STYLE["center"]))

    # dimensions: legs and thickness
    svg.append(_dim_v(fy - d_mm * s, fy, fx - 52, f"{d_mm:.0f}", ext_x1=fx, ext_x2=fx))
    svg.append(_dim_h(fx, fx + b_mm * s, fy + 26, f"{b_mm:.0f}", ext_y1=fy, ext_y2=fy,
                      text_above=False))
    svg.append(_dim_h(fx, fx + t_mm * s, fy - d_mm * s - 12, f"t={t_mm:.0f}",
                      ext_y1=fy - d_mm * s, ext_y2=fy - (d_mm - 2) * s))
    svg.append(_dim_h(fx, x_gh, fy + 52, f"g={gh['g']}", text_above=False))

    # ---------------- SIDE VIEW (elevation) ----------------
    ex_r = ex + elev_w
    top = ey - elev_h
    svg.append(f'<rect x="{ex:.1f}" y="{top:.1f}" width="{elev_w:.1f}" '
               f'height="{elev_h:.1f}" {STYLE["outline"]}/>')
    svg.append(_break_line(ex_r, top, ey))
    # horizontal leg edge-on: bottom strip of thickness t
    svg.append(_line(ex, ey - t_mm * s, ex_r, ey - t_mm * s, STYLE["hidden"]))
    svg.append(_text(ex + elev_w / 2, ey + 40, "SIDE VIEW (ELEVATION)", font=FONT_TITLE))

    # gauge lines + bolts on the vertical leg face
    def _bolts_on_line(y_px, x0_mm):
        out = []
        out.append(_line(ex, y_px, ex_r, y_px, STYLE["center"]))
        for i in range(n_bolts):
            cx = ex + (x0_mm + i * pitch_mm) * s
            rr = hole / 2.0 * s
            out.append(f'<circle cx="{cx:.1f}" cy="{y_px:.1f}" r="{rr:.1f}" {STYLE["bolt"]}/>')
            out.append(_line(cx, y_px - rr - 5, cx, y_px + rr + 5, STYLE["center"]))
        return out

    if two_rows:
        y1 = ey - gv["g1"] * s
        y2 = ey - (gv["g1"] + gv["g2"]) * s
        svg.extend(_bolts_on_line(y2, end_dist_mm + stagger_mm))   # top row (offset)
        svg.extend(_bolts_on_line(y1, end_dist_mm))                 # bottom row
        svg.append(_dim_v(ey, y1, ex_r + 26, f"g1={gv['g1']}", text_left=False))
        svg.append(_dim_v(y1, y2, ex_r + 26, f"g2={gv['g2']}", text_left=False))
        bolts_bottom_x0 = end_dist_mm
    else:
        yg = ey - gv["g"] * s
        svg.extend(_bolts_on_line(yg, end_dist_mm))
        svg.append(_dim_v(ey, yg, ex_r + 26, f"g={gv['g']}", text_left=False))
        bolts_bottom_x0 = end_dist_mm

    # bolt marks in the horizontal-leg edge strip (plan bolts seen edge-on)
    for i in range(n_bolts):
        cx = ex + (end_dist_mm + i * pitch_mm) * s
        svg.append(f'<rect x="{cx - 4:.1f}" y="{ey - t_mm * s:.1f}" width="8" '
                   f'height="{t_mm * s:.1f}" {STYLE["bolt_edge"]}/>')

    # longitudinal dimensions along the top: e, p, p, ... and s
    ytop_dim = top - 16
    xe0 = ex
    xe1 = ex + end_dist_mm * s
    svg.append(_dim_h(xe0, xe1, ytop_dim, f"e={end_dist_mm:.0f}", ext_y1=top, ext_y2=top))
    for i in range(n_bolts - 1):
        xa = ex + (end_dist_mm + i * pitch_mm) * s
        xb = xa + pitch_mm * s
        svg.append(_dim_h(xa, xb, ytop_dim, f"p={pitch_mm:.0f}", ext_y1=top, ext_y2=top))
    if two_rows and stagger_mm > 0:
        # stagger dimension s between adjacent-row holes (first bolt of each row)
        xa = ex + end_dist_mm * s
        xb = xa + stagger_mm * s
        svg.append(_dim_h(xa, xb, ytop_dim - 24, f"s={stagger_mm:.0f}",
                          ext_y1=top, ext_y2=top))
        # diagonal tie between staggered holes (net-area zig-zag path visual)
        y_lo = ey - gv["g1"] * s
        y_hi = ey - (gv["g1"] + gv["g2"]) * s
        for i in range(n_bolts):
            x_lo = ex + (end_dist_mm + i * pitch_mm) * s
            x_hi = x_lo + stagger_mm * s
            svg.append(_line(x_lo, y_lo, x_hi, y_hi, STYLE["dim"]))
    # hole callout
    svg.append(_text(ex + elev_w / 2, top - 46,
                     f"{n_bolts * (2 if two_rows else 1)} bolts M{bolt_dia_mm:.0f} "
                     f"in {hole:.0f} dia holes"))

    # vertical leg height dim on elevation
    svg.append(_dim_v(top, ey, ex - 26, f"{d_mm:.0f}", ext_x1=ex, ext_x2=ex))

    # ---------------- TOP VIEW (plan) ----------------
    ptop = py - plan_h
    svg.append(f'<rect x="{px_:.1f}" y="{ptop:.1f}" width="{elev_w:.1f}" '
               f'height="{plan_h:.1f}" {STYLE["outline"]}/>')
    svg.append(_break_line(px_ + elev_w, ptop, py))
    # vertical leg edge-on: strip of thickness t at the heel side (top of plan)
    svg.append(_line(px_, ptop + t_mm * s, px_ + elev_w, ptop + t_mm * s, STYLE["hidden"]))
    svg.append(_text(px_ + elev_w / 2, py + 40, "TOP VIEW (PLAN)", font=FONT_TITLE))

    # gauge line + bolts on the outstanding leg (measured from heel = top edge)
    ygp = ptop + gh["g"] * s
    svg.append(_line(px_, ygp, px_ + elev_w, ygp, STYLE["center"]))
    for i in range(n_bolts):
        cx = px_ + (end_dist_mm + i * pitch_mm) * s
        rr = hole / 2.0 * s
        svg.append(f'<circle cx="{cx:.1f}" cy="{ygp:.1f}" r="{rr:.1f}" {STYLE["bolt"]}/>')
        svg.append(_line(cx, ygp - rr - 5, cx, ygp + rr + 5, STYLE["center"]))
        # matching edge-on marks for the vertical-leg bolts
    for i in range(n_bolts):
        cx = px_ + (end_dist_mm + i * pitch_mm) * s
        svg.append(f'<rect x="{cx - 4:.1f}" y="{ptop:.1f}" width="8" '
                   f'height="{t_mm * s:.1f}" {STYLE["bolt_edge"]}/>')

    svg.append(_dim_v(ptop, ygp, px_ - 26, f"g={gh['g']}", ext_x1=px_, ext_x2=px_))
    svg.append(_dim_v(ptop, py, px_ + elev_w + 26, f"{b_mm:.0f}", text_left=False))

    svg.append("</svg>")
    return "".join(svg)


if __name__ == "__main__":
    # Test case = user's hand sketch: L152x102x13, 3 bolts per line,
    # pitch 80, end distance 40, second row staggered 40.
    out = angle_three_view_svg(
        d_mm=152.0, b_mm=102.0, t_mm=13.0,
        n_bolts=3, pitch_mm=80.0, end_dist_mm=40.0, stagger_mm=40.0,
        bolt_dia_mm=20.0, designation="L152x102x13",
    )
    with open("/home/claude/angle_views/L152x102x13_views.svg", "w") as f:
        f.write(out)
    print("SVG written,", len(out), "bytes")
