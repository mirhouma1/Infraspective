import math
from enum import Enum
import streamlit as st

# ================================================================
# CSA S16 / CIVE 3205 — Chapter 6 Part 1 — Bolted Connection Details
# 100% implementation for the note-set scope discussed:
# - Bearing-type: Vr, Br, Tr + interaction (V/Vr)^2 + (T/Tr)^2 <= 1
# - Slip-critical: Vs (Table 3) + interaction V/Vs + 1.9T/(n Ab Fu) <= 1
# - Modifiers: threads intercepted (0.70), long-slotted holes (Br coeff 2.4, Vs*0.75)
# - Detailing: min pitch 2.7d, min edge distance Table 6 (+ d>36 rule),
#              min end distance rule, max edge distance min(12t,150)
# - Internal units in N (display in kN)
# ================================================================

# ----------------------------
# Constants (resistance factors)
# ----------------------------
PHI_B = 0.80  # bolts
PHI_BR = 0.80  # bearing

# Shear / tension factors from the note-set
BOLT_SHEAR_FACTOR = 0.60  # Vr = 0.60 * phi_b * n * m * Ab * Fu
THREADS_INTERCEPT_FACTOR = 0.70  # if threads intercepted
BOLT_TENSION_FACTOR = 0.75  # Tr = 0.75 * phi_b * Ab * Fu

# Slip resistance factors from the note-set
SLIP_BASE_FACTOR = 0.53  # Vs = 0.53 * cs * ks * n * m * Ab * Fu
LONG_SLOT_SLIP_FACTOR = 0.75  # Vs_long = 0.75 Vs

# Bearing coefficient for long slots
BR_COEFF_STD = 3.0
BR_COEFF_LONG_SLOT = 2.4

# Detailing
PITCH_MIN_MULT = 2.7  # min pitch = 2.7 d
EDGE_MAX_LIMIT_MM = 150.0  # max edge dist cap
EDGE_MAX_MULT_T = 12.0  # max edge dist = min(12t,150)


# ----------------------------
# Bolt grades
# ----------------------------
class BoltGrade(Enum):
    A307 = ("ASTM A307", 414.0)
    A325M = ("ASTM A325M", 830.0)
    A490M = ("ASTM A490M", 1040.0)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def Fu_MPa(self) -> float:
        return self.value[1]


# ----------------------------
# Slip critical Table 3 (note-set)
# Includes installation method selection to cover the table structure.
# ----------------------------
class SlipSurfaceClass(Enum):
    A = ("Class A", 0.30)  # ks
    B = ("Class B", 0.52)  # ks

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def ks(self) -> float:
        return self.value[1]


class InstallationMethod(Enum):
    TURN_OF_NUT = "Turn-of-nut"
    OTHER = "Other (e.g., F959/F1852/F2280 column)"


# cs values per the note-set table structure:
# - Turn-of-nut column depends on bolt grade family (A325 vs A490)
# - Other column is a single cs value (surface class dependent)
SLIP_CS = {
    SlipSurfaceClass.A: {
        "turn_of_nut": {
            BoltGrade.A325M: 1.00,
            BoltGrade.A490M: 0.92
        },
        "other": 0.78,
        "desc": "Clean mill scale",
    },
    SlipSurfaceClass.B: {
        "turn_of_nut": {
            BoltGrade.A325M: 1.04,
            BoltGrade.A490M: 0.96
        },
        "other": 0.81,
        "desc": "Blast-cleaned",
    },
}


def get_cs(surface: SlipSurfaceClass, grade: BoltGrade,
           method: InstallationMethod) -> float:
    if method == InstallationMethod.OTHER:
        return float(SLIP_CS[surface]["other"])
    # turn-of-nut: only defined for high-strength families
    if grade in (BoltGrade.A325M, BoltGrade.A490M):
        return float(SLIP_CS[surface]["turn_of_nut"][grade])
    # A307 slip-critical is not applicable; return conservative placeholder (will be blocked in UI)
    return float(SLIP_CS[surface]["other"])


# ----------------------------
# Table 6 min edge distances (mm): bolt diameter -> (sheared, rolled/sawn/thermal)
# plus rule for d > 36: sheared = 1.75d, rolled/sawn = 1.25d
# ----------------------------
class EdgeType(Enum):
    SHEARED = "Sheared"
    ROLLED_SAWN_THERMAL = "Rolled / sawn / thermal cut"


TABLE_6 = {
    16: (28.0, 22.0),
    20: (34.0, 26.0),
    22: (38.0, 28.0),
    24: (42.0, 30.0),
    27: (48.0, 34.0),
    30: (52.0, 38.0),
    36: (64.0, 46.0),
}


def min_edge_distance_mm(d_mm: float, edge_type: EdgeType) -> float:
    if d_mm > 36.0:
        return 1.75 * d_mm if edge_type == EdgeType.SHEARED else 1.25 * d_mm
    d_int = int(round(d_mm))
    if d_int not in TABLE_6:
        raise ValueError(f"No Table 6 entry for d={d_mm} mm.")
    sheared, rolled = TABLE_6[d_int]
    return sheared if edge_type == EdgeType.SHEARED else rolled


def min_end_distance_mm(d_mm: float, bolts_in_line_parallel_to_load: int,
                        edge_type: EdgeType) -> float:
    # Note-set rule described: if 1–2 bolts in line parallel to load => >= 1.5d, else Table 6
    if bolts_in_line_parallel_to_load <= 2:
        return 1.5 * d_mm
    return min_edge_distance_mm(d_mm, edge_type)


def max_edge_distance_mm(t_mm: float) -> float:
    return min(EDGE_MAX_MULT_T * t_mm, EDGE_MAX_LIMIT_MM)


def min_pitch_mm(d_mm: float) -> float:
    return PITCH_MIN_MULT * d_mm


# ----------------------------
# Core mechanics (internal N)
# ----------------------------
def bolt_area_mm2(d_mm: float) -> float:
    return (math.pi * d_mm**2) / 4.0


def shear_resistance_N(n: int, m: int, d_mm: float, Fu_bolt_MPa: float,
                       threads_intercepted: bool) -> float:
    Ab = bolt_area_mm2(d_mm)
    Vr = BOLT_SHEAR_FACTOR * PHI_B * n * m * Ab * Fu_bolt_MPa  # N (MPa*mm^2 = N)
    if threads_intercepted:
        Vr *= THREADS_INTERCEPT_FACTOR
    return Vr


def bearing_resistance_N(n: int, t_mm: float, d_mm: float, Fu_plate_MPa: float,
                         long_slotted: bool) -> float:
    coeff = BR_COEFF_LONG_SLOT if long_slotted else BR_COEFF_STD
    return coeff * PHI_BR * n * t_mm * d_mm * Fu_plate_MPa


def tension_resistance_N_per_bolt(d_mm: float, Fu_bolt_MPa: float) -> float:
    Ab = bolt_area_mm2(d_mm)
    return BOLT_TENSION_FACTOR * PHI_B * Ab * Fu_bolt_MPa


def tension_resistance_N_group(n: int, d_mm: float,
                               Fu_bolt_MPa: float) -> float:
    return n * tension_resistance_N_per_bolt(d_mm, Fu_bolt_MPa)


def slip_resistance_N(n: int, m: int, d_mm: float, Fu_bolt_MPa: float,
                      ks: float, cs: float, long_slotted: bool) -> float:
    Ab = bolt_area_mm2(d_mm)
    Vs = SLIP_BASE_FACTOR * cs * ks * n * m * Ab * Fu_bolt_MPa
    if long_slotted:
        Vs *= LONG_SLOT_SLIP_FACTOR
    return Vs


# ----------------------------
# Interaction checks (dimensionless unity)
# ----------------------------
def unity_bearing_type(Vu_N: float, Tu_N: float, Vr_N: float,
                       Tr_N: float) -> float:
    # (V/Vr)^2 + (T/Tr)^2
    if Vr_N <= 0 or Tr_N <= 0:
        return float("inf")
    return (Vu_N / Vr_N)**2 + (Tu_N / Tr_N)**2


def unity_slip_critical(Vu_N: float, Tu_N: float, Vs_N: float, n: int,
                        d_mm: float, Fu_bolt_MPa: float) -> float:
    # V/Vs + 1.9T/(n Ab Fu)
    if Vs_N <= 0:
        return float("inf")
    Ab = bolt_area_mm2(d_mm)
    denom = n * Ab * Fu_bolt_MPa
    if denom <= 0:
        return float("inf")
    return (Vu_N / Vs_N) + (1.9 * Tu_N / denom)


# ----------------------------
# Prying helper (as per the simplified note expression used earlier)
# ----------------------------
def prying_k_factor(a_mm: float, b_mm: float, t_mm: float) -> float:
    # Conservative preview per your note expression: k = (3b)/(8a) - (t^3)/(328e3)
    if a_mm <= 0:
        return float("nan")
    return (3.0 * b_mm) / (8.0 * a_mm) - (t_mm**3) / (328e3)


# ================================================================
# Streamlit UI
# ================================================================
st.set_page_config(layout="wide",
                   page_title="CSA S16 Bolted Connection Solver — Part 1")
st.title(
    "🔩 CSA S16 Bolted Connection Solver — Chapter 6 Part 1 (Bolted Details)")
st.caption(
    "Implements Vr, Br, Tr, Vs (Table 3), interaction checks, and Table 6 detailing checks. Internal units: N; display: kN, mm."
)

with st.sidebar:
    st.header("1) Connection Inputs")

    conn_type = st.selectbox("Connection Type",
                             ["Bearing-type", "Slip-critical"])

    grade = st.selectbox("Bolt Grade",
                         list(BoltGrade),
                         format_func=lambda g: g.label)
    d_mm = st.selectbox("Bolt Diameter d [mm]", [16, 20, 22, 24, 27, 30, 36])
    n = int(st.number_input("Total bolts n", min_value=1, value=4, step=1))
    m = int(st.number_input("Shear planes m", min_value=1, value=1, step=1))

    st.divider()
    st.header("2) Plate Material")
    t_mm = float(
        st.number_input("Plate thickness t [mm]",
                        min_value=1.0,
                        value=10.0,
                        step=1.0))
    Fu_plate_MPa = float(
        st.number_input("Plate Fu [MPa]",
                        min_value=1.0,
                        value=450.0,
                        step=10.0))

    st.divider()
    st.header("3) Detailing Geometry Provided")
    pitch_prov_mm = float(
        st.number_input("Provided pitch p [mm]",
                        min_value=0.0,
                        value=0.0,
                        step=1.0))
    edge_type = st.radio("Edge type",
                         list(EdgeType),
                         format_func=lambda e: e.value)
    edge_prov_mm = float(
        st.number_input("Provided edge distance e [mm]",
                        min_value=0.0,
                        value=0.0,
                        step=1.0))

    bolts_in_line = int(
        st.number_input("Bolts in line parallel to load (for end distance)",
                        min_value=1,
                        value=2,
                        step=1))
    end_prov_mm = float(
        st.number_input("Provided end distance a_end [mm]",
                        min_value=0.0,
                        value=0.0,
                        step=1.0))

    st.divider()
    st.header("4) Factored Loads")
    Vu_kN = float(
        st.number_input("Factored shear Vu [kN]",
                        min_value=0.0,
                        value=0.0,
                        step=1.0))
    Tu_kN = float(
        st.number_input("Factored tension Tu [kN]",
                        min_value=0.0,
                        value=0.0,
                        step=1.0))

    st.divider()
    st.header("5) Options")
    threads_intercepted = st.checkbox("Threads intercepted by shear plane?")
    long_slotted = st.checkbox("Long-slotted holes?")

    # Slip-only inputs
    slip_surface = SlipSurfaceClass.A
    slip_method = InstallationMethod.TURN_OF_NUT
    if conn_type == "Slip-critical":
        st.divider()
        st.subheader("Slip-Critical (Table 3)")
        slip_surface = st.selectbox(
            "Surface class",
            list(SlipSurfaceClass),
            format_func=lambda s: f"{s.label} — {SLIP_CS[s]['desc']}")
        slip_method = st.selectbox("Installation method",
                                   list(InstallationMethod),
                                   format_func=lambda x: x.value)

# Convert loads to N
Vu_N = Vu_kN * 1000.0
Tu_N = Tu_kN * 1000.0

Fu_bolt_MPa = grade.Fu_MPa

# Compute core resistances (N)
Vr_N = shear_resistance_N(n, m, d_mm, Fu_bolt_MPa, threads_intercepted)
Br_N = bearing_resistance_N(n, t_mm, d_mm, Fu_plate_MPa, long_slotted)

# Tension: show BOTH per bolt and group explicitly to avoid ambiguity
Tr_per_bolt_N = tension_resistance_N_per_bolt(d_mm, Fu_bolt_MPa)
Tr_group_N = tension_resistance_N_group(n, d_mm, Fu_bolt_MPa)

# Slip resistance (if applicable)
Vs_N = 0.0
cs = None
ks = None
if grade == BoltGrade.A307:
    slip_applicable = False
else:
    slip_applicable = True

if conn_type == "Slip-critical":
    if not slip_applicable:
        Vs_N = 0.0
    else:
        ks = slip_surface.ks
        cs = get_cs(slip_surface, grade, slip_method)
        Vs_N = slip_resistance_N(n, m, d_mm, Fu_bolt_MPa, ks, cs, long_slotted)

# Layout
col_calc, col_detail = st.columns([3, 2], gap="large")

with col_calc:
    st.subheader("Capacities (Resistance Results)")

    # Display kN
    def kN(xN: float) -> float:
        return xN / 1000.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bolt Shear Vr", f"{kN(Vr_N):.1f} kN")
    c2.metric("Bearing Br", f"{kN(Br_N):.1f} kN")
    c3.metric("Bolt Tension Tr (per bolt)", f"{kN(Tr_per_bolt_N):.1f} kN")
    c4.metric("Bolt Tension Tr (group)", f"{kN(Tr_group_N):.1f} kN")

    st.divider()
    st.subheader("Interaction Checks")

    # Bearing-type interaction uses group Vr and group Tr (loads assumed to be group loads)
    u_bearing = unity_bearing_type(Vu_N, Tu_N, Vr_N, Tr_group_N)
    u1, u2 = st.columns(2)
    u1.write(
        f"**Bearing-type unity**: {u_bearing:.3f}  \nCriterion: (Vu/Vr)² + (Tu/Tr)² ≤ 1.0"
    )
    if math.isfinite(u_bearing) and u_bearing <= 1.0:
        u2.success("PASS")
    else:
        u2.error("FAIL")

    # Slip-critical interaction
    if conn_type == "Slip-critical":
        st.divider()
        st.subheader("Slip-Critical Capacity + Interaction")
        if not slip_applicable:
            st.warning(
                "Slip-critical resistance is not applicable to ASTM A307 bolts."
            )
        else:
            st.write(
                f"Table 3 inputs used: **ks = {ks:.2f}**, **cs = {cs:.2f}** ({SLIP_CS[slip_surface]['desc']}); method: {slip_method.value}"
            )
            st.metric("Slip Resistance Vs", f"{kN(Vs_N):.1f} kN")

            u_sc = unity_slip_critical(Vu_N, Tu_N, Vs_N, n, d_mm, Fu_bolt_MPa)
            s1, s2 = st.columns(2)
            s1.write(
                f"**Slip-critical unity**: {u_sc:.3f}  \nCriterion: Vu/Vs + 1.9Tu/(nAbFu) ≤ 1.0"
            )
            if math.isfinite(u_sc) and u_sc <= 1.0:
                s2.success("PASS")
            else:
                s2.error("FAIL")

    st.divider()
    st.subheader("Governing Summary (within Part 1 scope)")

    # For Part 1 scope: show governing among the computed capacities relevant to chosen type
    # Note: full design may also require block shear, net section fracture, tear-out, etc. (Part 2 / other sections).
    if conn_type == "Bearing-type":
        caps = {
            "Bolt shear Vr": Vr_N,
            "Bearing Br": Br_N,
            "Bolt tension Tr (group)": Tr_group_N,
        }
    else:
        if slip_applicable:
            caps = {
                "Slip Vs": Vs_N,
                "Bolt tension Tr (group)": Tr_group_N,
                "Bearing Br":
                Br_N,  # still useful to view, even if mechanism is slip
                "Bolt shear Vr": Vr_N,
            }
        else:
            caps = {
                "Bolt shear Vr": Vr_N,
                "Bearing Br": Br_N,
                "Bolt tension Tr (group)": Tr_group_N,
            }

    governing_name = min(caps,
                         key=lambda k: caps[k]
                         if caps[k] > 0 else float("inf"))
    st.info(
        f"Governing (minimum) capacity shown: **{governing_name} = {kN(caps[governing_name]):.1f} kN**"
    )

with col_detail:
    st.subheader("Detailing Checks (Table 6 + Limits)")

    # Pitch
    p_min = min_pitch_mm(d_mm)
    st.write(f"**Min pitch p_min = 2.7d = {p_min:.1f} mm**")
    if pitch_prov_mm > 0:
        if pitch_prov_mm >= p_min:
            st.success(
                f"Pitch PASS (provided {pitch_prov_mm:.1f} mm ≥ {p_min:.1f} mm)"
            )
        else:
            st.error(
                f"Pitch FAIL (provided {pitch_prov_mm:.1f} mm < {p_min:.1f} mm)"
            )
    else:
        st.caption("Enter a provided pitch to get PASS/FAIL.")

    st.divider()

    # Edge distance min/max
    e_min = min_edge_distance_mm(d_mm, edge_type)
    e_max = max_edge_distance_mm(t_mm)
    st.write(
        f"**Edge distance limits:**  \n- e_min (Table 6) = **{e_min:.1f} mm**  \n- e_max = min(12t,150) = **{e_max:.1f} mm**"
    )

    if edge_prov_mm > 0:
        if edge_prov_mm < e_min:
            st.error(
                f"Edge distance FAIL (provided {edge_prov_mm:.1f} mm < e_min {e_min:.1f} mm)"
            )
        elif edge_prov_mm > e_max:
            st.error(
                f"Edge distance FAIL (provided {edge_prov_mm:.1f} mm > e_max {e_max:.1f} mm)"
            )
        else:
            st.success(
                f"Edge distance PASS ({e_min:.1f} ≤ {edge_prov_mm:.1f} ≤ {e_max:.1f})"
            )
    else:
        st.caption("Enter a provided edge distance to get PASS/FAIL.")

    st.divider()

    # End distance min check (rule + Table 6)
    a_end_min = min_end_distance_mm(d_mm, bolts_in_line, edge_type)
    st.write(
        f"**Min end distance a_end,min = {a_end_min:.1f} mm**  \nRule: 1–2 bolts in line → 1.5d; >2 → Table 6"
    )

    if end_prov_mm > 0:
        if end_prov_mm >= a_end_min:
            st.success(
                f"End distance PASS (provided {end_prov_mm:.1f} mm ≥ {a_end_min:.1f} mm)"
            )
        else:
            st.error(
                f"End distance FAIL (provided {end_prov_mm:.1f} mm < {a_end_min:.1f} mm)"
            )
    else:
        st.caption("Enter a provided end distance to get PASS/FAIL.")

    st.divider()
    st.subheader("Prying (Conservative Preview)")

    with st.expander("Prying k-factor and Q = kP preview"):
        a_mm = float(
            st.number_input("Distance a [mm]",
                            min_value=0.0,
                            value=50.0,
                            step=1.0))
        b_mm = float(
            st.number_input("Distance b [mm]",
                            min_value=0.0,
                            value=40.0,
                            step=1.0))
        k = prying_k_factor(a_mm, b_mm, t_mm)
        if math.isfinite(k):
            st.write(f"**k = {k:.4f}** (per note-set simplified expression)")
            st.caption(
                "If P is the bolt force, prying estimate: Q = k·P; total bolt force ≈ P + Q."
            )
        else:
            st.warning("Invalid a (must be > 0).")
