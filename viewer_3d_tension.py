"""
viewer_3d_tension.py

Streamlit wrapper for the tension member viewer.

Same shape as viewer_3d_flexure.py, viewer_3d_beamcolumn.py and
viewer_3d_welded.py: the page hands over what it already computed, this
module turns it into the JSON the template reads, and
viewer_3d_tension.html draws it.

It does NOT go through viewer_3d.build_payload. That builder extrudes a
rolled section outline along the member, which cannot carry bolt holes.
The connected element here is built in plan with real holes cut in it,
so the geometry is assembled in the template from the dimensions passed
below. viewer_3d.py, viewer_3d.html and section_geometry.py are
untouched, so the Compression, Flexure, Beam-Column and Welded pages are
unaffected.

    import viewer_3d_tension
    viewer_3d_tension.render_tension_member(
        section_type="Single Angle", label=chosen,
        bolt=bp, hole_dia=hole_dia, d_eff=d_eff,
        w_conn=w_conn, t_conn=t,
        net_paths=paths, block_paths=bs_pats,
        U=U, Ut=Ut, Fy=mat.Fy, Fu=mat.Fu, Ag=Ag,
        calcs=calcs, Tf=Tf, leg_out=leg_out)

What the viewer draws
---------------------
The connected element in plan with every bolt hole cut through it, the
outstanding elements that make the section what it is, the bolts, the
gusset, and then one selectable overlay per limit state:

  gross yielding   the full section, away from every hole
  net fracture     one ribbon per candidate tear path, governing in red
  block shear      shear planes plus a tension plane per pattern, and
                   the block that tears out of the member
  utilisation      the member coloured by Tf / Tr

Every candidate path is passed through, not just the governing one, so
the page and the model always agree on what was considered.
"""

import json
import os

import streamlit as st
import streamlit.components.v1 as components


_HTML_NAME = "viewer_3d_tension.html"

PHI_U_DEFAULT = 0.75


# ===========================================================
# section type -> the shape the template builds
# ===========================================================

_KIND_BY_TYPE = {
    "plate": "plate",
    "single angle": "angle",
    "double angle": "double_angle",
    "wt section": "wt",
    "wt": "wt",
    "channel (c / mc)": "channel",
    "channel": "channel",
}


def _kind_of(section_type):
    return _KIND_BY_TYPE.get(str(section_type or "").strip().lower(), "plate")


def _template_path():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, _HTML_NAME)
    if os.path.exists(p):
        return p
    up = os.path.join(os.path.dirname(here), _HTML_NAME)
    if os.path.exists(up):
        return up
    return None


def _num(x, default=None):
    if x is None or x == "":
        return default
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if v != v:
        return default
    return v


def _attr(obj, name, default=None):
    """Read from a dataclass or a dict, whichever the page passes."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ===========================================================
# per-path resistances
#
# These mirror calc_net_fracture_paths and calc_block_shear_paths on the
# page, so the number on a ribbon in the model is the same number in the
# expander above it. If either clause changes on the page, change it
# here too.
# ===========================================================


def net_path_Tr_kN(An_mm2, U, Fu, area_mult=1.0, phi_u=PHI_U_DEFAULT):
    """Cl. 13.2 a) iii): Tr = phi_u * U * An * Fu."""
    return phi_u * U * (An_mm2 * area_mult) * Fu / 1000.0


def block_Fbs(Fy, Fu):
    """Cl. 13.11 shear basis. Above 460 MPa the code drops the average
    and uses Fy, which is the same rule the page warns about."""
    if Fy > 460.0:
        return float(Fy)
    return (float(Fy) + float(Fu)) / 2.0


def block_path_Tr_kN(Ant, Agv, planes, Fy, Fu, Ut, area_mult=1.0,
                     phi_u=PHI_U_DEFAULT):
    """Cl. 13.11: Tr = phi_u * [Ut Ant Fu + 0.6 Agv Fbs]."""
    Ant_total = Ant * area_mult
    Agv_total = Agv * planes * area_mult
    return phi_u * (Ut * Ant_total * Fu
                    + 0.6 * Agv_total * block_Fbs(Fy, Fu)) / 1000.0


# ===========================================================
# payload
# ===========================================================


def build_payload(section_type, label, bolt, hole_dia, d_eff, w_conn,
                  t_conn, net_paths=None, block_paths=None, U=1.0, Ut=1.0,
                  Fy=350.0, Fu=450.0, Ag=0.0, calcs=None, Tf=0.0,
                  area_mult=1.0, phi_u=PHI_U_DEFAULT, bolt_size=None,
                  bolt_dia=None, leg_out=0.0, b_flange=0.0, d_depth=0.0,
                  t_flange=0.0, t_stem=0.0, connected="", gusset_t=0.0,
                  clause=None, bg="#0d1117"):
    """Normalise everything the template reads."""

    n_lines = int(_attr(bolt, "n_lines", 1) or 1)
    rows = int(_attr(bolt, "bolts_per_line", 2) or 2)
    pitch = _num(_attr(bolt, "pitch"), 80.0)
    gauge = _num(_attr(bolt, "gauge"), 60.0)
    e1 = _num(_attr(bolt, "edge_end"), 40.0)
    e2 = _num(_attr(bolt, "edge_trans"), 30.0)

    dh = _num(hole_dia, 22.0)
    de = _num(d_eff, dh)

    # ---- net section fracture, every candidate path ----
    net_out = []
    for p in (net_paths or []):
        An = _num(p.get("An_mm2"), 0.0)
        desc = str(p.get("description", "path"))
        n_stag = int(p.get("n_staggers", 0) or 0)
        net_out.append({
            "desc": desc,
            "n_holes": int(p.get("n_holes", 1) or 1),
            "n_staggers": n_stag,
            "stagger_term": _num(p.get("stagger_term"), 0.0),
            "An": An * area_mult,
            "Tr": net_path_Tr_kN(An, U, Fu, area_mult, phi_u),
            "zig": bool(n_stag > 0 or "zig" in desc.lower()),
            "governs": False,
        })
    if net_out:
        gi = min(range(len(net_out)), key=lambda i: net_out[i]["Tr"])
        net_out[gi]["governs"] = True

    # ---- block shear, every candidate pattern ----
    blk_out = []
    for p in (block_paths or []):
        Ant = _num(p.get("Ant"), 0.0)
        Agv = _num(p.get("Agv"), 0.0)
        planes = int(p.get("planes", 1) or 1)
        blk_out.append({
            "key": str(p.get("key", "A")),
            "Lv": _num(p.get("Lv_mm"), e1 + (rows - 1) * pitch),
            "wnt": _num(p.get("tension_width_mm"), 0.0),
            "planes": planes,
            "Tr": block_path_Tr_kN(Ant, Agv, planes, Fy, Fu, Ut,
                                   area_mult, phi_u),
            "governs": False,
        })
    if blk_out:
        gi2 = min(range(len(blk_out)), key=lambda i: blk_out[i]["Tr"])
        blk_out[gi2]["governs"] = True

    # ---- governing limit state, taken from the page's own Calc list ----
    Tr_gross = Tr_net = Tr_block = None
    gov_name = None
    Tr_gov = None
    for c in (calcs or []):
        nm = str(_attr(c, "name", ""))
        val = _num(_attr(c, "value"))
        if val is None:
            continue
        low = nm.lower()
        if "gross" in low:
            Tr_gross = val
        elif "net section" in low:
            Tr_net = val
        elif "block" in low:
            Tr_block = val
        if Tr_gov is None or val < Tr_gov:
            Tr_gov = val
            gov_name = nm.split("(")[0].strip()

    Tf_v = _num(Tf, 0.0) or 0.0
    util = None
    overall = "INCOMPLETE"
    if Tr_gov and Tr_gov > 0 and Tf_v > 0:
        util = Tf_v / Tr_gov
        overall = "OK" if util <= 1.0 else "NG"
    elif Tr_gov:
        overall = ""

    props = [
        {"group": "Material", "symbol": "Fy", "value": "%.0f" % Fy,
         "unit": "MPa"},
        {"group": "Material", "symbol": "Fu", "value": "%.0f" % Fu,
         "unit": "MPa"},
        {"group": "Section", "symbol": "Ag",
         "value": "{:,.0f}".format(Ag or 0.0), "unit": "mm2"},
        {"group": "Section", "symbol": "w conn", "value": "%.1f" % w_conn,
         "unit": "mm"},
        {"group": "Section", "symbol": "t conn", "value": "%.1f" % t_conn,
         "unit": "mm"},
        {"group": "Bolts", "symbol": "lines", "value": str(n_lines),
         "unit": ""},
        {"group": "Bolts", "symbol": "rows", "value": str(rows), "unit": ""},
        {"group": "Bolts", "symbol": "s", "value": "%.0f" % pitch,
         "unit": "mm"},
        {"group": "Bolts", "symbol": "g", "value": "%.0f" % gauge,
         "unit": "mm"},
        {"group": "Bolts", "symbol": "e1", "value": "%.0f" % e1,
         "unit": "mm"},
        {"group": "Bolts", "symbol": "e2", "value": "%.0f" % e2,
         "unit": "mm"},
        {"group": "Bolts", "symbol": "hole", "value": "%.1f" % dh,
         "unit": "mm"},
        {"group": "Bolts", "symbol": "d_eff", "value": "%.1f" % de,
         "unit": "mm"},
        {"group": "Factors", "symbol": "U", "value": "%.2f" % U, "unit": ""},
        {"group": "Factors", "symbol": "Ut", "value": "%.2f" % Ut,
         "unit": ""},
    ]
    for nm2, v2 in (("Tr gross", Tr_gross), ("Tr net", Tr_net),
                    ("Tr block", Tr_block)):
        if v2 is not None:
            props.append({"group": "Resistances", "symbol": nm2,
                          "value": "{:,.1f}".format(v2), "unit": "kN"})
    if util is not None:
        props.append({"group": "Resistances", "symbol": "Tf/Tr",
                      "value": "%.3f" % util, "unit": ""})

    return {
        "kind": _kind_of(section_type),
        "label": label or str(section_type),
        "clause": clause or ("Cl. 13.2, 12.3.3 and 13.11"),
        "bg": bg,
        "sec": {
            "w_conn": _num(w_conn, 140.0),
            "t_conn": _num(t_conn, 10.0),
            "connected": str(connected or ""),
            "leg_out": _num(leg_out, 0.0) or 0.0,
            "b_flange": _num(b_flange, 0.0) or 0.0,
            "d_depth": _num(d_depth, 0.0) or 0.0,
            "t_flange": _num(t_flange, 0.0) or 0.0,
            "t_stem": _num(t_stem, 0.0) or 0.0,
            "gusset_t": _num(gusset_t, 0.0) or 0.0,
        },
        "bolt": {
            "n_lines": n_lines,
            "bolts_per_line": rows,
            "pitch": pitch,
            "gauge": gauge,
            "edge_end": e1,
            "edge_trans": e2,
            "hole_dia": dh,
            "d_eff": de,
            "bolt_dia": _num(bolt_dia, max(dh - 2.0, 2.0)),
            "size": bolt_size or "",
        },
        "net": net_out,
        "block": blk_out,
        "res": {
            "Ag": _num(Ag, 0.0),
            "U": _num(U, 1.0),
            "Ut": _num(Ut, 1.0),
            "Tr_gross": Tr_gross,
            "Tr_net": Tr_net,
            "Tr_block": Tr_block,
            "Tr": Tr_gov,
            "Tf": Tf_v,
            "util": util,
            "gov_name": gov_name,
            "overall": overall,
        },
        "props": props,
    }


def render_tension_member(section_type, label, bolt, hole_dia, d_eff,
                          w_conn, t_conn, net_paths=None, block_paths=None,
                          U=1.0, Ut=1.0, Fy=350.0, Fu=450.0, Ag=0.0,
                          calcs=None, Tf=0.0, area_mult=1.0,
                          phi_u=PHI_U_DEFAULT, bolt_size=None, bolt_dia=None,
                          leg_out=0.0, b_flange=0.0, d_depth=0.0,
                          t_flange=0.0, t_stem=0.0, connected="",
                          gusset_t=0.0, clause=None, height=680,
                          bg="#0d1117", show_diagnostics=False):
    """Render the member. Returns the payload, or None."""
    path = _template_path()
    if path is None:
        st.info("3D viewer not loaded. Place viewer_3d_tension.py and "
                "viewer_3d_tension.html in the repository root.")
        return None

    try:
        payload = build_payload(
            section_type, label, bolt, hole_dia, d_eff, w_conn, t_conn,
            net_paths=net_paths, block_paths=block_paths, U=U, Ut=Ut,
            Fy=Fy, Fu=Fu, Ag=Ag, calcs=calcs, Tf=Tf, area_mult=area_mult,
            phi_u=phi_u, bolt_size=bolt_size, bolt_dia=bolt_dia,
            leg_out=leg_out, b_flange=b_flange, d_depth=d_depth,
            t_flange=t_flange, t_stem=t_stem, connected=connected,
            gusset_t=gusset_t, clause=clause, bg=bg)
    except Exception as exc:
        st.warning("Could not build the member model: " + str(exc))
        return None

    fh = open(path, "r")
    html = fh.read()
    fh.close()
    html = html.replace("__GEOMETRY_JSON__", json.dumps(payload))

    components.html(html, height=height, scrolling=False)

    if show_diagnostics:
        cols = st.columns(4)
        cols[0].metric("Kind", payload["kind"])
        cols[1].metric("Net paths", str(len(payload["net"])))
        cols[2].metric("Block patterns", str(len(payload["block"])))
        u = payload["res"]["util"]
        cols[3].metric("Tf/Tr", "-" if u is None else "%.3f" % u)

    return payload
