from __future__ import annotations
from path_detection import build_bolt_grid
from path_detection import detect_net_section_paths
from path_detection import detect_block_shear_paths
from path_detection import resolve_connected_element


import io
#import io is the input/output library

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
#numpy is the numerical python library 
#pandas is the data analysis library
#streamlit is the web app framework
#streamlit.components.v1 is Streamlit components: embeds the generated SVG as HTML.

import re as _re
#re is the regular expression library

# FOOTNOTE: _theme.py acts as the single source of truth for global UI aesthetics, isolating custom HTML/CSS injections, color tokens, and layout configurations from functional application logic.

try:
    from _theme import apply_theme, render_sidebar_logo, render_footer, gate_disclaimer
except ImportError:
    def apply_theme(): pass
    def render_sidebar_logo(): pass
    def render_footer(): pass
    def gate_disclaimer(): pass
    def render_page_header(title, subtitle=""): pass
# 

def _nat_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in _re.split(r"(\d+)", str(s))]

#String: A string is just text. If Python sees letters, words, sentences, or symbols inside quotation marks, it treats them as a string.
#_re.split(): A function from Python's Regular Expressions (re) module that splits a string every time it matches a specific pattern.

#if c.isdigit(): Checks if the current chunk consists entirely of numeric digits.

#int(c): If the chunk is numeric, this converts it from a string (e.g., "12") into an actual integer (12). This ensures mathematical sorting.

#else c.lower(): If the chunk is text (letters/symbols), it converts it to lowercase. This enforces a case-insensitive sort, ensuring that "beam-1" and "Beam-1" are treated equally instead of uppercase letters automatically jumping to the front due to their ASCII character values.
#split: Use split() when one string actually contains multiple pieces of information, and you want Python to treat each piece separately.


try:
    from connection_diagram import generate_connection_svg
    HAS_SVG = True
except ImportError:
    HAS_SVG = False

try:
    from section_diagrams import single_angle_diagram
    HAS_SECTION_DIAGRAMS = True
except ImportError:
    HAS_SECTION_DIAGRAMS = False

try:
    from section_diagrams import double_angle_diagram
    HAS_SECTION_DIAGRAMS = True
except ImportError:
    HAS_SECTION_DIAGRAMS = False

try:
    from section_diagrams import wt_diagram
    HAS_WT_DIAGRAM = True
except ImportError:
    HAS_WT_DIAGRAM = False

try:
    from section_diagrams import channel_diagram
    HAS_CH_DIAGRAM = True
except ImportError:
    HAS_CH_DIAGRAM = False

# The function above tries to load the SVG generation module. If it's unavailable,the app continues without SVG support.



# ── Constants ─────────────────────────────────────────────────────────────────
PHI       = 0.90
PHI_U     = 0.75
MAX_SLEND = 300

# As per CSA S16 section 10.4.2 - Maximum slenderness ratio shall not exceed 300.


DATA_DIR   = Path(__file__).resolve().parent.parent / "data"
ANGLE_FILE = DATA_DIR / "Angle Properties Table.xlsx"
# you may have to remove all of this********************


BOLT_DIA: Dict[str, float] = {
    "M16": 16.0, "M20": 20.0, "M22": 22.0, "M24": 24.0,
    "M27": 27.0, "M30": 30.0, "M36": 36.0,
}
STD_HOLE: Dict[str, float] = {
    "M16": 18.0, "M20": 22.0, "M22": 24.0, "M24": 26.0,
    "M27": 30.0, "M30": 33.0, "M36": 39.0,
}
#Verify and site the table***********
#The strings store texts in a sequence.


SECTION_TYPES = [
    "Plate",
    "Single Angle",
    "Double Angle",
    "WT Section",
    "Channel (C / MC)",
]


UT_DEFAULTS = {
    "Plate":            1.0,
    "Single Angle":     0.6,
    "Double Angle":     0.6,
    "WT Section":       0.6,
    "Channel (C / MC)": 0.85,
}

#Site table********

# ── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class Material:
    Fy: float
    Fu: float

#data class stores data material e.g.  Fy - # Yield strength, Fu - # Ultimate tensile strength. 
# Float is a decimal number. 



@dataclass
class SectionProps:
    designation: str
    Ag:          float
    t:           float
    r_min:       float = 0.0
    b_flange:    float = 0.0
    d_depth:     float = 0.0
    info:        Dict[str, str] = field(default_factory=dict)
#

@dataclass
class BoltPattern:
    n_lines:        int
    bolts_per_line: int
    pitch:          float
    gauge:          float
    edge_end:       float
    edge_trans:     float

@dataclass
class Calc:
    name:  str
    value: float
    steps: List[str]
    note:  str = ""

    table: object = None


# ── Data loaders ──────────────────────────────────────────────────────────────


def _parse_multi_table_csv(text: str, area_col: str = "Area_mm2") -> pd.DataFrame:
# What other dimensions need to be added  with area_mm2?********

    
    """Parse a CSV that contains multiple sub-tables separated by blank lines."""
    frames: List[pd.DataFrame] = []
    current_header: Optional[List[str]] = None
#frames: This is a list that will store multiple DataFrames. Each DataFrame represents a table extracted from the CSV file.
#list is a collection of items.
#pd. is the pandas library.
#Optional[List[str]] means that current_header can either be a list of strings or None

    current_rows:   List[str] = []
#list[str] means a list of strings. current_rows is a list that will store the rows of data from the CSV file as strings.


    for raw_line in text.splitlines():
        line = raw_line.strip()

    # raw_line is the original line from the CSV file, including any leading or trailing whitespace. 
            # line = raw_line.strip() removes any leading or trailing whitespace from raw_line, ensuring that the line is clean and ready for processing.

        if not line or line.startswith("#"):
            if current_header and current_rows:
                buf = "\n".join([",".join(current_header)] + current_rows)
                #buf is a string that combines the header and the rows of the current table into a single string.

                try:
                    frames.append(pd.read_csv(io.StringIO(buf)))

# frames.append(pd.read_csv(io.StringIO(buf))) reads the combined header and rows into a DataFrame using pd.read_csv(). The io.StringIO(buf) converts the string buf into a file-like object that pd.read_csv() can read.
                except Exception:
                    pass
                current_rows = []
                current_header = None
            continue
        if line.startswith("Designation,"):
            if current_header and current_rows:
                buf = "\n".join([",".join(current_header)] + current_rows)
                try:
                    frames.append(pd.read_csv(io.StringIO(buf)))
                except Exception:
                    pass
                current_rows = []
            current_header = line.split(",")
        elif current_header:
            current_rows.append(line)

    if current_header and current_rows:
        buf = "\n".join([",".join(current_header)] + current_rows)
        try:
            frames.append(pd.read_csv(io.StringIO(buf)))
        except Exception:
            pass

    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined.columns = [c.strip() for c in combined.columns]
    return combined


@st.cache_data
def load_double_angle_table() -> pd.DataFrame:
    path = DATA_DIR / "Double Angle Properties.csv"
    if not path.exists():
        return pd.DataFrame()
    df = _parse_multi_table_csv(path.read_text())
    if df.empty:
        return df
    df = df.rename(columns={"Designation": "designation", "Area_mm2": "Ag",
                                "rx_mm": "rx", "ry_s0_mm": "ry_s0"})
    for c in ["designation", "Ag"]:
        if c not in df.columns:
            return pd.DataFrame()
    df["Ag"] = pd.to_numeric(df["Ag"], errors="coerce")

    def _parse_t(des: str) -> float:
        parts = str(des).replace("L", "").split("x")
        try:
            return float(parts[-1])
        except Exception:
            return float("nan")

    df["t"] = df["designation"].apply(_parse_t)
    return df.dropna(subset=["Ag", "t"]).reset_index(drop=True)


@st.cache_data
def load_wt_table() -> pd.DataFrame:
    path = DATA_DIR / "Structural Tees WT Properties.csv"
    if not path.exists():
        return pd.DataFrame()
    lines = [l for l in path.read_text().splitlines()
                if not l.strip().lstrip('"').startswith("#")]
    df = pd.read_csv(io.StringIO("\n".join(lines)))
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"Designation": "designation"})
    need = ["designation", "Area_mm2", "t_mm", "w_mm", "b_mm", "d_mm", "rx_mm", "ry_mm"]
    for c in need:
        if c not in df.columns:
            return pd.DataFrame()
    for c in need[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["Area_mm2", "t_mm"]).reset_index(drop=True)


@st.cache_data
def load_channel_table() -> pd.DataFrame:
    path = DATA_DIR / "Channel Sections Properties.csv"
    if not path.exists():
        return pd.DataFrame()
    frames: List[pd.DataFrame] = []
    current_header: Optional[List[str]] = None
    current_rows:   List[str] = []

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            if current_header and current_rows:
                buf = "\n".join([",".join(current_header)] + current_rows)
                try:
                    df = pd.read_csv(io.StringIO(buf))
                    if "Area_mm2" in df.columns:
                        frames.append(df)
                except Exception:
                    pass
                current_rows = []
                current_header = None
            continue
        if line.startswith("Designation,"):
            if current_header and current_rows:
                buf = "\n".join([",".join(current_header)] + current_rows)
                try:
                    df = pd.read_csv(io.StringIO(buf))
                    if "Area_mm2" in df.columns:
                        frames.append(df)
                except Exception:
                    pass
                current_rows = []
            current_header = line.split(",")
        elif current_header:
            current_rows.append(line)

    if current_header and current_rows:
        buf = "\n".join([",".join(current_header)] + current_rows)
        try:
            df = pd.read_csv(io.StringIO(buf))
            if "Area_mm2" in df.columns:
                frames.append(df)
        except Exception:
            pass

    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined.columns = [c.strip() for c in combined.columns]
    combined = combined.rename(columns={"Designation": "designation"})
    for c in ["Area_mm2", "t_mm", "w_mm", "d_mm", "b_mm", "rx_mm", "ry_mm"]:
        if c in combined.columns:
            combined[c] = pd.to_numeric(combined[c], errors="coerce")
    return combined.dropna(subset=["Area_mm2", "t_mm"]).reset_index(drop=True)


@st.cache_data
def load_angle_table() -> pd.DataFrame:
    """Load the single angle table from the xlsx file."""
    if not ANGLE_FILE.exists():
        return pd.DataFrame()
    df = pd.read_excel(ANGLE_FILE, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    def find_col(names: List[str]) -> Optional[str]:
        for n in names:
            for c in df.columns:
                if c.lower().replace(" ", "").replace("_", "") == \
                        n.lower().replace(" ", "").replace("_", ""):
                    return c
        return None

    des  = find_col(["Designation", "Section", "Shape"])
    b    = find_col(["b (mm)", "Leg1", "Leg 1", "b"])
    d    = find_col(["d (mm)", "Leg2", "Leg 2", "d"])
    t    = find_col(["t (mm)", "Thickness", "thk", "t"])
    area = find_col(["Area (mm2)", "Area (mm)", "Area", "Ag"])
    rx   = find_col(["rx (mm)", "rx"])
    ry   = find_col(["ry (mm)", "ry"])
    rz   = find_col(["rz (mm)", "rz"])

    if None in (des, b, d, t):
        return pd.DataFrame()

    out = pd.DataFrame({
        "designation": df[des].astype(str),
        "leg1":        pd.to_numeric(df[b], errors="coerce"),
        "leg2":        pd.to_numeric(df[d], errors="coerce"),
        "t":           pd.to_numeric(df[t], errors="coerce"),
        "Ag":          pd.to_numeric(df[area], errors="coerce") if area else np.nan,
        "rx":          pd.to_numeric(df[rx], errors="coerce") if rx else np.nan,
        "ry":          pd.to_numeric(df[ry], errors="coerce") if ry else np.nan,
        "rz":          pd.to_numeric(df[rz], errors="coerce") if rz else np.nan,
    })
    mask = out["Ag"].isna()
    out.loc[mask, "Ag"] = (
        out.loc[mask, "t"] *
        (out.loc[mask, "leg1"] + out.loc[mask, "leg2"] - out.loc[mask, "t"])
    )
    return out.dropna(subset=["leg1", "leg2", "t"]).reset_index(drop=True)


# ── Shear lag factor (CSA S16-14 Cl. 12.3.3.2) - 1. The numerical U value 2. A sentence explaining why that value was selected ───────────────────────────────
def shear_lag(
            section_type:  str,
            n_bolt_rows:   int,
            connected_el:  str   = "",
            b_flange:      float = 0,
            d_depth:       float = 0,
        ) -> Tuple[float, str]:

    #Tuple is a collection of items
    
            """Returns (U, explanation_string)."""
            if section_type in ("Single Angle", "Double Angle") or connected_el == "one_leg":
                if n_bolt_rows >= 4:
                    return 0.80, "One-leg connected angle, >=4 transverse bolt rows => U = 0.80 (Cl. 12.3.3.2b-i)"
                else:
                    return 0.60, "One-leg connected angle, <4 transverse bolt rows => U = 0.60 (Cl. 12.3.3.2b-ii)"
        
            if section_type == "WT Section":
                if connected_el == "flange" and b_flange > 0 and d_depth > 0:
                    if b_flange >= (2.0 / 3.0) * d_depth and n_bolt_rows >= 3:
                        return 0.90, "WT flange-connected, b>=2d/3, >=3 transverse lines => U = 0.90 (Cl. 12.3.3.2a)"
                if n_bolt_rows >= 3:
                    return 0.85, "WT stem/flange-connected, >=3 transverse lines => U = 0.85 (Cl. 12.3.3.2c-i)"
                else:
                    return 0.75, "WT stem/flange-connected, 2 transverse lines => U = 0.75 (Cl. 12.3.3.2c-ii)"
        
            if section_type == "Channel (C / MC)":
                if n_bolt_rows >= 3:
                    return 0.85, "Channel web-connected, >=3 transverse lines => U = 0.85 (Cl. 12.3.3.2c-i)"
                else:
                    return 0.75, "Channel web-connected, 2 transverse lines => U = 0.75 (Cl. 12.3.3.2c-ii)"
        
            if section_type == "Plate":
                return 1.00, "Plate: load distributed to all elements => U = 1.00 (Cl. 12.3.3.1)"
        
            if n_bolt_rows >= 3:
                return 0.85, ">=3 transverse lines => U = 0.85 (Cl. 12.3.3.2c-i)"
            return 0.75, "2 transverse lines => U = 0.75 (Cl. 12.3.3.2c-ii)"
    
    

# ── Calc Gross Yield - Limit-state calculations ──────────────────────────────────────────────────
def calc_gross_yield(Ag: float, Fy: float) -> Calc:
    Tr = PHI * Ag * Fy / 1000.0
    return Calc(
        "Gross Section Yielding (Cl. 13.2a-i)", Tr,
        [
            "**Gross Section Yielding — CSA S16 Cl. 13.2 a) i)**",
            "- Formula: Tr = φ · Ag · Fy",
            f"- Substitute: Tr = {PHI} × {Ag:,.1f} mm² × {Fy:.1f} MPa ÷ 1000",
            f"- Result: **{Tr:,.1f} kN**",
        ],
    )


    # ── Net area paths (Cl. 12.3.1) ──────────────────────────────────────────────
def net_paths(
    width: float,
    bolt: BoltPattern,
    hole_dia: float,
    allowance: float,
    t: float,
) -> List[Dict]:
    """
    Enumerate straight and zig-zag net-area paths through
    a connected plate element.

    An = wn × t
    """
    d_eff = hole_dia + allowance
    paths: List[Dict] = []

    # Straight paths
    for n_holes in range(1, bolt.n_lines + 1):
        wn = width - n_holes * d_eff

        if wn <= 0:
            continue

        paths.append({
            "area_basis": "connected_width",
            "width_mm": width,
            "d_eff_mm": d_eff,
            "t_mm": t,
            "An_mm2": wn * t,
            "wn_mm": wn,
            "n_holes": n_holes,
            "n_staggers": 0,
            "stagger_term": 0.0,
            "pitch_mm": bolt.pitch,
            "gauge_mm": bolt.gauge,
            "description": (
                f"Straight — {n_holes} "
                f"hole{'s' if n_holes > 1 else ''}"
            ),
        })

    # Zig-zag paths>>>>>>>>>
    
    if bolt.bolts_per_line >= 2 and bolt.n_lines >= 2:
        for n_holes in range(2, bolt.n_lines + 1):
            n_staggers = n_holes - 1

            stagger = (
                n_staggers
                * bolt.pitch ** 2
                / (4.0 * bolt.gauge)
            )

            wn = width - n_holes * d_eff + stagger
            An = wn * t

            if wn <= 0 or An <= 0:
                continue

            paths.append({
                "area_basis": "connected_width",
                "width_mm": width,
                "d_eff_mm": d_eff,
                "t_mm": t,
                "An_mm2": An,
                "wn_mm": wn,
                "n_holes": n_holes,
                "n_staggers": n_staggers,
                "stagger_term": stagger,
                "pitch_mm": bolt.pitch,
                "gauge_mm": bolt.gauge,
                "description": (
                    f"Zig-zag — {n_holes} holes, "
                    f"{n_staggers} stagger term(s)"
                ),
            })

    return paths


def gross_section_net_paths(
    Ag: float,
    bolt: BoltPattern,
    hole_dia: float,
    allowance: float,
    t: float,
    connected_parts: int = 1,
) -> List[Dict]:
    """
    Calculate net-section paths from the complete gross area.

    An = Ag - hole deductions + stagger additions
    """
    d_eff = hole_dia + allowance
    paths: List[Dict] = []

    # Straight paths
    for n_holes in range(1, bolt.n_lines + 1):
        hole_deduction = (
            connected_parts
            * n_holes
            * d_eff
            * t
        )

        An = Ag - hole_deduction

        if An <= 0:
            continue

        paths.append({
            "area_basis": "gross_section",
            "Ag_mm2": Ag,
            "An_mm2": An,
            "n_holes": n_holes,
            "n_staggers": 0,
            "d_eff_mm": d_eff,
            "t_mm": t,
            "connected_parts": connected_parts,
            "hole_deduction_mm2": hole_deduction,
            "stagger_term": 0.0,
            "stagger_area_mm2": 0.0,
            "pitch_mm": bolt.pitch,
            "gauge_mm": bolt.gauge,
            "description": (
                f"Straight — {n_holes} "
                f"hole{'s' if n_holes > 1 else ''}"
            ),
        })

    # Zig-zag paths
    if bolt.bolts_per_line >= 2 and bolt.n_lines >= 2:
        for n_holes in range(2, bolt.n_lines + 1):
            n_staggers = n_holes - 1

            stagger_length = (
                n_staggers
                * bolt.pitch ** 2
                / (4.0 * bolt.gauge)
            )

            hole_deduction = (
                connected_parts
                * n_holes
                * d_eff
                * t
            )

            stagger_area = (
                connected_parts
                * stagger_length
                * t
            )

            An = (
                Ag
                - hole_deduction
                + stagger_area
            )

            if An <= 0:
                continue

            paths.append({
                "area_basis": "gross_section",
                "Ag_mm2": Ag,
                "An_mm2": An,
                "n_holes": n_holes,
                "n_staggers": n_staggers,
                "d_eff_mm": d_eff,
                "t_mm": t,
                "connected_parts": connected_parts,
                "hole_deduction_mm2": hole_deduction,
                "stagger_term": stagger_length,
                "stagger_area_mm2": stagger_area,
                "pitch_mm": bolt.pitch,
                "gauge_mm": bolt.gauge,
                "description": (
                    f"Zig-zag — {n_holes} holes, "
                    f"{n_staggers} stagger term(s)"
                ),
            })

    return paths


# ── Net fracture calculation ──────────────────────────────────────────────────
def calc_net_fracture_paths(
    paths,
    U,
    Fu,
    area_mult=1.0,
    area_label="",
    table=None,
):
    results = []

    for p in paths:
        An_i = p["An_mm2"] * area_mult
        Ane_i = U * An_i
        Tr_i = PHI_U * Ane_i * Fu / 1000.0

        results.append((p, An_i, Ane_i, Tr_i))

    if not results:
        raise ValueError(
            "No valid net-section fracture paths were generated."
        )

    gov = min(results, key=lambda r: r[3])

    steps = [
        "**Net Section Fracture — CSA S16 Cl. 13.2 a) iii)**",
        "- Resistance equation:",
        r"\[T_r = \phi_u A_{ne}F_u\]",
        "- Effective net area:",
        r"\[A_{ne} = U A_n\]",
        f"- Resistance factor: φu = {PHI_U:.2f}",
        f"- Shear-lag factor: U = {U:.2f}",
        f"- Ultimate strength: Fu = {Fu:.1f} MPa",
    ]

    if area_label:
        steps.append(f"- {area_label}")

    for path_number, (p, An_i, Ane_i, Tr_i) in enumerate(
        results,
        start=1,
    ):
        tag = "  ← **GOVERNS**" if p is gov[0] else ""

        steps.append("---")
        steps.append(
            f"### Path {path_number}: "
            f"{p['description']}{tag}"
        )

        if p.get("area_basis") == "gross_section":
            Ag = p["Ag_mm2"]
            n_holes = p["n_holes"]
            d_eff = p["d_eff_mm"]
            t = p["t_mm"]
            parts = p.get("connected_parts", 1)
            hole_area = p["hole_deduction_mm2"]
            stagger_length = p.get("stagger_term", 0.0)
            stagger_area = p.get("stagger_area_mm2", 0.0)

            steps.append(
                f"- Effective hole diameter:"
                f"\n  d_eff = d_h + allowance"
                f"\n  = {d_eff:.2f} mm"
            )

            if parts == 1:
                steps.append(
                    f"- Hole deduction:"
                    f"\n  ΔA_h = n_h × d_eff × t"
                    f"\n  = {n_holes} × {d_eff:.2f}"
                    f" × {t:.3f}"
                    f"\n  = **{hole_area:,.1f} mm²**"
                )
            else:
                steps.append(
                    f"- Hole deduction:"
                    f"\n  ΔA_h = connected parts"
                    f" × n_h × d_eff × t"
                    f"\n  = {parts} × {n_holes}"
                    f" × {d_eff:.2f} × {t:.3f}"
                    f"\n  = **{hole_area:,.1f} mm²**"
                )

            if stagger_length > 0:
                n_staggers = p.get(
                    "n_staggers",
                    n_holes - 1,
                )
                pitch = p["pitch_mm"]
                gauge = p["gauge_mm"]

                steps.append(
                    f"- Stagger-length addition:"
                    f"\n  Σ(s²/4g)"
                    f" = {n_staggers} × "
                    f"({pitch:.1f}² / "
                    f"(4 × {gauge:.1f}))"
                    f"\n  = **{stagger_length:,.2f} mm**"
                )

                if parts == 1:
                    steps.append(
                        f"- Stagger-area addition:"
                        f"\n  ΔA_s = Σ(s²/4g) × t"
                        f"\n  = {stagger_length:,.2f}"
                        f" × {t:.3f}"
                        f"\n  = **{stagger_area:,.1f} mm²**"
                    )
                else:
                    steps.append(
                        f"- Stagger-area addition:"
                        f"\n  ΔA_s = connected parts"
                        f" × Σ(s²/4g) × t"
                        f"\n  = {parts}"
                        f" × {stagger_length:,.2f}"
                        f" × {t:.3f}"
                        f"\n  = **{stagger_area:,.1f} mm²**"
                    )

                steps.append(
                    f"- Net area:"
                    f"\n  An = Ag − ΔA_h + ΔA_s"
                    f"\n  = {Ag:,.1f}"
                    f" − {hole_area:,.1f}"
                    f" + {stagger_area:,.1f}"
                    f"\n  = **{An_i:,.1f} mm²**"
                )
            else:
                steps.append(
                    f"- Net area:"
                    f"\n  An = Ag − ΔA_h"
                    f"\n  = {Ag:,.1f}"
                    f" − {hole_area:,.1f}"
                    f"\n  = **{An_i:,.1f} mm²**"
                )

        else:
            width = p["width_mm"]
            d_eff = p["d_eff_mm"]
            t = p["t_mm"]
            stagger = p.get("stagger_term", 0.0)

            steps.append(
                f"- Net width:"
                f"\n  wn = width − holes × d_eff + stagger"
                f"\n  = {width:.1f}"
                f" − {p['n_holes']} × {d_eff:.2f}"
                f" + {stagger:.2f}"
                f"\n  = **{p['wn_mm']:,.1f} mm**"
            )

            steps.append(
                f"- Net area:"
                f"\n  An = wn × t"
                f"\n  = {p['wn_mm']:,.1f} × {t:.3f}"
                f"\n  = **{An_i:,.1f} mm²**"
            )

        steps.append(
            f"- Effective net area:"
            f"\n  Ane = U × An"
            f"\n  = {U:.2f} × {An_i:,.1f}"
            f"\n  = **{Ane_i:,.1f} mm²**"
        )

        steps.append(
            f"- Fracture resistance:"
            f"\n  Tr = φu × Ane × Fu ÷ 1000"
            f"\n  = {PHI_U:.2f}"
            f" × {Ane_i:,.1f}"
            f" × {Fu:.1f} ÷ 1000"
            f"\n  = **{Tr_i:,.1f} kN**"
        )

    steps.append("---")
    steps.append(
        f"### Governing net-fracture path\n"
        f"**{gov[0]['description']}**, "
        f"Tr = **{gov[3]:,.1f} kN**"
    )

    return Calc(
        "Net Section Fracture (Cl. 13.2a-iii)",
        gov[3],
        steps,
        table=table,
    )


def calc_block_shear(
    Ant: float, Agv: float, Fy: float, Fu: float, Ut: float,
    n_shear_planes: int = 1,
) -> Calc:
    """Tr = phi_u * [Ut*Ant*Fu + 0.6*Agv*(Fy+Fu)/2]"""
    Agv_total  = Agv * n_shear_planes
    shear_avg  = (Fy + Fu) / 2.0
    term1      = Ut * Ant * Fu
    term2      = 0.6 * Agv_total * shear_avg
    Tr         = PHI_U * (term1 + term2) / 1000.0
    return Calc(
        "Block Shear (Cl. 13.11)", Tr,
        [
            "**Block Shear — CSA S16 Cl. 13.11**",
            "- Formula: Tr = φu · [Ut·Ant·Fu + 0.6·Agv·(Fy+Fu)/2]",
            f"- Gross shear area: Agv = {n_shear_planes} plane(s) × {Agv:,.1f} mm² = **{Agv_total:,.1f} mm²**",
            f"- Tension term: Ut·Ant·Fu = {Ut:.2f} × {Ant:,.1f} × {Fu:.1f} = **{term1:,.0f} N**",
            f"- Shear term: 0.6·Agv·(Fy+Fu)/2 = 0.6 × {Agv_total:,.1f} × ({Fy:.1f}+{Fu:.1f})/2 = **{term2:,.0f} N**",
            f"- Substitute: Tr = {PHI_U} × ({term1:,.0f} + {term2:,.0f}) ÷ 1000",
            f"- Result: **{Tr:,.1f} kN**",
        ],
    )


def calc_pin(An: float, Fy: float) -> Calc:
    """Cl. 13.2(b): pin connections."""
    Tr = 0.75 * PHI * An * Fy / 1000.0
    return Calc(
        "Pin Connection (Cl. 13.2b)", Tr,
        [
            "**Pin Connection — CSA S16 Cl. 13.2 b)**",
            "- Formula: Tr = 0.75 · φ · An · Fy",
            f"- Substitute: Tr = 0.75 × {PHI} × {An:,.1f} mm² × {Fy:.1f} MPa ÷ 1000",
            f"- Result: **{Tr:,.1f} kN**",
        ],
    )

def block_shear_areas(
    bolt:  BoltPattern,
    t:     float,
    d_eff: float,
) -> Tuple[float, float]:
    """Returns (Ant, Agv_single_plane)."""
    nrows = bolt.bolts_per_line
    Lv    = bolt.edge_end + (nrows - 1) * bolt.pitch
    Agv   = Lv * t
    #Lv is the total length of the shear plane in the vertical direction.

    Ant   = max(0.0, bolt.edge_trans - 0.5 * d_eff) * t
    return Ant, Agv

#An is the area of the tension part of the block shear failure surface.


def block_shear_paths(
        bolt: BoltPattern,
        t: float,
        d_eff: float,
    ):
        """
        Generates candidate block-shear paths and retains all
        intermediate values required to show the work.
        """
        n_rows = bolt.bolts_per_line
        n_lines = bolt.n_lines

        Lv = bolt.edge_end + (n_rows - 1) * bolt.pitch
        Agv_single = Lv * t

        pats = []

        # Pattern A:
        # shear on far bolt line, tension path to free edge
        wt_A = (
            bolt.edge_trans
            + (n_lines - 1) * bolt.gauge
            - (n_lines - 0.5) * d_eff
        )

        pats.append({
            "key": "A",
            "Ant": max(0.0, wt_A) * t,
            "Agv": Agv_single,
            "planes": 1,
            "Lv_mm": Lv,
            "tension_width_mm": max(0.0, wt_A),
            "t_mm": t,
            "d_eff_mm": d_eff,
            "n_rows": n_rows,
            "n_lines": n_lines,
            "edge_end_mm": bolt.edge_end,
            "edge_trans_mm": bolt.edge_trans,
            "pitch_mm": bolt.pitch,
            "gauge_mm": bolt.gauge,
            "tension_formula": (
                "e2 + (n_lines − 1)g − "
                "(n_lines − 0.5)d_eff"
            ),
            "description": (
                "A: shear on far line, tension to free edge"
            ),
        })

        if n_lines >= 2:
            # Pattern B:
            # shear on edge bolt line, tension to adjacent free edge
            wt_B = bolt.edge_trans - 0.5 * d_eff

            pats.append({
                "key": "B",
                "Ant": max(0.0, wt_B) * t,
                "Agv": Agv_single,
                "planes": 1,
                "Lv_mm": Lv,
                "tension_width_mm": max(0.0, wt_B),
                "t_mm": t,
                "d_eff_mm": d_eff,
                "n_rows": n_rows,
                "n_lines": n_lines,
                "edge_end_mm": bolt.edge_end,
                "edge_trans_mm": bolt.edge_trans,
                "pitch_mm": bolt.pitch,
                "gauge_mm": bolt.gauge,
                "tension_formula": "e2 − 0.5d_eff",
                "description": (
                    "B: shear on edge line, tension to free edge"
                ),
            })

            # Pattern C:
            # shear on two outside lines, tension between lines
            wt_C = (
                (n_lines - 1) * bolt.gauge
                - (n_lines - 1) * d_eff
            )

            pats.append({
                "key": "C",
                "Ant": max(0.0, wt_C) * t,
                "Agv": Agv_single,
                "planes": 2,
                "Lv_mm": Lv,
                "tension_width_mm": max(0.0, wt_C),
                "t_mm": t,
                "d_eff_mm": d_eff,
                "n_rows": n_rows,
                "n_lines": n_lines,
                "edge_end_mm": bolt.edge_end,
                "edge_trans_mm": bolt.edge_trans,
                "pitch_mm": bolt.pitch,
                "gauge_mm": bolt.gauge,
                "tension_formula": (
                    "(n_lines − 1)g − "
                    "(n_lines − 1)d_eff"
                ),
                "description": (
                    "C: shear on both outer lines, "
                    "tension between lines"
                ),
            })

        return pats



def calc_block_shear_paths(
    pats,
    Fy,
    Fu,
    Ut,
    area_mult=1.0,
    area_label="",
):
    """
    Calculate all candidate block-shear paths and show the complete
    geometry, area, force-component, and resistance calculations.

    Returns:
        Calc object
        Governing block-shear pattern key: "A", "B", or "C"
    """

    if not pats:
        raise ValueError(
            "No valid block-shear paths were generated."
        )

    # This implements the high-strength-steel rule already stated
    # by the warning inside render_material().
    if Fy > 460.0:
        Fbs = Fy
        Fbs_name = "Fy"
        Fbs_substitution = f"{Fy:.1f}"
    else:
        Fbs = (Fy + Fu) / 2.0
        Fbs_name = "(Fy + Fu) / 2"
        Fbs_substitution = (
            f"({Fy:.1f} + {Fu:.1f}) / 2"
        )

    results = []

    # ── Calculate every candidate pattern ────────────────────────────────
    for p in pats:
        Ant_single = p["Ant"]
        Agv_single = p["Agv"]
        planes = p["planes"]

        # area_mult = 2.0 for double angles
        Ant_total = Ant_single * area_mult

        Agv_total = (
            Agv_single
            * planes
            * area_mult
        )

        tension_term = (
            Ut
            * Ant_total
            * Fu
        )

        shear_term = (
            0.6
            * Agv_total
            * Fbs
        )

        Tr_i = (
            PHI_U
            * (tension_term + shear_term)
            / 1000.0
        )

        results.append({
            "path": p,
            "Ant_single": Ant_single,
            "Ant_total": Ant_total,
            "Agv_single": Agv_single,
            "Agv_total": Agv_total,
            "tension_term": tension_term,
            "shear_term": shear_term,
            "Tr_kN": Tr_i,
        })

    # Lowest resistance governs
    gov = min(
        results,
        key=lambda result: result["Tr_kN"],
    )

    # ── General calculation information ──────────────────────────────────
    steps = [
        "**Block Shear — CSA S16 Cl. 13.11**",

        (
            "- Resistance equation:"
            "\n  Tr = φu × "
            "[Ut × Ant × Fu + 0.6 × Agv × Fbs]"
        ),

        f"- Resistance factor: φu = {PHI_U:.2f}",

        f"- Block-shear tension factor: Ut = {Ut:.2f}",

        f"- Yield strength: Fy = {Fy:.1f} MPa",

        f"- Ultimate strength: Fu = {Fu:.1f} MPa",

        (
            f"- Shear-strength basis:"
            f"\n  Fbs = {Fbs_name}"
            f"\n  = {Fbs_substitution}"
            f"\n  = **{Fbs:,.1f} MPa**"
        ),
    ]

    if area_label:
        steps.append(f"- {area_label}")

    # ── Show complete work for every pattern ─────────────────────────────
    for result in results:
        p = result["path"]

        key = p["key"]
        governs = key == gov["path"]["key"]

        tag = " ← **GOVERNS**" if governs else ""

        n_rows = p["n_rows"]
        n_lines = p["n_lines"]

        e1 = p["edge_end_mm"]
        e2 = p["edge_trans_mm"]

        pitch = p["pitch_mm"]
        gauge = p["gauge_mm"]

        d_eff = p["d_eff_mm"]
        t = p["t_mm"]

        Lv = p["Lv_mm"]
        wnt = p["tension_width_mm"]
        planes = p["planes"]

        description = p["description"].split(
            ": ",
            1,
        )[-1]

        # Numerical substitution for each tension path
        if key == "A":
            width_formula = (
                "wnt = e2 + (n_lines − 1)g "
                "− (n_lines − 0.5)d_eff"
            )

            width_substitution = (
                f"{e2:.1f}"
                f" + ({n_lines} − 1) × {gauge:.1f}"
                f" − ({n_lines} − 0.5) × {d_eff:.2f}"
            )

        elif key == "B":
            width_formula = (
                "wnt = e2 − 0.5d_eff"
            )

            width_substitution = (
                f"{e2:.1f}"
                f" − 0.5 × {d_eff:.2f}"
            )

        elif key == "C":
            width_formula = (
                "wnt = (n_lines − 1)g "
                "− (n_lines − 1)d_eff"
            )

            width_substitution = (
                f"({n_lines} − 1) × {gauge:.1f}"
                f" − ({n_lines} − 1) × {d_eff:.2f}"
            )

        else:
            width_formula = (
                f"wnt = {p.get('tension_formula', 'defined path')}"
            )
            width_substitution = "stored path geometry"

        steps.append("---")

        steps.append(
            f"### Pattern {key}: {description}{tag}"
        )

        # Effective hole diameter
        steps.append(
            f"- Effective hole diameter:"
            f"\n  d_eff = d_h + allowance"
            f"\n  = **{d_eff:.2f} mm**"
        )

        # Shear-path length
        steps.append(
            f"- Shear-path length:"
            f"\n  Lv = e1 + (n_rows − 1)s"
            f"\n  = {e1:.1f}"
            f" + ({n_rows} − 1) × {pitch:.1f}"
            f"\n  = **{Lv:,.1f} mm**"
        )

        # Gross shear area for one plane
        steps.append(
            f"- Gross shear area per plane:"
            f"\n  Agv,1 = Lv × t"
            f"\n  = {Lv:,.1f} × {t:.3f}"
            f"\n  = **{result['Agv_single']:,.1f} mm²**"
        )

        # Total gross shear area
        if planes == 1 and area_mult == 1.0:
            steps.append(
                f"- Total gross shear area:"
                f"\n  Agv = Agv,1"
                f"\n  = **{result['Agv_total']:,.1f} mm²**"
            )

        else:
            steps.append(
                f"- Total gross shear area:"
                f"\n  Agv = shear planes"
                f" × member parts × Agv,1"
                f"\n  = {planes}"
                f" × {area_mult:g}"
                f" × {result['Agv_single']:,.1f}"
                f"\n  = **{result['Agv_total']:,.1f} mm²**"
            )

        # Net tension width
        steps.append(
            f"- Net tension width:"
            f"\n  {width_formula}"
            f"\n  = {width_substitution}"
            f"\n  = **{wnt:,.1f} mm**"
        )

        # Net tension area
        if area_mult == 1.0:
            steps.append(
                f"- Net tension area:"
                f"\n  Ant = wnt × t"
                f"\n  = {wnt:,.1f} × {t:.3f}"
                f"\n  = **{result['Ant_total']:,.1f} mm²**"
            )

        else:
            steps.append(
                f"- Net tension area:"
                f"\n  Ant = member parts × wnt × t"
                f"\n  = {area_mult:g}"
                f" × {wnt:,.1f} × {t:.3f}"
                f"\n  = **{result['Ant_total']:,.1f} mm²**"
            )

        # Tension contribution
        steps.append(
            f"- Tension contribution:"
            f"\n  Rt = Ut × Ant × Fu"
            f"\n  = {Ut:.2f}"
            f" × {result['Ant_total']:,.1f}"
            f" × {Fu:.1f}"
            f"\n  = **{result['tension_term']:,.0f} N**"
        )

        # Shear contribution
        steps.append(
            f"- Shear contribution:"
            f"\n  Rv = 0.6 × Agv × Fbs"
            f"\n  = 0.6"
            f" × {result['Agv_total']:,.1f}"
            f" × {Fbs:,.1f}"
            f"\n  = **{result['shear_term']:,.0f} N**"
        )

        # Final block-shear resistance
        steps.append(
            f"- Block-shear resistance:"
            f"\n  Tr = φu × (Rt + Rv) ÷ 1000"
            f"\n  = {PHI_U:.2f}"
            f" × ({result['tension_term']:,.0f}"
            f" + {result['shear_term']:,.0f})"
            f" ÷ 1000"
            f"\n  = **{result['Tr_kN']:,.1f} kN**"
        )

    # ── Governing result ──────────────────────────────────────────────────
    gov_description = gov["path"]["description"].split(
        ": ",
        1,
    )[-1]

    steps.append("---")

    steps.append(
        f"### Governing block-shear pattern\n"
        f"**Pattern {gov['path']['key']}: "
        f"{gov_description}**, "
        f"Tr = **{gov['Tr_kN']:,.1f} kN**"
    )

    # ── Summary table ─────────────────────────────────────────────────────
    summary_table = pd.DataFrame([
        {
            "Pattern": result["path"]["key"],

            "Description": (
                result["path"]["description"].split(
                    ": ",
                    1,
                )[-1]
            ),

            "Lv (mm)": round(
                result["path"]["Lv_mm"],
                1,
            ),

            "wnt (mm)": round(
                result["path"]["tension_width_mm"],
                1,
            ),

            "Ant (mm²)": round(
                result["Ant_total"],
                1,
            ),

            "Shear planes": result["path"]["planes"],

            "Agv (mm²)": round(
                result["Agv_total"],
                1,
            ),

            "Rt (N)": round(
                result["tension_term"],
                0,
            ),

            "Rv (N)": round(
                result["shear_term"],
                0,
            ),

            "Tr (kN)": round(
                result["Tr_kN"],
                1,
            ),

            "Governs": (
                "YES"
                if result["path"]["key"]
                == gov["path"]["key"]
                else ""
            ),
        }
        for result in results
    ])

    return (
        Calc(
            "Block Shear (Cl. 13.11)",
            gov["Tr_kN"],
            steps,
            table=summary_table,
        ),
        gov["path"]["key"],
    )

# ── UI helpers ────────────────────────────────────────────────────────────────
def _bolt_hole_inputs(key_prefix: str) -> Tuple[str, float, float]:
    c1, c2, c3 = st.columns(3)
    with c1:
        bolt_size = st.selectbox("Bolt size", list(BOLT_DIA.keys()), index=1,
                                    key=f"{key_prefix}_bs")
    with c2:
        d_hole_nom = STD_HOLE.get(bolt_size, BOLT_DIA[bolt_size] + 2.0)
        hole_dia   = st.number_input("Hole diameter (mm)", min_value=0.0,
                                        #st is the streamlit library[
                                        value=float(d_hole_nom), step=1.0,
        # value=float(d_hole_nom) sets the default value of the number input to the nominal hole diameter calculated earlier.                                   
                                        key=f"{key_prefix}_hd")
    with c3:
        allowance = st.number_input("Hole allowance (mm)", min_value=0.0,
                                    max_value=10.0, value=0.0, step=0.5,
                                    key=f"{key_prefix}_ha",
                                    help="+2 mm for punched holes (Cl. 12.3.2)")
    return bolt_size, hole_dia, allowance


def _bolt_pattern_inputs(key_prefix: str) -> BoltPattern:
    c1, c2 = st.columns(2)
    with c1:
        n_lines        = st.selectbox("Bolt lines (columns)", [1, 2, 3],
                                            key=f"{key_prefix}_nl")
        bolts_per_line = st.number_input("Bolts per line (rows)", min_value=2,
                                            max_value=20, value=4, step=1,
                                            key=f"{key_prefix}_nb")
        pitch          = st.number_input("Pitch s (mm)", min_value=10.0,
                                            max_value=300.0, value=80.0, step=5.0,
                                            key=f"{key_prefix}_pi")
    with c2:
        gauge      = st.number_input("Gauge g (mm)", min_value=1.0,
                                        max_value=300.0, value=60.0, step=5.0,
                                        key=f"{key_prefix}_g")
        edge_end   = st.number_input("End distance e1 (mm)", min_value=5.0,
                                        max_value=300.0, value=40.0, step=5.0,
                                        key=f"{key_prefix}_e1")
        edge_trans = st.number_input("Transverse edge e2 (mm)", min_value=1.0,
                                        max_value=200.0, value=30.0, step=5.0,
                                        key=f"{key_prefix}_e2")
    return BoltPattern(
        n_lines=int(n_lines), bolts_per_line=int(bolts_per_line),
        pitch=float(pitch), gauge=float(gauge),
        edge_end=float(edge_end), edge_trans=float(edge_trans),
    )


def _show_results(calcs: List[Calc], Tf: float, section_type: str, show_steps: bool = True) -> None:
    vals = {c.name: c.value for c in calcs}
    gov  = min(vals, key=vals.__getitem__)
    Tr   = vals[gov]

    st.divider()
    if show_steps: st.subheader("Calculations — Shown Work")

    for c in (calcs if show_steps else []):
        with st.expander(f" Tr Calculation Steps — {c.name.split('(')[0].strip()}", expanded=True):
            st.markdown("\n".join(c.steps))
            if c.table is not None:

                st.dataframe(c.table, use_container_width=True)
            if c.note:
                st.info(c.note)


    st.subheader("Results")
    cols = st.columns(len(calcs))
    #st.columns(len(calcs)): This creates a list of column objects. The number of columns is determined by the length of the calcs list.

    for i, c in enumerate(calcs):
        cols[i].metric(
            c.name.split("(")[0].strip(),
            f"{c.value:,.1f} kN",
            delta="<-- governs" if c.name == gov else None,
            delta_color="inverse",
        )

    if Tf > 0:
        util = Tf / Tr
        st.progress(min(util, 1.0))
        lbl = f"Tf / Tr = {util:.3f}  ({Tf:.1f} / {Tr:.1f} kN)"
        if util <= 1.0:
            st.success(f"PASS   {lbl}")
        else:
            st.error(f"FAIL   {lbl}")



# ── Section panels ────────────────────────────────────────────────────────────
def render_material():
    st.divider()
    st.subheader("Material")
    GRADES = {
        "G300W  (Fy=300, Fu=440)": (300.0, 440.0),
        "G350W  (Fy=350, Fu=450)": (350.0, 450.0),
        "G400W  (Fy=400, Fu=520)": (400.0, 520.0),
        "G480W  (Fy=480, Fu=590)": (480.0, 590.0),
        "Custom":                   None,
    }

    def _sync_grade():
        vals = GRADES.get(st.session_state["tm_grade"])
        if vals:
            st.session_state["tm_Fy"] = vals[0]
            st.session_state["tm_Fu"] = vals[1]

    grade_sel = st.selectbox("Steel grade", list(GRADES.keys()),
                                key="tm_grade", on_change=_sync_grade)
    # on_change=_sync_grade: This parameter specifies a callback function that will be executed whenever the value of the selectbox changes. In this case, the callback function is _sync_grade, which is defined elsewhere in the code.   

    if GRADES[grade_sel]:
#GRADES[grade_sel]: This accesses the value associated with the key grade_sel in the GRADES dictionary. If the value is not None, the code inside the if block will be executed.
#grade_sel: This is a variable that holds the selected grade from the selectbox. It is used as the key to look up the corresponding value in the GRADES dictionary.

        Fy_def, Fu_def = GRADES[grade_sel]  # ty:ignore[not-iterable]
#Fy_def and Fu_def are variables that will store the yield strength and ultimate tensile strength values, respectively, for the selected steel grade.
#GRADES[grade_sel] is the value associated with the selected steel grade in the GRADES dictionary. This value is a tuple containing the yield strength and ultimate tensile strength values.

    else:
        Fy_def, Fu_def = 350.0, 450.0

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        Fy = st.number_input("Fy (MPa)", min_value=100.0, max_value=800.0,
                                    value=Fy_def, step=10.0, key="tm_Fy")
    with mc2:
        Fu = st.number_input("Fu (MPa)", min_value=200.0, max_value=900.0,
                                    value=Fu_def, step=10.0, key="tm_Fu")
    with mc3:
        Tf = st.number_input("Factored demand Tf (kN)", min_value=0.0,

                                max_value=50000.0, value=0.0, step=10.0,
                                    help="Optional — shows utilization ratio",
                                    key="tm_Tf")

    mat = Material(Fy=Fy, Fu=Fu)

    if Fy > 460:
        st.warning(
            "Fy > 460 MPa: CSA S16 requires using Fy in place of the "
            "(Fy+Fu)/2 shear average for block shear. "
            "Review results carefully for high-strength steels."
        )

    st.divider()
    return mat, Tf


def panel_plate(render_material) -> None:
    st.subheader("Section — Flat Plate")
    c1, c2 = st.columns(2)
    with c1:
        width = st.number_input("Plate width w (mm)", min_value=1.0,
                                max_value=2000.0, value=140.0, step=5.0,
                                key="pl_w")
    with c2:
        thick = st.number_input("Plate thickness t (mm)", min_value=1.0,
                                max_value=100.0, value=10.0, step=1.0,
                                key="pl_t")
    Ag = width * thick

    pin_conn = st.checkbox("Pin connection (Cl. 13.2b)?", value=False, key="pl_pin")

    mat, Tf = render_material()

    st.subheader("Connection Geometry")
    _, hole_dia, allowance = _bolt_hole_inputs("pl")
    bp = _bolt_pattern_inputs("pl")

    d_eff    = hole_dia + allowance
    U, U_note = shear_lag("Plate", bp.bolts_per_line)
    Ut = st.slider("Block shear efficiency Ut", 0.3, 1.0, 1.0, 0.05,
                            help="Ut = 1.0 for concentric symmetric plate (Cl. 13.11)",
                            key="pl_ut")

    st.subheader("Slenderness (Cl. 10.4.2)")
    c3, _ = st.columns(2)
    with c3:
        L_m = st.number_input("Unbraced length L (mm)", min_value=0.0,
                                    value=0.0, step=100.0, key="pl_L")
    r_min = min(thick, width) / math.sqrt(12.0)
    slend = (L_m / r_min) if r_min > 0 and L_m > 0 else 0.0

    st.divider()
    paths = net_paths(width, bp, hole_dia, allowance, thick)
    if not paths:
        st.error("No feasible net fracture path. Check bolt layout vs plate width.")
        return
    gov_path = min(paths, key=lambda p: p["An_mm2"])
    An = gov_path["An_mm2"]


    calcs = [calc_gross_yield(Ag, mat.Fy)]
    if pin_conn:
        calcs.append(calc_pin(An, mat.Fy))
    calcs.append(calc_net_fracture_paths(paths, U, mat.Fu))

    bs_pats = block_shear_paths(bp, thick, d_eff)
    bs_calc, bs_gov = calc_block_shear_paths(bs_pats, mat.Fy, mat.Fu, Ut)
    calcs.append(bs_calc)

    with st.expander("Net fracture paths", expanded=False):
        st.info(f"Shear lag: {U_note}")
        df_p = pd.DataFrame([{
            "Path":                 p["description"],
            "Holes":                p["n_holes"],
            "Ag (mm2)":             round(p["Ag_mm2"], 1),
            "Hole deduction (mm2)": round(p["hole_deduction_mm2"], 1),
            "s2/4g (mm)":           round(p["stagger_term"], 2),
            "Stagger add (mm2)":    round(p["stagger_area_mm2"], 1),
            "An (mm2)":             round(p["An_mm2"], 1),
            "Ane = U*An (mm2)":     round(U * p["An_mm2"], 1),
        } for p in paths])
        
        st.dataframe(df_p, use_container_width=True)

    if L_m > 0:
        with st.expander("Slenderness check (Cl. 10.4.2)", expanded=True):
            st.write(f"r_min = min(t,w)/sqrt(12) = {r_min:.1f} mm   |   L/r = {slend:.0f}")
            if slend > MAX_SLEND:
                st.error(f"L/r = {slend:.0f} > 300 — exceeds maximum slenderness")
            else:
                st.success(f"L/r = {slend:.0f} <= 300  PASS")

    _show_results(calcs, Tf, "Plate")

    if HAS_SVG:
        st.subheader("Connection Diagram")
        svg = generate_connection_svg(
            n_lines=bp.n_lines, bolts_per_line=bp.bolts_per_line,
            pitch=bp.pitch, gauge=bp.gauge, edge_end=bp.edge_end,
            edge_trans=bp.edge_trans, leg_width=width, thickness=thick,
            hole_dia=hole_dia, show_fracture=True, show_block_shear=True,
            section_label=f"Plate {width:.0f}\u00d7{thick:.0f} mm",
            governing_path_n_holes=gov_path["n_holes"],
            zig_zag="zig" in gov_path["description"].lower(),
        )
        components.html(svg, height=340)


#Panel Single Angle

def panel_single_angle(render_material) -> None:
    st.subheader("Section — Single Angle")
    df = load_angle_table()
    if df.empty:
        st.warning("Angle Properties Table.xlsx not found in data/ folder.")
        return

    chosen = st.selectbox("Angle designation", sorted(df["designation"].tolist(), key=_nat_key), key="sa_des")
    row    = df.loc[df["designation"] == chosen].iloc[0]
    Ag     = float(row["Ag"])
    t      = float(row["t"])
    leg1   = float(row["leg1"])
    leg2   = float(row["leg2"])

    rx_v = float(row["rx"]) if "rx" in row and pd.notna(row["rx"]) else None
    ry_v = float(row["ry"]) if "ry" in row and pd.notna(row["ry"]) else None
    rz_v = float(row["rz"]) if "rz" in row and pd.notna(row["rz"]) else None

    with st.expander("Section properties", expanded=True):
        cc = st.columns(4)
    #cc is a list of column objects.
        
        cc[0].metric("Leg 1 (mm)", f"{leg1:.1f}")
        cc[1].metric("Leg 2 (mm)", f"{leg2:.1f}")
        cc[2].metric("t (mm)", f"{t:.1f}")
        cc[3].metric("Ag (mm2)", f"{Ag:,.0f}")
        cc2 = st.columns(4)
        cc2[0].metric("rx (mm)", f"{rx_v:.1f}" if rx_v else "n/a")
        cc2[1].metric("ry (mm)", f"{ry_v:.1f}" if ry_v else "n/a")
        cc2[2].metric("rz min (mm)", f"{rz_v:.1f}" if rz_v else "n/a")

    mat, Tf = render_material()

    st.subheader("Connection Geometry")
    conn_leg = st.radio("Connected leg", ["Leg 1", "Leg 2"], horizontal=True, key="sa_leg")
    w_conn   = leg1 if conn_leg == "Leg 1" else leg2

    _, hole_dia, allowance = _bolt_hole_inputs("sa")
    bp = _bolt_pattern_inputs("sa")

    d_eff     = hole_dia + allowance
    U, U_note = shear_lag("Single Angle", bp.bolts_per_line)
    Ut = st.slider("Block shear Ut", 0.3, 1.0, 0.6, 0.05,
                            help="Ut = 0.60 for angle connected by one leg (Cl. 13.11)",
                            key="sa_ut")

    st.subheader("Slenderness (Cl. 10.4.2)")
    c3, _ = st.columns(2)
    with c3:
        L_m = st.number_input("Unbraced length L (mm)", min_value=0.0,
                                    value=0.0, step=100.0, key="sa_L")
    if rz_v:
        r_min = rz_v
    elif rx_v and ry_v:
        r_min = min(rx_v, ry_v)
    else:
        r_min = min(leg1, leg2) / math.sqrt(12)
    slend = (L_m / r_min) if r_min > 0 and L_m > 0 else 0.0

    st.divider()

    from path_detection import (build_bolt_grid, detect_net_section_paths,
                                detect_block_shear_paths, resolve_connected_element)

    grid = build_bolt_grid(bp)
    paths = detect_net_section_paths(
        Ag=Ag, t=t, d_eff=d_eff, bolts=grid,
        connected_parts=1, pitch_mm=bp.pitch, gauge_mm=bp.gauge,
    )

    
    if not paths:
        st.error("No feasible net fracture path.")
        return
    gov_path = min(paths, key=lambda p: p["An_mm2"])
    An = gov_path["An_mm2"]

    calcs = [
calc_gross_yield(Ag, mat.Fy),
        calc_net_fracture_paths(paths, U, mat.Fu),
    ]
    el = resolve_connected_element("Single Angle", "leg",
                                   {"leg_conn": w_conn, "t": t})
    bs_pats = detect_block_shear_paths(bp, el, d_eff)

    bs_calc, bs_gov = calc_block_shear_paths(bs_pats, mat.Fy, mat.Fu, Ut)
    calcs.append(bs_calc)

    geom = dict(
        w_conn=w_conn, n_lines=bp.n_lines, bolts_per_line=bp.bolts_per_line,
        pitch=bp.pitch, gauge=bp.gauge, edge_end=bp.edge_end,
        edge_trans=bp.edge_trans, hole_dia=hole_dia,
    )
    from path_thumbnails import render_net_paths, render_block_patterns

    _show_results(
        calcs,
        Tf,
        "Single Angle",
        show_steps=True,
    )
    
    render_net_paths(paths, geom, U=U, Fu=mat.Fu,
                     gov_desc=gov_path["description"])
    render_block_patterns(bs_pats, geom, Fy=mat.Fy, Fu=mat.Fu, Ut=Ut,
                          gov_key=bs_gov)

    with st.expander("Net fracture paths", expanded=False):
        st.info(f"Shear lag: {U_note}")
        df_p = pd.DataFrame([{
            "Path":                 p["description"],
            "Holes":                p["n_holes"],
            "Ag (mm2)":             round(p["Ag_mm2"], 1),
            "Hole deduction (mm2)": round(p["hole_deduction_mm2"], 1),
            "s2/4g (mm)":           round(p["stagger_term"], 2),
            "Stagger add (mm2)":    round(p["stagger_area_mm2"], 1),
            "An (mm2)":             round(p["An_mm2"], 1),
            "Ane = U*An (mm2)":     round(U * p["An_mm2"], 1),
        } for p in paths])
        
        st.dataframe(df_p, use_container_width=True)

    if L_m > 0:
        with st.expander("Slenderness check (Cl. 10.4.2)", expanded=True):
            st.write(f"r_min = {r_min:.1f} mm   |   L/r = {slend:.0f}")
            if slend > MAX_SLEND:
                st.error(f"L/r = {slend:.0f} > 300 — exceeds maximum slenderness")
            else:
                st.success(f"L/r = {slend:.0f} <= 300  PASS")

    _show_results(calcs, Tf, "Single Angle", show_steps=False)
    

    #Single Angle Diagram

    if HAS_SECTION_DIAGRAMS:
        st.subheader("Member Detail - Three Views")
        svg3 = single_angle_diagram(
            leg_conn=w_conn,
            leg_out=(leg2 if conn_leg == "Leg 1" else leg1),
            t=t,
            n_lines=bp.n_lines,
            bolts_per_line=bp.bolts_per_line,
            pitch=bp.pitch,
            gauge=bp.gauge,
            edge_end=bp.edge_end,
            edge_trans=bp.edge_trans,
            hole_dia=hole_dia,
            show_net_fracture=True,
            zig_zag="zig" in gov_path["description"].lower(),
            show_block_shear=True,
            governing_bs=bs_gov,
            section_label=chosen,
        )
        components.html(svg3, height=1250, scrolling=True)


def panel_double_angle(render_material) -> None:
    st.subheader("Section — Double Angle (Back-to-Back)")
    df = load_double_angle_table()
    if df.empty:
        st.warning(
            "Double_Angle_Properties.csv not found in data/ folder. "
            "Add the CSV to enable this section type."
        )
        return

    DA_ARRANGEMENTS = {
        "Equal legs (2L)":              "2LE",
        "Long legs back-to-back (2LL)": "2LL",
        "Short legs back-to-back (2LS)": "2LS",
    }
    arr_label = st.selectbox("Leg arrangement", list(DA_ARRANGEMENTS), key="da_arr")
    prefix    = DA_ARRANGEMENTS[arr_label]

    sub = df[df["designation"].astype(str).str.startswith(prefix)]
    if sub.empty:
        st.warning(f"No {arr_label} sections found in the data table.")
        return

    def _da_display(des: str) -> str:
        return "2L" + des[3:] if prefix == "2LE" else des

    chosen = st.selectbox(
        "Double angle designation",
        sorted(sub["designation"].tolist(), key=_nat_key),
        format_func=_da_display,
        key=f"da_des_{prefix}",
    )
    chosen_label = _da_display(chosen)
    row    = sub.loc[sub["designation"] == chosen].iloc[0]
    Ag     = float(row["Ag"])
    t      = float(row["t"])

    m = _re.match(r"^2L[ELS]?(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x", str(chosen))
    if m:
        legs = [float(m.group(1)), float(m.group(2))]
    else:
        legs = [100.0, 100.0]

    with st.expander("Section properties", expanded=True):
        cc = st.columns(3)
        cc[0].metric("Leg 1 (mm)", f"{legs[0]:.0f}")
        cc[1].metric("Leg 2 (mm)", f"{legs[1]:.0f}")
        cc[2].metric("Ag combined (mm2)", f"{Ag:,.0f}")
        cc2 = st.columns(3)
        rx_da = float(row["rx"]) if "rx" in row and pd.notna(row["rx"]) else None
        ry0_da = float(row["ry_s0"]) if "ry_s0" in row and pd.notna(row["ry_s0"]) else None
        cc2[0].metric("t (mm)", f"{t:.1f}")
        cc2[1].metric("rx (mm)", f"{rx_da:.1f}" if rx_da else "n/a")
        cc2[2].metric("ry, s=0 (mm)", f"{ry0_da:.1f}" if ry0_da else "n/a")

    mat, Tf = render_material()

    st.subheader("Connection Geometry")
    conn_leg = st.radio(
        "Connected leg",
        [f"Leg 1 ({legs[0]:.0f} mm)", f"Leg 2 ({legs[1]:.0f} mm)"],
        horizontal=True, key="da_leg",
    )
    w_conn = legs[0] if "Leg 1" in conn_leg else legs[1]

    _, hole_dia, allowance = _bolt_hole_inputs("da")
    bp = _bolt_pattern_inputs("da")

    d_eff     = hole_dia + allowance
    U, U_note = shear_lag("Double Angle", bp.bolts_per_line)
    Ut = st.slider("Block shear Ut", 0.3, 1.0, 0.6, 0.05,
                            help="Ut = 0.60 for double angles connected by one leg (Cl. 13.11)",
                            key="da_ut")

    st.subheader("Slenderness (Cl. 10.4.2)")
    L_m = st.number_input("Unbraced length L (mm)", min_value=0.0, value=0.0,
                                    step=100.0, key="da_L")
    ry_col = next((c for c in df.columns if "ry_s0" in c.lower()), None)
    r_min  = float(row[ry_col]) if ry_col else (min(legs) / math.sqrt(12))
    slend  = (L_m / r_min) if r_min > 0 and L_m > 0 else 0.0

    st.divider()

    grid = build_bolt_grid(bp)
    paths_one = detect_net_section_paths(
        Ag=Ag / 2.0, t=t, d_eff=d_eff, bolts=grid,
        connected_parts=1, pitch_mm=bp.pitch, gauge_mm=bp.gauge,
    )
    
    if not paths_one:
        st.error("No feasible net fracture path.")
        return

    gov_path = min(paths_one, key=lambda p: p["An_mm2"])
    An_pair = gov_path["An_mm2"] * 2.0

    df_p = pd.DataFrame([{
        "Path": p["description"],
        "Holes": p["n_holes"],
        "Ag start — per angle (mm²)": round(p["Ag_mm2"], 1),
        "Hole deduction — per angle (mm²)": round(
            p["hole_deduction_mm2"], 1
        ),
        "Stagger length (mm)": round(
            p["stagger_term"], 2
        ),
        "Stagger addition — per angle (mm²)": round(
            p["stagger_area_mm2"], 1
        ),
        "An — pair (mm²)": round(
            p["An_mm2"] * 2.0, 1
        ),
        "Ane = UAn — pair (mm²)": round(
            U * p["An_mm2"] * 2.0, 1
        ),
    } for p in paths_one])
    

    calcs = [
        calc_gross_yield(Ag, mat.Fy),
        calc_net_fracture_paths(paths_one, U, mat.Fu, area_mult=2.0,
    area_label="Areas doubled: pair of angles (2x per-leg An)",
    table=df_p),
        ]
    

    #Table of net fracture paths ^

    el = resolve_connected_element("Single Angle", "leg",
                                       {"leg_conn": w_conn, "t": t})
    bs_pats = detect_block_shear_paths(bp, el, d_eff)

    bs_calc, bs_gov = calc_block_shear_paths(bs_pats, mat.Fy, mat.Fu, Ut)

    geom = dict(
        w_conn=w_conn, n_lines=bp.n_lines, bolts_per_line=bp.bolts_per_line,
        pitch=bp.pitch, gauge=bp.gauge, edge_end=bp.edge_end,
        edge_trans=bp.edge_trans, hole_dia=hole_dia,
    )
    from path_thumbnails import render_net_paths, render_block_patterns
    render_net_paths(paths_one, geom, U=U, Fu=mat.Fu, area_mult=2.0,
                     gov_desc=gov_path["description"])
    render_block_patterns(bs_pats, geom, Fy=mat.Fy, Fu=mat.Fu, Ut=Ut,
                          area_mult=2.0, gov_key=bs_gov)

    with st.expander("Net fracture paths (per angle leg)", expanded=False):
        st.info(f"Shear lag: {U_note}")

        st.dataframe(df_p, use_container_width=True)

    if L_m > 0:
        with st.expander("Slenderness check (Cl. 10.4.2)", expanded=True):
            st.write(f"ry (s=0) = {r_min:.1f} mm   |   L/r = {slend:.0f}")
            if slend > MAX_SLEND:
                st.error(f"L/r = {slend:.0f} > 300 — exceeds maximum slenderness")
            else:
                st.success(f"L/r = {slend:.0f} <= 300  PASS")

    _show_results(calcs, Tf, "Double Angle", show_steps=True)

    
    if HAS_SECTION_DIAGRAMS:
        st.subheader("Member Detail - Three Views")
        gusset_t = st.number_input("Gusset plate thickness (mm)",
                                            min_value=3.0, max_value=50.0,
                                            value=10.0, step=1.0, key="da_gt")
        svg3 = double_angle_diagram(
            leg_conn=w_conn,
            leg_out=(legs[1] if "Leg 1" in conn_leg else legs[0]),
            t=t,
            gusset_t=float(gusset_t),
            n_lines=bp.n_lines,
            bolts_per_line=bp.bolts_per_line,
            pitch=bp.pitch,
            gauge=bp.gauge,
            edge_end=bp.edge_end,
            edge_trans=bp.edge_trans,
            hole_dia=hole_dia,
            show_net_fracture=True,
            zig_zag="zig" in gov_path["description"].lower(),
            show_block_shear=True,
            governing_bs= bs_gov,
            section_label=chosen,
        )
        components.html(svg3, height=1350, scrolling=True)



def panel_wt(render_material) -> None:
    st.subheader("Section — WT (Structural Tee)")
    df = load_wt_table()
    if df.empty:
        st.warning(
            "Structural_Tees_WT_Properties.csv not found in data/ folder. "
            "Add the CSV to enable this section type."
        )
        return

    chosen = st.selectbox("WT designation", sorted(df["designation"].tolist(), key=_nat_key), key="wt_des")
    row    = df.loc[df["designation"] == chosen].iloc[0]
    Ag     = float(row["Area_mm2"])
    t_fl   = float(row["t_mm"])
    t_st   = float(row["w_mm"])
    b_fl   = float(row["b_mm"])
    d_dep  = float(row["d_mm"])
    rx     = float(row["rx_mm"])
    ry     = float(row["ry_mm"])

    with st.expander("Section properties", expanded=True):
        cc = st.columns(5)
        cc[0].metric("Ag (mm2)", f"{Ag:,.0f}")
        cc[1].metric("d (mm)", f"{d_dep:.1f}")
        cc[2].metric("b (mm)", f"{b_fl:.1f}")
        cc[3].metric("t flange (mm)", f"{t_fl:.1f}")
        cc[4].metric("w stem (mm)", f"{t_st:.1f}")
        cc2 = st.columns(5)
        cc2[0].metric("rx (mm)", f"{rx:.1f}")
        cc2[1].metric("ry (mm)", f"{ry:.1f}")

    mat, Tf = render_material()

    st.subheader("Connection Type")
    conn_el      = st.radio("Connected element", ["Flange", "Stem"], horizontal=True, key="wt_el")
    connected_el = "flange" if conn_el == "Flange" else "stem"
    t_conn       = t_fl if connected_el == "flange" else t_st
    w_conn       = b_fl if connected_el == "flange" else d_dep
    Ut_def       = 1.0  if connected_el == "flange" else 0.6

    _, hole_dia, allowance = _bolt_hole_inputs("wt")
    bp = _bolt_pattern_inputs("wt")

    d_eff     = hole_dia + allowance
    U, U_note = shear_lag("WT Section", bp.bolts_per_line, connected_el,
                                b_flange=b_fl, d_depth=d_dep)
    Ut = st.slider("Block shear Ut", 0.3, 1.0, Ut_def, 0.05,
                            help="Ut = 1.0 flange-connected; 0.6 stem-connected (Cl. 13.11)",
                            key="wt_ut")

    st.subheader("Slenderness (Cl. 10.4.2)")
    L_m   = st.number_input("Unbraced length L (mm)", min_value=0.0, value=0.0,
                                step=100.0, key="wt_L")
    r_min = min(rx, ry)
    slend = (L_m / r_min) if r_min > 0 and L_m > 0 else 0.0

    st.divider()

    paths = net_paths(w_conn, bp, hole_dia, allowance, t_conn)
    if not paths:
        st.error("No feasible net fracture path.")
        return
    gov_path = min(paths, key=lambda p: p["An_mm2"])
    An = gov_path["An_mm2"]

    calcs = [
        calc_gross_yield(Ag, mat.Fy),
        calc_net_fracture_paths(paths, U, mat.Fu),
    ]
    bs_pats = block_shear_paths(bp, t_conn, d_eff)
    bs_calc, bs_gov = calc_block_shear_paths(bs_pats, mat.Fy, mat.Fu, Ut)
    calcs.append(bs_calc)

    with st.expander("Net fracture paths", expanded=False):
        st.info(f"Shear lag: {U_note}")
        df_p = pd.DataFrame([{
            "Path":      p["description"],
            "wn (mm)":   round(p["wn_mm"], 1),
            "An (mm2)":  round(p["An_mm2"], 1),
            "Ane (mm2)": round(U * p["An_mm2"], 1),
        } for p in paths])
        st.dataframe(df_p, use_container_width=True)

    if L_m > 0:
        with st.expander("Slenderness check (Cl. 10.4.2)", expanded=True):
            st.write(f"r_min = min(rx,ry) = {r_min:.1f} mm   |   L/r = {slend:.0f}")
            if slend > MAX_SLEND:
                st.error(f"L/r = {slend:.0f} > 300 — exceeds maximum slenderness")
            else:
                st.success(f"L/r = {slend:.0f} <= 300  PASS")

    _show_results(calcs, Tf, "WT Section")

    if HAS_WT_DIAGRAM:
        st.subheader("Member Detail - Three Views")
        svg3 = wt_diagram(
            b_flange=b_fl,
            d_depth=d_dep,
            t_flange=t_fl,
            t_stem=t_st,
            connected=connected_el,
            n_lines=bp.n_lines,
            bolts_per_line=bp.bolts_per_line,
            pitch=bp.pitch,
            gauge=bp.gauge,
            edge_end=bp.edge_end,
            edge_trans=bp.edge_trans,
            hole_dia=hole_dia,
            show_net_fracture=True,
            zig_zag="zig" in gov_path["description"].lower(),
            show_block_shear=True,
            governing_bs=bs_gov,
            section_label=f"{chosen} ({conn_el})",
        )
        components.html(svg3, height=1300, scrolling=True)
    elif HAS_SVG:
        st.subheader("Connection Diagram")
        svg = generate_connection_svg(
            n_lines=bp.n_lines, bolts_per_line=bp.bolts_per_line,
            pitch=bp.pitch, gauge=bp.gauge, edge_end=bp.edge_end,
            edge_trans=bp.edge_trans, leg_width=w_conn, thickness=t_conn,
            hole_dia=hole_dia, show_fracture=True, show_block_shear=True,
            section_label=f"{chosen} ({conn_el})",
            governing_path_n_holes=gov_path["n_holes"],
            zig_zag="zig" in gov_path["description"].lower(),
        )
        components.html(svg, height=340)


def panel_channel(render_material) -> None:
    st.subheader("Section — Channel (C / MC Shape)")
    df = load_channel_table()
    if df.empty:
        st.warning(
            "Channel_Sections_Properties.csv not found in data/ folder. "
            "Add the CSV to enable this section type."
        )
        return

    chosen = st.selectbox("Channel designation", sorted(df["designation"].tolist(), key=_nat_key), key="ch_des")
    row    = df.loc[df["designation"] == chosen].iloc[0]
    Ag     = float(row["Area_mm2"])
    t_fl   = float(row["t_mm"])
    t_web  = float(row["w_mm"])
    d_dep  = float(row["d_mm"])
    b_fl   = float(row["b_mm"])
    rx     = float(row.get("rx_mm", 0))
    ry     = float(row.get("ry_mm", 0))

    with st.expander("Section properties", expanded=True):
        cc = st.columns(5)
        cc[0].metric("Ag (mm2)", f"{Ag:,.0f}")
        cc[1].metric("d (mm)", f"{d_dep:.1f}")
        cc[2].metric("b (mm)", f"{b_fl:.1f}")
        cc[3].metric("t flange (mm)", f"{t_fl:.1f}")
        cc[4].metric("w web (mm)", f"{t_web:.1f}")
        cc2 = st.columns(5)
        cc2[0].metric("rx (mm)", f"{rx:.1f}" if rx > 0 else "n/a")
        cc2[1].metric("ry (mm)", f"{ry:.1f}" if ry > 0 else "n/a")

    mat, Tf = render_material()

    st.info("Channels are typically connected through the web. Connected width = depth d.")
    w_conn = d_dep
    t_conn = t_web

    _, hole_dia, allowance = _bolt_hole_inputs("ch")
    bp = _bolt_pattern_inputs("ch")

    d_eff     = hole_dia + allowance
    U, U_note = shear_lag("Channel (C / MC)", bp.bolts_per_line)
    Ut = st.slider("Block shear Ut", 0.3, 1.0, 0.85, 0.05,
                            help="Ut ≈ 0.85 web-bolted channel (Cl. 13.11)",
                            key="ch_ut")

    st.subheader("Slenderness (Cl. 10.4.2)")
    L_m   = st.number_input("Unbraced length L (mm)", min_value=0.0, value=0.0,
                                step=100.0, key="ch_L")
    r_min = min(rx, ry) if rx > 0 and ry > 0 else max(rx, ry)
    slend = (L_m / r_min) if r_min > 0 and L_m > 0 else 0.0

    st.divider()

    paths = net_paths(w_conn, bp, hole_dia, allowance, t_conn)
    if not paths:
        st.error("No feasible net fracture path.")
        return
    gov_path = min(paths, key=lambda p: p["An_mm2"])
    An = gov_path["An_mm2"]

    calcs = [
        calc_gross_yield(Ag, mat.Fy),
        calc_net_fracture_paths(paths, U, mat.Fu),

    ]
    bs_pats = block_shear_paths(bp, t_conn, d_eff)
    bs_calc, bs_gov = calc_block_shear_paths(bs_pats, mat.Fy, mat.Fu, Ut)
    calcs.append(bs_calc)

    with st.expander("Net fracture paths", expanded=False):
        st.info(f"Shear lag: {U_note}")
        df_p = pd.DataFrame([{
            "Path":      p["description"],
            "wn (mm)":   round(p["wn_mm"], 1),
            "An (mm2)":  round(p["An_mm2"], 1),
            "Ane (mm2)": round(U * p["An_mm2"], 1),
        } for p in paths])
        st.dataframe(df_p, use_container_width=True)

    if L_m > 0:
        with st.expander("Slenderness check (Cl. 10.4.2)", expanded=True):
            st.write(f"r_min = {r_min:.1f} mm   |   L/r = {slend:.0f}")
            if slend > MAX_SLEND:
                st.error(f"L/r = {slend:.0f} > 300 — exceeds maximum slenderness")
            else:
                st.success(f"L/r = {slend:.0f} <= 300  PASS")

    _show_results(calcs, Tf, "Channel (C / MC)")

    if HAS_CH_DIAGRAM:
        st.subheader("Member Detail - Three Views")
        svg3 = channel_diagram(
            b_flange=b_fl,
            d_depth=d_dep,
            t_flange=t_fl,
            t_web=t_web,
            n_lines=bp.n_lines,
            bolts_per_line=bp.bolts_per_line,
            pitch=bp.pitch,
            gauge=bp.gauge,
            edge_end=bp.edge_end,
            edge_trans=bp.edge_trans,
            hole_dia=hole_dia,
            show_net_fracture=True,
            zig_zag="zig" in gov_path["description"].lower(),
            show_block_shear=True,
            governing_bs=bs_gov,
            section_label=chosen,
        )
        components.html(svg3, height=1400, scrolling=True)
    elif HAS_SVG:
        st.subheader("Connection Diagram")
        svg = generate_connection_svg(
            n_lines=bp.n_lines, bolts_per_line=bp.bolts_per_line,
            pitch=bp.pitch, gauge=bp.gauge, edge_end=bp.edge_end,
            edge_trans=bp.edge_trans, leg_width=w_conn, thickness=t_conn,
            hole_dia=hole_dia, show_fracture=True, show_block_shear=True,
            section_label=chosen,
            governing_path_n_holes=gov_path["n_holes"],
            zig_zag="zig" in gov_path["description"].lower(),
        )
        components.html(svg, height=340)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    apply_theme()
    render_sidebar_logo()
    render_footer()
    if not st.session_state.get("accepted_disclaimer", False):
        st.error("Access restricted. Please open the Home page and accept the User Access Agreement before continuing.")
        st.stop()

    st.title("CSA S16 — Tension Member Design")
    st.caption(
        "Gross yielding (Cl. 13.2a-i)  |  Net fracture with shear lag (Cl. 12.3.3)  |  "
        "Block shear (Cl. 13.11)  |  Slenderness (Cl. 10.4.2)  |  All dimensions mm, forces kN"
    )
    st.divider()

    st.subheader("1. Section Type")
    sec_type = st.selectbox("Member cross-section type", SECTION_TYPES)

    if sec_type == "Plate":
        panel_plate(render_material)
    elif sec_type == "Single Angle":
        panel_single_angle(render_material)
    elif sec_type == "Double Angle":
        panel_double_angle(render_material)
    elif sec_type == "WT Section":
        panel_wt(render_material)
    elif sec_type == "Channel (C / MC)":
        panel_channel(render_material)

    DATASET_BY_TYPE = {
        "Single Angle":     ("Single Angles (L)", load_angle_table),
        "Double Angle":     ("Double Angles (2L)", load_double_angle_table),
        "WT Section":       ("WT Sections", load_wt_table),
        "Channel (C / MC)": ("Channels (C / MC)", load_channel_table),
    }
    if sec_type in DATASET_BY_TYPE:
        label, loader = DATASET_BY_TYPE[sec_type]
        st.divider()
        st.subheader("Raw Dataset (CISC SST12.1)")
        with st.expander(f"{label} — raw dataset", expanded=False):
            try:
                df_raw = loader()
                if df_raw is None or df_raw.empty:
                    st.warning("Dataset not found.")
                else:
                    st.caption(f"{len(df_raw)} sections")
                    st.dataframe(df_raw, use_container_width=True, height=400)
            except Exception as e:
                st.warning(f"Could not load dataset: {e}")

    st.divider()
    st.caption(
        "Reference: CSA S16-14 Cl. 10.4, 12.2, 12.3, 13.2, 13.11  |  "
        "CISC Handbook of Steel Construction, 11th Ed. "
        "Always verify minimum edge distances and pitch meet CSA S16 detailing requirements."
    )


main()