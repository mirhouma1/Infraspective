"""
CSA S16 Tension Angle (One-Leg Connected) Calculator
====================================================

This module implements a design aid for single‐angle tension members
connected by one leg using bolts.  It follows the provisions of
CSA S16‑14 as interpreted from the Canadian Institute of Steel
Construction (CISC) Handbook.  The tool allows the user to select an
angle section from an Excel table, specify the bolt pattern and
material strengths, and then evaluates three limit states:

* Gross section yielding
* Net section fracture (including effects of hole staggering)
* Block shear

For net fracture the tool enumerates plausible fracture paths for
common one‑ or two‑line bolt patterns on the connected leg.  For
shear‑lag effects an effective net area reduction of 60 % or 80 %
applies depending on the number of transverse lines of bolts, in
accordance with CSA S16 Clause 12.3.3.3.  The block shear capacity is
estimated using the simplified expression from Clause 13.11 and
treating the block along the connected leg.

The calculator is implemented as a Streamlit application.  To run the
app locally, install the dependencies from ``requirements.txt`` and
execute ``streamlit run angle_tension_app.py``.

Note
----
This script intentionally avoids reproducing handbook tables verbatim.
Bolt hole diameters and reduction factors are supplied as defaults
only.  Users should verify these values against the current edition of
the relevant design standard and adjust the input parameters
accordingly.  The block shear routine in this first version provides
a conservative estimate based on the connection geometry; more
sophisticated block enumeration would require additional inputs to
distinguish between different tear‑out planes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from connection_diagram import generate_connection_svg


# ----------------------------------------------------------------------------
# Configuration and default tables
# ----------------------------------------------------------------------------

# Resistance factors (CSA S16-14)
PHI_YIELD = 0.90  # for gross yielding
PHI_FRACTURE = 0.75  # for net fracture and block shear

# Bolt diameters by designation (metric series)
BOLT_DIAMETERS_MM: Dict[str, float] = {
    "M16": 16.0,
    "M20": 20.0,
    "M22": 22.0,
    "M24": 24.0,
    "M27": 27.0,
    "M30": 30.0,
    "M36": 36.0,
}

# Recommended standard hole diameters for drilled holes.  These values
# represent nominal clearance holes from common practice.  Consult
# CSA S16‐14 Table 3‑47 for definitive diameters and adjust as
# necessary.  Oversize and slotted holes are not included here but
# could be added via the user interface.
STANDARD_HOLE_DIAMETERS_MM: Dict[str, float] = {
    "M16": 18.0,
    "M20": 22.0,
    "M22": 24.0,
    "M24": 26.0,
    "M27": 30.0,
    "M30": 33.0,
    "M36": 39.0,
}

# Hole types.  Currently only "Standard" is supported; others may be
# added in a future release.
HOLE_TYPES = ["Standard"]


# ----------------------------------------------------------------------------
# Data classes for structured inputs
# ----------------------------------------------------------------------------

@dataclass
class Calc:
    """A calculation result with step-by-step explanation."""
    name: str
    value: float
    units: str
    steps: List[str]


@dataclass
class Material:
    """Material properties for the tension member.

    Parameters
    ----------
    Fy : float
        Yield strength, in MPa.
    Fu : float
        Tensile (ultimate) strength, in MPa.
    """
    Fy: float
    Fu: float


@dataclass
class AngleSection:
    """A steel angle section definition.

    Only the parameters needed for tension design are stored here.

    Parameters
    ----------
    designation : str
        The nominal name of the section (e.g. ``L203x203x25*``).
    leg1 : float
        Width of the first leg in mm.  For equal‑leg angles this equals
        ``leg2``.
    leg2 : float
        Width of the second leg in mm.
    thickness : float
        Thickness of the legs in mm.
    area : Optional[float]
        Gross area in mm².  If not supplied the script approximates
        area as ``t * (leg1 + leg2 - t)``.
    """
    designation: str
    leg1: float
    leg2: float
    thickness: float
    area: Optional[float] = None

    def gross_area(self) -> float:
        """Return the gross area of the angle in mm².

        If an area value has been provided this is returned.  Otherwise
        the gross area is approximated as ``t * (b1 + b2 - t)``, which
        assumes a small fillet radius.  This approximation is commonly
        used for design calculations and tends to underpredict area
        slightly (conservative).  For precise values consult the
        manufacturer’s catalogue or handbook.
        """
        if self.area is not None and not math.isnan(self.area):
            return self.area
        return self.thickness * (self.leg1 + self.leg2 - self.thickness)


@dataclass
class BoltPattern:
    """Definition of the bolt group on the connected leg.

    Parameters
    ----------
    n_lines : int
        Number of bolt lines (columns) on the connected leg.  Typical
        values are 1 or 2 for single‑angle connections.
    bolts_per_line : int
        Number of bolts in each line (rows).  Must be at least 2 to
        enable stagger effects.
    pitch : float
        Spacing between rows (centre to centre) along the load
        direction, in mm.
    gauge : float
        Spacing between bolt lines measured perpendicular to the load
        direction (transverse spacing), in mm.  If only one bolt line
        is provided this value represents the distance from the heel or
        free edge to the bolt line; it can be used for guidance when
        computing stagger additions but does not affect the net area
        calculation directly for the one‑line case.
    edge_end : float
        End distance from the end of the member to the centre of the
        first bolt, measured along the load direction, in mm.
    edge_trans : float
        Transverse edge distance from the bolt line(s) to the free
        edge of the angle, in mm.  This affects the block shear
        calculation.
    """
    n_lines: int
    bolts_per_line: int
    pitch: float
    gauge: float
    edge_end: float
    edge_trans: float


# ----------------------------------------------------------------------------
# Net area calculation routines
# ----------------------------------------------------------------------------

def enumerate_net_paths(
    connected_leg_width: float,
    bolt_pattern: BoltPattern,
    hole_dia: float,
    hole_allowance: float,
    t: float,
) -> List[Dict[str, float]]:
    """Generate potential net fracture paths through the connected leg.

    The net area is calculated as ``w_n * t + Σ (stagger additions) * t``
    where ``w_n`` is the net width normal to the load direction, minus
    hole deductions, and ``stagger additions`` come from diagonal
    segments between bolt lines.  This routine enumerates a set of
    likely paths but does not guarantee finding the absolute minimum
    net area for very unusual patterns.  It should suffice for most
    one‑ or two‑line bolt arrangements typical of single‑angle
    connections.

    Parameters
    ----------
    connected_leg_width : float
        Overall width of the connected leg (along the fracture plane),
        in mm.
    bolt_pattern : BoltPattern
        Details of the bolt group geometry.
    hole_dia : float
        Nominal hole diameter used for net area deduction, in mm.
    hole_allowance : float
        Additional allowance applied to the hole diameter (e.g. for
        punched holes).  The effective hole size becomes
        ``hole_dia + hole_allowance``.
    t : float
        Thickness of the section, in mm.

    Returns
    -------
    List of dictionaries describing each candidate path.  Each entry
    contains:

    ``An_mm2`` : float
        Net area of the path in mm² (before shear‑lag reduction).
    ``wn_mm`` : float
        Net width normal to the load direction (after hole deductions), in mm.
    ``n_holes`` : int
        Number of holes cut through by the path.
    ``stagger_term`` : float
        Sum of stagger terms ``s²/(4g)`` associated with diagonal
        segments, in mm.
    ``description`` : str
        Human‑readable description of the path.
    """
    paths: List[Dict[str, float]] = []
    d_eff = hole_dia + hole_allowance

    # For one bolt line there are no transverse staggers.  The only
    # critical net section is straight across that line.  However, we
    # consider different numbers of holes (typically one) for
    # completeness.  In standard practice only one hole is crossed.
    if bolt_pattern.n_lines == 1:
        # Path through one hole in a single row
        wn = connected_leg_width - 1 * d_eff
        An = wn * t
        paths.append({
            "An_mm2": An,
            "wn_mm": wn,
            "n_holes": 1,
            "stagger_term": 0.0,
            "description": "Straight (cuts 1 hole in one line)",
        })
        return paths

    # For two bolt lines we provide a set of candidate paths.  We
    # restrict our search to at most bolts_per_line holes to keep
    # enumeration reasonable.  More holes cut typically yields larger
    # deductions and lower net area, but some of these are not
    # physically feasible for a single cut.  We therefore include
    # straight paths through one hole and two holes, as well as
    # zig‑zag paths that alternate between lines across successive
    # rows.
    nrows = bolt_pattern.bolts_per_line

    # Straight path through one hole on a row (cutting only one bolt)
    wn = connected_leg_width - 1 * d_eff
    An = wn * t
    paths.append({
        "An_mm2": An,
        "wn_mm": wn,
        "n_holes": 1,
        "stagger_term": 0.0,
        "description": "Straight across one bolt (1 hole)",
    })

    # Straight path through both bolt lines on the same row (cutting two holes)
    wn2 = connected_leg_width - 2 * d_eff
    An2 = wn2 * t
    paths.append({
        "An_mm2": An2,
        "wn_mm": wn2,
        "n_holes": 2,
        "stagger_term": 0.0,
        "description": "Straight across two bolts (2 holes)",
    })

    # Zig‑zag across rows: we alternate between the two lines.  For k
    # holes cut, there are (k − 1) diagonal segments, each adding
    # ``s²/(4g)`` (CSA Clause 12.3.1).  We calculate the net width as
    # ``connected_leg_width − k*d_eff`` and the stagger term as
    # ``(k − 1)*(pitch²/(4*g))``.
    for k in range(2, nrows + 1):
        n_holes = k
        stagger = (k - 1) * (bolt_pattern.pitch ** 2) / (4.0 * bolt_pattern.gauge)
        wn_k = connected_leg_width - n_holes * d_eff
        An_k = (wn_k + stagger) * t
        paths.append({
            "An_mm2": An_k,
            "wn_mm": wn_k,
            "n_holes": n_holes,
            "stagger_term": stagger,
            "description": f"Zig‑zag across {k} bolts ({k-1} stagger terms)",
        })

    # Remove any paths with non‑positive net width (physically infeasible)
    paths = [p for p in paths if p["wn_mm"] > 0 and p["An_mm2"] > 0]
    return paths


def effective_net_area_angle_one_leg(An: float, n_transverse_lines: int) -> Tuple[float, float]:
    """Apply the shear‑lag reduction for angles connected by one leg.

    According to CSA S16‑14 Clause 12.3.3.3(b), the effective net area
    ``A_ne`` for an angle connected by only one leg is taken as:

    * ``0.80 An`` when there are four or more transverse lines of
      fasteners;
    * ``0.60 An`` when there are fewer than four transverse lines of
      fasteners.

    The number of transverse lines corresponds to the number of bolt
    rows along the connected leg (i.e. ``bolts_per_line``).

    Parameters
    ----------
    An : float
        Net area of the governing path, in mm².
    n_transverse_lines : int
        Number of bolt rows (lines perpendicular to the load).

    Returns
    -------
    (Ane, U) : tuple of (float, float)
        Effective net area and the reduction factor U applied.
    """
    if n_transverse_lines >= 4:
        U = 0.80
    else:
        U = 0.60
    return U * An, U


def calc_gross_yielding(Ag: float, Fy: float) -> Calc:
    """Calculate the gross section yielding resistance in kN."""
    Tr = PHI_YIELD * Ag * Fy
    val_kN = Tr / 1_000.0
    steps = [
        "Equation: Tr,y = φy × Ag × Fy",
        f"Substitute: = {PHI_YIELD:.2f} × {Ag:,.1f} × {Fy:.1f} / 1000",
        f"Result: Tr,y = {val_kN:,.1f} kN",
        "Note: MPa = N/mm², divide by 1000 to convert N → kN",
    ]
    return Calc("Gross Section Yielding", val_kN, "kN", steps)


def calc_net_fracture(Ane: float, Fu: float, An: float, U: float) -> Calc:
    """Calculate the net section fracture resistance in kN."""
    Tr = PHI_FRACTURE * Ane * Fu
    val_kN = Tr / 1_000.0
    steps = [
        "Equation: Ane = U × An",
        f"Substitute: Ane = {U:.2f} × {An:,.1f} = {Ane:,.1f} mm²",
        "Equation: Tr,u = φu × Ane × Fu",
        f"Substitute: = {PHI_FRACTURE:.2f} × {Ane:,.1f} × {Fu:.1f} / 1000",
        f"Result: Tr,u = {val_kN:,.1f} kN",
    ]
    return Calc("Net Section Fracture", val_kN, "kN", steps)
def calc_block_shear(
    An_tension: float,
    Ag_shear: float,
    Fy: float,
    Fu: float,
    Ut: float,
) -> Calc:
    """Compute the block shear resistance in kN.

    The simplified block shear resistance per CSA S16‑14 Clause 13.11 is
    expressed as:

    .. math::

       Tr_{bs} = φU\bigl[ U_t A_{nt} F_u + 0.6\,A_{gv}\,\tfrac{F_y + F_u}{2} \bigr]

    where:

    * φU is 0.75 for fracture
    * U_t is the efficiency factor (0.6 for angles connected by one leg)
    * A_nt is the net tension area of the block (mm²)
    * A_gv is the gross shear area of the block (mm²)
    * F_y and F_u are in MPa

    Parameters
    ----------
    An_tension : float
        Net tension area on the block, in mm².
    Ag_shear : float
        Gross shear area on the block, in mm² (sum of shear planes).
    Fy : float
        Yield strength, in MPa.
    Fu : float
        Ultimate tensile strength, in MPa.
    Ut : float
        Efficiency factor for block shear (CSA Table for angles: 0.6).

    Returns
    -------
    float
        Block shear resistance, in kN.
    """
    term1 = Ut * An_tension * Fu
    term2 = 0.6 * Ag_shear * (Fy + Fu) / 2.0
    Tr = PHI_FRACTURE * (term1 + term2)
    val_kN = Tr / 1_000.0
    steps = [
        "Equation: Tr,bs = φu × [Ut × Ant × Fu + 0.6 × Agv × (Fy + Fu)/2]",
        f"Term 1: Ut × Ant × Fu = {Ut:.2f} × {An_tension:,.1f} × {Fu:.1f} = {term1:,.1f} N",
        f"Term 2: 0.6 × Agv × (Fy + Fu)/2 = 0.6 × {Ag_shear:,.1f} × ({Fy:.1f} + {Fu:.1f})/2 = {term2:,.1f} N",
        f"Substitute: = {PHI_FRACTURE:.2f} × ({term1:,.1f} + {term2:,.1f}) / 1000",
        f"Result: Tr,bs = {val_kN:,.1f} kN",
    ]
    return Calc("Block Shear", val_kN, "kN", steps)


def estimate_block_areas(
    angle: AngleSection,
    bolt: BoltPattern,
    connected_leg_width: float,
    hole_dia: float,
    hole_allowance: float,
) -> Tuple[float, float]:
    """Estimate net tension and gross shear areas for block shear.

    This helper provides a conservative first‑pass estimate of the
    block shear areas.  It assumes the block tears out around the
    bolt group following two shear planes parallel to the load
    direction and one tension plane at the end of the bolt group.

    The gross shear area ``A_gv`` is taken as twice the shear
    length ``L_v`` multiplied by the thickness.  ``L_v`` equals
    ``edge_end + (n_rows-1)*pitch``.

    The net tension area ``A_nt`` is taken as ``(edge_trans − 0.5*
    d_eff) * thickness``, where ``edge_trans`` is the transverse edge
    distance from the bolt line to the free edge.  This assumes a
    single shear plane at the free edge; if two bolt lines exist the
    bolt group will typically tear along the outermost bolt line.  A
    full block shear evaluation may require considering multiple
    potential tear paths; this function returns a single estimate.
    """
    t = angle.thickness
    nrows = bolt.bolts_per_line
    d_eff = hole_dia + hole_allowance
    # Shear length parallel to load
    Lv = bolt.edge_end + (nrows - 1) * bolt.pitch
    Agv = 2.0 * Lv * t  # two shear planes
    # Net tension plane across block width
    # Use the lesser of gauge and edge distance for two lines; for one line
    # gauge is taken as the distance from bolt line to heel or free edge.
    b_net = max(0.0, bolt.edge_trans - 0.5 * d_eff)
    An_tension = b_net * t
    return An_tension, Agv


# ----------------------------------------------------------------------------
# Streamlit application
# ----------------------------------------------------------------------------

def load_angle_table(path: str) -> pd.DataFrame:
    """Load the user‑supplied angle properties table.

    The Excel file is expected to contain a column labelled
    ``Designation`` (or similar), along with dimensions labelled
    ``d (mm)``, ``b (mm)`` and ``t (mm)`` for the leg sizes and
    thickness, and ``Area (mm²)`` for the gross area.  Additional
    columns are ignored.  If the file does not contain these columns
    the user will be warned.
    """
    df = pd.read_excel(path, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    # Attempt to locate required fields
    def find_col(possibles: List[str]) -> Optional[str]:
        for p in possibles:
            for c in df.columns:
                if c.lower().replace(" ", "").replace("_", "") == p.lower().replace(" ", "").replace("_", ""):
                    return c
        return None

    design_col = find_col(["Designation", "Section", "Shape"])
    b_col = find_col(["b (mm)", "Leg 1", "Leg1", "b"])
    d_col = find_col(["d (mm)", "Leg 2", "Leg2", "d"])
    t_col = find_col(["t (mm)", "Thickness", "thk", "t"])
    area_col = find_col(["Area (mm²)", "Area", "Ag"])

    if None in (design_col, b_col, d_col, t_col):
        raise ValueError(
            "The angle table must include columns for designation, b, d and t. "
            "Please verify the Excel file has columns labelled 'Designation', 'b (mm)', "
            "'d (mm)' and 't (mm)'."
        )

    out = pd.DataFrame({
        "designation": df[design_col].astype(str),
        "leg1": pd.to_numeric(df[b_col], errors="coerce"),
        "leg2": pd.to_numeric(df[d_col], errors="coerce"),
        "thickness": pd.to_numeric(df[t_col], errors="coerce"),
    })
    if area_col is not None:
        out["area"] = pd.to_numeric(df[area_col], errors="coerce")
    else:
        out["area"] = np.nan
    out = out.dropna(subset=["leg1", "leg2", "thickness"]).reset_index(drop=True)
    return out


def main() -> None:
    st.set_page_config(page_title="Tension Angle (One‑Leg) Calculator", layout="centered")
    st.title("CSA S16 Single‑Angle Tension Member Calculator")
    st.write(
        "This tool evaluates the tensile resistance of a single‐angle member "
        "connected by one leg using bolts, according to CSA S16‐14.  Select "
        "an angle section, define the bolt pattern and material properties, "
        "and the app will report the governing resistance from gross yielding, "
        "net fracture (with stagger) and block shear.  Results are reported "
        "in kilonewtons.  All input dimensions are in millimetres."
    )

    st.divider()

    # Angle section data
    st.subheader("Angle Section Data")
    default_path = "Angle Properties Table.xlsx"
    angle_file = st.text_input("Angle properties Excel file", value=default_path)
    load_button = st.button("Load table")

    if "angle_table" not in st.session_state:
        st.session_state["angle_table"] = None
        st.session_state["load_error"] = None

    if load_button or st.session_state["angle_table"] is None:
        try:
            table = load_angle_table(angle_file)
            st.session_state["angle_table"] = table
            st.session_state["load_error"] = None
        except Exception as e:
            st.session_state["angle_table"] = None
            st.session_state["load_error"] = str(e)

    angle_df = st.session_state.get("angle_table")
    if st.session_state.get("load_error"):
        st.error(st.session_state["load_error"])
        return
    if angle_df is None or angle_df.empty:
        st.warning("No angle data loaded.  Please select a valid Excel file and click 'Load table'.")
        return

    st.divider()

    # Section and material
    st.subheader("Section and Material")
    chosen = st.selectbox("Angle designation", angle_df["designation"].tolist())
    row = angle_df.loc[angle_df["designation"] == chosen].iloc[0]
    section = AngleSection(
        designation=str(row["designation"]),
        leg1=float(row["leg1"]),
        leg2=float(row["leg2"]),
        thickness=float(row["thickness"]),
        area=float(row.get("area", float("nan"))),
    )

    st.markdown(
        f"**{section.designation}**  –  Legs = {section.leg1:.1f} × {section.leg2:.1f} mm,  "
        f"t = {section.thickness:.2f} mm"
    )
    st.markdown(f"Approx. gross area Ag ≈ {section.gross_area():,.0f} mm²")

    # Material properties
    Fy_input = st.number_input("Yield strength Fy (MPa)", min_value=100.0, max_value=800.0, value=350.0, step=10.0)
    Fu_input = st.number_input("Ultimate strength Fu (MPa)", min_value=200.0, max_value=900.0, value=450.0, step=10.0)
    material = Material(Fy=Fy_input, Fu=Fu_input)

    st.divider()

    # Bolt and hole
    st.subheader("Bolt and Hole")
    bolt_size = st.selectbox("Bolt size", list(BOLT_DIAMETERS_MM.keys()))
    hole_type = st.selectbox("Hole type", HOLE_TYPES, index=0)
    d_hole_nom = STANDARD_HOLE_DIAMETERS_MM.get(bolt_size, BOLT_DIAMETERS_MM[bolt_size] + 2.0)
    hole_dia = st.number_input(
        "Hole diameter d_h (mm)", min_value=0.0, max_value=100.0, value=float(d_hole_nom), step=1.0,
        help="Nominal hole diameter used for net area deduction."
    )
    hole_allowance = st.number_input(
        "Hole allowance (mm)", min_value=0.0, max_value=10.0, value=0.0, step=0.5,
        help="Additional allowance applied to hole diameter (e.g. +2 mm for punched holes)."
    )

    st.divider()

    # Connection geometry
    st.subheader("Connection Geometry")
    connected_leg_choice = st.radio(
        "Which leg is connected?",
        ["Leg 1", "Leg 2"],
        index=0,
        help="The connected leg is the one bolted to the gusset or supporting member."
    )
    connected_leg_width = section.leg1 if connected_leg_choice == "Leg 1" else section.leg2

    # Bolt pattern
    n_lines = st.selectbox("Number of bolt lines (columns)", [1, 2], index=0)
    bolts_per_line = st.number_input(
        "Bolts per line (rows)", min_value=2, max_value=20, value=4, step=1,
        help="Number of bolts along the load direction in each line."
    )
    pitch = st.number_input(
        "Pitch s (mm)", min_value=10.0, max_value=300.0, value=80.0, step=5.0,
        help="Spacing between bolt rows along the load direction."
    )
    gauge = st.number_input(
        "Gauge g (mm)", min_value=1.0, max_value=300.0, value=60.0, step=5.0,
        help="Spacing between bolt lines measured perpendicular to load; for one line this can be the distance from heel to bolt line."
    )
    edge_end = st.number_input(
        "End distance e (mm)", min_value=5.0, max_value=300.0, value=40.0, step=5.0,
        help="Distance from end of angle to centre of first bolt along the load direction."
    )
    edge_trans = st.number_input(
        "Transverse edge distance (mm)", min_value=1.0, max_value=200.0, value=30.0, step=5.0,
        help="Distance from bolt line(s) to free edge of connected leg."
    )

    bolt_pattern = BoltPattern(
        n_lines=int(n_lines),
        bolts_per_line=int(bolts_per_line),
        pitch=float(pitch),
        gauge=float(gauge),
        edge_end=float(edge_end),
        edge_trans=float(edge_trans),
    )

    # Factored demand for utilisation check
    Tf = st.number_input(
        "Factored tension demand T_f (kN)", min_value=0.0, max_value=5000.0, value=0.0, step=10.0,
        help="Optional: provide the factored tensile force on the member (ULS).  Utilisation will be computed."
    )

    # Perform calculations
    Ag = section.gross_area()
    calc_yield = calc_gross_yielding(Ag, material.Fy)

    # Enumerate net area paths
    net_paths = enumerate_net_paths(
        connected_leg_width=connected_leg_width,
        bolt_pattern=bolt_pattern,
        hole_dia=hole_dia,
        hole_allowance=hole_allowance,
        t=section.thickness,
    )
    if not net_paths:
        st.error("No feasible net fracture paths found.  Check bolt spacing, hole diameter and leg width.")
        return
    controlling_path = min(net_paths, key=lambda p: p["An_mm2"])
    An = controlling_path["An_mm2"]
    n_trans = bolt_pattern.bolts_per_line
    Ane, U_sl = effective_net_area_angle_one_leg(An, n_transverse_lines=n_trans)
    calc_fracture = calc_net_fracture(Ane, material.Fu, An, U_sl)

    # Block shear estimate
    An_bs, Agv_bs = estimate_block_areas(
        angle=section,
        bolt=bolt_pattern,
        connected_leg_width=connected_leg_width,
        hole_dia=hole_dia,
        hole_allowance=hole_allowance,
    )
    # Use Ut = 0.6 for angles connected by one leg (per CISC fig)
    Ut_default = 0.60
    Ut = st.slider(
        "Block shear efficiency factor U_t", min_value=0.3, max_value=1.0, value=float(Ut_default), step=0.05,
        help="CSA suggests U_t = 0.6 for angles connected by one leg; adjust if a different configuration applies."
    )
    calc_block = calc_block_shear(
        An_tension=An_bs,
        Ag_shear=Agv_bs,
        Fy=material.Fy,
        Fu=material.Fu,
        Ut=Ut,
    )

    R_gov = min(calc_yield.value, calc_fracture.value, calc_block.value)

    st.divider()

    # Connection Diagram
    st.header("Connection Diagram")
    col_diag1, col_diag2 = st.columns([3, 1])
    with col_diag2:
        show_fracture = st.checkbox("Show fracture line", value=True)
        show_block = st.checkbox("Show block shear", value=True)

    svg_diagram = generate_connection_svg(
        n_lines=bolt_pattern.n_lines,
        bolts_per_line=bolt_pattern.bolts_per_line,
        pitch=bolt_pattern.pitch,
        gauge=bolt_pattern.gauge,
        edge_end=bolt_pattern.edge_end,
        edge_trans=bolt_pattern.edge_trans,
        leg_width=connected_leg_width,
        thickness=section.thickness,
        hole_dia=hole_dia,
        show_fracture=show_fracture,
        show_block_shear=show_block,
    )

    with col_diag1:
        components.html(svg_diagram, height=320)

    st.divider()

    # Layout results
    st.header("Results")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Gross Yielding (kN)", f"{calc_yield.value:,.1f}")
    col2.metric("Net Fracture (kN)", f"{calc_fracture.value:,.1f}")
    col3.metric("Block Shear (kN)", f"{calc_block.value:,.1f}")
    col4.metric("Governing (kN)", f"{R_gov:,.1f}")

    # Calculation steps (shown work)
    st.header("Calculations (shown work)")

    # 2.3 Gross Section Yielding
    st.header("2.3 Gross Section Yielding")
    st.latex(r"\phi T_y = \phi A_g F_y")
    st.markdown(f"""
**Substitution:**

φ = {PHI_YIELD}  
A_g = {Ag:,.1f} mm²  
F_y = {material.Fy:.1f} MPa  

$$
\\phi T_y = {PHI_YIELD} \\times {Ag:,.1f} \\times {material.Fy:.1f} / 1000
$$

**Result:**  
### φTᵧ = **{calc_yield.value:,.1f} kN**
""")

    # 2.4 Net Section Fracture
    st.header("2.4 Net Section Fracture (CSA S16-14 13.3.2)")
    st.latex(r"\phi T_u = \phi U A_n F_u")

    # Build paths dataframe for display
    df_paths_display = pd.DataFrame([
        {
            "Path": p["description"],
            "Holes cut": p["n_holes"],
            "Net width wₙ (mm)": f"{p['wn_mm']:.1f}",
            "Net area Aₙ (mm²)": f"{p['An_mm2']:.1f}",
            "Effective area U·Aₙ (mm²)": f"{U_sl * p['An_mm2']:.1f}"
        }
        for p in net_paths
    ])

    st.subheader("Net Fracture Paths Considered")
    st.dataframe(df_paths_display, use_container_width=True)

    wn = controlling_path["wn_mm"]
    t = section.thickness

    st.markdown(f"""
$$
A_n = {wn:.1f} \\times {t:.1f} = {An:.1f} \\text{{ mm²}}
$$

$$
A_{{ne}} = U \\cdot A_n = {U_sl:.2f} \\times {An:.1f} = {Ane:.1f} \\text{{ mm²}}
$$

$$
\\phi T_u = {PHI_FRACTURE} \\times {U_sl:.2f} \\times {An:.1f} \\times {material.Fu:.1f} / 1000
$$

### φTᵤ = **{calc_fracture.value:,.1f} kN**
""")

    # 2.5 Block Shear
    st.header("2.5 Block Shear")
    st.latex(r"\phi T_{bs} = \phi U_t (0.6 F_u A_{nv} + F_u A_{nt})")

    # Calculate block shear geometry
    nrows = bolt_pattern.bolts_per_line
    d_eff = hole_dia + hole_allowance
    Lv = bolt_pattern.edge_end + (nrows - 1) * bolt_pattern.pitch
    t = section.thickness
    e = bolt_pattern.edge_trans

    st.markdown(f"""
**Shear Plane Area:**  
$$
A_{{gv}} = 2 \\cdot L_v \\cdot t = 2 \\times {Lv:.1f} \\times {t:.1f} = {Agv_bs:.1f} \\text{{ mm²}}
$$

**Tension Plane Area:**  
$$
A_{{nt}} = (e - 0.5 \\cdot d_{{eff}}) \\cdot t = ({e:.1f} - 0.5 \\times {d_eff:.1f}) \\times {t:.1f} = {An_bs:.1f} \\text{{ mm²}}
$$
""")

    Anv = Agv_bs  # Using gross shear area
    Ant = An_bs

    st.markdown(f"""
$$
\\phi T_{{bs}} = {PHI_FRACTURE} \\times {Ut:.2f} \\times (0.6 \\times {material.Fu:.1f} \\times {Anv:.1f} + {material.Fu:.1f} \\times {Ant:.1f}) / 1000
$$

### φTᵦₛ = **{calc_block.value:.1f} kN**
""")

    # 2.6 Governing Tensile Resistance
    st.header("2.6 Governing Tensile Resistance")

    results = {
        "Gross yielding": calc_yield.value,
        "Net fracture": calc_fracture.value,
        "Block shear": calc_block.value
    }

    governing_mode = min(results, key=results.get)
    governing_value = results[governing_mode]

    st.markdown(f"""
## Governing Limit State: **{governing_mode}**

### Design Resistance:
# **{governing_value:.1f} kN**
""")

    if Tf > 0 and R_gov > 0:
        utilisation = Tf / R_gov
        st.subheader("Utilisation")
        st.progress(min(utilisation, 1.0))
        st.write(f"T_f / R = {utilisation:.3f}")
        if utilisation <= 1.0:
            st.success("Adequate by strength limit states.")
        else:
            st.error("Insufficient capacity by these limit states.")

    st.divider()
    st.subheader("Audit Trail")
    st.write("**Controlling net fracture path:** ", controlling_path["description"])
    st.write(
        f"Net width w_n = {controlling_path['wn_mm']:.2f} mm, "
        f"stagger addition = {controlling_path['stagger_term']:.2f} mm"
    )
    st.write(f"Net area An = {An:,.1f} mm²")
    st.write(f"Effective net area Ane = U · An = {U_sl:.2f} × {An:,.1f} = {Ane:,.1f} mm²")

    # Present a table of all candidate net paths
    df_paths = pd.DataFrame(net_paths)
    df_paths_display = df_paths[["description", "n_holes", "wn_mm", "stagger_term", "An_mm2"]]
    df_paths_display.rename(
        columns={
            "description": "Path",
            "n_holes": "# holes cut",
            "wn_mm": "w_n (mm)",
            "stagger_term": "Stagger (mm)",
            "An_mm2": "An (mm²)",
        },
        inplace=True,
    )
    st.write("**Net area paths considered:**")
    st.dataframe(df_paths_display, width="stretch")

    st.write("**Block shear estimate:**")
    st.write(
        f"Net tension area A_nt ≈ (edge_trans − 0.5 d_eff) · t = {An_bs:,.1f} mm²\n"
        f"Gross shear area A_gv ≈ 2 · L_v · t = {Agv_bs:,.1f} mm²"
    )

    st.write(
        "\n*Note:* This tool applies simplified net fracture and block shear logic "
        "appropriate for typical one‑ or two‑line bolt groups on single angles.  "
        "More complex patterns or unusual geometries may require manual checks "
        "of additional fracture paths and block shear planes.  Always verify "
        "that minimum edge distances, pitch and gauge values meet the detailing "
        "requirements of CSA S16 and your bolt supplier."
    )


if __name__ == "__main__":
    main()