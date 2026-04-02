"""
CSA S16 Tension Angle (One-Leg Connected) Calculator
=====================================================

Evaluates a single-angle tension member connected by one leg using bolts,
per CSA S16-14:
  * Gross section yielding     (Cl. 13.2(a))
  * Net section fracture       (Cl. 13.2(b)) with shear-lag reduction
  * Block shear                (Cl. 13.11)

All dimensions in mm; all forces in kN.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from connection_diagram import generate_connection_svg


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PHI_YIELD    = 0.90   # gross yielding
PHI_FRACTURE = 0.75   # net fracture and block shear

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANGLE_FILE = DATA_DIR / "Angle Properties Table.xlsx"

BOLT_DIAMETERS_MM: Dict[str, float] = {
    "M16": 16.0, "M20": 20.0, "M22": 22.0, "M24": 24.0,
    "M27": 27.0, "M30": 30.0, "M36": 36.0,
}
STANDARD_HOLE_DIAMETERS_MM: Dict[str, float] = {
    "M16": 18.0, "M20": 22.0, "M22": 24.0, "M24": 26.0,
    "M27": 30.0, "M30": 33.0, "M36": 39.0,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Calc:
    name: str
    value: float
    units: str
    steps: List[str]


@dataclass
class Material:
    Fy: float
    Fu: float


@dataclass
class AngleSection:
    designation: str
    leg1: float
    leg2: float
    thickness: float
    area: Optional[float] = None

    def gross_area(self) -> float:
        if self.area is not None and not math.isnan(self.area):
            return self.area
        return self.thickness * (self.leg1 + self.leg2 - self.thickness)


@dataclass
class BoltPattern:
    n_lines: int
    bolts_per_line: int
    pitch: float
    gauge: float
    edge_end: float
    edge_trans: float


# ---------------------------------------------------------------------------
# Section data loading
# ---------------------------------------------------------------------------

def load_angle_table(path: str | Path) -> pd.DataFrame:
    df = pd.read_excel(path, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    def find_col(possibles: List[str]) -> Optional[str]:
        for p in possibles:
            for c in df.columns:
                if c.lower().replace(" ", "").replace("_", "") == p.lower().replace(" ", "").replace("_", ""):
                    return c
        return None

    design_col = find_col(["Designation", "Section", "Shape"])
    b_col  = find_col(["b (mm)", "Leg 1", "Leg1", "b"])
    d_col  = find_col(["d (mm)", "Leg 2", "Leg2", "d"])
    t_col  = find_col(["t (mm)", "Thickness", "thk", "t"])
    area_col = find_col(["Area (mm2)", "Area (mm)", "Area", "Ag"])

    if None in (design_col, b_col, d_col, t_col):
        raise ValueError(
            "Angle table must include Designation, b, d, and t columns. "
            f"Found columns: {list(df.columns)}"
        )

    out = pd.DataFrame({
        "designation": df[design_col].astype(str),
        "leg1":        pd.to_numeric(df[b_col],  errors="coerce"),
        "leg2":        pd.to_numeric(df[d_col],  errors="coerce"),
        "thickness":   pd.to_numeric(df[t_col],  errors="coerce"),
        "area":        pd.to_numeric(df[area_col], errors="coerce") if area_col else np.nan,
    })
    return out.dropna(subset=["leg1", "leg2", "thickness"]).reset_index(drop=True)


@st.cache_data
def _load_table(path: str) -> pd.DataFrame:
    return load_angle_table(path)


# ---------------------------------------------------------------------------
# Net area calculations
# ---------------------------------------------------------------------------

def enumerate_net_paths(
    connected_leg_width: float,
    bolt_pattern: BoltPattern,
    hole_dia: float,
    hole_allowance: float,
    t: float,
) -> List[Dict]:
    paths: List[Dict] = []
    d_eff = hole_dia + hole_allowance

    if bolt_pattern.n_lines == 1:
        wn = connected_leg_width - d_eff
        paths.append({
            "An_mm2": max(wn * t, 0.0),
            "wn_mm": wn,
            "n_holes": 1,
            "stagger_term": 0.0,
            "description": "Straight — 1 hole",
        })
        return [p for p in paths if p["An_mm2"] > 0]

    nrows = bolt_pattern.bolts_per_line

    # Straight through 1 hole
    wn = connected_leg_width - d_eff
    paths.append({
        "An_mm2": wn * t,
        "wn_mm": wn,
        "n_holes": 1,
        "stagger_term": 0.0,
        "description": "Straight across 1 bolt (1 hole)",
    })

    # Straight through 2 holes
    wn2 = connected_leg_width - 2 * d_eff
    paths.append({
        "An_mm2": wn2 * t,
        "wn_mm": wn2,
        "n_holes": 2,
        "stagger_term": 0.0,
        "description": "Straight across 2 bolts (2 holes)",
    })

    # Zig-zag paths (CSA S16 Cl. 12.3.1 stagger rule)
    for k in range(2, nrows + 1):
        stagger = (k - 1) * (bolt_pattern.pitch ** 2) / (4.0 * bolt_pattern.gauge)
        wn_k = connected_leg_width - k * d_eff
        An_k = (wn_k + stagger) * t
        paths.append({
            "An_mm2": An_k,
            "wn_mm": wn_k,
            "n_holes": k,
            "stagger_term": stagger,
            "description": f"Zig-zag {k} bolts ({k-1} stagger term{'s' if k>2 else ''})",
        })

    return [p for p in paths if p["wn_mm"] > 0 and p["An_mm2"] > 0]


def shear_lag_factor(n_transverse_lines: int) -> Tuple[float, str]:
    """CSA S16-14 Cl. 12.3.3.3(b): one-leg connected angles."""
    if n_transverse_lines >= 4:
        return 0.80, ">= 4 transverse bolt rows  →  U = 0.80"
    return 0.60, "< 4 transverse bolt rows  →  U = 0.60"


# ---------------------------------------------------------------------------
# Limit state calculations
# ---------------------------------------------------------------------------

def calc_gross_yielding(Ag: float, Fy: float) -> Calc:
    Tr = PHI_YIELD * Ag * Fy
    kN = Tr / 1000.0
    return Calc(
        "Gross Section Yielding", kN, "kN",
        [
            "Tr,y = phi_y * Ag * Fy",
            f"     = {PHI_YIELD} * {Ag:,.1f} * {Fy:.1f} / 1000",
            f"     = {kN:,.1f} kN",
        ],
    )


def calc_net_fracture(Ane: float, Fu: float, An: float, U: float) -> Calc:
    Tr = PHI_FRACTURE * Ane * Fu
    kN = Tr / 1000.0
    return Calc(
        "Net Section Fracture", kN, "kN",
        [
            "Ane = U * An",
            f"    = {U:.2f} * {An:,.1f} = {Ane:,.1f} mm^2",
            "Tr,u = phi_u * Ane * Fu",
            f"     = {PHI_FRACTURE} * {Ane:,.1f} * {Fu:.1f} / 1000",
            f"     = {kN:,.1f} kN",
        ],
    )


def calc_block_shear(
    An_tension: float,
    Ag_shear: float,
    Fy: float,
    Fu: float,
    Ut: float,
) -> Calc:
    """CSA S16-14 Cl. 13.11: Tr,bs = phi_u * [Ut*Ant*Fu + 0.6*Agv*(Fy+Fu)/2]"""
    term1 = Ut * An_tension * Fu
    term2 = 0.6 * Ag_shear * (Fy + Fu) / 2.0
    kN = PHI_FRACTURE * (term1 + term2) / 1000.0
    return Calc(
        "Block Shear", kN, "kN",
        [
            "Tr,bs = phi_u * [Ut*Ant*Fu + 0.6*Agv*(Fy+Fu)/2]",
            f"Term1 = {Ut:.2f} * {An_tension:,.1f} * {Fu:.1f} = {term1:,.1f} N",
            f"Term2 = 0.6 * {Ag_shear:,.1f} * ({Fy:.1f}+{Fu:.1f})/2 = {term2:,.1f} N",
            f"Tr,bs = {PHI_FRACTURE} * ({term1:,.1f}+{term2:,.1f}) / 1000",
            f"      = {kN:,.1f} kN",
        ],
    )


def estimate_block_areas(
    bolt: BoltPattern,
    t: float,
    hole_dia: float,
    hole_allowance: float,
) -> Tuple[float, float]:
    """Conservative estimate of Ant and Agv for one-leg angle block shear."""
    d_eff = hole_dia + hole_allowance
    nrows = bolt.bolts_per_line
    Lv = bolt.edge_end + (nrows - 1) * bolt.pitch
    Agv = 2.0 * Lv * t  # two shear planes
    An_t = max(0.0, bolt.edge_trans - 0.5 * d_eff) * t
    return An_t, Agv


# ---------------------------------------------------------------------------
# Streamlit application
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("CSA S16 — Single-Angle Tension Member")
    st.caption(
        "Gross yielding (Cl. 13.2a), net fracture with shear lag (Cl. 13.2b, 12.3.3.3), "
        "and block shear (Cl. 13.11) for a one-leg bolted angle. "
        "All dimensions in mm | forces in kN."
    )
    st.divider()

    # ── Load section table ──────────────────────────────────────────────────
    if "angle_table" not in st.session_state:
        try:
            st.session_state["angle_table"] = _load_table(str(ANGLE_FILE))
            st.session_state["load_error"] = None
        except Exception as exc:
            st.session_state["angle_table"] = None
            st.session_state["load_error"] = str(exc)

    angle_df: Optional[pd.DataFrame] = st.session_state.get("angle_table")
    if st.session_state.get("load_error"):
        st.error(f"Could not load angle table: {st.session_state['load_error']}")
        st.stop()
    if angle_df is None or angle_df.empty:
        st.warning("Angle Properties Table.xlsx not found in data/ folder.")
        st.stop()

    # ── 1. Section & material ───────────────────────────────────────────────
    st.subheader("1. Section & Material")
    col_s1, col_s2, col_s3 = st.columns([2, 1, 1])

    with col_s1:
        chosen = st.selectbox("Angle designation", angle_df["designation"].tolist(), key="tm_des")
    row = angle_df.loc[angle_df["designation"] == chosen].iloc[0]
    section = AngleSection(
        designation=str(row["designation"]),
        leg1=float(row["leg1"]),
        leg2=float(row["leg2"]),
        thickness=float(row["thickness"]),
        area=float(row.get("area", float("nan"))),
    )
    Ag = section.gross_area()

    with col_s2:
        Fy = st.number_input("Fy (MPa)", min_value=100.0, max_value=800.0, value=350.0, step=10.0, key="tm_fy")
    with col_s3:
        Fu = st.number_input("Fu (MPa)", min_value=200.0, max_value=900.0, value=450.0, step=10.0, key="tm_fu")

    material = Material(Fy=Fy, Fu=Fu)

    with st.expander(f"Section properties — {section.designation}"):
        p1, p2, p3 = st.columns(3)
        p1.metric("Leg 1 (mm)", f"{section.leg1:.1f}")
        p2.metric("Leg 2 (mm)", f"{section.leg2:.1f}")
        p3.metric("Thickness t (mm)", f"{section.thickness:.1f}")
        p1.metric("Ag (mm²)", f"{Ag:,.0f}")

    st.divider()

    # ── 2. Connection geometry ──────────────────────────────────────────────
    st.subheader("2. Connection Geometry")
    cg1, cg2 = st.columns(2)

    with cg1:
        connected_leg_choice = st.radio(
            "Connected leg", ["Leg 1", "Leg 2"], index=0, horizontal=True, key="tm_leg"
        )
        connected_leg_width = section.leg1 if connected_leg_choice == "Leg 1" else section.leg2

        n_lines       = st.selectbox("Bolt lines (columns)", [1, 2], index=0, key="tm_nlines")
        bolts_per_line = st.number_input("Bolts per line (rows)", min_value=2, max_value=20, value=4, step=1, key="tm_nbolt")
        pitch         = st.number_input("Pitch s (mm)", min_value=10.0, max_value=300.0, value=80.0, step=5.0, key="tm_pitch")

    with cg2:
        gauge       = st.number_input("Gauge g (mm)", min_value=1.0, max_value=300.0, value=60.0, step=5.0, key="tm_gauge",
                                      help="Transverse bolt spacing; or distance from heel to bolt for 1 line")
        edge_end    = st.number_input("End distance e_1 (mm)", min_value=5.0, max_value=300.0, value=40.0, step=5.0, key="tm_ee")
        edge_trans  = st.number_input("Transverse edge distance e_2 (mm)", min_value=1.0, max_value=200.0, value=30.0, step=5.0, key="tm_et")
        Tf          = st.number_input("Factored demand Tf (kN)", min_value=0.0, max_value=5000.0, value=0.0, step=10.0, key="tm_tf",
                                      help="Optional — shows utilization ratio if entered")

    bolt_pattern = BoltPattern(
        n_lines=int(n_lines),
        bolts_per_line=int(bolts_per_line),
        pitch=float(pitch),
        gauge=float(gauge),
        edge_end=float(edge_end),
        edge_trans=float(edge_trans),
    )

    st.divider()

    # ── 3. Bolt & hole ─────────────────────────────────────────────────────
    st.subheader("3. Bolt & Hole")
    bh1, bh2, bh3 = st.columns(3)

    with bh1:
        bolt_size = st.selectbox("Bolt size", list(BOLT_DIAMETERS_MM.keys()), index=1, key="tm_bolt")
    with bh2:
        d_hole_nom = STANDARD_HOLE_DIAMETERS_MM.get(bolt_size, BOLT_DIAMETERS_MM[bolt_size] + 2.0)
        hole_dia = st.number_input("Hole diameter dh (mm)", min_value=0.0, max_value=100.0,
                                   value=float(d_hole_nom), step=1.0, key="tm_hdiam")
    with bh3:
        hole_allowance = st.number_input("Hole allowance (mm)", min_value=0.0, max_value=10.0,
                                         value=0.0, step=0.5, key="tm_hallw",
                                         help="+2 mm for punched holes per CSA S16")

    Ut = st.slider("Block shear efficiency Ut", min_value=0.3, max_value=1.0, value=0.60, step=0.05, key="tm_ut",
                   help="CSA suggests Ut = 0.60 for angles connected by one leg")

    st.divider()

    # ── 4. Connection diagram ───────────────────────────────────────────────
    st.subheader("4. Connection Diagram")
    diag_col, ctrl_col = st.columns([4, 1])
    with ctrl_col:
        show_fracture = st.checkbox("Show fracture line", value=True, key="tm_sfrac")
        show_block    = st.checkbox("Show block shear",   value=True, key="tm_sblk")

    svg = generate_connection_svg(
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
    with diag_col:
        components.html(svg, height=310)

    st.divider()

    # ── 5. Calculations ─────────────────────────────────────────────────────
    # Gross yielding
    calc_yield = calc_gross_yielding(Ag, material.Fy)

    # Net fracture
    net_paths = enumerate_net_paths(
        connected_leg_width=connected_leg_width,
        bolt_pattern=bolt_pattern,
        hole_dia=hole_dia,
        hole_allowance=hole_allowance,
        t=section.thickness,
    )
    if not net_paths:
        st.error("No feasible net fracture paths. Check bolt spacing, hole diameter and leg width.")
        st.stop()

    governing_path = min(net_paths, key=lambda p: p["An_mm2"])
    An = governing_path["An_mm2"]
    U, U_note = shear_lag_factor(bolt_pattern.bolts_per_line)
    Ane = U * An
    calc_fracture = calc_net_fracture(Ane, material.Fu, An, U)

    # Block shear
    An_bs, Agv_bs = estimate_block_areas(bolt_pattern, section.thickness, hole_dia, hole_allowance)
    calc_block = calc_block_shear(An_bs, Agv_bs, material.Fy, material.Fu, Ut)

    R_gov = min(calc_yield.value, calc_fracture.value, calc_block.value)
    governing_mode = min(
        {"Gross yielding": calc_yield.value, "Net fracture": calc_fracture.value, "Block shear": calc_block.value},
        key=lambda k: {"Gross yielding": calc_yield.value, "Net fracture": calc_fracture.value, "Block shear": calc_block.value}[k],
    )

    # ── 6. Results summary ──────────────────────────────────────────────────
    st.subheader("5. Results")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Gross Yielding (kN)", f"{calc_yield.value:,.1f}")
    r2.metric("Net Fracture (kN)",   f"{calc_fracture.value:,.1f}")
    r3.metric("Block Shear (kN)",    f"{calc_block.value:,.1f}")
    r4.metric(f"Governing — {governing_mode}", f"{R_gov:,.1f} kN")

    if Tf > 0:
        util = Tf / R_gov
        st.progress(min(util, 1.0))
        if util <= 1.0:
            st.success(f"PASS   Tf / Tr = {util:.3f} ({Tf:.1f} / {R_gov:.1f} kN)")
        else:
            st.error(f"FAIL   Tf / Tr = {util:.3f} ({Tf:.1f} / {R_gov:.1f} kN)")

    st.divider()

    # ── 7. Shown work ───────────────────────────────────────────────────────
    st.subheader("6. Calculations — Shown Work")

    with st.expander("Gross Section Yielding (CSA S16 Cl. 13.2a)", expanded=True):
        st.latex(r"\phi T_r = \phi_y \cdot A_g \cdot F_y")
        st.markdown(
            f"φ = {PHI_YIELD} &nbsp;|&nbsp; "
            f"Ag = {Ag:,.1f} mm² &nbsp;|&nbsp; "
            f"Fy = {material.Fy:.1f} MPa"
        )
        st.latex(
            rf"\phi T_r = {PHI_YIELD} \times {Ag:,.1f} \times {material.Fy:.1f} \div 1000"
            rf"= \mathbf{{{calc_yield.value:,.1f}}} \text{{ kN}}"
        )

    with st.expander("Net Section Fracture (CSA S16 Cl. 13.2b + 12.3.3.3)", expanded=True):
        st.latex(r"\phi T_r = \phi_u \cdot A_{ne} \cdot F_u \quad;\quad A_{ne} = U \cdot A_n")

        st.markdown(f"**Shear-lag factor:** {U_note}")

        df_paths = pd.DataFrame([
            {
                "Path":               p["description"],
                "Holes cut":          p["n_holes"],
                "Net width wn (mm)":  round(p["wn_mm"], 1),
                "Stagger s2/4g (mm)": round(p["stagger_term"], 2),
                "An (mm2)":           round(p["An_mm2"], 1),
                "Ane = U*An (mm2)":   round(U * p["An_mm2"], 1),
            }
            for p in net_paths
        ])
        st.dataframe(df_paths, use_container_width=True)

        st.markdown(
            f"**Governing path:** {governing_path['description']} &nbsp;→&nbsp; "
            f"An = {An:,.1f} mm² &nbsp;|&nbsp; Ane = {U:.2f} × {An:,.1f} = {Ane:,.1f} mm²"
        )
        st.latex(
            rf"\phi T_r = {PHI_FRACTURE} \times {U:.2f} \times {An:,.1f} \times {material.Fu:.1f} \div 1000"
            rf"= \mathbf{{{calc_fracture.value:,.1f}}} \text{{ kN}}"
        )

    with st.expander("Block Shear (CSA S16 Cl. 13.11)", expanded=True):
        st.latex(
            r"\phi T_{bs} = \phi_u \left[ U_t A_{nt} F_u + 0.6 \, A_{gv} \frac{F_y + F_u}{2} \right]"
        )
        d_eff = hole_dia + hole_allowance
        Lv    = bolt_pattern.edge_end + (bolt_pattern.bolts_per_line - 1) * bolt_pattern.pitch
        st.markdown(
            f"**Shear area:** Agv = 2 × Lv × t = "
            f"2 × {Lv:.1f} × {section.thickness:.1f} = {Agv_bs:,.1f} mm²  \n"
            f"**Tension area:** Ant = (e2 − 0.5·dh) × t = "
            f"({edge_trans:.1f} − 0.5×{d_eff:.1f}) × {section.thickness:.1f} = {An_bs:,.1f} mm²  \n"
            f"**Ut** = {Ut:.2f}"
        )
        term1 = Ut * An_bs * material.Fu
        term2 = 0.6 * Agv_bs * (material.Fy + material.Fu) / 2
        st.latex(
            rf"\phi T_{{bs}} = {PHI_FRACTURE} \times "
            rf"[{Ut:.2f} \times {An_bs:,.1f} \times {material.Fu:.1f}"
            rf"+ 0.6 \times {Agv_bs:,.1f} \times \frac{{{material.Fy:.1f}+{material.Fu:.1f}}}{{2}}]"
            rf"\div 1000 = \mathbf{{{calc_block.value:,.1f}}} \text{{ kN}}"
        )

    st.divider()
    st.caption(
        "This tool applies simplified block shear logic appropriate for one- or two-line "
        "bolt groups on single angles. Always verify minimum edge distances and pitch meet "
        "CSA S16 detailing requirements."
    )


main()
