from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from _theme import apply_theme, render_sidebar_logo, render_footer, gate_disclaimer

# ─────────────────────────────────────────────────────────────
# DATA DIR  (pages/ is one level below root where data/ lives)
# ─────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ─────────────────────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = str(s).strip().lower()
    for ch in "()[]{}":
        s = s.replace(ch, "")
    s = s.replace("/", "_").replace("-", "_").replace(" ", "_")
    return "".join(c for c in s if (c.isalnum() or c == "_") and ord(c) < 128)


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    if not s or s in ("-", "\u2014", "N/A", "n/a"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def _pick(rec: Dict[str, Any], candidates: List[str]) -> Optional[Any]:
    m = {_norm(k): v for k, v in rec.items()}
    for c in candidates:
        k = _norm(c)
        if k in m and m[k] not in ("", None):
            return m[k]
    return None


def _fmt(x: Any, nd: int = 3) -> str:
    if x is None:
        return "\u2014"
    try:
        xf = float(x)
        if abs(xf) >= 10000:
            return f"{xf:,.0f}"
        if abs(xf) >= 1000:
            return f"{xf:,.{max(0, nd - 1)}f}"
        return f"{xf:.{nd}f}"
    except Exception:
        return str(x)

# ─────────────────────────────────────────────────────────────
# CSV COLUMN CANON
# ─────────────────────────────────────────────────────────────

CANON: Dict[str, List[str]] = {
    "designation": ["Designation", "designation", "section", "Section", "shape", "name"],
    "class":       ["Class", "class", "Section Class"],
    "ba_t":        ["ba/t", "b/t", "bf/t", "flange b/t"],
    "h_w":         ["h/w", "h/tw", "web h/w"],
    "A":           ["Area (mmý)", "Area (mm2)", "Area (mm²)", "Area (mm^2)", "Area", "area", "A"],
    "Ix":          ["Ix (10^6 mm?)", "Ix", "Ix (10^6 mm^4)"],
    "Sx":          ["Sx (10^3 mm?)", "Sx", "Sx (10^3 mm^3)"],
    "rx":          ["rx (mm)", "rx", "r_x"],
    "Zx":          ["Zx (10^3 mm?)", "Zx", "Zx (10^3 mm^3)"],
    "Iy":          ["Iy (10^6 mm?)", "Iy"],
    "Sy":          ["Sy (10^3 mm?)", "Sy"],
    "ry":          ["ry (mm)", "ry", "r_y"],
    "Zy":          ["Zy (10^3 mm?)", "Zy"],
    "J":           ["J (10^3 mm?)", "J (10^3 mm^4)", "J"],
    "Cw":          ["Cw (10^9 mm?)", "Cw (10^9 mm^6)", "Cw"],
    "d":           ["Depth d (mm)", "Depth (mm)", "d (mm)", "d", "depth"],
    "b":           ["Flange Width b (mm)", "Flange Width (mm)", "b (mm)", "b", "bf"],
    "t":           ["Flange Thickness t (mm)", "Flange Thickness (mm)", "t (mm)", "t", "tf"],
    "w":           ["Web Thickness w (mm)", "Web Thickness (mm)", "w (mm)", "w", "tw"],
}


def _canonicalize(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    for k, candidates in CANON.items():
        v = _pick(rec, candidates)
        if v is not None:
            out[k] = v
    des = out.get("designation")
    if des:
        out["designation"] = str(des).strip()
    return out

# ─────────────────────────────────────────────────────────────
# LOAD SHAPES FROM CSV
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_shapes() -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    shapes: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    if not DATA_DIR.exists():
        return {}, []

    for p in sorted(DATA_DIR.glob("*.csv"), key=lambda x: x.name.lower()):
        try:
            fh = p.open("r", encoding="utf-8", newline="")
            fh.read(256)
            fh.seek(0)
        except UnicodeDecodeError:
            fh = p.open("r", encoding="latin-1", newline="")

        with fh as f:
            reader = csv.DictReader(f)
            for rec in reader:
                r2 = _canonicalize(rec)
                des = r2.get("designation")
                if not des or not str(des).strip():
                    continue
                shapes[des] = r2
                order.append(des)

    seen: set = set()
    order2 = []
    for k in order:
        if k not in seen:
            seen.add(k)
            order2.append(k)
    import re as _re
    order2.sort(key=lambda s: [int(c) if c.isdigit() else c.lower() for c in _re.split(r"(\d+)", s)])
    return shapes, order2

# ─────────────────────────────────────────────────────────────
# HSS DESIGNATION PARSER
# ─────────────────────────────────────────────────────────────

def parse_hss_designation(des: str) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
    s = des.upper().replace("HSS", "").strip()
    s = s.replace("\u00d7", "X").replace("x", "X").replace(" ", "")
    parts = s.split("X")
    nums = []
    for p in parts:
        try:
            nums.append(float(p))
        except Exception:
            pass
    if len(nums) >= 3:
        return nums[0], nums[1], nums[2], "RHS/SHS"
    if len(nums) == 2:
        return nums[0], None, nums[1], "CHS"
    return None, None, None, "UNKNOWN"


def section_family(des: str) -> str:
    n = des.strip().upper()
    if n.startswith("WWF"):
        return "WWF"
    if n.startswith("W"):
        return "W"
    if "HSS" in n:
        return "HSS"
    if n.startswith("L"):
        return "ANGLE"
    if n.startswith("2L"):
        return "DOUBLE_ANGLE"
    return "OTHER"


def hss_type(des: str) -> str:
    _, _, _, typ = parse_hss_designation(des)
    return typ

# ─────────────────────────────────────────────────────────────
# SECTION DATACLASS
# ─────────────────────────────────────────────────────────────

@dataclass
class SectionProps:
    designation: str
    family: str
    A_mm2: float
    rx_mm: float
    ry_mm: float
    d_mm: Optional[float] = None
    b_mm: Optional[float] = None
    t_mm: Optional[float] = None
    w_mm: Optional[float] = None
    h_mm: Optional[float] = None
    section_class: Optional[int] = None
    ba_t: Optional[float] = None
    h_w: Optional[float] = None
    J_mm4: Optional[float] = None
    Cw_mm6: Optional[float] = None
    hss_kind: Optional[str] = None
    r_bar_o_sq: Optional[float] = None


def build_section(designation: str, rec: Dict[str, Any]) -> SectionProps:
    A  = _to_float(rec.get("A"))
    rx = _to_float(rec.get("rx"))
    ry = _to_float(rec.get("ry"))
    if A is None or rx is None or ry is None:
        raise ValueError(f"Missing A/rx/ry for {designation}.")

    fam = section_family(designation)
    d   = _to_float(rec.get("d"))
    b   = _to_float(rec.get("b"))
    t   = _to_float(rec.get("t"))
    w   = _to_float(rec.get("w"))

    cls_raw = rec.get("class") or rec.get("Class")
    sec_class: Optional[int] = None
    if cls_raw is not None:
        try:
            sec_class = int(float(str(cls_raw).strip()))
        except Exception:
            pass

    ba_t_val = _to_float(rec.get("ba_t"))
    h_w_val  = _to_float(rec.get("h_w"))

    h_mm: Optional[float] = None
    if d is not None and t is not None:
        h_mm = d - 2.0 * t

    J_raw  = _to_float(rec.get("J"))
    Cw_raw = _to_float(rec.get("Cw"))
    J_mm4:  Optional[float] = J_raw  * 1e3 if J_raw  is not None else None
    Cw_mm6: Optional[float] = Cw_raw * 1e9 if Cw_raw is not None else None

    kind = None
    if fam == "HSS":
        pd_, pb_, pt_, kind = parse_hss_designation(designation)
        if d is None and pd_ is not None:
            d = pd_
        if b is None and pb_ is not None:
            b = pb_
        if t is None and pt_ is not None:
            t = pt_

    r_bar_o_sq: Optional[float] = None
    if fam in ("W", "WWF"):
        r_bar_o_sq = rx ** 2 + ry ** 2

    return SectionProps(
        designation=designation,
        family=fam,
        A_mm2=float(A),
        rx_mm=float(rx),
        ry_mm=float(ry),
        d_mm=d, b_mm=b, t_mm=t, w_mm=w, h_mm=h_mm,
        section_class=sec_class,
        ba_t=ba_t_val,
        h_w=h_w_val,
        J_mm4=J_mm4,
        Cw_mm6=Cw_mm6,
        hss_kind=kind,
        r_bar_o_sq=r_bar_o_sq,
    )

# ─────────────────────────────────────────────────────────────
# TABLE 1 — W-SECTION LOCAL BUCKLING CHECK (CSA S16)
# ─────────────────────────────────────────────────────────────

@dataclass
class LocalBucklingResult:
    flange_ratio: Optional[float] = None
    flange_limit: Optional[float] = None
    flange_ok: Optional[bool] = None
    flange_note: str = ""
    web_ratio: Optional[float] = None
    web_limit: Optional[float] = None
    web_ok: Optional[bool] = None
    web_note: str = ""
    is_class4: bool = False
    source: str = "Table 1 (CSA S16) — axial compression"


def check_local_buckling_W(sec: SectionProps, Fy_MPa: float) -> LocalBucklingResult:
    res = LocalBucklingResult()
    sqrt_Fy = math.sqrt(float(Fy_MPa))
    is_class4 = False

    if sec.ba_t is not None:
        flange_ratio = float(sec.ba_t)
    elif sec.b_mm is not None and sec.t_mm is not None and sec.t_mm > 0:
        flange_ratio = (sec.b_mm / 2.0) / sec.t_mm
    else:
        flange_ratio = None

    flange_limit = 200.0 / sqrt_Fy
    res.flange_ratio = flange_ratio
    res.flange_limit = flange_limit

    if flange_ratio is not None:
        res.flange_ok = flange_ratio <= flange_limit
        if not res.flange_ok:
            is_class4 = True
            res.flange_note = f"FAIL — b_el/t = {flange_ratio:.2f} > {flange_limit:.2f} (Class 4 flange)"
        else:
            res.flange_note = f"OK — b_el/t = {flange_ratio:.2f} \u2264 {flange_limit:.2f}"

    if sec.h_w is not None:
        web_ratio = float(sec.h_w)
    elif sec.h_mm is not None and sec.w_mm is not None and sec.w_mm > 0:
        web_ratio = sec.h_mm / sec.w_mm
    else:
        web_ratio = None

    web_limit = 670.0 / sqrt_Fy
    res.web_ratio = web_ratio
    res.web_limit = web_limit

    if web_ratio is not None:
        res.web_ok = web_ratio <= web_limit
        if not res.web_ok:
            is_class4 = True
            res.web_note = f"FAIL — h/w = {web_ratio:.2f} > {web_limit:.2f} (Class 4 web)"
        else:
            res.web_note = f"OK — h/w = {web_ratio:.2f} \u2264 {web_limit:.2f}"

    if sec.section_class is not None and sec.section_class >= 4:
        is_class4 = True

    res.is_class4 = is_class4
    return res

# ─────────────────────────────────────────────────────────────
# HSS LOCAL BUCKLING (Table 1)
# ─────────────────────────────────────────────────────────────

def check_local_buckling_HSS(
    sec: SectionProps, Fy_MPa: float
) -> Tuple[float, str, Optional[float], Optional[float]]:
    if sec.family != "HSS":
        return sec.A_mm2, "N/A (not HSS)", None, None
    if sec.t_mm is None or sec.t_mm <= 0:
        return sec.A_mm2, "HSS (t missing)", None, None

    t = float(sec.t_mm)
    if sec.hss_kind == "CHS" and sec.d_mm is not None:
        lam   = float(sec.d_mm) / t
        limit = 23000.0 / float(Fy_MPa)
        Ae    = sec.A_mm2 if lam <= limit else sec.A_mm2 * (limit / lam)
        label = "CHS non-slender" if lam <= limit else "CHS slender (Class 4)"
        return Ae, label, lam, limit

    if sec.hss_kind == "RHS/SHS" and sec.b_mm is not None:
        bflat = float(sec.b_mm) - 3.0 * t
        lam   = bflat / t
        limit = 670.0 / math.sqrt(float(Fy_MPa))
        Ae    = sec.A_mm2 if lam <= limit else sec.A_mm2 * (limit / lam)
        label = "HSS non-slender" if lam <= limit else "HSS slender (Class 4)"
        return Ae, label, lam, limit

    return sec.A_mm2, "HSS (unknown kind)", None, None

# ─────────────────────────────────────────────────────────────
# EULER AND CSA COLUMN CURVE
# ─────────────────────────────────────────────────────────────

def euler_Fe(E_MPa: float, KL_over_r: float) -> float:
    return (math.pi ** 2) * float(E_MPa) / (float(KL_over_r) ** 2)


def csa_lambda(KL_over_r: float, Fy_MPa: float, E_MPa: float) -> float:
    return float(KL_over_r) * math.sqrt(float(Fy_MPa) / ((math.pi ** 2) * float(E_MPa)))


def csa_Fcr(Fy_MPa: float, lam: float, n: float) -> float:
    return float(Fy_MPa) / ((1.0 + lam ** (2.0 * float(n))) ** (1.0 / float(n)))

# ─────────────────────────────────────────────────────────────
# TORSIONAL BUCKLING (Clause 13.3.2a)
# ─────────────────────────────────────────────────────────────

def torsional_Fe(
    sec: SectionProps,
    E_MPa: float,
    G_MPa: float,
    Kz: float,
    Lz_mm: float,
) -> Optional[float]:
    if sec.J_mm4 is None or sec.Cw_mm6 is None or sec.r_bar_o_sq is None:
        return None
    if sec.A_mm2 <= 0 or sec.r_bar_o_sq <= 0:
        return None

    KzLz = float(Kz) * float(Lz_mm)
    if KzLz <= 0:
        return None

    warping   = (math.pi ** 2 * float(E_MPa) * float(sec.Cw_mm6)) / (KzLz ** 2)
    st_venant = float(G_MPa) * float(sec.J_mm4)
    Fez = (warping + st_venant) / (float(sec.A_mm2) * float(sec.r_bar_o_sq))
    return Fez

# ─────────────────────────────────────────────────────────────
# SINGLE-ANGLE MODIFIED KL/r  (Clause 13.3.3)
# ─────────────────────────────────────────────────────────────

def angle_modified_KLr(
    L_mm: float,
    rx_mm: float,
    ry_minor_mm: float,
    is_box_or_space_truss: bool = False,
    bl: Optional[float] = None,
    bs: Optional[float] = None,
    connected_through_shorter_leg: bool = False,
) -> Tuple[float, str]:
    Lr_x = L_mm / rx_mm if rx_mm > 0 else 9999.0

    if is_box_or_space_truss:
        if Lr_x <= 75.0:
            KLr = 60.0 + 0.8 * Lr_x
            note = "Box/space truss: KL/r = 60 + 0.8\u00b7L/rx"
        else:
            KLr = 45.0 + Lr_x
            note = "Box/space truss: KL/r = 45 + L/rx"
    else:
        if Lr_x <= 80.0:
            KLr = 72.0 + 0.75 * Lr_x
            note = "Individual/planar truss: KL/r = 72 + 0.75\u00b7L/rx"
        else:
            KLr = 32.0 + 1.25 * Lr_x
            note = "Individual/planar truss: KL/r = 32 + 1.25\u00b7L/rx"

    KLr = min(KLr, 200.0)

    if bl is not None and bs is not None and bs > 0:
        ratio = bl / bs
        if ratio < 1.7 and connected_through_shorter_leg:
            correction = 4.0 * (ratio ** 2 - 1.0) if not is_box_or_space_truss else 6.0 * (ratio ** 2 - 1.0)
            KLr = max(KLr + correction, 0.95 * L_mm / ry_minor_mm)
            note += f" + unequal-leg correction ({correction:.1f})"

    return KLr, note

# ─────────────────────────────────────────────────────────────
# MAIN COMPRESSION CHECK
# ─────────────────────────────────────────────────────────────

@dataclass
class CompressionResult:
    Ae_mm2: float = 0.0
    local_label: str = ""
    local_lambda: Optional[float] = None
    local_limit: Optional[float] = None
    local_check: Optional[LocalBucklingResult] = None
    is_class4: bool = False
    KLr_x: float = 0.0
    KLr_y: float = 0.0
    KLr_gov: float = 0.0
    KLr_warn: bool = False
    Fex_MPa: float = 0.0
    Fey_MPa: float = 0.0
    Fe_flex_MPa: float = 0.0
    Fez_MPa: Optional[float] = None
    Fe_gov_MPa: float = 0.0
    torsion_governs: bool = False
    lam: float = 0.0
    n_used: float = 1.34
    Fcr_MPa: float = 0.0
    Cr_kN: float = 0.0
    angle_note: str = ""


def run_compression_check(
    sec: SectionProps,
    Fy: float,
    E: float,
    G: float,
    phi_c: float,
    n_curve: float,
    Kx: float,
    Ky: float,
    Kz: float,
    Lx_mm: float,
    Ly_mm: float,
    Lz_mm: float,
    angle_truss_type: str = "individual",
    angle_bl: Optional[float] = None,
    angle_bs: Optional[float] = None,
    angle_short_leg: bool = False,
) -> CompressionResult:
    R = CompressionResult()
    R.n_used = n_curve

    # 1. Local buckling
    if sec.family in ("W", "WWF"):
        lb = check_local_buckling_W(sec, Fy)
        R.local_check = lb
        R.is_class4   = lb.is_class4
        R.Ae_mm2      = sec.A_mm2
        R.local_label = "W/WWF — Table 1 checked"
        if lb.is_class4:
            R.local_label = "WARNING: Class 4 — check Cl 13.3.5 for reduced Ae"
    elif sec.family == "HSS":
        Ae, label, lam_l, lim_l = check_local_buckling_HSS(sec, Fy)
        R.Ae_mm2      = Ae
        R.local_label = label
        R.local_lambda = lam_l
        R.local_limit  = lim_l
        R.is_class4    = "Class 4" in label or "slender" in label.lower()
    else:
        R.Ae_mm2      = sec.A_mm2
        R.local_label = "No local buckling check (angle/other)"

    # 2. Slenderness
    if sec.family in ("ANGLE", "DOUBLE_ANGLE"):
        ry_minor = min(sec.rx_mm, sec.ry_mm)
        KLr_mod, angle_note = angle_modified_KLr(
            L_mm=Ly_mm,
            rx_mm=sec.rx_mm,
            ry_minor_mm=ry_minor,
            is_box_or_space_truss=(angle_truss_type == "box"),
            bl=angle_bl,
            bs=angle_bs,
            connected_through_shorter_leg=angle_short_leg,
        )
        R.KLr_x   = KLr_mod
        R.KLr_y   = KLr_mod
        R.KLr_gov = KLr_mod
        R.angle_note = angle_note
    else:
        R.KLr_x = (Kx * Lx_mm) / sec.rx_mm
        R.KLr_y = (Ky * Ly_mm) / sec.ry_mm
        R.KLr_gov = max(R.KLr_x, R.KLr_y)

    R.KLr_warn = R.KLr_gov > 200.0

    # 3. Elastic buckling stresses
    R.Fex_MPa = euler_Fe(E, R.KLr_x) if R.KLr_x > 0 else 1e9
    R.Fey_MPa = euler_Fe(E, R.KLr_y) if R.KLr_y > 0 else 1e9
    R.Fe_flex_MPa = min(R.Fex_MPa, R.Fey_MPa)

    # 4. Torsional buckling (Cl 13.3.2a, doubly-symmetric)
    Fez = None
    if sec.family in ("W", "WWF") and sec.J_mm4 is not None and sec.Cw_mm6 is not None:
        Fez = torsional_Fe(sec, E, G, Kz, Lz_mm)

    R.Fez_MPa = Fez
    if Fez is not None and Fez < R.Fe_flex_MPa:
        R.Fe_gov_MPa     = Fez
        R.torsion_governs = True
    else:
        R.Fe_gov_MPa      = R.Fe_flex_MPa
        R.torsion_governs = False

    # 5. Column curve
    R.lam     = math.sqrt(Fy / R.Fe_gov_MPa) if R.Fe_gov_MPa > 0 else 99.0
    R.Fcr_MPa = csa_Fcr(Fy, R.lam, n_curve)

    # 6. Factored resistance
    R.Cr_kN = (phi_c * R.Ae_mm2 * R.Fcr_MPa) / 1000.0

    return R

# ─────────────────────────────────────────────────────────────
# REPORT RENDERER
# ─────────────────────────────────────────────────────────────

def render_report(
    sec: SectionProps,
    params: dict,
    R: CompressionResult,
    Pu_kN: Optional[float],
) -> None:
    Fy      = params["Fy"]
    E       = params["E"]
    G       = params["G"]
    phi_c   = params["phi_c"]
    n_curve = params["n_curve"]
    Kx      = params["Kx"]
    Ky      = params["Ky"]
    Kz      = params["Kz"]
    Lx      = params["Lx_mm"]
    Ly      = params["Ly_mm"]
    Lz      = params["Lz_mm"]

    # Step 0
    st.subheader("Step 0 \u2014 Section & Material Inputs")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Section:** {sec.designation} | Family: {sec.family}")
        st.write(f"A = {_fmt(sec.A_mm2, 0)} mm\u00b2 | rx = {_fmt(sec.rx_mm, 1)} mm | ry = {_fmt(sec.ry_mm, 1)} mm")
        if sec.section_class:
            st.write(f"Section class (CSV): {sec.section_class}")
        if sec.J_mm4:
            cw_str = _fmt(sec.Cw_mm6 / 1e9, 1) if sec.Cw_mm6 else "n/a"
            st.write(f"J = {_fmt(sec.J_mm4 / 1e3, 0)} \u00d710\u00b3 mm\u2074 | Cw = {cw_str} \u00d710\u2079 mm\u2076")
    with c2:
        st.write(f"Fy = {_fmt(Fy, 0)} MPa | E = {_fmt(E, 0)} MPa | G = {_fmt(G, 0)} MPa")
        st.write(f"\u03c6c = {phi_c} | n = {n_curve}")
        st.write(f"Kx = {Kx}, Ky = {Ky}, Kz = {Kz}")
        st.write(f"Lx = {_fmt(Lx / 1000, 2)} m | Ly = {_fmt(Ly / 1000, 2)} m | Lz = {_fmt(Lz / 1000, 2)} m")

    # Step 1
    st.subheader("Step 1 \u2014 Local Buckling (Table 1, CSA S16)")
    if sec.family in ("W", "WWF") and R.local_check is not None:
        lb = R.local_check
        st.write("**Flange check** (one edge supported, I-section flanges):")
        st.latex(r"\frac{b_{el}}{t} \leq \frac{200}{\sqrt{F_y}}")
        if lb.flange_ratio is not None:
            icon = "\u2705 PASS" if lb.flange_ok else "\u274c FAIL"
            st.write(f"{icon} | b_el/t = {_fmt(lb.flange_ratio, 2)} | limit = {_fmt(lb.flange_limit, 2)}")
        else:
            st.info("Flange ratio not available in CSV.")

        st.write("**Web check** (both edges supported, web of I-sections):")
        st.latex(r"\frac{h}{w} \leq \frac{670}{\sqrt{F_y}}")
        if lb.web_ratio is not None:
            icon = "\u2705 PASS" if lb.web_ok else "\u274c FAIL"
            st.write(f"{icon} | h/w = {_fmt(lb.web_ratio, 2)} | limit = {_fmt(lb.web_limit, 2)}")
        else:
            st.info("Web ratio not available in CSV.")

        if R.is_class4:
            st.warning("Class 4 section \u2014 factored resistance requires reduced effective area per Clause 13.3.5. Full gross area used here as an upper bound.")
        else:
            st.success("Section satisfies Table 1 limits (not Class 4). Full gross area used.")

    elif sec.family == "HSS":
        if R.local_lambda is not None:
            lim = R.local_limit
            lam = R.local_lambda
            if sec.hss_kind == "CHS":
                st.latex(r"\frac{D}{t} \leq \frac{23000}{F_y}")
                st.write(f"D/t = {_fmt(lam, 2)} | limit = 23000/{_fmt(Fy, 0)} = {_fmt(lim, 2)}")
            else:
                st.latex(r"\frac{b_{flat}}{t} = \frac{b - 3t}{t} \leq \frac{670}{\sqrt{F_y}}")
                st.write(f"b_flat/t = {_fmt(lam, 2)} | limit = {_fmt(lim, 2)}")
            icon = "\u2705 PASS" if not R.is_class4 else "\u274c FAIL"
            st.write(f"{icon} | {R.local_label} | Ae = {_fmt(R.Ae_mm2, 0)} mm\u00b2")
        else:
            st.write(R.local_label)
    else:
        st.write("Local buckling check not applicable for this section type.")

    # Step 2
    st.subheader("Step 2 \u2014 Global Slenderness Ratio")
    if sec.family in ("ANGLE", "DOUBLE_ANGLE"):
        st.info(f"Single/Double Angle \u2014 modified KL/r per CSA S16 Cl 13.3.3: {R.angle_note}")
        st.write(f"Modified KL/r = {_fmt(R.KLr_gov, 1)}")
    else:
        st.latex(r"\left(\frac{KL}{r}\right)_x = \frac{K_x L_x}{r_x} \qquad \left(\frac{KL}{r}\right)_y = \frac{K_y L_y}{r_y}")
        st.write(f"(KL/r)x = ({_fmt(Kx, 2)} \u00d7 {_fmt(Lx, 0)}) / {_fmt(sec.rx_mm, 1)} = {_fmt(R.KLr_x, 1)}")
        st.write(f"(KL/r)y = ({_fmt(Ky, 2)} \u00d7 {_fmt(Ly, 0)}) / {_fmt(sec.ry_mm, 1)} = {_fmt(R.KLr_y, 1)}")
        st.write(f"Governing KL/r = {_fmt(R.KLr_gov, 1)}")

    if R.KLr_warn:
        st.warning(f"KL/r = {_fmt(R.KLr_gov, 1)} exceeds 200 \u2014 CSA S16 recommended maximum for compression members.")
    else:
        st.success(f"KL/r = {_fmt(R.KLr_gov, 1)} is within the limit of 200.")

    # Step 3
    st.subheader("Step 3 \u2014 Elastic Buckling Stresses")
    st.latex(r"F_{ex} = \frac{\pi^2 E}{(K_x L_x / r_x)^2} \qquad F_{ey} = \frac{\pi^2 E}{(K_y L_y / r_y)^2}")
    st.write(f"Fex = {_fmt(R.Fex_MPa, 1)} MPa")
    st.write(f"Fey = {_fmt(R.Fey_MPa, 1)} MPa")
    st.write(f"Min (flexural) Fe = {_fmt(R.Fe_flex_MPa, 1)} MPa")

    if sec.family in ("W", "WWF"):
        st.subheader("Step 3b \u2014 Torsional Buckling (Clause 13.3.2a)")
        if R.Fez_MPa is not None:
            st.latex(r"F_{ez} = \left[\frac{\pi^2 E C_w}{(K_z L_z)^2} + G J\right] \frac{1}{A \bar{r}_o^2}")
            KzLz    = Kz * Lz
            warping = (math.pi ** 2 * E * sec.Cw_mm6) / (KzLz ** 2) if sec.Cw_mm6 else 0
            stv     = G * sec.J_mm4 if sec.J_mm4 else 0
            denom   = sec.A_mm2 * sec.r_bar_o_sq if sec.r_bar_o_sq else 1
            st.write(f"Warping term = {_fmt(warping, 0)} N")
            st.write(f"St. Venant term G\u00b7J = {_fmt(stv, 0)} N")
            st.write(f"A\u00b7r\u0305o\u00b2 = {_fmt(denom, 0)} mm\u2074")
            st.write(f"Fez = {_fmt(R.Fez_MPa, 1)} MPa")
            if R.torsion_governs:
                st.warning(f"Torsional buckling governs: Fez = {_fmt(R.Fez_MPa, 1)} MPa < Fe_flex = {_fmt(R.Fe_flex_MPa, 1)} MPa")
            else:
                st.success(f"Flexural buckling governs: Fe_flex = {_fmt(R.Fe_flex_MPa, 1)} MPa \u2264 Fez = {_fmt(R.Fez_MPa, 1)} MPa")
        else:
            st.info("Torsional buckling not computed \u2014 J or Cw not available in CSV for this section.")

    st.write(f"**Governing Fe = {_fmt(R.Fe_gov_MPa, 1)} MPa**")

    # Step 4
    st.subheader("Step 4 \u2014 CSA S16 Column Curve (Clause 13.3.1)")
    st.latex(r"\lambda = \sqrt{\frac{F_y}{F_e}}")
    st.write(f"\u03bb = \u221a({_fmt(Fy, 0)} / {_fmt(R.Fe_gov_MPa, 1)}) = {_fmt(R.lam, 3)}")
    st.latex(r"F_{cr} = \frac{F_y}{(1 + \lambda^{2n})^{1/n}}")
    st.write(f"n = {_fmt(n_curve, 2)}")
    st.write(f"Fcr = {_fmt(Fy, 0)} / (1 + {_fmt(R.lam, 3)}^(2\u00d7{n_curve}))^(1/{n_curve}) = {_fmt(R.Fcr_MPa, 1)} MPa")

    # Step 5
    st.subheader("Step 5 \u2014 Factored Compressive Resistance")
    st.latex(r"C_r = \phi_c \, A_e \, F_{cr}")
    st.write(f"Cr = {phi_c} \u00d7 {_fmt(R.Ae_mm2, 0)} mm\u00b2 \u00d7 {_fmt(R.Fcr_MPa, 1)} MPa / 1000")
    st.write(f"**Cr = {_fmt(R.Cr_kN, 1)} kN**")

    # Step 6
    st.subheader("Step 6 \u2014 Demand / Capacity Check")
    if Pu_kN is None:
        st.write("No factored load (Pu) provided.")
    else:
        util = Pu_kN / R.Cr_kN if R.Cr_kN > 0 else float("inf")
        st.latex(r"U = \frac{P_u}{C_r} \leq 1.0")
        st.write(f"U = {_fmt(Pu_kN, 1)} / {_fmt(R.Cr_kN, 1)} = {_fmt(util, 3)}")
        if util <= 1.0:
            st.success(f"\u2705 PASS \u2014 Pu/Cr = {util:.3f}")
        else:
            st.error(f"\u274c FAIL \u2014 Pu/Cr = {util:.3f} > 1.00")

# ─────────────────────────────────────────────────────────────
# STREAMLIT UI
# ─────────────────────────────────────────────────────────────

apply_theme()
render_sidebar_logo()
render_footer()
if not st.session_state.get("accepted_disclaimer", False):
    st.error("Access restricted. Please open the Home page and accept the User Access Agreement before continuing.")
    st.stop()
st.title("CSA S16 — Compression Member Design Check")
st.markdown("*Structural steel column capacity per CSA S16:19 — Clauses 11, 13.3.1, 13.3.2, 13.3.3*")

shapes, designations = load_shapes()
if not shapes or not designations:
    st.error("No CSV section tables found in `data/` directory.")
    st.stop()

# ── Material & curve in sidebar ───────────────────────────────
with st.sidebar:
    st.header("Material")
    Fy    = st.number_input("Fy (MPa)", 200.0, 700.0, 350.0, 5.0, key="comp_Fy")
    E     = st.number_input("E (MPa)", 150000.0, 250000.0, 200000.0, 1000.0, key="comp_E")
    G_MPa = st.number_input("G (MPa)", 50000.0, 100000.0, 77000.0, 1000.0, key="comp_G")
    phi_c = st.number_input("\u03c6c", 0.5, 1.0, 0.9, 0.05, key="comp_phi")

    st.divider()
    st.header("Column Curve")
    n_auto = st.checkbox("Auto-select n based on section type", value=True, key="comp_n_auto")
    if not n_auto:
        n_curve = st.number_input("n", 0.8, 2.5, 1.34, 0.01, key="comp_n")
    else:
        n_curve = 1.34

# ── Section selection — on-page 3-column row ─────────────────
st.subheader("1. Section Selection")
sel_col1, sel_col2, sel_col3 = st.columns([1, 1.2, 2])

with sel_col1:
    family_filter = st.selectbox(
        "Section family",
        ["All", "W", "WWF", "HSS Rectangular/Square", "HSS Circular", "Angle"],
        key="comp_family_filter",
    )

with sel_col2:
    search = st.text_input("Search", placeholder="e.g. W250, HSS 203", key="comp_search")

def _matches_family(des: str) -> bool:
    fam = section_family(des)
    if family_filter == "All":
        return fam in ("W", "WWF", "HSS", "ANGLE", "DOUBLE_ANGLE")
    if family_filter == "W":
        return fam == "W"
    if family_filter == "WWF":
        return fam == "WWF"
    if family_filter == "HSS Rectangular/Square":
        return fam == "HSS" and hss_type(des) == "RHS/SHS"
    if family_filter == "HSS Circular":
        return fam == "HSS" and hss_type(des) == "CHS"
    if family_filter == "Angle":
        return fam in ("ANGLE", "DOUBLE_ANGLE")
    return True

filtered = [d for d in designations if _matches_family(d) and (not search or search.lower() in d.lower())]

with sel_col3:
    if not filtered:
        st.warning("No sections match. Try clearing the search or choosing 'All'.")
        st.stop()
    sec_name = st.selectbox("Designation", filtered, index=0, key="comp_sec")

try:
    sec = build_section(sec_name, shapes[sec_name])
except Exception as e:
    st.error(f"Could not load section '{sec_name}': {e}")
    st.stop()

# Auto n
n_note = ""
if n_auto:
    if sec.family == "WWF":
        n_curve = 2.24
        n_note  = "n = 2.24 \u2014 WWF (doubly symmetric welded, flame-cut flanges, Cl 13.3.1)"
    elif sec.family == "HSS" and sec.hss_kind == "CHS":
        n_curve = 1.34
        n_note  = "n = 1.34 \u2014 CHS (CSA G40.20 Class C)"
    else:
        n_curve = 1.34
        n_note  = "n = 1.34 \u2014 W-shapes, HSS Class C, hot-rolled sections (Cl 13.3.1)"
    st.sidebar.caption(n_note)

# Input columns
st.markdown("---")
col_a, col_b, col_c = st.columns([1.2, 1.2, 1])

with col_a:
    st.subheader("Effective Length Factors & Unbraced Lengths")
    sub1, sub2 = st.columns(2)
    with sub1:
        Kx   = st.number_input("Kx", 0.1, 5.0, 1.0, 0.05, key="comp_kx")
        Ky   = st.number_input("Ky", 0.1, 5.0, 1.0, 0.05, key="comp_ky")
        Kz   = st.number_input("Kz (torsional)", 0.1, 2.0, 1.0, 0.05, key="comp_kz")
    with sub2:
        Lx_m = st.number_input("Lx (m)", 0.1, 50.0, 3.0, 0.5, key="comp_lx")
        Ly_m = st.number_input("Ly (m)", 0.1, 50.0, 3.0, 0.5, key="comp_ly")
        Lz_m = st.number_input("Lz (m)", 0.1, 50.0, 3.0, 0.5, key="comp_lz")

with col_b:
    st.subheader("Section Properties")
    _dash = "\u2014"
    _p_d  = _fmt(sec.d_mm, 1)  if sec.d_mm  else _dash
    _p_b  = _fmt(sec.b_mm, 1)  if sec.b_mm  else _dash
    _p_t  = _fmt(sec.t_mm, 1)  if sec.t_mm  else _dash
    _p_w  = _fmt(sec.w_mm, 1)  if sec.w_mm  else _dash
    _p_cl = str(sec.section_class) if sec.section_class else _dash
    _p_J  = _fmt(sec.J_mm4 / 1e3, 0) if sec.J_mm4  else _dash
    _p_Cw = _fmt(sec.Cw_mm6 / 1e9, 1) if sec.Cw_mm6 else _dash
    props_md = (
        "| Property | Value |\n"
        "|----------|-------|\n"
        f"| Family   | `{sec.family}` |\n"
        f"| A        | `{_fmt(sec.A_mm2, 0)}` mm\u00b2 |\n"
        f"| rx       | `{_fmt(sec.rx_mm, 1)}` mm |\n"
        f"| ry       | `{_fmt(sec.ry_mm, 1)}` mm |\n"
        f"| d        | `{_p_d}` mm |\n"
        f"| b        | `{_p_b}` mm |\n"
        f"| tf       | `{_p_t}` mm |\n"
        f"| tw       | `{_p_w}` mm |\n"
        f"| Class    | `{_p_cl}` |\n"
        f"| J        | `{_p_J}` \u00d710\u00b3 mm\u2074 |\n"
        f"| Cw       | `{_p_Cw}` \u00d710\u2079 mm\u2076 |\n"
    )
    st.markdown(props_md)

with col_c:
    st.subheader("Demand Check")
    check_demand = st.checkbox("Apply factored load Pu", value=False, key="comp_demand_cb")
    Pu_kN_val = None
    if check_demand:
        Pu_kN_val = st.number_input("Pu (kN)", 0.0, 1e7, 500.0, 50.0, key="comp_Pu")

    if sec.family in ("ANGLE", "DOUBLE_ANGLE"):
        st.subheader("Angle Options (Cl 13.3.3)")
        angle_truss = st.selectbox("Truss type", ["Individual/Planar", "Box/Space"], key="comp_angle_truss")
        angle_truss_type = "box" if "Box" in angle_truss else "individual"
        angle_unequal = st.checkbox("Unequal legs?", value=False, key="comp_angle_unequal")
        angle_bl = angle_bs = None
        angle_short_leg = False
        if angle_unequal:
            angle_bl = st.number_input("Longer leg bl (mm)", 20.0, 500.0, 89.0, 1.0, key="comp_bl")
            angle_bs = st.number_input("Shorter leg bs (mm)", 20.0, 500.0, 64.0, 1.0, key="comp_bs")
            angle_short_leg = st.checkbox("Connected through shorter leg?", key="comp_short_leg")
    else:
        angle_truss_type = "individual"
        angle_bl = angle_bs = None
        angle_short_leg = False

# Run check
params = dict(
    Fy=Fy, E=E, G=G_MPa, phi_c=phi_c, n_curve=n_curve,
    Kx=Kx, Ky=Ky, Kz=Kz,
    Lx_mm=Lx_m * 1000, Ly_mm=Ly_m * 1000, Lz_mm=Lz_m * 1000,
)

try:
    R = run_compression_check(
        sec=sec, **params,
        angle_truss_type=angle_truss_type,
        angle_bl=angle_bl, angle_bs=angle_bs, angle_short_leg=angle_short_leg,
    )
except Exception as e:
    st.error(f"Calculation error: {e}")
    st.stop()

# Results summary
st.markdown("---")
st.subheader("Results Summary")
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Cr (kN)", f"{R.Cr_kN:,.1f}")
with m2:
    st.metric("Gov. KL/r", f"{R.KLr_gov:.1f}", delta="\u26a0\ufe0f >200" if R.KLr_warn else None, delta_color="inverse")
with m3:
    st.metric("\u03bb", f"{R.lam:.3f}")
with m4:
    st.metric("Fcr (MPa)", f"{R.Fcr_MPa:.1f}")

if R.KLr_warn:
    st.warning(f"\u26a0\ufe0f KL/r = {R.KLr_gov:.1f} exceeds the CSA S16 recommended limit of 200 for compression members.")
if R.is_class4:
    st.warning("\u26a0\ufe0f Class 4 section detected \u2014 full gross area shown. Reduce Ae per Clause 13.3.5 for final design.")
if R.torsion_governs:
    st.warning(f"\u26a0\ufe0f Torsional buckling governs: Fez = {R.Fez_MPa:.1f} MPa (Clause 13.3.2a)")
if Pu_kN_val is not None:
    util = Pu_kN_val / R.Cr_kN if R.Cr_kN > 0 else float("inf")
    if util <= 1.0:
        st.success(f"\u2705 PASS \u2014 Pu/Cr = {util:.3f}")
    else:
        st.error(f"\u274c FAIL \u2014 Pu/Cr = {util:.3f} > 1.00")

# Detailed report in tabs
st.markdown("---")
tab1, tab2, tab3 = st.tabs(["📋 Step-by-Step Report", "📊 Column Curve", "🗃️ Raw CSV Record"])

with tab1:
    render_report(sec, params, R, Pu_kN_val)

with tab2:
    import numpy as np
    import pandas as pd
    st.subheader("Factored Compressive Resistance vs Effective Length")
    KLr_range = np.linspace(1, 250, 300)
    Cr_vals = []
    for klr in KLr_range:
        Fe_  = euler_Fe(E, klr)
        lam_ = math.sqrt(Fy / Fe_)
        Fcr_ = csa_Fcr(Fy, lam_, n_curve)
        Cr_  = phi_c * sec.A_mm2 * Fcr_ / 1000
        Cr_vals.append(Cr_)
    df_plot = pd.DataFrame({"KL/r": KLr_range, "Cr (kN)": Cr_vals})
    st.line_chart(df_plot.set_index("KL/r"), color=["#58a6ff"])
    st.markdown(f"**Current point:** KL/r = `{R.KLr_gov:.1f}` \u2192 Cr = `{R.Cr_kN:.1f}` kN")
    st.caption(f"n = {n_curve}, Fy = {Fy} MPa, A = {sec.A_mm2:,.0f} mm\u00b2")

with tab3:
    st.json(shapes[sec_name])
