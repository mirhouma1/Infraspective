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
    except:
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
    "d": ["d", "D", "depth", "Depth (mm)", "Depth_mm", "OD (mm)", "OD", "Outside Diameter (mm)", "Outside Dimension (mm)"],
    "b": ["b", "B", "width", "Width (mm)", "Width_mm", "bf", "flange_width"],
    "t": ["t", "T", "thickness", "Wall Thickness (mm)", "Wall_Thickness_mm", "wall_thickness"],
    "A": ["Area", "area", "A", "Area (mm2)", "Area (mm²)", "Area_mm2"],
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

    # de-dupe keep order
    seen = set()
    order2 = []
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
    Heuristic: count of 'x' in the dimension string:
      - >=2 => rectangular/square
      - ==1 => circular
    """
    s = des.upper().replace("HSS", "").strip()
    s = s.replace("×", "X").replace("x", "X").replace(" ", "")
    parts = s.split("X")
    nums = []
    for p in parts:
        try:
            nums.append(float(p))
        except:
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
    d, b, t, typ = parse_hss_designation(des)
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
    # Optional geometry for HSS local buckling
    d_mm: Optional[float] = None
    b_mm: Optional[float] = None
    t_mm: Optional[float] = None
    hss_kind: Optional[str] = None

def build_section(designation: str, rec: Dict[str, Any]) -> SectionProps:
    A = _to_float(rec.get("A")) or _to_float(rec.get("Area")) or _to_float(rec.get("A_mm2"))
    rx = _to_float(rec.get("rx"))
    ry = _to_float(rec.get("ry"))

    if A is None or rx is None or ry is None:
        raise ValueError(f"Missing A/rx/ry for {designation}. Check CSV headers / values.")

    fam = section_family(designation)

    d = _to_float(rec.get("d"))
    b = _to_float(rec.get("b"))
    t = _to_float(rec.get("t"))

    # If geometry missing, try parse from designation for HSS
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
# CSA COMPRESSION ENGINE (DOUBLY SYMMETRIC / AXISYMMETRIC ONLY)
# ============================================================

def effective_area_hss(sec: SectionProps, Fy_MPa: float) -> Tuple[float, str, Optional[float], Optional[float]]:
    """
    Local buckling reduction for HSS only (simplified):
      - RHS/SHS: (b-3t)/t <= 670/sqrt(Fy)
      - CHS: D/t <= 23000/Fy
    Returns (Ae_mm2, label, lambda, limit)
    """
    if sec.family != "HSS":
        return sec.A_mm2, "N/A (not HSS)", None, None

    if not sec.t_mm or sec.t_mm <= 0:
        return sec.A_mm2, "HSS (t missing)", None, None

    t = sec.t_mm

    # Circular
    if sec.hss_kind == "CHS" and sec.d_mm:
        lam = sec.d_mm / t
        limit = 23000.0 / Fy_MPa
        if lam <= limit:
            return sec.A_mm2, "CHS non-slender", lam, limit
        Ae = sec.A_mm2 * (limit / lam)
        return Ae, "CHS slender", lam, limit

    # Rect/Square
    if sec.hss_kind == "RHS/SHS" and sec.b_mm:
        bflat = sec.b_mm - 3.0 * t
        lam = bflat / t
        limit = 670.0 / math.sqrt(Fy_MPa)
        if lam <= limit:
            return sec.A_mm2, "HSS non-slender", lam, limit
        Ae = sec.A_mm2 * (limit / lam)
        return Ae, "HSS slender", lam, limit

    return sec.A_mm2, "HSS (unknown kind)", None, None

def euler_Fe(E_MPa: float, KL_over_r: float) -> float:
    return (math.pi ** 2) * E_MPa / (KL_over_r ** 2)

def csa_lambda(KL_over_r: float, Fy_MPa: float, E_MPa: float) -> float:
    return KL_over_r * math.sqrt(Fy_MPa / ((math.pi ** 2) * E_MPa))

def csa_Fcr(Fy_MPa: float, E_MPa: float, KL_over_r: float, n: float) -> float:
    lam = csa_lambda(KL_over_r, Fy_MPa, E_MPa)
    return Fy_MPa / ((1.0 + (lam ** (2.0 * n))) ** (1.0 / n))

def compression_check(sec: SectionProps, Fy, E, phi_c, n, Kx, Ky, Lx_mm, Ly_mm) -> Dict[str, Any]:
    # Local buckling (HSS only)
    Ae, local_label, lam_local, lim_local = effective_area_hss(sec, Fy)

    # Global buckling
    KLr_x = (Kx * Lx_mm) / sec.rx_mm
    KLr_y = (Ky * Ly_mm) / sec.ry_mm
    KLr = min(KLr_x, KLr_y)

    Fe = euler_Fe(E, KLr)
    lam = csa_lambda(KLr, Fy, E)
    Fcr = csa_Fcr(Fy, E, KLr, n)

    Cr_N = phi_c * Ae * Fcr
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
# STREAMLIT UI
# ============================================================

st.title("CSA S16 Compression Check")

shapes, designations = load_shapes()
if not shapes or not designations:
    st.error("No CSV shapes found in data/. Put your CISC CSVs in the app's data/ folder.")
    st.stop()

# --- Filter UI
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

filtered = []
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

# Build section props (safe)
try:
    sec = build_section(sec_name, shapes[sec_name])
except Exception as e:
    st.error(f"Failed to build section '{sec_name}': {e}")
    st.stop()

# --- Inputs
c1, c2, c3 = st.columns([1.2, 1, 1])

with c1:
    st.subheader("Material")
    Fy = st.number_input("Fy (MPa)", min_value=200.0, max_value=700.0, value=350.0, step=5.0)
    E = st.number_input("E (MPa)", min_value=100000.0, max_value=300000.0, value=200000.0, step=1000.0)
    phi_c = st.number_input("φc", min_value=0.5, max_value=1.0, value=0.9, step=0.05)
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

# --- Compute
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

# --- Results
st.subheader("Results")

r1, r2 = st.columns(2)
with r1:
    st.markdown(f"**Section:** {sec.designation}")
    st.markdown(f"- Family: `{sec.family}`")
    st.markdown(f"- A = {sec.A_mm2:,.0f} mm²")
    st.markdown(f"- rx = {sec.rx_mm:.1f} mm, ry = {sec.ry_mm:.1f} mm")
    if sec.family == "HSS":
        st.markdown(f"- HSS kind: `{sec.hss_kind}`")
        st.markdown(f"- d = {sec.d_mm if sec.d_mm else '—'} mm, b = {sec.b_mm if sec.b_mm else '—'} mm, t = {sec.t_mm if sec.t_mm else '—'} mm")

with r2:
    st.metric("Factored Compression Resistance (Cr)", f"{out['Cr_kN']:,.1f} kN")
    st.caption(f"Local: {out['local_label']} | φc={phi_c}, n={n_curve}")

st.divider()

st.subheader("Buckling Details")
b1, b2, b3 = st.columns(3)

with b1:
    st.markdown("**Local (HSS only)**")
    if out["local_lambda"] is None:
        st.write("N/A")
    else:
        st.write(f"λ_local = {out['local_lambda']:.2f}")
        st.write(f"limit = {out['local_limit']:.2f}")

with b2:
    st.markdown("**Slenderness**")
    st.write(f"KL/r (x) = {out['KLr_x']:.1f}")
    st.write(f"KL/r (y) = {out['KLr_y']:.1f}")
    st.write(f"Gov. KL/r = {out['KLr_gov']:.1f}")

with b3:
    st.markdown("**Stresses**")
    st.write(f"Fe = {out['Fe_MPa']:.1f} MPa")
    st.write(f"λ = {out['lambda']:.3f}")
    st.write(f"Fcr = {out['Fcr_MPa']:.1f} MPa")

if check_demand and Pu is not None:
    st.divider()
    util = float(Pu) / float(out["Cr_kN"]) if out["Cr_kN"] > 0 else float("inf")
    if util <= 1.0:
        st.success(f" PASS — Pu/Cr = {util:.2f}")
    else:
        st.error(f" FAIL — Pu/Cr = {util:.2f}")

with st.expander("Raw CSV Record"):
    st.json(shapes[sec_name])