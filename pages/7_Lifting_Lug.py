"""
pages/7_Lifting_Lug.py

CSA S16 lifting lug calculator.

Layout: the 3D model sits on the left and redraws on every keystroke, the
design inputs sit on the right, and the check groups run down the left
under the model. There is one set of inputs. The calculations read them
and the model reads the calculations, so nothing on the page can drift
out of step with anything else.
"""

import streamlit as st

st.set_page_config(page_title="Lifting Lug - CSA S16",
                   page_icon=":link:", layout="wide")

from _theme import (apply_theme, render_sidebar_logo, render_footer,
                    gate_disclaimer)

gate_disclaimer()
apply_theme()
render_sidebar_logo()
render_footer()

import lug_design
import viewer_3d_lug

st.title("Lifting Lug Design")
st.caption("CSA S16 - lug plate, weld, cap plate with bolt prying, and pin")

DEF = lug_design.SOURCE_CASE


def num(label, key, default, step=1.0, minv=0.0, fmt="%.1f", help=None):
    return st.number_input(label, min_value=minv, value=float(default),
                           step=step, format=fmt, key="lug_" + key, help=help)


col_model, col_in = st.columns([2, 1], gap="large")

# ---------------------------------------------------------------------
# INPUTS - right hand column, the only place anything is entered
# ---------------------------------------------------------------------
with col_in:
    st.subheader("Design Inputs")

    with st.expander("Lifting load", expanded=True):
        T_tons = num("T, service sling load (tonnes)", "T", DEF["T_tons"],
                     0.01, 0.0, "%.2f",
                     help="Maximum service sling load from the lift analysis")
        LDf = num("LDf, lifting device factor", "LDf", DEF["LDf"], 0.1, 1.0,
                  "%.2f", help="H3.1.1 minimum lifting device load factor")
        If = num("If, impact factor", "If", DEF["If"], 0.05, 1.0, "%.2f",
                 help="H2.1 impact factor")
        Sf = num("Sf, sling distribution factor", "Sf", DEF["Sf"], 0.05, 1.0,
                 "%.2f", help="H2.1 unequal sling distribution, 0.70/0.50")
        sling_angle = num("Sling angle from horizontal (deg)", "sang", 60.0,
                          5.0, 5.0, "%.0f",
                          help="Model geometry only, not used in the checks")

    with st.expander("Lug plate", expanded=True):
        L2 = num("L2, length at base", "L2", DEF["L2"], 5.0, 1.0)
        H2 = num("H2, base to hole centre", "H2", DEF["H2"], 5.0, 1.0)
        H1 = num("H1, hole centre to top edge", "H1", DEF["H1"], 5.0, 1.0)
        tp2 = num("tp2, lug thickness", "tp2", DEF["tp2"], 1.0, 1.0)

    with st.expander("Pin and cheek plates", expanded=True):
        Dpin = num("Dpin, pin diameter", "Dpin", DEF["Dpin"], 1.0, 1.0)
        Dhole = num("Dhole, hole diameter", "Dhole", DEF["Dhole"], 1.0, 1.0)
        Dcheekp = num("Dcheekp, cheek plate diameter", "Dch", DEF["Dcheekp"],
                      5.0, 1.0)
        tp3 = num("tp3, cheek plate thickness", "tp3", DEF["tp3"], 1.0, 0.0)
        Fypin = num("Fy pin (MPa)", "Fypin", DEF["Fypin"], 5.0, 100.0)
        Fupin = num("Fu pin (MPa)", "Fupin", DEF["Fupin"], 5.0, 100.0)

    with st.expander("Cap plate and bolts", expanded=False):
        L1 = num("L1, cap plate length", "L1", DEF["L1"], 5.0, 1.0)
        W1 = num("W1, cap plate width", "W1", DEF["W1"], 5.0, 1.0)
        tp1 = num("tp1, cap plate thickness", "tp1", DEF["tp1"], 1.0, 1.0)
        Db = num("Db, bolt diameter", "Db", DEF["Db"], 2.0, 1.0)
        Nrow = num("Nrow, number of bolt rows", "Nrow", DEF["Nrow"], 1.0, 1.0,
                   "%.0f")
        s_pitch = num("s, pitch along L1", "s", DEF["s"], 5.0, 1.0)
        g_gauge = num("g, gauge across W1", "g", DEF["g"], 5.0, 1.0)
        Fub = num("Fu bolt (MPa)", "Fub", DEF["Fub"], 10.0, 100.0)

    with st.expander("Weld and materials", expanded=False):
        w1 = num("w1, fillet weld leg", "w1", DEF["w1"], 1.0, 0.0)
        Xu = num("Xu, electrode strength (MPa)", "Xu", DEF["Xu"], 10.0, 100.0)
        Fyp = num("Fy plate (MPa)", "Fyp", DEF["Fyp"], 5.0, 100.0)
        Fup = num("Fu plate (MPa)", "Fup", DEF["Fup"], 5.0, 100.0)

    with st.expander("Resistance factors", expanded=False):
        phi = num("phi", "phi", DEF["phi"], 0.05, 0.1, "%.2f")
        phiw = num("phi w, weld", "phiw", DEF["phiw"], 0.01, 0.1, "%.2f")
        phib = num("phi b, bolt", "phib", DEF["phib"], 0.05, 0.1, "%.2f")
        phibr = num("phi br, bearing", "phibr", DEF["phibr"], 0.01, 0.1,
                    "%.2f")

    with st.expander("Method", expanded=False):
        pry_mode = st.radio(
            "Prying a' definition",
            options=["cisc", "sheet"],
            format_func=lambda k: ("CISC:  a' = a + Db/2  (recommended)"
                                   if k == "cisc"
                                   else "Source sheet:  a' = a - Db/2"),
            index=0, key="lug_prymode",
            help="The source workbook labels a' = a + Db/2 but is written "
                 "a - Db/2. CISC is the correct form. The sheet option is "
                 "kept so the original numbers can be reproduced.")

INP = {
    "Dpin": Dpin, "Dhole": Dhole, "Dcheekp": Dcheekp,
    "Fypin": Fypin, "Fupin": Fupin,
    "tp1": tp1, "L1": L1, "W1": W1,
    "Fyp": Fyp, "Fup": Fup, "phi": phi, "phiw": phiw,
    "Xu": Xu, "w1": w1,
    "tp2": tp2, "H1": H1, "H2": H2, "L2": L2, "tp3": tp3,
    "Db": Db, "Nrow": Nrow, "s": s_pitch, "g": g_gauge,
    "Fub": Fub, "phib": phib, "phibr": phibr,
    "T_tons": T_tons, "If": If, "Sf": Sf, "LDf": LDf,
}

try:
    R = lug_design.design_lug(INP, prying_mode=pry_mode)
except Exception as exc:
    with col_model:
        st.error("Calculation error: " + str(exc))
    st.stop()

F = R["forces"]
WM = R["welds"]["weld_metal"]
BM = R["welds"]["base_metal"]
LG = R["lug"]
PR = R["prying"]
PN = R["pin"]

# Each check is tagged with the part of the assembly it governs, which is
# how the model knows what to colour.
CHECKS = [
    {"key": "weld_metal", "label": "Weld metal", "component": "weld",
     "uc": WM["uc"], "verdict": WM["verdict"]},
    {"key": "base_metal", "label": "Weld base metal", "component": "weld",
     "uc": BM["uc"], "verdict": BM["verdict"]},
    {"key": "lug", "label": "Lug plate section", "component": "lug",
     "uc": LG["uc"], "verdict": LG["verdict"]},
    {"key": "conn", "label": "Connection capacity", "component": "cap",
     "uc": PR["uc_conn"], "verdict": PR["conn_verdict"]},
    {"key": "bolt", "label": "Bolt with prying", "component": "bolt",
     "uc": PR["uc_bolt"], "verdict": PR["bolt_verdict"]},
    {"key": "pin", "label": "Pin", "component": "pin",
     "uc": PN["uc"], "verdict": PN["verdict"]},
]
# The cheek plates carry the pin bearing and tear-out path with the lug.
CHECKS.append({"key": "cheek", "label": "Pin bearing and tear-out",
               "component": "cheek", "uc": PN["uc"],
               "verdict": PN["verdict"]})


def prow(group, symbol, value, unit, nd=1):
    try:
        v = "{:,.{}f}".format(float(value), nd)
    except (TypeError, ValueError):
        v = str(value)
    return {"group": group, "symbol": symbol, "value": v, "unit": unit}


PROPS = [
    prow("Load", "T", T_tons, "t", 2),
    prow("Load", "Tf", F["Tf_kN"], "kN"),
    prow("Load", "Vf", F["Rf_kN"], "kN"),
    prow("Load", "Mfx", F["Mfx_lug_kNm"], "kN-m", 2),
    prow("Lug", "L2", L2, "mm", 0),
    prow("Lug", "H1", H1, "mm", 0),
    prow("Lug", "H2", H2, "mm", 0),
    prow("Lug", "tp2", tp2, "mm", 0),
    prow("Pin", "Dpin", Dpin, "mm", 0),
    prow("Pin", "Dhole", Dhole, "mm", 0),
    prow("Pin", "Vr", PN["Vr_kN"], "kN"),
    prow("Cap", "L1", L1, "mm", 0),
    prow("Cap", "W1", W1, "mm", 0),
    prow("Cap", "tp1", tp1, "mm", 0),
    prow("Bolts", "Db", Db, "mm", 0),
    prow("Bolts", "Trb", PR["Trb_kN"], "kN"),
    prow("Weld", "w1", w1, "mm", 0),
    prow("Weld", "a", WM["a_mm"], "mm", 2),
]

# ---------------------------------------------------------------------
# MODEL AND RESULTS - left hand column
# ---------------------------------------------------------------------
with col_model:
    viewer_3d_lug.render_lug(
        dict(INP, label="Lifting lug"),
        height=560,
        checks=CHECKS,
        results={"Tf_kN": F["Tf_kN"],
                 "governing_name": R["governing_name"],
                 "governing_uc": R["governing_uc"],
                 "overall": R["overall"]},
        props=PROPS,
        load={"sling_angle_deg": sling_angle, "Tf_kN": F["Tf_kN"]},
        show_diagnostics=False)

    if R["overall"] == "OK":
        st.success("All checks pass. Governing: %s at %.3f"
                   % (R["governing_name"], R["governing_uc"]))
    else:
        st.error("One or more checks fail. Governing: %s at %.3f"
                 % (R["governing_name"], R["governing_uc"]))

    sc = st.columns(3)
    sc[0].metric("Factored load Tf", "%.1f kN" % F["Tf_kN"])
    sc[1].metric("Governing U/C", "%.3f" % R["governing_uc"])
    sc[2].metric("Governing check", R["governing_name"])

    st.divider()

    # ---- A. Design forces --------------------------------------------
    st.subheader("A. Design Forces")
    a1, a2 = st.columns(2)
    a1.metric("Service load Ts", "%.2f t" % F["Ts_tons"])
    a2.metric("Factored load Tf", "%.2f kN" % F["Tf_kN"])
    with st.expander("Show calculation steps", expanded=False):
        st.markdown("\n".join([
            "- Governing load factor: max(LDf, If x Sf) = max(%.2f, %.2f) "
            "= **%.2f**" % (LDf, If * Sf, F["total_factor"]),
            "- Ts = T x factor = %.2f x %.2f = **%.2f t**"
            % (T_tons, F["total_factor"], F["Ts_tons"]),
            "- Tf = Ts x 1.30 x 9.807 = **%.2f kN**" % F["Tf_kN"],
            "- Vfx = Vfy = 0.10 Tf = %.2f kN" % F["Vfx_kN"],
            "- Rf = sqrt(Vfx^2 + Vfy^2) = **%.2f kN**" % F["Rf_kN"],
            "- At the lug base: Mfx = H2 x Vfy = %.3f kN-m, "
            "Mfy = H2 x Vfx = %.3f kN-m"
            % (F["Mfx_lug_kNm"], F["Mfy_lug_kNm"]),
            "- At the top of beam: Mfx = (H2 + tp1) Vfy = %.3f kN-m"
            % F["Mfx_beam_kNm"],
        ]))

    st.divider()

    # ---- B. Weld ------------------------------------------------------
    st.subheader("B. Lug to Cap Plate Weld")
    b1, b2 = st.columns(2)
    with b1:
        st.markdown("**Weld metal** - cl 13.13.2.2(b)")
        st.metric("U/C", "%.3f" % WM["uc"], WM["verdict"])
        st.caption("a = 0.707 w1 = %.2f mm, sigma_t = %.1f MPa, "
                   "sigma_all = %.1f MPa, theta = %.1f deg"
                   % (WM["a_mm"], WM["sigma_t_MPa"], WM["sigma_all_MPa"],
                      WM["theta_deg"]))
    with b2:
        st.markdown("**Base metal** - cl 13.13.2.2(a)")
        st.metric("U/C", "%.3f" % BM["uc"], BM["verdict"])
        st.caption("a = w1 = %.2f mm, sigma_t = %.1f MPa, "
                   "sigma_all = 0.67 phi_w Fu = %.1f MPa"
                   % (BM["a_mm"], BM["sigma_t_MPa"], BM["sigma_all_MPa"]))
    with st.expander("Show calculation steps", expanded=False):
        for name, W in (("Weld metal", WM), ("Base metal", BM)):
            st.markdown("**%s**" % name)
            st.markdown("\n".join([
                "- A = 2 a L2 = %.1f mm2" % W["A_mm2"],
                "- Sx-x = %.0f mm3, Sy-y = %.0f mm3"
                % (W["Sxx_mm3"], W["Syy_mm3"]),
                "- sigma1 = Mfy/Sy-y + Mfx/Sx-x = %.2f MPa" % W["sigma1_MPa"],
                "- sigma2 = Tf/A = %.2f MPa" % W["sigma2_MPa"],
                "- sigma_n = %.2f MPa, tau = Rf/A = %.2f MPa"
                % (W["sigma_n_MPa"], W["tau_MPa"]),
                "- sigma_t = sqrt(sigma_n^2 + tau^2) = %.2f MPa"
                % W["sigma_t_MPa"],
                "- theta = %.2f deg, sigma_all = %.2f MPa (%s)"
                % (W["theta_deg"], W["sigma_all_MPa"], W["clause"]),
                "- U/C = **%.4f  %s**" % (W["uc"], W["verdict"]),
            ]))
            st.markdown("")

    st.divider()

    # ---- C. Lug plate section -----------------------------------------
    st.subheader("C. Lug Plate at Cap Plate")
    st.metric("U/C, combined axial and biaxial bending", "%.3f" % LG["uc"],
              LG["verdict"])
    st.caption("Tr = %.0f kN, Mrx = %.1f kN-m, Mry = %.1f kN-m - %s"
               % (LG["Tr_kN"], LG["Mrx_kNm"], LG["Mry_kNm"], LG["clause"]))
    with st.expander("Show calculation steps", expanded=False):
        st.markdown("\n".join([
            "- A = L2 tp2 = %.0f mm2" % LG["A_mm2"],
            "- Sx-x = tp2 L2^2 / 6 = %.0f mm3" % LG["Sxx_mm3"],
            "- Sy-y = tp2^2 L2 / 6 = %.0f mm3" % LG["Syy_mm3"],
            "- Tr = phi A Fy = **%.1f kN** (cl 13.2(a)(i))" % LG["Tr_kN"],
            "- Mrx = phi Sx-x Fy = **%.2f kN-m** (cl 13.5(b))" % LG["Mrx_kNm"],
            "- Mry = phi Sy-y Fy = **%.2f kN-m**" % LG["Mry_kNm"],
            "- Tf/Tr + Mfx/Mrx + Mfy/Mry = **%.4f  %s**"
            % (LG["uc"], LG["verdict"]),
        ]))

    st.divider()

    # ---- D. Cap plate and prying --------------------------------------
    st.subheader("D. Cap Plate Thickness and Bolt Prying")
    d1, d2, d3 = st.columns(3)
    d1.metric("Plate thickness", PR["plate_verdict"],
              "tmax = %.2f mm vs tp1 = %.0f mm"
              % (PR["t_max_mm"], PR["tp1_mm"]))
    d2.metric("Connection U/C", "%.3f" % PR["uc_conn"], PR["conn_verdict"])
    d3.metric("Bolt U/C", "%.3f" % PR["uc_bolt"], PR["bolt_verdict"])
    if PR["mode"] == "cisc":
        st.caption("a' = a + Db/2 per CISC, with a limited to 1.25 b. "
                   "The source workbook's formula gives a smaller a' and a "
                   "slightly higher connection U/C.")
    else:
        st.caption("Reproducing the source workbook: a' = a - Db/2.")
    with st.expander("Show calculation steps", expanded=False):
        st.markdown("\n".join([
            "- a = (W1 - g)/2 = %.1f mm, b = (W1 - tp2)/2 - a = %.1f mm"
            % (PR["a_mm"], PR["b_mm"]),
            "- a used = %.1f mm, a' = %.1f mm, b' = %.1f mm"
            % (PR["a_eff_mm"], PR["a_prime_mm"], PR["b_prime_mm"]),
            "- p = L1/Nrow = %.1f mm, hole d' = Db + 2 = %.1f mm"
            % (PR["p_mm"], PR["d_hole_mm"]),
            "- delta = 1 - d'/p = %.4f  (eq 2)" % PR["delta"],
            "- K = 4 b' x 10^3 / (phi p Fyp) = %.4f  (eq 1)" % PR["K"],
            "- Pfb = Tf/(2 Nrow) = %.2f kN over %.0f bolts"
            % (PR["Pfb_kN"], PR["n_bolts"]),
            "- tmin (alpha=1) = %.2f mm, tmax (alpha=0) = %.2f mm  (eq 3)"
            % (PR["t_min_mm"], PR["t_max_mm"]),
            "- Trb = 0.75 phi_b (pi Db^2/4) Fub = **%.2f kN** (cl 13.12.1.2)"
            % PR["Trb_kN"],
            "- alpha (connection) = %.4f, used %.4f  (eq 4)"
            % (PR["alpha_conn"], PR["alpha_conn_used"]),
            "- Fr = (tp1^2/K)(1 + delta alpha)(2 Nrow) = **%.1f kN**  (eq 5)"
            % PR["Fr_kN"],
            "- Tf/Fr = **%.4f  %s**" % (PR["uc_conn"], PR["conn_verdict"]),
            "- alpha (bolt) = %.4f, used %.4f" % (PR["alpha_bolt"],
                                                  PR["alpha_bolt_used"]),
            "- Tfb = %.2f kN, Tfb/Trb = **%.4f  %s**  (eq 7)"
            % (PR["Tfb_kN"], PR["uc_bolt"], PR["bolt_verdict"]),
        ]))

    st.divider()

    # ---- E. Pin --------------------------------------------------------
    st.subheader("E. Pin")
    st.metric("U/C", "%.3f" % PN["uc"], PN["verdict"])
    st.caption("Vr = %.1f kN governed by %s. Vf = Tf = %.1f kN. %s"
               % (PN["Vr_kN"], PN["governing"], PN["Vf_kN"], PN["clauses"]))
    e1, e2, e3 = st.columns(3)
    e1.metric("Vr1 shear", "%.0f kN" % PN["Vr1_kN"])
    e2.metric("Vr2 bearing", "%.0f kN" % PN["Vr2_kN"])
    e3.metric("Vr3 tear-out", "%.0f kN" % PN["Vr3_kN"])
    with st.expander("Show calculation steps", expanded=False):
        st.markdown("\n".join([
            "- Apin = pi Dpin^2 / 4 = %.1f mm2" % PN["Apin_mm2"],
            "- Vr1 = 0.66 phi_b n m Apin Fy = **%.1f kN**  "
            "(cl 13.12.1.1(b), double shear m = 2)" % PN["Vr1_kN"],
            "- bearing thickness 2 tp3 + tp2 = %.0f mm" % PN["t_bearing_mm"],
            "- Vr2 = 3 phi_br (2 tp3 + tp2) Dpin n Fu = **%.1f kN**  "
            "(cl 13.10(c))" % PN["Vr2_kN"],
            "- Vr3 = 2 (0.60 phi)[(Dcheekp/2 - Dhole/2)(2 tp3 + tp2) "
            "+ (H1 - Dcheekp/2) tp2] Fu = **%.1f kN**  (cl 13.11(a)(ii))"
            % PN["Vr3_kN"],
            "- Vr = min = **%.1f kN**, Vf/Vr = **%.4f  %s**"
            % (PN["Vr_kN"], PN["uc"], PN["verdict"]),
        ]))

    st.divider()
    with st.expander("Summary table", expanded=True):
        rows = [{"Check": n, "U/C": ("-" if u is None else "%.4f" % u),
                 "Result": v} for n, u, v in R["checks"]]
        st.table(rows)
