"""
viewer_3d_eye.py

Streamlit wrapper for the parametric 3D lifting eye viewer.

Same shape as viewer_3d_lug.py: this module owns the payload, the
template owns the rendering. Nothing is imported and no mesh file is
read; the member, the doublers, the bore, the pin, the welds and the
sling are all generated from the design inputs, so the model always
shows the numbers currently in the panel.

    import viewer_3d_eye
    viewer_3d_eye.render_eye(geom, checks=[...], results={...},
                             props=[...], load={...}, paths={...})

Why a lifting eye needs its own viewer rather than a reused lug one
------------------------------------------------------------------
A padeye is a plate standing proud of the structure, so the whole
assembly lives in one plane and the cheek plates sit on the outside of
that plane. A lifting eye is a hole bored THROUGH a member: the load
path runs into the web, out sideways through the doubler welds, into
the doublers, and back down into the member below. None of that is
visible unless the flanges and the doubler footprint are drawn, so the
model is a short length of the member rather than a single plate.

Coordinates, all millimetres, origin at the centre of the bore
--------------------------------------------------------------
x   horizontal, across the web, along the depth d of the member
y   up, along the axis of the member. y = e_top is the free edge above
    the hole, which is the surface the tear-out path runs out to
z   through the web thickness, along the flange width bf

So looking down -z you see the web face: the bore in the middle, the
doubler footprint around it, and the two flanges edge on at
x = +/- (d - tf) / 2. That is the same view as the DETAIL on a standard
lifting eye drawing, and the SECTION is the view down -x.

Payload contract for the template
---------------------------------
geom      the flat input dict plus the member shape, every key the
          template needs to size itself
web       {"outer": [[x, y], ...], "holes": [[[x, y], ...]]}
doubler   {"outer": [...], "holes": [...]}  one doubler, both are drawn
paths     failure planes, in the web plane, from the design engine so
          the drawing and the numbers can never disagree
checks    [{"key":, "label":, "component":, "uc": float or None,
           "verdict": "OK"|"NG"}]
          component is one of member, doubler, weld, pin and is what
          maps a check onto the geometry it colours
results   {"Tf_kN":, "governing_name":, "governing_uc":, "overall":}
load      {"sling_angle_deg":, "Tf_kN":, "P_leg_kN":, "P_web_kN":,
           "P_doubler_kN":}
props     [{"group":, "symbol":, "value":, "unit":}]

ASCII only. Straight quotes only. No markdown inside code.
"""

import json
import math
import os

import streamlit as st


_HTML_NAME = "viewer_3d_eye.html"


def _template_path():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, _HTML_NAME)
    if os.path.exists(p):
        return p
    up = os.path.join(os.path.dirname(here), _HTML_NAME)
    if os.path.exists(up):
        return up
    return None


# ---------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------
def _circle(cx, cy, r, segments=48, reverse=False):
    pts = []
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        pts.append([cx + r * math.cos(a), cy + r * math.sin(a)])
    if reverse:
        pts.reverse()
    return pts


def _rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def web_profile(width, y_bot, y_top, Dhole, segments=48):
    """The web of the member, seen on its face. The bore is a hole in
    the extrusion rather than a separate cut, so the solid is right in
    every view including the section."""
    outer = _rect(-width / 2.0, y_bot, width / 2.0, y_top)
    holes = []
    if Dhole > 0.0:
        holes.append(_circle(0.0, 0.0, Dhole / 2.0, segments, reverse=True))
    return {"outer": outer, "holes": holes}


def doubler_profile(W_d, L_d, e_dtop, Dhole, segments=48):
    """One doubler plate. Its top edge sits e_dtop above the hole
    centre, so where e_dtop is less than e_top the doubler stops short
    of the free edge and part of the tear-out path runs through the web
    alone. That is the split the engine calls k_doubler and k_web."""
    outer = _rect(-W_d / 2.0, e_dtop - L_d, W_d / 2.0, e_dtop)
    holes = []
    if Dhole > 0.0:
        holes.append(_circle(0.0, 0.0, Dhole / 2.0, segments, reverse=True))
    return {"outer": outer, "holes": holes}


def failure_paths(Dhole, e_top, e_dtop, W_web, k_full=None,
                  k_doubler=None, k_web=None, segments=40):
    """Geometry of the planes the clause checks are taken on.

    tear-out   from the free edge above the hole, tangent to the bore.
               The tangent is the shortest way out of the plate, so it
               is the one that governs, and its length is
               k = sqrt(e_top^2 - (Dhole/2)^2), Cl. 13.11 and its Note.
    net        the section through the hole centre carrying Anet,
               Cl. 13.2 (b)(ii).
    bearing    the loaded half of the bore, Cl. 13.10 / 13.12.1.2.
    split      the point on the tear-out path where the doubler stops
               and the remainder runs through the web alone.

    k_full, k_doubler and k_web are passed in from the design engine
    rather than recomputed, so the drawing can never disagree with the
    numbers on the page. Returns None if the geometry has degenerated.
    """
    r = Dhole / 2.0
    if r <= 0.0 or e_top <= r:
        return None

    if k_full is None:
        k_full = math.sqrt(e_top * e_top - r * r)

    alpha = math.acos(min(1.0, r / e_top))
    out = {}

    def tangent_leg(sign):
        a_t = math.pi / 2.0 + sign * alpha
        T = [r * math.cos(a_t), r * math.sin(a_t)]
        return [[0.0, e_top], T]

    out["tearout"] = tangent_leg(1.0)
    out["tearout_mirror"] = tangent_leg(-1.0)

    # Where the doubler top edge crosses each tear-out plane. Above this
    # point the plane runs through the web alone.
    out["split"] = []
    if e_dtop is not None and 0.0 < e_dtop < e_top:
        for leg in (out["tearout"], out["tearout_mirror"]):
            (x0, y0), (x1, y1) = leg[0], leg[1]
            if abs(y1 - y0) > 1.0e-9:
                t = (e_dtop - y0) / (y1 - y0)
                if 0.0 <= t <= 1.0:
                    out["split"].append([x0 + t * (x1 - x0), e_dtop])

    half = max(W_web / 2.0, r * 1.5)
    out["net_left"] = [[-half, 0.0], [-r, 0.0]]
    out["net_right"] = [[r, 0.0], [half, 0.0]]

    arc = []
    for i in range(segments + 1):
        a = math.pi * float(i) / float(segments)
        arc.append([r * math.cos(a), r * math.sin(a)])
    out["bearing"] = arc

    out["k"] = float(k_full)
    out["k_doubler"] = float(k_doubler) if k_doubler is not None else None
    out["k_web"] = float(k_web) if k_web is not None else None
    out["label_tearout"] = [r * 1.45, e_top * 0.55]
    out["label_net"] = [-half * 0.82, -r * 0.60]
    out["label_bearing"] = [0.0, r * 1.55]
    return out


def build_payload(geom, checks=None, results=None, props=None, load=None,
                  paths=None, metalness=0.85, roughness=0.30, segments=48):
    def gv(k, default=0.0):
        v = geom.get(k, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    Dhole = gv("Dhole")
    e_top = gv("e_top")
    e_dtop = gv("e_dtop")
    W_web = gv("W_web")
    W_d = gv("W_d")
    L_d = gv("L_d")
    tw = gv("tw")
    td = gv("td")

    # Member shape. When a section has been picked the real d, bf and tf
    # are used and the web is drawn to its true clear depth. Without a
    # section the web falls back to the clear width the user typed and
    # the flanges are left off rather than invented.
    d = gv("d_sec")
    bf = gv("bf_sec")
    tf = gv("tf_sec")
    has_section = d > 0.0 and bf > 0.0 and tf > 0.0

    web_w = (d - 2.0 * tf) if has_section else W_web
    if web_w <= 0.0:
        web_w = max(W_web, W_d, Dhole * 3.0)

    # How much member to draw. Enough below the doublers to show the
    # section reverting to the bare member, which is the Cl. 13.2 (a)
    # check, and a little above the free edge for the sling.
    below = max(L_d, e_top) * 1.60
    y_bot = min(e_dtop - L_d, 0.0) - below
    y_top = e_top

    prof = web_profile(web_w, y_bot, y_top, Dhole, segments)
    dbl = doubler_profile(W_d, L_d, e_dtop, Dhole, segments)

    def rnd(loop):
        return [[round(p[0], 3), round(p[1], 3)] for p in loop]

    src = paths or {}
    P = failure_paths(Dhole, e_top, e_dtop, W_web,
                      k_full=src.get("k_mm"),
                      k_doubler=src.get("k_doubler_mm"),
                      k_web=src.get("k_web_mm"))
    if P is not None:
        for key in ("tearout", "tearout_mirror", "net_left", "net_right",
                    "bearing"):
            P[key] = rnd(P[key])
        P["split"] = rnd(P["split"])

    payload = {
        "paths": P,
        "geom": {
            "Dpin": gv("Dpin"), "Dhole": Dhole,
            "e_top": e_top, "e_dtop": e_dtop,
            "tw": tw, "td": td, "W_web": W_web, "W_d": W_d, "L_d": L_d,
            "w_weld": gv("w_weld"),
            "d_sec": d, "bf_sec": bf, "tf_sec": tf, "k_sec": gv("k_sec"),
            "web_w": web_w, "y_bot": y_bot, "y_top": y_top,
            "t_eff": tw + 2.0 * td,
            "has_section": 1.0 if has_section else 0.0,
            "weld_top": 1.0 if geom.get("weld_top") else 0.0,
        },
        "web": {"outer": rnd(prof["outer"]),
                "holes": [rnd(h) for h in prof["holes"]]},
        "doubler": {"outer": rnd(dbl["outer"]),
                    "holes": [rnd(h) for h in dbl["holes"]]},
        "checks": checks or [],
        "results": results or {},
        "load": load or {},
        "props": props or [],
        "label": str(geom.get("label", "Lifting eye")),
        "section": str(geom.get("section_name", "")),
        "metalness": float(metalness),
        "roughness": float(roughness),
        "bg": "#0d1117",
    }
    return payload


def render_eye(geom, height=640, checks=None, results=None, props=None,
               load=None, paths=None, metalness=0.85, roughness=0.30,
               segments=48, show_diagnostics=False):
    """Render the bored eye. Returns the payload, or None on failure."""
    path = _template_path()
    if path is None:
        st.error("viewer_3d_eye.html was not found. Put it in the same "
                 "folder as viewer_3d_eye.py.")
        return None

    try:
        payload = build_payload(geom, checks=checks, results=results,
                                props=props, load=load, paths=paths,
                                metalness=metalness, roughness=roughness,
                                segments=segments)
    except Exception as exc:
        st.warning("Could not build the eye geometry: " + str(exc))
        return None

    fh = open(path, "r")
    html = fh.read()
    fh.close()
    html = html.replace("__GEOMETRY_JSON__", json.dumps(payload))

    st.components.v1.html(html, height=height, scrolling=False)

    if show_diagnostics:
        g = payload["geom"]
        cols = st.columns(4)
        cols[0].metric("Web drawn", "%.0f mm" % g["web_w"])
        cols[1].metric("Effective t", "%.1f mm" % g["t_eff"])
        cols[2].metric("Edge above hole",
                       "%.1f mm" % (g["e_top"] - g["Dhole"] / 2.0))
        cols[3].metric("Doubler cover",
                       "%.0f %%" % (100.0 * min(1.0, (g["W_d"] / g["W_web"]))
                                    if g["W_web"] else 0.0))
        st.caption("Edge above hole is e_top minus the bore radius, the "
                   "material the tear-out path has to cross. Doubler "
                   "cover is how much of the clear web the doubler "
                   "actually reaches.")

    return payload
