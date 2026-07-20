from __future__ import annotations

import io
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
# 1_Tension_Members.py → pages → project → data goes up two parent folders, then enters the "data" folder to access the datasets.
#********Check why the other tables aren't here.*****


BOLT_DIA: Dict[str, float] = {
    "M16": 16.0, "M20": 20.0, "M22": 22.0, "M24": 24.0,
    "M27": 27.0, "M30": 30.0, "M36": 36.0,
}
STD_HOLE: Dict[str, float] = {
    "M16": 18.0, "M20": 22.0, "M22": 24.0, "M24": 26.0,
    "M27": 30.0, "M30": 33.0, "M36": 39.0,
}

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

    if None in (des, b, d, t):
        return pd.DataFrame()

    out = pd.DataFrame({
        "designation": df[des].astype(str),
        "leg1":        pd.to_numeric(df[b], errors="coerce"),
        "leg2":        pd.to_numeric(df[d], errors="coerce"),
        "t":           pd.to_numeric(df[t], errors="coerce"),
        "Ag":          pd.to_numeric(df[area], errors="coerce") if area else np.nan,
    })
    mask = out["Ag"].isna()
    out.loc[mask, "Ag"] = (
        out.loc[mask, "t"] *
        (out.loc[mask, "leg1"] + out.loc[mask, "leg2"] - out.loc[mask, "t"])
    )
    return out.dropna(subset=["leg1", "leg2", "t"]).reset_index(drop=True)


# ── Shear lag factor (CSA S16-14 Cl. 12.3.3.2) ───────────────────────────────
def shear_lag(
    section_type:  str,
    n_bolt_rows:   int,
    connected_el:  str   = "",
    b_flange:      float = 0,
    d_depth:       float = 0,
) -> Tuple[float, str]:
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
    width:     float,
    bolt:      BoltPattern,
    hole_dia:  float,
    allowance: float,
    t:         float,
) -> List[Dict]:
    """Enumerate straight and zig-zag net-area paths through bolt holes."""
    d_eff  = hole_dia + allowance
    paths: List[Dict] = []

    for n_holes in range(1, bolt.n_lines + 1):
        wn = width - n_holes * d_eff
        if wn <= 0:
            continue
        paths.append({
            "An_mm2":       wn * t,
            "wn_mm":        wn,
            "n_holes":      n_holes,
            "stagger_term": 0.0,
            "description":  f"Straight — {n_holes} hole{'s' if n_holes > 1 else ''}",
        })

    if bolt.bolts_per_line >= 2 and bolt.n_lines >= 2:
        for n_h in range(2, bolt.n_lines + 1):
            stagger = (n_h - 1) * bolt.pitch ** 2 / (4.0 * bolt.gauge)
            wn      = width - n_h * d_eff + stagger
            An      = wn * t
            if wn > 0 and An > 0:
                paths.append({
                    "An_mm2":       An,
                    "wn_mm":        wn,
                    "n_holes":      n_h,
                    "stagger_term": stagger,
                    "description":  f"Zig-zag — {n_h} holes, {n_h-1} stagger term(s)",
                })

    return [p for p in paths if p["An_mm2"] > 0]


#Net Fracture Calculation
def calc_net_fracture_paths(paths, U, Fu, area_mult=1.0, area_label="", table=None):
    results = []
    for p in paths:
        An_i = p["An_mm2"] * area_mult
        Ane_i = U * An_i
        Tr_i = PHI_U * Ane_i * Fu / 1000.0
        results.append((p, An_i, Ane_i, Tr_i))

    gov = min(results, key=lambda r: r[3])

    steps = [
        "**Net Section Fracture - CSA S16 Cl. 13.2 a) iii)**",
        "- Formula: Tr = phi_u x Ane x Fu, where Ane = U x An (Cl. 12.3.3)",
        f"- Shear lag factor: U = {U:.2f}",
    ]
    if area_label:
        steps.append(f"- {area_label}")

    n = 0
    for p, An_i, Ane_i, Tr_i in results:
        n = n + 1
        tag = "  <-- GOVERNS" if p is gov[0] else ""
        steps.append("---")
        steps.append(f"**Path {n}: {p['description']}{tag}**")
        if p["stagger_term"] > 0:
            steps.append(f"- Net width: wn = {p['wn_mm']:,.1f} mm (incl. stagger s2/4g = {p['stagger_term']:,.2f} mm)")
        else:
            steps.append(f"- Net width: wn = {p['wn_mm']:,.1f} mm")
        steps.append(f"- Net area: An = {An_i:,.1f} mm2")
        steps.append(f"- Effective: Ane = {U:.2f} x {An_i:,.1f} = {Ane_i:,.1f} mm2")
        steps.append(f"- Tr = {PHI_U} x {Ane_i:,.1f} x {Fu:.1f} / 1000 = **{Tr_i:,.1f} kN**")

    steps.append("---")
    steps.append(f"- Governing path: **{gov[0]['description']}** with Tr = **{gov[3]:,.1f} kN**")
    return Calc("Net Section Fracture (Cl. 13.2a-iii)", gov[3], steps, table=table)



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


def block_shear_paths(bolt, t, d_eff):
    """All candidate block shear patterns. Returns list of dicts."""
    Lv = bolt.edge_end + (bolt.bolts_per_line - 1) * bolt.pitch
    Agv = Lv * t
    pats = []
    nl = bolt.n_lines
    w_tens_A = bolt.edge_trans + (nl - 1) * bolt.gauge - (nl - 0.5) * d_eff
    pats.append({
        "key": "A",
        "Ant": max(0.0, w_tens_A) * t,
        "Agv": Agv,
        "planes": 1,
        "description": "A: shear on far line, tension to free edge",
    })
    if nl >= 2:
        pats.append({
            "key": "B",
            "Ant": max(0.0, bolt.edge_trans - 0.5 * d_eff) * t,
            "Agv": Agv,
            "planes": 1,
            "description": "B: shear on edge line, tension to free edge",
        })
        pats.append({
            "key": "C",
            "Ant": max(0.0, (nl - 1) * bolt.gauge - (nl - 1) * d_eff) * t,
            "Agv": Agv,
            "planes": 2,
            "description": "C: shear on both outer lines, tension between lines",
        })
    return pats


def calc_block_shear_paths(pats, Fy, Fu, Ut, area_mult=1.0, area_label=""):
    shear_avg = (Fy + Fu) / 2.0
    results = []
    for p in pats:
        Ant_i = p["Ant"] * area_mult
        Agv_i = p["Agv"] * p["planes"] * area_mult
        Tr_i = PHI_U * (Ut * Ant_i * Fu + 0.6 * Agv_i * shear_avg) / 1000.0
        results.append((p, Ant_i, Agv_i, Tr_i))
    gov = min(results, key=lambda r: r[3])
    steps = [
        "**Block Shear - CSA S16 Cl. 13.11**",
        "- Formula: Tr = phi_u x [Ut x Ant x Fu + 0.6 x Agv x (Fy+Fu)/2]",
        f"- Ut = {Ut:.2f}",
    ]
    if area_label:
        steps.append(f"- {area_label}")
    for p, Ant_i, Agv_i, Tr_i in results:
        tag = "  <-- GOVERNS" if p is gov[0] else ""
        steps.append("---")
        steps.append(f"**Pattern {p['description']}{tag}**")
        steps.append(f"- Ant = {Ant_i:,.1f} mm2  |  Agv = {Agv_i:,.1f} mm2 ({p['planes']} plane(s))")
        steps.append(f"- Tr = **{Tr_i:,.1f} kN**")
    steps.append("---")
    steps.append(f"- Governing: **{gov[0]['description']}** with Tr = **{gov[3]:,.1f} kN**")
    return Calc("Block Shear (Cl. 13.11)", gov[3], steps), gov[0]["key"]


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


def _show_results(calcs: List[Calc], Tf: float, section_type: str) -> None:
    vals = {c.name: c.value for c in calcs}
    gov  = min(vals, key=vals.__getitem__)
    Tr   = vals[gov]

    st.divider()
    st.subheader("Calculations — Shown Work")

    for c in calcs:
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

        Fy_def, Fu_def = GRADES[grade_sel]
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
            "Path":          p["description"],
            "Holes":         p["n_holes"],
            "wn (mm)":       round(p["wn_mm"], 1),
            "s2/4g":         round(p["stagger_term"], 2),
            "An (mm2)":      round(p["An_mm2"], 1),
            "Ane = U*An (mm2)": round(U * p["An_mm2"], 1),
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

    with st.expander("Section properties", expanded=True):
        cc = st.columns(4)
        cc[0].metric("Leg 1 (mm)", f"{leg1:.1f}")
        cc[1].metric("Leg 2 (mm)", f"{leg2:.1f}")
        cc[2].metric("t (mm)", f"{t:.1f}")
        cc[3].metric("Ag (mm2)", f"{Ag:,.0f}")

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
    r_col = next((c for c in df.columns if "r" in c.lower()), None)
    r_min = float(row[r_col]) if r_col else (min(leg1, leg2) / math.sqrt(12))
    slend = (L_m / r_min) if r_min > 0 and L_m > 0 else 0.0

    st.divider()

    paths = net_paths(w_conn, bp, hole_dia, allowance, t)
    if not paths:
        st.error("No feasible net fracture path.")
        return
    gov_path = min(paths, key=lambda p: p["An_mm2"])
    An = gov_path["An_mm2"]

    calcs = [
        calc_gross_yield(Ag, mat.Fy),
        calc_net_fracture_paths(paths, U, mat.Fu),
    ]
    bs_pats = block_shear_paths(bp, t, d_eff)
    bs_calc, bs_gov = calc_block_shear_paths(bs_pats, mat.Fy, mat.Fu, Ut)
    calcs.append(bs_calc)

    with st.expander("Net fracture paths", expanded=False):
        st.info(f"Shear lag: {U_note}")
        df_p = pd.DataFrame([{
            "Path":     p["description"],
            "Holes":    p["n_holes"],
            "wn (mm)":  round(p["wn_mm"], 1),
            "s2/4g":    round(p["stagger_term"], 2),
            "An (mm2)": round(p["An_mm2"], 1),
            "Ane (mm2)":round(U * p["An_mm2"], 1),
        } for p in paths])
        st.dataframe(df_p, use_container_width=True)

    if L_m > 0:
        with st.expander("Slenderness check (Cl. 10.4.2)", expanded=True):
            st.write(f"r_min = {r_min:.1f} mm   |   L/r = {slend:.0f}")
            if slend > MAX_SLEND:
                st.error(f"L/r = {slend:.0f} > 300 — exceeds maximum slenderness")
            else:
                st.success(f"L/r = {slend:.0f} <= 300  PASS")

    _show_results(calcs, Tf, "Single Angle")


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

    paths_one = net_paths(w_conn, bp, hole_dia, allowance, t)
    if not paths_one:
        st.error("No feasible net fracture path.")
        return
    gov_path = min(paths_one, key=lambda p: p["An_mm2"])
    An_pair  = gov_path["An_mm2"] * 2.0

    df_p = pd.DataFrame([{
        "Path":          p["description"],
        "An per angle":  round(p["An_mm2"], 1),
        "An pair (mm2)": round(p["An_mm2"] * 2, 1),
        "Ane pair (mm2)":round(U * p["An_mm2"] * 2, 1),
    } for p in paths_one])

    calcs = [
        calc_gross_yield(Ag, mat.Fy),
        calc_net_fracture_paths(paths_one, U, mat.Fu, area_mult=2.0,
    area_label="Areas doubled: pair of angles (2x per-leg An)",
    table=df_p),
     ]

    #Table of net fracture paths ^

    bs_pats = block_shear_paths(bp, t, d_eff)
    bs_calc, bs_gov = calc_block_shear_paths(
        bs_pats, mat.Fy, mat.Fu, Ut, area_mult=2.0,
        area_label="Areas doubled: pair of angles (2x per-angle Ant and Agv)")
    calcs.append(bs_calc)

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

    _show_results(calcs, Tf, "Double Angle")


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
            governing_bs=bs_gov,
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

    st.divider()
    st.caption(
        "Reference: CSA S16-14 Cl. 10.4, 12.2, 12.3, 13.2, 13.11  |  "
        "CISC Handbook of Steel Construction, 11th Ed. "
        "Always verify minimum edge distances and pitch meet CSA S16 detailing requirements."
    )


main()
