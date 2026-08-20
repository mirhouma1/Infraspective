"""
9_End_Plate_Shear.py - Bolted end plate shear connection, CSA S16.

Infraspective Solutions - structural calculator suite.

LEARNING MODULE. This page is built to be worked through rather than
just answered: the checks are presented in load path order, each one
carries a short note on why it exists and what makes it govern, and
the 3D viewer can show the failure surface for each limit state.

Engine: shear_connection.py
Viewer: viewer_3d_endplate.py / viewer_3d_endplate.html

ASCII only. Straight quotes only.
"""

import math

import pandas as pd
import streamlit as st

import shear_connection as sc
import viewer_3d_endplate as v3d
import connection_details as cdet
import section_data as secd

# ----------------------------------------------------------------------
# Standard page bootstrap. Same call chain and order as app.py, so this
# page carries the theme, the brand, the directory tree, the footer and
# the agreement gate exactly like every other calculator.
# ----------------------------------------------------------------------
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

from _theme import (apply_theme, render_sidebar_logo, render_footer,
                    gate_disclaimer, render_page_title)

st.set_page_config(page_title="End Plate Shear Connection - Infraspective",
                   page_icon=":wrench:", layout="wide")

apply_theme()
render_sidebar_logo()
render_footer()
gate_disclaimer()


render_page_title(
    "End Plate Shear Connection",
    clauses="Cl. 13.4.1.1, 13.11, 13.12, 13.13.2.2, 22.3",
    standard="CSA S16",
    intro="Learning module. A plate is shop welded to the beam web and "
          "field bolted to the supporting member. The limit states are "
          "worked in load path order so the chain of resistances can be "
          "followed end to end.")

with st.expander("How to use this page", expanded=False):
    st.markdown(
        "This is a **simulator**, not a design sheet. The intent is "
        "that you change one variable at a time and watch which check "
        "takes over.\n\n"
        "The connection is a chain. The reaction leaves the beam web, "
        "crosses the fillet welds into the end plate, passes through "
        "the bolts and lands in the supporting member. Each link has "
        "its own limit state, and the chain is only as strong as the "
        "weakest one.\n\n"
        "**Things worth trying**\n\n"
        "- Shorten the plate and watch beam web shear take over.\n"
        "- Thin the plate and watch prying grow.\n"
        "- Move the bolts toward an edge and watch bearing collapse "
        "into tear-out.\n"
        "- Raise the axial force and watch the bolt interaction "
        "check catch up with bolt shear.")

LEFT, RIGHT = st.columns([1.2, 1.0], gap="large")

with LEFT:

    # ==================================================================
    st.header("1. Applied Forces")
    st.caption("Factored loads at the connection")

    f1, f2, f3 = st.columns(3)
    with f1:
        Vf = st.number_input("Vf, beam end reaction (kN)",
                             0.0, 5000.0, 250.0, 1.0)
    with f2:
        Nf = st.number_input("Nf, axial force in the beam (kN)",
                             0.0, 5000.0, 50.0, 1.0)
    with f3:
        Hf = st.number_input("Hf, transverse force (kN)",
                             0.0, 5000.0, 50.0, 1.0)

    r_plate, r_weld = sc.resultant_forces(Vf, Nf, Hf)
    st.latex(r"R_{plate} = \sqrt{V_f^2 + N_f^2} "
             r"= \sqrt{%.0f^2 + %.0f^2} = %.2f\ \text{kN}"
             % (Vf, Nf, r_plate))
    st.latex(r"R_{weld} = \sqrt{V_f^2 + N_f^2 + H_f^2} = %.2f\ "
             r"\text{kN}" % r_weld)
    st.caption("The bolt group and the plate see the in-plane "
               "resultant. The welds see the full three dimensional "
               "resultant, because the transverse force twists them "
               "as well.")

    # ==================================================================
    st.header("2. Connection Configuration")
    st.caption("Every one of these connections is the same handful of "
               "parts arranged differently: a W column, a W beam, and "
               "either a plate, a pair of plates, angle cleats or an "
               "end plate between them. Build the configuration rather "
               "than picking from a fixed list.")

    _pnames = list(v3d.PRESETS.keys())
    if "cfg_preset" not in st.session_state:
        st.session_state.cfg_preset = _pnames[0]

    def _shift_preset(step):
        i = _pnames.index(st.session_state.cfg_preset)
        st.session_state.cfg_preset = _pnames[(i + step) % len(_pnames)]

    nprev, nsel, nnext = st.columns([1, 6, 1])
    with nprev:
        st.write("")
        st.button("Prev", use_container_width=True, key="cfg_prev",
                  on_click=_shift_preset, args=(-1,))
    with nnext:
        st.write("")
        st.button("Next", use_container_width=True, key="cfg_next",
                  on_click=_shift_preset, args=(1,))
    with nsel:
        preset_name = st.selectbox("Start from", _pnames,
                                   key="cfg_preset")
    base = v3d.preset(preset_name)
    st.progress((_pnames.index(preset_name) + 1) / len(_pnames),
                text="Preset %d of %d"
                     % (_pnames.index(preset_name) + 1, len(_pnames)))

    c1, c2 = st.columns(2)
    with c1:
        frame_lbl = st.selectbox(
            "Beam lands on", list(v3d.FRAMES.keys()),
            index=list(v3d.FRAMES.values()).index(base["frame"]),
            key="cfg_frame_%s" % preset_name)
        fam_lbl = st.selectbox(
            "Connecting element", list(v3d.FAMILIES.keys()),
            index=list(v3d.FAMILIES.values()).index(base["family"]),
            key="cfg_fam_%s" % preset_name)
    with c2:
        beam_attach = st.radio(
            "Attachment to the beam web", ["bolted", "welded"],
            index=0 if base["beam_attach"] == "bolted" else 1,
            horizontal=True, key="cfg_ba_%s" % preset_name)
        col_attach = st.radio(
            "Attachment to the column", ["welded", "bolted"],
            index=0 if base["col_attach"] == "welded" else 1,
            horizontal=True, key="cfg_ca_%s" % preset_name)

    o1, o2, o3 = st.columns(3)
    with o1:
        slotted = st.checkbox("Slotted holes", value=base["slotted"],
                              key="cfg_slot_%s" % preset_name,
                              disabled=(beam_attach == "welded"))
    with o2:
        coped = st.checkbox("Beam coped", value=base["coped"],
                            key="cfg_cope_%s" % preset_name)
    with o3:
        use_stiff = st.checkbox("Column stiffeners",
                                value=base["stiffeners"],
                                key="cfg_stiff_%s" % preset_name)

    _geo = {"frame": v3d.FRAMES[frame_lbl],
            "family": v3d.FAMILIES[fam_lbl],
            "beam_attach": beam_attach, "col_attach": col_attach,
            "slotted": bool(slotted and beam_attach == "bolted"),
            "coped": bool(coped), "stiffeners": bool(use_stiff)}
    det_key = "2" if _geo["family"] == "end_plate" else "1"
    det = {"kind": _geo["family"], "note": "", "learn": ""}

    chips = [fam_lbl, "on the " + frame_lbl.lower(),
             beam_attach + " to the beam web",
             col_attach + " to the column"]
    if _geo["slotted"]:
        chips.append("slotted")
    if _geo["coped"]:
        chips.append("coped")
    if _geo["stiffeners"]:
        chips.append("stiffened")
    st.caption("Model:  " + "  |  ".join(chips))

    if _geo["family"] == "end_plate" and beam_attach == "bolted":
        st.info("An end plate is welded to the beam end, not bolted to "
                "the web. The model welds it; the bolt group is what "
                "connects to the column.")
    if _geo["family"] != "end_plate":
        st.info("The bolt group sits a distance e from the weld line, "
                "so it carries an eccentricity. This page does not yet "
                "resolve the resulting moment.")

    # ==================================================================
    st.header("3. Members and Materials")

    src_lines = secd.status()
    with st.expander("Section data source"):
        for line in src_lines:
            st.caption(line)

    w_list = secd.designations("W")
    l_list = secd.designations("L")

    if not w_list:
        st.error("No W shape data available. Upload the CISC SST12.1 "
                 "workbook or check sst12.py.")
        st.stop()

    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**Supported beam**")
        default_beam = ("W250x39" if "W250x39" in w_list else w_list[0])
        beam_des = st.selectbox("Beam section", w_list,
                                index=w_list.index(default_beam))
        bp = secd.props("W", beam_des) or {}
        beam_d = float(bp.get("d") or 262.0)
        beam_bf = float(bp.get("b") or 147.0)
        tw_beam = float(bp.get("w") or 6.6)
        tf_beam = float(bp.get("t") or 11.2)
        st.caption("d = %.0f, bf = %.0f, w = %.1f, t = %.1f mm"
                   % (beam_d, beam_bf, tw_beam, tf_beam))
        Fy_beam = st.number_input("Fy beam (MPa)", 200.0, 700.0,
                                  350.0, 5.0)

    with m2:
        st.markdown("**Supporting element**")
        sup_kind = st.selectbox(
            "Support type",
            ["W column - bolt to the flange",
             "W column - bolt to the web",
             "Angle cleat (L section)",
             "Plate or HSS face - enter thickness"], index=0)
        if sup_kind.startswith("W column"):
            default_col = ("W250x33" if "W250x33" in w_list
                           else w_list[0])
            col_des = st.selectbox("Column section", w_list,
                                   index=w_list.index(default_col))
            cp = secd.props("W", col_des) or {}
            t_support = float(cp.get("t") if "flange" in sup_kind
                              else cp.get("w") or 9.1)
            col_tf = float(cp.get("t") or 9.1)
            st.caption("Column d = %.0f, bf = %.0f, w = %.1f, "
                       "t = %.1f mm. Bearing thickness taken as "
                       "%.1f mm."
                       % (cp.get("d") or 0, cp.get("b") or 0,
                          cp.get("w") or 0, col_tf, t_support))
        elif sup_kind.startswith("Angle"):
            if not l_list:
                st.error("No angle data available.")
                st.stop()
            default_ang = ("L102x102x13" if "L102x102x13" in l_list
                           else l_list[0])
            ang_des = st.selectbox("Angle", l_list,
                                   index=l_list.index(default_ang))
            ap = secd.props("L", ang_des) or {}
            t_support = float(ap.get("t") or 12.7)
            col_tf = t_support
            st.caption("Leg %.0f x %.0f, t = %.1f mm"
                       % (ap.get("d") or 0, ap.get("b") or 0, t_support))
        else:
            t_support = st.number_input("Supporting thickness (mm)",
                                        3.0, 100.0, 9.1, 0.1)
            col_tf = t_support
        Fsup_u = st.number_input("Fu support (MPa)", 300.0, 900.0,
                                 450.0, 5.0)

    # ---- schedule lookup for this beam and detail ----
    # An end plate carries a bolt line each side of the web; the
    # plate and cleat families bolt through a single line.
    _per_side = (_geo["family"] == "end_plate")
    sched, band, in_range = cdet.schedule_for(det_key, beam_des)
    if sched is None:
        st.warning("Could not read a nominal depth from %s." % beam_des)
        sched = {"t_plate": 8.0, "n_bolts": 2, "bolt": "M19",
                 "w_weld": 6.0}
        band, in_range = "W250", False
    if not in_range:
        st.warning("%s is deeper than the W610 row of the schedule. "
                   "The W610 values are shown, but the standard detail "
                   "does not cover this section." % beam_des)

    t1_stiff, w1_stiff, band_txt = cdet.stiffener_and_weld(tf_beam)

    sc1, sc2 = st.columns([2, 1])
    with sc1:
        st.dataframe(pd.DataFrame({
            "Item": ["Nominal depth band", "Minimum plate thickness",
                     "Bolts", "Fillet weld W",
                     "Stiffener plate T1", "Stiffener weld W1"],
            "Schedule value": [
                band, "%.0f mm" % sched["t_plate"],
                ("%d - %s%s" % (sched["n_bolts"], sched["bolt"],
                                " each side" if _per_side
                                else "")) if sched["n_bolts"]
                else "erection bolt only",
                "%.0f mm" % sched["w_weld"],
                "%.0f mm" % t1_stiff if _geo["stiffeners"] else "n/a",
                "%.0f mm" % w1_stiff if _geo["stiffeners"] else "n/a"],
        }), hide_index=True, use_container_width=True)
        if _geo["stiffeners"]:
            st.caption("Stiffener schedule keyed on the flange "
                       "thickness: %s." % band_txt)
        if _geo["slotted"]:
            sl = cdet.SLOT_SCHEDULE.get(band, {})
            st.caption("Slotted holes %s mm, c = %.0f mm. Slots reduce "
                       "bearing and remove axial restraint."
                       % (sl.get("slot", "-"), sl.get("c", 0.0)))
    with sc2:
        use_sched = st.checkbox("Use schedule values", value=True,
                                help="Uncheck to enter the plate, "
                                     "bolts and weld by hand.")

    # ==================================================================
    st.header("4. End Plate")

    p1, p2 = st.columns(2)
    with p1:
        t_def = sched["t_plate"] if use_sched else 8.0
        t_plate = st.number_input("Plate thickness t (mm)", 3.0, 60.0,
                                  float(t_def), 0.5)
        plate_L = st.number_input("Plate length L (mm)", 30.0, 1200.0,
                                  float(round(beam_d - 2*tf_beam - 20)),
                                  1.0)
    with p2:
        plate_W = st.number_input("Plate width W (mm)", 30.0, 800.0,
                                  124.0, 1.0)
        edge_condition = st.selectbox("Plate edge preparation",
                                      ["Gas cut edge", "Sheared edge"])
    if _geo["stiffeners"]:
        st.markdown("**Column stiffeners**")
        s1, s2, s3 = st.columns(3)
        with s1:
            stiff_n = st.number_input(
                "Number of stiffeners", 0, 12, 2, 1,
                help="Two with no pitch given sit opposite the beam "
                     "flanges. More are spread symmetrically about the "
                     "beam centreline.")
        with s2:
            stiff_sp = st.number_input(
                "Pitch (mm), 0 = align to the beam flanges",
                0.0, 1000.0, 0.0, 5.0)
        with s3:
            stiff_t_in = st.number_input(
                "Stiffener thickness (mm)", 3.0, 50.0,
                float(t1_stiff), 1.0)
        _h_clear = max(1.0, float(locals().get("cp", {}).get("d") or 300.0)
                       - 2.0 * float(locals().get("cp", {}).get("t") or 15.0))
        st.caption("Stiffener depth is fixed by the column: "
                   "h = d - 2t = %.0f mm. The schedule calls up "
                   "t = %.0f mm for a %.1f mm flange."
                   % (_h_clear, t1_stiff, tf_beam))
    else:
        stiff_n, stiff_sp, stiff_t_in = 0, 0.0, t1_stiff

    if _geo["family"] != "end_plate":
        g1, g2, g3 = st.columns(3)
        with g1:
            ecc_e = st.number_input(
                "e, bolt line to weld line (mm)", 10.0, 400.0, 60.0, 1.0,
                help="The eccentricity the bolt group carries. This "
                     "page does not yet resolve the resulting moment.")
        with g2:
            tab_len = st.number_input("Plate projection (mm)", 30.0,
                                      600.0, 100.0, 1.0)
        with g3:
            setback = st.number_input("Beam setback (mm)", 0.0, 100.0,
                                      10.0, 1.0)
        angle_leg = st.number_input(
            "Angle leg (mm), used for the cleat family", 40.0, 250.0,
            89.0, 1.0) if _geo["family"] == "angles" else 0.0
    else:
        ecc_e, tab_len, setback, angle_leg = 0.0, 0.0, 0.0, 0.0

    q1, q2 = st.columns(2)
    with q1:
        Fyp = st.number_input("Fy plate (MPa)", 200.0, 700.0, 300.0, 5.0)
    with q2:
        Fup_u = st.number_input("Fu plate (MPa)", 300.0, 900.0,
                                450.0, 5.0)

    # ==================================================================
    st.header("5. Bolts and Layout")

    b1, b2, b3 = st.columns(3)
    with b1:
        _blist = list(sc.BOLTS.keys())
        _bdef = cdet.METRIC_BOLT_MAP.get(sched["bolt"], "A325 (1 in)")
        if not use_sched:
            _bdef = "A325 (1 in)"
        bolt_name = st.selectbox("Bolt", _blist,
                                 index=_blist.index(_bdef))
        _ndef = int(sched["n_bolts"]) or 2
        if _per_side:
            _ndef = _ndef * 2
        if not use_sched:
            _ndef = 4
        n_bolts = st.number_input("n, total number of bolts",
                                  2, 40, max(2, _ndef), 2,
                                  help="The schedule lists bolts per "
                                       "side where the detail says so; "
                                       "this field is the total.")
        st.caption("Schedule calls up %s (%s)."
                   % (sched["bolt"],
                      cdet.METRIC_BOLT_MAP.get(sched["bolt"], "-")))
    with b2:
        threads = st.selectbox("Shear plane",
                               ["Threads intercepted (N)",
                                "Threads excluded (X)"], index=0)
        hole_type = st.selectbox(
            "Hole type", ["Standard", "Oversize"],
            index=1 if _geo["slotted"] else 0,
            help="The slotted arrangement uses slotted holes. "
                 "Oversize is the closest approximation here.")
    with b3:
        pitch = st.number_input("p, pitch (mm)", 20.0, 400.0,
                                100.0, 1.0)
        gage = st.number_input("g, gage (mm)", 20.0, 500.0, 60.0, 1.0)

    e1, e2 = st.columns(2)
    with e1:
        ev = st.number_input("ev, vertical end distance (mm)",
                             5.0, 200.0, 32.0, 1.0)
    with e2:
        eh = st.number_input("eh, horizontal edge distance (mm)",
                             5.0, 200.0, 32.0, 1.0)

    bolt = sc.bolt_props(bolt_name)
    n_rows = max(1, int(round(n_bolts / 2.0)))
    d_hole = sc.hole_diameter(bolt["db"], hole_type)
    st.caption("Bolt d = %.2f mm, Ab = %.0f mm2, Fu = %.0f MPa. "
               "%d rows of 2. Hole diameter %.2f mm."
               % (bolt["db"], bolt["Ab"], bolt["Fub"], n_rows, d_hole))

    # ==================================================================
    st.header("6. Weld")

    w1, w2 = st.columns(2)
    with w1:
        electrode = st.selectbox("Electrode", list(sc.ELECTRODES.keys()),
                                 index=1)
        Xu = sc.ELECTRODES[electrode]
    with w2:
        weld_mode = st.radio("Leg size from",
                             ["Schedule (mm)", "Imperial list"],
                             horizontal=True)
        if weld_mode.startswith("Schedule"):
            weld_D = st.number_input(
                "Fillet leg D (mm)", 3.0, 25.0,
                float(sched["w_weld"]) if use_sched else 6.0, 1.0)
        else:
            weld_in = st.selectbox(
                "Fillet leg size", sc.WELD_SIZES_IN, index=1,
                format_func=lambda x: "%.4f in (%.2f mm)"
                % (x, x * 25.4))
            weld_D = weld_in * 25.4
        st.caption("Schedule calls up W = %.0f mm." % sched["w_weld"])

    dmin, dmax = sc.weld_leg_limits(min(t_plate, tw_beam))
    if weld_D > dmax:
        st.error("Leg %.2f mm exceeds the maximum %.2f mm for a %.1f "
                 "mm element (Cl. 13.13.2.2)." % (weld_D, dmax,
                                                  min(t_plate, tw_beam)))
    elif weld_D < dmin:
        st.warning("Leg %.2f mm is below the minimum %.2f mm for the "
                   "thicker part joined (Table 13)."
                   % (weld_D, dmin))
    else:
        st.success("Leg %.2f mm is within the %.2f to %.2f mm range."
                   % (weld_D, dmin, dmax))

    # ==================================================================
    inp = dict(bolt_name=bolt_name, n_bolts=int(n_bolts),
               threads_intercepted=threads.startswith("Threads inter"),
               n_planes_bolt=1, hole_type=hole_type,
               Vf=Vf, Nf=Nf, Hf=Hf,
               plate_L=plate_L, plate_W=plate_W, t_plate=t_plate,
               Fyp=Fyp, Fup_u=Fup_u, t_support=t_support,
               Fsup_u=Fsup_u, pitch=pitch, gage=gage, ev=ev, eh=eh,
               tw_beam=tw_beam, tf_beam=tf_beam, beam_d=beam_d,
               beam_bf=beam_bf, Fy_beam=Fy_beam,
               weld_D=weld_D, Xu=Xu, weld_theta=0.0,
               edge_condition=edge_condition,
               config=_geo,
               col_d=float(locals().get("cp", {}).get("d") or 300.0),
               col_bf=float(locals().get("cp", {}).get("b") or 300.0),
               col_tw=float(locals().get("cp", {}).get("w") or 10.0),
               col_tf=float(locals().get("cp", {}).get("t") or 15.0),
               ecc=ecc_e, tab_len=tab_len, setback=setback,
               angle_leg_col=angle_leg, angle_leg_beam=angle_leg,
               stiff_t=stiff_t_in, stiff_n=stiff_n, stiff_sp=stiff_sp)

    checks, extras = sc.run_all(inp)
    gov = extras["governing"]

    # ==================================================================
    st.header("7. Detailing Checks")
    st.caption("CSA S16 Cl. 22.3. These are geometry rules. They do "
               "not produce a capacity, but a connection that fails "
               "them is not buildable.")

    det_rows = []
    det_fail = 0
    for lab, val, lim, ok, cl in extras["detailing"]:
        det_rows.append({"Check": lab, "Value": round(val, 1),
                         "Limit": round(lim, 1),
                         "Status": "OK" if ok else "REVIEW",
                         "Reference": cl})
        if not ok:
            det_fail += 1
    st.dataframe(pd.DataFrame(det_rows), hide_index=True,
                 use_container_width=True)
    if det_fail:
        st.warning("%d detailing item(s) need review." % det_fail)

    # ==================================================================
    st.header("8. Limit States, in Load Path Order")

    ORDER = ["beam_web", "weld", "plate_shear_yield",
             "plate_shear_rupture", "block_shear",
             "bearing_end_plate", "plate_bending", "bolt_shear",
             "bolt_tension", "interaction",
             "bearing_supporting_member"]
    by_key = dict((c["key"], c) for c in checks)
    ordered = [by_key[k] for k in ORDER if k in by_key]

    for i, c in enumerate(ordered, start=1):
        flag = "OK" if c["ok"] else "NOT OK"
        head = "%d.  %s  -  %s  -  ratio %.3f  -  %s" % (
            i, c["name"], c["clause"], c["ratio"], flag)
        with st.expander(head, expanded=not c["ok"]):
            st.markdown("**Why this check exists**")
            st.caption(c["why"])
            st.latex(c["formula"])
            st.latex(c["subs"])
            if c["note"]:
                st.caption("Note: " + c["note"])
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("Demand", "%.2f" % c["demand"])
            cc2.metric("Capacity", "%.2f" % c["capacity"])
            cc3.metric("Ratio", "%.3f" % c["ratio"])
            if not c["ok"]:
                st.error("This check does not pass.")

    # ==================================================================
    st.header("9. Prying Action in Detail")
    st.caption("The one piece of this connection that is not a simple "
               "strength formula.")

    p = extras["pry"]
    st.markdown(
        "Prying is a geometry problem before it is a strength "
        "problem. When the beam pulls away from the support, the "
        "plate cannot stay flat: it bends between the bolt line and "
        "the beam web, and its outer edge presses back against the "
        "support. That contact force is the prying force, and it is "
        "carried by the bolts on top of the applied tension.")
    st.latex(r"b = \tfrac{1}{2}(g - w) = %.1f \quad "
             r"b' = b - \tfrac{d}{2} = %.1f \quad "
             r"a = \min(e_h,\ 1.25b) = %.1f \quad "
             r"a' = a + \tfrac{d}{2} = %.1f"
             % (p["b"], p["b_prime"], p["a"], p["a_prime"]))
    st.latex(r"\delta = 1 - \frac{d_{hole}}{p} = %.3f \qquad "
             r"K = \frac{4b'}{\phi\, p\, F_y} = %.3f"
             % (p["delta"], p["K"]))
    st.latex(r"q = \frac{b'}{a'}\cdot"
             r"\frac{\delta\alpha_b}{1 + \delta\alpha_b} = %.3f "
             r"\qquad T_f(1+q) = %.2f\ \text{kN}"
             % (p["q"], p["Tf_pry"]))
    st.caption("alpha is clamped to the range 0 to 1. The raw values "
               "here are alpha_b = %.2f and alpha_c = %.2f. A "
               "negative alpha means the plate is thick enough that "
               "no prying develops."
               % (p["alpha_b_raw"], p["alpha_c_raw"]))

    if p["alpha_b"] <= 0:
        st.success("alpha_b = 0. The plate is stiff enough that the "
                   "bolts see no prying force at this load.")
    else:
        st.info("alpha_b = %.2f. Prying adds %.1f%% to the bolt "
                "tension. Try increasing the plate thickness."
                % (p["alpha_b"], 100.0 * p["q"]))

    # ==================================================================
    st.header("10. Summary")

    sum_rows = [{"#": i, "Limit state": c["name"],
                 "Clause": c["clause"],
                 "Demand": round(c["demand"], 2),
                 "Capacity": round(c["capacity"], 2),
                 "Ratio": round(c["ratio"], 3),
                 "Status": "OK" if c["ok"] else "NOT OK"}
                for i, c in enumerate(ordered, start=1)]
    st.dataframe(pd.DataFrame(sum_rows), hide_index=True,
                 use_container_width=True)

    if gov["ok"]:
        st.success("Governing limit state: %s at a ratio of %.3f "
                   "(%s). The connection is adequate."
                   % (gov["name"], gov["ratio"], gov["clause"]))
    else:
        st.error("Governing limit state: %s at a ratio of %.3f (%s). "
                 "The connection is NOT adequate."
                 % (gov["name"], gov["ratio"], gov["clause"]))
        st.caption("What to change: " + {
            "beam_web": "lengthen the plate, or use a heavier beam. "
                        "Web shear scales directly with plate depth.",
            "weld": "increase the leg size or lengthen the weld. "
                    "Capacity scales linearly with both.",
            "plate_shear_yield": "thicken or lengthen the plate.",
            "plate_shear_rupture": "thicken the plate, or use fewer "
                                   "and larger bolts to remove less "
                                   "material.",
            "block_shear": "increase the end and edge distances, "
                           "which lengthen the tear-out path.",
            "bearing_end_plate": "thicken the plate or increase the "
                                 "end distance.",
            "bearing_supporting_member": "the supporting element is "
                                         "too thin for these bolts.",
            "plate_bending": "thicken the plate. Capacity goes with "
                             "t squared.",
            "bolt_tension": "add bolts, go up a diameter, or thicken "
                            "the plate to cut prying.",
            "bolt_shear": "add bolts, go up a diameter, or move to "
                          "threads excluded from the shear plane.",
            "interaction": "shear and tension are combining. Adding "
                           "bolts helps both terms at once.",
        }.get(gov["key"], "review the geometry."))

    st.caption("Resistance factors used: phi = %.2f, phi_u = %.2f, "
               "phi_b = %.2f, phi_br = %.2f, phi_w = %.2f "
               "(Cl. 13.1)." % (sc.PHI, sc.PHI_U, sc.PHI_B,
                                sc.PHI_BR, sc.PHI_W))


# ----------------------------------------------------------------------
# Viewer
# ----------------------------------------------------------------------
with RIGHT:
    st.subheader("3D Model")
    v3d.render(v3d.build_payload(inp, checks, extras), height=660)
    st.caption("Dropdown switches between the assembly, the load path "
               "and each failure surface. Labels hides all the text in "
               "the scene. Explode separates the parts, X-ray makes the "
               "steel translucent, Fit frames the whole model. The zoom "
               "slider and the wheel both step in even increments.")

    st.markdown("**Governing limit state**")
    st.metric(gov["name"], "%.3f" % gov["ratio"],
              delta="%.1f%% of capacity" % (100.0 * gov["ratio"]),
              delta_color="inverse")

    st.markdown("**Sensitivity**")
    st.caption("How the governing ratio responds to a single change, "
               "all else held constant.")

    sens = []
    for lab, key, mult in [("Plate 25% thicker", "t_plate", 1.25),
                           ("Plate 25% longer", "plate_L", 1.25),
                           ("Weld leg 25% larger", "weld_D", 1.25),
                           ("Pitch 25% larger", "pitch", 1.25)]:
        trial = dict(inp)
        trial[key] = inp[key] * mult
        try:
            tchecks, textras = sc.run_all(trial)
            new_gov = textras["governing"]
            sens.append({"Change": lab,
                         "New governing": new_gov["name"],
                         "Ratio": round(new_gov["ratio"], 3),
                         "Delta": round(new_gov["ratio"]
                                        - gov["ratio"], 3)})
        except Exception:
            pass
    if sens:
        st.dataframe(pd.DataFrame(sens), hide_index=True,
                     use_container_width=True)
