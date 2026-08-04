"""
pages/4_Beam_Column_Members.py

CSA S16 beam-column calculator. Self-contained: section loading, every
clause check and the page itself live in this file.

Section data is read the same way 2_Compression.py reads it, through
sst12.load_all_tables() with a direct r.get() on the keys sst12 already
publishes for the shared W and HSS sheets. sst12.py is not modified.

Covers Chapter 5 end to end:

  5.2     axial tension and bending        cl 13.9.1, 13.9.2 a) b)
  5.3.2.1 local buckling                   Table 1 axial, Table 2 flexure
                                           plus axial with the web limits
                                           reduced by Cf/phi.Cy
  5.3.2.2 cross-sectional strength         cl 13.8.2 a) / 13.8.3 a)
  5.3.2.3 overall member strength          cl 13.8.2 b) / 13.8.3 b)
  5.3.2.4 lateral torsional buckling       cl 13.8.2 c) / 13.8.3 c)
          moment amplification U1          cl 13.8.4
          equivalent moment factor omega1  cl 13.8.5 a) b) c)
          Mr laterally supported           cl 13.5
          Mr laterally unsupported         cl 13.6

Three points differ from the previous revision of this page, all
deliberate and all conservative.

1. The coefficients follow the clause, not the class alone. Cl. 13.8.2 is
   written for Class 1 and Class 2 sections OF I-SHAPED MEMBERS. Anything
   else, a Class 3 W or a Class 1 HSS alike, takes Cl. 13.8.3, where the
   0.85 on the x term and the 0.6 or beta on the y term all become 1.0.

2. Cr for check b) is taken on the axis of bending when the bending is
   uniaxial, per Cl. 13.8.2 b) i), not always on the governing axis.

3. U1 is forced to 1.0 in an unbraced frame, per Cl. 13.8.2 b) iii) and
   c) iv), and check a) is reported but not counted because it applies to
   braced frames only.

Section class is now computed from the geometry through Table 2 rather
than read from a "Class" column, so the web limits carry the axial
reduction that makes a beam-column classification differ from a beam one.

A Class 4 section returns Mr = None unless the Se option is ticked. It
never contributes a zero moment term to an interaction equation, because
that reads as a pass.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

import streamlit as st
from _theme import (apply_theme, render_sidebar_logo, render_footer,
                    gate_disclaimer)

import sys as _sys
from pathlib import Path
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sst12

try:
    import viewer_3d_beamcolumn
    HAS_VIEWER = True
except Exception:
    HAS_VIEWER = False

APP_TITLE = "Beam-Column Members"
DASH = "-"
PHI_DEFAULT = 0.9
E_DEFAULT = 200000.0
G_DEFAULT = 77000.0


# ============================================================
# FORMATTING
# ============================================================
def num(x: Any, nd: int = 2) -> str:
    if x is None:
        return DASH
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(v):
        return "inf"
    if abs(v) >= 100000:
        return "{:,.0f}".format(v)
    return "{:,.{}f}".format(v, nd)


def tx(x: Any, nd: int = 2) -> str:
    return num(x, nd).replace(",", r"\,")


def uc(v) -> str:
    return DASH if v is None else "{:.4f}".format(v)


def verdict(v) -> str:
    if v is None:
        return "INCOMPLETE"
    return "PASS" if v <= 1.0 else "FAIL"


def _f(x) -> Optional[float]:
    if x in (None, ""):
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _sd(a, b) -> Optional[float]:
    try:
        if b in (None, 0):
            return None
        return float(a) / float(b)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _nat_key(s):
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r"(\d+)", str(s))]


# ============================================================
# SECTION SOURCE
#
# Read exactly the way 2_Compression.py reads it. sst12 publishes short
# symbols on the shared W and HSS sheets, so this is a direct r.get() on
# each one. The only addition is the six keys Cl. 13.8 needs and
# Cl. 13.3 does not: Ix, Iy, Zx, Zy, Sx, Sy.
#
# Only the tables a beam-column check can complete are loaded. The
# channel, WT, single-angle and double-angle sheets come through the _mm
# normaliser without section moduli and without J or Cw, so Mr under
# Cl. 13.5 and Mu under Cl. 13.6 cannot be formed for them.
# ============================================================
FAMILIES = [
    ("W", "W shapes", "w", "I", True),
    ("HSS_SQUARE", "HSS square (SHS)", "hss_square", "RHS", False),
    ("HSS_RECT", "HSS rectangular (RHS)", "hss_rect", "RHS", False),
    ("HSS_ROUND", "HSS round (CHS)", "hss_round", "CHS", False),
]
FAMILY_ORDER = [f[0] for f in FAMILIES]
FAMILY_LABEL = dict((f[0], f[1]) for f in FAMILIES)
FAMILY_KIND = dict((f[0], f[3]) for f in FAMILIES)
FAMILY_LTB = dict((f[0], f[4]) for f in FAMILIES)

EXCLUDED_NOTE = (
    "Channels, WTs, single angles and double angles are not offered here. "
    "Those sheets come through sst12.py without section moduli and without "
    "J or Cw, so Mr under Cl. 13.5 and Mu under Cl. 13.6 cannot be formed "
    "and a Cl. 13.8 check cannot be completed. They remain available on "
    "the Compression page, which does not need those properties. S, M and "
    "HP shapes are not reachable through sst12.py at all."
)


def norm_shared(r: Dict[str, Any], fam: str) -> Dict[str, Any]:
    return {
        "designation": str(r.get("Designation", "")).strip(),
        "family": fam,
        "family_label": FAMILY_LABEL[fam],
        "kind": FAMILY_KIND[fam],
        "ltb_applies": FAMILY_LTB[fam],
        "d": _f(r.get("d")), "b": _f(r.get("b")),
        "t": _f(r.get("t")), "w": _f(r.get("w")),
        "A": _f(r.get("Area")),
        "rx": _f(r.get("rx")), "ry": _f(r.get("ry")),
        "bt": _f(r.get("ba/t")), "hw": _f(r.get("h/w")),
        "J": _f(r.get("J")), "Cw": _f(r.get("Cw")),
        "Ix": _f(r.get("Ix")), "Iy": _f(r.get("Iy")),
        "Zx": _f(r.get("Zx")), "Zy": _f(r.get("Zy")),
        "Sx": _f(r.get("Sx")), "Sy": _f(r.get("Sy")),
    }


def _finish(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in what the shape implies, then convert the table units. The
    Compression page does the same conversion in build_section."""
    fam = rec["family"]

    if fam == "HSS_ROUND":
        for a, b in (("Iy", "Ix"), ("Sy", "Sx"), ("Zy", "Zx"),
                     ("ry", "rx"), ("b", "d")):
            if rec.get(a) is None and rec.get(b) is not None:
                rec[a] = rec[b]

    if fam in ("HSS_SQUARE", "HSS_RECT", "HSS_ROUND") and rec.get("w") is None:
        rec["w"] = rec.get("t")

    if rec.get("d") is not None and rec.get("t") is not None:
        if fam == "W":
            rec["h"] = rec["d"] - 2.0 * rec["t"]
        elif fam in ("HSS_SQUARE", "HSS_RECT"):
            rec["h"] = rec["d"] - 4.0 * rec["t"]
        else:
            rec["h"] = None
    else:
        rec["h"] = None

    for k, mult in (("Ix", 1e6), ("Iy", 1e6), ("Zx", 1e3), ("Zy", 1e3),
                    ("Sx", 1e3), ("Sy", 1e3), ("J", 1e3), ("Cw", 1e9)):
        if rec.get(k) is not None:
            rec[k] = rec[k] * mult
    return rec


REQUIRED_ALL = ["A", "d", "b", "t", "rx", "ry", "Ix", "Iy", "Zx", "Sx"]
REQUIRED_I = ["w", "J", "Cw", "Zy", "Sy"]


def _missing(rec) -> List[str]:
    need = REQUIRED_ALL + (REQUIRED_I if rec["family"] == "W" else [])
    return [k for k in need if not rec.get(k)]


@st.cache_data(ttl=600)
def load_sections():
    t = sst12.load_all_tables()
    data: Dict[str, List[Dict[str, Any]]] = {}
    report = {"loaded": {}, "rejected": [], "tables_read": [],
              "tables_skipped": []}

    wanted = dict((f[2], f[0]) for f in FAMILIES)
    for tname in t.keys():
        (report["tables_read"] if tname in wanted
         else report["tables_skipped"]).append(tname)

    for fam, _label, tkey, _kind, _ltb in FAMILIES:
        keep = []
        for r in t.get(tkey, []):
            rec = _finish(norm_shared(r, fam))
            if not rec["designation"]:
                continue
            miss = _missing(rec)
            if miss:
                report["rejected"].append((fam, rec["designation"], miss))
                continue
            keep.append(rec)
        keep.sort(key=lambda r: _nat_key(r["designation"]))
        if keep:
            data[fam] = keep
            report["loaded"][fam] = len(keep)
    return data, report


# ============================================================
# PROPERTY DISPLAY - calculation inputs only
#
# The workbook publishes roughly thirty columns per section. Sixteen are
# listed, each used by a clause below, each saying which.
# ============================================================
_DISPLAY = [
    ("Geometry", [
        ("d", "d", "mm", "Web width for Table 1 and Table 2, h = d - 2t. "
                         "D/t for a round HSS."),
        ("b", "b", "mm", "Flange ratio. Cl. 11.3.1 c) takes b/2 for an "
                         "I-shape flange."),
        ("t", "t", "mm", "Flange or wall thickness."),
        ("w", "w", "mm", "Web thickness. Denominator of h/w."),
        ("h", "h", "mm", "Clear web depth. Cl. 11.3.2 d) rolled, "
                         "d - 4t hollow."),
    ]),
    ("Section properties", [
        ("A", "A", "mm2", "Cr = phi A Fcr, Tr = phi A Fy, and Cy = A Fy in "
                          "the Table 2 web reduction."),
        ("rx", "rx", "mm", "(KL/r)x, sets Cr for strong-axis bending."),
        ("ry", "ry", "mm", "(KL/r)y, sets Cr for check c) and lambda_y."),
        ("Ix", "Ix", "mm4", "Ce,x = pi^2 E Ix / Lx^2 for U1x, Cl. 13.8.4."),
        ("Iy", "Iy", "mm4", "Ce,y for U1y, and Mu under Cl. 13.6."),
    ]),
    ("Moduli for Mr, Cl. 13.5", [
        ("Zx", "Zx", "mm3", "Mrx = phi Zx Fy, Class 1 or 2."),
        ("Zy", "Zy", "mm3", "Mry, Class 1 or 2."),
        ("Sx", "Sx", "mm3", "Mrx, Class 3, and the S term in Cl. 13.9.2 b)."),
        ("Sy", "Sy", "mm3", "Mry, Class 3."),
    ]),
    ("Torsional, for Mu Cl. 13.6", [
        ("J", "J", "mm4", "St Venant torsion constant in Mu."),
        ("Cw", "Cw", "mm6", "Warping constant in Mu."),
    ]),
]


def display_rows(rec) -> List[Dict[str, Any]]:
    out = []
    for group, spec in _DISPLAY:
        for key, symbol, unit, why in spec:
            v = rec.get(key)
            if v is None:
                continue
            out.append({"group": group, "symbol": symbol, "value": v,
                        "unit": unit, "why": why})
    return out


# ============================================================
# CLASS 4 EFFECTIVE SECTION MODULUS
# ============================================================
def effective_flange_width(b, t, Fy):
    lam = (b / 2.0) / t
    lam_r = 200.0 / math.sqrt(Fy)
    return b if lam <= lam_r else min(b * (lam_r / lam), b)


def effective_web_height(h, w, Fy):
    lam = h / w
    lam_r = 1700.0 / math.sqrt(Fy)
    return h if lam <= lam_r else min(h * (lam_r / lam), h)


def compute_Se(d, b, t, w, Fy):
    h = d - 2.0 * t
    b_eff = effective_flange_width(b, t, Fy)
    h_eff = effective_web_height(h, w, Fy)
    Af = b_eff * t
    y = (h_eff / 2.0) + (t / 2.0)
    If = 2.0 * ((b_eff * t ** 3) / 12.0 + Af * y ** 2)
    Iw = (w * h_eff ** 3) / 12.0
    Ix_eff = If + Iw
    return {"h": h, "b_eff": b_eff, "h_eff": h_eff, "Ix_eff": Ix_eff,
            "Se": Ix_eff / (d / 2.0)}


# ============================================================
# TABLE 1 - local buckling under axial compression
# ============================================================
def table1_elements(rec, Fy):
    s = math.sqrt(Fy)
    kind = rec["kind"]
    out = []

    if kind == "I":
        b_el = rec["b"] / 2.0
        out.append({
            "key": "t1_flange", "zone": "flange",
            "label": "Flange, supported along one edge",
            "why": ("The flange is joined to the web along one edge and is "
                    "free at the other. That is the least stiff plate "
                    "boundary, so it carries the most severe limit."),
            "clause": "Table 1, width per Cl. 11.3.1 c)",
            "width": r"b_{el} = \frac{b}{2} = \frac{" + tx(rec["b"], 1)
                     + r"}{2} = " + tx(b_el, 1) + r"\ \mathrm{mm}",
            "ratio_tex": r"\frac{b_{el}}{t} = \frac{" + tx(b_el, 1) + r"}{"
                         + tx(rec["t"], 1) + r"} = " + tx(b_el / rec["t"], 2),
            "limit_tex": r"\frac{200}{\sqrt{F_y}} = \frac{200}{" + tx(s, 3)
                         + r"} = " + tx(200.0 / s, 2),
            "ratio": b_el / rec["t"], "limit": 200.0 / s})
        if rec.get("h") and rec.get("w"):
            out.append({
                "key": "t1_web", "zone": "web",
                "label": "Web, supported along two edges",
                "why": ("The web is held by a flange top and bottom. Two "
                        "supported edges is a far stiffer boundary, so the "
                        "limit rises from 200 to 670."),
                "clause": "Table 1, width per Cl. 11.3.2 d)",
                "width": r"h = d - 2t = " + tx(rec["d"], 1) + r" - 2("
                         + tx(rec["t"], 1) + r") = " + tx(rec["h"], 1)
                         + r"\ \mathrm{mm}",
                "ratio_tex": r"\frac{h}{w} = \frac{" + tx(rec["h"], 1)
                             + r"}{" + tx(rec["w"], 1) + r"} = "
                             + tx(rec["h"] / rec["w"], 2),
                "limit_tex": r"\frac{670}{\sqrt{F_y}} = " + tx(670.0 / s, 2),
                "ratio": rec["h"] / rec["w"], "limit": 670.0 / s})

    elif kind == "RHS":
        for key, dim, zone, lbl in (("t1_hss_flange", rec["b"], "flange",
                                     "Flange wall"),
                                    ("t1_hss_web", rec["d"], "web",
                                     "Web wall")):
            b_el = dim - 4.0 * rec["t"]
            out.append({
                "key": key, "zone": zone,
                "label": lbl + ", supported along two edges",
                "why": ("Every wall of a closed tube runs into the two "
                        "walls beside it, so each is supported on two "
                        "edges. The width takes off four wall thicknesses "
                        "to remove the corner radii."),
                "clause": "Table 1, width per Cl. 11.3.2 b)",
                "width": r"b_{el} = " + tx(dim, 1) + r" - 4("
                         + tx(rec["t"], 1) + r") = " + tx(b_el, 1)
                         + r"\ \mathrm{mm}",
                "ratio_tex": r"\frac{b_{el}}{t} = " + tx(b_el / rec["t"], 2),
                "limit_tex": r"\frac{670}{\sqrt{F_y}} = " + tx(670.0 / s, 2),
                "ratio": b_el / rec["t"], "limit": 670.0 / s})

    elif kind == "CHS":
        out.append({
            "key": "t1_chs", "zone": "wall",
            "label": "Circular tube wall",
            "why": ("A circular wall has no free edge anywhere. Its limit "
                    "is written on D/t and divided by Fy, not by the root "
                    "of Fy."),
            "clause": "Table 1",
            "width": r"D = " + tx(rec["d"], 1) + r"\ \mathrm{mm}",
            "ratio_tex": r"\frac{D}{t} = " + tx(rec["d"] / rec["t"], 2),
            "limit_tex": r"\frac{23\,000}{F_y} = " + tx(23000.0 / Fy, 2),
            "ratio": rec["d"] / rec["t"], "limit": 23000.0 / Fy})
    return out


# ============================================================
# TABLE 2 - classification for a beam-column
#
# The flange limits are the beam limits, because the flange is in
# uniform compression either way. The web limits carry the axial
# reduction, which is what makes this a beam-column classification.
# ============================================================
def table2_flange_limits(Fy):
    s = math.sqrt(Fy)
    return [145.0 / s, 170.0 / s, 200.0 / s]


def table2_web_limits(Fy, Cf_kN, A_mm2, phi):
    s = math.sqrt(Fy)
    Cy = A_mm2 * Fy / 1000.0
    ratio = _sd(Cf_kN, phi * Cy) or 0.0
    return ([(1100.0 / s) * (1.0 - 0.39 * ratio),
             (1700.0 / s) * (1.0 - 0.61 * ratio),
             (1900.0 / s) * (1.0 - 0.65 * ratio)], Cy, ratio)


def _class_from(ratio, limits):
    for i, lv in enumerate(limits, start=1):
        if ratio <= lv:
            return i
    return 4


def classify_table2(sec, Fy, Cf_kN, phi=PHI_DEFAULT):
    d, b, t, w, A = (sec.get("d"), sec.get("b"), sec.get("t"),
                     sec.get("w"), sec.get("A"))
    out = {"ok": False}
    if None in (b, t) or not t:
        return out

    lam_f = (b / 2.0) / t
    fl = table2_flange_limits(Fy)
    cf_cls = _class_from(lam_f, fl)

    wl, Cy, ratio = table2_web_limits(Fy, Cf_kN, A, phi)
    h = None
    cw_cls = None
    if None not in (d, t, w) and w:
        h = sec.get("h")
        if h is None:
            h = d - 2.0 * t
        cw_cls = _class_from(h / w, wl)

    classes = [c for c in (cf_cls, cw_cls) if c]
    out.update({
        "ok": True, "lam_f": lam_f, "flange_limits": fl,
        "flange_class": cf_cls, "h": h, "lam_w": _sd(h, w),
        "web_limits": wl, "web_class": cw_cls,
        "Cy_kN": Cy, "Cf_over_phiCy": ratio,
        "section_class": max(classes) if classes else None,
    })
    return out


# ============================================================
# CLAUSE 13.5 - Mr laterally supported
# ============================================================
def Mr_13_5(sec, Fy, section_class, axis="x", phi=PHI_DEFAULT,
            class4_use_Se=False):
    Z = sec.get("Zx") if axis == "x" else sec.get("Zy")
    S = sec.get("Sx") if axis == "x" else sec.get("Sy")

    if section_class in (1, 2):
        if not Z:
            return {"Mr_kNm": None, "note": "Z" + axis + " missing."}
        return {"Mr_kNm": phi * Fy * Z / 1e6, "modulus": "Z_{" + axis + "}",
                "modulus_value": Z, "clause": "Cl. 13.5 a)"}
    if section_class == 3:
        if not S:
            return {"Mr_kNm": None, "note": "S" + axis + " missing."}
        return {"Mr_kNm": phi * Fy * S / 1e6, "modulus": "S_{" + axis + "}",
                "modulus_value": S, "clause": "Cl. 13.5 b)"}

    if not class4_use_Se:
        return {"Mr_kNm": None, "class4": True,
                "note": ("Class 4 section. Cl. 13.5 c) needs an effective "
                         "section modulus. Tick the Se option to compute "
                         "it, otherwise the moment term cannot be formed.")}
    if axis != "x":
        return {"Mr_kNm": None, "class4": True,
                "note": ("Se is built for major-axis bending only, so a "
                         "Class 4 section with Mfy stays incomplete.")}
    d, b, t, w = sec.get("d"), sec.get("b"), sec.get("t"), sec.get("w")
    if None in (d, b, t, w):
        return {"Mr_kNm": None, "class4": True,
                "note": "d, b, t and w are needed to build Se."}
    se = compute_Se(d, b, t, w, Fy)
    return {"Mr_kNm": phi * Fy * se["Se"] / 1e6, "modulus": "S_e",
            "modulus_value": se["Se"], "se_detail": se,
            "clause": "Cl. 13.5 c)", "class4": True}


# ============================================================
# CLAUSE 13.6 - Mr laterally unsupported
# ============================================================
def Mu_13_6(omega2, L_mm, E, Iy, G, J, Cw):
    if not L_mm or L_mm <= 0:
        return None
    t1 = E * Iy * G * J
    t2 = ((math.pi * E / L_mm) ** 2) * Iy * Cw
    return (omega2 * math.pi / L_mm) * math.sqrt(max(t1 + t2, 0.0)) / 1e6


def Mr_13_6(sec, Fy, section_class, omega2, L_mm, E=E_DEFAULT, G=G_DEFAULT,
            phi=PHI_DEFAULT, class4_use_Se=False):
    Iy, J, Cw = sec.get("Iy"), sec.get("J"), sec.get("Cw")
    if None in (Iy, J, Cw):
        return {"Mr_kNm": None,
                "note": "Iy, J or Cw missing, so Cl. 13.6 cannot be run."}

    if section_class in (1, 2):
        mod, name = sec.get("Zx"), "Z_x"
    elif section_class == 3:
        mod, name = sec.get("Sx"), "S_x"
    else:
        if not class4_use_Se:
            return {"Mr_kNm": None, "class4": True,
                    "note": "Class 4. Tick the Se option to run Cl. 13.6."}
        d, b, t, w = sec.get("d"), sec.get("b"), sec.get("t"), sec.get("w")
        if None in (d, b, t, w):
            return {"Mr_kNm": None, "class4": True,
                    "note": "d, b, t and w are needed to build Se."}
        mod, name = compute_Se(d, b, t, w, Fy)["Se"], "S_e"
    if not mod:
        return {"Mr_kNm": None, "note": name + " missing."}

    Mp = Fy * mod / 1e6
    Mu = Mu_13_6(omega2, L_mm, E, Iy, G, J, Cw)
    if Mu is None:
        return {"Mr_kNm": None, "note": "Mu could not be formed."}

    phiMp = phi * Mp
    if Mu > 0.67 * Mp:
        Mr = min(1.15 * phiMp * (1.0 - 0.28 * Mp / Mu), phiMp)
        branch = "Mu > 0.67 Mp, inelastic"
        formula = (r"M_r = 1.15\,\phi M_p\left(1 - \frac{0.28 M_p}{M_u}"
                   r"\right) \leq \phi M_p")
    else:
        Mr = phi * Mu
        branch = "Mu <= 0.67 Mp, elastic"
        formula = r"M_r = \phi M_u"

    return {"Mr_kNm": Mr, "Mu_kNm": Mu, "Mp_kNm": Mp, "phiMp_kNm": phiMp,
            "threshold_kNm": 0.67 * Mp, "modulus": name,
            "modulus_value": mod, "branch": branch, "formula": formula,
            "omega2": omega2, "L_mm": L_mm, "clause": "Cl. 13.6"}


# ============================================================
# CLAUSE 13.3 - Cr
# ============================================================
def Cr_13_3(A, Fy, KLr, E=E_DEFAULT, phi=PHI_DEFAULT, n=1.34):
    if KLr is None or KLr <= 0:
        return {"Cr_kN": phi * A * Fy / 1000.0, "lam": 0.0, "Fe": None,
                "Fcr": Fy, "KLr": 0.0}
    Fe = (math.pi ** 2) * E / (KLr ** 2)
    lam = KLr * math.sqrt(Fy / ((math.pi ** 2) * E))
    Fcr = Fy / ((1.0 + lam ** (2.0 * n)) ** (1.0 / n))
    return {"Cr_kN": phi * A * Fcr / 1000.0, "lam": lam, "Fe": Fe,
            "Fcr": Fcr, "KLr": KLr}


# ============================================================
# CLAUSE 13.8.4 and 13.8.5 - Ce, U1, omega1
# ============================================================
def Ce_euler(E, I_mm4, L_mm):
    if not L_mm or L_mm <= 0 or not I_mm4:
        return None
    return (math.pi ** 2) * E * I_mm4 / (L_mm ** 2) / 1000.0


OMEGA1_CASES = [
    ("kappa", "No transverse loads between supports (kappa based)"),
    ("distributed", "Distributed load or a series of point loads"),
    ("concentrated", "A concentrated load or moment between supports"),
]


def omega1_from(case, kappa=1.0):
    if case == "distributed":
        return 1.0
    if case == "concentrated":
        return 0.85
    return max(0.4, 0.6 - 0.4 * float(kappa))


def U1_13_8_4(omega1, Cf_kN, Ce_kN, braced=True):
    if not braced:
        return {"U1": 1.0, "U1_raw": 1.0, "forced": True,
                "why": ("Unbraced frame. Cl. 13.8.2 b) iii) and c) iv) set "
                        "U1 to 1.0, because the peak moment sits at the "
                        "member ends where P-delta is negligible. Sway is "
                        "carried by the P-Delta analysis instead.")}
    if not Ce_kN or Ce_kN <= 0:
        return {"U1": 1.0, "U1_raw": None, "forced": False,
                "why": "Ce unavailable."}
    denom = 1.0 - float(Cf_kN) / float(Ce_kN)
    if denom <= 0:
        return {"U1": float("inf"), "U1_raw": float("inf"), "forced": False,
                "why": "Cf has reached Ce. The member is unstable."}
    raw = omega1 / denom
    return {"U1": max(1.0, raw), "U1_raw": raw, "forced": False,
            "why": "Cl. 13.8.4, not less than 1.0."}


# ============================================================
# CLAUSE 13.8 - the three checks
# ============================================================
def is_i_shaped(sec):
    return str(sec.get("family", "")).upper() in ("W", "WWF", "I", "S",
                                                  "M", "HP")


def coefficients(sec, section_class):
    """Cl. 13.8.2 is written for Class 1 and Class 2 sections OF I-SHAPED
    members. Everything else takes Cl. 13.8.3, where every coefficient
    is 1.0."""
    if is_i_shaped(sec) and section_class in (1, 2):
        return {"clause": "Cl. 13.8.2", "cx": 0.85, "cy_a": 0.60,
                "cy_b": None,
                "note": "Class %s I-shaped member." % section_class}
    why = ("Class %s section" % section_class if section_class not in (1, 2)
           else "Not an I-shaped member")
    return {"clause": "Cl. 13.8.3", "cx": 1.0, "cy_a": 1.0, "cy_b": 1.0,
            "note": ("%s, so Cl. 13.8.3 applies and the 0.85 and beta "
                     "reductions are not available." % why)}


def beta_factor(lam_y):
    return min(0.85, 0.6 + 0.4 * lam_y)


def check_13_8(sec, p):
    Fy, E, G, phi = p["Fy"], p["E"], p["G"], p["phi"]
    A = sec["A"]
    Cf, Mfx, Mfy = p["Cf"], p["Mfx"], p["Mfy"]
    braced, Lx, Ly = p["braced"], p["Lx"], p["Ly"]

    cls = classify_table2(sec, Fy, Cf, phi)
    section_class = cls.get("section_class")
    C = coefficients(sec, section_class)

    mrx = Mr_13_5(sec, Fy, section_class, "x", phi, p["class4_use_Se"])
    mry = Mr_13_5(sec, Fy, section_class, "y", phi, p["class4_use_Se"])
    Mrx, Mry = mrx.get("Mr_kNm"), mry.get("Mr_kNm")

    Ce_x = Ce_euler(E, sec.get("Ix"), Lx)
    Ce_y = Ce_euler(E, sec.get("Iy"), Ly)
    u1x = U1_13_8_4(p["omega1x"], Cf, Ce_x, braced)
    u1y = U1_13_8_4(p["omega1y"], Cf, Ce_y, braced)
    U1x, U1y = u1x["U1"], u1y["U1"]

    KLr_x1 = _sd(Lx, sec["rx"])
    KLr_y1 = _sd(Ly, sec["ry"])
    lam_y1 = (KLr_y1 or 0.0) * math.sqrt(Fy / ((math.pi ** 2) * E))
    beta = beta_factor(lam_y1)
    cy_b = C["cy_b"] if C["cy_b"] is not None else beta

    uniaxial_x = (Mfy or 0.0) <= 1e-9 and (Mfx or 0.0) > 0
    uniaxial_y = (Mfx or 0.0) <= 1e-9 and (Mfy or 0.0) > 0

    def term(coef, U1, Mf, Mr):
        # No applied moment about this axis contributes nothing, whether
        # or not Mr could be formed. Only a real moment with no
        # resistance to divide by stays None, so the check reads
        # INCOMPLETE rather than passing on a missing term.
        if not Mf:
            return 0.0
        if Mr is None or Mr <= 0:
            return None
        return coef * U1 * Mf / Mr

    def total(parts):
        return None if any(x is None for x in parts) else sum(parts)

    # a) cross-sectional strength, lambda = 0
    Cr_a = phi * A * Fy / 1000.0
    a_terms = [_sd(Cf, Cr_a), term(C["cx"], U1x, Mfx, Mrx),
               term(C["cy_a"], U1y, Mfy, Mry)]
    check_a = {"applies": braced, "Cr_kN": Cr_a, "coef_x": C["cx"],
               "coef_y": C["cy_a"], "terms": a_terms,
               "total": total(a_terms), "clause": C["clause"] + " a)"}

    # b) overall member strength, K = 1
    if uniaxial_x:
        KLr_b, axis_b = KLr_x1, "x-x, the axis of bending"
    elif uniaxial_y:
        KLr_b, axis_b = KLr_y1, "y-y, the axis of bending"
    else:
        vals = [v for v in (KLr_x1, KLr_y1) if v]
        KLr_b = max(vals) if vals else None
        axis_b = "x-x, governing" if KLr_b == KLr_x1 else "y-y, governing"
    cr_b = Cr_13_3(A, Fy, KLr_b, E, phi, p["n"])
    b_terms = [_sd(Cf, cr_b["Cr_kN"]), term(C["cx"], U1x, Mfx, Mrx),
               term(cy_b, U1y, Mfy, Mry)]
    check_b = {"applies": True, "Cr_kN": cr_b["Cr_kN"], "KLr": KLr_b,
               "lam": cr_b["lam"], "Fe": cr_b["Fe"], "Fcr": cr_b["Fcr"],
               "axis": axis_b, "coef_x": C["cx"], "coef_y": cy_b,
               "beta": beta, "lam_y": lam_y1, "terms": b_terms,
               "total": total(b_terms), "clause": C["clause"] + " b)"}

    # c) lateral torsional buckling
    ltb_applies = (Mfx or 0.0) > 0 and is_i_shaped(sec)
    cr_c = Cr_13_3(A, Fy, KLr_y1, E, phi, p["n"])
    mrx_136 = Mr_13_6(sec, Fy, section_class, p["omega2"], Ly, E, G, phi,
                      p["class4_use_Se"])
    Mrx_c = mrx_136.get("Mr_kNm")
    c_terms = [_sd(Cf, cr_c["Cr_kN"]), term(C["cx"], U1x, Mfx, Mrx_c),
               term(cy_b, U1y, Mfy, Mry)]
    check_c = {"applies": ltb_applies, "Cr_kN": cr_c["Cr_kN"],
               "KLr": KLr_y1, "lam": cr_c["lam"], "Fcr": cr_c["Fcr"],
               "coef_x": C["cx"], "coef_y": cy_b, "Mrx_kNm": Mrx_c,
               "ltb": mrx_136, "terms": c_terms, "total": total(c_terms),
               "clause": C["clause"] + " c)",
               "note": ("" if ltb_applies else
                        "Lateral torsional buckling is not a failure mode "
                        "for a closed section, and weak-axis bending alone "
                        "does not start it in an I-shape.")}

    mo = [0.0 if not Mfx else _sd(Mfx, Mrx),
          0.0 if not Mfy else _sd(Mfy, Mry)]
    check_m = {"terms": mo, "total": total(mo)}

    rows = [("a) Cross-sectional strength", check_a["total"], braced),
            ("b) Overall member strength", check_b["total"], True),
            ("c) Lateral torsional buckling", check_c["total"], ltb_applies),
            ("Moment only, Mfx/Mrx + Mfy/Mry", check_m["total"], True)]
    live = [(n, v) for n, v, ap in rows if ap and v is not None]
    gov = max(live, key=lambda z: z[1]) if live else (None, None)
    incomplete = any(v is None for _n, v, ap in rows if ap)

    return {"class_info": cls, "section_class": section_class,
            "coefficients": C, "beta": beta, "lam_y": lam_y1,
            "Mrx": mrx, "Mry": mry, "Mrx_kNm": Mrx, "Mry_kNm": Mry,
            "Ce_x_kN": Ce_x, "Ce_y_kN": Ce_y, "u1x": u1x, "u1y": u1y,
            "U1x": U1x, "U1y": U1y, "check_a": check_a,
            "check_b": check_b, "check_c": check_c, "check_moment": check_m,
            "rows": rows, "governing_name": gov[0], "governing_uc": gov[1],
            "incomplete": incomplete,
            "overall": ("INCOMPLETE" if incomplete else
                        ("OK" if gov[1] is not None and gov[1] <= 1.0
                         else "NG"))}


# ============================================================
# CLAUSE 13.9 - axial tension and bending
# ============================================================
def check_13_9(sec, p):
    Fy, phi = p["Fy"], p["phi"]
    A, Tf, Mfx, Mfy = sec["A"], p["Tf"], p["Mfx"], p["Mfy"]

    cls = classify_table2(sec, Fy, 0.0, phi)
    section_class = cls.get("section_class")

    Tr = phi * A * Fy / 1000.0
    mrx = Mr_13_5(sec, Fy, section_class, "x", phi, p["class4_use_Se"])
    mry = Mr_13_5(sec, Fy, section_class, "y", phi, p["class4_use_Se"])
    Mrx, Mry = mrx.get("Mr_kNm"), mry.get("Mr_kNm")

    t1 = _sd(Tf, Tr)
    t2 = 0.0 if not Mfx else _sd(Mfx, Mrx)
    t3 = 0.0 if not Mfy else _sd(Mfy, Mry)
    parts = [t1, t2, t3]
    total_1 = None if any(x is None for x in parts) else sum(parts)

    out = {"class_info": cls, "section_class": section_class, "Tr_kN": Tr,
           "Mrx": mrx, "Mry": mry, "terms_13_9_1": parts,
           "total_13_9_1": total_1}

    m136 = Mr_13_6(sec, Fy, section_class, p["omega2"], p["Lu"], p["E"],
                   p["G"], phi, p["class4_use_Se"])
    Mr_u = m136.get("Mr_kNm")
    if section_class in (1, 2):
        mod, mod_name, sub = sec.get("Zx"), "Z", "a) Class 1 and 2"
    else:
        mod, mod_name, sub = sec.get("Sx"), "S", "b) Class 3 and 4"
    val = None
    if Mr_u and mod and A:
        val = Mfx / Mr_u - (Tf * mod) / (Mr_u * 1e3 * A)
    out.update({"ltb": m136, "Mr_unsup_kNm": Mr_u, "modulus_13_9_2": mod,
                "modulus_name": mod_name, "sub_13_9_2": sub,
                "total_13_9_2": val})
    return out


# ============================================================
# STREAMLIT UI
# ============================================================
apply_theme()
render_sidebar_logo()
render_footer()
gate_disclaimer()

# Lock page here ***************
# from _theme import beta_lock_page
# beta_lock_page("Beam-Column Members")

st.title(APP_TITLE)
st.caption("CSA S16 Cl. 13.8 and 13.9  |  loads in kN and kN-m, "
           "geometry in mm")

try:
    DATA, REPORT = load_sections()
except Exception as exc:
    st.error("Could not read the SST12.1 workbook: " + str(exc))
    st.stop()

if not DATA:
    st.error("No section data found. Add the CISC SST12.1 workbook to "
             "attached_assets/.")
    st.stop()

col_calc, col_model = st.columns([1.15, 1], gap="large")

with col_calc:

    # ---- 1. Section ----
    st.subheader("1. Section")
    fam_opts = [(c, FAMILY_LABEL[c]) for c in FAMILY_ORDER if c in DATA]
    fam_codes = [c for c, _l in fam_opts]
    fam_lbl = dict(fam_opts)

    s1, s2 = st.columns([1, 1.4])
    with s1:
        fam = st.selectbox("Family", fam_codes,
                           format_func=lambda c: fam_lbl[c], key="bc_fam")
    rows_f = DATA.get(fam, [])
    with s2:
        search = st.text_input("Search", placeholder="e.g. W310",
                               key="bc_search")
        opts = [r["designation"] for r in rows_f]
        if search:
            q = search.strip().lower()
            opts = [d for d in opts if q in d.lower()]
        if not opts:
            st.warning("No sections match.")
            st.stop()
        des = st.selectbox("Designation", opts, key="bc_des_" + fam)

    rec = next((r for r in rows_f if r["designation"] == des), None)
    if rec is None:
        st.error("Could not load " + str(des))
        st.stop()

    with st.expander("Which tables are read", expanded=False):
        st.write(EXCLUDED_NOTE)
        st.caption("Read: " + ", ".join(REPORT["tables_read"])
                   + ".  Skipped: " + ", ".join(REPORT["tables_skipped"])
                   + ".")
        if REPORT["rejected"]:
            st.caption("%d rows dropped for missing properties a Cl. 13.8 "
                       "check needs." % len(REPORT["rejected"]))

    with st.expander("Section properties  -  " + des, expanded=False):
        st.caption("Only the values the checks below consume. Each row "
                   "says where it is used.")
        cur = None
        html = ["<table style='border-collapse:collapse;width:100%'>"]
        for r in display_rows(rec):
            if r["group"] != cur:
                cur = r["group"]
                html.append("<tr><td colspan='3' style='padding:10px 0 3px "
                            "0;font-weight:600'>" + cur + "</td></tr>")
            u = (" " + r["unit"]) if r["unit"] else ""
            u = (u.replace("mm2", "mm<sup>2</sup>")
                 .replace("mm3", "mm<sup>3</sup>")
                 .replace("mm4", "mm<sup>4</sup>")
                 .replace("mm6", "mm<sup>6</sup>"))
            html.append("<tr><td style='padding:3px 16px 3px 14px;"
                        "white-space:nowrap'>" + r["symbol"] + "</td>"
                        "<td style='padding:3px 16px 3px 0;white-space:"
                        "nowrap'>" + num(r["value"], 2) + u + "</td>"
                        "<td style='padding:3px 0;color:#8b949e;font-size:"
                        "0.88em'>" + r["why"] + "</td></tr>")
        html.append("</table>")
        st.markdown("".join(html), unsafe_allow_html=True)
        st.caption("Source: CISC SST12.1, read at run time through "
                   "sst12.py. Only calculation inputs are shown.")

    # ---- 2. Material and frame ----
    st.subheader("2. Material and Frame")
    m1, m2, m3 = st.columns(3)
    with m1:
        Fy = st.number_input("Fy (MPa)", 200.0, 700.0, 350.0, 5.0,
                             key="bc_fy")
        E = st.number_input("E (MPa)", 150000.0, 250000.0, 200000.0,
                            1000.0, key="bc_e")
    with m2:
        G = st.number_input("G (MPa)", 50000.0, 100000.0, 77000.0, 1000.0,
                            key="bc_g")
        phi = st.number_input("phi", 0.50, 1.00, 0.90, 0.05, key="bc_phi")
    with m3:
        fab = st.radio("Fabrication, sets n",
                       ["Hot-rolled, HSS Class C",
                        "Welded three-plate, HSS Class H"],
                       index=0, key="bc_fab")
        n_col = 2.24 if fab.startswith("Welded") else 1.34
        st.caption("n = " + str(n_col))

    frame = st.radio("Frame type (Cl. 13.8.1)",
                     ["Braced frame", "Unbraced frame"], index=0,
                     horizontal=True, key="bc_frame",
                     help="A frame with bracing counts as braced if its "
                          "sway stiffness is at least five times that of "
                          "the frame without it.")
    braced = frame.startswith("Braced")
    if not braced:
        st.info("Unbraced frame. Cl. 13.8.2 b) iii) and c) iv) set U1 to "
                "1.0, because the peak moment sits at the member ends "
                "where P-delta is negligible. Cl. 13.8.2 a) applies to "
                "braced frames only, so it is reported but not counted.")

    # ---- 3. Axial condition ----
    st.subheader("3. Axial Condition")
    axial = st.radio("Condition", ["Axial compression and bending",
                                   "Axial tension and bending"],
                     index=0, key="bc_axial")
    is_comp = axial.startswith("Axial compression")

    # ---- 4. Lengths and loads ----
    st.subheader("4. Lengths and Loads")
    K_TABLE = {
        "Pinned - Pinned": (1.00, "Pinned", "Pinned"),
        "Fixed - Fixed": (0.65, "Fixed", "Fixed"),
        "Fixed - Pinned": (0.80, "Fixed", "Pinned"),
        "Fixed - Guided (sway)": (1.20, "Fixed", "Guided"),
        "Pinned - Guided": (2.00, "Pinned", "Guided"),
        "Fixed - Free (cantilever)": (2.10, "Fixed", "Free"),
    }
    e1c, e2c = st.columns(2)
    with e1c:
        endx = st.selectbox("End conditions, strong axis",
                            list(K_TABLE.keys()), 0, key="bc_endx")
        Kx, xb, xt = K_TABLE[endx]
        Lx_m = st.number_input("Lx (m)", 0.1, 50.0, 4.3, 0.1, key="bc_lx")
    with e2c:
        endy = st.selectbox("End conditions, weak axis",
                            list(K_TABLE.keys()), 0, key="bc_endy")
        Ky, yb, yt = K_TABLE[endy]
        Ly_m = st.number_input("Ly (m)", 0.1, 50.0, 4.3, 0.1, key="bc_ly")
    st.caption("Kx = %.2f, Ky = %.2f. Cl. 13.8.2 b) i) uses K = 1 for the "
               "member check itself. K above sets the model supports."
               % (Kx, Ky))

    f1, f2, f3 = st.columns(3)
    with f1:
        if is_comp:
            Cf = st.number_input("Cf (kN)", 0.0, 1e7, 1250.0, 25.0,
                                 key="bc_cf")
            Tf = 0.0
        else:
            Tf = st.number_input("Tf (kN)", 0.0, 1e7, 800.0, 25.0,
                                 key="bc_tf")
            Cf = 0.0
    with f2:
        use_e = st.checkbox("Mfx from eccentricity", value=True,
                            key="bc_use_e")
        if use_e:
            e_mm = st.number_input("e (mm)", 0.0, 2000.0, 130.0, 5.0,
                                   key="bc_e_mm")
            Mfx = (Cf if is_comp else Tf) * e_mm / 1000.0
            st.caption("Mfx = P e = " + num(Mfx, 1) + " kN-m")
        else:
            e_mm = 0.0
            Mfx = st.number_input("Mfx (kN-m)", 0.0, 1e6, 162.5, 5.0,
                                  key="bc_mfx")
    with f3:
        Mfy = st.number_input("Mfy (kN-m)", 0.0, 1e6, 0.0, 5.0,
                              key="bc_mfy")

    # ---- 5. Moment gradient factors ----
    st.subheader("5. Moment Gradient Factors")
    st.caption("omega1 per Cl. 13.8.5 feeds U1. omega2 per Cl. 13.6 feeds "
               "Mu in check c).")
    w1c, w2c = st.columns(2)
    with w1c:
        c1 = st.selectbox("omega1 case, x-axis",
                          [k for k, _l in OMEGA1_CASES],
                          format_func=lambda k: dict(OMEGA1_CASES)[k],
                          key="bc_w1x")
        kx = (st.number_input("kappa x", -1.0, 1.0, 1.0, 0.1, key="bc_kx")
              if c1 == "kappa" else 1.0)
        om1x = omega1_from(c1, kx)
        st.caption("omega1x = %.3f" % om1x)
        c2 = st.selectbox("omega1 case, y-axis",
                          [k for k, _l in OMEGA1_CASES],
                          format_func=lambda k: dict(OMEGA1_CASES)[k],
                          key="bc_w1y")
        ky = (st.number_input("kappa y", -1.0, 1.0, 1.0, 0.1, key="bc_ky")
              if c2 == "kappa" else 1.0)
        om1y = omega1_from(c2, ky)
        st.caption("omega1y = %.3f" % om1y)
    with w2c:
        w2mode = st.radio("omega2 method",
                          ["Linear gradient (kappa)", "Quarter-point"],
                          key="bc_w2m")
        if w2mode.startswith("Linear"):
            k2 = st.number_input("kappa", -1.0, 1.0, 1.0, 0.1, key="bc_k2")
            om2 = min(2.5, 1.75 + 1.05 * k2 + 0.3 * k2 ** 2)
        else:
            q1, q2, q3, q4 = st.columns(4)
            Mmax = q1.number_input("Mmax", 0.01, 1e6, 200.0, 10.0,
                                   key="bc_qmax")
            Ma = q2.number_input("Ma", 0.0, 1e6, 150.0, 10.0, key="bc_qa")
            Mb = q3.number_input("Mb", 0.0, 1e6, 180.0, 10.0, key="bc_qb")
            Mc = q4.number_input("Mc", 0.0, 1e6, 160.0, 10.0, key="bc_qc")
            den = math.sqrt(Mmax ** 2 + 4 * Ma ** 2 + 7 * Mb ** 2
                            + 4 * Mc ** 2)
            om2 = min(2.5, 4 * Mmax / den) if den > 0 else 1.0
        st.caption("omega2 = %.3f" % om2)
        class4_Se = st.checkbox(
            "Class 4: compute effective section modulus Se", value=False,
            key="bc_se",
            help="Cl. 13.5 c). Without this a Class 4 section reports "
                 "INCOMPLETE rather than dropping the moment term, which "
                 "would read as a pass. Se is major-axis only, so a "
                 "Class 4 section with Mfy stays INCOMPLETE.")

    # ---- run ----
    sec = {"designation": rec["designation"], "family": rec["family"],
           "A": rec["A"], "d": rec["d"], "b": rec["b"], "t": rec["t"],
           "w": rec["w"], "h": rec.get("h"), "rx": rec["rx"],
           "ry": rec["ry"], "Ix": rec["Ix"], "Iy": rec["Iy"],
           "Zx": rec["Zx"], "Zy": rec.get("Zy"), "Sx": rec["Sx"],
           "Sy": rec.get("Sy"), "J": rec.get("J"), "Cw": rec.get("Cw")}

    P = dict(Fy=Fy, E=E, G=G, phi=phi, n=n_col, Kx=Kx, Ky=Ky,
             Lx=Lx_m * 1000.0, Ly=Ly_m * 1000.0, Cf=Cf, Tf=Tf,
             Mfx=Mfx, Mfy=Mfy, braced=braced, omega1x=om1x, omega1y=om1y,
             omega2=om2, class4_use_Se=class4_Se, Lu=Ly_m * 1000.0)

    try:
        R = check_13_8(sec, P) if is_comp else None
        T = None if is_comp else check_13_9(sec, P)
    except Exception as exc:
        st.error("Calculation error: " + str(exc))
        st.stop()

    CI = (R or T)["class_info"]
    section_class = (R or T)["section_class"]

    # ---- 6. Table 1 ----
    st.divider()
    st.subheader("6. Local Buckling  -  Table 1")
    st.caption("Elements in uniform axial compression, Cl. 11.2.  "
               "sqrt(Fy) = " + num(math.sqrt(Fy), 3))
    t1_all = table1_elements(rec, Fy)
    t1_sel = []
    for c in t1_all:
        if st.checkbox(c["label"], value=True, key="bc_" + c["key"]):
            t1_sel.append(c)
            st.markdown("*" + c["why"] + "*")
            st.caption(c["clause"])
            st.latex(c["width"])
            st.latex(c["ratio_tex"])
            st.latex(c["limit_tex"])
            ok = c["ratio"] <= c["limit"]
            st.latex(tx(c["ratio"], 2) + (r" \leq " if ok else r" > ")
                     + tx(c["limit"], 2)
                     + (r"\qquad\textbf{PASS}" if ok
                        else r"\qquad\textbf{FAIL}"))
            (st.success if ok else st.error)(
                "Satisfies Table 1." if ok else
                "Exceeds Table 1, so the section is Class 4 for axial "
                "compression, Cl. 11.2.")
            st.markdown("---")

    # ---- 7. Table 2 ----
    st.subheader("7. Section Classification  -  Table 2")
    st.caption("Cl. 11.2 sends flexural compression to Table 2. The flange "
               "limits are the beam limits, because the flange is in "
               "uniform compression either way. The web limits carry the "
               "axial reduction, which is what makes this a beam-column "
               "classification rather than a beam one.")
    if not CI.get("ok"):
        st.error("Table 2 could not be built for this section.")
        st.stop()

    st.markdown("**Flange**")
    st.latex(r"\frac{b_{el}}{t} = " + tx(CI["lam_f"], 2)
             + r"\qquad \frac{145}{\sqrt{F_y}},\ \frac{170}{\sqrt{F_y}},\ "
               r"\frac{200}{\sqrt{F_y}} = "
             + tx(CI["flange_limits"][0], 2) + r",\ "
             + tx(CI["flange_limits"][1], 2) + r",\ "
             + tx(CI["flange_limits"][2], 2))
    st.latex(r"\Rightarrow\ \textbf{Class } " + str(CI["flange_class"]))

    if CI.get("web_class"):
        st.markdown("**Web, reduced for the axial load**")
        st.latex(r"C_y = A F_y = " + tx(CI["Cy_kN"], 1)
                 + r"\ \mathrm{kN} \qquad \frac{C_f}{\phi C_y} = "
                 + tx(CI["Cf_over_phiCy"], 4))
        st.latex(r"\frac{h}{w} \leq \frac{1100}{\sqrt{F_y}}"
                 r"\left(1 - 0.39\frac{C_f}{\phi C_y}\right),\ "
                 r"\frac{1700}{\sqrt{F_y}}\left(1 - 0.61\frac{C_f}"
                 r"{\phi C_y}\right),\ \frac{1900}{\sqrt{F_y}}"
                 r"\left(1 - 0.65\frac{C_f}{\phi C_y}\right)")
        st.latex(r"\frac{h}{w} = " + tx(CI["lam_w"], 2) + r"\qquad "
                 + tx(CI["web_limits"][0], 2) + r",\ "
                 + tx(CI["web_limits"][1], 2) + r",\ "
                 + tx(CI["web_limits"][2], 2)
                 + r"\ \Rightarrow\ \textbf{Class } "
                 + str(CI["web_class"]))
    st.latex(r"\text{Section class} = \max = \textbf{Class } "
             + str(section_class))

    # ================= TENSION =================
    if not is_comp:
        st.divider()
        st.subheader("8. Axial Tension and Bending  -  Cl. 13.9")
        st.latex(r"T_r = \phi A F_y = " + tx(phi, 2) + r" \times "
                 + tx(sec["A"], 0) + r" \times " + tx(Fy, 0) + r" = "
                 + tx(T["Tr_kN"], 1) + r"\ \mathrm{kN}")
        for nm, mr in ((r"M_{rx}", T["Mrx"]), (r"M_{ry}", T["Mry"])):
            if mr.get("Mr_kNm") is None:
                st.warning(str(mr.get("note", "")))
            else:
                st.latex(nm + r" = \phi\," + mr["modulus"] + r" F_y = "
                         + tx(mr["Mr_kNm"], 1) + r"\ \mathrm{kN\,m}"
                         + r"\quad(\text{" + mr["clause"] + r"})")
        st.markdown("**Cl. 13.9.1**")
        st.latex(r"\frac{T_f}{T_r} + \frac{M_{fx}}{M_{rx}}"
                 r"+ \frac{M_{fy}}{M_{ry}} \leq 1.0")
        st.code("  Tf/Tr   = %s\n  Mfx/Mrx = %s\n  Mfy/Mry = %s\n"
                "  ---------------------------\n  total   = %s  %s"
                % (uc(T["terms_13_9_1"][0]), uc(T["terms_13_9_1"][1]),
                   uc(T["terms_13_9_1"][2]), uc(T["total_13_9_1"]),
                   verdict(T["total_13_9_1"])), language="text")
        v = T["total_13_9_1"]
        (st.success if (v is not None and v <= 1.0) else st.error)(
            "Cl. 13.9.1 = " + uc(v) + "  " + verdict(v))

        st.markdown("**Cl. 13.9.2, laterally unsupported**")
        if T.get("total_13_9_2") is None:
            st.info("Not computed: "
                    + str(T.get("ltb", {}).get("note", "Cl. 13.6 inputs "
                                                       "unavailable.")))
        else:
            st.caption(T["sub_13_9_2"])
            st.latex(r"\frac{M_f}{M_r} - \frac{T_f " + T["modulus_name"]
                     + r"}{M_r A} \leq 1.0")
            st.latex(r"M_r\ (\text{Cl. 13.6}) = "
                     + tx(T["Mr_unsup_kNm"], 1) + r"\ \mathrm{kN\,m}")
            v2 = T["total_13_9_2"]
            (st.success if v2 <= 1.0 else st.error)(
                "Cl. 13.9.2 = " + uc(v2) + "  " + verdict(v2))

    # ================= COMPRESSION =================
    else:
        C = R["coefficients"]
        st.divider()
        st.subheader("8. Moment Resistance  -  Cl. 13.5")
        st.caption("Governing clause: " + C["clause"] + ".  " + C["note"])
        for nm, mr in ((r"M_{rx}", R["Mrx"]), (r"M_{ry}", R["Mry"])):
            if mr.get("Mr_kNm") is None:
                st.warning(str(mr.get("note", "")))
            else:
                st.latex(nm + r" = \phi\," + mr["modulus"] + r" F_y = "
                         + tx(phi, 2) + r" \times "
                         + tx(mr["modulus_value"], 0) + r" \times "
                         + tx(Fy, 0) + r" = " + tx(mr["Mr_kNm"], 1)
                         + r"\ \mathrm{kN\,m}\quad(\text{" + mr["clause"]
                         + r"})")

        st.divider()
        st.subheader("9. P-delta  -  Ce and U1, Cl. 13.8.4 and 13.8.5")
        st.caption("Axial compression acting on the deflected shape of the "
                   "member between its ends generates a secondary moment. "
                   "U1 accounts for it. This is a member-level effect and "
                   "exists in braced frames.")
        st.latex(r"C_e = \frac{\pi^2 E I}{L^2} \qquad "
                 r"U_1 = \frac{\omega_1}{1 - C_f/C_e} \geq 1.0")
        st.latex(r"C_{e,x} = \frac{\pi^2 (" + tx(E, 0) + r")("
                 + tx(sec["Ix"], 0) + r")}{(" + tx(P["Lx"], 0) + r")^2} = "
                 + tx(R["Ce_x_kN"], 0) + r"\ \mathrm{kN}")
        st.latex(r"U_{1x} = \frac{" + tx(om1x, 3) + r"}{1 - " + tx(Cf, 1)
                 + r"/" + tx(R["Ce_x_kN"], 0) + r"} = " + tx(R["U1x"], 4))
        if R["u1x"]["forced"]:
            st.info(R["u1x"]["why"])
        st.latex(r"U_{1x} M_{fx} = " + tx(R["U1x"] * Mfx, 1)
                 + r"\ \mathrm{kN\,m}\quad(\text{primary }"
                 + tx(Mfx, 1) + r")")
        if Mfy > 0:
            st.latex(r"C_{e,y} = " + tx(R["Ce_y_kN"], 0)
                     + r"\ \mathrm{kN} \qquad U_{1y} = " + tx(R["U1y"], 4))

        st.info("**P-Delta**, the system-level sway effect, comes from "
                "vertical load acting through the sway displacement of the "
                "structure. It does not exist in a braced frame because "
                "the bracing prevents sway. "
                + ("This frame is braced, so P-Delta does not apply."
                   if braced else
                   "This frame is unbraced, so P-Delta must be carried by "
                   "the frame analysis that produced Mf. It is not "
                   "computed here."))

        st.divider()
        st.subheader("10. Check a)  Cross-sectional strength")
        A_ = R["check_a"]
        st.caption("lambda = 0, beta = 0.6.  " + A_["clause"])
        if not braced:
            st.warning("Cl. 13.8.2 a) applies to members in braced frames "
                       "only. Shown for reference, not counted.")
        st.latex(r"C_r = \phi A F_y = " + tx(A_["Cr_kN"], 1)
                 + r"\ \mathrm{kN}")
        st.latex(r"\frac{C_f}{C_r} + \frac{" + tx(A_["coef_x"], 2)
                 + r"\,U_{1x}M_{fx}}{M_{rx}} + \frac{"
                 + tx(A_["coef_y"], 2)
                 + r"\,U_{1y}M_{fy}}{M_{ry}} \leq 1.0")
        st.code("  Cf/Cr             = %s\n  %.2f U1x Mfx/Mrx  = %s\n"
                "  %.2f U1y Mfy/Mry  = %s\n"
                "  --------------------------------\n"
                "  total             = %s  %s"
                % (uc(A_["terms"][0]), A_["coef_x"], uc(A_["terms"][1]),
                   A_["coef_y"], uc(A_["terms"][2]), uc(A_["total"]),
                   verdict(A_["total"])), language="text")

        st.divider()
        st.subheader("11. Check b)  Overall member strength")
        B_ = R["check_b"]
        st.caption("K = 1, Cr on " + B_["axis"] + ".  " + B_["clause"])
        st.latex(r"\frac{KL}{r} = " + tx(B_["KLr"], 2)
                 + r"\qquad \lambda = \frac{KL}{r}\sqrt{\frac{F_y}"
                   r"{\pi^2 E}} = " + tx(B_["lam"], 4))
        st.latex(r"F_{cr} = \frac{F_y}{\left(1+\lambda^{2n}\right)^{1/n}}"
                 r" = " + tx(B_["Fcr"], 1) + r"\ \mathrm{MPa}")
        st.latex(r"C_r = \phi A F_{cr} = " + tx(B_["Cr_kN"], 1)
                 + r"\ \mathrm{kN}")
        st.latex(r"\beta = 0.6 + 0.4\lambda_y = 0.6 + 0.4("
                 + tx(B_["lam_y"], 4) + r") = " + tx(B_["beta"], 4)
                 + r" \leq 0.85")
        st.code("  Cf/Cr             = %s\n  %.2f U1x Mfx/Mrx  = %s\n"
                "  %.2f U1y Mfy/Mry  = %s\n"
                "  --------------------------------\n"
                "  total             = %s  %s"
                % (uc(B_["terms"][0]), B_["coef_x"], uc(B_["terms"][1]),
                   B_["coef_y"], uc(B_["terms"][2]), uc(B_["total"]),
                   verdict(B_["total"])), language="text")

        st.divider()
        st.subheader("12. Check c)  Lateral torsional buckling")
        C_ = R["check_c"]
        if not C_["applies"]:
            st.info("Does not apply. " + C_["note"])
        else:
            st.caption("Cr on the weak axis, Mrx from Cl. 13.6.  "
                       + C_["clause"])
            ltb = C_["ltb"]
            st.latex(r"\left(\frac{KL}{r}\right)_y = " + tx(C_["KLr"], 2)
                     + r"\qquad C_r = \phi A F_{cr} = "
                     + tx(C_["Cr_kN"], 1) + r"\ \mathrm{kN}")
            if ltb.get("Mr_kNm") is None:
                st.warning(str(ltb.get("note", "Cl. 13.6 unavailable.")))
            else:
                st.latex(r"M_u = \frac{\omega_2 \pi}{L}\sqrt{E I_y G J"
                         r" + \left(\frac{\pi E}{L}\right)^2 I_y C_w} = "
                         + tx(ltb["Mu_kNm"], 1) + r"\ \mathrm{kN\,m}")
                st.latex(r"M_p = F_y " + ltb["modulus"] + r" = "
                         + tx(ltb["Mp_kNm"], 1)
                         + r"\ \mathrm{kN\,m} \qquad 0.67 M_p = "
                         + tx(ltb["threshold_kNm"], 1))
                st.caption("Branch: " + ltb["branch"])
                st.latex(ltb["formula"])
                st.latex(r"M_{rx}\ (\text{Cl. 13.6}) = "
                         + tx(ltb["Mr_kNm"], 1) + r"\ \mathrm{kN\,m}")
            st.code("  Cf/Cr             = %s\n  %.2f U1x Mfx/Mrx  = %s\n"
                    "  %.2f U1y Mfy/Mry  = %s\n"
                    "  --------------------------------\n"
                    "  total             = %s  %s"
                    % (uc(C_["terms"][0]), C_["coef_x"], uc(C_["terms"][1]),
                       C_["coef_y"], uc(C_["terms"][2]), uc(C_["total"]),
                       verdict(C_["total"])), language="text")

        st.divider()
        st.subheader("13. Additional moment-only requirement")
        M_ = R["check_moment"]
        st.latex(r"\frac{M_{fx}}{M_{rx}} + \frac{M_{fy}}{M_{ry}} \leq 1.0")
        st.code("  Mfx/Mrx = %s\n  Mfy/Mry = %s\n"
                "  ---------------------\n  total   = %s  %s"
                % (uc(M_["terms"][0]), uc(M_["terms"][1]), uc(M_["total"]),
                   verdict(M_["total"])), language="text")

        st.divider()
        st.subheader("14. Governing Check")
        for name, val, ap in R["rows"]:
            if not ap:
                st.markdown("- " + name + "  -  does not apply")
            elif val is None:
                st.markdown("- " + name + "  -  **INCOMPLETE**")
            else:
                st.markdown("- " + name + "  =  **" + uc(val) + "**  "
                            + verdict(val))
        if R["overall"] == "OK":
            st.success("PASS.  Governing: " + str(R["governing_name"])
                       + " = " + uc(R["governing_uc"]))
        elif R["overall"] == "NG":
            st.error("FAIL.  Governing: " + str(R["governing_name"])
                     + " = " + uc(R["governing_uc"]))
        else:
            st.warning("INCOMPLETE. A moment resistance could not be "
                       "formed, so no interaction value is reported. "
                       "Dropping the term instead would read as a pass.")

# ============================================================
# MODEL
# ============================================================
with col_model:
    st.subheader("Member Model")
    if not HAS_VIEWER:
        st.info("3D viewer not loaded. Place section_geometry.py, "
                "viewer_3d.py, viewer_3d_beamcolumn.py and "
                "viewer_3d_beamcolumn.html in the repository root.")
    else:
        _sec_obj = type("S", (), dict(
            designation=rec["designation"],
            family=("W" if rec["kind"] == "I" else "HSS"),
            family_label=rec["family_label"],
            hss_kind=("CHS" if rec["kind"] == "CHS"
                      else ("RHS/SHS" if rec["kind"] == "RHS" else None)),
            A_mm2=rec["A"], d_mm=rec["d"], b_mm=rec["b"], t_mm=rec["t"],
            w_mm=rec["w"], h_mm=rec.get("h")))()

        _sup = {"x": {"K": float(Kx), "L": float(P["Lx"]),
                      "bottom": xb, "top": xt},
                "y": {"K": float(Ky), "L": float(P["Ly"]),
                      "bottom": yb, "top": yt}}
        _load = {"Cf_kN": float(Cf), "Tf_kN": float(Tf),
                 "Mfx_kNm": float(Mfx), "Mfy_kNm": float(Mfy),
                 "e_mm": float(e_mm),
                 "axial": "compression" if is_comp else "tension"}

        _e1 = [{"key": c["key"], "zone": c["zone"],
                "label": c["label"].split(",")[0],
                "ok": bool(c["ratio"] <= c["limit"]),
                "ratio": float(c["ratio"]), "limit": float(c["limit"])}
               for c in t1_sel]
        _e2 = []
        if CI.get("flange_class"):
            _e2.append({"zone": "flange", "label": "Flange",
                        "cls": int(CI["flange_class"])})
        if CI.get("web_class"):
            _e2.append({"zone": "web", "label": "Web",
                        "cls": int(CI["web_class"])})

        if is_comp:
            _res = {"section_class": section_class,
                    "clause": R["coefficients"]["clause"], "braced": braced,
                    "U1x": R["U1x"], "U1y": R["U1y"],
                    "Ce_x_kN": R["Ce_x_kN"], "Ce_y_kN": R["Ce_y_kN"],
                    "beta": R["beta"], "Cy_kN": CI.get("Cy_kN"),
                    "Mrx_kNm": R["Mrx_kNm"], "Mry_kNm": R["Mry_kNm"],
                    "Cr_kN": R["check_b"]["Cr_kN"],
                    "KLr": R["check_b"]["KLr"], "lam": R["check_b"]["lam"],
                    "Fcr": R["check_b"]["Fcr"],
                    "governing_name": R["governing_name"],
                    "governing_uc": R["governing_uc"],
                    "overall": R["overall"]}
        else:
            tv = T["total_13_9_1"]
            _res = {"section_class": section_class, "clause": "Cl. 13.9",
                    "braced": braced, "U1x": 1.0, "U1y": 1.0,
                    "Cy_kN": CI.get("Cy_kN"),
                    "Mrx_kNm": T["Mrx"].get("Mr_kNm"),
                    "Mry_kNm": T["Mry"].get("Mr_kNm"),
                    "governing_name": "Cl. 13.9.1", "governing_uc": tv,
                    "overall": ("OK" if (tv is not None and tv <= 1.0)
                                else ("NG" if tv is not None
                                      else "INCOMPLETE"))}

        _props = [{"group": r["group"], "symbol": r["symbol"],
                   "value": num(r["value"], 1), "unit": r["unit"]}
                  for r in display_rows(rec)]

        viewer_3d_beamcolumn.render_beamcolumn(
            _sec_obj, length_mm=max(P["Lx"], P["Ly"]), height=680,
            supports=_sup, load=_load, elements_t1=_e1, elements_t2=_e2,
            results=_res, props=_props, show_diagnostics=False)

        st.caption("The behaviour dropdown maps each calculation onto the "
                   "member: Table 1, Table 2 class, combined stress, "
                   "P-delta amplification, LTB and utilisation.")