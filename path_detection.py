from __future__ import annotations

# path_detection.py
# Geometry-driven detector for net-section and block-shear candidates.
#
# Design rule: GEOMETRY senses the candidate paths, MATERIAL (handled by the
# existing calc_* functions) picks the governing one. This module never touches
# Fy or Fu. It only turns dimensions + bolt layout into physical candidate
# paths, then the existing resistance functions rank them.
#
# ASCII only. Straight quotes only. No markdown inside strings.

from dataclasses import dataclass
from itertools import product, combinations
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Bolt coordinates
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BoltPoint:
    # x = transverse coordinate, measured from the reference free edge
    # y = longitudinal coordinate, measured from the loaded end
    line: int
    row: int
    x: float
    y: float


def build_bolt_grid(bolt, line_offsets: Optional[Sequence[float]] = None) -> List[BoltPoint]:
    # Convert the regular bolt-pattern inputs into physical coordinates.
    # line_offsets shifts each bolt line longitudinally, e.g. [0, s/2] for a
    # conventional half-pitch stagger between two lines.
    if line_offsets is None:
        line_offsets = [0.0] * bolt.n_lines
    if len(line_offsets) != bolt.n_lines:
        raise ValueError("line_offsets length must equal n_lines.")

    points: List[BoltPoint] = []
    for line in range(bolt.n_lines):
        x = bolt.edge_trans + line * bolt.gauge
        offset = float(line_offsets[line])
        for row in range(bolt.bolts_per_line):
            y = bolt.edge_end + row * bolt.pitch + offset
            points.append(BoltPoint(line=line, row=row, x=x, y=y))
    return points


# ---------------------------------------------------------------------------
# Section topology: dimensions -> connected element + free-edge rules
# ---------------------------------------------------------------------------
@dataclass
class ConnectedElement:
    # The flat strip the bolts pass through, expressed in the detector's
    # transverse x-frame. free_near / free_far say whether tension tear-out is
    # allowed to run off that side. obstruction_x is an interior x the tension
    # plane may not cross (e.g. the stem of a flange-connected WT).
    width: float
    thickness: float
    free_near: bool          # x = 0 side (the e2 reference edge)
    free_far: bool           # x = width side
    obstruction_x: Optional[float] = None
    note: str = ""


def resolve_connected_element(
    section_type: str,
    connected_element: str,
    dims: Dict[str, float],
) -> ConnectedElement:
    # dims keys used: leg_conn, t, b_flange, d_depth, t_flange, t_stem,
    # t_web, width (plate). Not all are needed by every branch.
    st = section_type

    if st == "Plate":
        return ConnectedElement(
            width=dims["width"],
            thickness=dims["t"],
            free_near=True,
            free_far=True,
            note="Plate: both transverse edges free.",
        )

    if st in ("Single Angle", "Double Angle"):
        # Connected element is the connected leg, treated as a flat strip.
        # Free edge at the leg toe (far). The heel/corner (near, x=0 datum at
        # e2) is the reference edge the bolts are dimensioned from.
        return ConnectedElement(
            width=dims["leg_conn"],
            thickness=dims["t"],
            free_near=True,
            free_far=False,
            note="Angle leg: tension tear-out toward the connected-leg toe.",
        )

    if st == "WT Section":
        if connected_element == "stem":
            # Stem width available for tear-out is roughly (D - T_flange).
            # One free edge at the stem tip; the flange is continuous
            # material, NOT a free edge.
            usable = dims["d_depth"] - dims["t_flange"]
            return ConnectedElement(
                width=usable,
                thickness=dims["t_stem"],
                free_near=True,   # stem tip
                free_far=False,   # runs into the flange
                note="WT stem-connected: one free edge at stem tip; flange restrains the far side.",
            )
        else:
            # Flange-connected: element is the flange, width B, two free tips,
            # but the stem sits at the centerline as an obstruction.
            return ConnectedElement(
                width=dims["b_flange"],
                thickness=dims["t_flange"],
                free_near=True,
                free_far=True,
                obstruction_x=dims["b_flange"] / 2.0,
                note="WT flange-connected: both flange tips free; stem at centerline blocks crossing.",
            )

    if st == "Channel (C / MC)":
        # Web-connected: web depth D bounded by BOTH flanges. Neither
        # transverse edge is truly free the way a plate edge is.
        return ConnectedElement(
            width=dims["d_depth"],
            thickness=dims["t_web"],
            free_near=False,
            free_far=False,
            note="Channel web-connected: both edges restrained by flanges (no plate free edge).",
        )

    # Fallback: treat as flat strip with one free edge.
    return ConnectedElement(
        width=dims.get("leg_conn", dims.get("width", 0.0)),
        thickness=dims["t"],
        free_near=True,
        free_far=False,
        note="Default flat-strip topology.",
    )


# ---------------------------------------------------------------------------
# Net-section detection (coordinate based, full-Ag basis)
# ---------------------------------------------------------------------------
def detect_net_section_paths(
    Ag: float,
    t: float,
    d_eff: float,
    bolts: Sequence[BoltPoint],
    connected_parts: int = 1,
    pitch_mm: float = 0.0,
    gauge_mm: float = 0.0,
    max_candidates: int = 40,
) -> List[Dict]:
    if Ag <= 0 or t <= 0 or d_eff <= 0:
        raise ValueError("Ag, t, and d_eff must all be positive.")

    by_line: Dict[int, List[BoltPoint]] = defaultdict(list)
    for p in bolts:
        by_line[p.line].append(p)
    line_numbers = sorted(by_line)
    if not line_numbers:
        raise ValueError("No bolt coordinates supplied.")
    for ln in line_numbers:
        by_line[ln].sort(key=lambda p: p.y)

    choices = [[None] + by_line[ln] for ln in line_numbers]
    detected: Dict[Tuple, Dict] = {}

    for raw in product(*choices):
        selected = [p for p in raw if p is not None]
        if not selected:
            continue
        selected.sort(key=lambda p: p.x)

        sel_lines = set(p.line for p in selected)
        y_lo = min(p.y for p in selected)
        y_hi = max(p.y for p in selected)
        skipped_ok = True
        for ln in line_numbers:
            if ln in sel_lines:
                continue
            for h in by_line[ln]:
                if y_lo - 1e-6 <= h.y <= y_hi + 1e-6:
                    skipped_ok = False
                    break
            if not skipped_ok:
                break
        if not skipped_ok:
            continue

        segments = []
        stagger_len = 0.0
        ok = True

        for a, b in zip(selected, selected[1:]):
            g = b.x - a.x
            s = abs(b.y - a.y)
            if g <= 0:
                ok = False
                break
            add = s * s / (4.0 * g)
            segments.append({"s_mm": s, "g_mm": g, "addition_mm": add,
                             "from_line": a.line, "to_line": b.line})
            stagger_len += add
        if not ok:
            continue

        n_holes = len(selected)
        hole_ded = connected_parts * n_holes * d_eff * t
        stag_area = connected_parts * stagger_len * t

        An_raw = Ag - hole_ded + stag_area
        was_clamped = An_raw > Ag
        An = min(An_raw, Ag)

        if An <= 0:
            continue

        line_sig = tuple(p.line for p in selected)
        stag_sig = tuple(round(abs(b.y - a.y), 6)
                         for a, b in zip(selected, selected[1:]))
        signature = (line_sig, stag_sig)

        path_type = "Straight" if stagger_len == 0 else "Zig-zag"
        route = " - ".join("L%d/R%d" % (p.line + 1, p.row + 1)
                           for p in selected)

        cand = {
            "area_basis": "gross_section",
            "description": "%s: %s" % (path_type, route),
            "selected": [(p.line, p.row) for p in selected],
            "n_holes": n_holes,
            "n_staggers": sum(1 for seg in segments if seg["s_mm"] > 0),
            "stagger_segments": segments,
            "stagger_term": stagger_len,
            "stagger_area_mm2": stag_area,
            "hole_deduction_mm2": hole_ded,
            "connected_parts": connected_parts,
            "Ag_mm2": Ag,
            "An_raw_mm2": An_raw,
            "An_mm2": An,
            "governed_by_Ag": was_clamped,
            "d_eff_mm": d_eff,
            "t_mm": t,
            "pitch_mm": pitch_mm,
            "gauge_mm": gauge_mm,
        }

        cur = detected.get(signature)
        if cur is None or An < cur["An_mm2"]:
            detected[signature] = cand

    out = sorted(detected.values(), key=lambda c: c["An_mm2"])
    return out[:max_candidates]


# ---------------------------------------------------------------------------
# Block-shear detection (geometry + topology driven)
# ---------------------------------------------------------------------------
def detect_block_shear_paths(
    bolt,
    element: ConnectedElement,
    d_eff: float,
) -> List[Dict]:
    if element.width <= 0:
        raise ValueError("Connected-element width must be positive.")
    if element.thickness <= 0 or d_eff <= 0:
        raise ValueError("thickness and d_eff must be positive.")

    t = element.thickness
    x_lines = [bolt.edge_trans + i * bolt.gauge for i in range(bolt.n_lines)]
    for x in x_lines:
        if x <= 0 or x > element.width + 1e-6:
            raise ValueError(
                "Bolt line at x=%.1f lies outside connected width %.1f."
                % (x, element.width))

    Lv = bolt.edge_end + (bolt.bolts_per_line - 1) * bolt.pitch
    Agv_single = Lv * t
    out: List[Dict] = []

    def add(key, desc, Lnt, planes, formula, subst):
        if Lnt <= 0:
            return  # infeasible geometry: report as absent, not shear-only
        out.append({
            "key": key,
            "description": desc,
            "Ant": Lnt * t,
            "Agv": Agv_single,
            "planes": planes,
            "Lv_mm": Lv,
            "tension_width_mm": Lnt,
            "t_mm": t,
            "d_eff_mm": d_eff,
            "n_rows": bolt.bolts_per_line,
            "n_lines": bolt.n_lines,
            "edge_end_mm": bolt.edge_end,
            "edge_trans_mm": bolt.edge_trans,
            "pitch_mm": bolt.pitch,
            "gauge_mm": bolt.gauge,
            "tension_formula": formula,
            "tension_substitution": subst,
        })

    # Tension terminating at the NEAR free edge (x = 0 side).
    if element.free_near:
        for i, x in enumerate(x_lines):
            equiv = i + 0.5
            Lnt = x - equiv * d_eff
            add("NEAR-%d" % (i + 1),
                "near free edge to bolt line %d" % (i + 1),
                Lnt, 1,
                "Lnt = x_line - (intermediate holes + 0.5) d_eff",
                "%.1f - %.1f x %.2f" % (x, equiv, d_eff))

    # Tension terminating at the FAR free edge (x = width side).
    if element.free_far:
        last = len(x_lines) - 1
        for i, x in enumerate(x_lines):
            equiv = (last - i) + 0.5
            gross = element.width - x
            Lnt = gross - equiv * d_eff
            add("FAR-%d" % (i + 1),
                "bolt line %d to far free edge" % (i + 1),
                Lnt, 1,
                "Lnt = (width - x_line) - (intermediate holes + 0.5) d_eff",
                "%.1f - %.1f x %.2f" % (gross, equiv, d_eff))

    # Tension BETWEEN two bolt lines (two shear planes). Always valid: the
    # material between interior lines can tear regardless of edge freedom.
    for a, b in combinations(range(len(x_lines)), 2):
        gross = x_lines[b] - x_lines[a]
        equiv = b - a
        Lnt = gross - equiv * d_eff
        add("BETWEEN-%d-%d" % (a + 1, b + 1),
            "between bolt lines %d and %d" % (a + 1, b + 1),
            Lnt, 2,
            "Lnt = (x_b - x_a) - (lines between) d_eff",
            "%.1f - %.1f x %.2f" % (gross, equiv, d_eff))

    return out
