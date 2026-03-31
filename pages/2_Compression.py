from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# ============================================================
# CONFIG
# ============================================================

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ============================================================
# UTIL: NORMALIZE + PICK
# ============================================================

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
    if not s:
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

# ============================================================
# CSV LOADING (all CSVs in /data)
# ============================================================

CANON = {
    "designation": ["designation", "Designation", "section", "Section", "shape", "name"],
    "d": ["d", "D", "depth", "Depth (mm)", "Depth_mm", "OD (mm)", "OD",
          "Outside Diameter (mm)", "Outside Dimension (mm)"],
    "b": ["b", "B", "width", "Width (mm)", "Width_mm", "bf", "flange_width"],
    "t": ["t", "T", "thickness", "Wall Thickness (mm)", "Wall_Thickness_mm", "wall_thickness"],
    "A": ["Area", "area", "A", "Area (mm2)", "Area (mm²)", "Area_mm2", "Area (mm^2)"],
    "rx": ["rx", "rx (mm)", "rx_mm", "r_x", "r (mm)", "r"],
    "ry": ["ry", "ry (mm)", "ry_mm", "r_y"],
}

def _canonicalize(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)

    des = _pick(rec, CANON["designation"])
    if des is not None:
        out["designation"] = str(des).strip()

    for k in ("d", "b", "t", "A", "rx", "ry"):
        v = _pick(rec, CANON[k])
        if v is not None:
            out[k] = v

    return out

@st.cache_data(ttl=120)
def load_shapes() -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    shapes: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    if not DATA_DIR.exists():
        return {}, []

    for p in sorted(DATA_DIR.glob("*.csv"), key=lambda x: x.name.lower()):
        # robust encoding: utf-8 first, fallback latin-1
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
                if not des:
                    continue
                shapes[des] = r2
                order.append(des)

    # de-dupe while keeping first-seen order
    seen: set[str] = set()
    order2: List[str] = []
    for k in order:
        if k not in seen:
            seen.add(k)
            order2.append(k)

    return shapes, order2

# ============================================================
# HSS DESIGNATION PARSER (for robust type/dims)
# ============================================================

def parse_hss_designation(des: str) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
    """
    Returns (d_mm, b_mm, t_mm, hss_type)
      - RHS/SHS: HSS 305x203x9.5  -> (d=305, b=203, t=9.5, 'RHS/SHS')
      - CHS:     HSS 273x12.7     -> (d=273, b=None, t=12.7, 'CHS')
    """
    s = des.upper().replace("HSS", "").strip()
    s = s.replace("×", "X").replace("x", "X").replace(" ", "")
    parts = s.split("X")

    nums: List[float] = []
    for p in parts:
        try:
            nums.append(float(p))
        except Exception:
            pass

    if len(nums) >= 3:
        d, b, t = nums[0], nums[1], nums[2]
        return d, b, t, "RHS/SHS"
    if len(nums) == 2:
        d, t = nums[0], nums[1]
        return d, None, t, "CHS"
    return None, None, None, "UNKNOWN"

def section_family(des: str) -> str:
    n = des.strip().upper()
    if n.startswith("W"):
        return "W"
    if "HSS" in n:
        return "HSS"
    return "OTHER"

def hss_type(des: str) -> str:
    _, _, _, typ = parse_hss_designation(des)
    return typ

# ============================================================
# SECTION MODEL
# ============================================================

@dataclass(frozen=True)
class SectionProps:
    designation: str
    family: str
    A_mm2: float
    rx_mm: float
    ry_mm: float
    d_mm: Optional[float] = None
    b_mm: Optional[float] = None
    t_mm: Optional[float] = None
    hss_kind: Optional[str] = None

def build_section(designation: str, rec: Dict[str, Any]) -> SectionProps:
    A = _to_float(rec.get("A")) or _to_float(rec.get("Area")) or _to_float(rec.get("A_mm2"))
    rx = _to_float(rec.get("rx"))
    ry = _to_float(rec.get("ry"))

    if A is None or rx is None or ry is None:
        raise ValueError(f"Missing A/rx/ry for {designation}. Check CSV headers/values.")

    fam = section_family(designation)

    d = _to_float(rec.get("d"))
    b = _to_float(rec.get("b"))
    t = _to_float(rec.get("t"))

    kind = None
    if fam == "HSS":
        pd, pb, pt, kind = parse_hss_designation(designation)
        if d is None and pd is not None:
            d = pd
        if b is None and pb is not None:
            b = pb
        if t is None and pt is not None:
            t = pt

    return SectionProps(
        designation=designation,
        family=fam,
        A_mm2=float(A),
        rx_mm=float(rx),
        ry_mm=float(ry),
        d_mm=d,
        b_mm=b,
        t_mm=t,
        hss_kind=kind,
    )

# ============================================================
# CSA COMPRESSION ENGINE
# ============================================================

def effective_area_hss(sec: SectionProps, Fy_MPa: float) -> Tuple[float, str, Optional[float], Optional[float]]:
    """
    Local buckling reduction for HSS only (simplified):
      - RHS/SHS: (b-3t)/t <= 670/sqrt(Fy)
      - CHS: D/t <= 23000/Fy
    Returns (Ae_mm2, label, lambda_local, limit)
    """
    if sec.family != "HSS":
        return sec.A_mm2, "N/A (not HSS)", None, None

    if sec.t_mm is None or sec.t_mm <= 0:
        return sec.A_mm2, "HSS (t missing)", None, None

    t = float(sec.t_mm)

    # Circular
    if sec.hss_kind == "CHS" and sec.d_mm is not None:
        lam = float(sec.d_mm) / t
        limit = 23000.0 / float(Fy_MPa)
        if lam <= limit:
            return sec.A_mm2, "CHS non-slender", lam, limit
        Ae = sec.A_mm2 * (limit / lam)
        return Ae, "CHS slender", lam, limit

    # Rect/Square (use b-flat)
    if sec.hss_kind == "RHS/SHS" and sec.b_mm is not None:
        bflat = float(sec.b_mm) - 3.0 * t
        lam = bflat / t
        limit = 670.0 / math.sqrt(float(Fy_MPa))
        if lam <= limit:
            return sec.A_mm2, "HSS non-slender", lam, limit
        Ae = sec.A_mm2 * (limit / lam)
        return Ae, "HSS slender", lam, limit

    return sec.A_mm2, "HSS (unknown kind)", None, None

def euler_Fe(E_MPa: float, KL_over_r: float) -> float:
    return (math.pi ** 2) * float(E_MPa) / (float(KL_over_r) ** 2)

def csa_lambda(KL_over_r: float, Fy_MPa: float, E_MPa: float) -> float:
    return float(KL_over_r) * math.sqrt(float(Fy_MPa) / ((math.pi ** 2) * float(E_MPa)))

def csa_Fcr(Fy_MPa: float, E_MPa: float, KL_over_r: float, n: float) -> float:
    lam = csa_lambda(KL_over_r, Fy_MPa, E_MPa)
    return float(Fy_MPa) / ((1.0 + (lam ** (2.0 * float(n)))) ** (1.0 / float(n)))

def compression_check(
    sec: SectionProps,
    Fy: float,
    E: float,
    phi_c: float,
    n: float,
    Kx: float,
    Ky: float,
    Lx_mm: float,
    Ly_mm: float,
) -> Dict[str, Any]:
    Ae, local_label, lam_local, lim_local = effective_area_hss(sec, Fy)

    KLr_x = (float(Kx) * float(Lx_mm)) / float(sec.rx_mm)
    KLr_y = (float(Ky) * float(Ly_mm)) / float(sec.ry_mm)
    KLr = min(KLr_x, KLr_y)

    Fe = euler_Fe(E, KLr)
    lam = csa_lambda(KLr, Fy, E)
    Fcr = csa_Fcr(Fy, E, KLr, n)

    Cr_N = float(phi_c) * float(Ae) * float(Fcr)
    Cr_kN = Cr_N / 1000.0

    return {
        "Ae_mm2": Ae,
        "local_label": local_label,
        "local_lambda": lam_local,
        "local_limit": lim_local,
        "KLr_x": KLr_x,
        "KLr_y": KLr_y,
        "KLr_gov": KLr,
        "Fe_MPa": Fe,
        "lambda": lam,
        "Fcr_MPa": Fcr,
        "Cr_kN": Cr_kN,
    }

# ============================================================
# REPORT RENDERER (helpers)
# ============================================================

def _fmt(x: Any, nd: int = 3) -> str:
    if x is None:
        return "—"
    try:
        xf = float(x)
        if abs(xf) >= 1000:
            return f"{xf:,.{nd}f}"
        return f"{xf:.{nd}f}"
    except Exception:
        return str(x)

def render_calculation_report(
    sec: SectionProps,
    Fy: float,
    E: float,
    phi_c: float,
    n_curve: float,
    Kx: float,
    Ky: float,
    Lx_mm: float,
    Ly_mm: float,
    out: Dict[str, Any],
    Pu_kN: Optional[float],
) -> None:
    st.subheader("Calculation Report (Step-by-step)")

    st.markdown("### Step 0 — Inputs")
    st.markdown(
        f"- Section = **{sec.designation}** | Family = `{sec.family}`\n"
        f"- Fy = **{_fmt(Fy,1)} MPa**, E = **{_fmt(E,0)} MPa**\n"
        f"- phi_c = **{_fmt(phi_c,2)}**, n = **{_fmt(n_curve,2)}**\n"
        f"- Kx = **{_fmt(Kx,2)}**, Ky = **{_fmt(Ky,2)}**\n"
        f"- Lx = **{_fmt(Lx_mm,1)} mm**, Ly = **{_fmt(Ly_mm,1)} mm**\n"
        f"- A = **{_fmt(sec.A_mm2,0)} mm^2**, rx = **{_fmt(sec.rx_mm,1)} mm**, ry = **{_fmt(sec.ry_mm,1)} mm**"
    )

    st.markdown("### Step 1 — Local Buckling / Slenderness (HSS only)")
    if sec.family != "HSS" or out.get("local_lambda") is None:
        st.write("Not applicable (non-HSS) or insufficient geometry.")
    else:
        lam_local = float(out["local_lambda"])
        lim_local = float(out["local_limit"])
        Ae = float(out["Ae_mm2"])

        if sec.hss_kind == "CHS":
            st.latex(r"\lambda_{local}=\dfrac{D}{t}\quad;\quad \text{limit}=\dfrac{23000}{F_y}")
            st.markdown(
                f"- lambda_local = D/t = **{_fmt(lam_local,2)}**\n"
                f"- limit = 23000/Fy = **{_fmt(lim_local,2)}**\n"
                f"- Result: **{out['local_label']}**\n"
                f"- Effective area used: **Ae = {_fmt(Ae,0)} mm^2**"
            )
        else:
            st.latex(r"\lambda_{local}=\dfrac{b_{flat}}{t}\quad;\quad b_{flat}=b-3t\quad;\quad \text{limit}=\dfrac{670}{\sqrt{F_y}}")
            st.markdown(
                f"- lambda_local = (b-3t)/t = **{_fmt(lam_local,2)}**\n"
                f"- limit = 670/sqrt(Fy) = **{_fmt(lim_local,2)}**\n"
                f"- Result: **{out['local_label']}**\n"
                f"- Effective area used: **Ae = {_fmt(Ae,0)} mm^2**"
            )

    st.markdown("### Step 2 — Global Slenderness")
    KLr_x = float(out["KLr_x"])
    KLr_y = float(out["KLr_y"])
    KLr_g = float(out["KLr_gov"])
    st.latex(r"\left(\dfrac{KL}{r}\right)_x=\dfrac{K_x L_x}{r_x}\quad,\quad \left(\dfrac{KL}{r}\right)_y=\dfrac{K_y L_y}{r_y}\quad,\quad \left(\dfrac{KL}{r}\right)_{gov}=\min(\cdot)")
    st.markdown(
        f"- (KL/r)x = ({_fmt(Kx,2)}*{_fmt(Lx_mm,1)})/{_fmt(sec.rx_mm,1)} = **{_fmt(KLr_x,1)}**\n"
        f"- (KL/r)y = ({_fmt(Ky,2)}*{_fmt(Ly_mm,1)})/{_fmt(sec.ry_mm,1)} = **{_fmt(KLr_y,1)}**\n"
        f"- Governing KL/r = **{_fmt(KLr_g,1)}**"
    )

    st.markdown("### Step 3 — Euler Elastic Buckling Stress")
    Fe = float(out["Fe_MPa"])
    st.latex(r"F_e=\dfrac{\pi^2 E}{\left(\dfrac{KL}{r}\right)^2}")
    st.markdown(f"- Fe = **{_fmt(Fe,1)} MPa**")

    st.markdown("### Step 4 — CSA Column Curve")
    lam = float(out["lambda"])
    Fcr = float(out["Fcr_MPa"])
    st.latex(r"\lambda=\sqrt{\dfrac{F_y}{F_e}}")
    st.markdown(f"- lambda = **{_fmt(lam,3)}**")
    st.latex(r"F_{cr}=\dfrac{F_y}{\left(1+\lambda^{2n}\right)^{1/n}}")
    st.markdown(f"- Fcr = **{_fmt(Fcr,1)} MPa**")

    st.markdown("### Step 5 — Factored Compressive Resistance")
    Ae = float(out["Ae_mm2"])
    Cr_kN = float(out["Cr_kN"])
    st.latex(r"C_r=\phi_c\,A_e\,F_{cr}")
    st.markdown(f"- Cr = **{_fmt(Cr_kN,1)} kN**")

    st.markdown("### Step 6 — Demand / Capacity (optional)")
    if Pu_kN is None:
        st.write("Pu check not enabled.")
    else:
        util = float(Pu_kN) / Cr_kN if Cr_kN > 0 else float("inf")
        st.latex(r"U=\dfrac{P_u}{C_r}")
        st.markdown(f"- U = Pu/Cr = **{_fmt(util,3)}**")
        if util <= 1.0:
            st.success(f"PASS — Pu/Cr = {util:.2f} <= 1.00")
        else:
            st.error(f"FAIL — Pu/Cr = {util:.2f} > 1.00")

# ============================================================
# STREAMLIT UI
# ============================================================

st.title("CSA S16 Compression Check")

shapes, designations = load_shapes()
if not shapes or not designations:
    st.error("No CSV shapes found in data/. Put your CISC CSVs in the app's data/ folder.")
    st.stop()

st.subheader("Section Type")

family = st.selectbox(
    "Choose section family",
    ["All", "W", "HSS Rectangular/Square", "HSS Circular"],
    index=0,
    key="family_filter",
)

search = st.text_input("Search", placeholder="e.g., W250 or HSS 203", key="search_box")

def matches_family(des: str) -> bool:
    fam = section_family(des)
    if family == "All":
        return fam in ("W", "HSS")
    if family == "W":
        return fam == "W"
    if family == "HSS Rectangular/Square":
        return fam == "HSS" and hss_type(des) == "RHS/SHS"
    if family == "HSS Circular":
        return fam == "HSS" and hss_type(des) == "CHS"
    return True

filtered: List[str] = []
for d in designations:
    if not matches_family(d):
        continue
    if search and search.strip().lower() not in d.lower():
        continue
    filtered.append(d)

if not filtered:
    st.warning("No sections match your filter/search. Try 'All' and clear search.")
    st.stop()

sec_name = st.selectbox("Section", filtered, key="section_select")

try:
    sec = build_section(sec_name, shapes[sec_name])
except Exception as e:
    st.error(f"Failed to build section '{sec_name}': {e}")
    st.stop()

c1, c2, c3 = st.columns([1.2, 1, 1])

with c1:
    st.subheader("Material")
    Fy = st.number_input("Fy (MPa)", min_value=200.0, max_value=700.0, value=350.0, step=5.0)
    E = st.number_input("E (MPa)", min_value=100000.0, max_value=300000.0, value=200000.0, step=1000.0)
    phi_c = st.number_input("phi_c", min_value=0.5, max_value=1.0, value=0.9, step=0.05)
    n_curve = st.number_input("n (curve)", min_value=0.8, max_value=2.5, value=1.34, step=0.01)

with c2:
    st.subheader("Effective Lengths")
    Kx = st.number_input("Kx", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
    Lx_m = st.number_input("Lx (m)", min_value=0.1, max_value=50.0, value=3.0, step=0.5)
    Ky = st.number_input("Ky", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
    Ly_m = st.number_input("Ly (m)", min_value=0.1, max_value=50.0, value=3.0, step=0.5)

with c3:
    st.subheader("Demand")
    check_demand = st.checkbox("Check Pu", value=False)
    Pu = st.number_input("Pu (kN)", min_value=0.0, value=500.0, step=50.0) if check_demand else None

st.divider()

# --- Compute (ONLY compute here)
out = compression_check(
    sec=sec,
    Fy=float(Fy),
    E=float(E),
    phi_c=float(phi_c),
    n=float(n_curve),
    Kx=float(Kx),
    Ky=float(Ky),
    Lx_mm=float(Lx_m) * 1000.0,
    Ly_mm=float(Ly_m) * 1000.0,
)

# --- Report (RIGHT AFTER out exists; NOT INSIDE compression_check)
render_calculation_report(
    sec=sec,
    Fy=float(Fy),
    E=float(E),
    phi_c=float(phi_c),
    n_curve=float(n_curve),
    Kx=float(Kx),
    Ky=float(Ky),
    Lx_mm=float(Lx_m) * 1000.0,
    Ly_mm=float(Ly_m) * 1000.0,
    out=out,
    Pu_kN=float(Pu) if (check_demand and Pu is not None) else None,
)

st.divider()

# --- Results
st.subheader("Results")

r1, r2 = st.columns(2)
with r1:
    st.markdown(f"**Section:** {sec.designation}")
    st.markdown(f"- Family: `{sec.family}`")
    st.markdown(f"- A = {sec.A_mm2:,.0f} mm^2")
    st.markdown(f"- rx = {sec.rx_mm:.1f} mm, ry = {sec.ry_mm:.1f} mm")
    if sec.family == "HSS":
        st.markdown(f"- HSS kind: `{sec.hss_kind}`")
        st.markdown(f"- d = {sec.d_mm if sec.d_mm else '—'} mm, b = {sec.b_mm if sec.b_mm else '—'} mm, t = {sec.t_mm if sec.t_mm else '—'} mm")

with r2:
    st.metric("Factored Compression Resistance (Cr)", f"{out['Cr_kN']:,.1f} kN")
    st.caption(f"Local: {out['local_label']} | phi_c={phi_c}, n={n_curve}")

st.divider()

st.subheader("Buckling Details")
b1, b2, b3 = st.columns(3)

with b1:
    st.markdown("**Local (HSS only)**")
    if out["local_lambda"] is None:
        st.write("N/A")
    else:
        st.write(f"lambda_local = {out['local_lambda']:.2f}")
        st.write(f"limit = {out['local_limit']:.2f}")

with b2:
    st.markdown("**Slenderness**")
    st.write(f"KL/r (x) = {out['KLr_x']:.1f}")
    st.write(f"KL/r (y) = {out['KLr_y']:.1f}")
    st.write(f"Gov. KL/r = {out['KLr_gov']:.1f}")

with b3:
    st.markdown("**Stresses**")
    st.write(f"Fe = {out['Fe_MPa']:.1f} MPa")
    st.write(f"lambda = {out['lambda']:.3f}")
    st.write(f"Fcr = {out['Fcr_MPa']:.1f} MPa")

if check_demand and Pu is not None:
    st.divider()
    util = float(Pu) / float(out["Cr_kN"]) if out["Cr_kN"] > 0 else float("inf")
    if util <= 1.0:
        st.success(f"PASS — Pu/Cr = {util:.2f}")
    else:
        st.error(f"FAIL — Pu/Cr = {util:.2f}")

with st.expander("Raw CSV Record"):
    st.json(shapes[sec_name])