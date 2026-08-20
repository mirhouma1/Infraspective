"""
pages/11_Blast_SDOF.py

Dynamic blast response of a member, by the single degree of freedom
method.

This page is built to be learned from rather than only used. The model
on the left is not an illustration drawn beside the answer: it is the
answer, played back. blast_sdof.py solves the equation of motion once,
and the beam that bends on screen, the mass on the spring beside it, the
reaction arrows, the three plots and every figure in the steps below are
all reading the same array.

The sequence on this page follows Section 6.4:

    0  what is being replaced by what, and why
    1  dynamic material strength, F_dy = SIF x DIF x Fy
    2  section capacity, Mp = F_dy Z
    3  the resistance function R(y) from the transformation tables
    4  the transformation factors themselves, and why they change with
       the strain range
    5  mass, and the equivalent system K_LM M a + R = F(t)
    6  the natural period, and t_d / t_n, which decides everything
    7  time integration, and the peak response
    8  dynamic reactions, Section 6.4.6
    9  closed form cross checks, Equations 6.9, 6.10 and 6.11

Method, not code, is the thing being taught, so every step shows its
working and names the equation it came from.

ASCII only. Straight quotes only. No markdown inside code.
"""

import math

import streamlit as st

st.set_page_config(page_title="Blast SDOF - Infraspective",
                   page_icon=":boom:", layout="wide")

from _theme import (apply_theme, render_sidebar_logo, render_footer,
                    gate_disclaimer, render_page_title)

gate_disclaimer()
apply_theme()
render_sidebar_logo()
render_footer()

import blast_sdof
import viewer_3d_blast

render_page_title(
    "Dynamic Blast Response, SDOF",
    clauses=("Eq. 6.1 to 6.11  |  Tables 6.1 and 6.2  |  "
             "Figures 6.3, 6.4 and 6.8"),
    intro=("A member with distributed mass and load, replaced by one "
           "mass on one spring, and the resulting motion solved in "
           "time. The model plays back the solution, so the animation "
           "and the arithmetic are the same numbers."),
)


# ---------------------------------------------------------------------
# Section table, shared with the rest of the app
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def w_rows():
    try:
        import sst12
        rows = sst12.load_all_tables().get("w", [])
    except Exception:
        return []
    out = []
    for r in rows:
        if r.get("Ix") and r.get("Zx") and r.get("Area") and r.get("d"):
            out.append({
                "name": r["Designation"],
                "d": float(r["d"]), "bf": float(r["b"] or 0.0),
                "tf": float(r["t"] or 0.0), "tw": float(r["w"] or 0.0),
                # SST keeps its 10^x convention: Ix in 10^6 mm4,
                # Zx in 10^3 mm3. Both come out as 1e-6 in metres.
                "Ix_m4": float(r["Ix"]) * 1.0e-6,
                "Zx_m3": float(r["Zx"]) * 1.0e-6,
                "A_m2": float(r["Area"]) * 1.0e-6,
                "Ix_disp": float(r["Ix"]), "Zx_disp": float(r["Zx"]),
                "A_disp": float(r["Area"]),
            })
    return out


def w_lookup(name):
    for r in w_rows():
        if r["name"] == name:
            return r
    return None


PRESETS = {
    "Blast wall girt, 35 kPa short pulse": {
        "sec": "W310x39", "L": 6.0, "sup": "fixed", "lc": "uniform",
        "Po": 35.0, "td": 20.0, "b": 1.5, "msup": 25.0},
    "Same girt, doubled pressure": {
        "sec": "W310x39", "L": 6.0, "sup": "fixed", "lc": "uniform",
        "Po": 90.0, "td": 20.0, "b": 1.5, "msup": 25.0},
    "Long duration, nearly static": {
        "sec": "W310x39", "L": 6.0, "sup": "simple", "lc": "uniform",
        "Po": 20.0, "td": 400.0, "b": 1.5, "msup": 25.0},
    "Very short pulse, impulsive": {
        "sec": "W310x39", "L": 6.0, "sup": "simple", "lc": "uniform",
        "Po": 400.0, "td": 2.0, "b": 1.5, "msup": 25.0},
}


def apply_preset():
    p = PRESETS.get(st.session_state.get("bl_preset"))
    if not p:
        return
    st.session_state["bl_sec"] = p["sec"]
    st.session_state["bl_L"] = p["L"]
    st.session_state["bl_sup"] = p["sup"]
    st.session_state["bl_lc"] = p["lc"]
    st.session_state["bl_Po"] = p["Po"]
    st.session_state["bl_td"] = p["td"]
    st.session_state["bl_b"] = p["b"]
    st.session_state["bl_msup"] = p["msup"]


col_model, col_in = st.columns([2, 1], gap="large")


def num(label, key, default, step=1.0, minv=0.0, fmt="%.1f", help=None):
    return st.number_input(label, min_value=minv, value=float(default),
                           step=step, format=fmt, key="bl_" + key, help=help)


# ---------------------------------------------------------------------
# INPUTS
# ---------------------------------------------------------------------
with col_in:
    st.subheader("Design Inputs")

    ROWS = w_rows()
    NAMES = [r["name"] for r in ROWS]

    with st.expander("Start from", expanded=True):
        st.selectbox(
            "Preset", ["(keep what is set)"] + list(PRESETS.keys()),
            key="bl_preset", on_change=apply_preset,
            help="Four cases chosen to sit in different parts of the "
                 "response range: one ordinary, one pushed past yield, "
                 "one long enough to behave like a static load, and one "
                 "short enough that only the impulse matters. Run all "
                 "four and watch t_d / t_n change what the member does.")

    with st.expander("Member", expanded=True):
        if NAMES:
            default_i = NAMES.index("W310x39") if "W310x39" in NAMES else 0
            st.selectbox("Section", NAMES, index=default_i, key="bl_sec",
                         help="Read from the CISC SST12.1 workbook, the "
                              "same source the rest of the app uses. It "
                              "supplies I for the stiffness, Z for the "
                              "plastic capacity, the area for the self "
                              "weight, and d, bf and tf so the model is "
                              "drawn to shape.")
        else:
            st.error("Section table unavailable.")
            st.stop()
        L = num("L, span (m)", "L", 6.0, 0.25, 0.5, "%.2f",
                help="Clear span between supports. Stiffness goes as "
                     "1/L cubed and resistance as 1/L, so span moves "
                     "the period more than anything else on this page.")
        support = st.radio(
            "Support condition", ["simple", "fixed"], horizontal=True,
            key="bl_sup",
            format_func=lambda k: blast_sdof.SUPPORTS[k],
            help="Fixed ends give roughly eight times the stiffness and "
                 "twice the resistance of pinned ends, and they add an "
                 "elastic-plastic range under uniform load because the "
                 "support hinges form before the midspan one.")
        loadcase = st.radio(
            "Load case", ["uniform", "point", "third"], horizontal=True,
            key="bl_lc",
            format_func=lambda k: blast_sdof.LOADCASES[k],
            help="How the blast reaches the member. A wall girt or a "
                 "cladding rail takes uniform pressure. Point loads are "
                 "for a member picking up reactions from something "
                 "else, which is the member by member load path of "
                 "Section 6.2.3.")
        b = num("b, tributary width (m)", "b", 1.5, 0.1, 0.05, "%.2f",
                help="Width of wall or roof this member picks up. It "
                     "scales the load and the supported mass together, "
                     "so it moves the response less than it looks.")

    with st.expander("Blast load", expanded=True):
        Po = num("Po, peak pressure (kPa)", "Po", 35.0, 5.0, 0.0, "%.1f",
                 help="Peak of the idealised pulse. Section 6.2.2 is "
                      "blunt about this being the largest approximation "
                      "in the whole analysis, which is why the rest of "
                      "the method stays simple.")
        td_ms = num("td, pulse duration (ms)", "td", 20.0, 1.0, 0.1, "%.1f",
                    help="Time for the pressure to fall to zero on the "
                         "straight line idealisation of Section 3.3.6. "
                         "What matters is this against the natural "
                         "period, not its absolute size.")
        st.caption("The pulse is a straight line from Po at t = 0 to "
                   "zero at td. Impulse is the area under it, Io = "
                   "0.5 Fo td.")

    with st.expander("Materials", expanded=True):
        Fy = num("Fy, static yield (MPa)", "Fy", 350.0, 5.0, 100.0, "%.0f",
                 help="Specified minimum yield. It gets increased twice "
                      "before it is used, by SIF and DIF below.")
        SIF = num("SIF, strength increase factor", "SIF", 1.10, 0.01, 1.0,
                  "%.2f",
                  help="Chapter 5. Recognises that steel is delivered "
                       "above its specified minimum. Around 1.1 for "
                       "structural steel.")
        DIF = num("DIF, dynamic increase factor", "DIF", 1.19, 0.01, 1.0,
                  "%.2f",
                  help="Chapter 5. Steel yields higher when it is "
                       "strained fast, and a blast strains it very "
                       "fast. Around 1.19 for bending in a blast, less "
                       "for shear, and 1.0 if you want it left out.")
        msup = num("Supported mass (kg/m2)", "msup", 25.0, 5.0, 0.0, "%.1f",
                   help="Cladding, insulation and anything else that "
                        "accelerates with the member. Section 6.2.4: "
                        "leave out live load that would be blown away "
                        "or that does not add inertia.")

    with st.expander("Solver", expanded=False):
        method = st.radio(
            "Integration method", ["central", "newmark"], horizontal=True,
            key="bl_method",
            format_func=lambda k: ("Central difference" if k == "central"
                                   else "Newmark, constant average"),
            help="Two ways of solving the same equation. Central "
                 "difference is the recurrence Biggs uses and is the "
                 "easier one to follow by hand. Newmark is "
                 "unconditionally stable for a linear system. If they "
                 "disagree, the time step is too coarse.")
        dt_ratio = num("Time step, 1 / this many", "dtr", 400.0, 50.0, 20.0,
                       "%.0f",
                       help="The step is the smaller of tn and td "
                            "divided by this. The rule of thumb in "
                            "Section 6.4.5 is at least 10; the default "
                            "here is far finer because it costs "
                            "nothing.")
        n_per = num("Run for this many periods", "nper", 3.0, 0.5, 0.5,
                    "%.1f",
                    help="How long to keep integrating after the pulse "
                         "has gone. Two or three periods is enough to "
                         "catch the rebound peak, which is one of the "
                         "four things the analysis has to deliver.")
        klm_mode = st.radio(
            "K_LM to use", ["average", "elastic", "plastic"],
            horizontal=True, key="bl_klm",
            format_func=lambda k: {"average": "Average of the ranges",
                                   "elastic": "Elastic range",
                                   "plastic": "Plastic range"}[k],
            help="Section 6.4.2: in practice the factors are held "
                 "constant through the analysis and picked for the "
                 "response expected to dominate. Averaging the elastic "
                 "and plastic values is the common compromise. Switch "
                 "between them and watch the period move.")

    with st.expander("Model", expanded=False):
        dscale = st.selectbox(
            "Deflection scale", ["auto", "1", "5", "20", "50", "200"],
            key="bl_dscale",
            help="Real deflections are a fraction of the span and "
                 "invisible at true scale. Auto puts the peak at about "
                 "a twelfth of the span. This is drawing only and "
                 "changes no number on the page.")


# ---------------------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------------------
sec = w_lookup(st.session_state.get("bl_sec"))
if sec is None:
    st.stop()

case = blast_sdof.CASES.get((support, loadcase))
if case is None:
    with col_model:
        st.error("That combination of support condition and load case is "
                 "not in the encoded tables. Simply supported and fixed "
                 "end members are covered; the simple-fixed table of "
                 "Table 6.3 has deliberately been left out rather than "
                 "guessed at.")
    st.stop()

KLM_el = case["stages"][0]["KLM"]
KLM_pl = case["plastic"]["KLM"]
KLM = {"elastic": KLM_el, "plastic": KLM_pl,
       "average": 0.5 * (KLM_el + KLM_pl)}[klm_mode]

INP = {
    "L_m": L,
    "EI_Nm2": blast_sdof.E_STEEL * sec["Ix_m4"],
    "Z_m3": sec["Zx_m3"], "A_m2": sec["A_m2"],
    "support": support, "loadcase": loadcase,
    "Fy_Pa": Fy * 1.0e6, "SIF": SIF, "DIF": DIF,
    "Po_Pa": Po * 1.0e3, "td_s": td_ms / 1000.0,
    "b_m": b, "mass_sup_kgm2": msup,
    "method": method, "dt_ratio": dt_ratio, "n_periods": n_per,
    "KLM": KLM,
}

try:
    R = blast_sdof.analyse(INP)
except Exception as exc:
    with col_model:
        st.error("Calculation error: " + str(exc))
    st.stop()

MAT = R["material"]
SEC = R["section"]
RES = R["resistance"]
MAS = R["mass"]
DYN = R["dynamics"]
LOAD = R["load"]
RESP = R["response"]
CHK = R["checks"]


def prow(group, symbol, value, unit, nd=1):
    try:
        v = "{:,.{}f}".format(float(value), nd)
    except (TypeError, ValueError):
        v = str(value)
    return {"group": group, "symbol": symbol, "value": v, "unit": unit}


PROPS = [
    prow("Member", "section", sec["name"], ""),
    prow("Member", "L", L, "m", 2),
    prow("Member", "I", sec["Ix_disp"], "10^6 mm4", 1),
    prow("Member", "Z", sec["Zx_disp"], "10^3 mm3", 0),
    prow("Load", "Po", Po, "kPa"),
    prow("Load", "td", td_ms, "ms"),
    prow("Load", "Fo", LOAD["Fo_N"] / 1e3, "kN", 0),
    prow("Load", "Io", LOAD["Io_Ns"] / 1e3, "kN s", 2),
    prow("Strength", "Fdy", MAT["Fdy_Pa"] / 1e6, "MPa", 0),
    prow("Strength", "Mp", SEC["Mpc_Nm"] / 1e3, "kN m", 1),
    prow("System", "Ru", RES["Ru_N"] / 1e3, "kN", 0),
    prow("System", "KE", RES["KE_Npm"] / 1e6, "MN/m", 2),
    prow("System", "yE", RES["yE_m"] * 1e3, "mm", 1),
    prow("System", "M", MAS["M_kg"], "kg", 0),
    prow("System", "KLM", MAS["KLM"], "", 3),
    prow("System", "Me", MAS["Me_kg"], "kg", 0),
    prow("System", "tn", DYN["tn_s"] * 1e3, "ms", 1),
    prow("Response", "td/tn", CHK["tau"], "", 3),
    prow("Response", "ymax", RESP["ymax_m"] * 1e3, "mm", 1),
    prow("Response", "mu", RESP["mu"], "", 2),
    prow("Response", "theta", RESP["theta_deg"], "deg", 2),
    prow("Response", "Vmax", RESP["Vmax_N"] / 1e3, "kN", 0),
]


# ---------------------------------------------------------------------
# MODEL AND THE SEQUENCE
# ---------------------------------------------------------------------
with col_model:
    viewer_3d_blast.render_blast(
        R, height=780,
        section={"d_mm": sec["d"], "bf_mm": sec["bf"],
                 "tf_mm": sec["tf"], "tw_mm": sec["tw"]},
        props=PROPS,
        defl_scale=(None if dscale == "auto" else float(dscale)),
        show_diagnostics=False)

    st.caption("Press Play. The beam, the mass on the spring beside it, "
               "the pressure arrows, the reaction arrows and the three "
               "plots are all one solution being played back. Use the "
               "Explain dropdown in the viewer to change what the "
               "caption underneath is telling you to look at.")

    if not DYN["stable"]:
        st.error("The time step is larger than tn / pi, which is the "
                 "stability limit for the central difference method. "
                 "The numbers below cannot be trusted. Raise the time "
                 "step divisor under Solver.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Peak deflection", "%.1f mm" % (RESP["ymax_m"] * 1e3))
    m2.metric("Ductility, mu", "%.2f" % RESP["mu"])
    m3.metric("Support rotation", "%.2f deg" % RESP["theta_deg"])
    m4.metric("Peak reaction", "%.0f kN" % (RESP["Vmax_N"] / 1e3))

    if RESP["mu"] is not None and RESP["mu"] > 20:
        st.error("Ductility over 20. With Fo/Ru = %.2f and a pulse this "
                 "long the member is not reaching a peak and springing "
                 "back, it is running away: the load stays above the "
                 "resistance and the deflection grows until something "
                 "else stops it. That is collapse, not a large number."
                 % (LOAD["Fo_N"] / RES["Ru_N"]))
    elif RESP["yielded"]:
        st.warning("The member yields at t = %.1f ms and takes %.2f "
                   "times its elastic limit deflection. Compare mu and "
                   "the support rotation against the acceptance "
                   "criteria of Chapter 5 before calling this adequate."
                   % (RESP["t_yield_s"] * 1e3, RESP["mu"]))
    else:
        st.success("The member stays elastic. Peak deflection is %.1f "
                   "mm against an elastic limit of %.1f mm."
                   % (RESP["ymax_m"] * 1e3, RES["yE_m"] * 1e3))

    st.divider()

    # ---- 0. The idea -------------------------------------------------
    st.subheader("0. What is being replaced by what")
    st.caption(case["label"] + ", " + case["table"] + ".")
    st.markdown(
        "A real member has mass and stiffness spread along its length, "
        "so strictly it has as many degrees of freedom as you care to "
        "count. The SDOF method replaces it with one mass on one "
        "spring, chosen so that at the control point the two systems "
        "have the same kinetic energy, the same strain energy and the "
        "same work done by the load, for an assumed deflected shape. "
        "The assumed shape is the whole approximation. Everything else "
        "follows from it.")
    st.info(case["note"])

    st.divider()

    # ---- 1 and 2. Strength and capacity ------------------------------
    st.subheader("1. Dynamic Material Strength and Section Capacity")
    a1, a2, a3 = st.columns(3)
    a1.metric("Fdy", "%.0f MPa" % (MAT["Fdy_Pa"] / 1e6))
    a2.metric("Mp", "%.1f kN m" % (SEC["Mpc_Nm"] / 1e3))
    a3.metric("Increase over Fy", "%.0f %%"
              % (100.0 * (MAT["Fdy_Pa"] / MAT["Fy_Pa"] - 1.0)))
    with st.expander("Show the working", expanded=False):
        st.markdown("\n".join([
            "- Fdy = SIF x DIF x Fy = %.2f x %.2f x %.0f = **%.0f MPa**"
            % (SIF, DIF, Fy, MAT["Fdy_Pa"] / 1e6),
            "- Mp = Fdy Z = %.0f MPa x %.0f x 10^3 mm3 = **%.1f kN m**"
            % (MAT["Fdy_Pa"] / 1e6, sec["Zx_disp"], SEC["Mpc_Nm"] / 1e3),
            "- Both factors are Chapter 5 quantities. Set either to "
            "1.00 to take them out and watch the resistance drop.",
        ]))

    st.divider()

    # ---- 3. Resistance function --------------------------------------
    st.subheader("2. The Resistance Function")
    rows = []
    for i, s in enumerate(RES["stages"]):
        rows.append({"Range": s["name"],
                     "K": "%.2f MN/m" % (s["K"] / 1e6),
                     "Ends at R": "%.0f kN" % (s["R_end"] / 1e3),
                     "Ends at y": "%.1f mm" % (s["y_end"] * 1e3),
                     "V = c1 R + c2 F": "%.3f R + %.3f F"
                                        % (s["V"][0], s["V"][1])})
    rows.append({"Range": "plastic", "K": "0",
                 "Ends at R": "%.0f kN" % (RES["Ru_N"] / 1e3),
                 "Ends at y": "mechanism",
                 "V = c1 R + c2 F": "%.3f Ru + %.3f F"
                                    % (RES["plastic"]["V"][0],
                                       RES["plastic"]["V"][1])})
    st.table(rows)
    b1, b2, b3 = st.columns(3)
    b1.metric("Ru", "%.0f kN" % (RES["Ru_N"] / 1e3))
    b2.metric("yE", "%.1f mm" % (RES["yE_m"] * 1e3))
    b3.metric("KE = Ru / yE", "%.2f MN/m" % (RES["KE_Npm"] / 1e6))
    st.caption("yE is the deflection at which the member becomes a "
               "mechanism, not the end of the elastic range. That is "
               "what ductility is measured against, and it is why a "
               "fixed end member under uniform load has a middle stage "
               "at all. The third plot in the viewer draws this "
               "function and traces the path the response actually "
               "took across it.")

    st.divider()

    # ---- 4. Transformation factors -----------------------------------
    st.subheader("3. Transformation Factors")
    tf_rows = []
    for s in RES["stages"]:
        tf_rows.append({"Range": s["name"], "K_L": "%.2f" % s["KL"],
                        "K_M": "%.2f" % s["KM"],
                        "K_LM = K_M / K_L": "%.2f" % s["KLM"]})
    tf_rows.append({"Range": "plastic",
                    "K_L": "%.2f" % RES["plastic"]["KL"],
                    "K_M": "%.2f" % RES["plastic"]["KM"],
                    "K_LM = K_M / K_L": "%.2f" % RES["plastic"]["KLM"]})
    st.table(tf_rows)
    st.caption("The factors change with the strain range because the "
               "deflected shape changes: an elastic curve while the "
               "member is elastic, a straight sided mechanism once the "
               "hinges have formed. Figure 6.4 shows exactly this for a "
               "simply supported beam. In practice they are held "
               "constant through the analysis, which is what the K_LM "
               "choice under Solver is doing. This run uses K_LM = "
               "%.3f, the %s value." % (MAS["KLM"], klm_mode))
    with st.expander("Show the working", expanded=False):
        st.markdown("\n".join([
            "- Ke = KL K, Me = KM M, Fe = KL F, Re = KL R "
            "(Eq 6.4a to 6.4d)",
            "- Dividing through by KL turns Me a + Re = Fe (Eq 6.5) "
            "into KLM M a + K y = F(t) (Eq 6.6), with KLM = KM / KL",
            "- so only one factor is needed, and the applied load and "
            "the resistance keep their real values",
            "- elastic KLM = %.2f, plastic KLM = %.2f, this run uses "
            "**%.3f**" % (KLM_el, KLM_pl, MAS["KLM"]),
        ]))

    st.divider()

    # ---- 5 and 6. Mass, equivalent system and period ------------------
    st.subheader("4. Mass, Equivalent System and Period")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total mass M", "%.0f kg" % MAS["M_kg"])
    c2.metric("Equivalent Me", "%.0f kg" % MAS["Me_kg"])
    c3.metric("Period tn", "%.1f ms" % (DYN["tn_s"] * 1e3))
    c4.metric("td / tn", "%.3f" % CHK["tau"])
    regime_note = {
        "impulsive": "td / tn is under 0.1. The pulse is over before "
                     "the member has had time to respond, so only its "
                     "impulse matters and the shape of the pressure "
                     "history is irrelevant. Section 6.4.4.",
        "quasi-static": "td / tn is over 10. The load is still there "
                        "when the member reaches its peak, so it "
                        "behaves as though the pressure had been "
                        "switched on and left. Section 6.4.4.",
        "dynamic": "td / tn is between 0.1 and 10, the range where "
                   "neither shortcut applies and the response genuinely "
                   "depends on the time history. This is where the "
                   "numerical integration earns its place.",
    }[CHK["regime"]]
    st.info(regime_note)
    with st.expander("Show the working", expanded=False):
        st.markdown("\n".join([
            "- self weight = A x 7850 = %.1f kg/m, supported = %.1f "
            "kg/m2 x %.2f m = %.1f kg/m"
            % (MAS["m_self_kgm"], msup, b, MAS["m_sup_kgm"]),
            "- M = %.1f kg/m x %.2f m = **%.0f kg**"
            % (MAS["m_line_kgm"], L, MAS["M_kg"]),
            "- Me = KLM M = %.3f x %.0f = **%.0f kg**"
            % (MAS["KLM"], MAS["M_kg"], MAS["Me_kg"]),
            "- f = (1/2 pi) sqrt(Ke/Me) = **%.1f Hz** (Eq 6.7)"
            % DYN["f_Hz"],
            "- tn = 1/f = 2 pi sqrt(Me/Ke) = **%.1f ms** (Eq 6.8)"
            % (DYN["tn_s"] * 1e3),
            "- Fo = Po b L = %.1f kPa x %.2f m x %.2f m = **%.0f kN**"
            % (Po, b, L, LOAD["Fo_N"] / 1e3),
            "- Io = 0.5 Fo td = **%.2f kN s**" % (LOAD["Io_Ns"] / 1e3),
            "- Fo / Ru = **%.3f**" % (LOAD["Fo_N"] / RES["Ru_N"]),
        ]))

    st.divider()

    # ---- 7. Integration ----------------------------------------------
    st.subheader("5. Time Integration and Peak Response")
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("ymax", "%.1f mm" % (RESP["ymax_m"] * 1e3))
    d2.metric("at t", "%.1f ms" % (RESP["tmax_s"] * 1e3))
    d3.metric("mu = ymax / yE", "%.2f" % RESP["mu"])
    d4.metric("Rebound", "%.1f mm" % (RESP["ymin_m"] * 1e3))
    st.caption("Solved with the %s method, %d steps of %.4f ms, which "
               "is tn / %.0f. Section 6.4.5 asks for no worse than a "
               "tenth of the smaller of tn and td."
               % ("central difference" if method == "central"
                  else "Newmark constant average",
                  len(R["history"]["t"]), DYN["dt_s"] * 1e3,
                  DYN["tn_s"] / DYN["dt_s"] if DYN["dt_s"] else 0.0))
    with st.expander("Show the working", expanded=False):
        st.markdown("\n".join([
            "- The equation being solved is Me a + R(y) = F(t), which "
            "is Eq 6.3 written for the equivalent system",
            "- R is the lesser of KE y and Ru, and on unloading it "
            "comes back down a line of slope KE, which is what lets "
            "the member rebound",
            "- Damping is left out, as Section 6.4.1 recommends: the "
            "peak arrives too early for it to matter, and claiming "
            "energy dissipation during plastic response is doubtful "
            "anyway",
            "- central difference: y(i+1) = 2 y(i) - y(i-1) + a dt^2, "
            "the recurrence in Biggs and in the appendix of the report",
            "- Newmark constant average acceleration is offered as the "
            "alternative. Switch between them under Solver: if the "
            "answers move, the step is too coarse",
        ]))

    st.divider()

    # ---- 8. Reactions ------------------------------------------------
    st.subheader("6. Dynamic Reactions")
    e1, e2 = st.columns(2)
    e1.metric("Peak reaction", "%.0f kN" % (RESP["Vmax_N"] / 1e3))
    e2.metric("Peak resistance", "%.0f kN" % (RES["Ru_N"] / 1e3))
    st.caption("Section 6.4.6. The spring force in the SDOF system is "
               "not the support reaction. Part of the load is carried "
               "by the inertia of the member itself, so the reaction "
               "follows V = c1 R + c2 F with the coefficients in the "
               "table above, and it changes as the member goes plastic. "
               "This is the number the supporting member is designed "
               "for, and it is the input to the next member along the "
               "load path.")
    with st.expander("Show the working", expanded=False):
        el = RES["stages"][-1]["V"]
        pl = RES["plastic"]["V"]
        st.markdown("\n".join([
            "- while elastic: V = %.3f R + %.3f F" % (el[0], el[1]),
            "- once plastic: V = %.3f Ru + %.3f F" % (pl[0], pl[1]),
            "- peak V = **%.0f kN**, against Ru = %.0f kN and Fo = "
            "%.0f kN" % (RESP["Vmax_N"] / 1e3, RES["Ru_N"] / 1e3,
                         LOAD["Fo_N"] / 1e3),
            "- Figure 6.8 derives these coefficients by taking moments "
            "on half the member with the inertia force distributed the "
            "way the assumed shape says it is",
            "- watch the green arrows in the viewer reverse on rebound: "
            "the support is pulled the other way, and a connection "
            "designed only for the downward peak has nothing holding "
            "it",
        ]))

    st.divider()

    # ---- 9. Cross checks ---------------------------------------------
    st.subheader("7. Closed Form Cross Checks")
    ck = []
    ck.append({"Method": "Time integration, this page",
               "mu": "%.3f" % RESP["mu"],
               "Applies": "always"})
    if CHK["mu_impulsive"] is not None:
        ck.append({"Method": "Eq 6.9, impulsive asymptote",
                   "mu": "%.3f" % CHK["mu_impulsive"],
                   "Applies": "td/tn below about 0.1"})
    if CHK["mu_quasi_static"] is not None:
        ck.append({"Method": "Eq 6.10, quasi-static asymptote",
                   "mu": "%.3f" % CHK["mu_quasi_static"],
                   "Applies": "td/tn above about 10"})
    else:
        ck.append({"Method": "Eq 6.10, quasi-static asymptote",
                   "mu": "no bounded answer",
                   "Applies": "needs Fo < Ru"})
    if CHK["mu_manual42"] is not None:
        ck.append({"Method": "Eq 6.11, ASCE Manual 42 transition",
                   "mu": "%.3f" % CHK["mu_manual42"],
                   "Applies": "the whole range, quoted to 5 percent"})
    st.table(ck)
    if RESP["mu"] is not None and RESP["mu"] < 1.0:
        st.info("The member has not yielded, so ductility is below 1 "
                "and none of the closed form expressions apply: they "
                "are all written for a member that has gone plastic. "
                "Raise the pressure until mu passes 1 and the "
                "comparison becomes meaningful.")
    elif CHK["manual42_diff_pct"] is not None:
        st.caption("Eq 6.11 differs from the time integration by %.1f "
                   "percent here. Be careful reading that number: the "
                   "5 percent the chapter quotes is on Fo/Rm for a "
                   "given ductility, and inverting the formula to get "
                   "ductility magnifies the error, badly so near the "
                   "elastic end." % CHK["manual42_diff_pct"])

    st.divider()

    with st.expander("Sources for this page", expanded=False):
        st.table([
            {"Source": "ASCE, Design of Blast-Resistant Buildings in "
                       "Petrochemical Facilities, Chapter 6",
             "Used for": "The method and its sequence: Eq 6.1 to 6.11, "
                         "Figures 6.3, 6.4 and 6.8, and Tables 6.1 and "
                         "6.2. Read the chapter itself; this page "
                         "implements the method, it does not reproduce "
                         "the text."},
            {"Source": "TM 5-856", "Used for":
                "The origin of the transformation factors and dynamic "
                "reaction coefficients tabulated in Tables 6.1 and 6.2. "
                "A US Army technical manual, in the public domain."},
            {"Source": "Biggs, Introduction to Structural Dynamics",
             "Used for": "The equivalent SDOF derivation and the "
                         "central difference recurrence used here."},
            {"Source": "UFC 3-340-02", "Used for":
                "The same transformation factors, and the equivalent "
                "elastic deflection convention used for yE."},
            {"Source": "ASCE Manual 42", "Used for":
                "Eq 6.11, the empirical transition between the "
                "impulsive and quasi-static asymptotes."},
            {"Source": "CISC SST12.1", "Used for":
                "Every section property on this page."},
        ])
        st.caption("Not implemented on purpose: Table 6.3, the "
                   "simple-fixed case. Its resistance column could not "
                   "be read with confidence from the scan available, "
                   "and a factor guessed off a blurred table is worse "
                   "than a gap. Send a clean copy and it goes in.")
        st.caption("Also out of scope for this page: the acceptance "
                   "criteria themselves, which are Chapter 5. This "
                   "page tells you the ductility and the rotation; it "
                   "does not tell you whether they are allowed.")
