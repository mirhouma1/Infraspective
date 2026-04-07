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

import re as _re

try:
    from _theme import apply_theme, render_sidebar_logo, render_footer, gate_disclaimer
except ImportError:
    def apply_theme(): pass
    def render_sidebar_logo(): pass
    def render_footer(): pass
    def gate_disclaimer(): pass


def _nat_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in _re.split(r"(\d+)", str(s))]

try:
    from connection_diagram import generate_connection_svg
    HAS_SVG = True
except ImportError:
    HAS_SVG = False

# ── Constants ─────────────────────────────────────────────────────────────────
PHI       = 0.90
PHI_U     = 0.75
MAX_SLEND = 300

DATA_DIR   = Path(__file__).resolve().parent.parent / "data"
ANGLE_FILE = DATA_DIR / "Angle Properties Table.xlsx"

BOLT_DIA: Dict[str, float] = {
    "M16": 16.0, "M20": 20.0, "M22": 22.0, "M24": 24.0,
    "M27": 27.0, "M30": 30.0, "M36": 36.0,
}
STD_HOLE: Dict[str, float] = {
    "M16": 18.0, "M20": 22.0, "M22": 24.0, "M24": 26.0,
    "M27": 30.0, "M30": 33.0, "M36": 39.0,
}

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

@dataclass
class SectionProps:
    designation: str
    Ag:          float
    t:           float
    r_min:       float = 0.0
    b_flange:    float = 0.0
    d_depth:     float = 0.0
    info:        Dict[str, str] = field(default_factory=dict)

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

# ── Data loaders ──────────────────────────────────────────────────────────────
def _parse_multi_table_csv(text: str, area_col: str = "Area_mm2") -> pd.DataFrame:
    """Parse a CSV that contains multiple sub-tables separated by blank lines."""
    frames: List[pd.DataFrame] = []
    current_header: Optional[List[str]] = None
    current_rows:   List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            if current_header and current_rows:
                buf = "\n".join([",".join(current_header)] + current_rows)
                try:
                    frames.append(pd.read_csv(io.StringIO(buf)))
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
    path = DATA_DIR / "Double_Angle_Properties.csv"
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
    path = DATA_DIR / "Structural_Tees_WT_Properties.csv"
    if not path.exists():
        return pd.DataFrame()
    lines = [l for l in path.read_text().splitlines() if not l.startswith("#")]
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
    path = DATA_DIR / "Channel_Sections_Properties.csv"
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


# ── Limit-state calculations ──────────────────────────────────────────────────
def calc_gross_yield(Ag: float, Fy: float) -> Calc:
    Tr = PHI * Ag * Fy / 1000.0
    return Calc(
        "Gross Section Yielding (Cl. 13.2a-i)", Tr,
        [
            "Tr = phi * Ag * Fy",
            f"   = {PHI} x {Ag:,.1f} mm2 x {Fy:.1f} MPa / 1000",
            f"   = {Tr:,.1f} kN",
        ],
    )


def calc_net_fracture(An: float, U: float, Fu: float) -> Calc:
    Ane = U * An
    Tr  = PHI_U * Ane * Fu / 1000.0
    return Calc(
        "Net Section Fracture (Cl. 13.2a-iii)", Tr,
        [
            "Ane = U * An",
            f"    = {U:.2f} x {An:,.1f} = {Ane:,.1f} mm2",
            "Tr = phi_u * Ane * Fu",
            f"   = {PHI_U} x {Ane:,.1f} x {Fu:.1f} / 1000",
            f"   = {Tr:,.1f} kN",
        ],
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
            "Tr = phi_u * [Ut*Ant*Fu + 0.6*Agv*(Fy+Fu)/2]",
            f"Agv (total) = {n_shear_planes} plane(s) x {Agv:,.1f} = {Agv_total:,.1f} mm2",
            f"Term1 = {Ut:.2f} x {Ant:,.1f} x {Fu:.1f} = {term1:,.0f} N",
            f"Term2 = 0.6 x {Agv_total:,.1f} x ({Fy:.1f}+{Fu:.1f})/2 = {term2:,.0f} N",
            f"Tr = {PHI_U} x ({term1:,.0f} + {term2:,.0f}) / 1000",
            f"   = {Tr:,.1f} kN",
        ],
    )


def calc_pin(An: float, Fy: float) -> Calc:
    """Cl. 13.2(b): pin connections."""
    Tr = 0.75 * PHI * An * Fy / 1000.0
    return Calc(
        "Pin Connection (Cl. 13.2b)", Tr,
        [
            "Tr = 0.75 * phi * An * Fy",
            f"   = 0.75 x {PHI} x {An:,.1f} x {Fy:.1f} / 1000",
            f"   = {Tr:,.1f} kN",
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
    Ant   = max(0.0, bolt.edge_trans - 0.5 * d_eff) * t
    return Ant, Agv


# ── UI helpers ────────────────────────────────────────────────────────────────
def _bolt_hole_inputs(key_prefix: str) -> Tuple[str, float, float]:
    c1, c2, c3 = st.columns(3)
    with c1:
        bolt_size = st.selectbox("Bolt size", list(BOLT_DIA.keys()), index=1,
                                 key=f"{key_prefix}_bs")
    with c2:
        d_hole_nom = STD_HOLE.get(bolt_size, BOLT_DIA[bolt_size] + 2.0)
        hole_dia   = st.number_input("Hole diameter (mm)", min_value=0.0,
                                     value=float(d_hole_nom), step=1.0,
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

    st.subheader("Results")
    cols = st.columns(len(calcs) + 1)
    for i, c in enumerate(calcs):
        cols[i].metric(
            c.name.split("(")[0].strip(),
            f"{c.value:,.1f} kN",
            delta="<-- governs" if c.name == gov else None,
            delta_color="inverse",
        )
    cols[-1].metric("Governing Tr", f"{Tr:,.1f} kN")

    if Tf > 0:
        util = Tf / Tr
        st.progress(min(util, 1.0))
        lbl = f"Tf / Tr = {util:.3f}  ({Tf:.1f} / {Tr:.1f} kN)"
        if util <= 1.0:
            st.success(f"PASS   {lbl}")
        else:
            st.error(f"FAIL   {lbl}")

    st.divider()
    st.subheader("Calculations — Shown Work")
    for c in calcs:
        with st.expander(c.name, expanded=True):
            for step in c.steps:
                st.code(step, language=None)
            if c.note:
                st.info(c.note)


# ── Section panels ────────────────────────────────────────────────────────────
def panel_plate(mat: Material, Tf: float) -> None:
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
    calcs.append(calc_net_fracture(An, U, mat.Fu))
    Ant, Agv = block_shear_areas(bp, thick, d_eff)
    calcs.append(calc_block_shear(Ant, Agv, mat.Fy, mat.Fu, Ut, n_shear_planes=1))

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


def panel_single_angle(mat: Material, Tf: float) -> None:
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
        calc_net_fracture(An, U, mat.Fu),
    ]
    Ant, Agv = block_shear_areas(bp, t, d_eff)
    calcs.append(calc_block_shear(Ant, Agv, mat.Fy, mat.Fu, Ut, n_shear_planes=2))

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

    if HAS_SVG:
        st.subheader("Connection Diagram")
        svg = generate_connection_svg(
            n_lines=bp.n_lines, bolts_per_line=bp.bolts_per_line,
            pitch=bp.pitch, gauge=bp.gauge, edge_end=bp.edge_end,
            edge_trans=bp.edge_trans, leg_width=w_conn, thickness=t,
            hole_dia=hole_dia, show_fracture=True, show_block_shear=True,
        )
        components.html(svg, height=310)


def panel_double_angle(mat: Material, Tf: float) -> None:
    st.subheader("Section — Double Angle (Back-to-Back)")
    df = load_double_angle_table()
    if df.empty:
        st.warning(
            "Double_Angle_Properties.csv not found in data/ folder. "
            "Add the CSV to enable this section type."
        )
        return

    chosen = st.selectbox("Double angle designation", sorted(df["designation"].tolist(), key=_nat_key), key="da_des")
    row    = df.loc[df["designation"] == chosen].iloc[0]
    Ag     = float(row["Ag"])
    t      = float(row["t"])

    parts = chosen.replace("L", "").split("x")
    try:
        legs = [float(parts[0]), float(parts[1])]
    except Exception:
        legs = [100.0, 100.0]

    with st.expander("Section properties", expanded=True):
        cc = st.columns(3)
        cc[0].metric("Leg 1 (mm)", f"{legs[0]:.0f}")
        cc[1].metric("Leg 2 (mm)", f"{legs[1]:.0f}")
        cc[2].metric("Ag combined (mm2)", f"{Ag:,.0f}")

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

    calcs = [
        calc_gross_yield(Ag, mat.Fy),
        calc_net_fracture(An_pair, U, mat.Fu),
    ]
    Ant_one, Agv_one = block_shear_areas(bp, t, d_eff)
    calcs.append(calc_block_shear(Ant_one * 2, Agv_one * 2, mat.Fy, mat.Fu, Ut, n_shear_planes=1))

    with st.expander("Net fracture paths (per angle leg)", expanded=False):
        st.info(f"Shear lag: {U_note}")
        df_p = pd.DataFrame([{
            "Path":          p["description"],
            "An per angle":  round(p["An_mm2"], 1),
            "An pair (mm2)": round(p["An_mm2"] * 2, 1),
            "Ane pair (mm2)":round(U * p["An_mm2"] * 2, 1),
        } for p in paths_one])
        st.dataframe(df_p, use_container_width=True)

    if L_m > 0:
        with st.expander("Slenderness check (Cl. 10.4.2)", expanded=True):
            st.write(f"ry (s=0) = {r_min:.1f} mm   |   L/r = {slend:.0f}")
            if slend > MAX_SLEND:
                st.error(f"L/r = {slend:.0f} > 300 — exceeds maximum slenderness")
            else:
                st.success(f"L/r = {slend:.0f} <= 300  PASS")

    _show_results(calcs, Tf, "Double Angle")


def panel_wt(mat: Material, Tf: float) -> None:
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
        calc_net_fracture(An, U, mat.Fu),
    ]
    Ant, Agv = block_shear_areas(bp, t_conn, d_eff)
    calcs.append(calc_block_shear(Ant, Agv, mat.Fy, mat.Fu, Ut, n_shear_planes=1))

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


def panel_channel(mat: Material, Tf: float) -> None:
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
        calc_net_fracture(An, U, mat.Fu),
    ]
    Ant, Agv = block_shear_areas(bp, t_conn, d_eff)
    calcs.append(calc_block_shear(Ant, Agv, mat.Fy, mat.Fu, Ut, n_shear_planes=1))

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


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    apply_theme()
    render_sidebar_logo()
    render_footer()
    if not st.session_state.get("accepted_disclaimer", False):
        st.warning("Please accept the User Access Agreement on the Home page before using the calculator.")
        if st.button("Go to Home Page"):
            st.switch_page("app.py")
        st.stop()

    st.title("CSA S16 — Tension Member Design")
    st.caption(
        "Gross yielding (Cl. 13.2a-i)  |  Net fracture with shear lag (Cl. 12.3.3)  |  "
        "Block shear (Cl. 13.11)  |  Slenderness (Cl. 10.4.2)  |  All dimensions mm, forces kN"
    )
    st.divider()

    st.subheader("1. Section Type")
    sec_type = st.selectbox("Member cross-section type", SECTION_TYPES)
    st.divider()

    st.subheader("2. Material")
    GRADES = {
        "G300W  (Fy=300, Fu=440)": (300.0, 440.0),
        "G350W  (Fy=350, Fu=450)": (350.0, 450.0),
        "G400W  (Fy=400, Fu=520)": (400.0, 520.0),
        "G480W  (Fy=480, Fu=590)": (480.0, 590.0),
        "Custom":                   None,
    }
    grade_sel = st.selectbox("Steel grade", list(GRADES.keys()))
    if GRADES[grade_sel]:
        Fy_def, Fu_def = GRADES[grade_sel]
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

    if sec_type == "Plate":
        panel_plate(mat, Tf)
    elif sec_type == "Single Angle":
        panel_single_angle(mat, Tf)
    elif sec_type == "Double Angle":
        panel_double_angle(mat, Tf)
    elif sec_type == "WT Section":
        panel_wt(mat, Tf)
    elif sec_type == "Channel (C / MC)":
        panel_channel(mat, Tf)

    st.divider()
    st.caption(
        "Reference: CSA S16-14 Cl. 10.4, 12.2, 12.3, 13.2, 13.11  |  "
        "CISC Handbook of Steel Construction, 11th Ed. "
        "Always verify minimum edge distances and pitch meet CSA S16 detailing requirements."
    )


main()
