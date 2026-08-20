"""
pages/7_Lifting_Lug.py

CSA S16 lifting attachment calculator: lifting lug and lifting eye.

Both configurations live on one page because they are the same design
problem seen twice. A shackle pin bears on a hole in a plate, and the
plate has to carry that bearing out into the structure. What differs is
the route the load takes:

    Lifting lug (padeye)
        a plate projects from a bolted cap, cheek plates make up the
        thickness at the hole, and the cap plate bolts pry

    Lifting eye (bored hole)
        the hole goes straight through the web or cap plate of the
        member, doubler plates on both faces make up the thickness,
        nothing pries, and the doubler weld has to deliver the
        doublers' share of the load into them

Pick the configuration at the top of the input column. The two share
the load derivation, the resistance factors and the clause set; only
the geometry and the load path change.

Clause coverage. Every resistance is computed from the clause named
beside it; nothing is carried over from an external calculation sheet:

    Cl. 13.2 (a)    gross section, lug base or member below doublers
    Cl. 13.2 (b)    pin connected section at the hole, three branches
    Cl. 13.5        bending of the lug plate at the base (lug only)
    Cl. 13.10 (a)   bearing on an accurately fitted pin
    Cl. 13.11       tear-out at the hole, and its closing Note
    Cl. 13.12.1.1   pin shear
    Cl. 13.12.1.2   bearing of a pin in a clearance hole
    Cl. 13.13       welds

ASCII only. Straight quotes only. No markdown inside code.
"""

import math

import streamlit as st

st.set_page_config(page_title="Lifting Lug and Lifting Eye - Infraspective",
                   page_icon=":link:", layout="wide")

from _theme import (apply_theme, render_sidebar_logo, render_footer,
                    gate_disclaimer, render_page_title)

gate_disclaimer()
apply_theme()
render_sidebar_logo()
render_footer()

import lug_design
import eye_design
import viewer_3d_lug
import viewer_3d_eye


# ---------------------------------------------------------------------
# Section table. A bored eye needs the real shape of the member, not
# just its web thickness: the flanges are what the doublers sit between
# and what the model has to draw. Everything comes from the same
# SST12.1 workbook the rest of the app reads, so nothing here is a
# second copy of the section data.
# ---------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def w_section_rows():
    try:
        import sst12
        rows = sst12.load_all_tables().get("w", [])
    except Exception:
        return []
    out = []
    for r in rows:
        if r.get("d") and r.get("b") and r.get("t") and r.get("w"):
            out.append({"name": r["Designation"], "d": float(r["d"]),
                        "bf": float(r["b"]), "tf": float(r["t"]),
                        "tw": float(r["w"]), "k": float(r.get("k") or 0.0),
                        "Ag": float(r.get("Area") or 0.0)})
    return out


def w_section_lookup(name):
    for r in w_section_rows():
        if r["name"] == name:
            return r
    return None


SECTION_NONE = "Not from the table - enter the numbers by hand"


def apply_section_to_eye():
    """Push the picked section into the input boxes. Runs as the
    selectbox callback, so it lands before the boxes are rebuilt."""
    rec = w_section_lookup(st.session_state.get("eye_sec"))
    if rec is None:
        return
    st.session_state["eye_tw"] = rec["tw"]
    st.session_state["eye_Agm"] = rec["Ag"]
    clear = rec["d"] - 2.0 * rec["k"]
    if clear > 0:
        st.session_state["eye_Wweb"] = round(clear, 1)


# ---------------------------------------------------------------------
# Where the numbers come from. Written out on the page so a reviewer
# can check the source of every resistance without opening the code.
# ---------------------------------------------------------------------
SOURCES_COMMON = [
    ("CSA S16, Cl. 13.2 (a)", "Axial tension on the gross and net "
     "section, used for the member below the connection."),
    ("CSA S16, Cl. 13.2 (b)", "Axial tension for PIN CONNECTIONS other "
     "than eyebars, the least of phi Ag Fy, phiu Anet Fu and 0.60 phiu "
     "Anes Fu. This is the branch a bored hole or a padeye falls under."),
    ("CSA S16, Cl. 13.10 (a)", "Bearing on the contact area of "
     "accurately cut or fitted parts, Br = 1.50 phi Fy A."),
    ("CSA S16, Cl. 13.11 and its closing Note", "Block shear, and the "
     "Note that permits the shear term alone as the plate tear-out "
     "resistance on planes tangent to the hole."),
    ("CSA S16, Cl. 13.12.1.1", "Shear resistance of the pin."),
    ("CSA S16, Cl. 13.12.1.2", "Bearing of a pin in a clearance hole, "
     "used when the pin is not an accurate fit."),
    ("CSA S16, Cl. 13.13.1 / 13.13.2.1 / 13.13.2.2", "phi_w, base metal "
     "shear, and fillet weld metal including the directional term and "
     "the multi-orientation reduction Mw."),
    ("CISC Structural Section Tables SST12.1", "Every W section shape "
     "and area on this page. Read directly from the workbook in "
     "attached_assets, not from a retyped copy."),
    ("Crosby G-2130 product catalogue", "Nominal size, pin diameter and "
     "working load limit for the bolt type anchor shackle. Confirm "
     "against the current catalogue before issue, because WLL and pin "
     "sizes are the manufacturer's data and can change."),
]

SOURCES_NOT_S16 = [
    ("Flexure above the hole", "An industry practice check from the "
     "lifting literature, treating the material above the hole as a "
     "fixed end strip of span 0.8 Dhole. It is NOT a clause of S16 and "
     "is reported separately so it is never mistaken for one."),
    ("Proportioning rules", "Detailing rules in general use for pin "
     "connected plates. They are review items, not code requirements."),
    ("Lifting load factors LDf, If, Sf", "Lifting device factor, impact "
     "and unequal sling distribution. These come from the lift "
     "engineering basis for the project, not from S16."),
]


def render_sources(extra=None):
    with st.expander("Sources for the design", expanded=False):
        st.caption("Every resistance on this page is computed from the "
                   "clause named beside it. Clause numbering follows "
                   "CSA S16. Check the clause numbers against the "
                   "edition adopted by the governing building code for "
                   "your project before issue.")
        st.table([{"Source": a, "Used for": b}
                  for a, b in (SOURCES_COMMON + (extra or []))])
        st.caption("Not from S16:")
        st.table([{"Item": a, "Basis": b} for a, b in SOURCES_NOT_S16])
        st.caption("Standard details this page was built against: "
                   "45 dia lifting eye for a Crosby G-2130 1-1/2 in "
                   "shackle at 17 t per lug with PL13 doublers and a 6 "
                   "fillet, and 75 dia for a 2-1/2 in shackle at 55 t "
                   "per lug with PL25 doublers and an 8 fillet. See the "
                   "issued structural general notes for the drawing "
                   "number that governs on your project.")


CONFIGS = {
    "lug": "Lifting lug - padeye on a bolted cap plate",
    "eye": "Lifting eye - hole bored through the member",
}

mode = st.radio(
    "Configuration", list(CONFIGS.keys()), horizontal=True,
    format_func=lambda k: CONFIGS[k], key="lift_mode",
    help="A padeye projects from the structure and its cap plate bolts "
         "pry. A lifting eye is bored through the member itself, has "
         "doubler plates instead of cheek plates, and nothing pries.")

if mode == "lug":
    render_page_title(
        "Lifting Lug Design",
        clauses=("Cl. 13.2 (a) and (b)  |  Cl. 13.5  |  Cl. 13.10  |  "
                 "Cl. 13.11  |  Cl. 13.12  |  Cl. 13.13"),
        intro=("Lug plate, pin connected section at the hole, "
               "tear-out, bearing, pin, weld, and cap plate with bolt "
               "prying."),
    )
else:
    render_page_title(
        "Lifting Eye Design",
        clauses=("Cl. 13.2 (a) and (b)  |  Cl. 13.10  |  Cl. 13.11  |  "
                 "Cl. 13.12  |  Cl. 13.13.2.2"),
        intro=("Bored hole with doubler plates both faces. Tension at "
               "the hole, tear-out, bearing, pin, the member below the "
               "doublers, and the doubler weld."),
    )

col_model, col_in = st.columns([2, 1], gap="large")

if mode == "lug":
    DEF = lug_design.SOURCE_CASE


    def num(label, key, default, step=1.0, minv=0.0, fmt="%.1f", help=None):
        return st.number_input(label, min_value=minv, value=float(default),
                               step=step, format=fmt, key="lug_" + key,
                               help=help)



    # ---------------------------------------------------------------------
    # INPUTS - right hand column, the only place anything is entered
    # ---------------------------------------------------------------------
    with col_in:
        st.subheader("Design Inputs")

        with st.expander("Lifting load", expanded=True):
            T_tons = num("T, service sling load (tonnes)", "T", DEF["T_tons"],
                         0.01, 0.0, "%.2f",
                         help="Maximum service sling load from the lift "
                              "analysis")
            LDf = num("LDf, lifting device factor", "LDf", DEF["LDf"], 0.1,
                      1.0, "%.2f", help="H3.1.1 minimum lifting device "
                                        "load factor")
            If = num("If, impact factor", "If", DEF["If"], 0.05, 1.0, "%.2f",
                     help="H2.1 impact factor")
            Sf = num("Sf, sling distribution factor", "Sf", DEF["Sf"], 0.05,
                     1.0, "%.2f",
                     help="H2.1 unequal sling distribution, 0.70/0.50")
            sling_angle = num("Sling angle from horizontal (deg)", "sang",
                              60.0, 5.0, 5.0, "%.0f",
                              help="Model geometry only, not used in the "
                                   "checks")

        with st.expander("Shackle", expanded=True):
            sizes = [s[0] for s in lug_design.SHACKLES_G2130]
            shackle_in = st.selectbox(
                "Crosby G-2130 nominal size (in)", sizes,
                index=sizes.index(2.0) if 2.0 in sizes else 0,
                format_func=lambda v: "%.3f in  -  WLL %.1f t" % (
                    v, lug_design.shackle_lookup(v)["WLL_t"]),
                key="lug_shackle")

        with st.expander("Lug plate", expanded=True):
            L2 = num("L2, length at base", "L2", DEF["L2"], 5.0, 1.0)
            H2 = num("H2, base to hole centre", "H2", DEF["H2"], 5.0, 1.0)
            H1 = num("H1, hole centre to top edge", "H1", DEF["H1"], 5.0, 1.0)
            tp2 = num("tp2, lug thickness", "tp2", DEF["tp2"], 1.0, 1.0)

        with st.expander("Pin and cheek plates", expanded=True):
            Dpin = num("Dpin, pin diameter", "Dpin", DEF["Dpin"], 1.0, 1.0)
            Dhole = num("Dhole, hole diameter", "Dhole", DEF["Dhole"], 1.0,
                        1.0)
            Dcheekp = num("Dcheekp, cheek plate diameter", "Dch",
                          DEF["Dcheekp"], 5.0, 1.0)
            tp3 = num("tp3, cheek plate thickness", "tp3", DEF["tp3"], 1.0,
                      0.0)
            Fypin = num("Fy pin (MPa)", "Fypin", DEF["Fypin"], 5.0, 100.0)
            Fupin = num("Fu pin (MPa)", "Fupin", DEF["Fupin"], 5.0, 100.0)
            pin_fit = st.radio(
                "Pin fit", ["clearance", "fitted"], horizontal=True,
                index=0, key="lug_pinfit",
                format_func=lambda k: ("Clearance hole - Cl. 13.12.1.2"
                                       if k == "clearance"
                                       else "Accurately fitted - Cl. 13.10(a)"),
                help="Cl. 13.10(a) is written for accurately cut or fitted "
                     "parts. A shackle pin in an oversized hole is not "
                     "fitted, so the bolt bearing model of Cl. 13.12.1.2 "
                     "is the appropriate one.")
            cheeks_eff = st.checkbox(
                "Cheek plates developed into the lug", value=True,
                key="lug_cheekeff",
                help="Tick only if the cheek plate weld develops the plate "
                     "into the lug. If not, the cheek plates carry bearing "
                     "but not tension.")

        with st.expander("Cap plate and bolts", expanded=False):
            L1 = num("L1, cap plate length", "L1", DEF["L1"], 5.0, 1.0)
            W1 = num("W1, cap plate width", "W1", DEF["W1"], 5.0, 1.0)
            tp1 = num("tp1, cap plate thickness", "tp1", DEF["tp1"], 1.0, 1.0)
            Db = num("Db, bolt diameter", "Db", DEF["Db"], 2.0, 1.0)
            Nrow = num("Nrow, number of bolt rows", "Nrow", DEF["Nrow"], 1.0,
                       1.0, "%.0f")
            s_pitch = num("s, pitch along L1", "s", DEF["s"], 5.0, 1.0)
            g_gauge = num("g, gauge across W1", "g", DEF["g"], 5.0, 1.0)
            Fub = num("Fu bolt (MPa)", "Fub", DEF["Fub"], 10.0, 100.0)

        with st.expander("Weld and materials", expanded=False):
            weld_type = st.radio(
                "Weld type", ["fillet", "pjp"], horizontal=True, index=0,
                key="lug_weldtype",
                format_func=lambda k: ("Fillet - Cl. 13.13.2.2" if k == "fillet"
                                       else "PJP groove - Cl. 13.13.3.2"))
            w1 = num("w1, fillet weld leg", "w1", DEF["w1"], 1.0, 0.0)
            Xu = num("Xu, electrode strength (MPa)", "Xu", DEF["Xu"], 10.0,
                     100.0)
            use_Mw = st.checkbox(
                "Apply Mw, multi-orientation reduction", value=True,
                key="lug_useMw",
                help="Cl. 13.13.2.2. Mw = (0.85 + th1/600)/(0.85 + th2/600) "
                     "for joints with more than one weld orientation. A lug "
                     "welded on all four sides qualifies.")
            Fyp = num("Fy plate (MPa)", "Fyp", DEF["Fyp"], 5.0, 100.0)
            Fup = num("Fu plate (MPa)", "Fup", DEF["Fup"], 5.0, 100.0)

        with st.expander("Resistance factors", expanded=False):
            phi = num("phi, Cl. 13.1", "phi", DEF["phi"], 0.05, 0.1, "%.2f")
            phiu = num("phi u, fracture", "phiu", DEF["phiu"], 0.05, 0.1,
                       "%.2f",
                       help="Cl. 13.1. Every fracture based term, so "
                            "Cl. 13.2(b)(ii), 13.2(b)(iii) and 13.11.")
            phiw = num("phi w, weld", "phiw", DEF["phiw"], 0.01, 0.1, "%.2f",
                       help="Cl. 13.13.1 sets phi_w = 0.67. The 0.67 "
                            "coefficient inside the Cl. 13.13.2 equations "
                            "is separate and is applied as well.")
            phib = num("phi b, bolt", "phib", DEF["phib"], 0.05, 0.1, "%.2f")
            phibr = num("phi br, bearing", "phibr", DEF["phibr"], 0.01, 0.1,
                        "%.2f")

        with st.expander("Method", expanded=False):
            Ut = num("Ut, Cl. 13.11 efficiency factor", "Ut", DEF["Ut"],
                     0.05, 0.1, "%.2f",
                     help="1.0 for symmetrical blocks and concentric "
                          "loading. Only used if a tension path is entered "
                          "below.")
            An_t = num("An, tension area for Cl. 13.11 (mm2)", "Ant", 0.0,
                       10.0, 0.0, "%.0f",
                       help="Leave at zero for a padeye. The closing Note "
                            "to Cl. 13.11 allows the shear term alone as "
                            "the plate tear-out resistance.")
            pry_mode = st.radio(
                "Prying a' definition",
                options=["cisc", "sheet"],
                format_func=lambda k: ("CISC:  a' = a + Db/2  (recommended)"
                                       if k == "cisc"
                                       else "Alternative:  a' = a - Db/2"),
                index=0, key="lug_prymode",
                help="CISC gives a' = a + Db/2, with a limited to 1.25 b, "
                     "and that is the correct form. The alternative is kept "
                     "only so that a legacy hand calculation using the "
                     "other sign can be reproduced for comparison.")

    INP = {
        "Dpin": Dpin, "Dhole": Dhole, "Dcheekp": Dcheekp,
        "Fypin": Fypin, "Fupin": Fupin,
        "tp1": tp1, "L1": L1, "W1": W1,
        "Fyp": Fyp, "Fup": Fup, "phi": phi, "phiu": phiu, "phiw": phiw,
        "Xu": Xu, "w1": w1, "use_Mw": use_Mw, "weld_type": weld_type,
        "tp2": tp2, "H1": H1, "H2": H2, "L2": L2, "tp3": tp3,
        "Db": Db, "Nrow": Nrow, "s": s_pitch, "g": g_gauge,
        "Fub": Fub, "phib": phib, "phibr": phibr,
        "T_tons": T_tons, "If": If, "Sf": Sf, "LDf": LDf,
        "Ut": Ut, "An_tension_mm2": An_t,
        "pin_fit": pin_fit, "cheeks_effective": cheeks_eff,
        "shackle_in": shackle_in,
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
    PC = R["pin_conn"]
    TO = R["tearout"]
    BR = R["bearing"]
    PS = R["pin_shear"]
    HF = R["flexure"]
    PR = R["prying"]
    PN = R["pin"]
    GC = R["geom_check"]
    SH = R["shackle"]

    CHECKS = [
        {"key": "weld_metal", "label": "Weld metal", "component": "weld",
         "uc": WM["uc"], "verdict": WM["verdict"]},
        {"key": "base_metal", "label": "Weld base metal", "component": "weld",
         "uc": BM["uc"], "verdict": BM["verdict"]},
        {"key": "lug", "label": "Lug plate section", "component": "lug",
         "uc": LG["uc"], "verdict": LG["verdict"]},
        {"key": "pin_conn", "label": "Pin connected section",
         "component": "lug", "uc": PC["uc"], "verdict": PC["verdict"]},
        {"key": "conn", "label": "Connection capacity", "component": "cap",
         "uc": PR["uc_conn"], "verdict": PR["conn_verdict"]},
        {"key": "bolt", "label": "Bolt with prying", "component": "bolt",
         "uc": PR["uc_bolt"], "verdict": PR["bolt_verdict"]},
        {"key": "pin", "label": "Pin", "component": "pin",
         "uc": PS["uc"], "verdict": PS["verdict"]},
        {"key": "cheek", "label": "Bearing and tear-out", "component": "cheek",
         "uc": max(TO["uc"] or 0.0, BR["uc"] or 0.0),
         "verdict": ("OK" if TO["verdict"] == "OK" and BR["verdict"] == "OK"
                     else "NG")},
    ]


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
            load={"sling_angle_deg": sling_angle, "Tf_kN": F["Tf_kN"],
                  "Vf_kN": F["Rf_kN"], "Tfb_kN": PR.get("Tfb_kN")},
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

        # ---- 0. Proportioning ---------------------------------------------
        st.subheader("0. Proportioning and Shackle")
        if GC["all_ok"]:
            st.success("All proportioning rules satisfied.")
        else:
            st.warning("One or more proportioning rules are not satisfied. "
                       "These are detailing rules in general use for pin "
                       "connected plates, not clauses of S16, so treat them "
                       "as items for review rather than as failures.")
        st.table([{"Item": i["item"], "Required": i["required"],
                   "Actual": i["value"],
                   "Result": "OK" if i["ok"] else "REVIEW"}
                  for i in GC["items"]])

        s0 = st.columns(4)
        s0[0].metric("Shackle", "%.3f in" % SH["nominal_in"])
        s0[1].metric("WLL", "%.1f t" % SH["WLL_t"])
        s0[2].metric("Service load", "%.2f t" % SH["T_tons"])
        s0[3].metric("U/C", "%.3f" % (SH["uc"] or 0.0), SH["verdict"])
        if not SH["pin_fits_hole"]:
            st.warning("The catalogue pin diameter of %.0f mm does not "
                       "clear the %.0f mm hole." % (SH["pin_mm"], Dhole))
        st.caption("Working load limits are the manufacturer's published "
                   "ratings and pin diameters are nominal. Rigging hardware "
                   "ratings are revised from time to time, so confirm the "
                   "size specified against the current catalogue before "
                   "issuing the design.")

        st.divider()

        # ---- A. Design forces --------------------------------------------
        st.subheader("A. Design Forces")
        a1, a2 = st.columns(2)
        a1.metric("Service load Ts", "%.2f t" % F["Ts_tons"])
        a2.metric("Factored load Tf", "%.2f kN" % F["Tf_kN"])
        with st.expander("Show calculation steps", expanded=False):
            st.markdown("\n".join([
                "- Governing load factor: max(LDf, If x Sf) = max(%.2f, "
                "%.2f) = **%.2f**" % (LDf, If * Sf, F["total_factor"]),
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
            st.markdown("**Weld metal** - Cl. 13.13.2.2")
            st.metric("U/C", "%.3f" % WM["uc"], WM["verdict"])
            st.caption("a = 0.707 w1 = %.2f mm, sigma_t = %.1f MPa, "
                       "sigma_all = %.1f MPa, theta = %.1f deg, Mw = %.3f"
                       % (WM["a_mm"], WM["sigma_t_MPa"], WM["sigma_all_MPa"],
                          WM["theta_deg"], WM["Mw"]))
        with b2:
            st.markdown("**Base metal** - Cl. 13.13.2.1 (a)")
            st.metric("U/C", "%.3f" % BM["uc"], BM["verdict"])
            st.caption("a = w1 = %.2f mm, sigma_t = %.1f MPa, "
                       "sigma_all = 0.67 phi_w Fu = %.1f MPa"
                       % (BM["a_mm"], BM["sigma_t_MPa"], BM["sigma_all_MPa"]))
        with st.expander("Show calculation steps", expanded=False):
            st.markdown(
                "Cl. 13.13.1 sets phi_w = %.2f. The 0.67 coefficient inside "
                "the Cl. 13.13.2 equations is a separate factor and both "
                "are applied.\n\n"
                "Directional term: 1.00 + 0.50 sin^1.5 theta = %.3f at "
                "theta = %.1f deg.\n\n"
                "Multi-orientation factor Mw = (0.85 + th1/600)/(0.85 + "
                "th2/600) = %.3f, with th2 taken as 90 deg because the lug "
                "is welded on all four sides."
                % (phiw, R["welds"]["dir_factor"], R["welds"]["theta_deg"],
                   R["welds"]["Mw"]))
            for name, W in (("Weld metal", WM), ("Base metal", BM)):
                st.markdown("**%s**" % name)
                st.markdown("\n".join([
                    "- A = 2 a L2 = %.1f mm2" % W["A_mm2"],
                    "- Sx-x = %.0f mm3, Sy-y = %.0f mm3"
                    % (W["Sxx_mm3"], W["Syy_mm3"]),
                    "- sigma1 = Mfy/Sy-y + Mfx/Sx-x = %.2f MPa"
                    % W["sigma1_MPa"],
                    "- sigma2 = Tf/A = %.2f MPa" % W["sigma2_MPa"],
                    "- sigma_n = %.2f MPa, tau = Rf/A = %.2f MPa"
                    % (W["sigma_n_MPa"], W["tau_MPa"]),
                    "- sigma_t = sqrt(sigma_n^2 + tau^2) = %.2f MPa"
                    % W["sigma_t_MPa"],
                    "- sigma_all = %.2f MPa (%s)"
                    % (W["sigma_all_MPa"], W["clause"]),
                    "- U/C = **%.4f  %s**" % (W["uc"], W["verdict"]),
                ]))
                st.markdown("")
        if R["welds"]["pjp"] is not None:
            P = R["welds"]["pjp"]
            st.info("PJP groove weld, Cl. 13.13.3.2: Tr = phi_w An Fu = "
                    "%.0f kN, limited by phi Ag Fy = %.0f kN. Tr = %.0f kN, "
                    "U/C = %.3f  %s"
                    % (P["Tr_weld_kN"], P["Tr_base_kN"], P["Tr_kN"],
                       P["uc"], P["verdict"]))

        st.divider()

        # ---- C. Lug plate at the base -------------------------------------
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
                "- Tr = phi A Fy = **%.1f kN** (Cl. 13.2(a)(i))" % LG["Tr_kN"],
                "- Mrx = phi Sx-x Fy = **%.2f kN-m** (Cl. 13.5(b))"
                % LG["Mrx_kNm"],
                "- Mry = phi Sy-y Fy = **%.2f kN-m**" % LG["Mry_kNm"],
                "- Tf/Tr + Mfx/Mrx + Mfy/Mry = **%.4f  %s**"
                % (LG["uc"], LG["verdict"]),
            ]))

        st.divider()

        # ---- D. Pin connected section, Cl. 13.2 (b) ------------------------
        st.subheader("D. Pin Connected Section at the Hole")
        st.caption("Cl. 13.2 (b). A padeye is a pin connection, so the head "
                   "of the lug is governed by the least of three branches, "
                   "not by the gross section alone.")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("(i) phi Ag Fy", "%.0f kN" % PC["Tr_i_kN"])
        d2.metric("(ii) phiu Anet Fu", "%.0f kN" % PC["Tr_ii_kN"])
        d3.metric("(iii) 0.60 phiu Anes Fu", "%.0f kN" % PC["Tr_iii_kN"])
        d4.metric("U/C", "%.3f" % PC["uc"], PC["verdict"])
        st.caption("Governing branch: %s. Effective thickness %.0f mm%s."
                   % (PC["governing"], PC["t_eff_mm"],
                      " including both cheek plates" if PC["cheeks_effective"]
                      else ", cheek plates excluded from tension"))
        with st.expander("Show calculation steps", expanded=False):
            st.markdown("\n".join([
                "- t_eff = tp2 + 2 tp3 = %.0f mm" % PC["t_eff_mm"],
                "- Net width each side of the hole, H1 - Dhole/2 = %.1f mm"
                % PC["e_side_mm"],
                "- Ag = 2 H1 t_eff = %.0f mm2" % PC["Ag_mm2"],
                "- Anet = 2 (H1 - Dhole/2) t_eff = %.0f mm2" % PC["Anet_mm2"],
                "- Tear-out plane length, tangent to the hole, "
                "k = sqrt(H1^2 - (Dhole/2)^2) = %.1f mm" % PC["k_mm"],
                "- Anes = 2 k t_eff = %.0f mm2" % PC["Anes_mm2"],
                "- (i) phi Ag Fy = %.1f kN" % PC["Tr_i_kN"],
                "- (ii) phiu Anet Fu = %.1f kN" % PC["Tr_ii_kN"],
                "- (iii) 0.60 phiu Anes Fu = %.1f kN" % PC["Tr_iii_kN"],
                "- Tr = least = **%.1f kN**, Tf/Tr = **%.4f  %s**"
                % (PC["Tr_kN"], PC["uc"], PC["verdict"]),
            ]))

        st.divider()

        # ---- E. Tear-out, Cl. 13.11 ---------------------------------------
        st.subheader("E. Tear-out Above the Pin")
        e1, e2, e3 = st.columns(3)
        e1.metric("Agv", "%.0f mm2" % TO["Agv_mm2"])
        e2.metric("Tr", "%.0f kN" % TO["Tr_kN"])
        e3.metric("U/C", "%.3f" % TO["uc"], TO["verdict"])
        st.caption("Cl. 13.11 with the closing Note: the shear term alone is "
                   "the plate tear-out resistance along planes tangent to "
                   "the hole and directed towards the edge of the plate.")
        if TO["note_c"]:
            st.info("Fy exceeds 460 MPa, so per Note (c) the term "
                    "(Fy + Fu)/2 has been replaced by Fy.")
        with st.expander("Show calculation steps", expanded=False):
            st.markdown("\n".join([
                "- Tangent plane length k = sqrt(H1^2 - (Dhole/2)^2) "
                "= %.1f mm" % TO["k_mm"],
                "- Through the cheek plate for %.1f mm at t = tp2 + 2 tp3, "
                "then through the lug alone for %.1f mm at t = tp2"
                % (TO["k_cheek_mm"], TO["k_lug_mm"]),
                "- Agv = 2 [k_cheek (tp2 + 2 tp3) + k_lug tp2] = %.0f mm2"
                % TO["Agv_mm2"],
                "- Shear stress term = (Fy + Fu)/2 = %.1f MPa"
                % TO["shear_stress_MPa"],
                "- Tr = phiu [Ut An Fu + 0.6 Agv (Fy+Fu)/2] "
                "= **%.1f kN**" % TO["Tr_kN"],
                "- Tf/Tr = **%.4f  %s**" % (TO["uc"], TO["verdict"]),
            ]))
            st.warning("The superseded form 2 (0.60 phi) Agv Fu gives "
                       "%.0f kN, which is %.0f per cent higher than the "
                       "current clause. The difference is phi against "
                       "phi_u and Fu against (Fy + Fu)/2."
                       % (TO["Tr_legacy_kN"],
                          100.0 * (TO["Tr_legacy_kN"] / TO["Tr_kN"] - 1.0)
                          if TO["Tr_kN"] > 0 else 0.0))

        st.divider()

        # ---- F. Bearing ----------------------------------------------------
        st.subheader("F. Bearing of the Pin on the Hole")
        f1, f2, f3 = st.columns(3)
        f1.metric("Cl. 13.10(a) fitted", "%.0f kN" % BR["Br_fitted_kN"])
        f2.metric("Cl. 13.12.1.2 clearance", "%.0f kN"
                  % BR["Br_clearance_kN"])
        f3.metric("U/C", "%.3f" % BR["uc"], BR["verdict"])
        st.caption("Using %s. Projected bearing area Apb = Dpin (tp2 + "
                   "2 tp3) = %.0f mm2." % (BR["clause"], BR["Apb_mm2"]))
        with st.expander("Show calculation steps", expanded=False):
            st.markdown("\n".join([
                "- Apb = Dpin x (tp2 + 2 tp3) = %.1f x %.1f = %.0f mm2"
                % (Dpin, BR["t_mm"], BR["Apb_mm2"]),
                "- Cl. 13.10(a), accurately cut or fitted parts: "
                "Br = 1.50 phi Fy A = **%.1f kN**" % BR["Br_fitted_kN"],
                "- Cl. 13.12.1.2, clearance hole: "
                "Br = 3 phi_br t Dpin Fu = **%.1f kN**"
                % BR["Br_clearance_kN"],
                "- Tf/Br = **%.4f  %s**" % (BR["uc"], BR["verdict"]),
            ]))
            st.info("Cl. 13.10 is written for accurately cut or fitted "
                    "parts and has only two branches, (a) and (b). A "
                    "shackle pin in an oversized hole does not meet that "
                    "description, so the bolt bearing model is the "
                    "defensible one. The two differ by a factor of about "
                    "%.1f here." % (BR["Br_clearance_kN"] /
                                    BR["Br_fitted_kN"]
                                    if BR["Br_fitted_kN"] > 0 else 0.0))

        st.divider()

        # ---- G. Pin and head flexure ---------------------------------------
        st.subheader("G. Pin and Lug Head")
        g1, g2, g3 = st.columns(3)
        g1.metric("Pin shear Vr", "%.0f kN" % PS["Vr_kN"], PS["verdict"])
        g2.metric("Head flexure Pr", "%.0f kN" % HF["Pr_kN"], HF["verdict"])
        g3.metric("Least of pin group", "%.0f kN" % PN["Vr_kN"])
        st.caption("Pin shear governed by %s. The head flexure check is an "
                   "industry practice check from the lifting literature. It "
                   "is not a clause of S16 and is reported separately so it "
                   "is never mistaken for one." % PN["governing"])
        with st.expander("Show calculation steps", expanded=False):
            st.markdown("\n".join([
                "- Apin = pi Dpin^2 / 4 = %.1f mm2" % PS["Apin_mm2"],
                "- Vr = 0.60 phi_b m Apin Fu = **%.1f kN**  (%s)"
                % (PS["Vr_kN"], PS["clause"]),
                "- Head flexure, e = H1 - Dhole/2 = %.1f mm, t = %.0f mm"
                % (HF["e_mm"], HF["t_mm"]),
                "- M = Pu (0.8 Dhole)/8 = [t e^2/4](0.9 Fy), so "
                "Pr = 10 t e^2 (0.9 Fy)/(4 Dhole) = **%.1f kN**"
                % HF["Pr_kN"],
            ]))

        st.divider()

        # ---- H. Cap plate and prying ---------------------------------------
        st.subheader("H. Cap Plate Thickness and Bolt Prying")
        h1, h2, h3 = st.columns(3)
        h1.metric("Plate thickness", PR["plate_verdict"],
                  "tmax = %.2f mm vs tp1 = %.0f mm"
                  % (PR["t_max_mm"], PR["tp1_mm"]))
        h2.metric("Connection U/C", "%.3f" % PR["uc_conn"],
                  PR["conn_verdict"])
        h3.metric("Bolt U/C", "%.3f" % PR["uc_bolt"], PR["bolt_verdict"])
        if PR["mode"] == "cisc":
            st.caption("a' = a + Db/2 per CISC, with a limited to 1.25 b.")
        else:
            st.caption("Alternative definition a' = a - Db/2, kept for "
                       "comparison against a legacy hand calculation. It "
                       "gives a smaller a' and a higher connection U/C.")
        with st.expander("Show calculation steps", expanded=False):
            st.markdown("\n".join([
                "- a = (W1 - g)/2 = %.1f mm, b = (W1 - tp2)/2 - a = %.1f mm"
                % (PR["a_mm"], PR["b_mm"]),
                "- a used = %.1f mm, a' = %.1f mm, b' = %.1f mm"
                % (PR["a_eff_mm"], PR["a_prime_mm"], PR["b_prime_mm"]),
                "- p = L1/Nrow = %.1f mm, hole d' = Db + 2 = %.1f mm"
                % (PR["p_mm"], PR["d_hole_mm"]),
                "- delta = 1 - d'/p = %.4f" % PR["delta"],
                "- K = 4 b' x 10^3 / (phi p Fyp) = %.4f" % PR["K"],
                "- Pfb = Tf/(2 Nrow) = %.2f kN over %.0f bolts"
                % (PR["Pfb_kN"], PR["n_bolts"]),
                "- tmin (alpha=1) = %.2f mm, tmax (alpha=0) = %.2f mm"
                % (PR["t_min_mm"], PR["t_max_mm"]),
                "- Trb = 0.75 phi_b (pi Db^2/4) Fub = **%.2f kN** "
                "(Cl. 13.12.1.2)" % PR["Trb_kN"],
                "- alpha (connection) = %.4f, used %.4f"
                % (PR["alpha_conn"], PR["alpha_conn_used"]),
                "- Fr = (tp1^2/K)(1 + delta alpha)(2 Nrow) = **%.1f kN**"
                % PR["Fr_kN"],
                "- Tf/Fr = **%.4f  %s**" % (PR["uc_conn"],
                                            PR["conn_verdict"]),
                "- Tfb = %.2f kN, Tfb/Trb = **%.4f  %s**"
                % (PR["Tfb_kN"], PR["uc_bolt"], PR["bolt_verdict"]),
            ]))

        st.divider()
        with st.expander("Summary table", expanded=True):
            rows = [{"Check": n, "U/C": ("-" if u is None else "%.4f" % u),
                     "Result": v} for n, u, v in R["checks"]]
            st.table(rows)

        render_sources([
            ("CSA S16, Cl. 13.5", "Bending resistance of the lug plate "
             "at the base."),
            ("CISC Handbook, prying action", "The prying model used for "
             "the cap plate bolts. The alternative mode offered on this "
             "page is the AISC formulation; both are shown so the "
             "difference is visible rather than buried."),
        ])

else:
    DEF = eye_design.SOURCE_CASE_EYE


    def num(label, key, default, step=1.0, minv=0.0, fmt="%.1f", help=None):
        return st.number_input(label, min_value=minv, value=float(default),
                               step=step, format=fmt, key="eye_" + key,
                               help=help)



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
            sling_angle = num("Sling angle from horizontal (deg)", "sang",
                              60.0, 5.0, 5.0, "%.0f",
                              help="Sets the leg tension drawn on the "
                                   "model, P = Tf / (2 sin theta). It "
                                   "does not change Tf and it does not "
                                   "enter the checks.")

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
            _rows = w_section_rows()
            if _rows:
                _names = [SECTION_NONE] + [r["name"] for r in _rows]
                st.selectbox(
                    "Member section", _names, key="eye_sec",
                    on_change=apply_section_to_eye,
                    help="Picking a section fills in tw, the clear web "
                         "width d - 2k and Ag, and gives the model the "
                         "real d, bf and tf so the flanges are drawn to "
                         "shape. Leave it unset for a built-up member "
                         "or a cap plate and type the numbers instead.")
            else:
                st.caption("Section table unavailable, so the numbers "
                           "below have to be entered by hand.")
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
        with col_model:
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
    # What the model is told. Every check that has a piece of steel to
    # point at is handed to the viewer, so a part can be coloured by the
    # check that governs it rather than by a guess.
    # ---------------------------------------------------------------------
    EYE_CHECKS = [
        {"key": "hole", "label": "Tension at the hole",
         "component": "member", "uc": HS["uc"], "verdict": HS["verdict"]},
        {"key": "tear", "label": "Tear-out above the hole",
         "component": "member", "uc": TO["uc"], "verdict": TO["verdict"]},
        {"key": "below", "label": "Member below the doublers",
         "component": "member", "uc": MB["uc"], "verdict": MB["verdict"]},
        {"key": "weld", "label": "Doubler weld",
         "component": "weld", "uc": DW["uc"], "verdict": DW["verdict"]},
        {"key": "dblr", "label": "Doubler share at the hole",
         "component": "doubler", "uc": HS["uc"], "verdict": HS["verdict"]},
        {"key": "bear", "label": "Bearing on the bore",
         "component": "pin", "uc": BR["uc"], "verdict": BR["verdict"]},
        {"key": "pin", "label": "Pin shear",
         "component": "pin", "uc": PS["uc"], "verdict": PS["verdict"]},
    ]

    _sec = w_section_lookup(st.session_state.get("eye_sec"))

    def _prow(group, symbol, value, unit, nd=1):
        try:
            v = "{:,.{}f}".format(float(value), nd)
        except (TypeError, ValueError):
            v = str(value)
        return {"group": group, "symbol": symbol, "value": v, "unit": unit}

    _theta = math.radians(max(1.0, sling_angle))
    _Pleg = F["Tf_kN"] / (2.0 * math.sin(_theta))

    EYE_PROPS = [
        _prow("Load", "T", T_tons, "t", 2),
        _prow("Load", "Tf", F["Tf_kN"], "kN"),
        _prow("Load", "P leg", _Pleg, "kN"),
        _prow("Load", "theta", sling_angle, "deg", 0),
        _prow("Share", "t_eff", SHR["t_eff_mm"], "mm"),
        _prow("Share", "P web", SHR["P_web_kN"], "kN"),
        _prow("Share", "P dblr", SHR["P_doubler_kN"], "kN"),
        _prow("Hole", "Dhole", Dhole, "mm", 0),
        _prow("Hole", "Dpin", Dpin, "mm", 0),
        _prow("Hole", "k", HS["k_mm"], "mm"),
        _prow("Doubler", "td", td, "mm", 0),
        _prow("Doubler", "W_d", W_d, "mm", 0),
        _prow("Doubler", "L_d", L_d, "mm", 0),
        _prow("Weld", "w", w_weld, "mm", 0),
        _prow("Weld", "Vr", DW["Vr_kN"], "kN"),
    ]
    if _sec is not None:
        EYE_PROPS = [
            _prow("Member", "section", _sec["name"], ""),
            _prow("Member", "d", _sec["d"], "mm", 0),
            _prow("Member", "bf", _sec["bf"], "mm", 0),
            _prow("Member", "tf", _sec["tf"], "mm", 1),
            _prow("Member", "tw", _sec["tw"], "mm", 1),
        ] + EYE_PROPS

    # ---------------------------------------------------------------------
    # RESULTS
    # ---------------------------------------------------------------------
    with col_model:
        viewer_3d_eye.render_eye(
            dict(INP, label="Lifting eye",
                 section_name=(_sec["name"] if _sec else ""),
                 d_sec=(_sec["d"] if _sec else 0.0),
                 bf_sec=(_sec["bf"] if _sec else 0.0),
                 tf_sec=(_sec["tf"] if _sec else 0.0),
                 k_sec=(_sec["k"] if _sec else 0.0)),
            height=560,
            checks=EYE_CHECKS,
            results={"Tf_kN": F["Tf_kN"],
                     "governing_name": R["governing_name"],
                     "governing_uc": R["governing_uc"],
                     "overall": R["overall"]},
            props=EYE_PROPS,
            load={"sling_angle_deg": sling_angle, "Tf_kN": F["Tf_kN"],
                  "P_leg_kN": _Pleg, "P_web_kN": SHR["P_web_kN"],
                  "P_doubler_kN": SHR["P_doubler_kN"]},
            paths=HS,
            show_diagnostics=False)
        st.caption("Turn on Load path to follow the force: bearing on "
                   "the bore, the share each ply carries, the weld that "
                   "is the only way into the doublers, and the bare "
                   "member below them. Failure paths draws the planes "
                   "the clause checks are taken on. The two red arrows "
                   "are the sling legs at P = Tf / (2 sin theta); the "
                   "green one is Tf, which is what the checks use.")
        if _sec is None:
            st.caption("No section picked, so the flanges are left off "
                       "rather than invented. Pick one under Member "
                       "being bored to draw the member to shape.")

        with st.expander("Elevation, flat", expanded=False):
            st.markdown(elevation_svg(), unsafe_allow_html=True)
            st.caption("The same numbers as the model, drawn flat. Red "
                       "is the tear-out path, the line from the free "
                       "edge tangent to the hole. Orange is the net "
                       "tension section. Green is the loaded half of "
                       "the bore.")

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

        render_sources([
            ("CSA S16, Cl. 13.13.2.2", "The doubler weld, which is the "
             "only path into the doubler plates. If it cannot deliver "
             "their share they do not participate, whatever their "
             "thickness."),
        ])

