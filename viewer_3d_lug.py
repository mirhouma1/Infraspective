"""
viewer_3d_lug.py

Streamlit wrapper for the parametric 3D lifting lug viewer.

Same shape as viewer_3d_flexure.py: this module owns the payload, the
template owns the rendering. The difference is that a lug is an assembly
rather than one extruded section, so the outlines are built here instead
of in section_geometry.py. Nothing is imported and no mesh file is read;
every plate, hole, bolt and pin is generated from the design inputs, so
the model always shows the numbers currently in the panel.

    import viewer_3d_lug
    viewer_3d_lug.render_lug(geom, checks=[...], results={...},
                             props=[...], load={...})

Coordinates, all millimetres
----------------------------
x   along the lug length L2 and the cap plate length L1
y   up, zero at the top face of the cap plate
z   across the lug thickness tp2, the cap plate width W1 direction

The pin hole centre sits at (0, H2, 0). The lug head is a circle of
radius H1 about that centre, and the sides are the straight tangents
from the two base corners onto that circle, which is the usual padeye
silhouette.

Payload contract for the template
---------------------------------
geom     the flat input dict, every key from the design panel
profile  {"outer": [[x, y], ...], "holes": [[[x, y], ...]]}  lug plate
cap      {"outer": [...], "holes": [...]}  cap plate, in its own plane
cheek    {"outer": [...], "holes": [...]}  one cheek plate
checks   [{"key":, "label":, "component":, "uc": float or None,
           "verdict": "OK"|"NG"}]
           component is one of lug, weld, cap, bolt, pin, cheek and is
           what maps a check onto the geometry it colours
results  {"Tf_kN":, "governing_name":, "governing_uc":, "overall":}
load     {"sling_angle_deg":, "Tf_kN":}
props    [{"group":, "symbol":, "value":, "unit":}]
"""

import json
import math
import os

import streamlit as st


_HTML_NAME = "viewer_3d_lug.html"


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


def _arc(cx, cy, r, a0, a1, segments=40):
    pts = []
    for i in range(segments + 1):
        a = a0 + (a1 - a0) * float(i) / float(segments)
        pts.append([cx + r * math.cos(a), cy + r * math.sin(a)])
    return pts


def lug_profile(L2, H1, H2, Dhole, segments=48):
    """Padeye outline: base corners, straight tangents onto the head
    circle of radius H1 centred on the hole, then the arc over the top."""
    half = L2 / 2.0
    cx, cy, R = 0.0, float(H2), float(H1)

    P = (half, 0.0)
    dx, dy = cx - P[0], cy - P[1]
    d = math.hypot(dx, dy)

    if d <= R * 1.001:
        # The head circle swallows the base corners, so there is no
        # tangent. Fall back to straight sides up to the hole centre.
        outer = [[half, 0.0], [half, cy]]
        outer += _arc(cx, cy, R, 0.0, math.pi, segments)
        outer += [[-half, cy], [-half, 0.0]]
    else:
        Lt = math.sqrt(d * d - R * R)
        phi = math.atan2(dy, dx)
        alpha = math.asin(min(1.0, R / d))
        best = None
        for sign in (1.0, -1.0):
            ang = phi + sign * alpha
            T = (P[0] + Lt * math.cos(ang), P[1] + Lt * math.sin(ang))
            if best is None or T[0] > best[0]:
                best = T
        Tr = best
        aT = math.atan2(Tr[1] - cy, Tr[0] - cx)

        outer = [[half, 0.0], [Tr[0], Tr[1]]]
        outer += _arc(cx, cy, R, aT, math.pi - aT, segments)
        outer += [[-Tr[0], Tr[1]], [-half, 0.0]]

    holes = [_circle(cx, cy, Dhole / 2.0, segments, reverse=True)]
    return {"outer": outer, "holes": holes}


def cap_profile(L1, W1, Db, Nrow, s, g, segments=24):
    """Cap plate in its own plane: x along L1, y along W1. Bolt holes are
    2 per row, Nrow rows, spaced s along L1 and g across W1."""
    hx, hy = L1 / 2.0, W1 / 2.0
    outer = [[hx, -hy], [hx, hy], [-hx, hy], [-hx, -hy]]

    holes = []
    nrow = max(1, int(round(Nrow)))
    if nrow == 1:
        xs = [0.0]
    else:
        xs = [(-(nrow - 1) / 2.0 + i) * s for i in range(nrow)]
    for x in xs:
        for z in (-g / 2.0, g / 2.0):
            holes.append(_circle(x, z, (Db + 2.0) / 2.0, segments,
                                 reverse=True))
    return {"outer": outer, "holes": holes, "bolt_xy": [[x, z]
            for x in xs for z in (-g / 2.0, g / 2.0)]}


def cheek_profile(Dcheekp, Dhole, H2, segments=48):
    return {
        "outer": _circle(0.0, float(H2), Dcheekp / 2.0, segments),
        "holes": [_circle(0.0, float(H2), Dhole / 2.0, segments,
                          reverse=True)],
    }


def failure_paths(L2, H1, H2, Dhole, Dpin, tp2, tp3, segments=40):
    """Geometry of the planes the clause checks are taken on.

    tear-out   from the free edge of the head, tangent to the hole. The
               tangent is the shortest path out of the plate, so it is
               the one that governs, and its length is
               k = sqrt(H1^2 - (Dhole/2)^2).
    net        the section through the hole centre, the two ligaments
               of width H1 - Dhole/2 that carry Anet.
    bearing    the loaded half of the bore, where the pin pushes.

    All in the lug plane, x across the lug, y up from the cap plate.
    Returns None if the geometry has degenerated."""
    r = Dhole / 2.0
    if H1 <= r or r <= 0.0:
        return None

    cy = float(H2)
    k = math.sqrt(H1 * H1 - r * r)

    # Tangent from the top of the head down onto the hole. The tangent
    # point sits where the radius meets the tangent at a right angle.
    top = (0.0, cy + H1)
    d = H1
    alpha = math.acos(r / d)          # angle at the hole centre
    out = {}

    def tangent_leg(sign):
        a_t = math.pi / 2.0 + sign * alpha
        T = (r * math.cos(a_t), cy + r * math.sin(a_t))
        return [[top[0], top[1]], [T[0], T[1]]]

    out["tearout"] = tangent_leg(1.0)
    out["tearout_mirror"] = tangent_leg(-1.0)

    # Net tension section, the two ligaments either side of the hole
    out["net_left"] = [[-H1, cy], [-r, cy]]
    out["net_right"] = [[r, cy], [H1, cy]]

    # Bearing arc, the upper half of the bore
    arc = []
    for i in range(segments + 1):
        a = math.pi * float(i) / float(segments)
        arc.append([r * math.cos(a), cy + r * math.sin(a)])
    out["bearing"] = arc

    out["k"] = k
    out["t_eff"] = tp2 + 2.0 * tp3
    out["label_tearout"] = [H1 * 0.62, cy + H1 * 0.62]
    out["label_net"] = [-H1 * 0.80, cy - r * 0.55]
    out["label_bearing"] = [0.0, cy + r * 1.35]
    return out


def build_payload(geom, checks=None, results=None, props=None, load=None,
                  metalness=0.85, roughness=0.30, segments=48):
    def gv(k, default=0.0):
        v = geom.get(k, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    prof = lug_profile(gv("L2"), gv("H1"), gv("H2"), gv("Dhole"), segments)
    cap = cap_profile(gv("L1"), gv("W1"), gv("Db"), gv("Nrow", 2.0),
                      gv("s"), gv("g"), max(16, segments // 2))
    cheek = cheek_profile(gv("Dcheekp"), gv("Dhole"), gv("H2"), segments)

    def rnd(loop):
        return [[round(p[0], 3), round(p[1], 3)] for p in loop]

    paths = failure_paths(gv("L2"), gv("H1"), gv("H2"), gv("Dhole"),
                          gv("Dpin"), gv("tp2"), gv("tp3"))
    if paths is not None:
        for key in ("tearout", "tearout_mirror", "net_left", "net_right",
                    "bearing"):
            paths[key] = rnd(paths[key])

    payload = {
        "paths": paths,
        "geom": {k: gv(k) for k in
                 ("Dpin", "Dhole", "Dcheekp", "tp1", "L1", "W1", "tp2",
                  "H1", "H2", "L2", "tp3", "Db", "Nrow", "s", "g", "w1")},
        "profile": {"outer": rnd(prof["outer"]),
                    "holes": [rnd(h) for h in prof["holes"]]},
        "cap": {"outer": rnd(cap["outer"]),
                "holes": [rnd(h) for h in cap["holes"]],
                "bolt_xy": [[round(a, 3), round(b, 3)]
                            for a, b in cap["bolt_xy"]]},
        "cheek": {"outer": rnd(cheek["outer"]),
                  "holes": [rnd(h) for h in cheek["holes"]]},
        "checks": checks or [],
        "results": results or {},
        "load": load or {},
        "props": props or [],
        "label": str(geom.get("label", "Lifting lug")),
        "metalness": float(metalness),
        "roughness": float(roughness),
        "bg": "#0d1117",
    }
    return payload


def render_lug(geom, height=640, checks=None, results=None, props=None,
               load=None, metalness=0.85, roughness=0.30, segments=48,
               show_diagnostics=False):
    """Render the lug assembly. Returns the payload, or None on failure."""
    path = _template_path()
    if path is None:
        st.error("viewer_3d_lug.html was not found. Put it in the same "
                 "folder as viewer_3d_lug.py.")
        return None

    try:
        payload = build_payload(geom, checks=checks, results=results,
                                props=props, load=load, metalness=metalness,
                                roughness=roughness, segments=segments)
    except Exception as exc:
        st.warning("Could not build the lug geometry: " + str(exc))
        return None

    fh = open(path, "r")
    html = fh.read()
    fh.close()
    html = html.replace("__GEOMETRY_JSON__", json.dumps(payload))

    st.components.v1.html(html, height=height, scrolling=False)

    if show_diagnostics:
        cols = st.columns(4)
        cols[0].metric("Lug outline pts", str(len(payload["profile"]["outer"])))
        cols[1].metric("Bolt holes", str(len(payload["cap"]["holes"])))
        g = payload["geom"]
        cols[2].metric("Head clear", "%.1f mm"
                       % (g["H1"] - g["Dhole"] / 2.0))
        cols[3].metric("Cheek clear", "%.1f mm"
                       % (g["Dcheekp"] / 2.0 - g["Dhole"] / 2.0))
        st.caption("Head clear is H1 minus the hole radius, the material "
                   "left above the hole. Cheek clear is the ring of cheek "
                   "plate around the hole. Both feed the tear-out path.")

    return payload
