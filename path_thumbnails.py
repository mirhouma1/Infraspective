from __future__ import annotations

# path_thumbnails.py
# Compact per-candidate SVG diagrams. One small picture for ONE net-fracture
# path or ONE block-shear pattern, drawn straight from that candidate's own
# fields. No combined overlay, no A/B/C guessing.
#
# Frame: member length runs DOWN the page (y), transverse width runs ACROSS
# (x). A bolt at (line, row) sits at
#     x = edge_trans + line * gauge      (from the near/reference edge, x=0)
#     y = edge_end   + row  * pitch      (from the loaded end, top)

# geom is a plain dict the panel already has the pieces for:
#   w_conn, n_lines, bolts_per_line, pitch, gauge, edge_end, edge_trans, hole_dia
#
# ASCII only. Straight quotes only.

from typing import Dict, List, Tuple

# ---- styles ---------------------------------------------------------------
EL = 'stroke="#1a1a1a" stroke-width="1.4" fill="#eef2f6"'
HOLE = 'stroke="#1a1a1a" stroke-width="1" fill="white"'
FRAC = 'stroke="#c0392b" stroke-width="2.2" stroke-dasharray="7,4" fill="none"'
SHEAR = 'stroke="#d35400" stroke-width="2.4" fill="none"'
TENS = 'stroke="#c0392b" stroke-width="2.4" fill="none"'
BLOCK = 'fill="#f39c12" fill-opacity="0.20" stroke="none"'
GOV = 'fill="#2e7d32" fill-opacity="0.10" stroke="#2e7d32" stroke-width="1.2"'
TITLE = 'font-family="Helvetica,Arial,sans-serif" font-size="12" font-weight="bold" fill="#1a1a1a"'
LBL = 'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#c0392b"'
LBLO = 'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#d35400"'


def _frame(geom: Dict) -> Tuple[float, float, float, float, float, float, float]:
    # Returns (W, H, ML, MT, sx, sy, Lmember).
    w = float(geom["w_conn"])
    rows = int(geom["bolts_per_line"])
    Lmember = geom["edge_end"] + (rows - 1) * geom["pitch"] + geom["edge_end"]
    DW, DH = 170.0, 230.0
    sx = DW / w if w > 0 else 1.0
    sy = DH / Lmember if Lmember > 0 else 1.0
    ML, MT, MR, MB = 42.0, 30.0, 42.0, 22.0
    W = ML + w * sx + MR
    H = MT + Lmember * sy + MB
    return W, H, ML, MT, sx, sy, Lmember


def _xy(geom, ML, MT, sx, sy, line, row):
    x = ML + (geom["edge_trans"] + line * geom["gauge"]) * sx
    y = MT + (geom["edge_end"] + row * geom["pitch"]) * sy
    return x, y


def _shell(geom, title):
    W, H, ML, MT, sx, sy, Lm = _frame(geom)
    w = float(geom["w_conn"])
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
        f'viewBox="0 0 {W:.0f} {H:.0f}" style="background:white">',
        f'<text x="{W/2:.1f}" y="18" text-anchor="middle" {TITLE}>{title}</text>',
        f'<rect x="{ML:.1f}" y="{MT:.1f}" width="{w*sx:.1f}" '
        f'height="{Lm*sy:.1f}" {EL}/>',
    ]
    return body, W, H, ML, MT, sx, sy, Lm


def _holes(geom, ML, MT, sx, sy):
    out = []
    rr = max(2.0, min(7.0, geom["hole_dia"] / 2 * sx))
    for line in range(int(geom["n_lines"])):
        for row in range(int(geom["bolts_per_line"])):
            cx, cy = _xy(geom, ML, MT, sx, sy, line, row)
            out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr:.1f}" {HOLE}/>')
    return out


# ---------------------------------------------------------------------------
def net_thumb(cand: Dict, geom: Dict, governs: bool = False) -> str:
    # Draw ONE net-fracture path through the holes it actually cuts.
    title = ("GOVERNS  " if governs else "") + cand.get("description", "net path")
    svg, W, H, ML, MT, sx, sy, Lm = _shell(geom, title)
    svg += _holes(geom, ML, MT, sx, sy)

    sel: List[Tuple[int, int]] = cand.get("selected", [])
    if sel:
        sel = sorted(sel, key=lambda lr: lr[0])          # by line, left to right
        pts = [_xy(geom, ML, MT, sx, sy, ln, rw) for ln, rw in sel]
        # extend to the two transverse edges so the tear crosses the width
        left = (ML, pts[0][1])
        right = (ML + geom["w_conn"] * sx, pts[-1][1])
        chain = [left] + pts + [right]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in chain)
        svg.append(f'<polyline points="{d}" {FRAC}/>')

    An = cand.get("An_mm2")
    if An is not None:
        svg.append(f'<text x="{W/2:.1f}" y="{H-6:.1f}" text-anchor="middle" '
                   f'{LBL}>An = {An:,.0f} mm2</text>')
    svg.append("</svg>")
    return "".join(svg)


# ---------------------------------------------------------------------------
def _parse_key(key: str) -> Tuple[str, List[int]]:
    # "NEAR-2" -> ("NEAR",[1]); "BETWEEN-1-3" -> ("BETWEEN",[0,2]) (0-based lines)
    parts = key.split("-")
    kind = parts[0]
    idx = [int(p) - 1 for p in parts[1:] if p.isdigit()]
    return kind, idx


def block_thumb(cand: Dict, geom: Dict, governs: bool = False) -> str:
    # Draw ONE block-shear pattern: shear plane(s) down the member, tension
    # plane across to the free edge or between lines.
    key = cand.get("key", "block")
    title = ("GOVERNS  " if governs else "") + key + ": " + cand.get("description", "")
    svg, W, H, ML, MT, sx, sy, Lm = _shell(geom, title)

    kind, lines = _parse_key(key)
    rows = int(geom["bolts_per_line"])
    x_of = lambda ln: ML + (geom["edge_trans"] + ln * geom["gauge"]) * sx
    y_top = MT
    y_bot = MT + (geom["edge_end"] + (rows - 1) * geom["pitch"]) * sy
    x_near = ML
    x_far = ML + geom["w_conn"] * sx

    # block region + shear planes + tension plane
    if kind == "NEAR" and lines:
        xs = x_of(lines[0])
        svg.append(f'<rect x="{x_near:.1f}" y="{y_top:.1f}" '
                   f'width="{xs-x_near:.1f}" height="{y_bot-y_top:.1f}" {BLOCK}/>')
        svg.append(f'<line x1="{xs:.1f}" y1="{y_top:.1f}" x2="{xs:.1f}" '
                   f'y2="{y_bot:.1f}" {SHEAR}/>')
        svg.append(f'<line x1="{x_near:.1f}" y1="{y_bot:.1f}" x2="{xs:.1f}" '
                   f'y2="{y_bot:.1f}" {TENS}/>')
    elif kind == "FAR" and lines:
        xs = x_of(lines[0])
        svg.append(f'<rect x="{xs:.1f}" y="{y_top:.1f}" '
                   f'width="{x_far-xs:.1f}" height="{y_bot-y_top:.1f}" {BLOCK}/>')
        svg.append(f'<line x1="{xs:.1f}" y1="{y_top:.1f}" x2="{xs:.1f}" '
                   f'y2="{y_bot:.1f}" {SHEAR}/>')
        svg.append(f'<line x1="{xs:.1f}" y1="{y_bot:.1f}" x2="{x_far:.1f}" '
                   f'y2="{y_bot:.1f}" {TENS}/>')
    elif kind == "BETWEEN" and len(lines) == 2:
        xa, xb = x_of(lines[0]), x_of(lines[1])
        svg.append(f'<rect x="{xa:.1f}" y="{y_top:.1f}" '
                   f'width="{xb-xa:.1f}" height="{y_bot-y_top:.1f}" {BLOCK}/>')
        svg.append(f'<line x1="{xa:.1f}" y1="{y_top:.1f}" x2="{xa:.1f}" '
                   f'y2="{y_bot:.1f}" {SHEAR}/>')
        svg.append(f'<line x1="{xb:.1f}" y1="{y_top:.1f}" x2="{xb:.1f}" '
                   f'y2="{y_bot:.1f}" {SHEAR}/>')
        svg.append(f'<line x1="{xa:.1f}" y1="{y_bot:.1f}" x2="{xb:.1f}" '
                   f'y2="{y_bot:.1f}" {TENS}/>')

    svg += _holes(geom, ML, MT, sx, sy)

    ant = cand.get("Ant")
    planes = cand.get("planes")
    lab = []
    if ant is not None:
        lab.append(f"Ant={ant:,.0f}")
    if planes is not None:
        lab.append(f"{planes} shear plane(s)")
    if lab:
        svg.append(f'<text x="{W/2:.1f}" y="{H-6:.1f}" text-anchor="middle" '
                   f'{LBLO}>{" | ".join(lab)}</text>')
    svg.append("</svg>")
    return "".join(svg)


# ---------------------------------------------------------------------------
# Step 3: per-candidate shown-work text (the LEFT column)
# ---------------------------------------------------------------------------
# These mirror the resistance math in calc_net_fracture_paths /
# calc_block_shear_paths exactly, but format ONE candidate at a time so it can
# sit beside its own thumbnail. phi_u and area_mult are passed in from the
# panel so material/factor handling has a single source of truth.
PHI_U = 0.75


def format_net_candidate(p, U, Fu, phi_u=PHI_U, area_mult=1.0, governs=False):
    An = p["An_mm2"] * area_mult
    Ane = U * An
    Tr = phi_u * Ane * Fu / 1000.0
    tag = "  **<- GOVERNS**" if governs else ""
    mult = f"  (x{area_mult:g} parts)" if area_mult != 1.0 else ""
    lines = [
        f"**{p['description']}**{tag}",
        f"- Holes cut: {p['n_holes']}   Stagger add: {p['stagger_area_mm2']:,.0f} mm2",
        f"- An = Ag - holes + stagger = **{An:,.0f} mm2**{mult}",
        f"- Ane = U x An = {U:.2f} x {An:,.0f} = **{Ane:,.0f} mm2**",
        f"- Tr = {phi_u:.2f} x Ane x Fu / 1000 = **{Tr:,.1f} kN**",
    ]
    return "\n".join(lines)


def format_block_candidate(p, Fy, Fu, Ut, phi_u=PHI_U, area_mult=1.0, governs=False):
    planes = p["planes"]
    Ant = p["Ant"] * area_mult
    Agv = p["Agv"] * planes * area_mult
    if Fy > 460.0:
        Fbs = Fy
        fbs_txt = f"Fy = {Fy:.1f}"
    else:
        Fbs = (Fy + Fu) / 2.0
        fbs_txt = f"(Fy+Fu)/2 = {Fbs:.1f}"
    Rt = Ut * Ant * Fu
    Rv = 0.6 * Agv * Fbs
    Tr = phi_u * (Rt + Rv) / 1000.0
    tag = "  **<- GOVERNS**" if governs else ""
    lines = [
        f"**{p['key']}: {p['description']}**{tag}",
        f"- Net tension width = {p['tension_substitution']} = **{p['tension_width_mm']:.1f} mm**",
        f"- Ant = **{Ant:,.0f} mm2**   Agv ({planes} plane) = **{Agv:,.0f} mm2**",
        f"- Fbs = {fbs_txt}",
        f"- Rt = Ut x Ant x Fu = {Rt:,.0f} N",
        f"- Rv = 0.6 x Agv x Fbs = {Rv:,.0f} N",
        f"- Tr = {phi_u:.2f} x (Rt + Rv) / 1000 = **{Tr:,.1f} kN**",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Step 4: TWO independent displays. Net fracture and block shear are separate
# calculations - separate functions, separate loops. They share no loop and do
# not call each other. Each is invoked on its own from the panel.
# ---------------------------------------------------------------------------
def render_net_paths(paths, geom, *, U, Fu, phi_u=PHI_U, area_mult=1.0,
                     gov_desc=None):
    # Net-Section Fracture ONLY. Loops net paths and nothing else.
    import streamlit as st
    import streamlit.components.v1 as components

    st.subheader("Net-Section Fracture (Cl. 13.2a-iii) - each path")
    for p in paths:
        governs = (p.get("description") == gov_desc)
        left, right = st.columns([1, 1])
        with left:
            st.markdown(format_net_candidate(p, U, Fu, phi_u,
                                             area_mult, governs))
        with right:
            components.html(net_thumb(p, geom, governs), height=300)


def render_block_patterns(bs_pats, geom, *, Fy, Fu, Ut, phi_u=PHI_U,
                          area_mult=1.0, gov_key=None):
    # Block Shear ONLY. Loops block patterns and nothing else.
    import streamlit as st
    import streamlit.components.v1 as components

    st.subheader("Block Shear (Cl. 13.11) - each pattern")
    for p in bs_pats:
        governs = (p.get("key") == gov_key)
        left, right = st.columns([1, 1])
        with left:
            st.markdown(format_block_candidate(p, Fy, Fu, Ut, phi_u,
                                               area_mult, governs))
        with right:
            components.html(block_thumb(p, geom, governs), height=300)
