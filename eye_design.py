"""
eye_design.py

Lifting eye design engine, CSA S16.

A lifting eye is not a padeye. There is no projecting plate, no cheek
plates and no bolted cap, so there is nothing to pry. The hole is bored
straight through the web or cap plate of the member, and doubler plates
are welded on both faces to make up the thickness lost at the hole.

That changes what has to be checked:

  * the load is shared between the web and the doublers in proportion
    to thickness, so the doubler weld has to be able to deliver the
    doublers' share into them
  * the section below the doublers reverts to the bare member, and has
    to carry the whole load on its own gross area
  * the tear-out path runs partly through web plus doublers and partly
    through the web alone, wherever the doubler stops short of the free
    edge

Interface
---------
    eye_design.SOURCE_CASE_EYE      default input dict
    eye_design.design_eye(inp)

Clause basis
------------
Cl. 13.2 (a)    tension on the gross section of the member below the
                doublers
Cl. 13.2 (b)    tension at the hole, for pin connections excluding
                eyebars, the least of phi Ag Fy, phiu Anet Fu and
                0.60 phiu Anes Fu
Cl. 13.10 (a)   bearing on an accurately fitted pin
Cl. 13.11       tear-out above the hole, and its closing Note
Cl. 13.12.1.1   pin shear
Cl. 13.12.1.2   bearing of a pin in a clearance hole
Cl. 13.13.2.2   fillet weld attaching the doublers

The tear-out plane is the line from the free edge drawn tangent to the
hole, which is the shortest path out of the plate, so k = sqrt(R^2 -
(D/2)^2) with R measured from the hole centre to the free edge.

ASCII only. Straight quotes only. No markdown inside code.
"""

import math

G_ACC = 9.807
UC_INF = 999.0


SOURCE_CASE_EYE = {
    # load
    "T_tons": 17.0, "LDf": 1.50, "If": 1.15, "Sf": 1.00,
    # pin and hole
    "Dpin": 42.0, "Dhole": 45.0, "shackle_in": 1.5,
    # member being bored
    "tw": 11.2, "W_web": 286.0, "Ag_member": 17100.0,
    "Fy_col": 350.0, "Fu_col": 450.0,
    # doubler plates, one each face
    "td": 13.0, "W_d": 286.0, "L_d": 140.0,
    "Fy_d": 300.0, "Fu_d": 450.0,
    # free edge above the hole
    "e_top": 90.0, "e_dtop": 70.0,
    # weld
    "w_weld": 6.0, "Xu": 490.0, "weld_top": False,
    # pin material
    "Fypin": 620.0, "Fupin": 725.0,
    # resistance factors
    "phi": 0.90, "phiu": 0.75, "phiw": 0.67, "phib": 0.80,
    "phibr": 0.80,
    # method
    "pin_fit": "clearance", "Ut": 1.00, "An_tension_mm2": 0.0,
    "use_Mw": True,
}


def _safe(x, default=0.0):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return v


def _uc(demand, resistance):
    try:
        d = float(demand)
        r = float(resistance)
    except (TypeError, ValueError):
        return UC_INF
    if r <= 0.0 or math.isnan(r) or math.isinf(r):
        return UC_INF
    v = d / r
    if math.isnan(v) or math.isinf(v):
        return UC_INF
    return v


def verdict(uc):
    return "OK" if (uc is not None and uc <= 1.0) else "NG"


def tangent_tearout_length(R, Dhole):
    r = Dhole / 2.0
    if R <= r:
        return 0.0
    return math.sqrt(R * R - r * r)


# ---------------------------------------------------------------------
# 1. Design forces
# ---------------------------------------------------------------------
def design_forces(inp):
    T = _safe(inp.get("T_tons"))
    LDf = _safe(inp.get("LDf"), 1.0)
    If = _safe(inp.get("If"), 1.0)
    Sf = _safe(inp.get("Sf"), 1.0)

    factor = max(LDf, If * Sf)
    Ts = T * factor
    Tf = Ts * 1.30 * G_ACC
    return {"total_factor": factor, "Ts_tons": Ts, "Tf_kN": Tf,
            "T_tons": T}


# ---------------------------------------------------------------------
# 2. Load sharing between the member and the doublers
# ---------------------------------------------------------------------
def load_share(inp, F):
    """The doublers only carry what their weld can deliver into them.
    Share is taken in proportion to thickness, which is the usual
    assumption for a symmetric pack in direct tension."""
    tw = _safe(inp.get("tw"))
    td = _safe(inp.get("td"))

    t_eff = tw + 2.0 * td
    frac_d = (2.0 * td / t_eff) if t_eff > 0 else 0.0
    return {"tw_mm": tw, "td_mm": td, "t_eff_mm": t_eff,
            "frac_doubler": frac_d, "frac_web": 1.0 - frac_d,
            "P_doubler_kN": F["Tf_kN"] * frac_d,
            "P_web_kN": F["Tf_kN"] * (1.0 - frac_d)}


# ---------------------------------------------------------------------
# 3. Tension at the hole, Cl. 13.2 (b)
# ---------------------------------------------------------------------
def hole_section(inp, F, SHR):
    Dhole = _safe(inp.get("Dhole"))
    W_web = _safe(inp.get("W_web"))
    W_d = _safe(inp.get("W_d"))
    tw = _safe(inp.get("tw"))
    td = _safe(inp.get("td"))
    e_top = _safe(inp.get("e_top"))
    e_dtop = _safe(inp.get("e_dtop"))
    Fy = min(_safe(inp.get("Fy_col"), 350.0), _safe(inp.get("Fy_d"), 300.0))
    Fu = min(_safe(inp.get("Fu_col"), 450.0), _safe(inp.get("Fu_d"), 450.0))
    phi = _safe(inp.get("phi"), 0.90)
    phiu = _safe(inp.get("phiu"), 0.75)

    t_eff = tw + 2.0 * td
    W_cover = min(W_d, W_web)
    W_outside = max(W_web - W_cover, 0.0)

    # Section through the hole centre. Inside the doubler footprint the
    # thickness is tw + 2 td, outside it reverts to tw.
    Ag = W_cover * t_eff + W_outside * tw
    Anet = max(W_cover - Dhole, 0.0) * t_eff + W_outside * tw

    # Net area on the tear-out planes, same split by thickness
    k_full = tangent_tearout_length(e_top, Dhole)
    k_d = tangent_tearout_length(e_dtop, Dhole)
    k_d = min(k_d, k_full)
    k_w = max(k_full - k_d, 0.0)
    Anes = 2.0 * (k_d * t_eff + k_w * tw)

    Tr_i = phi * Ag * Fy / 1000.0
    Tr_ii = phiu * Anet * Fu / 1000.0
    Tr_iii = 0.60 * phiu * Anes * Fu / 1000.0

    opts = [("13.2(b)(i) gross yield", Tr_i),
            ("13.2(b)(ii) net fracture", Tr_ii),
            ("13.2(b)(iii) 0.60 phiu Anes Fu", Tr_iii)]
    name, Tr = min(opts, key=lambda p: p[1])
    uc = _uc(F["Tf_kN"], Tr)

    return {"t_eff_mm": t_eff, "W_cover_mm": W_cover,
            "W_outside_mm": W_outside, "Ag_mm2": Ag, "Anet_mm2": Anet,
            "Anes_mm2": Anes, "k_mm": k_full, "k_doubler_mm": k_d,
            "k_web_mm": k_w, "Fy_used": Fy, "Fu_used": Fu,
            "Tr_i_kN": Tr_i, "Tr_ii_kN": Tr_ii, "Tr_iii_kN": Tr_iii,
            "Tr_kN": Tr, "governing": name, "clause": "Cl. 13.2 (b)",
            "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 4. Tear-out above the hole, Cl. 13.11 and its closing Note
# ---------------------------------------------------------------------
def tearout(inp, F, HS):
    Fy = HS["Fy_used"]
    Fu = HS["Fu_used"]
    phiu = _safe(inp.get("phiu"), 0.75)
    Ut = _safe(inp.get("Ut"), 1.0)
    An_t = _safe(inp.get("An_tension_mm2"), 0.0)

    Agv = HS["Anes_mm2"]
    if Fy > 460.0:
        stress = Fy
        note_c = True
    else:
        stress = (Fy + Fu) / 2.0
        note_c = False

    Tr = phiu * (Ut * An_t * Fu + 0.6 * Agv * stress) / 1000.0
    uc = _uc(F["Tf_kN"], Tr)
    return {"Agv_mm2": Agv, "shear_stress_MPa": stress, "note_c": note_c,
            "Ut": Ut, "An_tension_mm2": An_t, "Tr_kN": Tr,
            "clause": "Cl. 13.11, Note", "uc": uc,
            "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 5. Bearing on the hole
# ---------------------------------------------------------------------
def bearing(inp, F, SHR):
    Dpin = _safe(inp.get("Dpin"))
    Fy = min(_safe(inp.get("Fy_col"), 350.0), _safe(inp.get("Fy_d"), 300.0))
    Fu = min(_safe(inp.get("Fu_col"), 450.0), _safe(inp.get("Fu_d"), 450.0))
    phi = _safe(inp.get("phi"), 0.90)
    phibr = _safe(inp.get("phibr"), 0.80)
    fit = str(inp.get("pin_fit", "clearance"))

    t = SHR["t_eff_mm"]
    Apb = Dpin * t
    Br_fitted = 1.50 * phi * Fy * Apb / 1000.0
    Br_clear = 3.0 * phibr * t * Dpin * Fu / 1000.0

    if fit == "fitted":
        Br, used = Br_fitted, "Cl. 13.10 (a), fitted pin"
    else:
        Br, used = Br_clear, "Cl. 13.12.1.2, clearance hole"
    uc = _uc(F["Tf_kN"], Br)
    return {"t_mm": t, "Apb_mm2": Apb, "Br_fitted_kN": Br_fitted,
            "Br_clearance_kN": Br_clear, "Br_kN": Br, "fit": fit,
            "clause": used, "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 6. Pin shear
# ---------------------------------------------------------------------
def pin_shear(inp, F):
    Dpin = _safe(inp.get("Dpin"))
    Fupin = _safe(inp.get("Fupin"), 725.0)
    phib = _safe(inp.get("phib"), 0.80)
    Apin = math.pi * Dpin * Dpin / 4.0
    m = 2.0
    Vr = 0.60 * phib * m * Apin * Fupin / 1000.0
    uc = _uc(F["Tf_kN"], Vr)
    return {"Apin_mm2": Apin, "m": m, "Vr_kN": Vr,
            "clause": "Cl. 13.12.1.1 (b), double shear",
            "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 7. Member below the doublers, Cl. 13.2 (a)
# ---------------------------------------------------------------------
def member_below(inp, F):
    """Below the doubler the section reverts to the bare member and has
    to carry the whole load on its own gross area."""
    Ag = _safe(inp.get("Ag_member"))
    Fy = _safe(inp.get("Fy_col"), 350.0)
    phi = _safe(inp.get("phi"), 0.90)
    Tr = phi * Ag * Fy / 1000.0
    uc = _uc(F["Tf_kN"], Tr)
    return {"Ag_mm2": Ag, "Fy_MPa": Fy, "Tr_kN": Tr,
            "clause": "Cl. 13.2 (a)(i)", "uc": uc,
            "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 8. Doubler to member weld, Cl. 13.13.2.2
# ---------------------------------------------------------------------
def doubler_weld(inp, F, SHR):
    """The weld has to deliver the doublers' share of the load into
    them. The run along the top is normally discounted, because the
    tear-out path crosses it and it cannot be relied on to transfer
    load in the same direction."""
    w = _safe(inp.get("w_weld"))
    Xu = _safe(inp.get("Xu"), 490.0)
    phiw = _safe(inp.get("phiw"), 0.67)
    W_d = _safe(inp.get("W_d"))
    L_d = _safe(inp.get("L_d"))
    td = _safe(inp.get("td"))
    tw = _safe(inp.get("tw"))
    Fu = min(_safe(inp.get("Fu_col"), 450.0), _safe(inp.get("Fu_d"), 450.0))
    weld_top = bool(inp.get("weld_top", False))
    use_Mw = bool(inp.get("use_Mw", True))

    # Two vertical runs plus the bottom, and the top only if included
    Lw = 2.0 * L_d + W_d + (W_d if weld_top else 0.0)

    # The load runs along the vertical legs and across the bottom, so
    # the joint has more than one orientation and Mw applies.
    theta = 0.0
    dir_factor = 1.00 + 0.50 * (math.sin(math.radians(theta)) ** 1.5)
    Mw = ((0.85 + theta / 600.0) / (0.85 + 90.0 / 600.0)) if use_Mw else 1.0

    Aw = 0.707 * w * Lw
    Vr_weld = 0.67 * phiw * Aw * Xu * dir_factor * Mw / 1000.0
    # Cl. 13.13.2.1 (a), base metal on the fusion face
    Am = w * Lw
    Vr_base = 0.67 * phiw * Am * Fu / 1000.0
    Vr = min(Vr_weld, Vr_base)

    Pd = SHR["P_doubler_kN"] * 2.0 / 2.0   # both doublers, both faces
    uc = _uc(Pd, Vr)

    # required leg for the demand
    denom = 0.67 * phiw * 0.707 * Lw * Xu * dir_factor * Mw / 1000.0
    w_req = (Pd / denom) if denom > 0 else 0.0

    # Cl. 13.13.2.2 practical limits on leg size
    t_thick = max(td, tw)
    if t_thick <= 13.0:
        w_min = 5.0
    elif t_thick <= 19.0:
        w_min = 6.0
    elif t_thick <= 38.0:
        w_min = 8.0
    else:
        w_min = 10.0
    w_max = (td - 2.0) if td >= 6.0 else td

    return {"Lw_mm": Lw, "Aw_mm2": Aw, "Am_mm2": Am, "theta_deg": theta,
            "Mw": Mw, "dir_factor": dir_factor,
            "Vr_weld_kN": Vr_weld, "Vr_base_kN": Vr_base, "Vr_kN": Vr,
            "P_demand_kN": Pd, "w_req_mm": w_req, "w_mm": w,
            "w_min_mm": w_min, "w_max_mm": w_max,
            "size_ok": (w >= w_min - 1e-9) and (w <= w_max + 1e-9),
            "weld_top": weld_top, "clause": "Cl. 13.13.2.2",
            "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 9. Flexure of the material above the hole
# ---------------------------------------------------------------------
def head_flexure(inp, F, SHR):
    """Industry practice check, not a clause of S16, reported separately
    so it is never mistaken for a Code requirement."""
    Dhole = _safe(inp.get("Dhole"))
    e_top = _safe(inp.get("e_top"))
    Fy = min(_safe(inp.get("Fy_col"), 350.0), _safe(inp.get("Fy_d"), 300.0))

    t = SHR["t_eff_mm"]
    e = max(e_top - Dhole / 2.0, 0.0)
    if Dhole <= 0.0:
        return {"t_mm": t, "e_mm": e, "Pr_kN": 0.0, "uc": UC_INF,
                "verdict": "NG",
                "clause": "Head flexure, industry practice"}
    Pr = 10.0 * t * e * e * (0.9 * Fy) / (4.0 * Dhole) / 1000.0
    uc = _uc(F["Tf_kN"], Pr)
    return {"t_mm": t, "e_mm": e, "Pr_kN": Pr,
            "clause": "Head flexure, industry practice",
            "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 10. Proportioning
# ---------------------------------------------------------------------
def geometry_checks(inp):
    Dpin = _safe(inp.get("Dpin"))
    Dhole = _safe(inp.get("Dhole"))
    e_top = _safe(inp.get("e_top"))
    e_dtop = _safe(inp.get("e_dtop"))
    W_d = _safe(inp.get("W_d"))
    td = _safe(inp.get("td"))
    tw = _safe(inp.get("tw"))

    items = []

    d_min = Dpin + 2.0
    items.append({"item": "Hole diameter",
                  "required": ">= Dpin + 2 mm = %.1f mm" % d_min,
                  "value": "%.1f mm" % Dhole,
                  "ok": Dhole >= d_min - 1e-6})

    clr = Dhole - Dpin
    items.append({"item": "Pin clearance",
                  "required": "<= 6 mm, otherwise not a fitted pin",
                  "value": "%.1f mm" % clr, "ok": clr <= 6.0})

    e_min = 0.75 * Dhole
    e_act = e_top - Dhole / 2.0
    items.append({"item": "Edge distance above the hole",
                  "required": ">= 0.75 Dhole = %.1f mm" % e_min,
                  "value": "%.1f mm" % e_act,
                  "ok": e_act >= e_min - 1e-6})

    items.append({"item": "Doubler covers the hole",
                  "required": "doubler top above the hole",
                  "value": "%.1f vs %.1f mm" % (e_dtop, Dhole / 2.0),
                  "ok": e_dtop > Dhole / 2.0})

    items.append({"item": "Doubler within the free edge",
                  "required": "e_dtop <= e_top",
                  "value": "%.1f vs %.1f mm" % (e_dtop, e_top),
                  "ok": e_dtop <= e_top + 1e-6})

    items.append({"item": "Doubler width covers the hole",
                  "required": "W_d > Dhole",
                  "value": "%.1f vs %.1f mm" % (W_d, Dhole),
                  "ok": W_d > Dhole})

    items.append({"item": "Doubler not thinner than the web",
                  "required": "advisory, td >= tw/2",
                  "value": "td %.1f, tw %.1f mm" % (td, tw),
                  "ok": td >= tw / 2.0 - 1e-6})

    return {"items": items, "all_ok": all(i["ok"] for i in items)}


# ---------------------------------------------------------------------
# Master routine
# ---------------------------------------------------------------------
def design_eye(inp):
    F = design_forces(inp)
    SHR = load_share(inp, F)
    HS = hole_section(inp, F, SHR)
    TO = tearout(inp, F, HS)
    BR = bearing(inp, F, SHR)
    PS = pin_shear(inp, F)
    MB = member_below(inp, F)
    DW = doubler_weld(inp, F, SHR)
    HF = head_flexure(inp, F, SHR)
    GC = geometry_checks(inp)

    named = [
        ("Tension at the hole, Cl. 13.2(b)", HS["uc"], HS["verdict"]),
        ("Tear-out above the hole, Cl. 13.11", TO["uc"], TO["verdict"]),
        ("Bearing, %s" % BR["clause"], BR["uc"], BR["verdict"]),
        ("Pin shear, Cl. 13.12.1.1", PS["uc"], PS["verdict"]),
        ("Member below doublers, Cl. 13.2(a)", MB["uc"], MB["verdict"]),
        ("Doubler weld, Cl. 13.13.2.2", DW["uc"], DW["verdict"]),
        ("Flexure above the hole, practice check", HF["uc"],
         HF["verdict"]),
    ]

    real = [(n, u, v) for n, u, v in named if u is not None]
    if real:
        gname, guc, _ = max(real, key=lambda p: p[1])
    else:
        gname, guc = "none", 0.0
    if guc >= UC_INF:
        gname = gname + " (degenerate geometry)"

    overall = "OK" if all(v == "OK" for _, _, v in named) else "NG"

    return {"forces": F, "share": SHR, "hole": HS, "tearout": TO,
            "bearing": BR, "pin_shear": PS, "member": MB,
            "weld": DW, "flexure": HF, "geom_check": GC,
            "checks": named, "governing_name": gname,
            "governing_uc": guc, "overall": overall}
