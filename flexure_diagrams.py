"""
flexure_diagrams.py
───────────────────
SVG diagram generators for the CSA S16 Flexure Calculator (app.py).

Public API
──────────
    i_section_stress_svg(section_class, mode="stress") -> str
    beam_elevation_svg(braced, load_type) -> str
    ltb_curve_svg(L_list, Mr_list, phiMp, phiMy, section_class) -> str
    shear_fs_curve_svg(Fy, h_over_w_actual, Fs_actual, stiffened, kv) -> str

All functions return raw SVG strings ready for `st.markdown(svg, unsafe_allow_html=True)`.
Palette is tuned to match the existing _theme.py dark-navy / blueprint look.
"""

from __future__ import annotations
import math
from typing import List, Optional


C_PANEL_BG = "#0F172A"
C_BORDER   = "#1E3A8A"
C_GRID     = "#1E40AF55"
C_ACCENT   = "#2563EB"
C_TEXT     = "#E2E8F0"
C_MUTED    = "#94A3B8"
C_GREEN    = "#10B981"
C_YELLOW   = "#F59E0B"
C_RED      = "#EF4444"
C_PURPLE   = "#A78BFA"
C_STEEL    = "#60A5FA"

_CLASS_COLOR = {1: C_GREEN, 2: C_ACCENT, 3: C_YELLOW, 4: C_RED}


def _wrap(svg_inner: str, w: int, h: int) -> str:
    return (
        f'<div style="background:{C_PANEL_BG};border:1px solid {C_BORDER};'
        f'border-radius:8px;padding:10px;display:flex;justify-content:center;">'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">{svg_inner}</svg></div>'
    )


def i_section_stress_svg(section_class: int, mode: str = "stress") -> str:
    """Annotated I-section cross-section with plastic/elastic stress overlay."""
    W, H = 220, 230
    bf, tf, hw, tw = 96, 10, 140, 7
    cx = W / 2
    top = 24
    plastic = section_class <= 2
    label_color = _CLASS_COLOR.get(section_class, C_MUTED)

    parts: List[str] = []

    # Web + flanges
    parts.append(f'<rect x="{cx - tw/2}" y="{top + tf}" width="{tw}" height="{hw}" '
                 f'fill="#334155" stroke="{C_BORDER}" stroke-width="1"/>')
    parts.append(f'<rect x="{cx - bf/2}" y="{top}" width="{bf}" height="{tf}" '
                 f'fill="#475569" stroke="{C_BORDER}" stroke-width="1"/>')
    parts.append(f'<rect x="{cx - bf/2}" y="{top + tf + hw}" width="{bf}" height="{tf}" '
                 f'fill="#475569" stroke="{C_BORDER}" stroke-width="1"/>')

    if mode == "stress":
        comp = "#EF4149AA"
        tens = "#10B981AA"
        if plastic:
            parts.append(f'<rect x="{cx - bf/2}" y="{top}" width="{bf}" height="{tf + hw/2}" '
                         f'fill="{comp}" opacity="0.55"/>')
            parts.append(f'<rect x="{cx - bf/2}" y="{top + tf + hw/2}" width="{bf}" '
                         f'height="{hw/2 + tf}" fill="{tens}" opacity="0.55"/>')
            mode_label = "Plastic stress block (\u00b1Fy)"
        else:
            parts.append(
                f'<polygon points="{cx-bf/2},{top} {cx+bf/2},{top} {cx},{top+tf+hw/2}" '
                f'fill="{comp}" opacity="0.40"/>'
            )
            parts.append(
                f'<polygon points="{cx-bf/2},{top+tf+hw+tf} {cx+bf/2},{top+tf+hw+tf} '
                f'{cx},{top+tf+hw/2}" fill="{tens}" opacity="0.40"/>'
            )
            mode_label = "Elastic triangular stress (\u00b1Fy at extreme fibre)"
        # Neutral axis
        na_y = top + tf + hw / 2
        parts.append(f'<line x1="{cx-bf/2-12}" y1="{na_y}" x2="{cx+bf/2+12}" y2="{na_y}" '
                     f'stroke="#fff" stroke-width="1.4" stroke-dasharray="4,3"/>')
        parts.append(f'<text x="{cx-bf/2-16}" y="{na_y-6}" fill="#EF4149" font-size="10">C</text>')
        parts.append(f'<text x="{cx-bf/2-16}" y="{na_y+13}" fill="#10B981" font-size="10">T</text>')
        parts.append(f'<text x="{cx+bf/2+14}" y="{na_y+4}" fill="{C_MUTED}" font-size="9">NA</text>')
    else:
        mode_label = "Cross-section"

    # Dimension marks
    parts.append(f'<text x="{cx-bf/2-22}" y="{top+tf/2+3}" fill="{C_MUTED}" font-size="9">tf</text>')
    parts.append(f'<text x="{cx+bf/2+8}" y="{top+tf+hw/2+3}" fill="{C_MUTED}" font-size="9">d</text>')
    parts.append(f'<text x="{cx}" y="{top-6}" fill="{C_MUTED}" font-size="9" text-anchor="middle">b</text>')

    # Class label
    desc = {1: "Plastic", 2: "Compact", 3: "Non-Compact", 4: "Slender"}.get(section_class, "")
    parts.append(
        f'<text x="{cx}" y="{H-22}" text-anchor="middle" fill="{label_color}" '
        f'font-size="13" font-weight="700">Class {section_class} \u2014 {desc}</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{H-6}" text-anchor="middle" fill="{C_MUTED}" '
        f'font-size="10">{mode_label}</text>'
    )
    return _wrap("".join(parts), W, H)


def beam_elevation_svg(braced: bool, load_type: str = "udl") -> str:
    """Beam elevation with brace marks (if braced) and qualitative moment diagram."""
    W, H = 380, 170
    x0, x1 = 35, W - 35
    by = 70
    L = x1 - x0

    parts: List[str] = []
    # Beam
    parts.append(f'<rect x="{x0}" y="{by-6}" width="{L}" height="12" fill="#475569" '
                 f'stroke="{C_BORDER}" stroke-width="1" rx="2"/>')

    # Arrow marker
    parts.append(
        f'<defs><marker id="arr" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">'
        f'<path d="M0,0 L6,3 L0,6 Z" fill="{C_STEEL}"/></marker></defs>'
    )

    # Loads
    if load_type == "udl":
        parts.append(f'<line x1="{x0}" y1="{by-22}" x2="{x1}" y2="{by-22}" stroke="{C_STEEL}" stroke-width="1"/>')
        for i in range(8):
            xa = x0 + (i + 0.5) * L / 8
            parts.append(f'<line x1="{xa}" y1="{by-22}" x2="{xa}" y2="{by-8}" '
                         f'stroke="{C_STEEL}" stroke-width="1.4" marker-end="url(#arr)"/>')
        parts.append(f'<text x="{(x0+x1)/2}" y="{by-28}" text-anchor="middle" fill="{C_STEEL}" '
                     f'font-size="10">w (UDL)</text>')
        m_pts = (f"{x0},{by} {x0+L*0.25},{by+30} {(x0+x1)/2},{by+45} "
                 f"{x0+L*0.75},{by+30} {x1},{by}")
    else:
        xa = (x0 + x1) / 2
        parts.append(f'<line x1="{xa}" y1="{by-26}" x2="{xa}" y2="{by-8}" '
                     f'stroke="{C_STEEL}" stroke-width="2" marker-end="url(#arr)"/>')
        parts.append(f'<text x="{xa+6}" y="{by-30}" fill="{C_STEEL}" font-size="10">P</text>')
        m_pts = f"{x0},{by} {(x0+x1)/2},{by+45} {x1},{by}"

    # Brace marks
    braces = [x0, x0 + L/3, x0 + 2*L/3, x1] if braced else [x0, x1]
    for bx in braces:
        parts.append(f'<line x1="{bx}" y1="{by-7}" x2="{bx}" y2="{by+22}" '
                     f'stroke="{C_GREEN}" stroke-width="1.6"/>')
        parts.append(f'<line x1="{bx-7}" y1="{by+22}" x2="{bx+7}" y2="{by+22}" '
                     f'stroke="{C_GREEN}" stroke-width="1.6"/>')

    # Moment diagram (dashed)
    parts.append(f'<polyline points="{m_pts}" fill="none" stroke="{C_ACCENT}" '
                 f'stroke-width="1.8" stroke-dasharray="5,3" opacity="0.85"/>')
    parts.append(f'<text x="{(x0+x1)/2+8}" y="{by+58}" fill="{C_ACCENT}" '
                 f'font-size="10">Moment diagram</text>')

    # Supports
    parts.append(f'<polygon points="{x0},{by+6} {x0-9},{by+22} {x0+9},{by+22}" fill="{C_MUTED}"/>')
    parts.append(f'<polygon points="{x1},{by+6} {x1-9},{by+22} {x1+9},{by+22}" fill="{C_MUTED}"/>')
    parts.append(f'<line x1="{x0-12}" y1="{by+22}" x2="{x1+12}" y2="{by+22}" '
                 f'stroke="{C_MUTED}" stroke-width="1"/>')

    # Caption
    cap = ("Laterally Supported (intermediate braces shown)" if braced
           else "Laterally Unsupported (ends only)")
    cap += " \u2014 " + ("UDL" if load_type == "udl" else "Midspan Point Load")
    parts.append(f'<text x="{W/2}" y="{H-8}" text-anchor="middle" fill="{C_MUTED}" '
                 f'font-size="11">{cap}</text>')

    return _wrap("".join(parts), W, H)


def ltb_curve_svg(
    L_list: List[float],
    Mr_list: List[float],
    phiMp: float,
    phiMy: float,
    section_class: int,
    L_current_mm: Optional[float] = None,
    Mr_current: Optional[float] = None,
) -> str:
    """Mr (kN·m) vs unbraced length L (mm) curve with φMp / φMy reference lines."""
    if not L_list or not Mr_list or len(L_list) != len(Mr_list):
        return ""
    W, H = 380, 200
    pad_l, pad_r, pad_t, pad_b = 50, 18, 16, 38
    iW = W - pad_l - pad_r
    iH = H - pad_t - pad_b

    Lmax = max(L_list)
    Mmax = max(max(Mr_list), phiMp, phiMy) * 1.08

    def sx(L: float) -> float:
        return pad_l + (L / Lmax) * iW

    def sy(M: float) -> float:
        return pad_t + iH - (M / Mmax) * iH

    parts: List[str] = []
    # Grid
    for f in (0.25, 0.5, 0.75, 1.0):
        parts.append(f'<line x1="{pad_l}" y1="{sy(Mmax*f)}" x2="{W-pad_r}" '
                     f'y2="{sy(Mmax*f)}" stroke="{C_GRID}" stroke-width="0.6"/>')

    # phiMp
    parts.append(f'<line x1="{pad_l}" y1="{sy(phiMp)}" x2="{W-pad_r}" y2="{sy(phiMp)}" '
                 f'stroke="{C_GREEN}" stroke-width="1.2" stroke-dasharray="6,3"/>')
    parts.append(f'<text x="{W-pad_r-2}" y="{sy(phiMp)-4}" fill="{C_GREEN}" '
                 f'font-size="10" text-anchor="end">\u03c6Mp = {phiMp:.0f}</text>')
    # phiMy (only show separately if different)
    if section_class >= 3 or abs(phiMy - phiMp) > 1e-3:
        parts.append(f'<line x1="{pad_l}" y1="{sy(phiMy)}" x2="{W-pad_r}" y2="{sy(phiMy)}" '
                     f'stroke="{C_YELLOW}" stroke-width="1" stroke-dasharray="6,3"/>')
        parts.append(f'<text x="{W-pad_r-2}" y="{sy(phiMy)+12}" fill="{C_YELLOW}" '
                     f'font-size="10" text-anchor="end">\u03c6My = {phiMy:.0f}</text>')

    # 0.67 Mref threshold marker (where curve transitions inelastic ↔ elastic)
    Mref = phiMp / 0.9 if section_class <= 2 else phiMy / 0.9
    thresh = 0.67 * Mref * 0.9  # show factored threshold
    parts.append(f'<line x1="{pad_l}" y1="{sy(thresh)}" x2="{W-pad_r}" y2="{sy(thresh)}" '
                 f'stroke="{C_PURPLE}" stroke-width="0.8" stroke-dasharray="2,3"/>')

    # Curve
    pts = " ".join(f"{sx(L):.1f},{sy(M):.1f}" for L, M in zip(L_list, Mr_list))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{C_ACCENT}" stroke-width="2.2"/>')

    # Current point marker
    if L_current_mm is not None and Mr_current is not None and L_current_mm <= Lmax:
        cx_, cy_ = sx(L_current_mm), sy(Mr_current)
        parts.append(f'<circle cx="{cx_}" cy="{cy_}" r="5" fill="{C_RED}" '
                     f'stroke="#fff" stroke-width="1.5"/>')
        parts.append(f'<text x="{cx_+8}" y="{cy_-8}" fill="{C_RED}" font-size="10">'
                     f'L={L_current_mm:.0f}mm</text>')

    # Axes
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{H-pad_b}" '
                 f'stroke="{C_MUTED}" stroke-width="1"/>')
    parts.append(f'<line x1="{pad_l}" y1="{H-pad_b}" x2="{W-pad_r}" y2="{H-pad_b}" '
                 f'stroke="{C_MUTED}" stroke-width="1"/>')

    # Tick labels — x
    for f in (0.0, 0.25, 0.5, 0.75, 1.0):
        xt = sx(Lmax * f)
        parts.append(f'<text x="{xt}" y="{H-pad_b+14}" text-anchor="middle" '
                     f'fill="{C_MUTED}" font-size="9">{Lmax*f:.0f}</text>')
    # Tick labels — y
    for f in (0.0, 0.5, 1.0):
        yt = sy(Mmax * f)
        parts.append(f'<text x="{pad_l-4}" y="{yt+3}" text-anchor="end" '
                     f'fill="{C_MUTED}" font-size="9">{Mmax*f:.0f}</text>')

    parts.append(f'<text x="{W/2}" y="{H-4}" text-anchor="middle" fill="{C_TEXT}" '
                 f'font-size="11">Unbraced length L (mm)</text>')
    parts.append(f'<text x="14" y="{H/2}" text-anchor="middle" fill="{C_TEXT}" '
                 f'font-size="11" transform="rotate(-90, 14, {H/2})">'
                 f'Mr (kN\u00b7m)</text>')

    return _wrap("".join(parts), W, H)


def shear_fs_curve_svg(
    Fy: float,
    h_over_w_actual: float,
    Fs_actual: float,
    stiffened: bool,
    kv: Optional[float] = None,
) -> str:
    """Fs (MPa) vs h/w curve with the actual operating point marked."""
    W, H = 380, 200
    pad_l, pad_r, pad_t, pad_b = 50, 18, 16, 38
    iW = W - pad_l - pad_r
    iH = H - pad_t - pad_b

    sqFy = math.sqrt(Fy)
    rmax = 250.0
    Fsmax = 0.66 * Fy

    def calc_Fs(r: float) -> float:
        if r <= 0:
            return Fsmax
        if not stiffened:
            l1 = 1014.0 / sqFy
            l2 = 1435.0 / sqFy
            if r <= l1:
                return 0.66 * Fy
            elif r <= l2:
                return 670.0 * sqFy / r
            else:
                return 961200.0 / (r ** 2)
        kvv = kv if kv else 5.34
        Fcri = 290.0 * math.sqrt(Fy * kvv) / r
        Fcre = 180000.0 * kvv / (r ** 2)
        l1 = 439.0 * math.sqrt(kvv / Fy)
        l2 = 502.0 * math.sqrt(kvv / Fy)
        l3 = 621.0 * math.sqrt(kvv / Fy)
        ka = 1.0 / math.sqrt(1.0 + (r / 100.0) ** 2)
        if r <= l1:
            return 0.66 * Fy
        elif r <= l2:
            return Fcri
        elif r <= l3:
            return Fcri + ka * (0.5 * Fy - 0.866 * Fcri)
        else:
            return Fcre + ka * (0.5 * Fy - 0.866 * Fcre)

    def sx(r: float) -> float:
        return pad_l + (r / rmax) * iW

    def sy(F: float) -> float:
        return pad_t + iH - (max(0.0, F) / Fsmax) * iH

    parts: List[str] = []
    for f in (0.25, 0.5, 0.75, 1.0):
        parts.append(f'<line x1="{pad_l}" y1="{sy(Fsmax*f)}" x2="{W-pad_r}" '
                     f'y2="{sy(Fsmax*f)}" stroke="{C_GRID}" stroke-width="0.6"/>')

    # 0.66Fy plateau label
    parts.append(f'<line x1="{pad_l}" y1="{sy(Fsmax)}" x2="{W-pad_r}" y2="{sy(Fsmax)}" '
                 f'stroke="{C_GREEN}" stroke-width="1" stroke-dasharray="5,3"/>')
    parts.append(f'<text x="{pad_l+6}" y="{sy(Fsmax)-4}" fill="{C_GREEN}" '
                 f'font-size="10">0.66 Fy = {Fsmax:.0f} MPa</text>')

    # Curve
    steps = 140
    pts: List[str] = []
    for i in range(steps + 1):
        r = (i / steps) * rmax
        if r == 0:
            r = 0.001
        F = min(Fsmax, max(0.0, calc_Fs(r)))
        pts.append(f"{sx(r):.1f},{sy(F):.1f}")
    parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{C_ACCENT}" '
                 f'stroke-width="2.2"/>')

    # Operating point
    if h_over_w_actual <= rmax and Fs_actual >= 0:
        cx_, cy_ = sx(min(h_over_w_actual, rmax)), sy(Fs_actual)
        parts.append(f'<circle cx="{cx_}" cy="{cy_}" r="5" fill="{C_RED}" '
                     f'stroke="#fff" stroke-width="1.5"/>')
        parts.append(f'<text x="{cx_+8}" y="{cy_-8}" fill="{C_RED}" font-size="10">'
                     f'h/w={h_over_w_actual:.1f}, Fs={Fs_actual:.0f}</text>')

    # Axes
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{H-pad_b}" '
                 f'stroke="{C_MUTED}" stroke-width="1"/>')
    parts.append(f'<line x1="{pad_l}" y1="{H-pad_b}" x2="{W-pad_r}" y2="{H-pad_b}" '
                 f'stroke="{C_MUTED}" stroke-width="1"/>')

    # Tick labels
    for f in (0.0, 0.25, 0.5, 0.75, 1.0):
        xt = sx(rmax * f)
        parts.append(f'<text x="{xt}" y="{H-pad_b+14}" text-anchor="middle" '
                     f'fill="{C_MUTED}" font-size="9">{rmax*f:.0f}</text>')
    for f in (0.0, 0.5, 1.0):
        yt = sy(Fsmax * f)
        parts.append(f'<text x="{pad_l-4}" y="{yt+3}" text-anchor="end" '
                     f'fill="{C_MUTED}" font-size="9">{Fsmax*f:.0f}</text>')

    parts.append(f'<text x="{W/2}" y="{H-4}" text-anchor="middle" fill="{C_TEXT}" '
                 f'font-size="11">h / w</text>')
    parts.append(f'<text x="14" y="{H/2}" text-anchor="middle" fill="{C_TEXT}" '
                 f'font-size="11" transform="rotate(-90, 14, {H/2})">Fs (MPa)</text>')
    title = "Stiffened web" if stiffened else "Unstiffened web"
    if stiffened and kv:
        title += f" (kv = {kv:.2f})"
    parts.append(f'<text x="{W-pad_r-2}" y="{pad_t+10}" text-anchor="end" '
                 f'fill="{C_MUTED}" font-size="10">{title}</text>')

    return _wrap("".join(parts), W, H)
