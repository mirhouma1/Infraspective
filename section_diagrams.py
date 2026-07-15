    """
    section_diagrams.py

    Dimensioned three-view SVG diagrams for tension members, driven entirely
    by the inputs already collected in the Tension Members page:
        n_lines, bolts_per_line, pitch, gauge, edge_end (e1), edge_trans (e2),
        hole_dia, section dimensions from the data tables.

    Views for single angle:
      FRONT (cross-section): L-profile with root/toe fillets, leg dims, t,
          gauge line positions (e2 from toe, g between lines).
      ELEVATION: connected leg face, bolt columns, e1 / p / g / e2 dims,
          optional net-fracture critical path (straight or zig-zag) and
          block shear tear-out region overlays.
      PLAN: outstanding leg with the connected leg edge-on; if the
          outstanding leg is bolted (out_n_lines >= 1), its holes are drawn
          with their own e1 / p / e2 / g dimensions.

    Double angle (2L back-to-back on a gusset): same three views with the
    gusset strip and gap s in the section, mirrored outstanding legs, and
    automatic LLBB / SLBB / equal-legs labeling for unequal angles. Both
    builders accept an independent outstanding-leg bolt pattern (out_*
    parameters, default off).

    Extensible: register new section builders in DIAGRAM_BUILDERS and call
    member_diagram(section_type, ...) from the app.

    ASCII-only source.
    """

    import math
    from typing import Any, Dict, List, Optional

    # ---------------------------------------------------------------------------
    # styles
    # ---------------------------------------------------------------------------
    S_OUT = 'stroke="#1a1a1a" stroke-width="1.6" fill="#e8edf2"'
    S_OUTN = 'stroke="#1a1a1a" stroke-width="1.6" fill="none"'
    S_HID = 'stroke="#666" stroke-width="1" stroke-dasharray="6,4" fill="none"'
    S_CL = 'stroke="#c0392b" stroke-width="0.8" stroke-dasharray="14,4,3,4" fill="none"'
    S_DIM = 'stroke="#2c5f8a" stroke-width="0.9" fill="none"'
    S_BOLT = 'stroke="#1a1a1a" stroke-width="1.1" fill="white"'
    S_FRAC = 'stroke="#c0392b" stroke-width="2" stroke-dasharray="8,5" fill="none"'
    S_BLOCK = 'fill="#f39c12" fill-opacity="0.22" stroke="none"'
    S_BLOCK_EDGE = 'stroke="#d35400" stroke-width="2.2" fill="none"'
    FONT = 'font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#2c5f8a"'
    FONT_T = 'font-family="Helvetica, Arial, sans-serif" font-size="14" font-weight="bold" fill="#1a1a1a"'
    FONT_R = 'font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#c0392b"'
    FONT_O = 'font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#d35400"'


    def _ln(x1, y1, x2, y2, style):
        return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" {style}/>'


    def _tx(x, y, s, anchor="middle", font=FONT, rot=None):
        tr = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot is not None else ""
        return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" {font}{tr}>{s}</text>'


    def _defs():
        return ('<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" '
                'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                '<path d="M 0 0 L 10 5 L 0 10 z" fill="#2c5f8a"/></marker></defs>')


    def _dimh(x1, x2, y, label, ey1=None, ey2=None, above=True):
        p = []
        if ey1 is not None:
            p.append(_ln(x1, ey1, x1, y + (4 if y > ey1 else -4), S_DIM))
        if ey2 is not None:
            p.append(_ln(x2, ey2, x2, y + (4 if y > ey2 else -4), S_DIM))
        p.append(f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
                 f'{S_DIM} marker-start="url(#ar)" marker-end="url(#ar)"/>')
        p.append(_tx((x1 + x2) / 2, y - 5 if above else y + 14, label))
        return "".join(p)


    def _dimv(y1, y2, x, label, ex1=None, ex2=None, left=True):
        p = []
        if ex1 is not None:
            p.append(_ln(ex1, y1, x + (4 if x > ex1 else -4), y1, S_DIM))
        if ex2 is not None:
            p.append(_ln(ex2, y2, x + (4 if x > ex2 else -4), y2, S_DIM))
        p.append(f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" '
                 f'{S_DIM} marker-start="url(#ar)" marker-end="url(#ar)"/>')
        anchor = "end" if left else "start"
        p.append(_tx(x - 7 if left else x + 7, (y1 + y2) / 2 + 4, label, anchor=anchor))
        return "".join(p)


    def _brk(x, yt, yb, amp=6.0):
        n = max(4, int((yb - yt) / 14))
        pts = [f"{x:.1f},{yt:.1f}"]
        for i in range(1, n):
            yy = yt + (yb - yt) * i / n
            pts.append(f"{x + (amp if i % 2 else -amp):.1f},{yy:.1f}")
        pts.append(f"{x:.1f},{yb:.1f}")
        return f'<polyline points="{" ".join(pts)}" {S_OUTN}/>'


    def _lprofile(ox, oy, d, b, t, r, rt, s, sign=1):
        """L cross-section path. (ox,oy)=heel outer corner bottom, y up.
        sign=+1 outstanding leg points right, sign=-1 points left (mirrored)."""
        sw1 = 1 if sign > 0 else 0
        sw0 = 0 if sign > 0 else 1

        def X(v):
            return ox + sign * v * s

        def Y(v):
            return oy - v * s

        p = [f"M {X(0):.1f} {Y(d):.1f}",
             f"L {X(0):.1f} {Y(0):.1f}",
             f"L {X(b):.1f} {Y(0):.1f}",
             f"L {X(b):.1f} {Y(t - rt):.1f}",
             f"A {rt*s:.1f} {rt*s:.1f} 0 0 {sw1} {X(b - rt):.1f} {Y(t):.1f}",
             f"L {X(t + r):.1f} {Y(t):.1f}",
             f"A {r*s:.1f} {r*s:.1f} 0 0 {sw0} {X(t):.1f} {Y(t + r):.1f}",
             f"L {X(t):.1f} {Y(d - rt):.1f}",
             f"A {rt*s:.1f} {rt*s:.1f} 0 0 {sw1} {X(t - rt):.1f} {Y(d):.1f}",
             "Z"]
        return f'<path d="{" ".join(p)}" {S_OUT}/>'


    # ---------------------------------------------------------------------------
    # single angle
    # ---------------------------------------------------------------------------
    def single_angle_diagram(
        leg_conn: float,            # connected leg length (mm) - drawn vertical
        leg_out: float,             # outstanding leg length (mm)
        t: float,
        n_lines: int = 1,           # gauge lines (bolt columns across the leg)
        bolts_per_line: int = 3,    # bolts along the member per line
        pitch: float = 80.0,        # longitudinal spacing p (mm)
        gauge: float = 60.0,        # spacing g between gauge lines (mm)
        edge_end: float = 40.0,     # e1: member end to first bolt (mm)
        edge_trans: float = 30.0,   # e2: toe edge to nearest gauge line (mm)
        hole_dia: float = 22.0,
        out_n_lines: int = 0,           # 0 = outstanding leg not bolted
        out_bolts_per_line: int = 0,
        out_pitch: float = 75.0,
        out_gauge: float = 60.0,
        out_edge_end: float = 40.0,
        out_edge_trans: float = 30.0,   # from outstanding-leg toe to nearest line
        out_hole_dia: Optional[float] = None,
        show_net_fracture: bool = True,
        zig_zag: bool = False,
        show_block_shear: bool = True,
        section_label: str = "",
        root_r: Optional[float] = None,
        toe_r: Optional[float] = None,
        scale: float = 2.0,
    ) -> str:
        r = root_r if root_r is not None else 1.0 * t
        rt = toe_r if toe_r is not None else 0.5 * t
        has_out = out_n_lines >= 1 and out_bolts_per_line >= 1
        ohd = out_hole_dia if out_hole_dia is not None else hole_dia

        # gauge line heights measured from the HEEL (line 0 nearest heel)
        line_h = [leg_conn - edge_trans - (n_lines - 1 - i) * gauge
                  for i in range(n_lines)]
        # outstanding-leg lines, measured from ITS toe
        out_line = ([out_edge_trans + k * out_gauge for k in range(out_n_lines)]
                    if has_out else [])
        warn = []
        if line_h and line_h[0] < 0.3 * leg_conn:
            warn.append("Gauge layout crowds the heel: check g / e2 vs leg size.")
        if has_out and out_line and out_line[-1] > leg_out - t:
            warn.append("Outstanding-leg gauge exceeds available leg width.")

        x_bolt = [edge_end + j * pitch for j in range(bolts_per_line)]
        xo_bolt = ([out_edge_end + j * out_pitch for j in range(out_bolts_per_line)]
                   if has_out else [])
        L_show = max(x_bolt[-1], xo_bolt[-1] if xo_bolt else 0.0) + 55.0
        s = scale
        M = 72.0
        gap = 58.0

        fw, fh = leg_out * s, leg_conn * s
        ew, eh = L_show * s, leg_conn * s
        pw = leg_out * s

        W = M + fw + gap + ew + M + 46
        H = M + max(fh, eh) + gap + pw + M + 34

        fx, fy = M + 26, M + fh + 6          # front origin (heel, bottom-left)
        ex, ey = fx + fw + gap + 46, fy      # elevation bottom-left (heel edge)
        px_, py = ex, ey + gap + pw          # plan bottom-left

        top = ey - eh                        # elevation toe edge (top)
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" '
               f'height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}" '
               f'style="background:white">', _defs()]
        if section_label:
            svg.append(_tx(W / 2, 24, f"{section_label} - Single Angle Tension Member",
                           font=FONT_T))
        for w in warn:
            svg.append(_tx(W / 2, 42, "WARNING: " + w, font=FONT_R))

        # ---------------- FRONT (cross-section) ----------------
        svg.append(_lprofile(fx, fy, leg_conn, leg_out, t, r, rt, s))
        svg.append(_tx(fx + fw / 2, fy + 46, "SECTION", font=FONT_T))
        for i, h in enumerate(line_h):
            yh = fy - h * s
            svg.append(_ln(fx - 12, yh, fx + t * s + 12, yh, S_CL))
        # e2 from toe (top) down to nearest line, then g between lines
        svg.append(_dimv(fy - leg_conn * s, fy - line_h[-1] * s, fx - 26,
                         f"e2={edge_trans:.0f}"))
        for i in range(n_lines - 1, 0, -1):
            svg.append(_dimv(fy - line_h[i] * s, fy - line_h[i - 1] * s, fx - 26,
                             f"g={gauge:.0f}"))
        svg.append(_dimv(fy - leg_conn * s, fy, fx - 54, f"{leg_conn:.0f}",
                         ex1=fx, ex2=fx))
        svg.append(_dimh(fx, fx + leg_out * s, fy + 24, f"{leg_out:.0f}",
                         ey1=fy, ey2=fy, above=False))
        svg.append(_dimh(fx, fx + t * s, fy - leg_conn * s - 12, f"t={t:.0f}"))
        if has_out:
            for ol in out_line:
                xo = fx + (leg_out - ol) * s
                svg.append(_ln(xo, fy + 12, xo, fy - t * s - 12, S_CL))
            svg.append(_dimh(fx + (leg_out - out_line[0]) * s, fx + leg_out * s,
                             fy + 48, f"e2={out_edge_trans:.0f}", above=False))
            for k in range(1, out_n_lines):
                svg.append(_dimh(fx + (leg_out - out_line[k]) * s,
                                 fx + (leg_out - out_line[k - 1]) * s,
                                 fy + 48, f"g={out_gauge:.0f}", above=False))

        # ---------------- ELEVATION ----------------
        svg.append(f'<rect x="{ex:.1f}" y="{top:.1f}" width="{ew:.1f}" '
                   f'height="{eh:.1f}" {S_OUT}/>')
        svg.append(_brk(ex + ew, top, ey))
        svg.append(_ln(ex, ey - t * s, ex + ew, ey - t * s, S_HID))  # out. leg edge-on
        if has_out:
            for xb in xo_bolt:
                cx = ex + xb * s
                svg.append(f'<rect x="{cx - 4:.1f}" y="{ey - t * s:.1f}" width="8" '
                           f'height="{t * s:.1f}" fill="#1a1a1a"/>')
        svg.append(_tx(ex + ew / 2, ey + 46, "ELEVATION (connected leg)", font=FONT_T))

        # block shear tear-out region (behind holes)
        if show_block_shear:
            h0 = line_h[0]                       # heel-most line = shear plane
            xL = ex + x_bolt[-1] * s
            y0 = ey - h0 * s
            svg.append(f'<polygon points="{ex:.1f},{top:.1f} {xL:.1f},{top:.1f} '
                       f'{xL:.1f},{y0:.1f} {ex:.1f},{y0:.1f}" {S_BLOCK}/>')
            svg.append(_ln(ex, y0, xL, y0, S_BLOCK_EDGE))            # shear plane Agv
            svg.append(_ln(xL, y0, xL, top, S_BLOCK_EDGE))           # tension plane Ant
            svg.append(_tx(ex + x_bolt[-1] * s / 2, y0 + 15, "Agv (shear plane)",
                           font=FONT_O))
            svg.append(_tx(xL + 6, (y0 + top) / 2, "Ant", anchor="start", font=FONT_O))

        # gauge lines + bolts
        for h in line_h:
            yh = ey - h * s
            svg.append(_ln(ex, yh, ex + ew, yh, S_CL))
            for xb in x_bolt:
                cx = ex + xb * s
                rr = hole_dia / 2 * s
                svg.append(f'<circle cx="{cx:.1f}" cy="{yh:.1f}" r="{rr:.1f}" {S_BOLT}/>')

        # net fracture critical path
        if show_net_fracture:
            x0 = ex + x_bolt[0] * s
            if zig_zag and n_lines >= 2 and bolts_per_line >= 2:
                pts = [(x0, top)]
                for i in range(n_lines - 1, -1, -1):        # toe-most line first
                    col = min(n_lines - 1 - i, bolts_per_line - 1)
                    pts.append((ex + x_bolt[col] * s, ey - line_h[i] * s))
                pts.append((pts[-1][0], ey))
                d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                svg.append(f'<polyline points="{d}" {S_FRAC}/>')
                svg.append(_tx(pts[-1][0] + 8, ey - 8, "critical zig-zag path",
                               anchor="start", font=FONT_R))
            else:
                svg.append(_ln(x0, top, x0, ey, S_FRAC))
                svg.append(_tx(x0 + 8, ey - 8, "critical net section",
                               anchor="start", font=FONT_R))

        # longitudinal dims: e1 then p
        yd = top - 16
        svg.append(_dimh(ex, ex + edge_end * s, yd, f"e1={edge_end:.0f}",
                         ey1=top, ey2=top))
        for j in range(bolts_per_line - 1):
            xa = ex + x_bolt[j] * s
            svg.append(_dimh(xa, xa + pitch * s, yd, f"p={pitch:.0f}",
                             ey1=top, ey2=top))
        # transverse dims on right: e2 from toe, g between lines
        xr = ex + ew + 26
        svg.append(_dimv(top, ey - line_h[-1] * s, xr, f"e2={edge_trans:.0f}",
                         left=False))
        for i in range(n_lines - 1, 0, -1):
            svg.append(_dimv(ey - line_h[i] * s, ey - line_h[i - 1] * s, xr,
                             f"g={gauge:.0f}", left=False))
        svg.append(_dimv(top, ey, ex - 26, f"{leg_conn:.0f}", ex1=ex, ex2=ex))
        svg.append(_tx(ex + ew / 2, top - 44,
                       f"{n_lines * bolts_per_line} bolts in "
                       f"{hole_dia:.0f} dia holes"))

        # ---------------- PLAN (outstanding leg, no holes) ----------------
        ptop = py - pw
        svg.append(f'<rect x="{px_:.1f}" y="{ptop:.1f}" width="{ew:.1f}" '
                   f'height="{pw:.1f}" {S_OUT}/>')
        svg.append(_brk(px_ + ew, ptop, py))
        svg.append(_ln(px_, ptop + t * s, px_ + ew, ptop + t * s, S_HID))
        svg.append(_tx(px_ + ew / 2, py + 46,
                       "PLAN (outstanding leg" +
                       (", bolted)" if has_out else ")"), font=FONT_T))
        for xb in x_bolt:                       # connected-leg bolts, edge-on marks
            cx = px_ + xb * s
            svg.append(f'<rect x="{cx - 4:.1f}" y="{ptop:.1f}" width="8" '
                       f'height="{t * s:.1f}" fill="#1a1a1a"/>')
        if has_out:
            for ol in out_line:
                yo = py - ol * s
                svg.append(_ln(px_, yo, px_ + ew, yo, S_CL))
                for xb in xo_bolt:
                    cx = px_ + xb * s
                    rr = ohd / 2 * s
                    svg.append(f'<circle cx="{cx:.1f}" cy="{yo:.1f}" '
                               f'r="{rr:.1f}" {S_BOLT}/>')
            ypd = py + 20
            svg.append(_dimh(px_, px_ + out_edge_end * s, ypd,
                             f"e1={out_edge_end:.0f}", ey1=py, ey2=py, above=False))
            for j in range(out_bolts_per_line - 1):
                xa = px_ + xo_bolt[j] * s
                svg.append(_dimh(xa, xa + out_pitch * s, ypd,
                                 f"p={out_pitch:.0f}", ey1=py, ey2=py, above=False))
            xpr = px_ + ew + 26
            svg.append(_dimv(py - out_line[0] * s, py, xpr,
                             f"e2={out_edge_trans:.0f}", left=False))
            for k in range(1, out_n_lines):
                svg.append(_dimv(py - out_line[k] * s, py - out_line[k - 1] * s,
                                 xpr, f"g={out_gauge:.0f}", left=False))
        svg.append(_dimv(ptop, py, px_ - 26, f"{leg_out:.0f}", ex1=px_, ex2=px_))
        svg.append(_dimh(px_, px_ + t * s, py + 22, f"t={t:.0f}", above=False))

        svg.append("</svg>")
        return "".join(svg)


    # ---------------------------------------------------------------------------
    # double angle (2L back-to-back on a gusset)
    # ---------------------------------------------------------------------------
    def double_angle_diagram(
        leg_conn: float,            # connected leg length (mm) - vertical, on gusset
        leg_out: float,             # outstanding leg length (mm) - each side
        t: float,
        gusset_t: float = 10.0,     # gap s between back faces = gusset thickness
        n_lines: int = 1,
        bolts_per_line: int = 3,
        pitch: float = 75.0,
        gauge: float = 60.0,
        edge_end: float = 40.0,
        edge_trans: float = 30.0,
        hole_dia: float = 22.0,
        out_n_lines: int = 0,           # 0 = outstanding legs not bolted
        out_bolts_per_line: int = 0,
        out_pitch: float = 75.0,
        out_gauge: float = 60.0,
        out_edge_end: float = 40.0,
        out_edge_trans: float = 30.0,   # from each outstanding-leg toe
        out_hole_dia: Optional[float] = None,
        show_net_fracture: bool = True,
        zig_zag: bool = False,
        show_block_shear: bool = True,
        section_label: str = "",
        root_r: Optional[float] = None,
        toe_r: Optional[float] = None,
        scale: float = 2.0,
    ) -> str:
        r = root_r if root_r is not None else 1.0 * t
        rt = toe_r if toe_r is not None else 0.5 * t
        gp = gusset_t
        has_out = out_n_lines >= 1 and out_bolts_per_line >= 1
        ohd = out_hole_dia if out_hole_dia is not None else hole_dia

        line_h = [leg_conn - edge_trans - (n_lines - 1 - i) * gauge
                  for i in range(n_lines)]
        out_line = ([out_edge_trans + k * out_gauge for k in range(out_n_lines)]
                    if has_out else [])
        warn = []
        if line_h and line_h[0] < 0.3 * leg_conn:
            warn.append("Gauge layout crowds the heel: check g / e2 vs leg size.")
        if has_out and out_line and out_line[-1] > leg_out - t:
            warn.append("Outstanding-leg gauge exceeds available leg width.")

        x_bolt = [edge_end + j * pitch for j in range(bolts_per_line)]
        xo_bolt = ([out_edge_end + j * out_pitch for j in range(out_bolts_per_line)]
                   if has_out else [])
        L_show = max(x_bolt[-1], xo_bolt[-1] if xo_bolt else 0.0) + 55.0
        s = scale
        M = 72.0
        gap = 58.0

        sec_w = (2 * leg_out + gp) * s          # section total width
        fh = leg_conn * s
        ew, eh = L_show * s, leg_conn * s
        pw = (2 * leg_out + gp) * s             # plan transverse extent

        W = M + sec_w + gap + ew + M + 46
        H = M + max(fh, eh) + gap + pw + M + 34

        cxf = M + 26 + leg_out * s + gp * s / 2   # section center x (gusset axis)
        fy = M + fh + 6
        ex, ey = M + 26 + sec_w + gap + 46, fy
        px_, py = ex, ey + gap + pw
        top = ey - eh

        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" '
               f'height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}" '
               f'style="background:white">', _defs()]
        if abs(leg_conn - leg_out) < 0.5:
            config = "equal legs"
        elif leg_conn > leg_out:
            config = "LLBB - long legs back-to-back"
        else:
            config = "SLBB - short legs back-to-back"
        if section_label:
            svg.append(_tx(W / 2, 24,
                           f"2L {section_label} - Double Angle Tension Member "
                           f"({config})",
                           font=FONT_T))
        for w in warn:
            svg.append(_tx(W / 2, 42, "WARNING: " + w, font=FONT_R))

        # ---------------- SECTION (2L back-to-back) ----------------
        # gusset plate strip in the gap
        svg.append(f'<rect x="{cxf - gp*s/2:.1f}" y="{fy - fh:.1f}" '
                   f'width="{gp*s:.1f}" height="{fh:.1f}" '
                   f'fill="#cfd8dc" stroke="#666" stroke-width="0.8"/>')
        svg.append(_lprofile(cxf + gp * s / 2, fy, leg_conn, leg_out, t, r, rt, s, sign=1))
        svg.append(_lprofile(cxf - gp * s / 2, fy, leg_conn, leg_out, t, r, rt, s, sign=-1))
        svg.append(_tx(cxf, fy + 46, "SECTION (2L on gusset)", font=FONT_T))

        xl_in = cxf - gp * s / 2 - t * s
        xr_in = cxf + gp * s / 2 + t * s
        for h in line_h:
            yh = fy - h * s
            svg.append(_ln(xl_in - 12, yh, xr_in + 12, yh, S_CL))

        svg.append(_dimv(fy - leg_conn * s, fy - line_h[-1] * s,
                         cxf - gp * s / 2 - leg_out * s - 26, f"e2={edge_trans:.0f}"))
        for i in range(n_lines - 1, 0, -1):
            svg.append(_dimv(fy - line_h[i] * s, fy - line_h[i - 1] * s,
                             cxf - gp * s / 2 - leg_out * s - 26, f"g={gauge:.0f}"))
        svg.append(_dimv(fy - leg_conn * s, fy,
                         cxf - gp * s / 2 - leg_out * s - 54, f"{leg_conn:.0f}",
                         ex1=cxf - gp * s / 2 - leg_out * s,
                         ex2=cxf - gp * s / 2 - leg_out * s))
        svg.append(_dimh(cxf + gp * s / 2, cxf + gp * s / 2 + leg_out * s, fy + 24,
                         f"{leg_out:.0f}", ey1=fy, ey2=fy, above=False))
        svg.append(_dimh(cxf - gp * s / 2, cxf + gp * s / 2,
                         fy - leg_conn * s - 12, f"s={gp:.0f}"))
        svg.append(_dimh(cxf + gp * s / 2, cxf + gp * s / 2 + t * s, fy + 48,
                         f"t={t:.0f}", above=False))
        if has_out:
            for ol in out_line:
                for sgn in (1, -1):
                    xo = cxf + sgn * (gp / 2 + leg_out - ol) * s
                    svg.append(_ln(xo, fy + 12, xo, fy - t * s - 12, S_CL))
            svg.append(_dimh(cxf + (gp / 2 + leg_out - out_line[0]) * s,
                             cxf + (gp / 2 + leg_out) * s, fy + 70,
                             f"e2={out_edge_trans:.0f}", above=False))

        # ---------------- ELEVATION (shared bolt pattern) ----------------
        svg.append(f'<rect x="{ex:.1f}" y="{top:.1f}" width="{ew:.1f}" '
                   f'height="{eh:.1f}" {S_OUT}/>')
        svg.append(_brk(ex + ew, top, ey))
        svg.append(_ln(ex, ey - t * s, ex + ew, ey - t * s, S_HID))
        if has_out:
            for xb in xo_bolt:
                cx = ex + xb * s
                svg.append(f'<rect x="{cx - 4:.1f}" y="{ey - t * s:.1f}" width="8" '
                           f'height="{t * s:.1f}" fill="#1a1a1a"/>')
        svg.append(_tx(ex + ew / 2, ey + 46,
                       "ELEVATION (connected legs, bolts through gusset)",
                       font=FONT_T))

        if show_block_shear:
            h0 = line_h[0]
            xL = ex + x_bolt[-1] * s
            y0 = ey - h0 * s
            svg.append(f'<polygon points="{ex:.1f},{top:.1f} {xL:.1f},{top:.1f} '
                       f'{xL:.1f},{y0:.1f} {ex:.1f},{y0:.1f}" {S_BLOCK}/>')
            svg.append(_ln(ex, y0, xL, y0, S_BLOCK_EDGE))
            svg.append(_ln(xL, y0, xL, top, S_BLOCK_EDGE))
            svg.append(_tx(ex + x_bolt[-1] * s / 2, y0 + 15,
                           "Agv (per angle, x2)", font=FONT_O))
            svg.append(_tx(xL + 6, (y0 + top) / 2, "Ant", anchor="start", font=FONT_O))

        for h in line_h:
            yh = ey - h * s
            svg.append(_ln(ex, yh, ex + ew, yh, S_CL))
            for xb in x_bolt:
                cx = ex + xb * s
                rr = hole_dia / 2 * s
                svg.append(f'<circle cx="{cx:.1f}" cy="{yh:.1f}" r="{rr:.1f}" {S_BOLT}/>')

        if show_net_fracture:
            x0 = ex + x_bolt[0] * s
            if zig_zag and n_lines >= 2 and bolts_per_line >= 2:
                pts = [(x0, top)]
                for i in range(n_lines - 1, -1, -1):
                    col = min(n_lines - 1 - i, bolts_per_line - 1)
                    pts.append((ex + x_bolt[col] * s, ey - line_h[i] * s))
                pts.append((pts[-1][0], ey))
                d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                svg.append(f'<polyline points="{d}" {S_FRAC}/>')
                svg.append(_tx(pts[-1][0] + 8, ey - 8, "critical zig-zag path",
                               anchor="start", font=FONT_R))
            else:
                svg.append(_ln(x0, top, x0, ey, S_FRAC))
                svg.append(_tx(x0 + 8, ey - 8, "critical net section",
                               anchor="start", font=FONT_R))

        yd = top - 16
        svg.append(_dimh(ex, ex + edge_end * s, yd, f"e1={edge_end:.0f}",
                         ey1=top, ey2=top))
        for j in range(bolts_per_line - 1):
            xa = ex + x_bolt[j] * s
            svg.append(_dimh(xa, xa + pitch * s, yd, f"p={pitch:.0f}",
                             ey1=top, ey2=top))
        xr = ex + ew + 26
        svg.append(_dimv(top, ey - line_h[-1] * s, xr, f"e2={edge_trans:.0f}",
                         left=False))
        for i in range(n_lines - 1, 0, -1):
            svg.append(_dimv(ey - line_h[i] * s, ey - line_h[i - 1] * s, xr,
                             f"g={gauge:.0f}", left=False))
        svg.append(_dimv(top, ey, ex - 26, f"{leg_conn:.0f}", ex1=ex, ex2=ex))
        svg.append(_tx(ex + ew / 2, top - 44,
                       f"{n_lines * bolts_per_line} bolts in {hole_dia:.0f} dia "
                       f"holes (through both angles + gusset)"))

        # ---------------- PLAN (both outstanding legs) ----------------
        ptop = py - pw
        strip_h = (2 * t + gp) * s              # central connected-legs strip
        ymid = ptop + pw / 2
        svg.append(f'<rect x="{px_:.1f}" y="{ptop:.1f}" width="{ew:.1f}" '
                   f'height="{pw:.1f}" {S_OUT}/>')
        svg.append(_brk(px_ + ew, ptop, py))
        svg.append(_ln(px_, ymid - strip_h / 2, px_ + ew, ymid - strip_h / 2, S_HID))
        svg.append(_ln(px_, ymid + strip_h / 2, px_ + ew, ymid + strip_h / 2, S_HID))
        svg.append(_tx(px_ + ew / 2, py + 46,
                       "PLAN (outstanding legs both sides" +
                       (", bolted)" if has_out else ")"), font=FONT_T))
        for xb in x_bolt:
            cx = px_ + xb * s
            svg.append(f'<rect x="{cx - 4:.1f}" y="{ymid - strip_h / 2:.1f}" '
                       f'width="8" height="{strip_h:.1f}" fill="#1a1a1a"/>')
        if has_out:
            for ol in out_line:
                off = (gp / 2 + leg_out - ol) * s
                for sgn in (1, -1):
                    yo = ymid + sgn * off
                    svg.append(_ln(px_, yo, px_ + ew, yo, S_CL))
                    for xb in xo_bolt:
                        cx = px_ + xb * s
                        rr = ohd / 2 * s
                        svg.append(f'<circle cx="{cx:.1f}" cy="{yo:.1f}" '
                                   f'r="{rr:.1f}" {S_BOLT}/>')
            ypd = py + 20
            svg.append(_dimh(px_, px_ + out_edge_end * s, ypd,
                             f"e1={out_edge_end:.0f}", ey1=py, ey2=py, above=False))
            for j in range(out_bolts_per_line - 1):
                xa = px_ + xo_bolt[j] * s
                svg.append(_dimh(xa, xa + out_pitch * s, ypd,
                                 f"p={out_pitch:.0f}", ey1=py, ey2=py, above=False))
            xpr = px_ + ew + 26
            yo0 = ymid + (gp / 2 + leg_out - out_line[0]) * s
            svg.append(_dimv(yo0, py, xpr, f"e2={out_edge_trans:.0f}", left=False))
        svg.append(_dimv(ptop, py, px_ - 26, f"{2 * leg_out + gp:.0f}",
                         ex1=px_, ex2=px_))
        svg.append(_dimv(ymid - strip_h / 2, ymid + strip_h / 2, px_ + ew + 26,
                         f"2t+s={2 * t + gp:.0f}", left=False))

        svg.append("</svg>")
        return "".join(svg)


    # ---------------------------------------------------------------------------
    # dispatcher - add future section types here
    # ---------------------------------------------------------------------------
    DIAGRAM_BUILDERS = {
        "single_angle": single_angle_diagram,
        "double_angle": double_angle_diagram,
        # "plate":        plate_diagram,        (future)
        # "wt":           wt_diagram,           (future)
        # "channel":      channel_diagram,      (future)
    }


    def member_diagram(section_type: str, **kwargs) -> str:
        key = section_type.lower().replace(" ", "_").replace("(", "").replace(")", "")
        fn = DIAGRAM_BUILDERS.get(key)
        if fn is None:
            raise ValueError(f"No diagram builder for '{section_type}'. "
                             f"Available: {sorted(DIAGRAM_BUILDERS)}")
        return fn(**kwargs)


    if __name__ == "__main__":
        out = single_angle_diagram(
            leg_conn=152.0, leg_out=102.0, t=13.0,
            n_lines=2, bolts_per_line=4, pitch=80.0, gauge=60.0,
            edge_end=40.0, edge_trans=30.0, hole_dia=22.0,
            show_net_fracture=True, zig_zag=True, show_block_shear=True,
            section_label="L152x102x13",
        )
        with open("/home/claude/angle_views/single_angle_full.svg", "w") as f:
            f.write(out)
        print("written", len(out))
