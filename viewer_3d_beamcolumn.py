"""
viewer_3d_beamcolumn.py

Streamlit wrapper for the beam-column member viewer.

Same shape as viewer_3d_flexure.py: the geometry payload is built by
viewer_3d.build_payload, so there is one outline builder shared with the
Compression page, and only the template differs. This one renders
viewer_3d_beamcolumn.html, which stands the member up as a column, draws
the axial load and both bending moments, and offers a behaviour per
failure mode in Chapter 5.

viewer_3d.py, viewer_3d.html and section_geometry.py are not modified, so
the Compression page is unaffected.

    import viewer_3d_beamcolumn
    viewer_3d_beamcolumn.render_beamcolumn(sec, length_mm=4300,
                                           supports={...}, load={...},
                                           elements_t1=[...],
                                           elements_t2=[...],
                                           results={...}, props=[...])

Payload contract for the template
---------------------------------
supports  {"x": {"K":, "L":, "bottom":, "top":},
           "y": {...}, "z": {...}}
          Drives the end symbols and the brace rings, exactly as the
          Compression page uses them.

load      {"Cf_kN":, "Tf_kN":, "Mfx_kNm":, "Mfy_kNm":, "e_mm":,
           "axial": "compression" | "tension"}
          Sets the axial arrows, the moment arcs and the eccentricity
          offset drawn at the top of the member.

results   {"section_class":, "clause":, "braced": bool,
           "U1x":, "U1y":, "Ce_x_kN":, "Ce_y_kN":, "beta":,
           "Mrx_kNm":, "Mry_kNm":, "Cr_kN":, "KLr":, "lam":, "Fcr":,
           "governing_name":, "governing_uc":, "overall":,
           "checks": [{"label":, "uc": float or None, "applies": bool}]}

elements_t1  [{"zone":, "label":, "ok": bool, "ratio":, "limit":}]
elements_t2  [{"zone":, "label":, "cls": 1..4}]
             zone is flange, web, leg or wall, and is what maps a check
             onto the plate element it colours.
"""

import json
import os

import streamlit as st

import viewer_3d


_HTML_NAME = "viewer_3d_beamcolumn.html"


def _template_path():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, _HTML_NAME)
    if os.path.exists(p):
        return p
    up = os.path.join(os.path.dirname(here), _HTML_NAME)
    if os.path.exists(up):
        return up
    return None


def render_beamcolumn(sec, length_mm, height=660, supports=None, load=None,
                      elements_t1=None, elements_t2=None, results=None,
                      props=None, metalness=0.85, roughness=0.30,
                      segments=8, show_diagnostics=False):
    """Render the beam-column. Returns the outline dict, or None."""
    path = _template_path()
    if path is None:
        st.error("viewer_3d_beamcolumn.html was not found. Put it in the "
                 "same folder as viewer_3d_beamcolumn.py.")
        return None

    try:
        payload, outline = viewer_3d.build_payload(
            sec, length_mm, supports=supports, load=load,
            elements_t1=elements_t1 or [], elements_t2=elements_t2 or [],
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
