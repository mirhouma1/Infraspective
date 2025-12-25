import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
import streamlit as st

# ----------------------------
# CONFIG
# ----------------------------
DATA_DIR = Path(__file__).resolve().parent / "data"
PHI_B = 0.9

# ----------------------------
# KEY NORMALIZATION + CANONICAL FIELD MAP
# ----------------------------
def _norm(s: str) -> str:
    return (
        str(s).strip().lower()
        .replace("(", "").replace(")", "")
        .replace("[", "").replace("]", "")
        .replace("/", "_").replace("-", "_")
        .replace(" ", "_")
        .replace("^", "")
    )

CANON_SYNONYMS = {
    "designation": {"designation", "shape", "section", "name", "w_shape"},
    "d": {"d", "depth", "depth_d", "depth_d_mm", "overall_depth", "depth_d"},
    "b": {"b", "bf", "flange_width", "flange_width_b", "flange_width_b_mm"},
    "tf": {"tf", "t", "flange_thickness", "flange_thickness_t", "flange_thickness_t_mm"},
    "tw": {"tw", "w", "web_thickness", "web_thickness_w", "web_thickness_w_mm"},
    "zx": {"zx", "z_x", "plastic_modulus_zx", "plastic_modulus_zx_mm3", "zx_mm3", "zx_103_mm"},
    "sx": {"sx", "s_x", "elastic_modulus_sx", "elastic_modulus_sx_mm3", "sx_mm3", "sx_103_mm"},
    "k": {"k", "distance_k", "distance_k_mm", "fillet_distance"},
}

def _canonicalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    norm_map = {_norm(k): v for k, v in rec.items()}
    out = dict(rec)

    def pick(field: str) -> Optional[Any]:
        for cand in CANON_SYNONYMS[field]:
            ck = _norm(cand)
            if ck in norm_map and norm_map[ck] not in (None, ""):
                return norm_map[ck]
        return None
    
    def pick_by_prefix(prefix: str) -> Optional[Any]:
        for k, v in rec.items():
            k_lower = k.lower().strip()
            if k_lower.startswith(prefix) and v not in (None, ""):
                return v
        return None

    for f in ("designation", "d", "b", "tf", "tw", "zx", "sx", "k"):
        v = pick(f)
        if v is not None:
            out[f] = v
    
    # Fallback: try prefix matching for Zx and Sx columns (e.g., "Zx (10^3 mm³)")
    if out.get("zx") is None:
        v = pick_by_prefix("zx")
        if v is not None:
            out["zx"] = v
    if out.get("sx") is None:
        v = pick_by_prefix("sx")
        if v is not None:
            out["sx"] = v
    
    # Also match "Depth d" and similar patterns
    if out.get("d") is None:
        v = pick_by_prefix("depth d")
        if v is not None:
            out["d"] = v
    if out.get("b") is None:
        v = pick_by_prefix("flange width")
        if v is not None:
            out["b"] = v
    if out.get("tf") is None:
        v = pick_by_prefix("flange thickness")
        if v is not None:
            out["tf"] = v
    if out.get("tw") is None:
        v = pick_by_prefix("web thickness")
        if v is not None:
            out["tw"] = v
    if out.get("k") is None:
        v = pick_by_prefix("distance k")
        if v is not None:
            out["k"] = v

    return out


def _load_csv(path: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for rec in reader:
            rec2 = _canonicalize_record(rec)
            des = rec2.get("designation") or rec2.get("Designation") or rec2.get("name")
            if des:
                out[str(des)] = rec2
    return out


@st.cache_data
def load_shapes() -> Dict[str, Dict[str, Any]]:
    if not DATA_DIR.exists():
        st.error(f"Missing data directory: {DATA_DIR}")
        return {}

    merged: Dict[str, Dict[str, Any]] = {}

    for p in sorted(DATA_DIR.iterdir(), key=lambda x: x.name.lower()):
        if p.suffix.lower() == ".csv":
            merged.update(_load_csv(p))

    return merged


def list_designations(q: str = "") -> List[str]:
    shapes = load_shapes()
    keys = sorted(shapes.keys())
    if not q:
        return keys
    qq = q.lower().strip()
    return [k for k in keys if qq in k.lower()]


def get_shape(designation: str) -> Optional[Dict[str, Any]]:
    shapes = load_shapes()
    return shapes.get(designation)


def fnum(x: Any, field_name: str) -> float:
    try:
        return float(x)
    except Exception:
        raise ValueError(f"Field '{field_name}' is not numeric: {x!r}")


def to_kNm_from_Nmm(M_Nmm: float) -> float:
    return M_Nmm * 1e-6


def table2_class_major_axis(shape: Dict[str, Any], Fy: float) -> Dict[str, Any]:
    d  = fnum(shape.get("d"), "d")
    b  = fnum(shape.get("b"), "b")
    tf = fnum(shape.get("tf"), "tf")
    tw = fnum(shape.get("tw"), "tw")
    
    # CSA S16: clear web depth h = d - 2k (k is the fillet distance)
    # Fallback to d - 2tf if k is not available
    k = shape.get("k")
    if k is not None:
        try:
            k_val = float(k)
            hw = d - 2.0 * k_val
        except (ValueError, TypeError):
            hw = d - 2.0 * tf
    else:
        hw = d - 2.0 * tf

    if Fy <= 0:
        raise ValueError("Fy must be > 0")

    be = 0.5 * b

    lam_f = be / tf
    lam_w = hw / tw

    r = 1.0 / math.sqrt(Fy)

    f1, f2, f3 = 145*r, 170*r, 200*r
    w1, w2, w3 = 420*r, 525*r, 670*r

    def classify(lam: float, lim1: float, lim2: float, lim3: float) -> int:
        if lam <= lim1: return 1
        if lam <= lim2: return 2
        if lam <= lim3: return 3
        return 4

    class_flange = classify(lam_f, f1, f2, f3)
    class_web    = classify(lam_w, w1, w2, w3)
    section_class = max(class_flange, class_web)

    if section_class == class_flange and section_class == class_web:
        governing = "Flange & Web (tie)"
    elif section_class == class_flange:
        governing = "Flange"
    else:
        governing = "Web"

    return {
        "class_flange": class_flange,
        "class_web": class_web,
        "class_section": section_class,
        "governing": governing,
        "ratios": {"b/2t": round(lam_f, 2), "h/w": round(lam_w, 2)},
        "limits": {
            "flange": {"Class 1": round(f1, 2), "Class 2": round(f2, 2), "Class 3": round(f3, 2)},
            "web": {"Class 1": round(w1, 2), "Class 2": round(w2, 2), "Class 3": round(w3, 2)},
        },
        "geometry_used_mm": {"d": d, "b": b, "tf": tf, "tw": tw, "hw": round(hw, 2), "be": round(be, 2), "k": k},
    }


def Mr_laterally_supported(shape: Dict[str, Any], Fy: float, class_section: int) -> Dict[str, Any]:
    zx = shape.get("zx")
    sx = shape.get("sx")
    
    if zx is None or sx is None:
        return {
            "mr_kNm": None,
            "mode": "Missing Zx/Sx data",
            "error": True
        }

    # Note: Zx and Sx in CSV are in 10^3 mm^3, so multiply by 1000
    Zx = fnum(zx, "Zx") * 1000
    Sx = fnum(sx, "Sx") * 1000

    if class_section in (1, 2):
        Mr_Nmm = PHI_B * Zx * Fy
        mode = f"Plastic (Zx = {Zx/1000:.0f} × 10³ mm³)"
    elif class_section == 3:
        Mr_Nmm = PHI_B * Sx * Fy
        mode = f"Elastic (Sx = {Sx/1000:.0f} × 10³ mm³)"
    else:
        return {
            "mr_kNm": None,
            "mode": "Class 4 requires effective section modulus (Se) — not implemented",
            "error": True
        }

    return {
        "mr_kNm": round(to_kNm_from_Nmm(Mr_Nmm), 1),
        "mode": mode,
        "error": False
    }


# ----------------------------
# STREAMLIT APP
# ----------------------------
st.set_page_config(
    page_title="CSA S16 Flexure Calculator",
    page_icon="🔧",
    layout="wide"
)

st.title("CSA S16 Flexure Calculator")
st.markdown("**Laterally Supported W-Section Bending Check per CSA S16**")

# Sidebar for inputs
with st.sidebar:
    st.header("Input Parameters")
    
    # Load shapes
    shapes = load_shapes()
    if not shapes:
        st.error("No section data found. Please add CSV files to the data/ directory.")
        st.stop()
    
    designations = list_designations()
    
    # Section search/select
    search_query = st.text_input("Search sections", placeholder="e.g., W410")
    if search_query:
        filtered = list_designations(search_query)
    else:
        filtered = designations
    
    if not filtered:
        st.warning("No sections match your search.")
        st.stop()
    
    selected_section = st.selectbox(
        "Select W-Section",
        options=filtered,
        index=0
    )
    
    st.divider()
    
    # Material properties
    Fy = st.number_input(
        "Yield Strength Fy (MPa)",
        min_value=200.0,
        max_value=700.0,
        value=345.0,
        step=5.0,
        help="Typical values: 300 MPa (Grade 300W), 345 MPa (Grade 350W)"
    )
    
    st.divider()
    
    # Optional demand check
    check_demand = st.checkbox("Check against factored moment demand")
    Mu = None
    if check_demand:
        Mu = st.number_input(
            "Factored Moment Mu (kN·m)",
            min_value=0.0,
            value=100.0,
            step=10.0
        )

# Main content
if selected_section:
    shape = get_shape(selected_section)
    
    if shape is None:
        st.error(f"Section {selected_section} not found.")
        st.stop()
    
    # Run calculations
    try:
        class_info = table2_class_major_axis(shape, Fy)
        mr_info = Mr_laterally_supported(shape, Fy, class_info["class_section"])
    except Exception as e:
        st.error(f"Calculation error: {e}")
        st.stop()
    
    # Results layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader(f"Section: {selected_section}")
        
        # Section properties table
        st.markdown("**Section Properties**")
        props_data = {
            "Property": ["Depth (d)", "Flange Width (b)", "Flange Thickness (tf)", "Web Thickness (tw)"],
            "Value": [
                f"{class_info['geometry_used_mm']['d']:.1f} mm",
                f"{class_info['geometry_used_mm']['b']:.1f} mm",
                f"{class_info['geometry_used_mm']['tf']:.1f} mm",
                f"{class_info['geometry_used_mm']['tw']:.1f} mm"
            ]
        }
        st.table(props_data)
    
    with col2:
        st.subheader("Classification Results")
        
        # Section class with color
        section_class = class_info["class_section"]
        if section_class == 1:
            class_color = "green"
            class_desc = "Plastic"
        elif section_class == 2:
            class_color = "blue"
            class_desc = "Compact"
        elif section_class == 3:
            class_color = "orange"
            class_desc = "Non-Compact"
        else:
            class_color = "red"
            class_desc = "Slender"
        
        st.markdown(f"### Section Class: :{'green' if section_class <= 2 else 'orange' if section_class == 3 else 'red'}[**{section_class}**] ({class_desc})")
        st.markdown(f"*Governed by: {class_info['governing']}*")
        
        # Slenderness ratios
        st.markdown("**Slenderness Ratios**")
        ratio_data = {
            "Element": ["Flange (b/2t)", "Web (h/w)"],
            "Actual": [class_info["ratios"]["b/2t"], class_info["ratios"]["h/w"]],
            "Class 1 Limit": [class_info["limits"]["flange"]["Class 1"], class_info["limits"]["web"]["Class 1"]],
            "Class 2 Limit": [class_info["limits"]["flange"]["Class 2"], class_info["limits"]["web"]["Class 2"]],
            "Class 3 Limit": [class_info["limits"]["flange"]["Class 3"], class_info["limits"]["web"]["Class 3"]],
            "Element Class": [class_info["class_flange"], class_info["class_web"]]
        }
        st.table(ratio_data)
    
    st.divider()
    
    # Moment Resistance
    st.subheader("Moment Resistance (Laterally Supported)")
    
    if mr_info.get("error"):
        st.warning(mr_info["mode"])
    else:
        mr_col1, mr_col2 = st.columns(2)
        
        with mr_col1:
            st.metric(
                label="Factored Moment Resistance (Mr)",
                value=f"{mr_info['mr_kNm']:,.1f} kN·m"
            )
            st.caption(f"Mode: {mr_info['mode']}")
            st.caption(f"φb = {PHI_B}")
        
        with mr_col2:
            if check_demand and Mu is not None:
                ratio = Mu / mr_info['mr_kNm'] if mr_info['mr_kNm'] > 0 else float('inf')
                
                if ratio <= 1.0:
                    st.success(f"✅ **PASS** — Mu/Mr = {ratio:.2f} ≤ 1.0")
                else:
                    st.error(f"❌ **FAIL** — Mu/Mr = {ratio:.2f} > 1.0")
                
                st.metric(
                    label="Demand/Capacity Ratio",
                    value=f"{ratio:.2%}"
                )
    
    st.divider()
    
    # References
    with st.expander("References"):
        st.markdown("""
        - **CSA S16 Table 2**: Width-to-thickness ratios for elements in flexural compression
        - **CSA S16 Clause 13.5**: Laterally supported members in bending
        - **φb = 0.9**: Resistance factor for bending
        
        **Classification Limits (for Fy = {:.0f} MPa):**
        - Flange outstand: 145/√Fy, 170/√Fy, 200/√Fy
        - Web in flexure: 420/√Fy, 525/√Fy, 670/√Fy
        """.format(Fy))
    
    # Raw data expander
    with st.expander("Raw Section Data"):
        st.json(shape)
