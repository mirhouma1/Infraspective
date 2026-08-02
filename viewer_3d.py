"""
viewer_3d.py

Streamlit wrapper for the parametric 3D member viewer.

Reads the section dimensions and, when the caller supplies them, the end
conditions, unbraced lengths, factored load and check results, so the
model shows what was actually entered rather than a generic stick.

    import viewer_3d
    viewer_3d.render_member(sec, length_mm=4000,
                            supports={...}, load={...},
                            elements_t1=[...], elements_t2=[...],
                            results={...})

Nothing is cached to disk and no model files are stored.
"""

import json
import os

import streamlit as st

import section_geometry


_HTML_NAME = "viewer_3d.html"


def _template_path():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, _HTML_NAME)
    if os.path.exists(p):
        return p
    up = os.path.join(os.path.dirname(here), _HTML_NAME)
    if os.path.exists(up):
        return up
    return None


def _round_loop(loop):
    return [[round(p[0], 3), round(p[1], 3)] for p in loop]


def build_payload(sec, length_mm, supports=None, load=None,
                  elements_t1=None, elements_t2=None, results=None,
                  props=None, metalness=0.85, roughness=0.30, segments=8):
    """Turn a SectionProps object plus the page inputs into viewer JSON."""
    outline = section_geometry.section_outline(sec, segments=segments)

    d = getattr(sec, "d_mm", None)
    b = getattr(sec, "b_mm", None)
    t = getattr(sec, "t_mm", None)
    w = getattr(sec, "w_mm", None)
    h = getattr(sec, "h_mm", None)

    # A tee outline is recentred, so the viewer needs the centroid height
    # to know where the flange sits.
    y_bar = None
    if outline["kind"] == "TEE" and d is not None:
        ys = [p[1] for p in outline["outer"]]
        y_bar = d + min(ys)

    payload = {
        "outer": _round_loop(outline["outer"]),
        "holes": [_round_loop(x) for x in outline["holes"]],
        "extra_loops": [_round_loop(x) for x in outline["extra_loops"]],
        "kind": outline["kind"],
        "zones": outline["zones"],
        "length_mm": float(length_mm),
        "label": str(outline.get("designation", "")),
        "family_label": str(getattr(sec, "family_label", "")),
        "dims": {
            "d": d, "b": b, "t": t, "w": w, "h": h, "y_bar": y_bar,
        },
        "supports": supports,
        "load": load,
        "elements_t1": elements_t1 or [],
        "elements_t2": elements_t2 or [],
        "results": results,
        # calculation inputs only, supplied by the caller's whitelist
        "props": props or [],
        "metalness": float(metalness),
        "roughness": float(roughness),
        "bg": "#0d1117",
    }
    return payload, outline


def render_member(sec, length_mm, height=620, supports=None, load=None,
                  elements_t1=None, elements_t2=None, results=None,
                  props=None, metalness=0.85, roughness=0.30, segments=8,
                  show_diagnostics=False):
    """Render the member. Returns the outline dict, or None on failure."""
    path = _template_path()
    if path is None:
        st.error("viewer_3d.html was not found. Put it in the same folder "
                 "as viewer_3d.py.")
        return None

    try:
        payload, outline = build_payload(
            sec, length_mm, supports=supports, load=load,
            elements_t1=elements_t1, elements_t2=elements_t2,
            results=results, props=props, metalness=metalness,
            roughness=roughness, segments=segments)
    except ValueError as exc:
        st.info("3D view not available for this section: " + str(exc))
        return None
    except Exception as exc:
        st.warning("Could not build the section outline: " + str(exc))
        return None

    fh = open(path, "r")
    html = fh.read()
    fh.close()
    html = html.replace("__GEOMETRY_JSON__", json.dumps(payload))

    st.components.v1.html(html, height=height, scrolling=False)

    if show_diagnostics:
        cols = st.columns(4)
        cols[0].metric("Outline points", str(len(payload["outer"])))
        cols[1].metric("Fillet r (mm)", "%.2f" % outline["r_mm"])
        cols[2].metric("Polygon area", "%.0f" % outline["area_polygon_mm2"])
        e = outline.get("area_error_pct")
        cols[3].metric("vs table A", "-" if e is None else "%.2f %%" % e)
        st.caption("The polygon area is generated from the outline and "
                   "compared with the published area. A small percentage "
                   "means the fillet geometry is right.")

    return outline
