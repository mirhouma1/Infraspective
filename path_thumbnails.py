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
DIM = 'stroke="#345" stroke-width="0.9"'
DIMT = 'font-family="Helvetica,Arial,sans-serif" font-size="9" fill="#345"'
SUBT = 'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#555"'


def _hdim(x1, x2, y, label):
    # Horizontal dimension line with end ticks and centred label above it.
    return [
        f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" {DIM}/>',
        f'<line x1="{x1:.1f}" y1="{y-3:.1f}" x2="{x1:.1f}" y2="{y+3:.1f}" {DIM}/>',
        f'<line x1="{x2:.1f}" y1="{y-3:.1f}" x2="{x2:.1f}" y2="{y+3:.1f}" {DIM}/>',
        f'<text x="{(x1+x2)/2:.1f}" y="{y-3:.1f}" text-anchor="middle" {DIMT}>{label}</text>',
    ]


def _vdim(x, y1, y2, label):
    # Vertical dimension line with end ticks and label rotated alongside.
    return [
        f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" {DIM}/>',
        f'<line x1="{x-3:.1f}" y1="{y1:.1f}" x2="{x+3:.1f}" y2="{y1:.1f}" {DIM}/>',
        f'<line x1="{x-3:.1f}" y1="{y2:.1f}" x2="{x+3:.1f}" y2="{y2:.1f}" {DIM}/>',
        f'<text x="{x+4:.1f}" y="{(y1+y2)/2:.1f}" {DIMT}>{label}</text>',
    ]


def _frame(geom: Dict) -> Tuple[float, float, float, float, float, float, float]:
    # Returns (W, H, ML, MT, sx, sy, Lmember).
    w = float(geom["w_conn"])
    rows = int(geom["bolts_per_line"])
    Lmember = geom["edge_end"] + (rows - 1) * geom["pitch"] + geom["edge_end"]
    DW, DH = 170.0, 230.0
    sx = DW / w if w > 0 else 1.0
    sy = DH / Lmember if Lmember > 0 else 1.0
    ML, MT, MR, MB = 46.0, 46.0, 50.0, 36.0
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
        f'<text x="{W/2:.1f}" y="14" text-anchor="middle" {TITLE}>{title}</text>',
    ]
    sec = geom.get("section_label")
    if sec:
        body.append(
            f'<text x="{W/2:.1f}" y="26" text-anchor="middle" {SUBT}>{sec}</text>'
        )
    body.append(
        f'<rect x="{ML:.1f}" y="{MT:.1f}" width="{w*sx:.1f}" '
        f'height="{Lm*sy:.1f}" {EL}/>'
    )
    # connected width dimension across the top of the element
    body += _hdim(ML, ML + w * sx, MT - 8.0, f"w = {w:g} mm")
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

    # case-relevant dimensions: gauge g between lines cut by the path,
    # pitch/stagger s only when the path actually staggers
    if sel and len(sel) >= 2:
        (l0, r0), (l1, r1) = sel[0], sel[1]
        x0, y0 = _xy(geom, ML, MT, sx, sy, l0, r0)
        x1, y1 = _xy(geom, ML, MT, sx, sy, l1, r1)
        if l0 != l1:
            svg += _hdim(x0, x1, MT + Lm * sy + 12.0, f"g = {geom['gauge']:g}")
        if r0 != r1 and int(cand.get("n_staggers", 0)) > 0:
            svg += _vdim(ML + geom["w_conn"] * sx + 10.0, min(y0, y1),
                         max(y0, y1), f"s = {geom['pitch']:g}")
    elif int(geom.get("n_lines", 1)) > 1:
        xa, _ = _xy(geom, ML, MT, sx, sy, 0, 0)
        xb, _ = _xy(geom, ML, MT, sx, sy, 1, 0)
        svg += _hdim(xa, xb, MT + Lm * sy + 12.0, f"g = {geom['gauge']:g}")

    An = cand.get("An_mm2")
    foot = []
    if An is not None:
        foot.append(f"An = {An:,.0f} mm2")
    t = cand.get("t_mm")
    d_eff = cand.get("d_eff_mm")
    if t:
        foot.append(f"t = {float(t):g}")
    if d_eff:
        foot.append(f"d_eff = {float(d_eff):g}")
    if foot:
        svg.append(f'<text x="{W/2:.1f}" y="{H-6:.1f}" text-anchor="middle" '
                   f'{LBL}>{" | ".join(foot)}</text>')
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

    # case-relevant dimensions: shear length Lv down the shear plane,
    # net tension width Lnt along the tension plane
    Lv = cand.get("Lv_mm")
    Lnt = cand.get("tension_width_mm")
    if lines:
        xs = x_of(lines[0])
        if Lv:
            svg += _vdim(x_far + 10.0, y_top, y_bot, f"Lv = {float(Lv):g}")
        if Lnt:
            if kind == "NEAR":
                svg += _hdim(x_near, xs, y_bot + 12.0, f"Lnt = {float(Lnt):g}")
            elif kind == "FAR":
                svg += _hdim(xs, x_far, y_bot + 12.0, f"Lnt = {float(Lnt):g}")
            elif kind == "BETWEEN" and len(lines) == 2:
                svg += _hdim(x_of(lines[0]), x_of(lines[1]), y_bot + 12.0,
                             f"Lnt = {float(Lnt):g}")

    ant = cand.get("Ant")
    planes = cand.get("planes")
    lab = []
    if ant is not None:
        lab.append(f"Ant={ant:,.0f}")
    if planes is not None:
        lab.append(f"{planes} shear plane(s)")
    t = cand.get("t_mm")
    if t:
        lab.append(f"t = {float(t):g}")
    if lab:
        svg.append(f'<text x="{W/2:.1f}" y="{H-6:.1f}" text-anchor="middle" '
                   f'{LBLO}>{" | ".join(lab)}</text>')
    svg.append("</svg>")
    return "".join(svg)


# ---------------------------------------------------------------------------
# Unified calculation + diagram cards
# ---------------------------------------------------------------------------
# A calculation path is rendered ONCE as one HTML grid:
#   left  = complete numerical calculation and result
#   right = the matching path/pattern SVG
# This deliberately avoids st.columns(), because Streamlit stacks columns on
# narrow screens. The CSS grid below remains left/right on phones as requested.

from html import escape

PHI_U = 0.75


_CARD_CSS = r"""
<style>
.tm-path-stack {
    width: 100%;
    margin: 0;
    padding: 0;
}
.tm-path-card {
    display: block;
    width: 100%;
    box-sizing: border-box;
    margin: 0 0 18px 0;
    padding: 18px;
    border: 1px solid #d7e2f4;
    border-left: 5px solid #315fd6;
    border-radius: 14px;
    background: #ffffff;
    box-shadow: 0 4px 16px rgba(28, 48, 88, 0.07);
    color: #101828;
}
.tm-path-card.tm-governing {
    border-color: #315fd6;
    border-left-color: #315fd6;
    background: #f8fbff;
}
.tm-calc-pane {
    min-width: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    font-size: 15px;
    line-height: 1.48;
}
.tm-path-title {
    margin: 0 0 10px 0;
    font-size: 18px;
    line-height: 1.25;
    font-weight: 800;
    color: #2449ad;
    overflow-wrap: anywhere;
}
.tm-governs-badge {
    display: inline-block;
    margin-left: 8px;
    padding: 3px 8px;
    border-radius: 999px;
    background: #315fd6;
    color: white;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.04em;
    vertical-align: 2px;
}
.tm-step {
    margin: 7px 0;
    overflow-wrap: anywhere;
}
.tm-step-label {
    font-weight: 700;
}
.tm-substitution {
    display: block;
    margin-top: 2px;
    color: #344054;
}
.tm-result {
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: 10px;
    background: #eef4ff;
    border: 1px solid #c8d8ff;
    font-weight: 700;
}
.tm-result strong {
    display: inline-block;
    margin-left: 6px;
    font-size: 20px;
    color: #0f1f49;
}
.tm-figure-pane {
    margin: 12px auto 0 auto;
    max-width: 280px;
    border-radius: 10px;
    overflow: hidden;
    background: white;
}
.tm-figure-pane svg {
    display: block;
    margin: 0 auto;
    width: 100% !important;
    height: auto !important;
    max-height: 340px;
}
@media (max-width: 620px) {
    .tm-path-card {
        padding: 10px;
        margin-bottom: 12px;
        border-radius: 10px;
    }
    .tm-figure-pane {
        max-width: 230px;
    }
    .tm-calc-pane {
        font-size: 12px;
        line-height: 1.38;
    }
    .tm-path-title {
        font-size: 14px;
        margin-bottom: 7px;
    }
    .tm-governs-badge {
        margin-left: 4px;
        padding: 2px 5px;
        font-size: 9px;
    }
    .tm-step {
        margin: 5px 0;
    }
    .tm-result {
        margin-top: 8px;
        padding: 7px 8px;
    }
    .tm-result strong {
        display: block;
        margin: 2px 0 0 0;
        font-size: 16px;
    }
    .tm-figure-pane svg {
        max-height: 300px;
    }
}
</style>
"""


def _fmt(value, decimals=1):
    return f"{value:,.{decimals}f}"


def _step(label: str, formula: str, substitution: str = "") -> str:
    sub = (
        f'<span class="tm-substitution">{substitution}</span>'
        if substitution else ""
    )
    return (
        '<div class="tm-step">'
        f'<span class="tm-step-label">{label}:</span> {formula}{sub}'
        '</div>'
    )


def _net_card(p, geom, U, Fu, phi_u, area_mult, governs):
    d_eff = float(p.get("d_eff_mm", 0.0))
    t = float(p.get("t_mm", 0.0))
    n_holes = int(p.get("n_holes", 0))
    Ag = float(p.get("Ag_mm2", 0.0)) * area_mult
    hole_ded = float(p.get("hole_deduction_mm2", 0.0)) * area_mult
    stag_len = float(p.get("stagger_term", 0.0))
    stag_area = float(p.get("stagger_area_mm2", 0.0)) * area_mult
    An = float(p["An_mm2"]) * area_mult
    Ane = U * An
    Tr = phi_u * Ane * Fu / 1000.0

    badge = '<span class="tm-governs-badge">GOVERNS</span>' if governs else ""
    multiplier = (
        f"; areas multiplied by {area_mult:g} connected parts"
        if area_mult != 1.0 else ""
    )

    steps = []
    hole_dia = float(geom.get("hole_dia", d_eff))
    allowance = d_eff - hole_dia
    steps.append(_step(
        "Effective hole diameter",
        "d<sub>eff</sub> = d<sub>h</sub> + allowance",
        f"d<sub>eff</sub> = {_fmt(hole_dia, 2)} + {_fmt(allowance, 2)} "
        f"= <strong>{_fmt(d_eff, 2)} mm</strong>",
    ))
    part_factor = f"{area_mult:g} × " if area_mult != 1.0 else ""
    steps.append(_step(
        "Gross area basis",
        "A<sub>g,total</sub> = connected parts × A<sub>g,part</sub>"
        if area_mult != 1.0 else "A<sub>g</sub> = member gross area",
        f"A<sub>g</sub> = <strong>{_fmt(Ag)} mm²</strong>",
    ))
    steps.append(_step(
        "Hole deduction",
        "ΔA<sub>h</sub> = connected parts × n<sub>h</sub> × d<sub>eff</sub> × t"
        if area_mult != 1.0 else
        "ΔA<sub>h</sub> = n<sub>h</sub> × d<sub>eff</sub> × t",
        f"ΔA<sub>h</sub> = {part_factor}{n_holes} × {_fmt(d_eff, 2)} × {_fmt(t, 3)} "
        f"= <strong>{_fmt(hole_ded)} mm²</strong>",
    ))

    segments = p.get("stagger_segments", [])
    if segments:
        pieces = []
        for seg in segments:
            s_mm = float(seg.get("s_mm", 0.0))
            g_mm = float(seg.get("g_mm", 0.0))
            add = float(seg.get("addition_mm", 0.0))
            pieces.append(
                f"{_fmt(s_mm)}²/(4 × {_fmt(g_mm)}) = {_fmt(add, 2)} mm"
            )
        steps.append(_step(
            "Stagger-length addition",
            "Σ(s²/4g)",
            " + ".join(pieces) + f" = <strong>{_fmt(stag_len, 2)} mm</strong>",
        ))
        steps.append(_step(
            "Stagger-area addition",
            "ΔA<sub>s</sub> = connected parts × Σ(s²/4g) × t"
            if area_mult != 1.0 else
            "ΔA<sub>s</sub> = Σ(s²/4g) × t",
            f"ΔA<sub>s</sub> = {part_factor}{_fmt(stag_len, 2)} × {_fmt(t, 3)} "
            f"= <strong>{_fmt(stag_area)} mm²</strong>",
        ))
    else:
        steps.append(_step(
            "Stagger-area addition",
            "ΔA<sub>s</sub> = 0",
            "Straight path; no stagger addition.",
        ))

    steps.append(_step(
        "Net area",
        "A<sub>n</sub> = A<sub>g</sub> − ΔA<sub>h</sub> + ΔA<sub>s</sub>",
        f"A<sub>n</sub> = {_fmt(Ag)} − {_fmt(hole_ded)} + {_fmt(stag_area)} "
        f"= <strong>{_fmt(An)} mm²</strong>",
    ))
    steps.append(_step(
        "Effective net area",
        "A<sub>ne</sub> = U × A<sub>n</sub>",
        f"A<sub>ne</sub> = {_fmt(U, 2)} × {_fmt(An)} "
        f"= <strong>{_fmt(Ane)} mm²</strong>",
    ))

    thumb_data = dict(p)
    thumb_data["An_mm2"] = An
    svg = net_thumb(thumb_data, geom, governs)

    result = (
        '<div class="tm-result">Fracture resistance '
        f'<strong>{_fmt(Tr)} kN</strong>'
        '<span class="tm-substitution">'
        f'T<sub>r</sub> = {_fmt(phi_u, 2)} × {_fmt(Ane)} × {_fmt(Fu)} ÷ 1000'
        '</span></div>'
    )

    return (
        f'<div class="tm-path-card{" tm-governing" if governs else ""}">'
        '<div class="tm-calc-pane">'
        f'<div class="tm-path-title">{escape(str(p.get("description", "Net path")))}{badge}</div>'
        f'{"".join(steps)}{result}'
        '</div>'
        f'<div class="tm-figure-pane">{svg}</div>'
        '</div>'
    )


def _block_card(p, geom, Fy, Fu, Ut, phi_u, area_mult, governs):
    planes = int(p["planes"])
    Ant = float(p["Ant"]) * area_mult
    Agv = float(p["Agv"]) * planes * area_mult
    if Fy > 460.0:
        Fbs = Fy
        fbs_formula = "F<sub>bs</sub> = F<sub>y</sub>"
        fbs_sub = f"F<sub>bs</sub> = <strong>{_fmt(Fbs)} MPa</strong>"
    else:
        Fbs = (Fy + Fu) / 2.0
        fbs_formula = "F<sub>bs</sub> = (F<sub>y</sub> + F<sub>u</sub>)/2"
        fbs_sub = (
            f"F<sub>bs</sub> = ({_fmt(Fy)} + {_fmt(Fu)})/2 "
            f"= <strong>{_fmt(Fbs)} MPa</strong>"
        )

    Rt = Ut * Ant * Fu
    Rv = 0.6 * Agv * Fbs
    Tr = phi_u * (Rt + Rv) / 1000.0
    badge = '<span class="tm-governs-badge">GOVERNS</span>' if governs else ""

    steps = []
    steps.append(_step(
        "Net tension width",
        escape(str(p.get("tension_formula", "Lnt"))),
        f'{escape(str(p.get("tension_substitution", "")))} '
        f'= <strong>{_fmt(float(p["tension_width_mm"]))} mm</strong>',
    ))
    t = float(p.get("t_mm", 0.0))
    Lnt = float(p.get("tension_width_mm", 0.0))
    Lv = float(p.get("Lv_mm", 0.0))
    part_factor = f"{area_mult:g} × " if area_mult != 1.0 else ""
    steps.append(_step(
        "Net tension area",
        "A<sub>nt</sub> = connected parts × L<sub>nt</sub> × t"
        if area_mult != 1.0 else "A<sub>nt</sub> = L<sub>nt</sub> × t",
        f"A<sub>nt</sub> = {part_factor}{_fmt(Lnt)} × {_fmt(t, 3)} "
        f"= <strong>{_fmt(Ant)} mm²</strong>",
    ))
    steps.append(_step(
        "Gross shear area",
        "A<sub>gv</sub> = connected parts × shear planes × L<sub>v</sub> × t"
        if area_mult != 1.0 else
        "A<sub>gv</sub> = shear planes × L<sub>v</sub> × t",
        f"A<sub>gv</sub> = {part_factor}{planes} × {_fmt(Lv)} × {_fmt(t, 3)} "
        f"= <strong>{_fmt(Agv)} mm²</strong>",
    ))
    steps.append(_step("Shear strength basis", fbs_formula, fbs_sub))
    steps.append(_step(
        "Tension term",
        "R<sub>t</sub> = U<sub>t</sub> × A<sub>nt</sub> × F<sub>u</sub>",
        f"R<sub>t</sub> = {_fmt(Ut, 2)} × {_fmt(Ant)} × {_fmt(Fu)} "
        f"= <strong>{_fmt(Rt, 0)} N</strong>",
    ))
    steps.append(_step(
        "Shear term",
        "R<sub>v</sub> = 0.6 × A<sub>gv</sub> × F<sub>bs</sub>",
        f"R<sub>v</sub> = 0.6 × {_fmt(Agv)} × {_fmt(Fbs)} "
        f"= <strong>{_fmt(Rv, 0)} N</strong>",
    ))

    thumb_data = dict(p)
    thumb_data["Ant"] = Ant
    svg = block_thumb(thumb_data, geom, governs)

    result = (
        '<div class="tm-result">Block-shear resistance '
        f'<strong>{_fmt(Tr)} kN</strong>'
        '<span class="tm-substitution">'
        f'T<sub>r</sub> = {_fmt(phi_u, 2)} × ({_fmt(Rt, 0)} + {_fmt(Rv, 0)}) ÷ 1000'
        '</span></div>'
    )

    title = f'{p.get("key", "")}: {p.get("description", "Block-shear pattern")}'
    return (
        f'<div class="tm-path-card{" tm-governing" if governs else ""}">'
        '<div class="tm-calc-pane">'
        f'<div class="tm-path-title">{escape(str(title))}{badge}</div>'
        f'{"".join(steps)}{result}'
        '</div>'
        f'<div class="tm-figure-pane">{svg}</div>'
        '</div>'
    )


def _render_html_cards(html: str, fallback_height: int) -> None:
    import streamlit as st

    full_html = _CARD_CSS + f'<div class="tm-path-stack">{html}</div>'
    # st.html renders in the main document and sizes itself automatically.
    # Keep a components fallback for older Streamlit releases.
    if hasattr(st, "html"):
        st.html(full_html)
    else:
        import streamlit.components.v1 as components
        components.html(full_html, height=fallback_height, scrolling=False)


def render_net_paths(paths, geom, *, U, Fu, phi_u=PHI_U, area_mult=1.0,
                     gov_desc=None):
    cards = []
    for p in paths:
        governs = p.get("description") == gov_desc
        cards.append(_net_card(p, geom, U, Fu, phi_u, area_mult, governs))
    _render_html_cards("".join(cards), max(520, 610 * len(cards)))


def render_block_patterns(bs_pats, geom, *, Fy, Fu, Ut, phi_u=PHI_U,
                          area_mult=1.0, gov_key=None):
    cards = []
    for p in bs_pats:
        governs = p.get("key") == gov_key
        cards.append(_block_card(p, geom, Fy, Fu, Ut, phi_u, area_mult, governs))
    _render_html_cards("".join(cards), max(520, 610 * len(cards)))
