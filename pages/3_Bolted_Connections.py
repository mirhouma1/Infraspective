import math
import re
from enum import Enum
import streamlit as st
import streamlit.components.v1 as components


def _svg_html(svg: str) -> None:
    """Render an SVG using components.html to bypass Streamlit's HTML sanitiser."""
    m = re.search(r'height="(\d+)"', svg)
    h = int(m.group(1)) + 16 if m else 320
    components.html(svg, height=h, scrolling=False)

# ================================================================
# CSA S16 / CIVE 3205 — Chapter 6 Part 1 — Bolted Connections
# Failure modes: Vr, Br, Tr_bolt, Tr_gross, Tr_net, Vr_bs, Vs
# Interaction checks + 4 SVG diagrams
# ================================================================

PHI_B   = 0.80   # bolts (shear + tension)
PHI_BR  = 0.80   # bearing
PHI     = 0.90   # plate gross yielding
PHI_U   = 0.75   # plate net fracture / block shear

BOLT_SHEAR_FACTOR      = 0.60
BOLT_SHEAR_LONG_FACTOR = 0.50   # lap splices L >= 760 mm
THREADS_INTERCEPT      = 0.70
BOLT_TENSION_FACTOR    = 0.75

SLIP_BASE_FACTOR    = 0.53
LONG_SLOT_SLIP      = 0.75
BR_COEFF_STD        = 3.0
BR_COEFF_LONG_SLOT  = 2.4

PITCH_MIN_MULT   = 2.7
EDGE_MAX_LIMIT   = 150.0
EDGE_MAX_MULT_T  = 12.0


# ── Enums ────────────────────────────────────────────────────────────────────
class BoltGrade(Enum):
    A307  = ("ASTM A307",  414.0)
    A325M = ("ASTM A325M", 830.0)
    A490M = ("ASTM A490M", 1040.0)

    @property
    def label(self) -> str:  return self.value[0]
    @property
    def Fu_MPa(self) -> float: return self.value[1]


class SlipSurfaceClass(Enum):
    A = ("Class A", 0.30)
    B = ("Class B", 0.52)

    @property
    def label(self) -> str:   return self.value[0]
    @property
    def ks(self) -> float:    return self.value[1]


class InstallationMethod(Enum):
    TURN_OF_NUT = "Turn-of-nut"
    OTHER       = "Other (F959/F1852/F2280)"


class EdgeType(Enum):
    SHEARED           = "Sheared"
    ROLLED_SAWN       = "Rolled / sawn / thermal cut"


# ── Table 3 ──────────────────────────────────────────────────────────────────
# Separate typed structures to avoid pyright dict-subscript warnings

# cs values: turn-of-nut method, keyed by (surface_class, bolt_grade)
_CS_TURN: dict[tuple[SlipSurfaceClass, BoltGrade], float] = {
    (SlipSurfaceClass.A, BoltGrade.A325M): 1.00,
    (SlipSurfaceClass.A, BoltGrade.A490M): 0.92,
    (SlipSurfaceClass.B, BoltGrade.A325M): 1.04,
    (SlipSurfaceClass.B, BoltGrade.A490M): 0.96,
}

# cs values: other installation method
_CS_OTHER: dict[SlipSurfaceClass, float] = {
    SlipSurfaceClass.A: 0.78,
    SlipSurfaceClass.B: 0.81,
}

# Surface class descriptions (for UI display)
SLIP_DESC: dict[SlipSurfaceClass, str] = {
    SlipSurfaceClass.A: "Clean mill scale",
    SlipSurfaceClass.B: "Blast-cleaned",
}

# Retained for UI label lookups (desc only)
SLIP_CS = {
    SlipSurfaceClass.A: {"desc": "Clean mill scale"},
    SlipSurfaceClass.B: {"desc": "Blast-cleaned"},
}


def get_cs(surface: SlipSurfaceClass, grade: BoltGrade,
           method: InstallationMethod) -> float:
    if method == InstallationMethod.OTHER:
        return _CS_OTHER[surface]
    # Turn-of-nut: only defined for A325M and A490M
    key = (surface, grade)
    if key in _CS_TURN:
        return _CS_TURN[key]
    # A307 or unrecognised — fall back to "other" column (conservative)
    return _CS_OTHER[surface]


# ── Table 6 ──────────────────────────────────────────────────────────────────
TABLE_6: dict[int, tuple[int, int]] = {16:(28,22), 20:(34,26), 22:(38,28), 24:(42,30),
           27:(48,34), 30:(52,38), 36:(64,46)}

def min_edge_dist(d: float, edge_type: EdgeType) -> float:
    if d > 36:
        return 1.75*d if edge_type == EdgeType.SHEARED else 1.25*d
    s, r = TABLE_6[int(round(d))]
    return s if edge_type == EdgeType.SHEARED else r

def min_end_dist(d: float, n_in_line: int, edge_type: EdgeType) -> float:
    return 1.5*d if n_in_line <= 2 else min_edge_dist(d, edge_type)

def max_edge_dist(t: float) -> float: return min(EDGE_MAX_MULT_T*t, EDGE_MAX_LIMIT)
def min_pitch(d: float) -> float: return PITCH_MIN_MULT * d


# ── Core resistance functions (all return N) ──────────────────────────────────
def bolt_area(d: float) -> float: return math.pi * d**2 / 4.0

def vr_N(n, m, d, Fu_bolt, threads, long_splice):
    Ab  = bolt_area(d)
    fac = BOLT_SHEAR_LONG_FACTOR if long_splice else BOLT_SHEAR_FACTOR
    Vr  = fac * PHI_B * n * m * Ab * Fu_bolt
    if threads: Vr *= THREADS_INTERCEPT
    return Vr

def br_N(n, t, d, Fu_plate, long_slot):
    c = BR_COEFF_LONG_SLOT if long_slot else BR_COEFF_STD
    return c * PHI_BR * n * t * d * Fu_plate

def tr_bolt_N(d, Fu_bolt):
    return BOLT_TENSION_FACTOR * PHI_B * bolt_area(d) * Fu_bolt

def vs_N(n, m, d, Fu_bolt, ks, cs, long_slot):
    Ab = bolt_area(d)
    Vs = SLIP_BASE_FACTOR * cs * ks * n * m * Ab * Fu_bolt
    if long_slot: Vs *= LONG_SLOT_SLIP
    return Vs

def tr_gross_N(w, t, Fy):
    return PHI * w * t * Fy

def tr_net_N(w, t, n_holes_row, d_h, Fu_plate):
    Ane = (w - n_holes_row * d_h) * t
    return PHI_U * max(Ane, 0) * Fu_plate

def block_shear_N(n_rows, n_cols, pitch, end_dist, t, d_h, Fy, Fu, Ut):
    """
    Shear path: n_rows lines, each of length = end_dist + (n_cols-1)*pitch
    Tension path: (n_rows-1) spaces of pitch perpendicular to load
    Returns (Vr_bs, Agv, Anv, Ane, case1, case2)
    """
    shear_len = end_dist + (n_cols - 1) * pitch
    Agv = n_rows * shear_len * t
    # net shear: subtract n_rows * n_cols half-holes + n_rows * (n_cols-1) full holes
    # Simplified: n_rows * (n_cols - 0.5) holes per shear line
    Anv = Agv - n_rows * (n_cols - 0.5) * d_h * t
    Anv = max(Anv, 0)

    # Tension path between outermost bolt lines (net)
    if n_rows > 1:
        tension_len = (n_rows - 1) * pitch
        Ane = tension_len * t - (n_rows - 1) * 0.5 * d_h * t
        Ane = max(Ane, 0)
    else:
        Ane = 0.0  # single bolt line — no tension area

    case1 = PHI_U * (Ut * Ane * Fu + 0.6 * Agv * Fy)   # gross shear
    case2 = PHI_U * (Ut * Ane * Fu + 0.6 * Anv * Fu)   # net shear
    Vr_bs = min(case1, case2)
    return Vr_bs, Agv, Anv, Ane, case1, case2

def prying_k(a: float, b: float, t: float) -> float:
    if a <= 0: return float("nan")
    return (3*b)/(8*a) - t**3/328e3


# ── SVG helpers ───────────────────────────────────────────────────────────────
def _hatch(x, y, w, h, col="#94a3b8", spacing=8, angle=45):
    lines = []
    if angle == 45:
        for i in range(-int(h/spacing)-2, int((w+h)/spacing)+2):
            x1 = x + i*spacing; y1 = y
            x2 = x + i*spacing + h; y2 = y + h
            lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="1.2" opacity="0.6"/>')
    else:  # vertical
        for i in range(int(w/spacing)+2):
            xi = x + i*spacing
            lines.append(f'<line x1="{xi}" y1="{y}" x2="{xi}" y2="{y+h}" stroke="{col}" stroke-width="1.2" opacity="0.6"/>')
    return "".join(lines)


def svg_bolt_layout(n_rows, n_cols, pitch, end_dist, edge_dist, d_mm, d_h):
    """Plan view of bolt layout on plate."""
    margin = 40
    scale  = min(50.0, 300.0 / max(n_cols * pitch + 2*end_dist, 1))
    scale  = max(scale, 12.0)

    bw = end_dist + (n_cols-1)*pitch + end_dist
    bh = edge_dist + (n_rows-1)*pitch + edge_dist

    W = int(bw * scale + 2*margin)
    H = int(bh * scale + 2*margin)
    W = max(W, 320); H = max(H, 200)

    ox = margin; oy = margin
    pw = bw*scale; ph = bh*scale

    # Plate
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"
      style="font-family:'Courier New',monospace;background:#1e293b;border-radius:10px;">
  <!-- Plate -->
  <rect x="{ox}" y="{oy}" width="{pw:.1f}" height="{ph:.1f}"
        fill="#334155" stroke="#64748b" stroke-width="2" rx="3"/>
  <!-- Load arrows -->
  <defs>
    <marker id="arr" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <polygon points="0 0, 8 3, 0 6" fill="#f59e0b"/>
    </marker>
  </defs>
  <line x1="{ox-30}" y1="{oy+ph/2:.1f}" x2="{ox+5}" y2="{oy+ph/2:.1f}"
        stroke="#f59e0b" stroke-width="2.5" marker-end="url(#arr)"/>
  <text x="{ox-36}" y="{oy+ph/2-6:.1f}" fill="#f59e0b" font-size="10" text-anchor="middle">T</text>
'''
    # Bolts
    br = max(4.0, d_mm * scale / 2 * 0.6)
    for r in range(n_rows):
        for c in range(n_cols):
            bx = ox + (end_dist + c*pitch)*scale
            by = oy + (edge_dist + r*pitch)*scale
            is_edge = (r == 0 or r == n_rows-1 or c == 0)
            col = "#ef4444" if is_edge else "#22c55e"
            svg += f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{br:.1f}" fill="{col}" opacity="0.85" stroke="#1e293b" stroke-width="1.5"/>'
            # hole
            svg += f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{max(2,br*0.4):.1f}" fill="#1e293b" opacity="0.6"/>'

    # Dimension: pitch
    if n_cols > 1:
        y_dim = oy + ph + 18
        x1d = ox + end_dist*scale; x2d = ox + (end_dist+pitch)*scale
        svg += f'<line x1="{x1d:.1f}" y1="{y_dim}" x2="{x2d:.1f}" y2="{y_dim}" stroke="#94a3b8" stroke-width="1"/>'
        svg += f'<text x="{(x1d+x2d)/2:.1f}" y="{y_dim+12}" fill="#94a3b8" font-size="10" text-anchor="middle">p={pitch:.0f}</text>'

    # Dimension: end
    y_dim2 = oy + ph + 18
    svg += f'<text x="{ox+end_dist*scale/2:.1f}" y="{y_dim2+12}" fill="#64748b" font-size="9" text-anchor="middle">end={end_dist:.0f}</text>'

    # Title
    svg += f'<text x="{ox+pw/2:.1f}" y="{oy-10}" fill="#e2e8f0" font-size="12" font-weight="bold" text-anchor="middle">'
    svg += f'Bolt Layout — {n_rows}×{n_cols} ({n_rows*n_cols} bolts)</text>'

    # Legend
    lx = W - 110; ly = oy + 10
    svg += f'<circle cx="{lx+6}" cy="{ly+5}" r="5" fill="#22c55e"/>'
    svg += f'<text x="{lx+14}" y="{ly+9}" fill="#94a3b8" font-size="9">Interior</text>'
    svg += f'<circle cx="{lx+6}" cy="{ly+20}" r="5" fill="#ef4444"/>'
    svg += f'<text x="{lx+14}" y="{ly+24}" fill="#94a3b8" font-size="9">Edge/End</text>'

    svg += '</svg>'
    return svg


def svg_failure_modes(n_rows, n_cols, pitch, end_dist, edge_dist, d_h,
                      governing_mode):
    """Side elevation showing failure paths."""
    W, H = 560, 240
    ox, oy = 50, 50
    pw, ph_plate = 420, 80

    # bolt positions in elevation (along load direction)
    bolt_xs = [ox + end_dist/(end_dist+(n_cols-1)*pitch+end_dist)*pw +
               c*pitch/(end_dist+(n_cols-1)*pitch+end_dist)*pw
               for c in range(n_cols)]
    bolt_xs = [ox + (end_dist + c*pitch) * pw /
               (end_dist + (n_cols-1)*pitch + end_dist)
               for c in range(n_cols)]
    by_mid  = oy + ph_plate/2

    mode_colors = {
        "Bolt shear":     "#3b82f6",
        "Bearing":        "#8b5cf6",
        "Net fracture":   "#f97316",
        "Gross yielding": "#eab308",
        "Block shear":    "#ef4444",
    }

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"
      style="font-family:'Courier New',monospace;background:#1e293b;border-radius:10px;">
  <!-- Plate -->
  <rect x="{ox}" y="{oy}" width="{pw}" height="{ph_plate}"
        fill="#334155" stroke="#475569" stroke-width="2"/>
'''
    # Gross yielding band (full width)
    col = "#eab308" if governing_mode == "Gross yielding" else "#eab30840"
    sw  = 3 if governing_mode == "Gross yielding" else 1
    svg += f'<rect x="{ox}" y="{oy+8}" width="{pw}" height="{ph_plate-16}" fill="{col}" opacity="0.25" stroke="{col}" stroke-width="{sw}" stroke-dasharray="6,3"/>'

    # Net fracture lines through bolt holes
    for bx in bolt_xs:
        col = "#f97316" if governing_mode == "Net fracture" else "#f9731660"
        svg += f'<line x1="{bx:.1f}" y1="{oy}" x2="{bx:.1f}" y2="{oy+ph_plate}" stroke="{col}" stroke-width="2" stroke-dasharray="4,2"/>'

    # Block shear — L-shaped path from end to last bolt then across
    if n_cols > 0:
        bx_last = bolt_xs[-1]
        col = "#ef4444" if governing_mode == "Block shear" else "#ef444460"
        svg += f'<polyline points="{ox},{oy+15} {bx_last:.1f},{oy+15} {bx_last:.1f},{oy+ph_plate-15}" fill="none" stroke="{col}" stroke-width="3" stroke-dasharray="5,2"/>'
        svg += f'<text x="{ox+(bx_last-ox)/2:.1f}" y="{oy+12}" fill="{col}" font-size="9" text-anchor="middle">Block shear</text>'

    # Bolts in elevation
    br = 10
    for bx in bolt_xs:
        bcol = "#3b82f6" if governing_mode == "Bolt shear" else "#60a5fa"
        svg += f'<ellipse cx="{bx:.1f}" cy="{by_mid}" rx="{br}" ry="{br*1.2}" fill="{bcol}" opacity="0.85" stroke="#1e293b" stroke-width="1.5"/>'
        # bearing arrows
        arrow_col = "#8b5cf6" if governing_mode == "Bearing" else "#8b5cf660"
        svg += f'<line x1="{bx+br:.1f}" y1="{by_mid}" x2="{bx+br+14:.1f}" y2="{by_mid}" stroke="{arrow_col}" stroke-width="2" marker-end="url(#arr2)"/>'

    # Load arrow
    svg += f'''<defs>
    <marker id="arr2" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <polygon points="0 0, 8 3, 0 6" fill="#f59e0b"/>
    </marker></defs>
  <line x1="{ox-35}" y1="{by_mid}" x2="{ox-5}" y2="{by_mid}"
        stroke="#f59e0b" stroke-width="3" marker-end="url(#arr2)"/>
  <text x="{ox-40}" y="{by_mid-6}" fill="#f59e0b" font-size="11" font-weight="bold" text-anchor="middle">T</text>'''

    # Legend
    lx = 10; ly = H - 95
    for i, (mode, col) in enumerate(mode_colors.items()):
        is_gov = mode == governing_mode
        svg += f'<rect x="{lx}" y="{ly+i*17}" width="12" height="10" fill="{col}" opacity="{"1" if is_gov else "0.5"}"/>'
        fw = "bold" if is_gov else "normal"
        svg += f'<text x="{lx+16}" y="{ly+i*17+9}" fill="{col if is_gov else "#94a3b8"}" font-size="9" font-weight="{fw}">{mode}{"  ← GOVERNING" if is_gov else ""}</text>'

    svg += f'<text x="{ox+pw/2}" y="18" fill="#e2e8f0" font-size="12" font-weight="bold" text-anchor="middle">Failure Mode Visualization</text>'
    svg += '</svg>'
    return svg


def svg_capacity_bars(capacities_kN, applied_kN, governing_mode):
    """Horizontal bar chart of all failure mode capacities."""
    W, H = 560, max(260, len(capacities_kN)*38 + 70)
    pad_l, pad_r, pad_t, pad_b = 160, 40, 40, 40
    bw = W - pad_l - pad_r

    max_val = max(v for v in capacities_kN.values() if v > 0 and math.isfinite(v))
    max_val = max(max_val, applied_kN * 1.2, 1)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"
      style="font-family:'Courier New',monospace;background:#1e293b;border-radius:10px;">
  <text x="{W//2}" y="22" fill="#e2e8f0" font-size="13" font-weight="bold" text-anchor="middle">Capacity Comparison (kN)</text>
'''
    bar_h = 22
    for i, (label, val) in enumerate(capacities_kN.items()):
        y = pad_t + i * (bar_h + 10)
        is_gov = label == governing_mode
        passes = val >= applied_kN if math.isfinite(val) else False
        bar_col  = "#ef4444" if not passes else ("#f59e0b" if is_gov else "#22c55e")
        text_col = "#fbbf24" if is_gov else "#e2e8f0"

        # Label
        svg += f'<text x="{pad_l-6}" y="{y+bar_h//2+4}" fill="{text_col}" font-size="10" text-anchor="end" font-weight="{"bold" if is_gov else "normal"}">{label}</text>'

        # Bar
        bar_w = min(bw * val / max_val, bw) if math.isfinite(val) and val > 0 else 0
        svg += f'<rect x="{pad_l}" y="{y}" width="{bw}" height="{bar_h}" fill="#1e293b" rx="3"/>'
        svg += f'<rect x="{pad_l}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" fill="{bar_col}" opacity="0.85" rx="3"/>'
        if is_gov:
            svg += f'<rect x="{pad_l}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" fill="none" stroke="{bar_col}" stroke-width="2" rx="3"/>'

        # Value label
        val_str = f"{val:.1f}" if math.isfinite(val) else "N/A"
        svg += f'<text x="{pad_l + bar_w + 4:.1f}" y="{y+bar_h//2+4}" fill="{bar_col}" font-size="10">{val_str}</text>'

    # Applied load line
    appl_x = pad_l + min(bw * applied_kN / max_val, bw)
    svg += f'<line x1="{appl_x:.1f}" y1="{pad_t-10}" x2="{appl_x:.1f}" y2="{H-pad_b}" stroke="#f59e0b" stroke-width="2" stroke-dasharray="5,3"/>'
    svg += f'<text x="{appl_x:.1f}" y="{pad_t-13}" fill="#f59e0b" font-size="10" text-anchor="middle">Tu/Vu={applied_kN:.1f}</text>'

    svg += '</svg>'
    return svg


def svg_block_shear_detail(n_rows, n_cols, pitch, end_dist, edge_dist,
                           Agv, Anv, Ane, d_h):
    """Annotated block shear geometry diagram."""
    W, H = 400, 280
    margin = 55
    total_w = end_dist + (n_cols-1)*pitch + end_dist
    total_h = edge_dist + (n_rows-1)*pitch + edge_dist
    scale = min(240/max(total_w,1), 180/max(total_h,1))
    pw = total_w * scale; ph = total_h * scale
    ox = margin; oy = (H - ph) / 2

    # shear block dimensions
    sb_w = (end_dist + (n_cols-1)*pitch) * scale
    sb_h = ((n_rows-1)*pitch) * scale if n_rows > 1 else ph*0.6

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"
      style="font-family:'Courier New',monospace;background:#1e293b;border-radius:10px;">
  <text x="{W//2}" y="20" fill="#e2e8f0" font-size="12" font-weight="bold" text-anchor="middle">Block Shear Geometry</text>
  <!-- Plate -->
  <rect x="{ox:.1f}" y="{oy:.1f}" width="{pw:.1f}" height="{ph:.1f}" fill="#334155" stroke="#475569" stroke-width="2"/>
'''
    # Shear area (Agv) — vertical hatch
    svg += f'<rect x="{ox:.1f}" y="{oy:.1f}" width="{sb_w:.1f}" height="{sb_h:.1f}" fill="#3b82f620"/>'
    svg += _hatch(ox, oy, sb_w, sb_h, col="#3b82f6", spacing=10, angle=90)
    svg += f'<rect x="{ox:.1f}" y="{oy:.1f}" width="{sb_w:.1f}" height="{sb_h:.1f}" fill="none" stroke="#3b82f6" stroke-width="2"/>'

    # Tension area (Ane) — diagonal hatch
    if n_rows > 1:
        tn_y = oy
        tn_h = (n_rows-1)*pitch*scale
        svg += f'<rect x="{ox+sb_w:.1f}" y="{tn_y:.1f}" width="{end_dist*scale:.1f}" height="{tn_h:.1f}" fill="#f9731620"/>'
        svg += _hatch(ox+sb_w, tn_y, end_dist*scale, tn_h, col="#f97316", spacing=8, angle=45)
        svg += f'<rect x="{ox+sb_w:.1f}" y="{tn_y:.1f}" width="{end_dist*scale:.1f}" height="{tn_h:.1f}" fill="none" stroke="#f97316" stroke-width="2"/>'
        svg += f'<text x="{ox+sb_w+end_dist*scale/2:.1f}" y="{tn_y+tn_h+14}" fill="#f97316" font-size="9" text-anchor="middle">Ane={Ane:.0f} mm²</text>'

    # Bolts
    br = 7
    for r in range(n_rows):
        for c in range(n_cols):
            bx = ox + (end_dist + c*pitch)*scale
            by = oy + (edge_dist + r*pitch)*scale
            svg += f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{br}" fill="#60a5fa" stroke="#1e293b" stroke-width="1.5"/>'

    # Labels
    svg += f'<text x="{ox + sb_w/2:.1f}" y="{oy + sb_h + 14}" fill="#3b82f6" font-size="9" text-anchor="middle">Agv={Agv:.0f} mm²</text>'
    svg += f'<text x="{ox + sb_w/2:.1f}" y="{oy + sb_h + 24}" fill="#60a5fa" font-size="9" text-anchor="middle">Anv={Anv:.0f} mm²</text>'

    # Legend
    svg += f'<rect x="10" y="{H-50}" width="10" height="10" fill="#3b82f660"/>'
    svg += f'<text x="24" y="{H-41}" fill="#3b82f6" font-size="9">Shear area (Agv/Anv)</text>'
    svg += f'<rect x="10" y="{H-34}" width="10" height="10" fill="#f9731660"/>'
    svg += f'<text x="24" y="{H-25}" fill="#f97316" font-size="9">Tension area (Ane)</text>'

    svg += '</svg>'
    return svg


# ================================================================
# STREAMLIT UI
# ================================================================
st.title("CSA S16 — Bolted Connection Solver")
st.caption("Chapter 6 Part 1 · Failure modes: Vr, Br, Tr(bolt), Tr(gross), Tr(net), Vr(block shear), Vs · Prying integrated · 4 diagrams")

st.markdown("---")

# ── INPUTS ───────────────────────────────────────────────────────────────────
col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("### Bolt Configuration")
    conn_type = st.selectbox("Connection type", ["Bearing-type", "Slip-critical"], key="conn_type")
    grade     = st.selectbox("Bolt grade", list(BoltGrade), format_func=lambda g: g.label, key="grade")
    d_mm      = st.selectbox("Bolt diameter d (mm)", [16,20,22,24,27,30,36], key="d_mm")
    n_rows    = int(st.number_input("Bolt rows (⊥ to load)", min_value=1, value=1, step=1, key="n_rows"))
    n_cols    = int(st.number_input("Bolt columns (∥ to load)", min_value=1, value=4, step=1, key="n_cols"))
    n         = n_rows * n_cols
    st.info(f"Total bolts n = {n_rows} × {n_cols} = **{n}**")
    m         = int(st.number_input("Shear planes m", min_value=1, value=1, step=1, key="m"))

    st.markdown("### Plate Material")
    t_mm      = float(st.number_input("Plate thickness t (mm)", min_value=1.0, value=10.0, step=1.0, key="t_mm"))
    w_mm      = float(st.number_input("Plate width w (mm)", min_value=10.0, value=140.0, step=5.0, key="w_mm"))
    Fy_plate  = float(st.number_input("Plate Fy (MPa)", min_value=200.0, value=350.0, step=10.0, key="Fy_plate"))
    Fu_plate  = float(st.number_input("Plate Fu (MPa)", min_value=200.0, value=450.0, step=10.0, key="Fu_plate"))
    d_h_auto  = d_mm + 2.0
    d_h       = float(st.number_input(f"Hole diameter d_h (mm)  [auto = {d_h_auto:.0f}]",
                                       min_value=float(d_mm), value=d_h_auto, step=1.0, key="d_h"))

with col_b:
    st.markdown("### Detailing Geometry")
    edge_type     = st.radio("Edge type", list(EdgeType), format_func=lambda e: e.value, key="edge_type")
    pitch_mm      = float(st.number_input("Bolt pitch p (mm)", min_value=0.0, value=60.0, step=5.0, key="pitch"))
    edge_prov_mm  = float(st.number_input("Edge distance e (mm)", min_value=0.0, value=40.0, step=5.0, key="edge"))
    end_prov_mm   = float(st.number_input("End distance a_end (mm)", min_value=0.0, value=40.0, step=5.0, key="end"))

    st.markdown("### Options")
    threads       = st.checkbox("Threads intercepted by shear plane?", key="threads")
    long_slot     = st.checkbox("Long-slotted holes?", key="long_slot")
    L_splice      = float(st.number_input("Splice length L (mm)  [0 = not a lap splice]",
                                           min_value=0.0, value=0.0, step=10.0, key="splice"))
    long_splice   = L_splice >= 760.0
    if long_splice:
        st.warning("L ≥ 760 mm → Vr uses 0.50 factor (long splice, Cl. 13.12.1.2c)")

    Ut = float(st.selectbox("Shear lag factor Ut (block shear)",
                             [("1.0 — all elements connected", 1.0),
                              ("0.6 — partial connection (e.g. angles)", 0.6)],
                             format_func=lambda x: x[0], key="Ut")[1])

    if conn_type == "Slip-critical":
        st.markdown("### Slip-Critical (Table 3)")
        slip_surface = st.selectbox("Surface class", list(SlipSurfaceClass),
                                    format_func=lambda s: f"{s.label} — {SLIP_DESC[s]}", key="surf")
        slip_method  = st.selectbox("Installation method", list(InstallationMethod),
                                    format_func=lambda x: x.value, key="method")
    else:
        slip_surface = SlipSurfaceClass.A
        slip_method  = InstallationMethod.TURN_OF_NUT

with col_c:
    st.markdown("### Factored Loads")
    Vu_kN = float(st.number_input("Factored shear Vu (kN)", min_value=0.0, value=150.0, step=5.0, key="Vu"))
    Tu_kN = float(st.number_input("Factored tension Tu (kN)", min_value=0.0, value=0.0, step=5.0, key="Tu"))

    st.markdown("### Prying Action")
    pry_enabled = st.checkbox("Include prying action?", value=False, key="pry_on")
    if pry_enabled:
        a_pry = float(st.number_input("Distance a (mm) — bolt to free edge", min_value=1.0, value=77.0, step=1.0, key="a_pry"))
        b_pry = float(st.number_input("Distance b (mm) — bolt to applied load line", min_value=1.0, value=57.5, step=1.0, key="b_pry"))
        P_per_bolt = Tu_kN / max(n, 1)
        k_pry = prying_k(a_pry, b_pry, t_mm)
        if math.isfinite(k_pry) and k_pry > 0:
            Q_per_bolt = k_pry * P_per_bolt
            Tu_total_kN = Tu_kN + Q_per_bolt * n
            st.info(f"k = {k_pry:.4f}  |  Q/bolt = {Q_per_bolt:.2f} kN  |  **Tu (incl. prying) = {Tu_total_kN:.2f} kN**")
        else:
            Q_per_bolt  = 0.0
            Tu_total_kN = Tu_kN
            st.warning("k ≤ 0 — prying negligible")
    else:
        a_pry = b_pry = k_pry = 0.0
        Q_per_bolt = 0.0
        Tu_total_kN = Tu_kN

st.markdown("---")

# ── CALCULATIONS ─────────────────────────────────────────────────────────────
Vu_N = Vu_kN * 1e3
Tu_N = Tu_total_kN * 1e3
Fu_bolt = grade.Fu_MPa
Ab = bolt_area(d_mm)

Vr   = vr_N(n, m, d_mm, Fu_bolt, threads, long_splice)
Br   = br_N(n, t_mm, d_mm, Fu_plate, long_slot)
Tr_b = tr_bolt_N(d_mm, Fu_bolt)          # per bolt
Tr_b_group = Tr_b * n
Tr_g = tr_gross_N(w_mm, t_mm, Fy_plate)
Tr_n = tr_net_N(w_mm, t_mm, n_rows, d_h, Fu_plate)

# Block shear
use_end = end_prov_mm if end_prov_mm > 0 else (1.5*d_mm)
use_pitch = pitch_mm if pitch_mm > 0 else min_pitch(d_mm)
Vr_bs, Agv, Anv, Ane, bs_case1, bs_case2 = block_shear_N(
    n_rows, n_cols, use_pitch, use_end, t_mm, d_h, Fy_plate, Fu_plate, Ut
)

# Slip
Vs = 0.0
cs_val = ks_val = None
slip_ok = grade != BoltGrade.A307
if conn_type == "Slip-critical" and slip_ok:
    ks_val = slip_surface.ks
    cs_val = get_cs(slip_surface, grade, slip_method)
    Vs = vs_N(n, m, d_mm, Fu_bolt, ks_val, cs_val, long_slot)

def kN(x: float) -> float: return x / 1e3

# Build capacity dict
caps = {
    "Bolt shear Vr":      kN(Vr),
    "Bearing Br":         kN(Br),
    "Bolt tension Tr":    kN(Tr_b_group),
    "Gross yielding":     kN(Tr_g),
    "Net fracture":       kN(Tr_n),
    "Block shear":        kN(Vr_bs),
}
if conn_type == "Slip-critical" and slip_ok:
    caps["Slip Vs"] = kN(Vs)

gov_label = min(caps, key=lambda k: caps[k] if caps[k] > 0 else float("inf"))
gov_val   = caps[gov_label]

# Applied governs: use max of Vu or Tu for chart
applied_chart = max(Vu_kN, Tu_total_kN)

# ── RESULTS ──────────────────────────────────────────────────────────────────
st.subheader("Results")
res_col, diag_col = st.columns([3, 2], gap="large")

with res_col:
    # Step 1 — Bolt area
    st.markdown("#### Step 1 — Bolt Geometry")
    st.latex(r"A_b = \frac{\pi d^2}{4}")
    st.code(f"  d  = {d_mm} mm\n  Ab = π × {d_mm}² / 4 = {Ab:.1f} mm²\n  n  = {n_rows} × {n_cols} = {n} bolts,  m = {m} shear planes",
            language="text")

    # Step 2 — Bolt shear
    st.markdown("---")
    st.markdown("#### Step 2 — Bolt Shear Resistance  *(Cl. 13.12.1.2c)*")
    fac_used = BOLT_SHEAR_LONG_FACTOR if long_splice else BOLT_SHEAR_FACTOR
    if long_splice:
        st.latex(r"V_r = 0.50\,\phi_b\,n\,m\,A_b\,F_u \quad (L \geq 760\,\text{mm})")
    else:
        st.latex(r"V_r = 0.60\,\phi_b\,n\,m\,A_b\,F_u")
    thr_str = f" × {THREADS_INTERCEPT} (threads)" if threads else ""
    st.code(f"  = {fac_used} × {PHI_B} × {n} × {m} × {Ab:.1f} × {Fu_bolt:.0f}{thr_str}\n  = {kN(Vr):.1f} kN",
            language="text")
    _icon = "PASS" if Vr >= Vu_N else "FAIL"
    st.markdown(f"{_icon} — Vr = **{kN(Vr):.1f} kN**  vs  Vu = {Vu_kN:.1f} kN")

    # Step 3 — Bearing
    st.markdown("---")
    st.markdown("#### Step 3 — Bearing Resistance  *(Cl. 13.12.1.2a)*")
    coeff_str = "2.4" if long_slot else "3.0"
    st.latex(r"B_r = " + coeff_str + r"\,\phi_{br}\,n\,t\,d\,F_u")
    st.code(f"  = {coeff_str} × {PHI_BR} × {n} × {t_mm} × {d_mm} × {Fu_plate:.0f}\n  = {kN(Br):.1f} kN",
            language="text")

    # Step 4 — Bolt tension
    st.markdown("---")
    st.markdown("#### Step 4 — Bolt Tension Resistance  *(Cl. 13.12.1.3)*")
    st.latex(r"T_r = 0.75\,\phi_b\,A_b\,F_u")
    st.code(f"  Per bolt = 0.75 × {PHI_B} × {Ab:.1f} × {Fu_bolt:.0f} = {kN(Tr_b):.1f} kN\n"
            f"  Group ({n} bolts) = {kN(Tr_b_group):.1f} kN", language="text")

    # Step 5 — Prying
    if pry_enabled and math.isfinite(k_pry) and k_pry > 0:
        st.markdown("---")
        st.markdown("#### Step 5 — Prying Action")
        st.latex(r"k = \frac{3b}{8a} - \frac{t^3}{328\times10^3} \qquad Q = kP")
        st.code(f"  k = (3 × {b_pry}) / (8 × {a_pry}) - {t_mm}³/328000\n"
                f"    = {k_pry:.4f}\n"
                f"  P/bolt = {Tu_kN:.1f}/{n} = {P_per_bolt:.3f} kN\n"
                f"  Q/bolt = {k_pry:.4f} × {P_per_bolt:.3f} = {Q_per_bolt:.3f} kN\n"
                f"  Tu (incl. prying) = {Tu_kN:.1f} + {Q_per_bolt*n:.2f} = {Tu_total_kN:.2f} kN",
                language="text")

    # Step 6 — Gross yielding
    st.markdown("---")
    st.markdown("#### Step 6 — Plate Gross Yielding  *(Cl. 13.2a)*")
    st.latex(r"T_{r,gross} = \phi \cdot A_g \cdot F_y")
    Ag = w_mm * t_mm
    st.code(f"  Ag = w × t = {w_mm:.0f} × {t_mm:.0f} = {Ag:.0f} mm²\n"
            f"  Tr,gross = {PHI} × {Ag:.0f} × {Fy_plate:.0f} = {kN(Tr_g):.1f} kN",
            language="text")
    _icon = "PASS" if Tr_g >= Tu_N else "FAIL"
    st.markdown(f"{_icon} — Tr,gross = **{kN(Tr_g):.1f} kN**  vs  Tu = {Tu_total_kN:.1f} kN")

    # Step 7 — Net fracture
    st.markdown("---")
    st.markdown("#### Step 7 — Plate Net Section Fracture  *(Cl. 13.2b)*")
    st.latex(r"T_{r,net} = \phi_u \cdot A_{ne} \cdot F_u")
    Ane_plate = (w_mm - n_rows * d_h) * t_mm
    st.code(f"  Ane = (w - n_rows × d_h) × t\n"
            f"      = ({w_mm:.0f} - {n_rows} × {d_h:.0f}) × {t_mm:.0f} = {Ane_plate:.0f} mm²\n"
            f"  Tr,net = {PHI_U} × {max(Ane_plate,0):.0f} × {Fu_plate:.0f} = {kN(Tr_n):.1f} kN",
            language="text")
    _icon = "PASS" if Tr_n >= Tu_N else "FAIL"
    st.markdown(f"{_icon} — Tr,net = **{kN(Tr_n):.1f} kN**  vs  Tu = {Tu_total_kN:.1f} kN")

    # Step 8 — Block shear
    st.markdown("---")
    st.markdown("#### Step 8 — Block Shear  *(Cl. 13.11)*")
    st.latex(r"V_{r,bs} = \phi_u\!\left(U_t A_{ne} F_u + 0.6\,A_{gv} F_y\right) \text{ or } \phi_u\!\left(U_t A_{ne} F_u + 0.6\,A_{nv} F_u\right)")
    st.code(f"  Shear path length = {use_end:.0f} + ({n_cols}-1)×{use_pitch:.0f} = {use_end+(n_cols-1)*use_pitch:.0f} mm\n"
            f"  Agv  = {n_rows} lines × {use_end+(n_cols-1)*use_pitch:.0f} × {t_mm:.0f} = {Agv:.0f} mm²\n"
            f"  Anv  = {Agv:.0f} - {n_rows}×({n_cols}-0.5)×{d_h:.0f}×{t_mm:.0f} = {Anv:.0f} mm²\n"
            f"  Ane  = {Ane:.0f} mm²   (tension path between bolt lines)\n"
            f"  Ut   = {Ut}\n"
            f"  ──────────────────────────────────────────────────\n"
            f"  Case 1 (gross shear): {PHI_U}×({Ut}×{Ane:.0f}×{Fu_plate:.0f} + 0.6×{Agv:.0f}×{Fy_plate:.0f}) = {kN(bs_case1):.1f} kN\n"
            f"  Case 2 (net shear):   {PHI_U}×({Ut}×{Ane:.0f}×{Fu_plate:.0f} + 0.6×{Anv:.0f}×{Fu_plate:.0f}) = {kN(bs_case2):.1f} kN\n"
            f"  Governing (lesser) = {kN(Vr_bs):.1f} kN",
            language="text")
    _icon = "PASS" if Vr_bs >= Vu_N else "FAIL"
    st.markdown(f"{_icon} — Vr,bs = **{kN(Vr_bs):.1f} kN**  vs  Vu = {Vu_kN:.1f} kN")

    # Step 9 — Slip
    if conn_type == "Slip-critical":
        st.markdown("---")
        st.markdown("#### Step 9 — Slip Resistance  *(Cl. 13.12.2.2)*")
        if not slip_ok:
            st.warning("Slip-critical resistance not applicable to A307 bolts.")
        else:
            st.latex(r"V_s = 0.53\,c_s\,k_s\,n\,m\,A_b\,F_u")
            ls_note = " × 0.75 (long slot)" if long_slot else ""
            st.code(f"  ks = {ks_val:.2f}  cs = {cs_val:.2f}  ({SLIP_DESC[slip_surface]})\n"
                    f"  = 0.53 × {cs_val:.2f} × {ks_val:.2f} × {n} × {m} × {Ab:.1f} × {Fu_bolt:.0f}{ls_note}\n"
                    f"  = {kN(Vs):.1f} kN", language="text")

    # Step 10 — Interaction
    st.markdown("---")
    st.markdown("#### Step 10 — Interaction Checks")

    u_bt = (Vu_N/Vr)**2 + (Tu_N/Tr_b_group)**2 if (Vr > 0 and Tr_b_group > 0) else float("inf")
    st.latex(r"\left(\frac{V_f}{V_r}\right)^2 + \left(\frac{T_f}{T_r}\right)^2 \leq 1.0")
    st.code(f"  = ({Vu_kN:.1f}/{kN(Vr):.1f})² + ({Tu_total_kN:.1f}/{kN(Tr_b_group):.1f})²\n"
            f"  = {(Vu_N/Vr)**2:.4f} + {(Tu_N/Tr_b_group)**2:.4f} = {u_bt:.4f}",
            language="text")
    if u_bt <= 1.0: st.success(f"PASS — bearing-type interaction = {u_bt:.3f}")
    else:           st.error(f"FAIL — bearing-type interaction = {u_bt:.3f}")

    if conn_type == "Slip-critical" and slip_ok and Vs > 0:
        u_sc = Vu_N/Vs + 1.9*Tu_N/(n*Ab*Fu_bolt)
        st.latex(r"\frac{V}{V_s} + \frac{1.9\,T}{n\,A_b\,F_u} \leq 1.0")
        st.code(f"  = {Vu_kN:.1f}/{kN(Vs):.1f} + 1.9×{Tu_total_kN:.1f}/({n}×{Ab:.1f}×{kN(Fu_bolt*1000):.0f})\n"
                f"  = {u_sc:.4f}", language="text")
        if u_sc <= 1.0: st.success(f"PASS — slip-critical interaction = {u_sc:.3f}")
        else:           st.error(f"FAIL — slip-critical interaction = {u_sc:.3f}")

    # Step 11 — Governing
    st.markdown("---")
    st.markdown("#### Step 11 — Governing Summary")
    for label, val in caps.items():
        passes = val >= applied_chart
        icon   = "PASS" if passes else "FAIL"
        bold   = "**" if label == gov_label else ""
        st.markdown(f"{icon} — {bold}{label} = {val:.1f} kN{bold}")
    st.markdown("---")
    if gov_val >= applied_chart:
        st.success(f"OVERALL PASS — Governing: {gov_label} = {gov_val:.1f} kN >= {applied_chart:.1f} kN")
    else:
        st.error(f"OVERALL FAIL — Governing: {gov_label} = {gov_val:.1f} kN < {applied_chart:.1f} kN")

    # Detailing checks
    st.markdown("---")
    st.markdown("#### Detailing Checks  *(Cl. 22.3)*")
    p_min = min_pitch(d_mm)
    e_min = min_edge_dist(d_mm, edge_type)
    e_max = max_edge_dist(t_mm)
    a_min = min_end_dist(d_mm, n_cols, edge_type)
    for label, prov, req_min, req_max in [
        ("Pitch",         pitch_mm,    p_min, None),
        ("Edge distance", edge_prov_mm, e_min, e_max),
        ("End distance",  end_prov_mm, a_min, None),
    ]:
        if prov <= 0:
            st.caption(f"{label}: enter value for PASS/FAIL")
            continue
        ok = prov >= req_min and (req_max is None or prov <= req_max)
        req_str = f">= {req_min:.1f}" + (f" and <= {req_max:.1f}" if req_max else "")
        icon = "PASS" if ok else "FAIL"
        st.markdown(f"{icon} — **{label}**: {prov:.1f} mm  ({req_str})")


with diag_col:
    st.markdown("#### Diagrams")

    # Diagram 1 — bolt layout
    st.markdown("**Bolt Layout Plan**")
    use_edge = edge_prov_mm if edge_prov_mm > 0 else min_edge_dist(d_mm, edge_type)
    _svg_html(svg_bolt_layout(n_rows, n_cols, use_pitch, use_end, use_edge, d_mm, d_h))

    # Diagram 2 — failure modes
    st.markdown("**Failure Mode Visualization**")
    gov_mode_map = {
        "Bolt shear Vr": "Bolt shear", "Bearing Br": "Bearing",
        "Net fracture":  "Net fracture", "Gross yielding": "Gross yielding",
        "Block shear":   "Block shear", "Bolt tension Tr": "Bolt shear",
        "Slip Vs":       "Bolt shear",
    }
    gov_mode = gov_mode_map.get(gov_label, "Bolt shear")
    _svg_html(svg_failure_modes(n_rows, n_cols, use_pitch, use_end, use_edge, d_h, gov_mode))

    # Diagram 3 — capacity bar chart
    st.markdown("**Capacity Bar Chart**")
    _svg_html(svg_capacity_bars(caps, applied_chart, gov_label))

    # Diagram 4 — block shear geometry
    st.markdown("**Block Shear Geometry**")
    _svg_html(svg_block_shear_detail(n_rows, n_cols, use_pitch, use_end,
                                     use_edge, Agv, Anv, Ane, d_h))
