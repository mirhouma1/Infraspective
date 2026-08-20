"""
pages/10_Lifting_Eye.py

CSA S16 lifting eye calculator.

A lifting eye is a hole bored through the web or cap plate of a member,
with doubler plates welded on both faces to make up the thickness lost
at the hole. There is no projecting plate, no cheek plates and no
bolted cap, so nothing pries and there is no lug bending at a base.

What is different from a padeye, and why it needs its own page:

    the load is shared between the web and the doublers in proportion
    to thickness, so the doubler weld has to deliver the doublers'
    share into them or they do not participate

    below the doublers the section reverts to the bare member and has
    to carry the whole load on its own gross area

    the tear-out path runs partly through web plus doublers and partly
    through the web alone, wherever the doubler stops short of the
    free edge

Clause coverage. Every resistance is computed from the clause named
beside it:

    Cl. 13.2 (a)    member below the doublers, gross section
    Cl. 13.2 (b)    tension at the hole, three branches
    Cl. 13.10 (a)   bearing on an accurately fitted pin
    Cl. 13.11       tear-out above the hole, and its closing Note
    Cl. 13.12.1.1   pin shear
    Cl. 13.12.1.2   bearing of a pin in a clearance hole
    Cl. 13.13.2.2   doubler weld

ASCII only. Straight quotes only. No markdown inside code.
"""

import math

import streamlit as st

st.set_page_config(page_title="Lifting Eye - Infraspective",
                   page_icon=":o:", layout="wide")

from _theme import (apply_theme, render_sidebar_logo, render_footer,
                    gate_disclaimer, render_page_title)

gate_disclaimer()
apply_theme()
render_sidebar_logo()
render_footer()

import eye_design

render_page_title(
    "Lifting Eye Design",
    clauses=("Cl. 13.2 (a) and (b)  |  Cl. 13.10  |  Cl. 13.11  |  "
             "Cl. 13.12  |  Cl. 13.13.2.2"),
    intro=("Bored hole with doubler plates both faces. Tension at the "
           "hole, tear-out, bearing, pin, the member below the "
           "doublers, and the doubler weld."),
)

DEF = eye_design.SOURCE_CASE_EYE


def num(label, key, default, step=1.0, minv=0.0, fmt="%.1f", help=None):
    return st.number_input(label, min_value=minv, value=float(default),
                           step=step, format=fmt, key="eye_" + key,
                           help=help)


col_dwg, col_in = st.columns([2, 1], gap="large")

# ---------------------------------------------------------------------
# INPUTS
# ---------------------------------------------------------------------
with col_in:
    st.subheader("Design Inputs")

    with st.expander("Lifting load", expanded=True):
        T_tons = num("T, service sling load (tonnes)", "T",
                     DEF["T_tons"], 0.01, 0.0, "%.2f")
        LDf = num("LDf, lifting device factor", "LDf", DEF["LDf"], 0.1,
                  1.0, "%.2f")
        If = num("If, impact factor", "If", DEF["If"], 0.05, 1.0, "%.2f")
        Sf = num("Sf, sling distribution factor", "Sf", DEF["Sf"], 0.05,
                 1.0, "%.2f")

    with st.expander("Pin and hole", expanded=True):
        Dpin = num("Dpin, shackle pin diameter", "Dpin", DEF["Dpin"],
                   1.0, 1.0)
        Dhole = num("Dhole, bored hole diameter", "Dhole", DEF["Dhole"],
                    1.0, 1.0)
        e_top = num("e_top, hole centre to the free edge above", "etop",
                    DEF["e_top"], 5.0, 1.0,
                    help="Measured from the hole centre up to the top "
                         "edge of the plate. This sets the tear-out "
                         "path.")
        pin_fit = st.radio(
            "Pin fit", ["clearance", "fitted"], horizontal=True,
            index=0, key="eye_pinfit",
            format_func=lambda k: ("Clearance - Cl. 13.12.1.2"
                                   if k == "clearance"
                                   else "Fitted - Cl. 13.10(a)"))
        Fypin = num("Fy pin (MPa)", "Fypin", DEF["Fypin"], 5.0, 100.0)
        Fupin = num("Fu pin (MPa)", "Fupin", DEF["Fupin"], 5.0, 100.0)

    with st.expander("Member being bored", expanded=True):
        tw = num("tw, web or cap plate thickness", "tw", DEF["tw"], 0.5,
                 1.0, "%.1f")
        W_web = num("W_web, clear width available", "Wweb",
                    DEF["W_web"], 5.0, 1.0,
                    help="Clear width of web between the flange "
                         "fillets, or the width of the cap plate.")
        Ag_member = num("Ag, gross area of the member below (mm2)",
                        "Agm", DEF["Ag_member"], 100.0, 1.0, "%.0f",
                        help="Used for the Cl. 13.2(a) check on the "
                             "section below the doublers.")
        Fy_col = num("Fy member (MPa)", "Fycol", DEF["Fy_col"], 5.0,
                     100.0)
        Fu_col = num("Fu member (MPa)", "Fucol", DEF["Fu_col"], 5.0,
                     100.0)

    with st.expander("Doubler plates", expanded=True):
        td = num("td, doubler thickness, each face", "td", DEF["td"],
                 1.0, 0.0)
        W_d = num("W_d, doubler width", "Wd", DEF["W_d"], 5.0, 1.0)
        L_d = num("L_d, doubler height", "Ld", DEF["L_d"], 5.0, 1.0)
        e_dtop = num("e_dtop, hole centre to the doubler top edge",
                     "edtop", DEF["e_dtop"], 5.0, 0.0,
                     help="Where the doubler stops short of the free "
                          "edge, the rest of the tear-out path runs "
                          "through the web alone.")
        Fy_d = num("Fy doubler (MPa)", "Fyd", DEF["Fy_d"], 5.0, 100.0)
        Fu_d = num("Fu doubler (MPa)", "Fud", DEF["Fu_d"], 5.0, 100.0)

    with st.expander("Doubler weld", expanded=False):
        w_weld = num("w, fillet weld leg", "w", DEF["w_weld"], 1.0, 0.0)
        Xu = num("Xu, electrode strength (MPa)", "Xu", DEF["Xu"], 10.0,
                 100.0)
        weld_top = st.checkbox(
            "Include the run along the top edge", value=False,
            key="eye_weldtop",
            help="Normally discounted. The tear-out path crosses it, "
                 "so it cannot be relied on to transfer load in the "
                 "same direction.")
        use_Mw = st.checkbox("Apply Mw, multi-orientation reduction",
                             value=True, key="eye_useMw")

    with st.expander("Resistance factors", expanded=False):
        phi = num("phi", "phi", DEF["phi"], 0.05, 0.1, "%.2f")
        phiu = num("phi u, fracture", "phiu", DEF["phiu"], 0.05, 0.1,
                   "%.2f")
        phiw = num("phi w, weld", "phiw", DEF["phiw"], 0.01, 0.1, "%.2f")
        phib = num("phi b, bolt", "phib", DEF["phib"], 0.05, 0.1, "%.2f")
        phibr = num("phi br, bearing", "phibr", DEF["phibr"], 0.01, 0.1,
                    "%.2f")

    with st.expander("Method", expanded=False):
        Ut = num("Ut, Cl. 13.11 efficiency factor", "Ut", DEF["Ut"],
                 0.05, 0.1, "%.2f")
        An_t = num("An, tension area for Cl. 13.11 (mm2)", "Ant", 0.0,
                   10.0, 0.0, "%.0f",
                   help="Leave at zero. The closing Note to Cl. 13.11 "
                        "allows the shear term alone as the plate "
                        "tear-out resistance.")

INP = {
    "T_tons": T_tons, "LDf": LDf, "If": If, "Sf": Sf,
    "Dpin": Dpin, "Dhole": Dhole, "e_top": e_top, "e_dtop": e_dtop,
    "tw": tw, "W_web": W_web, "Ag_member": Ag_member,
    "Fy_col": Fy_col, "Fu_col": Fu_col,
    "td": td, "W_d": W_d, "L_d": L_d, "Fy_d": Fy_d, "Fu_d": Fu_d,
    "w_weld": w_weld, "Xu": Xu, "weld_top": weld_top, "use_Mw": use_Mw,
    "Fypin": Fypin, "Fupin": Fupin,
    "phi": phi, "phiu": phiu, "phiw": phiw, "phib": phib,
    "phibr": phibr, "pin_fit": pin_fit, "Ut": Ut,
    "An_tension_mm2": An_t,
}

try:
    R = eye_design.design_eye(INP)
except Exception as exc:
    with col_dwg:
        st.error("Calculation error: " + str(exc))
    st.stop()

F = R["forces"]
SHR = R["share"]
HS = R["hole"]
TO = R["tearout"]
BR = R["bearing"]
PS = R["pin_shear"]
MB = R["member"]
DW = R["weld"]
HF = R["flexure"]
GC = R["geom_check"]


# ---------------------------------------------------------------------
# Elevation, drawn from the same numbers the checks use
# ---------------------------------------------------------------------
def elevation_svg(width=620, height=440):
    r = Dhole / 2.0
    span_x = max(W_web, W_d) * 1.15
    span_y = (e_top + L_d) * 1.35
    sc = min(width * 0.80 / span_x, height * 0.80 / span_y) \
        if span_x > 0 and span_y > 0 else 1.0
    cx, cy = width / 2.0, height * 0.42

    def X(x):
        return cx + x * sc

    def Y(y):
        return cy - y * sc

    p = []
    p.append('<svg viewBox="0 0 %d %d" width="100%%" '
             'xmlns="http://www.w3.org/2000/svg">' % (width, height))
    p.append('<rect width="%d" height="%d" fill="#0d1117"/>'
             % (width, height))

    # web outline
    p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
             'fill="#161b22" stroke="#30363d" stroke-width="1.2"/>'
             % (X(-W_web / 2.0), Y(e_top), W_web * sc,
                (e_top + L_d * 0.9) * sc))
    # doubler outline
    p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
             'fill="#1f2933" fill-opacity="0.85" stroke="#58a6ff" '
             'stroke-width="1.4" stroke-dasharray="5 3"/>'
             % (X(-W_d / 2.0), Y(e_dtop), W_d * sc, L_d * sc))
    p.append('<text x="%.1f" y="%.1f" fill="#58a6ff" font-size="11" '
             'font-family="system-ui">doubler 2 - PL%.0f</text>'
             % (X(-W_d / 2.0) + 4, Y(e_dtop) - 5, td))

    # hole
    p.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#0d1117" '
             'stroke="#c9d1d9" stroke-width="1.4"/>'
             % (X(0), Y(0), r * sc))
    # pin
    p.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" '
             'stroke="#c9a227" stroke-width="1.2" '
             'stroke-dasharray="3 2"/>'
             % (X(0), Y(0), Dpin / 2.0 * sc))

    # tear-out tangent planes
    if e_top > r > 0:
        alpha = math.acos(r / e_top)
        for sgn in (1.0, -1.0):
            a_t = math.pi / 2.0 + sgn * alpha
            tx, ty = r * math.cos(a_t), r * math.sin(a_t)
            p.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                     'stroke="#ff7b72" stroke-width="2"/>'
                     % (X(0), Y(e_top), X(tx), Y(ty)))
        p.append('<text x="%.1f" y="%.1f" fill="#ff7b72" font-size="11" '
                 'font-family="system-ui">tear-out k = %.0f</text>'
                 % (X(r * 1.2), Y(e_top * 0.55), HS["k_mm"]))

    # net tension section through the hole centre
    p.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
             'stroke="#ffa657" stroke-width="2" '
             'stroke-dasharray="6 3"/>'
             % (X(-W_web / 2.0), Y(0), X(-r), Y(0)))
    p.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
             'stroke="#ffa657" stroke-width="2" '
             'stroke-dasharray="6 3"/>'
             % (X(r), Y(0), X(W_web / 2.0), Y(0)))
    p.append('<text x="%.1f" y="%.1f" fill="#ffa657" font-size="11" '
             'font-family="system-ui">Anet section</text>'
             % (X(-W_web / 2.0) + 4, Y(0) - 6))

    # bearing arc on the loaded half of the bore
    p.append('<path d="M %.1f %.1f A %.1f %.1f 0 0 1 %.1f %.1f" '
             'stroke="#7ee787" stroke-width="3" fill="none"/>'
             % (X(-r), Y(0), r * sc, r * sc, X(r), Y(0)))

    # load arrow
    p.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
             'stroke="#7ee787" stroke-width="2"/>'
             % (X(0), Y(0), X(0), Y(e_top + L_d * 0.30)))
    p.append('<text x="%.1f" y="%.1f" fill="#7ee787" font-size="12" '
             'font-family="system-ui">Tf = %.0f kN</text>'
             % (X(0) + 8, Y(e_top + L_d * 0.28), F["Tf_kN"]))

    p.append('</svg>')
    return "".join(p)


# ---------------------------------------------------------------------
# RESULTS
# ---------------------------------------------------------------------
with col_dwg:
    st.markdown(elevation_svg(), unsafe_allow_html=True)
    st.caption("Elevation drawn from the same numbers the checks use. "
               "Red is the tear-out path, the line from the free edge "
               "tangent to the hole. Orange is the net tension section. "
               "Green is the loaded half of the bore.")

    if R["overall"] == "OK":
        st.success("All checks pass. Governing: %s at %.3f"
                   % (R["governing_name"], R["governing_uc"]))
    else:
        st.error("One or more checks fail. Governing: %s at %.3f"
                 % (R["governing_name"], R["governing_uc"]))

    sc0 = st.columns(4)
    sc0[0].metric("Factored load Tf", "%.1f kN" % F["Tf_kN"])
    sc0[1].metric("Effective thickness", "%.1f mm" % SHR["t_eff_mm"])
    sc0[2].metric("Governing U/C", "%.3f" % R["governing_uc"])
    sc0[3].metric("Governing check", R["governing_name"][:22])

    st.warning("Bore the lift hole only after the doubler plates are "
               "fully welded to the member. Drilling first leaves the "
               "hole out of position once the weld shrinks, and the "
               "doublers cannot then be relied on to share the load.")

    st.divider()

    # ---- 0. Proportioning ---------------------------------------------
    st.subheader("0. Proportioning")
    if GC["all_ok"]:
        st.success("All proportioning rules satisfied.")
    else:
        st.warning("One or more proportioning rules are not satisfied. "
                   "These are detailing rules in general use for pin "
                   "connected plates, not clauses of S16, so treat "
                   "them as items for review.")
    st.table([{"Item": i["item"], "Required": i["required"],
               "Actual": i["value"],
               "Result": "OK" if i["ok"] else "REVIEW"}
              for i in GC["items"]])

    st.divider()

    # ---- A. Forces and load sharing ------------------------------------
    st.subheader("A. Design Forces and Load Sharing")
    a1, a2, a3 = st.columns(3)
    a1.metric("Service load Ts", "%.2f t" % F["Ts_tons"])
    a2.metric("Factored load Tf", "%.1f kN" % F["Tf_kN"])
    a3.metric("Doublers carry", "%.0f %%"
              % (100.0 * SHR["frac_doubler"]))
    st.caption("The doublers only carry what the weld can deliver into "
               "them. Their share is taken in proportion to thickness, "
               "which is the usual assumption for a symmetric pack in "
               "direct tension.")
    with st.expander("Show calculation steps", expanded=False):
        st.markdown("\n".join([
            "- Governing load factor: max(LDf, If x Sf) = max(%.2f, "
            "%.2f) = **%.2f**" % (LDf, If * Sf, F["total_factor"]),
            "- Ts = T x factor = %.2f x %.2f = **%.2f t**"
            % (T_tons, F["total_factor"], F["Ts_tons"]),
            "- Tf = Ts x 1.30 x 9.807 = **%.1f kN**" % F["Tf_kN"],
            "- t_eff = tw + 2 td = %.1f + 2(%.1f) = **%.1f mm**"
            % (SHR["tw_mm"], SHR["td_mm"], SHR["t_eff_mm"]),
            "- Doubler share = 2 td / t_eff = **%.3f**, so "
            "P_doubler = %.1f kN and P_web = %.1f kN"
            % (SHR["frac_doubler"], SHR["P_doubler_kN"],
               SHR["P_web_kN"]),
        ]))

    st.divider()

    # ---- B. Tension at the hole ----------------------------------------
    st.subheader("B. Tension at the Hole")
    st.caption("Cl. 13.2 (b). A bored eye is a pin connection, so the "
               "section at the hole is the least of three branches.")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("(i) phi Ag Fy", "%.0f kN" % HS["Tr_i_kN"])
    b2.metric("(ii) phiu Anet Fu", "%.0f kN" % HS["Tr_ii_kN"])
    b3.metric("(iii) 0.60 phiu Anes Fu", "%.0f kN" % HS["Tr_iii_kN"])
    b4.metric("U/C", "%.3f" % HS["uc"], HS["verdict"])
    st.caption("Governing branch: %s. Fy = %.0f MPa and Fu = %.0f MPa, "
               "the lesser of member and doubler."
               % (HS["governing"], HS["Fy_used"], HS["Fu_used"]))
    with st.expander("Show calculation steps", expanded=False):
        st.markdown("\n".join([
            "- Over the doubler footprint the thickness is tw + 2 td = "
            "%.1f mm, and outside it reverts to tw = %.1f mm"
            % (HS["t_eff_mm"], SHR["tw_mm"]),
            "- Ag = %.0f mm2, Anet = %.0f mm2"
            % (HS["Ag_mm2"], HS["Anet_mm2"]),
            "- Tear-out plane length k = sqrt(e_top^2 - (Dhole/2)^2) "
            "= %.1f mm, of which %.1f mm runs through the doubler and "
            "%.1f mm through the web alone"
            % (HS["k_mm"], HS["k_doubler_mm"], HS["k_web_mm"]),
            "- Anes = 2 [k_d (tw + 2 td) + k_w tw] = %.0f mm2"
            % HS["Anes_mm2"],
            "- (i) phi Ag Fy = %.1f kN" % HS["Tr_i_kN"],
            "- (ii) phiu Anet Fu = %.1f kN" % HS["Tr_ii_kN"],
            "- (iii) 0.60 phiu Anes Fu = %.1f kN" % HS["Tr_iii_kN"],
            "- Tr = least = **%.1f kN**, Tf/Tr = **%.4f  %s**"
            % (HS["Tr_kN"], HS["uc"], HS["verdict"]),
        ]))

    st.divider()

    # ---- C. Tear-out ---------------------------------------------------
    st.subheader("C. Tear-out Above the Hole")
    c1, c2, c3 = st.columns(3)
    c1.metric("Agv", "%.0f mm2" % TO["Agv_mm2"])
    c2.metric("Tr", "%.0f kN" % TO["Tr_kN"])
    c3.metric("U/C", "%.3f" % TO["uc"], TO["verdict"])
    st.caption("Cl. 13.11 with its closing Note: the shear term alone "
               "is the plate tear-out resistance along planes tangent "
               "to the hole and directed towards the edge of the "
               "plate.")
    if TO["note_c"]:
        st.info("Fy exceeds 460 MPa, so per Note (c) the term "
                "(Fy + Fu)/2 has been replaced by Fy.")
    with st.expander("Show calculation steps", expanded=False):
        st.markdown("\n".join([
            "- Agv = %.0f mm2, split %.1f mm through the doubler pack "
            "and %.1f mm through the web alone"
            % (TO["Agv_mm2"], HS["k_doubler_mm"], HS["k_web_mm"]),
            "- Shear term = (Fy + Fu)/2 = %.1f MPa"
            % TO["shear_stress_MPa"],
            "- Tr = phiu [Ut An Fu + 0.6 Agv (Fy+Fu)/2] = **%.1f kN**"
            % TO["Tr_kN"],
            "- Tf/Tr = **%.4f  %s**" % (TO["uc"], TO["verdict"]),
        ]))

    st.divider()

    # ---- D. Bearing and pin --------------------------------------------
    st.subheader("D. Bearing and Pin")
    d1, d2, d3 = st.columns(3)
    d1.metric("Cl. 13.10(a) fitted", "%.0f kN" % BR["Br_fitted_kN"])
    d2.metric("Cl. 13.12.1.2 clearance", "%.0f kN"
              % BR["Br_clearance_kN"])
    d3.metric("Bearing U/C", "%.3f" % BR["uc"], BR["verdict"])
    e1, e2 = st.columns(2)
    e1.metric("Pin shear Vr", "%.0f kN" % PS["Vr_kN"])
    e2.metric("Pin U/C", "%.3f" % PS["uc"], PS["verdict"])
    st.caption("Using %s. Apb = Dpin x t_eff = %.0f mm2."
               % (BR["clause"], BR["Apb_mm2"]))

    st.divider()

    # ---- E. Member below the doublers ----------------------------------
    st.subheader("E. Member Below the Doublers")
    f1, f2 = st.columns(2)
    f1.metric("Tr = phi Ag Fy", "%.0f kN" % MB["Tr_kN"])
    f2.metric("U/C", "%.3f" % MB["uc"], MB["verdict"])
    st.caption("Below the doubler the section reverts to the bare "
               "member and carries the whole load on its own gross "
               "area, Cl. 13.2 (a)(i). Ag = %.0f mm2 at Fy = %.0f MPa."
               % (MB["Ag_mm2"], MB["Fy_MPa"]))

    st.divider()

    # ---- F. Doubler weld ------------------------------------------------
    st.subheader("F. Doubler Weld")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Weld length", "%.0f mm" % DW["Lw_mm"])
    g2.metric("Vr", "%.0f kN" % DW["Vr_kN"])
    g3.metric("Leg required", "%.1f mm" % DW["w_req_mm"])
    g4.metric("U/C", "%.3f" % DW["uc"], DW["verdict"])
    if not DW["size_ok"]:
        st.warning("Weld leg %.1f mm is outside the practical range "
                   "%.0f to %.1f mm for these thicknesses."
                   % (DW["w_mm"], DW["w_min_mm"], DW["w_max_mm"]))
    st.caption("The weld carries the doublers' share of the load, "
               "%.1f kN. The run along the top edge is %s."
               % (DW["P_demand_kN"],
                  "included" if DW["weld_top"] else "discounted, because "
                  "the tear-out path crosses it"))
    with st.expander("Show calculation steps", expanded=False):
        st.markdown("\n".join([
            "- Effective weld length Lw = 2 L_d + W_d%s = %.0f mm"
            % (" + W_d" if DW["weld_top"] else "", DW["Lw_mm"]),
            "- Aw = 0.707 w Lw = %.0f mm2" % DW["Aw_mm2"],
            "- Mw = %.3f, directional term = %.3f at theta = %.0f deg"
            % (DW["Mw"], DW["dir_factor"], DW["theta_deg"]),
            "- Weld metal, Cl. 13.13.2.2: Vr = 0.67 phi_w Aw Xu "
            "(1.00 + 0.50 sin^1.5 theta) Mw = **%.1f kN**"
            % DW["Vr_weld_kN"],
            "- Base metal, Cl. 13.13.2.1(a): Vr = 0.67 phi_w Am Fu "
            "= **%.1f kN**" % DW["Vr_base_kN"],
            "- Vr = lesser = %.1f kN against a demand of %.1f kN"
            % (DW["Vr_kN"], DW["P_demand_kN"]),
            "- Leg required for the demand = **%.2f mm**, minimum for "
            "these thicknesses = %.0f mm, maximum = %.1f mm"
            % (DW["w_req_mm"], DW["w_min_mm"], DW["w_max_mm"]),
            "- U/C = **%.4f  %s**" % (DW["uc"], DW["verdict"]),
        ]))

    st.divider()

    # ---- G. Flexure above the hole --------------------------------------
    st.subheader("G. Flexure Above the Hole")
    h1, h2 = st.columns(2)
    h1.metric("Pr", "%.0f kN" % HF["Pr_kN"])
    h2.metric("U/C", "%.3f" % HF["uc"], HF["verdict"])
    st.caption("Industry practice check from the lifting literature, "
               "treating the material above the hole as a fixed end "
               "strip of span 0.8 Dhole. It is not a clause of S16 and "
               "is reported separately so it is never mistaken for "
               "one. e = e_top - Dhole/2 = %.1f mm at t = %.1f mm."
               % (HF["e_mm"], HF["t_mm"]))

    st.divider()
    with st.expander("Summary table", expanded=True):
        st.table([{"Check": n,
                   "U/C": ("-" if u is None else "%.4f" % u),
                   "Result": v} for n, u, v in R["checks"]])
