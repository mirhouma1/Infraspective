from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from _theme import apply_theme, render_sidebar_logo, render_footer, gate_disclaimer

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sst12

try:
    import viewer_3d
    HAS_VIEWER = True
except Exception:
    HAS_VIEWER = False

DASH = "-"


# ===========================================================
# UTILITIES
# ===========================================================


def num(x: Any, nd: int = 2) -> str:
    if x is None:
        return DASH
    try:
        xf = float(x)
    except Exception:
        return str(x)
    if not math.isfinite(xf):
        return "inf"
    if abs(xf) >= 100000:
        return "{:,.0f}".format(xf)
    return "{:,.{}f}".format(xf, nd)


def tex_num(x: Any, nd: int = 2) -> str:
    return num(x, nd).replace(",", r"\,")


def _f(x: Any) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except (ValueError, TypeError):
        return None
    return v


def _safe_div(a, b) -> Optional[float]:
    try:
        if b is None or b == 0:
            return None
        return float(a) / float(b)
    except Exception:
        return None


def md(text: str) -> None:
    st.markdown(text, unsafe_allow_html=True)


def _nat_key(s: str):
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r"(\d+)", str(s))]


# ===========================================================
# SECTION SOURCE
#
# Everything is read through the existing sst12.py. That module is not
# modified and no new data module is introduced. The tables it exposes
# are load_all_tables() -> w, hss_square, hss_rect, hss_round, channels,
# wt, double_angles, single_angles.
#
# Families are presented the same way the tension page presents double
# angles: family, then a classification dropdown where the family has
# more than one table, then the designation.
# ===========================================================

SYM_DOUBLE = "doubly symmetric"
SYM_SINGLE = "singly symmetric"
SYM_ASYM = "asymmetric"

# family code -> (label, plate topology, symmetry, geometry family)
FAMILY_SPEC = {
    "W":          ("W shapes",              "I",       SYM_DOUBLE, "W"),
    "HSS_ROUND":  ("HSS round (CHS)",       "CHS",     SYM_DOUBLE, "HSS"),
    "HSS_SQUARE": ("HSS square (SHS)",      "RHS",     SYM_DOUBLE, "HSS"),
    "HSS_RECT":   ("HSS rectangular (RHS)", "RHS",     SYM_DOUBLE, "HSS"),
    "C":          ("C channels",            "CHANNEL", SYM_SINGLE, "CHANNEL"),
    "MC":         ("MC channels",           "CHANNEL", SYM_SINGLE, "CHANNEL"),
    "L":          ("Single angles",         "ANGLE",   SYM_ASYM,   "ANGLE"),
    "2L":         ("Double angles",         "ANGLE",   SYM_SINGLE, "DOUBLE_ANGLE"),
    "WT":         ("WT tees",               "TEE",     SYM_SINGLE, "WT"),
}

FAMILY_ORDER = ["W", "HSS_ROUND", "HSS_SQUARE", "HSS_RECT",
                "C", "MC", "L", "2L", "WT"]

# Families that need a second dropdown, and how the rows are split.
VARIANT_SPEC = {
    "2L": [("2LE", "Equal legs"),
           ("2LL", "Long legs back to back"),
           ("2LS", "Short legs back to back")],
}

# Every family now has an outline builder in section_geometry.py.
VIEWER_OK = {"W", "HSS_ROUND", "HSS_SQUARE", "HSS_RECT",
             "C", "MC", "L", "2L", "WT"}

# Not reachable through sst12.py as written: it reads the W sheet but not
# the S, M or HP sheets, and the HS_* HSS sheets but not the HA_* ones.
NOT_AVAILABLE = (
    "S, M and HP shapes are not reachable through sst12.py, which reads "
    "the W, HSS, C, MC, L, WT and double-angle sheets only. The workbook "
    "also holds a second HSS table with a reduced design wall thickness "
    "that sst12.py does not read."
)


def _parse_legs(des: str) -> Tuple[Optional[float], Optional[float],
                                   Optional[float]]:
    """Leg dimensions from an angle designation, used where the table
    does not carry d, b and t (the double-angle rows)."""
    s = str(des).upper().replace(" ", "")
    s = re.sub(r"^2L[ELS]?", "", s)
    s = re.sub(r"^L", "", s)
    nums = []
    for part in s.split("X"):
        try:
            nums.append(float(part))
        except ValueError:
            pass
    if len(nums) >= 3:
        return max(nums[0], nums[1]), min(nums[0], nums[1]), nums[2]
    return None, None, None


@st.cache_data(ttl=600)
def load_families() -> Dict[str, List[Dict[str, Any]]]:
    """Group every sst12 table into the family/variant buckets this page
    presents. Keys are 'FAMILY' or 'FAMILY|VARIANT'."""
    t = sst12.load_all_tables()
    out: Dict[str, List[Dict[str, Any]]] = {}

    def norm_shared(r, fam):
        return {
            "designation": str(r.get("Designation", "")).strip(),
            "family": fam,
            "d": _f(r.get("d")), "b": _f(r.get("b")),
            "t": _f(r.get("t")), "w": _f(r.get("w")),
            "A": _f(r.get("Area")),
            "rx": _f(r.get("rx")), "ry": _f(r.get("ry")), "rz": None,
            "bt": _f(r.get("ba/t")), "hw": _f(r.get("h/w")),
            "J": _f(r.get("J")), "Cw": _f(r.get("Cw")),
        }

    def norm_mm(r, fam):
        return {
            "designation": str(r.get("Designation", "")).strip(),
            "family": fam,
            "d": _f(r.get("d_mm")), "b": _f(r.get("b_mm")),
            "t": _f(r.get("t_mm")), "w": _f(r.get("w_mm")),
            "A": _f(r.get("Area_mm2")),
            "rx": _f(r.get("rx_mm")),
            "ry": _f(r.get("ry_mm")) or _f(r.get("ry_s0_mm")),
            "rz": None, "bt": None, "hw": None, "J": None, "Cw": None,
        }

    out["W"] = [norm_shared(r, "W") for r in t.get("w", [])]
    out["HSS_SQUARE"] = [norm_shared(r, "HSS_SQUARE")
                         for r in t.get("hss_square", [])]
    out["HSS_RECT"] = [norm_shared(r, "HSS_RECT")
                       for r in t.get("hss_rect", [])]
    out["HSS_ROUND"] = [norm_shared(r, "HSS_ROUND")
                        for r in t.get("hss_round", [])]

    chans = [norm_mm(r, "C") for r in t.get("channels", [])]
    out["C"] = [r for r in chans
                if not r["designation"].upper().startswith("MC")]
    out["MC"] = []
    for r in chans:
        if r["designation"].upper().startswith("MC"):
            r["family"] = "MC"
            out["MC"].append(r)

    out["WT"] = [norm_mm(r, "WT") for r in t.get("wt", [])]

    for r in t.get("single_angles", []):
        rec = {
            "designation": str(r.get("Designation", "")).strip(),
            "family": "L",
            "d": _f(r.get("d (mm)")), "b": _f(r.get("b (mm)")),
            "t": _f(r.get("t (mm)")), "w": _f(r.get("t (mm)")),
            "A": _f(r.get("Area (mm2)")),
            "rx": _f(r.get("rx (mm)")), "ry": _f(r.get("ry (mm)")),
            "rz": _f(r.get("rz (mm)")),
            "bt": None, "hw": None, "J": None, "Cw": None,
        }
        out.setdefault("L", []).append(rec)

    for r in t.get("double_angles", []):
        des = str(r.get("Designation", "")).strip()
        up = des.upper()
        var = "2LE"
        if up.startswith("2LL"):
            var = "2LL"
        elif up.startswith("2LS"):
            var = "2LS"
        lg, ls, lt = _parse_legs(des)
        rec = {
            "designation": des, "family": "2L",
            "d": lg, "b": ls, "t": lt, "w": lt,
            "A": _f(r.get("Area_mm2")),
            "rx": _f(r.get("rx_mm")), "ry": _f(r.get("ry_s0_mm")),
            "rz": None, "bt": None, "hw": None, "J": None, "Cw": None,
        }
        out.setdefault("2L|" + var, []).append(rec)

    for key in list(out.keys()):
        rows = [r for r in out[key]
                if r["designation"] and r["A"] and r["rx"] and r["ry"]]
        rows.sort(key=lambda r: _nat_key(r["designation"]))
        if rows:
            out[key] = rows
        else:
            del out[key]
    return out


def family_options(data) -> List[Tuple[str, str]]:
    out = []
    for code in FAMILY_ORDER:
        if code in data or any(k.startswith(code + "|") for k in data):
            out.append((code, FAMILY_SPEC[code][0]))
    return out


def variant_options(data, family: str) -> List[Tuple[str, str]]:
    spec = VARIANT_SPEC.get(family)
    if not spec:
        return []
    return [(c, l) for c, l in spec if (family + "|" + c) in data]


def rows_for(data, family: str, variant: Optional[str]) -> List[Dict[str, Any]]:
    if variant:
        return data.get(family + "|" + variant, [])
    return data.get(family, [])


# ===========================================================
# SECTION MODEL
# ===========================================================


@dataclass
class SectionProps:
    designation: str
    family: str                 # geometry family for section_geometry.py
    src_family: str             # this page's family code
    family_label: str
    variant_label: str
    kind: str                   # I, RHS, CHS, CHANNEL, TEE, ANGLE
    symmetry: str
    A_mm2: float
    rx_mm: float
    ry_mm: float
    rz_mm: Optional[float] = None
    d_mm: Optional[float] = None
    b_mm: Optional[float] = None
    t_mm: Optional[float] = None
    w_mm: Optional[float] = None
    h_mm: Optional[float] = None
    bt: Optional[float] = None
    hw: Optional[float] = None
    leg_long_mm: Optional[float] = None
    leg_short_mm: Optional[float] = None
    J_mm4: Optional[float] = None
    Cw_mm6: Optional[float] = None
    hss_kind: Optional[str] = None

    def r_bar_o_sq(self, x0: float = 0.0, y0: float = 0.0) -> float:
        return x0 ** 2 + y0 ** 2 + self.rx_mm ** 2 + self.ry_mm ** 2


def build_section(rec: Dict[str, Any], variant_label: str) -> SectionProps:
    fam = rec["family"]
    label, kind, symmetry, geom = FAMILY_SPEC[fam]

    hss_kind = None
    if kind == "CHS":
        hss_kind = "CHS"
    elif kind == "RHS":
        hss_kind = "RHS/SHS"

    h_mm = None
    if kind in ("I", "CHANNEL") and rec["d"] and rec["t"]:
        h_mm = rec["d"] - 2.0 * rec["t"]

    leg_long = leg_short = None
    if kind == "ANGLE":
        legs = [v for v in (rec["d"], rec["b"]) if v]
        if len(legs) == 2:
            leg_long, leg_short = max(legs), min(legs)

    return SectionProps(
        designation=rec["designation"], family=geom, src_family=fam,
        family_label=label, variant_label=variant_label,
        kind=kind, symmetry=symmetry,
        A_mm2=float(rec["A"]), rx_mm=float(rec["rx"]), ry_mm=float(rec["ry"]),
        rz_mm=rec.get("rz"),
        d_mm=rec.get("d"), b_mm=rec.get("b"),
        t_mm=rec.get("t"), w_mm=rec.get("w"), h_mm=h_mm,
        bt=rec.get("bt"), hw=rec.get("hw"),
        leg_long_mm=leg_long, leg_short_mm=leg_short,
        J_mm4=(rec["J"] * 1e3 if rec.get("J") else None),
        Cw_mm6=(rec["Cw"] * 1e9 if rec.get("Cw") else None),
        hss_kind=hss_kind)


# ===========================================================
# PROPERTY DISPLAY - calculation inputs only
#
# The workbook publishes about thirty columns per section. Only the
# values the CSA S16 clauses below consume are shown, so the page never
# reproduces a full published table.
# ===========================================================

_DISPLAY = [
    ("Geometry", [
        ("d_mm", "d", "mm", "Overall depth. Sets h and the Table 1 web width."),
        ("b_mm", "b", "mm",
         "Flange width. Cl. 11.3.1 c) takes b/2 for an I-shape flange."),
        ("t_mm", "t", "mm", "Flange or wall thickness. Denominator of b/t."),
        ("w_mm", "w", "mm", "Web thickness. Denominator of h/w."),
        ("h_mm", "h", "mm", "Clear web depth, d - 2t, per Cl. 11.3.2 d)."),
        ("leg_long_mm", "bl", "mm", "Longer leg. Cl. 13.3.3 leg ratio test."),
        ("leg_short_mm", "bs", "mm", "Shorter leg. Cl. 13.3.3 leg ratio test."),
    ]),
    ("Published ratios", [
        ("bt", "b/t", "", "Published flange ratio, cross-checks Table 1."),
        ("hw", "h/w", "", "Published web ratio, cross-checks Table 1."),
    ]),
    ("Section properties", [
        ("A_mm2", "A", "mm2", "Gross area. Cr = phi x Ae x Fcr."),
        ("rx_mm", "rx", "mm", "Strong-axis radius of gyration. (KL/r)x."),
        ("ry_mm", "ry", "mm", "Weak-axis radius of gyration. (KL/r)y."),
        ("rz_mm", "rz", "mm",
         "Minor principal axis radius. Cl. 13.3.3 lower bound on KL/r."),
        ("J_mm4", "J", "mm4", "St. Venant torsion constant. Fez, Cl. 13.3.2."),
        ("Cw_mm6", "Cw", "mm6", "Warping constant. Fez, Cl. 13.3.2."),
    ]),
]


def display_rows(sec: SectionProps) -> List[Dict[str, Any]]:
    out = []
    for group, spec in _DISPLAY:
        for key, symbol, unit, why in spec:
            val = getattr(sec, key, None)
            if val is None:
                continue
            out.append({"group": group, "symbol": symbol, "value": val,
                        "unit": unit, "why": why})
    return out


# ===========================================================
# TABLE 1 - ONLY THE ELEMENTS THIS SECTION HAS
# ===========================================================


@dataclass
class ElementCheck:
    key: str
    label: str
    condition: str
    elements: str
    why: str
    limit_formula: str = ""
    width_clause: str = ""
    width_steps: List[str] = field(default_factory=list)
    ratio_step: str = ""
    limit_step: str = ""
    ratio: Optional[float] = None
    limit: Optional[float] = None
    symbol: str = "b_{el}/t"
    limits: List[float] = field(default_factory=list)
    limit_formulas: List[str] = field(default_factory=list)
    limit_steps: List[str] = field(default_factory=list)
    narrative: List[str] = field(default_factory=list)
    section_class: Optional[int] = None

    @property
    def ok(self) -> Optional[bool]:
        if self.ratio is None or self.limit is None:
            return None
        return self.ratio <= self.limit


def table1_elements(sec: SectionProps, Fy: float) -> List[ElementCheck]:
    sq = math.sqrt(float(Fy))
    kind = sec.kind
    out: List[ElementCheck] = []

    def limstep(const, val, over_sqrt=True):
        if over_sqrt:
            return (r"\text{limit} = \frac{" + str(int(const))
                    + r"}{\sqrt{F_y}} = \frac{" + str(int(const))
                    + r"}{\sqrt{" + tex_num(Fy, 0) + r"}} = \frac{"
                    + str(int(const)) + r"}{" + tex_num(sq, 3) + r"} = "
                    + tex_num(val, 2))
        return (r"\text{limit} = \frac{" + tex_num(const, 0) + r"}{F_y}"
                r" = \frac{" + tex_num(const, 0) + r"}{" + tex_num(Fy, 0)
                + r"} = " + tex_num(val, 2))

    if kind in ("I", "TEE", "CHANNEL"):
        if sec.b_mm is not None and sec.t_mm:
            if kind == "CHANNEL":
                b_el = sec.b_mm
                wsteps = [r"b_{el} = b = " + tex_num(sec.b_mm, 1)
                          + r"\ \text{mm}"]
                wc = ("Cl. 11.3.1 b) - flanges of channels take the full "
                      "nominal width")
            else:
                b_el = sec.b_mm / 2.0
                wsteps = [r"b_{el} = \frac{b}{2} = \frac{"
                          + tex_num(sec.b_mm, 1) + r"}{2} = "
                          + tex_num(b_el, 1) + r"\ \text{mm}"]
                wc = ("Cl. 11.3.1 c) - flanges of beams and T-sections take "
                      "one-half the nominal width, because the web divides "
                      "the flange into two outstands")
            v = 200.0 / sq
            out.append(ElementCheck(
                key="t1_flange",
                label="Flange - supported along one edge, free at the other",
                condition="Element supported along ONE edge",
                elements="Flanges of I-sections, T-sections and channels",
                why=("The flange is joined to the web along one edge only. "
                     "Its outer edge is free, which is the least stiff plate "
                     "boundary, so it carries the most severe limit in "
                     "Table 1."),
                limit_formula=r"\frac{b_{el}}{t} \leq \frac{200}{\sqrt{F_y}}",
                width_clause=wc, width_steps=wsteps,
                ratio_step=(r"\frac{b_{el}}{t} = \frac{" + tex_num(b_el, 1)
                            + r"}{" + tex_num(sec.t_mm, 1) + r"} = "
                            + tex_num(_safe_div(b_el, sec.t_mm), 2)),
                limit_step=limstep(200, v),
                ratio=_safe_div(b_el, sec.t_mm), limit=v))

        if kind == "TEE":
            if sec.d_mm is not None and sec.w_mm:
                v = 340.0 / sq
                out.append(ElementCheck(
                    key="t1_stem",
                    label="Stem - one edge, restrained by a stiffer flange",
                    condition=("Element supported along ONE edge and "
                               "restrained by a substantially stiffer plate"),
                    elements="Stems of T-sections",
                    why=("The stem hangs from a flange that is much stiffer "
                         "than the stem itself. That restraint at the "
                         "supported edge raises the limit from 200 to 340."),
                    limit_formula=(r"\frac{b_{el}}{w} \leq "
                                   r"\frac{340}{\sqrt{F_y}}"),
                    width_clause=("Cl. 11.3.1 b) - stems take the full "
                                  "nominal depth"),
                    width_steps=[r"b_{el} = d = " + tex_num(sec.d_mm, 1)
                                 + r"\ \text{mm}"],
                    ratio_step=(r"\frac{b_{el}}{w} = \frac{"
                                + tex_num(sec.d_mm, 1) + r"}{"
                                + tex_num(sec.w_mm, 1) + r"} = "
                                + tex_num(_safe_div(sec.d_mm, sec.w_mm), 2)),
                    limit_step=limstep(340, v),
                    ratio=_safe_div(sec.d_mm, sec.w_mm), limit=v,
                    symbol="b_{el}/w"))
        elif sec.h_mm is not None and sec.w_mm:
            v = 670.0 / sq
            out.append(ElementCheck(
                key="t1_web",
                label="Web - supported along both edges",
                condition="Element supported along TWO edges",
                elements=("Web of I-shape sections; web supported on both "
                          "edges"),
                why=("The web is joined to a flange at the top edge and again "
                     "at the bottom edge. Two supported edges is a far "
                     "stiffer boundary than one, so the limit rises from 200 "
                     "to 670."),
                limit_formula=r"\frac{h}{w} \leq \frac{670}{\sqrt{F_y}}",
                width_clause=("Cl. 11.3.2 d) - for webs of hot-rolled "
                              "sections the width is the clear distance "
                              "between flanges"),
                width_steps=[r"h = d - 2t = " + tex_num(sec.d_mm, 1)
                             + r" - 2(" + tex_num(sec.t_mm, 1) + r") = "
                             + tex_num(sec.h_mm, 1) + r"\ \text{mm}"],
                ratio_step=(r"\frac{h}{w} = \frac{" + tex_num(sec.h_mm, 1)
                            + r"}{" + tex_num(sec.w_mm, 1) + r"} = "
                            + tex_num(_safe_div(sec.h_mm, sec.w_mm), 2)),
                limit_step=limstep(670, v),
                ratio=_safe_div(sec.h_mm, sec.w_mm), limit=v, symbol="h/w"))

    elif kind == "ANGLE":
        leg = sec.leg_long_mm if sec.leg_long_mm is not None else sec.b_mm
        if leg is not None and sec.t_mm:
            v = 250.0 / sq
            out.append(ElementCheck(
                key="t1_leg",
                label="Leg of angle - supported at the heel only",
                condition="Element supported along ONE edge",
                elements="Legs of angles",
                why=("Each leg is connected only at the heel and is free at "
                     "the toe. Table 1 gives angle legs their own limit "
                     "of 250."),
                limit_formula=r"\frac{b_{el}}{t} \leq \frac{250}{\sqrt{F_y}}",
                width_clause=("Cl. 11.3.1 b) - legs take the full nominal "
                              "dimension"),
                width_steps=[r"b_{el} = " + tex_num(leg, 1)
                             + r"\ \text{mm}\quad(\text{longer leg governs})"],
                ratio_step=(r"\frac{b_{el}}{t} = \frac{" + tex_num(leg, 1)
                            + r"}{" + tex_num(sec.t_mm, 1) + r"} = "
                            + tex_num(_safe_div(leg, sec.t_mm), 2)),
                limit_step=limstep(250, v),
                ratio=_safe_div(leg, sec.t_mm), limit=v))

    elif kind == "CHS":
        if sec.d_mm is not None and sec.t_mm:
            v = 23000.0 / float(Fy)
            out.append(ElementCheck(
                key="t1_chs",
                label="Circular tube wall",
                condition="Circular hollow sections",
                elements="Circular hollow sections",
                why=("A circular tube wall has no free edge anywhere. Its "
                     "limit is written on D/t and is divided by F_y rather "
                     "than by the square root of F_y."),
                limit_formula=r"\frac{D}{t} \leq \frac{23\,000}{F_y}",
                width_clause="Nominal outside diameter",
                width_steps=[r"D = " + tex_num(sec.d_mm, 1) + r"\ \text{mm}"],
                ratio_step=(r"\frac{D}{t} = \frac{" + tex_num(sec.d_mm, 1)
                            + r"}{" + tex_num(sec.t_mm, 1) + r"} = "
                            + tex_num(_safe_div(sec.d_mm, sec.t_mm), 2)),
                limit_step=limstep(23000, v, over_sqrt=False),
                ratio=_safe_div(sec.d_mm, sec.t_mm), limit=v, symbol="D/t"))

    elif kind == "RHS":
        v = 670.0 / sq
        if sec.b_mm is not None and sec.t_mm:
            b_el = sec.b_mm - 4.0 * sec.t_mm
            out.append(ElementCheck(
                key="t1_hss_flange",
                label="Flange wall - supported along both edges",
                condition="Element supported along TWO edges",
                elements="Flanges of rectangular hollow sections",
                why=("Each wall of a closed tube runs continuously into the "
                     "two walls beside it, so every wall is supported on two "
                     "edges."),
                limit_formula=r"\frac{b_{el}}{t} \leq \frac{670}{\sqrt{F_y}}",
                width_clause=("Cl. 11.3.2 b) - the width is the outside "
                              "dimension less four wall thicknesses, which "
                              "removes the two corner radii"),
                width_steps=[r"b_{el} = b - 4t = " + tex_num(sec.b_mm, 1)
                             + r" - 4(" + tex_num(sec.t_mm, 1) + r") = "
                             + tex_num(b_el, 1) + r"\ \text{mm}"],
                ratio_step=(r"\frac{b_{el}}{t} = \frac{" + tex_num(b_el, 1)
                            + r"}{" + tex_num(sec.t_mm, 1) + r"} = "
                            + tex_num(_safe_div(b_el, sec.t_mm), 2)),
                limit_step=limstep(670, v),
                ratio=_safe_div(b_el, sec.t_mm), limit=v))
        if sec.d_mm is not None and sec.t_mm:
            h_el = sec.d_mm - 4.0 * sec.t_mm
            out.append(ElementCheck(
                key="t1_hss_web",
                label="Web wall - supported along both edges",
                condition="Element supported along TWO edges",
                elements="Webs of rectangular hollow sections",
                why="The deeper wall of the tube, checked the same way.",
                limit_formula=(r"\frac{h_{el}}{t} \leq "
                               r"\frac{670}{\sqrt{F_y}}"),
                width_clause="Cl. 11.3.2 b)",
                width_steps=[r"h_{el} = d - 4t = " + tex_num(sec.d_mm, 1)
                             + r" - 4(" + tex_num(sec.t_mm, 1) + r") = "
                             + tex_num(h_el, 1) + r"\ \text{mm}"],
                ratio_step=(r"\frac{h_{el}}{t} = \frac{" + tex_num(h_el, 1)
                            + r"}{" + tex_num(sec.t_mm, 1) + r"} = "
                            + tex_num(_safe_div(h_el, sec.t_mm), 2)),
                limit_step=limstep(670, v),
                ratio=_safe_div(h_el, sec.t_mm), limit=v,
                symbol="h_{el}/t"))

    return out


# ===========================================================
# TABLE 2
# ===========================================================


def _class_of(ratio: float, limits: List[float]) -> Tuple[int, List[str]]:
    lines = []
    for i, lv in enumerate(limits, start=1):
        if ratio <= lv:
            lines.append(r"\text{Class }" + str(i) + r":\quad "
                         + tex_num(ratio, 2) + r" \leq " + tex_num(lv, 2)
                         + r"\quad\checkmark\ \Rightarrow\ \textbf{Class }"
                         + str(i))
            return i, lines
        lines.append(r"\text{Class }" + str(i) + r":\quad "
                     + tex_num(ratio, 2) + r" > " + tex_num(lv, 2)
                     + r"\quad\times\ \text{not Class }" + str(i))
    lines.append(r"\text{Exceeds every Class 3 limit}\ \Rightarrow\ "
                 r"\textbf{Class 4 (slender)}")
    return 4, lines


def table2_elements(sec: SectionProps, Fy: float, Cf_kN: float,
                    phi: float) -> List[ElementCheck]:
    sq = math.sqrt(float(Fy))
    kind = sec.kind
    out: List[ElementCheck] = []

    def three(consts, sym="b_{el}", den="t"):
        vals = [c / sq for c in consts]
        steps = [r"\text{Class }" + str(i + 1) + r"\text{ limit} = \frac{"
                 + str(int(c)) + r"}{\sqrt{" + tex_num(Fy, 0) + r"}} = "
                 + tex_num(v, 2) for i, (c, v) in enumerate(zip(consts, vals))]
        forms = [r"\frac{" + sym + r"}{" + den + r"} \leq \frac{"
                 + str(int(c)) + r"}{\sqrt{F_y}}" for c in consts]
        return vals, steps, forms

    if kind in ("I", "TEE"):
        if sec.b_mm is not None and sec.t_mm:
            b_el = sec.b_mm / 2.0
            vals, steps, forms = three([145.0, 170.0, 200.0])
            r = b_el / sec.t_mm
            cls, narr = _class_of(r, vals)
            out.append(ElementCheck(
                key="t2_flange",
                label="Flange in flexural compression - one edge free",
                condition=("Supported along ONE edge, under flexural "
                           "compression"),
                elements=("Flanges of I-sections or T-sections under bending "
                          "about the major axis"),
                why=("Under bending the outer fibre of the flange reaches "
                     "yield first. How much rotation the section can sustain "
                     "before that flange buckles is what separates Class 1 "
                     "from 2 and 3."),
                width_clause="Cl. 11.3.1 c)",
                width_steps=[r"b_{el} = \frac{b}{2} = \frac{"
                             + tex_num(sec.b_mm, 1) + r"}{2} = "
                             + tex_num(b_el, 1) + r"\ \text{mm}"],
                ratio_step=(r"\frac{b_{el}}{t} = \frac{" + tex_num(b_el, 1)
                            + r"}{" + tex_num(sec.t_mm, 1) + r"} = "
                            + tex_num(r, 2)),
                ratio=r, limits=vals, limit_steps=steps, limit_formulas=forms,
                narrative=narr, section_class=cls))

        if kind == "TEE" and sec.d_mm is not None and sec.w_mm:
            vals, steps, forms = three([145.0, 170.0, 340.0],
                                       sym="b_{el}", den="w")
            r = sec.d_mm / sec.w_mm
            cls, narr = _class_of(r, vals)
            out.append(ElementCheck(
                key="t2_stem",
                label="Stem in flexural compression - part in traction",
                condition=("Supported along ONE edge, compressive stress "
                           "with part of the element in traction"),
                elements="Stems of T-sections",
                why=("A T-stem in bending has part of its depth in tension, "
                     "which delays local buckling and relaxes the Class 3 "
                     "limit from 200 to 340."),
                width_clause="Cl. 11.3.1 b)",
                width_steps=[r"b_{el} = d = " + tex_num(sec.d_mm, 1)
                             + r"\ \text{mm}"],
                ratio_step=(r"\frac{b_{el}}{w} = \frac{"
                            + tex_num(sec.d_mm, 1) + r"}{"
                            + tex_num(sec.w_mm, 1) + r"} = " + tex_num(r, 2)),
                ratio=r, limits=vals, limit_steps=steps, limit_formulas=forms,
                narrative=narr, section_class=cls, symbol="b_{el}/w"))

        if kind == "I" and sec.h_mm is not None and sec.w_mm:
            Cy = sec.A_mm2 * float(Fy) / 1000.0
            cfr = _safe_div(Cf_kN, phi * Cy) or 0.0
            vals = [(1100.0 / sq) * (1 - 0.39 * cfr),
                    (1700.0 / sq) * (1 - 0.61 * cfr),
                    (1900.0 / sq) * (1 - 0.65 * cfr)]
            coefs = [(1100, 0.39), (1700, 0.61), (1900, 0.65)]
            steps, forms = [], []
            for i, ((c, k), v) in enumerate(zip(coefs, vals)):
                forms.append(r"\frac{h}{w} \leq \frac{" + str(c)
                             + r"}{\sqrt{F_y}}\left(1 - " + str(k)
                             + r"\,\frac{C_f}{\phi C_y}\right)")
                steps.append(r"\text{Class }" + str(i + 1)
                             + r"\text{ limit} = \frac{" + str(c) + r"}{"
                             + tex_num(sq, 3) + r"}\left(1 - " + str(k)
                             + r"(" + tex_num(cfr, 4) + r")\right) = "
                             + tex_num(v, 2))
            r = sec.h_mm / sec.w_mm
            cls, narr = _class_of(r, vals)
            out.append(ElementCheck(
                key="t2_web",
                label="Web in combined flexure and axial compression",
                condition=("Supported along TWO edges, combined major-axis "
                           "flexure and axial compression"),
                elements="Webs of I-sections",
                why=("Axial load pushes more of the web depth into "
                     "compression, so every limit is reduced by a factor "
                     "that grows with the axial ratio."),
                width_clause="Cl. 11.3.2 d)",
                width_steps=[
                    r"C_y = A F_y = " + tex_num(sec.A_mm2, 0) + r" \times "
                    + tex_num(Fy, 0) + r" = " + tex_num(Cy, 1)
                    + r"\ \text{kN}",
                    r"\frac{C_f}{\phi C_y} = \frac{" + tex_num(Cf_kN, 1)
                    + r"}{" + tex_num(phi, 2) + r" \times " + tex_num(Cy, 1)
                    + r"} = " + tex_num(cfr, 4),
                    r"h = d - 2t = " + tex_num(sec.h_mm, 1) + r"\ \text{mm}"],
                ratio_step=(r"\frac{h}{w} = \frac{" + tex_num(sec.h_mm, 1)
                            + r"}{" + tex_num(sec.w_mm, 1) + r"} = "
                            + tex_num(r, 2)),
                ratio=r, limits=vals, limit_steps=steps, limit_formulas=forms,
                narrative=narr, section_class=cls, symbol="h/w"))

    elif kind == "RHS":
        for key, dim, lbl, symb in (("t2_hss_flange", sec.b_mm, "Flange wall",
                                     "b_{el}/t"),
                                    ("t2_hss_web", sec.d_mm, "Web wall",
                                     "h_{el}/t")):
            if dim is None or not sec.t_mm:
                continue
            b_el = dim - 4.0 * sec.t_mm
            vals, steps, forms = three([420.0, 525.0, 670.0])
            r = b_el / sec.t_mm
            cls, narr = _class_of(r, vals)
            out.append(ElementCheck(
                key=key, label=lbl + " in flexural compression",
                condition="Supported along TWO edges",
                elements="Flanges of rectangular hollow sections",
                why="A tube wall supported on both edges, in flexure.",
                width_clause="Cl. 11.3.2 b)",
                width_steps=[r"b_{el} = " + tex_num(dim, 1) + r" - 4("
                             + tex_num(sec.t_mm, 1) + r") = "
                             + tex_num(b_el, 1) + r"\ \text{mm}"],
                ratio_step=(r"\frac{b_{el}}{t} = \frac{" + tex_num(b_el, 1)
                            + r"}{" + tex_num(sec.t_mm, 1) + r"} = "
                            + tex_num(r, 2)),
                ratio=r, limits=vals, limit_steps=steps, limit_formulas=forms,
                narrative=narr, section_class=cls, symbol=symb))

    elif kind == "CHS":
        if sec.d_mm is not None and sec.t_mm:
            vals = [13000.0 / Fy, 18000.0 / Fy, 66000.0 / Fy]
            forms = [r"\frac{D}{t} \leq \frac{" + c + r"}{F_y}"
                     for c in (r"13\,000", r"18\,000", r"66\,000")]
            steps = [r"\text{Class }" + str(i + 1) + r"\text{ limit} = "
                     + tex_num(v, 2) for i, v in enumerate(vals)]
            r = sec.d_mm / sec.t_mm
            cls, narr = _class_of(r, vals)
            out.append(ElementCheck(
                key="t2_chs", label="Circular tube wall in flexure",
                condition="Circular hollow sections in flexure",
                elements="Circular hollow sections",
                why="A circular tube in bending.",
                width_clause="Nominal outside diameter",
                width_steps=[r"D = " + tex_num(sec.d_mm, 1) + r"\ \text{mm}"],
                ratio_step=(r"\frac{D}{t} = \frac{" + tex_num(sec.d_mm, 1)
                            + r"}{" + tex_num(sec.t_mm, 1) + r"} = "
                            + tex_num(r, 2)),
                ratio=r, limits=vals, limit_steps=steps, limit_formulas=forms,
                narrative=narr, section_class=cls, symbol="D/t"))

    elif kind == "ANGLE":
        leg = sec.leg_long_mm if sec.leg_long_mm is not None else sec.b_mm
        if leg is not None and sec.t_mm:
            vals, steps, forms = three([145.0, 170.0, 200.0])
            r = leg / sec.t_mm
            cls, narr = _class_of(r, vals)
            out.append(ElementCheck(
                key="t2_leg", label="Outstanding leg in flexural compression",
                condition=("Supported along ONE edge, under flexural "
                           "compression"),
                elements=("Outstanding legs of pairs of angles in continuous "
                          "contact"),
                why="The free toe of the leg is the first thing to buckle.",
                width_clause="Cl. 11.3.1 b)",
                width_steps=[r"b_{el} = " + tex_num(leg, 1) + r"\ \text{mm}"],
                ratio_step=(r"\frac{b_{el}}{t} = \frac{" + tex_num(leg, 1)
                            + r"}{" + tex_num(sec.t_mm, 1) + r"} = "
                            + tex_num(r, 2)),
                ratio=r, limits=vals, limit_steps=steps, limit_formulas=forms,
                narrative=narr, section_class=cls))

    return out


# ===========================================================
# BUCKLING
# ===========================================================


def euler_Fe(E, KLr):
    if KLr is None or KLr <= 0:
        return None
    return (math.pi ** 2) * float(E) / (float(KLr) ** 2)


def torsional_Fe(sec, E, G, Kz, Lz, x0, y0):
    if sec.J_mm4 is None or sec.Cw_mm6 is None:
        return None
    ro_sq = sec.r_bar_o_sq(x0, y0)
    if sec.A_mm2 <= 0 or ro_sq <= 0:
        return None
    KzLz = float(Kz) * float(Lz)
    if KzLz <= 0:
        return None
    warp = (math.pi ** 2) * float(E) * float(sec.Cw_mm6) / (KzLz ** 2)
    stv = float(G) * float(sec.J_mm4)
    return (warp + stv) / (float(sec.A_mm2) * ro_sq)


def flexural_torsional_Fe(Fey, Fez, ro_sq, x0, y0):
    if ro_sq <= 0:
        return None, 1.0
    om = 1.0 - (x0 ** 2 + y0 ** 2) / ro_sq
    if om <= 0:
        return None, om
    tot = Fey + Fez
    if tot <= 0:
        return None, om
    rad = max(0.0, 1.0 - (4.0 * Fey * Fez * om) / (tot ** 2))
    return (tot / (2.0 * om)) * (1.0 - math.sqrt(rad)), om


def asymmetric_Fe(Fex, Fey, Fez, ro_sq, x0, y0):
    if ro_sq <= 0:
        return None
    xr, yr = (x0 ** 2) / ro_sq, (y0 ** 2) / ro_sq

    def f(Fe):
        return ((Fe - Fex) * (Fe - Fey) * (Fe - Fez)
                - (Fe ** 2) * (Fe - Fey) * xr
                - (Fe ** 2) * (Fe - Fex) * yr)

    lo, hi = 1e-6, min(Fex, Fey, Fez)
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


# ===========================================================
# SINGLE ANGLE (Cl. 13.3.3)
# ===========================================================


@dataclass
class AngleInput:
    eligible: bool = True
    truss_type: str = "individual"
    connected_through_shorter_leg: bool = False
    rx_connected_mm: Optional[float] = None
    ry_prime_mm: Optional[float] = None
    ineligible_reasons: List[str] = field(default_factory=list)


def angle_modified_KLr(L_mm, sec, ai):
    steps = []
    rx = ai.rx_connected_mm or sec.rx_mm
    ryp = ai.ry_prime_mm or sec.rz_mm or min(sec.rx_mm, sec.ry_mm)
    Lr = _safe_div(L_mm, rx)
    if Lr is None:
        return None, []
    steps.append(r"\frac{L}{r_x} = \frac{" + tex_num(L_mm, 0) + r"}{"
                 + tex_num(rx, 1) + r"} = " + tex_num(Lr, 2))
    if ai.truss_type == "box":
        if Lr <= 75.0:
            KLr = 60.0 + 0.8 * Lr
            steps.append(r"\frac{L}{r_x} \leq 75 \Rightarrow \frac{KL}{r}"
                         r" = 60 + 0.8\left(" + tex_num(Lr, 2)
                         + r"\right) = " + tex_num(KLr, 2))
        else:
            raw = 45.0 + Lr
            KLr = min(raw, 200.0)
            steps.append(r"\frac{L}{r_x} > 75 \Rightarrow \frac{KL}{r}"
                         r" = 45 + " + tex_num(Lr, 2) + r" = "
                         + tex_num(raw, 2)
                         + (r"\ \rightarrow\ 200\ (\text{cap})"
                            if raw > 200 else ""))
        addf, floorf = 6.0, 0.82
    else:
        if Lr <= 80.0:
            KLr = 72.0 + 0.75 * Lr
            steps.append(r"\frac{L}{r_x} \leq 80 \Rightarrow \frac{KL}{r}"
                         r" = 72 + 0.75\left(" + tex_num(Lr, 2)
                         + r"\right) = " + tex_num(KLr, 2))
        else:
            raw = 32.0 + 1.25 * Lr
            KLr = min(raw, 200.0)
            steps.append(r"\frac{L}{r_x} > 80 \Rightarrow \frac{KL}{r}"
                         r" = 32 + 1.25\left(" + tex_num(Lr, 2)
                         + r"\right) = " + tex_num(raw, 2)
                         + (r"\ \rightarrow\ 200\ (\text{cap})"
                            if raw > 200 else ""))
        addf, floorf = 4.0, 0.95

    if (ai.connected_through_shorter_leg and sec.leg_long_mm
            and sec.leg_short_mm and sec.leg_short_mm > 0):
        rt = sec.leg_long_mm / sec.leg_short_mm
        corr = addf * (rt ** 2 - 1.0)
        KLr += corr
        steps.append(r"\text{shorter leg: } +" + str(int(addf))
                     + r"\left[\left(\frac{b_l}{b_s}\right)^2 - 1\right] = "
                     + str(int(addf)) + r"\left[" + tex_num(rt ** 2, 4)
                     + r" - 1\right] = " + tex_num(corr, 2))
        fl = _safe_div(floorf * L_mm, ryp)
        if fl is not None:
            steps.append(r"\text{lower bound} = " + str(floorf)
                         + r"\frac{L}{r'_y} = " + str(floorf) + r"\frac{"
                         + tex_num(L_mm, 0) + r"}{" + tex_num(ryp, 1)
                         + r"} = " + tex_num(fl, 2))
            if fl > KLr:
                KLr = fl
    return KLr, steps


# ===========================================================
# MAIN CHECK
# ===========================================================


@dataclass
class Result:
    is_class4: bool = False
    Ae_mm2: float = 0.0
    KLr_x: Optional[float] = None
    KLr_y: Optional[float] = None
    KLr_gov: Optional[float] = None
    gov_axis: str = ""
    KLr_over: bool = False
    angle_steps: List[str] = field(default_factory=list)
    uses_angle: bool = False
    Fex: Optional[float] = None
    Fey: Optional[float] = None
    Fez: Optional[float] = None
    Feyz: Optional[float] = None
    omega: Optional[float] = None
    Fe: Optional[float] = None
    mode: str = ""
    clause: str = ""
    n: float = 1.34
    n_forced: bool = False
    lam: Optional[float] = None
    Fcr: Optional[float] = None
    Cr_kN: Optional[float] = None
    Cr_yield_kN: Optional[float] = None
    warnings: List[str] = field(default_factory=list)


def run_check(sec, p, ai, class4_from_t1) -> Result:
    R = Result()
    Fy, E, G, phi = p["Fy"], p["E"], p["G"], p["phi"]
    x0, y0 = p["x0"], p["y0"]

    R.is_class4 = class4_from_t1
    R.Ae_mm2 = float(p["Ae"]) if p.get("Ae") else sec.A_mm2
    if R.is_class4 and not p.get("Ae"):
        R.warnings.append(
            "Class 4 section. Cl. 13.3.5 requires a reduced effective area. "
            "The gross area is used below as an upper bound only.")

    if sec.src_family == "L" and ai.eligible:
        R.uses_angle = True
        R.KLr_gov, R.angle_steps = angle_modified_KLr(p["Ly"], sec, ai)
        R.KLr_x = R.KLr_y = R.KLr_gov
        R.gov_axis = "modified"
    else:
        if sec.src_family == "L" and not ai.eligible:
            R.warnings.append(
                "Cl. 13.3.3.1 is not satisfied, so Cl. 13.3.3.4 sends this "
                "member to Cl. 13.3.2 with eccentricity accounted for. The "
                "concentric result below is not sufficient on its own.")
        R.KLr_x = _safe_div(p["Kx"] * p["Lx"], sec.rx_mm)
        R.KLr_y = _safe_div(p["Ky"] * p["Ly"], sec.ry_mm)
        vals = [v for v in (R.KLr_x, R.KLr_y) if v and v > 0]
        R.KLr_gov = max(vals) if vals else None
        if R.KLr_gov is not None:
            R.gov_axis = "x-x" if R.KLr_gov == R.KLr_x else "y-y"

    if not R.KLr_gov:
        return R
    R.KLr_over = R.KLr_gov > 200.0

    R.Fex = euler_Fe(E, R.KLr_x)
    R.Fey = euler_Fe(E, R.KLr_y)
    R.Fez = torsional_Fe(sec, E, G, p["Kz"], p["Lz"], x0, y0)
    ro_sq = sec.r_bar_o_sq(x0, y0)

    if R.uses_angle:
        R.Fe = euler_Fe(E, R.KLr_gov)
        R.mode = "Flexural, modified slenderness"
        R.clause = "Cl. 13.3.3.1"
    elif sec.symmetry == SYM_DOUBLE:
        R.clause = "Cl. 13.3.1" if not R.is_class4 else "Cl. 13.3.2 a)"
        live = [(v, n) for v, n in ((R.Fex, "Flexural about x-x"),
                                    (R.Fey, "Flexural about y-y"),
                                    (R.Fez, "Torsional")) if v is not None]
        R.Fe, R.mode = min(live, key=lambda z: z[0])
        if R.Fez is None:
            R.warnings.append(
                "J or Cw is not carried in this table, so torsional buckling "
                "(Fez) could not be evaluated. For a doubly symmetric shape "
                "that is usually not the governing mode, but confirm it.")
    elif sec.symmetry == SYM_SINGLE:
        R.clause = "Cl. 13.3.2 b)"
        if R.Fey is not None and R.Fez is not None:
            R.Feyz, R.omega = flexural_torsional_Fe(R.Fey, R.Fez, ro_sq,
                                                    x0, y0)
        live = [(v, n) for v, n in ((R.Fex, "Flexural about x-x"),
                                    (R.Feyz, "Flexural-torsional"))
                if v is not None]
        if live:
            R.Fe, R.mode = min(live, key=lambda z: z[0])
        else:
            R.Fe = min(v for v in (R.Fex, R.Fey) if v is not None)
            R.mode = "Flexural only"
        if R.Fez is None:
            R.warnings.append(
                "This is a singly symmetric section, so Cl. 13.3.2 b) "
                "requires the flexural-torsional stress Feyz. J and Cw are "
                "not carried in this table, so Feyz could not be computed "
                "and the result below covers flexural buckling only. It is "
                "NOT a complete Cl. 13.3.2 check.")
        elif x0 == 0.0 and y0 == 0.0:
            R.warnings.append(
                "No shear-centre offset was entered, so Omega collapses to "
                "1.0 and Feyz reduces to min(Fey, Fez). Enter x0 or y0 in "
                "the sidebar for the full Cl. 13.3.2 b) result.")
    else:
        R.clause = "Cl. 13.3.2 c)"
        if None not in (R.Fex, R.Fey, R.Fez):
            R.Fe = asymmetric_Fe(R.Fex, R.Fey, R.Fez, ro_sq, x0, y0)
            R.mode = "Combined flexural-torsional"
        if R.Fe is None:
            live = [(v, n) for v, n in ((R.Fex, "Flexural about x-x"),
                                        (R.Fey, "Flexural about y-y"),
                                        (R.Fez, "Torsional")) if v is not None]
            if live:
                R.Fe, R.mode = min(live, key=lambda z: z[0])
            R.warnings.append(
                "The Cl. 13.3.2 c) cubic needs J, Cw, x0 and y0. Those are "
                "not all carried in this table, so the least of the "
                "available buckling stresses is used instead.")

    if not R.Fe or R.Fe <= 0:
        return R

    R.n = float(p["n"])
    if R.clause.startswith("Cl. 13.3.2") or R.clause == "Cl. 13.3.3.1":
        if abs(R.n - 1.34) > 1e-9:
            R.n_forced = True
        R.n = 1.34
    R.lam = math.sqrt(float(Fy) / R.Fe)
    R.Fcr = float(Fy) / ((1.0 + R.lam ** (2.0 * R.n)) ** (1.0 / R.n))
    R.Cr_kN = phi * R.Ae_mm2 * R.Fcr / 1000.0
    R.Cr_yield_kN = phi * R.Ae_mm2 * float(Fy) / 1000.0
    return R


# ===========================================================
# RENDERING HELPERS
# ===========================================================


def section_heading(text: str) -> None:
    md("<h3 style='margin-bottom:0.2rem'>" + text + "</h3>")


def sub_heading(text: str) -> None:
    md("<p style='font-weight:600;margin:0.9rem 0 0.25rem 0'>" + text + "</p>")


def note(text: str) -> None:
    md("<p style='margin:0.25rem 0 0.6rem 0;line-height:1.55'>" + text + "</p>")


def indent(text: str) -> None:
    md("<p style='margin:0.15rem 0 0.15rem 1.6rem;line-height:1.6'>"
       + text + "</p>")


def render_t1(chk: ElementCheck) -> None:
    note("<i>" + chk.condition + " &mdash; " + chk.elements + "</i>")
    note(chk.why)

    sub_heading("Limit from Table 1")
    st.latex(chk.limit_formula)

    sub_heading("Step 1 &mdash; establish the element width")
    indent(chk.width_clause)
    for s in chk.width_steps:
        st.latex(s)

    sub_heading("Step 2 &mdash; form the width-to-thickness ratio")
    st.latex(chk.ratio_step)

    sub_heading("Step 3 &mdash; evaluate the limit")
    st.latex(chk.limit_step)

    sub_heading("Step 4 &mdash; compare")
    numer, denom = chk.symbol.split("/")
    if chk.ok:
        st.latex(r"\frac{" + numer + r"}{" + denom + r"} = "
                 + tex_num(chk.ratio, 2) + r" \;\leq\; "
                 + tex_num(chk.limit, 2) + r"\qquad\textbf{PASS}")
        st.success("The element satisfies Table 1.")
    else:
        st.latex(r"\frac{" + numer + r"}{" + denom + r"} = "
                 + tex_num(chk.ratio, 2) + r" \;>\; "
                 + tex_num(chk.limit, 2) + r"\qquad\textbf{FAIL}")
        st.error("The element exceeds Table 1, so the section is Class 4 "
                 "(Cl. 11.2).")


def render_t2(chk: ElementCheck) -> None:
    note("<i>" + chk.condition + " &mdash; " + chk.elements + "</i>")
    note(chk.why)

    sub_heading("Limits from Table 2")
    for f in chk.limit_formulas:
        st.latex(f)

    sub_heading("Step 1 &mdash; establish the element width and inputs")
    indent(chk.width_clause)
    for s in chk.width_steps:
        st.latex(s)

    sub_heading("Step 2 &mdash; form the ratio")
    st.latex(chk.ratio_step)

    sub_heading("Step 3 &mdash; evaluate each limit")
    for s in chk.limit_steps:
        st.latex(s)

    sub_heading("Step 4 &mdash; find the class")
    for s in chk.narrative:
        st.latex(s)

    cls = chk.section_class
    if cls == 4:
        st.error("Class 4 &mdash; slender. Cl. 13.5 applies for bending.")
    elif cls == 3:
        st.warning("Class 3 &mdash; yield moment capacity only.")
    else:
        st.success("Class " + str(cls) + " &mdash; plastic moment capacity "
                   "available.")


# ===========================================================
# PAGE
# ===========================================================

apply_theme()
render_sidebar_logo()
render_footer()
gate_disclaimer()

md("<h2 style='margin-bottom:0'>CSA S16 &mdash; Compression Member Design</h2>")
note("Factored axial compressive resistance per Clauses 11, 13.3.1, 13.3.2 "
     "and 13.3.3.")

DATA = load_families()
if not DATA:
    st.error("No section data found. Check that the CISC SST12.1 workbook is "
             "in attached_assets/ at the repository root.")
    st.stop()

# ---- sidebar ----
with st.sidebar:
    st.header("Material")
    Fy = st.number_input("Fy (MPa)", 200.0, 700.0, 350.0, 5.0, key="cFy")
    E = st.number_input("E (MPa)", 150000.0, 250000.0, 200000.0, 1000.0,
                        key="cE")
    G_MPa = st.number_input("G (MPa)", 50000.0, 100000.0, 77000.0, 1000.0,
                            key="cG")
    phi_c = st.number_input("Resistance factor", 0.50, 1.00, 0.90, 0.05,
                            key="cphi")

    st.divider()
    st.header("Fabrication")
    fab = st.radio(
        "Category (sets n in the column curve)",
        ["Hot-rolled or fabricated; HSS Class C, A500, A1085",
         "Welded three-plate, flame-cut flanges; HSS Class H, A1085 S1"],
        index=0, key="cfab")
    n_input = 2.24 if fab.startswith("Welded") else 1.34
    st.caption("n = " + str(n_input))

    st.divider()
    with st.expander("Advanced"):
        st.caption("Shear-centre coordinates for singly symmetric and "
                   "asymmetric sections, Cl. 13.3.2 b) and c).")
        x0 = st.number_input("Shear centre x0 (mm)", -1000.0, 1000.0, 0.0,
                             1.0, key="cx0")
        y0 = st.number_input("Shear centre y0 (mm)", -1000.0, 1000.0, 0.0,
                             1.0, key="cy0")
        use_ae = st.checkbox("Class 4: enter effective area", value=False,
                             key="cuseae")
        Ae_override = None
        if use_ae:
            Ae_override = st.number_input("Ae (mm2)", 100.0, 1e6, 5000.0,
                                          50.0, key="cae")

# ---- 1. section ----
section_heading("1. Section")

fam_opts = family_options(DATA)
fam_codes = [c for c, _l in fam_opts]
fam_labels = {c: l for c, l in fam_opts}

c1, c2, c3 = st.columns([1.1, 1.3, 1.6])

with c1:
    fam_code = st.selectbox("Member family", fam_codes,
                            format_func=lambda c: fam_labels[c], key="cfam")

var_opts = variant_options(DATA, fam_code)
with c2:
    if var_opts:
        var_codes = [c for c, _l in var_opts]
        var_labels = {c: l for c, l in var_opts}
        var_code = st.selectbox("Classification", var_codes,
                                format_func=lambda c: var_labels[c],
                                key="cvar_" + fam_code)
        var_label = var_labels[var_code]
    else:
        var_code = None
        var_label = ""
        st.markdown("&nbsp;", unsafe_allow_html=True)
        st.caption("No sub-classification for this family.")

rows = rows_for(DATA, fam_code, var_code)
with c3:
    if not rows:
        st.warning("No sections in this table.")
        st.stop()
    des_list = [r["designation"] for r in rows]
    des = st.selectbox("Designation", des_list,
                       key="cdes_" + fam_code + "_" + str(var_code))

rec = next((r for r in rows if r["designation"] == des), None)
if rec is None:
    st.error("Could not load " + str(des) + ".")
    st.stop()

try:
    sec = build_section(rec,var_label)
except Exception as exc:
    st.error("Could not build " + str(des) + ": " + str(exc))
    st.stop()

st.caption("Families available here are those sst12.py reads. " + NOT_AVAILABLE)

with st.expander("Section properties  -  " + sec.designation, expanded=False):
    note("Only the values the checks below consume are listed. Each row "
         "states where it is used.")
    _rows = display_rows(sec)
    if not _rows:
        st.warning("No properties available for this section.")
    else:
        _cur = None
        _html = ["<table style='border-collapse:collapse;width:100%'>"]
        for _row in _rows:
            if _row["group"] != _cur:
                _cur = _row["group"]
                _html.append(
                    "<tr><td colspan='3' style='padding:10px 0 3px 0;"
                    "font-weight:600'>" + _cur + "</td></tr>")
            _unit = (" " + _row["unit"]) if _row["unit"] else ""
            _unit = (_unit.replace("mm2", "mm<sup>2</sup>")
                     .replace("mm4", "mm<sup>4</sup>")
                     .replace("mm6", "mm<sup>6</sup>"))
            _html.append(
                "<tr>"
                "<td style='padding:3px 16px 3px 14px;white-space:nowrap'>"
                + _row["symbol"] + "</td>"
                "<td style='padding:3px 16px 3px 0;white-space:nowrap'>"
                + num(_row["value"], 2) + _unit + "</td>"
                "<td style='padding:3px 0;color:#8b949e;font-size:0.88em'>"
                + _row["why"] + "</td></tr>")
        _html.append("</table>")
        md("".join(_html))
    st.caption("Source: CISC Structural Section Tables SST12.1, read at run "
               "time through sst12.py. Only calculation inputs are shown.")

# ---- 2. effective lengths ----
section_heading("2. Effective Lengths")
note("Choose the end restraint per axis, or Custom to enter K directly. "
     "These drive the support symbols on the model at the bottom of the "
     "page.")

# label -> (K, bottom end, top end). The end names drive the support
# symbols drawn on the 3D model.
K_TABLE = {
    "Select end condition":      (None, "", ""),
    "Fixed - Fixed":             (0.65, "Fixed", "Fixed"),
    "Fixed - Pinned":            (0.80, "Fixed", "Pinned"),
    "Fixed - Guided (sway)":     (1.20, "Fixed", "Guided"),
    "Pinned - Pinned":           (1.00, "Pinned", "Pinned"),
    "Pinned - Guided":           (2.00, "Pinned", "Guided"),
    "Fixed - Free (cantilever)": (2.10, "Fixed", "Free"),
    "Custom":                    ("custom", "Custom", "Custom"),
}


def k_selector(label, key):
    """Returns (K, bottom_end, top_end)."""
    choice = st.selectbox(label, list(K_TABLE.keys()), index=0,
                          key=key + "_sel")
    val, bot, top = K_TABLE[choice]
    if val == "custom":
        kv = st.number_input("K value", 0.0, 5.0, 0.0, 0.05,
                             key=key + "_cus")
        return kv, "Custom", "Custom"
    if val is None:
        return 0.0, "", ""
    st.caption("K = " + "{:.2f}".format(val))
    return val, bot, top


gx, gy, gz = st.columns(3)
with gx:
    Kx, x_bot, x_top = k_selector("Kx - strong axis restraint", "kx")
    Lx_m = st.number_input("Lx (m)", 0.0, 50.0, 0.0, 0.10, key="clx")
with gy:
    Ky, y_bot, y_top = k_selector("Ky - weak axis restraint", "ky")
    Ly_m = st.number_input("Ly (m)", 0.0, 50.0, 0.0, 0.10, key="cly")
with gz:
    Kz, z_bot, z_top = k_selector("Kz - torsional restraint", "kz")
    Lz_m = st.number_input("Lz (m)", 0.0, 50.0, 0.0, 0.10, key="clz")

apply_load = st.checkbox("Apply a factored load", value=False, key="cdem")
Cf_kN = 0.0
if apply_load:
    Cf_kN = st.number_input("Cf (kN)", 0.0, 1e7, 0.0, 25.0, key="cCf")

# ---- angle options ----
ai = AngleInput()
if sec.src_family in ("L", "2L"):
    section_heading("2b. Single-Angle Options (Cl. 13.3.3)")
    a1, a2, a3 = st.columns(3)
    with a1:
        note("All three conditions of Cl. 13.3.3.1 must hold.")
        ca = st.checkbox("Loaded at the ends through the same one leg", True,
                         key="ca")
        cb = st.checkbox("Welded, or at least a two-bolt connection", True,
                         key="cb")
        cc = st.checkbox("No intermediate transverse loads", True, key="cc")
    with a2:
        tr = st.selectbox("Member type", ["Individual member or planar truss",
                                          "Box or space truss"], key="ctr")
        ai.truss_type = "box" if tr.startswith("Box") else "individual"
        ai.connected_through_shorter_leg = st.checkbox(
            "Connected through the shorter leg", False, key="cshort")
    with a3:
        ai.rx_connected_mm = st.number_input(
            "rx parallel to the connected leg (mm)", 1.0, 500.0,
            float(sec.rx_mm), 0.1, key="carx")
        ai.ry_prime_mm = st.number_input(
            "r'y minor principal axis (mm)", 1.0, 500.0,
            float(sec.rz_mm or min(sec.rx_mm, sec.ry_mm)), 0.1, key="caryp")
        if sec.rz_mm is None:
            st.caption("rz is not in this table. The geometric minimum is "
                       "shown as a placeholder - confirm r'y from the CISC "
                       "tables.")
    if sec.leg_long_mm and sec.leg_short_mm:
        lr = sec.leg_long_mm / sec.leg_short_mm
        if lr >= 1.7:
            ai.ineligible_reasons.append(
                "Leg ratio bl/bs = " + num(lr, 2) + " is not less than 1.7.")
    for flag, txt in ((ca, "not loaded through the same one leg at both ends"),
                      (cb, "not welded or two-bolt connected"),
                      (cc, "carrying intermediate transverse loads")):
        if not flag:
            ai.ineligible_reasons.append("The member is " + txt + ".")
    ai.eligible = sec.src_family == "L" and not ai.ineligible_reasons

# ---- 3. Table 1 ----
section_heading("3. Local Buckling &mdash; Table 1 (Axial Compression)")
note("Clause 11.2 sends elements in axial compression to Table 1. Only the "
     "plate elements this section actually has are listed. Tick an element "
     "to run its check and see the work. Ticked elements are also the ones "
     "coloured on the 3D model.")
note("Common term: <i>&radic;F<sub>y</sub></i> = &radic;" + num(Fy, 0)
     + " = <b>" + num(math.sqrt(Fy), 3) + "</b>")

t1_checks = table1_elements(sec, Fy)
t1_selected: List[ElementCheck] = []
if not t1_checks:
    st.info("No Table 1 element could be built for this section, most likely "
            "because a dimension is missing from the table.")
else:
    for chk in t1_checks:
        on = st.checkbox(chk.label, value=False, key="sel_" + chk.key)
        if on:
            t1_selected.append(chk)
            render_t1(chk)
            st.markdown("---")

class4 = any(c.ok is False for c in t1_selected)

if t1_selected:
    if class4:
        st.error("Table 1 conclusion: at least one element exceeds its limit, "
                 "so the section is Class 4 for axial compression.")
    else:
        st.success("Table 1 conclusion: every selected element satisfies its "
                   "limit, so the section is not Class 4. The full gross "
                   "area is effective.")

# ---- 4. Table 2 ----
section_heading("4. Section Classification &mdash; Table 2 "
                "(Flexural Compression)")
note("Cl. 11.2 sends flexural compression to Table 2. This class carries "
     "into a beam or beam-column check; it does not govern the axial "
     "resistance below.")

t2_checks = table2_elements(sec, Fy, Cf_kN, phi_c)
t2_selected: List[ElementCheck] = []
if not t2_checks:
    st.info("No Table 2 element applies to this section.")
else:
    for chk in t2_checks:
        on = st.checkbox(chk.label, value=False, key="sel_" + chk.key)
        if on:
            t2_selected.append(chk)
            render_t2(chk)
            st.markdown("---")

if t2_selected:
    classes = [c.section_class for c in t2_selected if c.section_class]
    gov = max(classes)
    note("The governing class is the least compact among the selected "
         "elements: " + ", ".join("Class " + str(c) for c in classes)
         + " &rarr; <b>Class " + str(gov) + "</b>.")

# ---- run ----
inputs_ready = all(v > 0 for v in (Kx, Ky, Lx_m, Ly_m))
if not inputs_ready:
    st.divider()
    st.warning("Enter an end condition and an unbraced length for each axis "
               "to compute the resistance.")
    st.stop()

params = dict(Fy=Fy, E=E, G=G_MPa, phi=phi_c, n=n_input,
              Kx=Kx, Ky=Ky, Kz=Kz, Lx=Lx_m * 1000.0, Ly=Ly_m * 1000.0,
              Lz=Lz_m * 1000.0, x0=x0, y0=y0, Ae=Ae_override)

try:
    R = run_check(sec, params, ai, class4)
except Exception as exc:
    st.error("Calculation error: " + str(exc))
    st.stop()

if not R.KLr_gov or not R.Fe:
    st.warning("The slenderness or elastic buckling stress could not be "
               "computed from the inputs given.")
    st.stop()

# ---- 5. slenderness ----
section_heading("5. Slenderness Ratio")
if R.uses_angle:
    note("Cl. 13.3.3.1 is satisfied, so a modified slenderness replaces "
         "KL/r and eccentricity may be neglected.")
    for s in R.angle_steps:
        st.latex(s)
else:
    note("Cl. 13.3.1. The larger ratio governs; it gives the lower "
         "buckling stress.")
    st.latex(r"\left(\frac{KL}{r}\right)_x = \frac{K_x L_x}{r_x} = \frac{"
             + tex_num(Kx, 2) + r" \times " + tex_num(params["Lx"], 0)
             + r"}{" + tex_num(sec.rx_mm, 1) + r"} = " + tex_num(R.KLr_x, 2))
    st.latex(r"\left(\frac{KL}{r}\right)_y = \frac{K_y L_y}{r_y} = \frac{"
             + tex_num(Ky, 2) + r" \times " + tex_num(params["Ly"], 0)
             + r"}{" + tex_num(sec.ry_mm, 1) + r"} = " + tex_num(R.KLr_y, 2))
    st.latex(r"\frac{KL}{r} = \max\left(" + tex_num(R.KLr_x, 2) + r",\;"
             + tex_num(R.KLr_y, 2) + r"\right) = " + tex_num(R.KLr_gov, 2)
             + r"\quad(" + R.gov_axis + r"\ \text{governs})")

if R.KLr_over:
    st.error("KL/r = " + num(R.KLr_gov, 1) + " exceeds 200, the recommended "
             "maximum for compression members.")
else:
    st.success("KL/r = " + num(R.KLr_gov, 1) + " is within the recommended "
               "maximum of 200.")

# ---- 6. elastic buckling ----
section_heading("6. Elastic Buckling Stresses")
st.latex(r"F_e = \frac{\pi^2 E}{\left(\frac{KL}{r}\right)^2}")
if R.Fex:
    st.latex(r"F_{ex} = \frac{\pi^2 (" + tex_num(E, 0) + r")}{\left("
             + tex_num(R.KLr_x, 2) + r"\right)^2} = " + tex_num(R.Fex, 1)
             + r"\ \text{MPa}")
if R.Fey:
    st.latex(r"F_{ey} = \frac{\pi^2 (" + tex_num(E, 0) + r")}{\left("
             + tex_num(R.KLr_y, 2) + r"\right)^2} = " + tex_num(R.Fey, 1)
             + r"\ \text{MPa}")

sub_heading("Torsional buckling (Cl. 13.3.2)")
st.latex(r"F_{ez} = \left[\frac{\pi^2 E C_w}{(K_z L_z)^2} + GJ\right]"
         r"\frac{1}{A\,\bar{r}_o^{\,2}}")
if R.Fez is not None:
    ro_sq = sec.r_bar_o_sq(x0, y0)
    KzLz = Kz * params["Lz"]
    warp = (math.pi ** 2) * E * sec.Cw_mm6 / (KzLz ** 2)
    stv = G_MPa * sec.J_mm4
    st.latex(r"\bar{r}_o^{\,2} = x_0^2 + y_0^2 + r_x^2 + r_y^2 = "
             + tex_num(ro_sq, 1) + r"\ \text{mm}^2")
    st.latex(r"\frac{\pi^2 E C_w}{(K_z L_z)^2} = " + tex_num(warp, 0)
             + r"\ \text{N} \qquad GJ = " + tex_num(stv, 0) + r"\ \text{N}")
    st.latex(r"F_{ez} = \frac{" + tex_num(warp, 0) + r" + " + tex_num(stv, 0)
             + r"}{" + tex_num(sec.A_mm2, 0) + r" \times "
             + tex_num(ro_sq, 1) + r"} = " + tex_num(R.Fez, 1)
             + r"\ \text{MPa}")
else:
    st.info("Not evaluated. J and Cw are not carried in this table, or "
            "Kz times Lz is zero.")

if sec.symmetry == SYM_SINGLE:
    sub_heading("Flexural-torsional buckling (Cl. 13.3.2 b)")
    note("Singly symmetric, so weak-axis flexure and torsion couple.")
    st.latex(r"\Omega = 1 - \frac{x_0^2 + y_0^2}{\bar{r}_o^{\,2}}")
    st.latex(r"F_{eyz} = \frac{F_{ey} + F_{ez}}{2\Omega}\left[1 - "
             r"\sqrt{1 - \frac{4 F_{ey} F_{ez}\Omega}{(F_{ey} + F_{ez})^2}}"
             r"\right]")
    if R.Feyz is not None:
        st.latex(r"\Omega = " + tex_num(R.omega, 4)
                 + r"\qquad F_{eyz} = " + tex_num(R.Feyz, 1)
                 + r"\ \text{MPa}")
    else:
        st.warning("Feyz could not be computed because Fez is unavailable.")

sub_heading("Governing elastic buckling stress")
cands = []
for v, lbl in ((R.Fex, "F_{ex}"), (R.Fey, "F_{ey}"), (R.Fez, "F_{ez}"),
               (R.Feyz, "F_{eyz}")):
    if v is not None:
        cands.append(lbl + " = " + tex_num(v, 1))
st.latex(r"F_e = \min\left(" + r",\;".join(cands) + r"\right) = "
         + tex_num(R.Fe, 1) + r"\ \text{MPa}")
note("Governing mode: <b>" + R.mode + "</b> (" + R.clause + ")")

# ---- 7. column curve ----
section_heading("7. Column Curve")
st.latex(r"\lambda = \sqrt{\frac{F_y}{F_e}} = \sqrt{\frac{" + tex_num(Fy, 0)
         + r"}{" + tex_num(R.Fe, 1) + r"}} = " + tex_num(R.lam, 3))
inner = 1.0 + R.lam ** (2.0 * R.n)
st.latex(r"F_{cr} = \frac{F_y}{\left(1 + \lambda^{2n}\right)^{1/n}}"
         r" = \frac{" + tex_num(Fy, 0) + r"}{\left(1 + " + tex_num(R.lam, 3)
         + r"^{\,2(" + tex_num(R.n, 2) + r")}\right)^{1/" + tex_num(R.n, 2)
         + r"}} = \frac{" + tex_num(Fy, 0) + r"}{"
         + tex_num(inner ** (1.0 / R.n), 4) + r"} = " + tex_num(R.Fcr, 1)
         + r"\ \text{MPa}")
if R.n_forced:
    st.info(R.clause + " specifies n = 1.34, so the fabrication selection "
            "was overridden here.")

# ---- 8. resistance ----
section_heading("8. Factored Compressive Resistance")
st.latex(r"C_r = \phi\, A_e F_{cr} = " + tex_num(phi_c, 2) + r" \times "
         + tex_num(R.Ae_mm2, 0) + r" \times " + tex_num(R.Fcr, 1) + r" = "
         + tex_num(R.Cr_kN, 1) + r"\ \text{kN}")

sub_heading("Yield capacity check")
st.latex(r"C_{r,yield} = \phi\, A_e F_y = " + tex_num(phi_c, 2) + r" \times "
         + tex_num(R.Ae_mm2, 0) + r" \times " + tex_num(Fy, 0) + r" = "
         + tex_num(R.Cr_yield_kN, 1) + r"\ \text{kN}")
st.latex(r"\frac{C_r}{C_{r,yield}} = \frac{" + tex_num(R.Cr_kN, 1) + r"}{"
         + tex_num(R.Cr_yield_kN, 1) + r"} = "
         + tex_num(R.Cr_kN / R.Cr_yield_kN, 3))
if R.Cr_kN <= R.Cr_yield_kN + 1e-6:
    st.success("The column curve governs, as it must. Buckling has reduced "
               "the capacity to "
               + num(100.0 * R.Cr_kN / R.Cr_yield_kN, 1)
               + " percent of the squash load.")
else:
    st.error("The column curve exceeded the squash load. Check the inputs.")

for msg in R.warnings:
    st.warning(msg)

# ---- 9. results ----
st.divider()
section_heading("9. Results")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Cr (kN)", "{:,.0f}".format(R.Cr_kN))
m2.metric("Governing KL/r", "{:.1f}".format(R.KLr_gov))
m3.metric("Slenderness lambda", "{:.3f}".format(R.lam))
m4.metric("Fcr (MPa)", "{:.1f}".format(R.Fcr))
note("Governing mode: <b>" + R.mode + "</b> &nbsp;|&nbsp; " + R.clause
     + " &nbsp;|&nbsp; n = " + num(R.n, 2)
     + " &nbsp;|&nbsp; A<sub>e</sub> = " + num(R.Ae_mm2, 0)
     + " mm<sup>2</sup>")

section_heading("Demand versus capacity")
if not apply_load or Cf_kN <= 0:
    st.info("Enter a factored load Cf above to run the demand check.")
else:
    U = Cf_kN / R.Cr_kN
    pct = 100.0 * U
    st.latex(r"U = \frac{C_f}{C_r} = \frac{" + tex_num(Cf_kN, 1) + r"}{"
             + tex_num(R.Cr_kN, 1) + r"} = " + tex_num(U, 3) + r" = "
             + tex_num(pct, 1) + r"\%")
    st.progress(min(U, 1.0))
    r1, r2, r3 = st.columns(3)
    r1.metric("Utilisation", "{:.1f} %".format(pct))
    r2.metric("Capacity used", "{:,.0f} kN".format(Cf_kN))
    if U <= 1.0:
        r3.metric("Remaining", "{:,.0f} kN".format(R.Cr_kN - Cf_kN),
                  delta="{:.1f} % spare".format(100.0 - pct))
        st.success("PASS  -  U = " + num(U, 3) + " (" + num(pct, 1)
                   + " percent of capacity used, " + num(100.0 - pct, 1)
                   + " percent spare).")
    else:
        r3.metric("Shortfall", "{:,.0f} kN".format(Cf_kN - R.Cr_kN),
                  delta="{:.1f} % over".format(pct - 100.0),
                  delta_color="inverse")
        st.error("FAIL  -  U = " + num(U, 3) + " (" + num(pct, 1)
                 + " percent of capacity used, " + num(pct - 100.0, 1)
                 + " percent over). Increase the section or reduce the "
                 "unbraced length.")

# ---- 10. member model (bottom of page, so it reflects every input) ----
st.divider()
section_heading("10. Member Model")
note("The model is built from the inputs above: the section outline from "
     "its dimensions, the supports from the end conditions, the arrows "
     "from Cf, and the colour maps from the checks. Use the controls under "
     "the view to change what is shown.")

if not HAS_VIEWER:
    st.info("3D viewer not loaded. Place section_geometry.py, viewer_3d.py "
            "and viewer_3d.html in the repository root.")
elif sec.src_family not in VIEWER_OK:
    st.info("No outline builder for " + sec.family_label.lower()
            + ", so no model is shown rather than an incorrect one.")
else:
    _supports = {
        "x": {"K": float(Kx), "L": float(Lx_m * 1000.0),
              "bottom": x_bot, "top": x_top},
        "y": {"K": float(Ky), "L": float(Ly_m * 1000.0),
              "bottom": y_bot, "top": y_top},
        "z": {"K": float(Kz), "L": float(Lz_m * 1000.0),
              "bottom": z_bot, "top": z_top},
    }

    _util = (Cf_kN / R.Cr_kN) if (apply_load and Cf_kN > 0 and R.Cr_kN) else None
    _load = {"Cf_kN": float(Cf_kN), "util": _util} if (apply_load and Cf_kN > 0) else None

    # Only the elements the user ticked are mapped onto the model.
    _zone_for = {
        "t1_flange": "flange", "t1_web": "web", "t1_stem": "web",
        "t1_leg": "leg", "t1_chs": "wall",
        "t1_hss_flange": "flange", "t1_hss_web": "web",
        "t2_flange": "flange", "t2_web": "web", "t2_stem": "web",
        "t2_leg": "leg", "t2_chs": "wall",
        "t2_hss_flange": "flange", "t2_hss_web": "web",
    }
    _e1 = [{"key": c.key, "label": c.label.split(" - ")[0],
            "zone": _zone_for.get(c.key, "web"),
            "ok": bool(c.ok), "ratio": float(c.ratio or 0.0),
            "limit": float(c.limit or 0.0)}
           for c in t1_selected if c.ratio is not None]
    _e2 = [{"key": c.key, "label": c.label.split(" in ")[0],
            "zone": _zone_for.get(c.key, "web"),
            "cls": int(c.section_class or 0)}
           for c in t2_selected if c.section_class]

    _results = {
        "KLr": float(R.KLr_gov), "lam": float(R.lam),
        "Fcr": float(R.Fcr), "Fe": float(R.Fe),
        "Cr": float(R.Cr_kN), "util": _util,
        "gov_axis": R.gov_axis or "y-y",
        "mode": R.mode, "clause": R.clause,
    }

    _len = max(Lx_m, Ly_m, Lz_m) * 1000.0
    if _len <= 0:
        _len = 2000.0

    viewer_3d.render_member(
        sec, length_mm=_len, height=640,
        supports=_supports, load=_load,
        elements_t1=_e1, elements_t2=_e2, results=_results,
        show_diagnostics=False)

    if not _e1 and not _e2:
        st.caption("Tick a Table 1 or Table 2 element above to colour that "
                   "plate element on the model.")
