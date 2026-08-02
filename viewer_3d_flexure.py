"""
viewer_3d_flexure.py

Streamlit wrapper for the flexure member viewer.

The geometry payload is built by viewer_3d.build_payload, exactly as the
Compression page builds it, so there is one outline builder and one place
where section dimensions turn into a mesh. Only the template differs:
this module renders viewer_3d_flexure.html, which lays the member down as
a beam, draws transverse load arrows and a moment diagram, and offers
flexure behaviours instead of column behaviours.

viewer_3d.py and viewer_3d.html are not modified, so the Compression page
is unaffected by anything here.

    import viewer_3d_flexure
    viewer_3d_flexure.render_beam(sec, length_mm=6000,
                                  supports={...}, load={...},
                                  elements_t2=[...], results={...},
                                  props=[...])

Payload contract for the flexure template
-----------------------------------------
supports  {"y": {"K":, "L": span_mm, "bottom": "pinned", "top": "roller"},
           "x": {"K":, "L": Lb_mm}}
          The y entry draws the end symbols. The x entry sets Lb, which
          drives the lateral brace marks and the LTB half-wave length.

load      {"type": "udl" | "point" | "none",
           "w_kN_m": float or None, "P_kN": float or None}
          Sets the arrow layout, the moment diagram shape and the moment
          envelope used by the colour maps.

results   {"util": Mf/Mr or None, "Mr_kNm":, "Mf_kNm":,
           "section_class": 1..4, "governs": str}

elements_t2  [{"zone": "flange"|"web", "label": str, "cls": 1..4}, ...]
"""

import json
import os

import streamlit as st

import viewer_3d


_HTML_NAME = "viewer_3d_flexure.html"


def _template_path():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, _HTML_NAME)
    if os.path.exists(p):
        return p
    up = os.path.join(os.path.dirname(here), _HTML_NAME)
    if os.path.exists(up):
        return up
    return None


def render_beam(sec, length_mm, height=640, supports=None, load=None,
                elements_t2=None, results=None, props=None,
                metalness=0.85, roughness=0.30, segments=8,
                show_diagnostics=False):
    """Render the beam. Returns the outline dict, or None on failure."""
    path = _template_path()
    if path is None:
        st.error("viewer_3d_flexure.html was not found. Put it in the same "
                 "folder as viewer_3d_flexure.py.")
        return None

    try:
        payload, outline = viewer_3d.build_payload(
            sec, length_mm, supports=supports, load=load,
            elements_t1=[], elements_t2=elements_t2,
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
