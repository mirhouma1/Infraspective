"""
viewer_3d_blast.py

Streamlit wrapper for the animated 3D SDOF blast response viewer.

Same shape as viewer_3d_lug.py and viewer_3d_eye.py: this module owns
the payload, the template owns the rendering. The difference is that
this one carries a time history rather than a single state, because the
whole point of the chapter is that the answer is a motion, not a number.

The integration is NOT redone in the browser. blast_sdof.py solves the
equation of motion once, in Python, and the frames handed to the
template are samples of that one solution. So the beam on screen, the
mass on the spring beside it, the reaction arrows, the plots and every
figure printed on the page are all the same array of numbers. If the
animation is wrong, the answer is wrong, and that is deliberate: an
animation that can drift away from the calculation teaches the wrong
thing twice.

Coordinates, metres, origin at the left support at the level of the
undeflected neutral axis
------------------------------------------------------------------
x   along the span, 0 to L
y   up. Blast arrives from +y and pushes the member down, so the
    plotted response y(t) is positive downward and the model bends the
    way the load points
z   across the flange width

Payload contract for the template
---------------------------------
geom      span, section dimensions, hinge positions, deflection scale
shapes    {"elastic": [phi at each station], "plastic": [...]}
          the shape functions the transformation factors were derived
          from, sampled once here so the template never has to know a
          formula
frames    [{t, y, F, R, V, stage, mu}, ...] sampled from the solution
keys      the scalars worth printing on the model: tn, td, yE, Ru, Fo,
          ymax, mu, Vmax
sdof      Me, KE, KLM, and the spring travel for the box beside the beam
props     [{group, symbol, value, unit}]

ASCII only. Straight quotes only. No markdown inside code.
"""

import json
import math
import os

import streamlit as st

import blast_sdof


_HTML_NAME = "viewer_3d_blast.html"

N_STATIONS = 61          # stations along the span for the deflected shape
N_FRAMES = 320           # animation frames, resampled from the solution


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
# frame sampling
# ---------------------------------------------------------------------
def _stage_of(R, res, tol=1.0e-6):
    """Which range of the resistance function the member is in.

    0 elastic, 1 elastic-plastic, 2 fully plastic. Driven off the
    resistance rather than the deflection so that unloading is reported
    honestly: a member that has yielded and sprung back is elastic
    again, and the hinges on the model close accordingly.
    """
    a = abs(R)
    ends = [s["R_end"] for s in res["stages"]]
    Ru = res["Ru_N"]
    if Ru <= 0:
        return 0
    if a >= Ru * (1.0 - tol):
        return len(ends)              # fully plastic
    for i, Re in enumerate(ends):
        if a < Re * (1.0 - tol):
            return i
    return len(ends) - 1


def sample_frames(result, n=N_FRAMES):
    """Resample the solution onto a fixed number of frames.

    The instant of peak response is forced into the sample. Dropping the
    one frame the whole analysis is about, purely because it fell
    between two sampling points, would be a poor trade for a round
    number of frames.
    """
    hist = result["history"]
    res = result["resistance"]
    t, y, F, R, V = hist["t"], hist["y"], hist["F"], hist["R"], hist["V"]
    N = len(t)
    if N == 0:
        return []
    yE = res["yE_m"] or 1.0

    idx = sorted(set(
        [int(round(i * (N - 1) / float(max(1, n - 1)))) for i in range(n)]
        + [y.index(max(y)), y.index(min(y)), 0, N - 1]))

    out = []
    for i in idx:
        out.append({
            "t": round(t[i], 8),
            "y": round(y[i], 8),
            "F": round(F[i], 4),
            "R": round(R[i], 4),
            "V": round(V[i], 4),
            "stage": _stage_of(R[i], res),
            "mu": round(y[i] / yE, 5),
        })
    return out


# ---------------------------------------------------------------------
# deflected shapes
# ---------------------------------------------------------------------
def sample_shapes(result, n=N_STATIONS):
    case = result["case"]
    el = case["shape_elastic"]
    pl = ("plastic_third" if result["loadcase"] == "third" else "plastic")
    xs = [i / float(n - 1) for i in range(n)]
    return {
        "x": [round(v, 6) for v in xs],
        "elastic": [round(blast_sdof.shape(el, v), 6) for v in xs],
        "plastic": [round(blast_sdof.shape(pl, v), 6) for v in xs],
    }


# ---------------------------------------------------------------------
# payload
# ---------------------------------------------------------------------
def build_payload(result, section=None, props=None, defl_scale=None,
                  metalness=0.85, roughness=0.30):
    res = result["resistance"]
    resp = result["response"]
    load = result["load"]
    dyn = result["dynamics"]
    L = load["L_m"]

    sec = section or {}
    d = float(sec.get("d_mm", 300.0)) / 1000.0
    bf = float(sec.get("bf_mm", 150.0)) / 1000.0
    tf = float(sec.get("tf_mm", 10.0)) / 1000.0
    tw = float(sec.get("tw_mm", 7.0)) / 1000.0

    # Deflection has to be exaggerated or nothing is visible: a 40 mm
    # peak on a 6 m span is under one percent of the span. The default
    # puts the peak at about a twelfth of the span, which reads as a
    # bent beam without looking like a skipping rope.
    ypk = max(abs(resp["ymax_m"]), abs(resp["ymin_m"]), 1.0e-9)
    auto = (L / 12.0) / ypk
    scale = float(defl_scale) if defl_scale else auto

    frames = sample_frames(result)
    shapes = sample_shapes(result)

    stage_names = [s["name"] for s in res["stages"]] + ["plastic"]

    hinge_x = result["case"]["hinges"](L)
    # Which stage each hinge belongs to. For a fixed end member under
    # uniform load the support hinges form first and the midspan hinge
    # only at the mechanism, which is exactly the thing the elastic
    # plastic range exists to describe.
    if result["support"] == "fixed" and len(res["stages"]) > 1:
        hinge_stage = [1 if abs(x) < 1e-9 or abs(x - L) < 1e-9 else 2
                       for x in hinge_x]
    else:
        hinge_stage = [len(res["stages"]) for _ in hinge_x]

    payload = {
        "geom": {
            "L": L, "d": d, "bf": bf, "tf": tf, "tw": tw,
            "support": result["support"], "loadcase": result["loadcase"],
            "hinge_x": [round(v, 6) for v in hinge_x],
            "hinge_stage": hinge_stage,
            "defl_scale": scale, "auto_scale": auto,
            "b_m": load["b_m"],
        },
        "shapes": shapes,
        "frames": frames,
        "stage_names": stage_names,
        "keys": {
            "tn_s": dyn["tn_s"], "td_s": load["td_s"],
            "dt_s": dyn["dt_s"], "method": dyn["method"],
            "tau": result["checks"]["tau"],
            "regime": result["checks"]["regime"],
            "Fo_N": load["Fo_N"], "Po_Pa": load["Po_Pa"],
            "Io_Ns": load["Io_Ns"],
            "Ru_N": res["Ru_N"], "yE_m": res["yE_m"], "KE_Npm": res["KE_Npm"],
            "ymax_m": resp["ymax_m"], "tmax_s": resp["tmax_s"],
            "ymin_m": resp["ymin_m"], "mu": resp["mu"],
            "theta_deg": resp["theta_deg"], "Vmax_N": resp["Vmax_N"],
            "yielded": resp["yielded"], "t_yield_s": resp["t_yield_s"],
            "t_end_s": dyn["t_end_s"],
        },
        "sdof": {
            "Me_kg": result["mass"]["Me_kg"], "M_kg": result["mass"]["M_kg"],
            "KLM": result["mass"]["KLM"], "KE_Npm": res["KE_Npm"],
        },
        "resistance": {
            "y_pts": [round(v, 8) for v in res["y_pts"]],
            "R_pts": [round(v, 4) for v in res["R_pts"]],
            "Ru_N": res["Ru_N"], "yE_m": res["yE_m"],
        },
        "label": result["case"]["label"],
        "table": result["case"]["table"],
        "props": props or [],
        "metalness": float(metalness),
        "roughness": float(roughness),
        "bg": "#0d1117",
    }
    return payload


def render_blast(result, height=760, section=None, props=None,
                 defl_scale=None, show_diagnostics=False):
    """Render the animated SDOF response. Returns the payload, or None."""
    path = _template_path()
    if path is None:
        st.error("viewer_3d_blast.html was not found. Put it in the same "
                 "folder as viewer_3d_blast.py.")
        return None

    try:
        payload = build_payload(result, section=section, props=props,
                                defl_scale=defl_scale)
    except Exception as exc:
        st.warning("Could not build the blast model: " + str(exc))
        return None

    fh = open(path, "r")
    html = fh.read()
    fh.close()
    html = html.replace("__GEOMETRY_JSON__", json.dumps(payload))

    st.components.v1.html(html, height=height, scrolling=False)

    if show_diagnostics:
        c = st.columns(4)
        c[0].metric("Frames", str(len(payload["frames"])))
        c[1].metric("Solver steps", str(len(result["history"]["t"])))
        c[2].metric("Deflection scale", "x%.0f" % payload["geom"]["defl_scale"])
        c[3].metric("dt / tn", "1 / %.0f"
                    % ((payload["keys"]["tn_s"] / payload["keys"]["dt_s"])
                       if payload["keys"]["dt_s"] else 0.0))
        st.caption("Frames are samples of the one solution computed in "
                   "Python. The peak is forced into the sample so the "
                   "animation cannot miss the instant the whole "
                   "analysis is about.")

    return payload
