"""
viewer_3d_endplate.py - 3D viewer for the bolted end plate shear
connection.

Follows the house pattern: this module owns the payload and the
injection, the geometry and shading live in viewer_3d_endplate.html.
The template is a fork, so viewer_3d.py is not touched.

ASCII only. Straight quotes only.
"""

import json
import os

import streamlit.components.v1 as components

_HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = "viewer_3d_endplate.html"

# Which limit state each viewer mode is annotated with.
MODE_KEY = {
    "assembly": "",
    "loadpath": "",
    "weld": "weld",
    "boltshear": "bolt_shear",
    "bearing": "bearing_end_plate",
    "shear": "plate_shear_rupture",
    "block": "block_shear",
    "prying": "plate_bending",
    "web": "beam_web",
}

# Order the utilisation bars follow the load path.
ORDER = ["beam_web", "weld", "plate_shear_yield", "plate_shear_rupture",
         "block_shear", "bearing_end_plate", "plate_bending",
         "bolt_shear", "bolt_tension", "interaction",
         "bearing_supporting_member"]


def _template_path():
    for p in (os.path.join(_HERE, TEMPLATE),
              os.path.join(_HERE, "..", TEMPLATE),
              os.path.join(os.getcwd(), TEMPLATE)):
        p = os.path.normpath(p)
        if os.path.isfile(p):
            return p
    return None


# Every arrangement in practice is one of four families sitting on one of
# two column faces. Rather than hard-coding a fixed set of details, the
# viewer takes a configuration and builds from it.
FAMILIES = {
    "End plate on the beam end": "end_plate",
    "Single plate to the beam web": "single_plate",
    "Double plate, beam web between": "double_plate",
    "Angle cleats each side of the web": "angles",
}

FRAMES = {
    "Column web": "web",
    "Column flange": "flange",
    "HSS face": "hss",
}

# Presets that reproduce the common arrangements, so the configuration
# does not have to be built from scratch every time.
PRESETS = {
    "Single plate to the column web, bolted": {
        "frame": "web", "family": "single_plate",
        "beam_attach": "bolted", "col_attach": "welded",
        "slotted": False, "coped": False, "stiffeners": True},
    "Single plate to the column flange, bolted": {
        "frame": "flange", "family": "single_plate",
        "beam_attach": "bolted", "col_attach": "welded",
        "slotted": False, "coped": False, "stiffeners": False},
    "End plate to the column flange": {
        "frame": "flange", "family": "end_plate",
        "beam_attach": "welded", "col_attach": "bolted",
        "slotted": False, "coped": False, "stiffeners": False},
    "End plate to the column web": {
        "frame": "web", "family": "end_plate",
        "beam_attach": "welded", "col_attach": "bolted",
        "slotted": False, "coped": False, "stiffeners": False},
    "Double plate, bolted, slotted, coped": {
        "frame": "web", "family": "double_plate",
        "beam_attach": "bolted", "col_attach": "welded",
        "slotted": True, "coped": True, "stiffeners": True},
    "Angle cleats to the column web": {
        "frame": "web", "family": "angles",
        "beam_attach": "bolted", "col_attach": "welded",
        "slotted": False, "coped": False, "stiffeners": False},
    "Single plate to an HSS column": {
        "frame": "hss", "family": "single_plate",
        "beam_attach": "bolted", "col_attach": "welded",
        "slotted": False, "coped": False, "stiffeners": False},
    "Double plate welded to the beam web": {
        "frame": "web", "family": "double_plate",
        "beam_attach": "welded", "col_attach": "welded",
        "slotted": False, "coped": False, "stiffeners": True},
}


def preset(name):
    return dict(PRESETS.get(name, list(PRESETS.values())[0]))


def build_payload(inp, checks, extras):
    """Assemble the geometry and results payload for the template."""
    results = {}
    for c in checks:
        results[c["key"]] = {
            "name": c["name"], "clause": c["clause"],
            "ratio": round(c["ratio"], 4), "ok": bool(c["ok"]),
            "demand": round(c["demand"], 2),
            "capacity": round(c["capacity"], 2),
        }
    pry = extras["pry"]
    return {
        "geom": {
            "plate_L": inp["plate_L"], "plate_W": inp["plate_W"],
            "t_plate": inp["t_plate"], "t_support": inp["t_support"],
            "beam_d": inp["beam_d"], "beam_bf": inp["beam_bf"],
            "tw_beam": inp["tw_beam"], "tf_beam": inp["tf_beam"],
            "db": extras["bolt"]["db"], "d_hole": extras["d_hole"],
            "gage": inp["gage"], "pitch": inp["pitch"],
            "ev": inp["ev"], "eh": inp["eh"],
            "n_rows": extras["n_rows"], "weld_D": inp["weld_D"],
            "col_d": inp.get("col_d", 300.0),
            "col_bf": inp.get("col_bf", 300.0),
            "col_tw": inp.get("col_tw", 10.0),
            "col_tf": inp.get("col_tf", 15.0),
            "ecc": inp.get("ecc", 0.0) or inp["plate_L"] * 0.35,
            "tab_len": inp.get("tab_len", 0.0)
                       or max(inp["plate_L"] * 0.6, 90.0),
            "setback": inp.get("setback", 10.0),
            "cope_len": inp.get("cope_len", 0.0)
                        or inp["plate_L"] * 0.55,
            "slot_len": inp.get("slot_len", 0.0)
                        or extras["bolt"]["db"] * 2.2,
            "stiff_t": inp.get("stiff_t", 10.0),
            "stiff_n": inp.get("stiff_n", 2),
            "stiff_sp": inp.get("stiff_sp", 0.0),
            "angle_leg_col": inp.get("angle_leg_col", 0.0),
            "angle_leg_beam": inp.get("angle_leg_beam", 0.0),
        },
        "config": inp.get("config", preset(list(PRESETS)[0])),
        "forces": {"Vf": inp["Vf"], "Nf": inp["Nf"],
                   "Hf": inp.get("Hf", 0.0),
                   "r_plate": round(extras["r_plate"], 2),
                   "r_weld": round(extras["r_weld"], 2)},
        "prying": {k: round(float(pry[k]), 4) for k in
                   ("b", "b_prime", "a", "a_prime", "delta", "K",
                    "alpha_b", "alpha_c", "Tf", "Tf_pry", "Tr", "q")},
        "results": results,
        "order": [k for k in ORDER if k in results],
        "modeKey": MODE_KEY,
    }


def render(payload, height=620):
    """Inject the payload into the template and render it."""
    path = _template_path()
    if path is None:
        components.html(
            "<div style='color:#f87171;font-family:sans-serif;"
            "padding:12px'>%s was not found. Place it beside "
            "viewer_3d_endplate.py.</div>" % TEMPLATE, height=90)
        return
    with open(path, "r", encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace("__PAYLOAD__", json.dumps(payload))
    html = html.replace("__H__", str(int(height)))
    components.html(html, height=int(height) + 10, scrolling=False)
