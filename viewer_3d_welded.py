"""
viewer_3d_welded.py

Streamlit wrapper for the welded connection viewer.

Same shape as viewer_3d_flexure.py and viewer_3d_beamcolumn.py: the page
hands over a description of the joint and the results, this module turns
it into the JSON the template reads, and viewer_3d_welded.html draws it.

It does NOT go through viewer_3d.build_payload. That builder produces a
rolled section outline from the CISC tables, and a welded joint has no
section to extrude - it has plates, beads, throats and fusion faces. So
the geometry is built in the template from the dimensions passed here.
viewer_3d.py, viewer_3d.html and section_geometry.py are untouched, so
the Compression, Flexure and Beam-Column pages are unaffected.

    import viewer_3d_welded
    viewer_3d_welded.render_joint(
        kind="fillet", label="Fillet weld, 3 segments",
        dims={...}, segments=[...], loads={...}, results={...},
        detailing=[...], props=[...])

Payload contract for the template
---------------------------------
kind      "fillet" | "cjp" | "pjp" | "flare"
          Selects which joint the template builds.

dims      {"t1": thinner part mm, "t2": thicker part mm,
           "D": fillet leg mm, "throat": effective throat mm,
           "gap": groove root opening mm, "penetration": PJP depth mm,
           "has_fillet": bool, "wf": flare face width mm,
           "L_fb": flare weld length mm}

segments  [{"L": mm, "theta": deg, "Aw": mm2, "Vr_kN": float,
            "Mw": float, "orient": float, "share": 0..1, "util": float}]
          One entry per weld segment. share is that segment's fraction of
          the total weld-metal resistance, and is what the capacity
          colour map reads.

loads     {"Vf_kN": float, "Tf_kN": float}

results   {"Vr_kN":, "Tr_kN":, "util":, "overall": "OK"|"NG"|"INCOMPLETE",
           "governs": "weld metal" | "base metal",
           "Vr_weld_kN":, "Vr_base_kN":, "detail_ok": bool}
          governs is what decides which surface the Rupture effect tears
          on: the throat for weld metal, the fusion face for base metal.

detailing [{"label":, "actual":, "limit":, "op": ">=" | "<=", "ok": bool,
            "unit":}]

props     [{"group":, "symbol":, "value":, "unit":}]
          Shown in the Design data panel.
"""

import json
import os

import streamlit as st
import streamlit.components.v1 as components


_HTML_NAME = "viewer_3d_welded.html"


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
    if v != v:  # NaN
        return default
    return v


def build_payload(kind, label=None, clause=None, dims=None, segments=None,
                  loads=None, results=None, detailing=None, props=None,
                  bg="#0d1117"):
    """Normalise everything the template reads. Missing values become
    None rather than zero, so the template can tell 'not computed' from
    'computed as zero'."""
    kind = str(kind or "fillet").lower()
    if kind not in ("fillet", "cjp", "pjp", "flare"):
        kind = "fillet"

    d_in = dims or {}
    d_out = {}
    for k in ("t1", "t2", "D", "throat", "gap", "penetration", "wf", "L_fb"):
        v = _num(d_in.get(k))
        if v is not None:
            d_out[k] = v
    d_out["has_fillet"] = bool(d_in.get("has_fillet", False))

    segs_out = []
    for s in (segments or []):
        segs_out.append({
            "L": _num(s.get("L"), 100.0),
            "theta": _num(s.get("theta"), 0.0),
            "Aw": _num(s.get("Aw")),
            "Vr_kN": _num(s.get("Vr_kN")),
            "Mw": _num(s.get("Mw"), 1.0),
            "orient": _num(s.get("orient"), 1.0),
            "share": _num(s.get("share"), 0.0),
            "util": _num(s.get("util")),
        })

    l_in = loads or {}
    l_out = {"Vf_kN": _num(l_in.get("Vf_kN"), 0.0),
             "Tf_kN": _num(l_in.get("Tf_kN"), 0.0)}

    r_in = results or {}
    r_out = {
        "Vr_kN": _num(r_in.get("Vr_kN")),
        "Tr_kN": _num(r_in.get("Tr_kN")),
        "Vr_weld_kN": _num(r_in.get("Vr_weld_kN")),
        "Vr_base_kN": _num(r_in.get("Vr_base_kN")),
        "util": _num(r_in.get("util")),
        "governs": r_in.get("governs"),
        "overall": r_in.get("overall"),
        "detail_ok": r_in.get("detail_ok"),
    }

    det_out = []
    for c in (detailing or []):
        det_out.append({
            "label": str(c.get("label", "")),
            "actual": _num(c.get("actual")),
            "limit": _num(c.get("limit")),
            "op": c.get("op", ">="),
            "ok": bool(c.get("ok")),
            "unit": c.get("unit", "mm"),
        })

    return {
        "kind": kind,
        "label": label or "Welded joint",
        "clause": clause or "",
        "bg": bg,
        "dims": d_out,
        "segments": segs_out,
        "loads": l_out,
        "results": r_out,
        "detailing": det_out,
        "props": props or [],
    }


def render_joint(kind, label=None, clause=None, dims=None, segments=None,
                 loads=None, results=None, detailing=None, props=None,
                 height=660, bg="#0d1117", show_diagnostics=False):
    """Render the joint. Returns the payload, or None if the template is
    missing or the payload could not be built."""
    path = _template_path()
    if path is None:
        st.error("viewer_3d_welded.html was not found. Put it in the same "
                 "folder as viewer_3d_welded.py.")
        return None

    try:
        payload = build_payload(kind, label=label, clause=clause, dims=dims,
                                segments=segments, loads=loads,
                                results=results, detailing=detailing,
                                props=props, bg=bg)
    except Exception as exc:
        st.warning("Could not build the joint model: " + str(exc))
        return None

    fh = open(path, "r")
    html = fh.read()
    fh.close()
    html = html.replace("__GEOMETRY_JSON__", json.dumps(payload))

    components.html(html, height=height, scrolling=False)

    if show_diagnostics:
        cols = st.columns(4)
        cols[0].metric("Joint type", payload["kind"])
        cols[1].metric("Segments", str(len(payload["segments"])))
        thr = payload["dims"].get("throat")
        cols[2].metric("Throat (mm)", "-" if thr is None else "%.2f" % thr)
        u = payload["results"].get("util")
        cols[3].metric("Utilisation", "-" if u is None else "%.3f" % u)

    return payload
