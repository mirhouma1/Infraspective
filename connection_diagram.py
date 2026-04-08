"""
connection_diagram.py
─────────────────────
Generates a dual-view SVG for CSA S16 tension member bolt connections.

  Left  → Elevation view  (side view along member length)
  Right → Plan view  (face-on view of connected element)

Public API
──────────
    generate_connection_svg(
        n_lines, bolts_per_line, pitch, gauge,
        edge_end, edge_trans,
        leg_width, thickness, hole_dia,
        show_fracture=True, show_block_shear=True,
        section_label="",
        governing_path_n_holes=1,
        zig_zag=False,
    ) -> str
"""

from __future__ import annotations
from typing import List, Tuple
import math


# ── Palette ───────────────────────────────────────────────────────────────────
C_MEMBER      = "#2d3a4a"
C_MEMBER_STK  = "#1a252f"
C_HOLE        = "#ffffff"
C_HOLE_STK    = "#555"
C_FRACTURE    = "#d32f2f"
C_ANT         = "rgba(25,118,210,0.22)"
C_ANT_STK     = "#1976d2"
C_AGV         = "rgba(245,124,0,0.22)"
C_AGV_STK     = "#f57c00"
C_DIM         = "#37474f"
C_BG          = "#f5f7fa"
C_PANEL       = "#ffffff"
C_LABEL       = "#263238"
C_TITLE       = "#1a252f"

FONT = "font-family='Consolas,Monaco,monospace'"


# ── SVG helpers ───────────────────────────────────────────────────────────────
def _line(x1, y1, x2, y2, stroke, sw=1.0, dash="", extra=""):
    d = f"stroke-dasharray='{dash}'" if dash else ""
    return (f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
            f"stroke='{stroke}' stroke-width='{sw}' {d} {extra}/>")


def _rect(x, y, w, h, fill, stroke="none", sw=1.0, rx=0, extra=""):
    return (f"<rect x='{x:.1f}' y='{y:.1f}' width='{w:.1f}' height='{h:.1f}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}' rx='{rx}' {extra}/>")


def _circle(cx, cy, r, fill, stroke, sw=1.0):
    return (f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='{r:.1f}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'/>")


def _text(x, y, txt, size=10, fill=C_LABEL, anchor="middle", weight="normal", extra=""):
    return (f"<text x='{x:.1f}' y='{y:.1f}' text-anchor='{anchor}' "
            f"font-size='{size}' fill='{fill}' font-weight='{weight}' "
            f"{FONT} {extra}>{txt}</text>")


def _dim_line(x1, y1, x2, y2, label, orient="h", offset=18):
    els = []
    if orient == "h":
        yl = y1 + offset
        els.append(_line(x1, y1, x1, yl + 5, C_DIM, 0.7))
        els.append(_line(x2, y2, x2, yl + 5, C_DIM, 0.7))
        els.append(_line(x1, yl, x2, yl, C_DIM, 0.8))
        mx = (x1 + x2) / 2
        els.append(_text(mx, yl - 3, label, size=9, fill=C_DIM))
    else:
        xl = x1 - offset
        els.append(_line(x1, y1, xl - 5, y1, C_DIM, 0.7))
        els.append(_line(x2, y2, xl - 5, y2, C_DIM, 0.7))
        els.append(_line(xl, y1, xl, y2, C_DIM, 0.8))
        my = (y1 + y2) / 2
        els.append(
            f"<text x='{xl - 4:.1f}' y='{my:.1f}' text-anchor='middle' "
            f"font-size='9' fill='{C_DIM}' {FONT} "
            f"transform='rotate(-90,{xl - 4:.1f},{my:.1f})'>{label}</text>"
        )
    return "\n".join(els)


def _scale_factor(real_extent: float, pixel_budget: float, margin: float = 0.80) -> float:
    return (pixel_budget * margin) / max(real_extent, 1.0)


# ── Elevation view ────────────────────────────────────────────────────────────
def _elevation_view(
    px, py, pw, ph,
    bolts_per_line, pitch, edge_end, hole_dia, thickness,
    show_fracture, governing_n_holes, zig_zag,
) -> str:
    els: List[str] = []
    els.append(_rect(px, py, pw, ph, C_PANEL, C_DIM, 0.5, rx=4))
    els.append(_text(px + pw / 2, py + 14, "ELEVATION VIEW", size=10,
                     fill=C_TITLE, weight="bold"))

    total_len_mm = edge_end + (bolts_per_line - 1) * pitch + edge_end * 0.6
    member_h_mm  = max(thickness, 20.0)
    draw_w = pw - 60
    draw_h = ph - 60
    sx = _scale_factor(total_len_mm, draw_w)
    sy = _scale_factor(member_h_mm,  draw_h * 0.4)
    s  = min(sx, sy, 2.5)

    ox = px + 30
    oy = py + 34
    member_w_px = total_len_mm * s
    member_h_px = max(member_h_mm * s, 18)

    els.append(_rect(ox, oy, member_w_px, member_h_px, C_MEMBER, C_MEMBER_STK, 1.2))

    step_h = max(4, member_h_px / 5)
    yh = oy + step_h
    while yh < oy + member_h_px - 1:
        els.append(_line(ox + 1, yh, ox + member_w_px - 1, yh, "#4a6070", 0.35))
        yh += step_h

    r_hole = max(hole_dia * s / 2, 3.5)
    cy_hole = oy + member_h_px / 2
    hole_xs: List[float] = []
    for i in range(bolts_per_line):
        hx = ox + (edge_end + i * pitch) * s
        hole_xs.append(hx)
        els.append(_circle(hx, cy_hole, r_hole, C_HOLE, C_HOLE_STK, 1.0))

    if show_fracture and hole_xs:
        n = min(governing_n_holes, len(hole_xs))
        fy = cy_hole
        if zig_zag and n >= 2:
            pts = [(ox, fy)]
            for i in range(n):
                hx = hole_xs[i]
                yoff = oy + member_h_px * 0.2 if i % 2 == 0 else oy + member_h_px * 0.8
                pts.append((hx - r_hole, yoff))
                pts.append((hx + r_hole, yoff))
            pts.append((hole_xs[n - 1] + r_hole + (edge_end * 0.2) * s, fy))
        else:
            pts = [(ox, fy), (hole_xs[0] - r_hole, fy), (hole_xs[0] + r_hole, fy)]
            for i in range(1, n):
                pts.append((hole_xs[i] - r_hole, fy))
                pts.append((hole_xs[i] + r_hole, fy))
            pts.append((ox + member_w_px, fy))
        path_d = "M " + " L ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts)
        els.append(
            f"<path d='{path_d}' fill='none' stroke='{C_FRACTURE}' "
            f"stroke-width='2' stroke-dasharray='6,3' stroke-linecap='round'/>"
        )

    dim_y_base = oy + member_h_px + 10
    els.append(_dim_line(ox, dim_y_base, ox + edge_end * s, dim_y_base,
                         f"e\u2081={edge_end:.0f}", orient="h", offset=12))
    if bolts_per_line >= 2:
        els.append(_dim_line(hole_xs[0], dim_y_base, hole_xs[1], dim_y_base,
                             f"s={pitch:.0f}", orient="h", offset=26))

    for i, hx in enumerate(hole_xs):
        els.append(_text(hx, oy - 5, str(i + 1), size=8, fill=C_DIM))

    if show_fracture:
        lx = px + pw - 10
        ly = py + ph - 16
        els.append(_line(lx - 40, ly, lx - 10, ly, C_FRACTURE, 2, "6,3"))
        els.append(_text(lx - 42, ly + 4, "Net fracture path", size=8,
                         fill=C_FRACTURE, anchor="end"))

    return "\n".join(els)


# ── Plan view ─────────────────────────────────────────────────────────────────
def _plan_view(
    px, py, pw, ph,
    n_lines, bolts_per_line, pitch, gauge,
    edge_end, edge_trans, hole_dia, thickness, leg_width,
    show_block_shear,
) -> str:
    els: List[str] = []
    els.append(_rect(px, py, pw, ph, C_PANEL, C_DIM, 0.5, rx=4))
    els.append(_text(px + pw / 2, py + 14, "PLAN VIEW", size=10,
                     fill=C_TITLE, weight="bold"))

    total_w_mm = edge_trans + (n_lines - 1) * gauge + edge_trans
    total_h_mm = edge_end   + (bolts_per_line - 1) * pitch + edge_end * 0.6
    plate_w_mm = max(leg_width, total_w_mm + 5)
    plate_h_mm = total_h_mm

    draw_w = pw - 70
    draw_h = ph - 60
    sx = _scale_factor(plate_w_mm, draw_w)
    sy = _scale_factor(plate_h_mm, draw_h)
    s  = min(sx, sy, 2.5)

    ox = px + 45
    oy = py + 28
    plate_w_px = plate_w_mm * s
    plate_h_px = plate_h_mm * s

    els.append(_rect(ox, oy, plate_w_px, plate_h_px, C_MEMBER, C_MEMBER_STK, 1.2))

    for k in range(-int(plate_h_px), int(plate_w_px + plate_h_px), 12):
        x1 = ox + k
        x2 = x1 + plate_h_px
        els.append(_line(max(x1, ox), oy,
                         min(x2, ox + plate_w_px), oy + plate_h_px,
                         "#4a6070", 0.25))

    r_hole = max(hole_dia * s / 2, 3.5)
    hole_grid: List[Tuple[float, float]] = []
    for col in range(n_lines):
        for row in range(bolts_per_line):
            hx = ox + (edge_trans + col * gauge) * s
            hy = oy + (edge_end   + row * pitch) * s
            hole_grid.append((hx, hy))
            els.append(_circle(hx, hy, r_hole, C_HOLE, C_HOLE_STK, 1.0))

    if show_block_shear and hole_grid:
        last_row_y  = oy + (edge_end + (bolts_per_line - 1) * pitch) * s
        first_col_x = ox + edge_trans * s

        for col in range(n_lines):
            shear_x = ox + (edge_trans + col * gauge) * s - r_hole
            shear_w = r_hole * 2
            els.append(_rect(shear_x, oy, shear_w, last_row_y - oy + r_hole,
                             C_AGV, C_AGV_STK, 1.2))

        ant_x = ox
        ant_y = last_row_y - r_hole
        ant_w = first_col_x - ox + r_hole
        ant_h = r_hole * 2 + (edge_end * 0.2 * s)
        if ant_w > 0:
            els.append(_rect(ant_x, ant_y, ant_w, ant_h, C_ANT, C_ANT_STK, 1.2))

        for hx, hy in hole_grid:
            els.append(_circle(hx, hy, r_hole, C_HOLE, C_HOLE_STK, 1.0))

    if n_lines >= 2:
        g_x1 = ox + edge_trans * s
        g_x2 = ox + (edge_trans + gauge) * s
        g_y  = oy - 10
        els.append(_dim_line(g_x1, g_y, g_x2, g_y,
                             f"g={gauge:.0f}", orient="h", offset=-14))

    e2_x1 = ox
    e2_x2 = ox + edge_trans * s
    e2_y  = oy + plate_h_px + 8
    els.append(_dim_line(e2_x1, e2_y, e2_x2, e2_y,
                         f"e\u2082={edge_trans:.0f}", orient="h", offset=12))

    if bolts_per_line >= 2:
        p_y1 = oy + edge_end * s
        p_y2 = oy + (edge_end + pitch) * s
        p_x  = ox - 10
        els.append(_dim_line(p_x, p_y1, p_x, p_y2,
                             f"s={pitch:.0f}", orient="v", offset=22))

    lx = px + 6
    ly = py + ph - 44
    leg_items = []
    if show_block_shear:
        leg_items = [
            (C_AGV, C_AGV_STK, "Shear plane (Agv)"),
            (C_ANT, C_ANT_STK, "Tension face (Ant)"),
        ]
    for i, (fill, stk, label) in enumerate(leg_items):
        bx = lx
        by = ly + i * 16
        els.append(_rect(bx, by, 12, 10, fill, stk, 1.0))
        els.append(_text(bx + 16, by + 9, label, size=8, fill=C_DIM, anchor="start"))

    return "\n".join(els)


# ── Public entry point ────────────────────────────────────────────────────────
def generate_connection_svg(
    n_lines:                int,
    bolts_per_line:         int,
    pitch:                  float,
    gauge:                  float,
    edge_end:               float,
    edge_trans:             float,
    leg_width:              float,
    thickness:              float,
    hole_dia:               float,
    show_fracture:          bool = True,
    show_block_shear:       bool = True,
    section_label:          str  = "",
    governing_path_n_holes: int  = 1,
    zig_zag:                bool = False,
) -> str:
    W  = 820
    H  = 320
    PW = 390
    PH = H - 20
    GAP = 20
    LPX = 10
    RPX = LPX + PW + GAP

    parts: List[str] = []
    parts.append(
        f"<svg xmlns='http://www.w3.org/2000/svg' "
        f"width='{W}' height='{H}' viewBox='0 0 {W} {H}'>"
    )
    parts.append(_rect(0, 0, W, H, C_BG, "none"))

    if section_label:
        parts.append(_text(W / 2, 13, section_label, size=11,
                           fill=C_TITLE, weight="bold"))

    parts.append(_elevation_view(
        px=LPX, py=10, pw=PW, ph=PH,
        bolts_per_line=bolts_per_line,
        pitch=pitch,
        edge_end=edge_end,
        hole_dia=hole_dia,
        thickness=thickness,
        show_fracture=show_fracture,
        governing_n_holes=governing_path_n_holes,
        zig_zag=zig_zag,
    ))

    parts.append(_plan_view(
        px=RPX, py=10, pw=PW, ph=PH,
        n_lines=n_lines,
        bolts_per_line=bolts_per_line,
        pitch=pitch,
        gauge=gauge,
        edge_end=edge_end,
        edge_trans=edge_trans,
        hole_dia=hole_dia,
        thickness=thickness,
        leg_width=leg_width,
        show_block_shear=show_block_shear,
    ))

    parts.append("</svg>")
    return "\n".join(parts)
