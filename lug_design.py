"""
lug_design.py

Lifting lug and lifting eye design engine, CSA S16.

This is a complete replacement for the previous module. The public
interface is unchanged, so pages/7_Lifting_Lug.py keeps working:

    lug_design.SOURCE_CASE          default input dict
    lug_design.design_lug(inp, prying_mode="cisc")

design_lug still returns forces / welds / lug / prying / pin, and adds
pin_conn, tearout, bearing, geom_check, shackle and flexure.

Clause basis
------------
Cl. 13.2 (a)   axial tension, gross and net, for the section at the base
Cl. 13.2 (b)   axial tension for PIN CONNECTIONS excluding eyebars, the
               least of phi Ag Fy, phiu Anet Fu and 0.60 phiu Anes Fu
Cl. 13.5       bending resistance of the lug plate at the base
Cl. 13.10 (a)  load bearing on the contact area of accurately cut or
               fitted parts, Br = 1.50 phi Fy A
Cl. 13.11      block shear, Tr = phiu [Ut An Fu + 0.6 Agv (Fy+Fu)/2],
               and its closing Note, which permits the second term
               alone as the plate tear-out resistance
Cl. 13.12.1.1  pin shear
Cl. 13.12.1.2  bolt bearing, used for a pin in a clearance hole
Cl. 13.13.1    phi_w = 0.67
Cl. 13.13.2.1  groove and base metal shear, Vr = 0.67 phi_w Am Fu
Cl. 13.13.2.2  fillet weld, Vr = 0.67 phi_w Aw Xu (1.00 + 0.50
               sin^1.5 theta) Mw, including the multi-orientation
               reduction factor Mw
Cl. 13.13.3.2  partial joint penetration groove weld in tension

Geometry of the tear-out path
-----------------------------
The tear-out plane is taken as the line drawn from the free edge of the
plate TANGENT to the pin hole. That is the shortest path from the edge
to the hole, so it is the one that governs, and its length follows
directly from the geometry of a tangent to a circle:

    k = sqrt(R^2 - (D/2)^2),   R = distance, hole centre to free edge

The gross shear area on the two tangent planes is Agv = 2 k t. This is
the same path referred to by the closing Note to Cl. 13.11, which
describes planes tangent to the hole and directed towards the edge of
the plate.

ASCII only. Straight quotes only. No markdown inside code.
"""

import math

MM2_PER_IN2 = 645.16
MM_PER_IN = 25.4
G_ACC = 9.807


# ---------------------------------------------------------------------
# Default case: the 35 tonne per lug standard detail
#   PL38 lug, R110 head, 60 dia hole, 2 - PL16 x 130 dia cheek plates,
#   300 x 280 PL32 cap plate, 4 - 27 dia holes for M25 A325M bolts at
#   100 gauge and 120 pitch, 12 mm fillet welds.
# ---------------------------------------------------------------------
SOURCE_CASE = {
    "T_tons": 35.0, "LDf": 1.50, "If": 1.15, "Sf": 1.00,
    "L2": 280.0, "H2": 100.0, "H1": 110.0, "tp2": 38.0,
    "Dpin": 54.0, "Dhole": 60.0, "Dcheekp": 130.0, "tp3": 16.0,
    "Fypin": 620.0, "Fupin": 725.0,
    "L1": 300.0, "W1": 280.0, "tp1": 32.0,
    "Db": 25.0, "Nrow": 2.0, "s": 120.0, "g": 100.0, "Fub": 830.0,
    "w1": 12.0, "Xu": 490.0, "Fyp": 345.0, "Fup": 450.0,
    "phi": 0.90, "phiu": 0.75, "phiw": 0.67, "phib": 0.80,
    "phibr": 0.80,
    "Ut": 1.00, "pin_fit": "clearance", "weld_type": "fillet",
    "shackle_in": 2.0,
}


# ---------------------------------------------------------------------
# Crosby G-2130 bolt type anchor shackles, published working load limit
#
# Working load limits are the manufacturer's published ratings. Pin
# diameters are nominal. Rigging hardware ratings are revised from time
# to time, so confirm the size actually specified against the current
# catalogue before issuing a design.
# ---------------------------------------------------------------------
SHACKLES_G2130 = [
    # nominal size (in), pin diameter (mm), WLL (tonnes)
    (1.000, 29.0, 8.5),
    (1.125, 32.0, 9.5),
    (1.250, 35.0, 12.0),
    (1.375, 38.0, 13.5),
    (1.500, 42.0, 17.0),
    (1.750, 51.0, 25.0),
    (2.000, 54.0, 35.0),
    (2.500, 70.0, 55.0),
    (3.000, 82.0, 85.0),
    (3.500, 95.0, 120.0),
    (4.000, 108.0, 150.0),
    (4.500, 127.0, 175.0),
]


def shackle_lookup(size_in):
    """Return the Crosby G-2130 entry nearest the requested size."""
    best = None
    for nom, dpin, wll in SHACKLES_G2130:
        d = abs(nom - float(size_in))
        if best is None or d < best[0]:
            best = (d, {"nominal_in": nom, "pin_mm": dpin, "WLL_t": wll})
    return best[1]


UC_INF = 999.0


def verdict(uc):
    return "OK" if (uc is not None and uc <= 1.0) else "NG"


def _uc(demand, resistance):
    """Utilisation ratio that never returns None.

    A zero or negative resistance means the geometry has degenerated,
    for example a hole larger than the head. That is a real failure,
    not a missing number, so it is reported as a very large ratio."""
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


def _safe(x, default=0.0):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return v


def tangent_tearout_length(R, Dhole):
    """Length of the plane drawn from a free edge tangent to the hole.

    R is the distance from the hole centre to the free edge. Returns
    zero if the hole runs out through the edge."""
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
    H2 = _safe(inp.get("H2"))
    tp1 = _safe(inp.get("tp1"))

    factor = max(LDf, If * Sf)
    Ts = T * factor
    Tf = Ts * 1.30 * G_ACC
    Vfx = 0.10 * Tf
    Vfy = 0.10 * Tf
    Rf = math.sqrt(Vfx ** 2 + Vfy ** 2)

    return {
        "total_factor": factor, "Ts_tons": Ts, "Tf_kN": Tf,
        "Vfx_kN": Vfx, "Vfy_kN": Vfy, "Rf_kN": Rf,
        "Mfx_lug_kNm": H2 * Vfy / 1000.0,
        "Mfy_lug_kNm": H2 * Vfx / 1000.0,
        "Mfx_beam_kNm": (H2 + tp1) * Vfy / 1000.0,
    }


# ---------------------------------------------------------------------
# 2. Lug to cap plate weld, Cl. 13.13
# ---------------------------------------------------------------------
def _weld_case(a_mm, L2, tp2, F, allow_MPa, clause, theta_deg, Mw):
    A = 2.0 * a_mm * L2
    if A <= 0.0:
        return {"a_mm": a_mm, "A_mm2": 0.0, "Sxx_mm3": 0.0,
                "Syy_mm3": 0.0, "sigma1_MPa": 0.0, "sigma2_MPa": 0.0,
                "sigma_n_MPa": 0.0, "tau_MPa": 0.0,
                "sigma_t_MPa": 0.0, "sigma_all_MPa": allow_MPa,
                "theta_deg": theta_deg, "Mw": Mw, "clause": clause,
                "uc": UC_INF, "verdict": "NG"}
    Sxx = a_mm * L2 * L2 / 3.0
    Syy = a_mm * L2 * (tp2 + a_mm)

    s1 = 0.0
    if Sxx > 0:
        s1 += F["Mfx_lug_kNm"] * 1.0e6 / Sxx
    if Syy > 0:
        s1 += F["Mfy_lug_kNm"] * 1.0e6 / Syy
    s2 = F["Tf_kN"] * 1000.0 / A
    sn = s1 + s2
    tau = F["Rf_kN"] * 1000.0 / A
    st = math.sqrt(sn * sn + tau * tau)
    uc = _uc(st, allow_MPa)

    return {"a_mm": a_mm, "A_mm2": A, "Sxx_mm3": Sxx, "Syy_mm3": Syy,
            "sigma1_MPa": s1, "sigma2_MPa": s2, "sigma_n_MPa": sn,
            "tau_MPa": tau, "sigma_t_MPa": st,
            "sigma_all_MPa": allow_MPa, "theta_deg": theta_deg,
            "Mw": Mw, "clause": clause, "uc": uc, "verdict": verdict(uc)}


def weld_checks(inp, F):
    w1 = _safe(inp.get("w1"))
    L2 = _safe(inp.get("L2"))
    tp2 = _safe(inp.get("tp2"))
    Xu = _safe(inp.get("Xu"), 490.0)
    Fup = _safe(inp.get("Fup"), 450.0)
    phiw = _safe(inp.get("phiw"), 0.67)
    use_Mw = bool(inp.get("use_Mw", True))

    # Orientation of the resultant on the weld, from a trial pass with
    # unit allowable, so theta reflects the actual force combination.
    a_trial = 0.707 * w1
    A = 2.0 * a_trial * L2
    if A > 0:
        Sxx = a_trial * L2 * L2 / 3.0
        Syy = a_trial * L2 * (tp2 + a_trial)
        sn = (F["Mfx_lug_kNm"] * 1.0e6 / Sxx if Sxx > 0 else 0.0)
        sn += (F["Mfy_lug_kNm"] * 1.0e6 / Syy if Syy > 0 else 0.0)
        sn += F["Tf_kN"] * 1000.0 / A
        tau = F["Rf_kN"] * 1000.0 / A
        theta = math.degrees(math.atan2(abs(sn), abs(tau)))
    else:
        theta = 90.0
    theta = max(0.0, min(90.0, theta))

    # Cl. 13.13.2.2, Mw for a joint with several weld orientations.
    # theta2 is the orientation in the joint nearest to 90 degrees; the
    # lug is welded on all four sides, so theta2 is taken as 90.
    if use_Mw:
        th2 = 90.0
        Mw = (0.85 + theta / 600.0) / (0.85 + th2 / 600.0)
    else:
        Mw = 1.0

    dir_factor = 1.00 + 0.50 * (math.sin(math.radians(theta)) ** 1.5)
    allow_wm = 0.67 * phiw * Xu * dir_factor * Mw
    allow_bm = 0.67 * phiw * Fup

    wm = _weld_case(0.707 * w1, L2, tp2, F, allow_wm,
                    "Cl. 13.13.2.2", theta, Mw)
    bm = _weld_case(w1, L2, tp2, F, allow_bm, "Cl. 13.13.2.1 (a)",
                    theta, 1.0)

    # Cl. 13.13.3.2, PJP groove weld in tension, reported for reference
    pjp = None
    if inp.get("weld_type") == "pjp":
        An = 2.0 * w1 * L2
        Tr_w = phiw * An * Fup / 1000.0
        Tr_b = _safe(inp.get("phi"), 0.9) * (L2 * tp2) \
            * _safe(inp.get("Fyp"), 345.0) / 1000.0
        Tr = min(Tr_w, Tr_b)
        uc = _uc(F["Tf_kN"], Tr)
        pjp = {"An_mm2": An, "Tr_weld_kN": Tr_w, "Tr_base_kN": Tr_b,
               "Tr_kN": Tr, "uc": uc, "verdict": verdict(uc),
               "clause": "Cl. 13.13.3.2"}

    return {"weld_metal": wm, "base_metal": bm, "pjp": pjp,
            "theta_deg": theta, "Mw": Mw, "dir_factor": dir_factor}


# ---------------------------------------------------------------------
# 3. Lug plate at the cap plate, Cl. 13.2 (a) and Cl. 13.5
# ---------------------------------------------------------------------
def lug_section(inp, F):
    L2 = _safe(inp.get("L2"))
    tp2 = _safe(inp.get("tp2"))
    Fyp = _safe(inp.get("Fyp"), 345.0)
    phi = _safe(inp.get("phi"), 0.90)

    A = L2 * tp2
    Sxx = tp2 * L2 * L2 / 6.0
    Syy = tp2 * tp2 * L2 / 6.0

    Tr = phi * A * Fyp / 1000.0
    Mrx = phi * Sxx * Fyp / 1.0e6
    Mry = phi * Syy * Fyp / 1.0e6

    uc = 0.0
    if Tr > 0:
        uc += F["Tf_kN"] / Tr
    if Mrx > 0:
        uc += F["Mfx_lug_kNm"] / Mrx
    if Mry > 0:
        uc += F["Mfy_lug_kNm"] / Mry

    return {"A_mm2": A, "Sxx_mm3": Sxx, "Syy_mm3": Syy,
            "Tr_kN": Tr, "Mrx_kNm": Mrx, "Mry_kNm": Mry,
            "clause": "Cl. 13.2 (a)(i) and Cl. 13.5 (b)",
            "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 4. Pin connected member at the hole, Cl. 13.2 (b)
# ---------------------------------------------------------------------
def pin_connected_section(inp, F):
    """Cl. 13.2 (b): for pin connections excluding eyebars, the least of
        (i)   phi Ag Fy
        (ii)  phiu Anet Fu
        (iii) 0.60 phiu Anes Fu
    A padeye is a pin connection, so this governs the head of the lug.
    The cheek plates are included only where they are developed into the
    lug by their own weld."""
    H1 = _safe(inp.get("H1"))
    Dhole = _safe(inp.get("Dhole"))
    tp2 = _safe(inp.get("tp2"))
    tp2 = _safe(inp.get("tp2"))
    tp3 = _safe(inp.get("tp3"))
    Fyp = _safe(inp.get("Fyp"), 345.0)
    Fup = _safe(inp.get("Fup"), 450.0)
    phi = _safe(inp.get("phi"), 0.90)
    phiu = _safe(inp.get("phiu"), 0.75)
    cheeks = bool(inp.get("cheeks_effective", True))

    t_eff = tp2 + (2.0 * tp3 if cheeks else 0.0)
    r = Dhole / 2.0
    e_side = max(H1 - r, 0.0)          # net width each side of the hole

    Ag = 2.0 * H1 * t_eff
    Anet = 2.0 * e_side * t_eff
    k = tangent_tearout_length(H1, Dhole)
    Anes = 2.0 * k * t_eff

    Tr_i = phi * Ag * Fyp / 1000.0
    Tr_ii = phiu * Anet * Fup / 1000.0
    Tr_iii = 0.60 * phiu * Anes * Fup / 1000.0

    opts = [("13.2(b)(i) gross yield", Tr_i),
            ("13.2(b)(ii) net fracture", Tr_ii),
            ("13.2(b)(iii) 0.60 phiu Anes Fu", Tr_iii)]
    name, Tr = min(opts, key=lambda p: p[1])
    uc = _uc(F["Tf_kN"], Tr)

    return {"t_eff_mm": t_eff, "e_side_mm": e_side, "k_mm": k,
            "Ag_mm2": Ag, "Anet_mm2": Anet, "Anes_mm2": Anes,
            "Tr_i_kN": Tr_i, "Tr_ii_kN": Tr_ii, "Tr_iii_kN": Tr_iii,
            "Tr_kN": Tr, "governing": name, "cheeks_effective": cheeks,
            "clause": "Cl. 13.2 (b)", "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 5. Tear-out above the pin, Cl. 13.11 and its closing Note
# ---------------------------------------------------------------------
def tearout(inp, F):
    """Cl. 13.11 reads

        Tr = phiu [ Ut An Fu + 0.6 Agv (Fy + Fu)/2 ]

    and its Note permits the second term alone to be used as the plate
    tear-out resistance along planes tangent to the hole and directed
    towards the edge of the plate. That is exactly the padeye case, so
    the tension term is dropped unless a tension path is supplied.

    Note (c): where Fy > 460 MPa, (Fy + Fu)/2 is replaced by Fy."""
    H1 = _safe(inp.get("H1"))
    Dhole = _safe(inp.get("Dhole"))
    Dcheekp = _safe(inp.get("Dcheekp"))
    tp2 = _safe(inp.get("tp2"))
    tp3 = _safe(inp.get("tp3"))
    Fyp = _safe(inp.get("Fyp"), 345.0)
    Fup = _safe(inp.get("Fup"), 450.0)
    phiu = _safe(inp.get("phiu"), 0.75)
    Ut = _safe(inp.get("Ut"), 1.0)
    An_t = _safe(inp.get("An_tension_mm2"), 0.0)

    r = Dhole / 2.0
    rc = Dcheekp / 2.0

    # The tangent plane runs through the cheek plate for the first
    # (rc - r) of its length and through the lug alone beyond that.
    k_full = tangent_tearout_length(H1, Dhole)
    k_cheek = min(max(rc - r, 0.0), k_full)
    k_lug = max(k_full - k_cheek, 0.0)
    Agv = 2.0 * (k_cheek * (tp2 + 2.0 * tp3) + k_lug * tp2)

    if Fyp > 460.0:
        shear_stress = Fyp
        note_c = True
    else:
        shear_stress = (Fyp + Fup) / 2.0
        note_c = False

    term_v = 0.6 * Agv * shear_stress
    term_t = Ut * An_t * Fup
    Tr = phiu * (term_t + term_v) / 1000.0
    uc = _uc(F["Tf_kN"], Tr)

    # Legacy form used by the previous engine, kept only for comparison
    phi = _safe(inp.get("phi"), 0.90)
    Tr_legacy = 0.60 * phi * Agv * Fup / 1000.0

    return {"k_mm": k_full, "k_cheek_mm": k_cheek, "k_lug_mm": k_lug,
            "Agv_mm2": Agv, "An_tension_mm2": An_t, "Ut": Ut,
            "shear_stress_MPa": shear_stress, "note_c": note_c,
            "Tr_kN": Tr, "Tr_legacy_kN": Tr_legacy,
            "clause": "Cl. 13.11, Note", "uc": uc,
            "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 6. Bearing of the pin on the hole
# ---------------------------------------------------------------------
def bearing(inp, F):
    """Two routes, because a lug pin is rarely a fitted pin.

    Cl. 13.10 (a), accurately cut or fitted parts:
        Br = 1.50 phi Fy A,  A = projected area = Dpin t

    Cl. 13.12.1.2, bolt in a clearance hole, the appropriate model when
    the hole is oversized to clear a shackle pin:
        Br = 3 phi_br t Dpin Fu
    """
    Dpin = _safe(inp.get("Dpin"))
    tp2 = _safe(inp.get("tp2"))
    tp3 = _safe(inp.get("tp3"))
    Fyp = _safe(inp.get("Fyp"), 345.0)
    Fup = _safe(inp.get("Fup"), 450.0)
    phi = _safe(inp.get("phi"), 0.90)
    phibr = _safe(inp.get("phibr"), 0.80)
    fit = str(inp.get("pin_fit", "clearance"))

    t = tp2 + 2.0 * tp3
    Apb = Dpin * t

    Br_fitted = 1.50 * phi * Fyp * Apb / 1000.0
    Br_clear = 3.0 * phibr * t * Dpin * Fup / 1000.0

    if fit == "fitted":
        Br, used = Br_fitted, "Cl. 13.10 (a), fitted pin"
    else:
        Br, used = Br_clear, "Cl. 13.12.1.2, clearance hole"

    uc = _uc(F["Tf_kN"], Br)
    return {"t_mm": t, "Apb_mm2": Apb, "Br_fitted_kN": Br_fitted,
            "Br_clearance_kN": Br_clear, "Br_kN": Br, "fit": fit,
            "clause": used, "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 7. Pin shear, Cl. 13.12.1.1
# ---------------------------------------------------------------------
def pin_shear(inp, F):
    Dpin = _safe(inp.get("Dpin"))
    Fupin = _safe(inp.get("Fupin"), 725.0)
    phib = _safe(inp.get("phib"), 0.80)

    Apin = math.pi * Dpin * Dpin / 4.0
    m = 2.0                                  # double shear
    Vr = 0.60 * phib * m * Apin * Fupin / 1000.0
    uc = _uc(F["Tf_kN"], Vr)
    return {"Apin_mm2": Apin, "m": m, "Vr_kN": Vr,
            "clause": "Cl. 13.12.1.1 (b), double shear",
            "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 8. Out of plane flexural failure of the lug head
# ---------------------------------------------------------------------
def head_flexure(inp, F):
    """Flexural check on the material above the hole, treating it as a
    fixed end strip of span 0.8 D:

        M = Pu (0.8 D) / 8 = [t e^2 / 4] (0.9 Fy)
        Pu = 10 t e^2 (0.9 Fy) / (4 D)

    This is an industry practice check from the lifting literature, not
    a clause of S16, and it is reported separately for that reason so
    that it is never mistaken for a Code requirement."""
    H1 = _safe(inp.get("H1"))
    Dhole = _safe(inp.get("Dhole"))
    tp2 = _safe(inp.get("tp2"))
    tp3 = _safe(inp.get("tp3"))
    Fyp = _safe(inp.get("Fyp"), 345.0)
    cheeks = bool(inp.get("cheeks_effective", True))

    t = tp2 + (2.0 * tp3 if cheeks else 0.0)
    e = max(H1 - Dhole / 2.0, 0.0)
    if Dhole <= 0.0:
        return {"Pr_kN": 0.0, "uc": UC_INF, "verdict": "NG",
                "e_mm": e, "t_mm": t,
                "clause": "Head flexure, industry practice"}

    Pr = 10.0 * t * e * e * (0.9 * Fyp) / (4.0 * Dhole) / 1000.0
    uc = _uc(F["Tf_kN"], Pr)
    return {"t_mm": t, "e_mm": e, "Pr_kN": Pr,
            "clause": "Head flexure, industry practice",
            "uc": uc, "verdict": verdict(uc)}


# ---------------------------------------------------------------------
# 9. Cap plate thickness and bolt prying (unchanged method)
# ---------------------------------------------------------------------
def prying(inp, F, mode="cisc"):
    W1 = _safe(inp.get("W1"))
    L1 = _safe(inp.get("L1"))
    tp1 = _safe(inp.get("tp1"))
    tp2 = _safe(inp.get("tp2"))
    g = _safe(inp.get("g"))
    Db = _safe(inp.get("Db"))
    Nrow = max(1.0, _safe(inp.get("Nrow"), 2.0))
    Fyp = _safe(inp.get("Fyp"), 345.0)
    Fub = _safe(inp.get("Fub"), 830.0)
    phi = _safe(inp.get("phi"), 0.90)
    phib = _safe(inp.get("phib"), 0.80)

    a = (W1 - g) / 2.0
    b = (W1 - tp2) / 2.0 - a
    a_eff = min(a, 1.25 * b) if b > 0 else a
    if mode == "cisc":
        a_prime = a_eff + Db / 2.0
    else:
        a_prime = a_eff - Db / 2.0
    b_prime = b - Db / 2.0

    p = L1 / Nrow
    d_hole = Db + 2.0
    delta = 1.0 - d_hole / p if p > 0 else 0.0
    K = (4.0 * b_prime * 1000.0 / (phi * p * Fyp)) if p > 0 else 0.0

    n_bolts = 2.0 * Nrow
    Pfb = F["Tf_kN"] / n_bolts if n_bolts > 0 else 0.0

    Trb = 0.75 * phib * (math.pi * Db * Db / 4.0) * Fub / 1000.0

    t_min = math.sqrt(K * Pfb / (1.0 + delta)) if (1.0 + delta) > 0 else 0.0
    t_max = math.sqrt(K * Pfb) if K * Pfb > 0 else 0.0

    def alpha_of(P, t):
        if delta <= 0 or t <= 0:
            return 0.0
        val = (K * P / (t * t) - 1.0) / delta
        return val

    alpha_conn = alpha_of(Pfb, tp1)
    alpha_conn_used = max(0.0, min(1.0, alpha_conn))
    Fr = (tp1 * tp1 / K) * (1.0 + delta * alpha_conn_used) * n_bolts \
        if K > 0 else 0.0
    uc_conn = _uc(F["Tf_kN"], Fr)

    alpha_bolt = alpha_conn
    alpha_bolt_used = max(0.0, min(1.0, alpha_bolt))
    q = (a_prime / b_prime) if b_prime > 0 else 0.0
    Tfb = Pfb * (1.0 + delta * alpha_bolt_used * q)
    uc_bolt = _uc(Tfb, Trb)

    plate_ok = "OK" if tp1 >= t_min else "NG"

    return {"a_mm": a, "b_mm": b, "a_eff_mm": a_eff,
            "a_prime_mm": a_prime, "b_prime_mm": b_prime,
            "p_mm": p, "d_hole_mm": d_hole, "delta": delta, "K": K,
            "n_bolts": n_bolts, "Pfb_kN": Pfb, "Trb_kN": Trb,
            "t_min_mm": t_min, "t_max_mm": t_max, "tp1_mm": tp1,
            "alpha_conn": alpha_conn, "alpha_conn_used": alpha_conn_used,
            "alpha_bolt": alpha_bolt, "alpha_bolt_used": alpha_bolt_used,
            "Fr_kN": Fr, "Tfb_kN": Tfb, "mode": mode,
            "uc_conn": uc_conn, "conn_verdict": verdict(uc_conn),
            "uc_bolt": uc_bolt, "bolt_verdict": verdict(uc_bolt),
            "plate_verdict": plate_ok}


# ---------------------------------------------------------------------
# 10. Geometric proportioning
# ---------------------------------------------------------------------
def geometry_checks(inp):
    """Detailing rules for pin connected plates.

    These are not clauses of S16. They are the proportioning limits in
    general use for padeyes, and they are reported as advisory so that
    a detail that departs from them is flagged for review rather than
    silently failed."""
    Dpin = _safe(inp.get("Dpin"))
    Dhole = _safe(inp.get("Dhole"))
    H1 = _safe(inp.get("H1"))
    L2 = _safe(inp.get("L2"))
    Dcheekp = _safe(inp.get("Dcheekp"))

    items = []

    d_min_hole = Dpin + 3.2
    items.append({
        "item": "Hole diameter", "required": ">= Dpin + 3.2 mm",
        "value": "%.1f vs %.1f mm" % (Dhole, d_min_hole),
        "ok": Dhole >= d_min_hole - 1e-6})

    clearance = Dhole - Dpin
    items.append({
        "item": "Pin clearance", "required": "<= 6 mm, otherwise the "
        "fitted bearing route does not apply",
        "value": "%.1f mm" % clearance, "ok": clearance <= 6.0})

    e_min = 0.75 * Dhole
    e_act = H1 - Dhole / 2.0
    items.append({
        "item": "Edge distance above the hole",
        "required": ">= 0.75 Dhole = %.1f mm" % e_min,
        "value": "%.1f mm" % e_act, "ok": e_act >= e_min - 1e-6})

    w_min = 2.5 * Dhole
    items.append({
        "item": "Head width at the hole",
        "required": ">= 2.5 Dhole = %.1f mm" % w_min,
        "value": "%.1f mm" % (2.0 * H1), "ok": 2.0 * H1 >= w_min - 1e-6})

    items.append({
        "item": "Cheek plate over the hole",
        "required": "Dcheekp > Dhole",
        "value": "%.1f vs %.1f mm" % (Dcheekp, Dhole),
        "ok": Dcheekp > Dhole})

    items.append({
        "item": "Lug base wider than the head",
        "required": "L2 >= 2 H1",
        "value": "%.1f vs %.1f mm" % (L2, 2.0 * H1),
        "ok": L2 >= 2.0 * H1 - 1e-6})

    return {"items": items, "all_ok": all(i["ok"] for i in items)}


# ---------------------------------------------------------------------
# 11. Shackle
# ---------------------------------------------------------------------
def shackle_check(inp, F):
    sh = shackle_lookup(inp.get("shackle_in", 2.0))
    Ts = F["Ts_tons"]
    T = _safe(inp.get("T_tons"))
    uc = _uc(T, sh["WLL_t"])
    fits = sh["pin_mm"] <= _safe(inp.get("Dhole")) - 1.0
    return {"nominal_in": sh["nominal_in"], "pin_mm": sh["pin_mm"],
            "WLL_t": sh["WLL_t"], "T_tons": T, "Ts_tons": Ts,
            "uc": uc, "verdict": verdict(uc), "pin_fits_hole": fits}


# ---------------------------------------------------------------------
# Master routine
# ---------------------------------------------------------------------
def design_lug(inp, prying_mode="cisc"):
    F = design_forces(inp)
    W = weld_checks(inp, F)
    LG = lug_section(inp, F)
    PC = pin_connected_section(inp, F)
    TO = tearout(inp, F)
    BR = bearing(inp, F)
    PS = pin_shear(inp, F)
    HF = head_flexure(inp, F)
    PR = prying(inp, F, mode=prying_mode)
    GC = geometry_checks(inp)
    SH = shackle_check(inp, F)

    # The old page reads R["pin"] and expects Vr_kN plus the three
    # component resistances, so that shape is preserved and now fed by
    # the corrected clauses.
    Vr_opts = [("pin shear", PS["Vr_kN"]),
               ("bearing", BR["Br_kN"]),
               ("tear-out", TO["Tr_kN"])]
    gov_name, Vr = min(Vr_opts, key=lambda p: p[1])
    uc_pin = _uc(F["Tf_kN"], Vr)
    PN = {"Apin_mm2": PS["Apin_mm2"], "t_bearing_mm": BR["t_mm"],
          "Vr1_kN": PS["Vr_kN"], "Vr2_kN": BR["Br_kN"],
          "Vr3_kN": TO["Tr_kN"], "Vr_kN": Vr, "Vf_kN": F["Tf_kN"],
          "governing": gov_name, "uc": uc_pin, "verdict": verdict(uc_pin),
          "clauses": "Cl. 13.12.1.1, %s, Cl. 13.11"
                     % BR["clause"]}

    named = [
        ("Weld metal, Cl. 13.13.2.2", W["weld_metal"]["uc"],
         W["weld_metal"]["verdict"]),
        ("Weld base metal, Cl. 13.13.2.1", W["base_metal"]["uc"],
         W["base_metal"]["verdict"]),
        ("Lug plate at base, Cl. 13.2(a)/13.5", LG["uc"], LG["verdict"]),
        ("Pin connected section, Cl. 13.2(b)", PC["uc"], PC["verdict"]),
        ("Tear-out above pin, Cl. 13.11", TO["uc"], TO["verdict"]),
        ("Pin bearing, %s" % BR["clause"], BR["uc"], BR["verdict"]),
        ("Pin shear, Cl. 13.12.1.1", PS["uc"], PS["verdict"]),
        ("Lug head flexure, practice check", HF["uc"],
         HF["verdict"]),
        ("Cap plate connection", PR["uc_conn"], PR["conn_verdict"]),
        ("Bolt with prying", PR["uc_bolt"], PR["bolt_verdict"]),
        ("Shackle WLL", SH["uc"], SH["verdict"]),
    ]
    if W["pjp"] is not None:
        named.append(("PJP groove weld, Cl. 13.13.3.2",
                      W["pjp"]["uc"], W["pjp"]["verdict"]))

    real = [(n, u, v) for n, u, v in named if u is not None]
    if real:
        gname, guc, _ = max(real, key=lambda p: p[1])
    else:
        gname, guc = "none", 0.0
    if guc >= UC_INF:
        gname = gname + " (degenerate geometry)"
    overall = "OK" if all(v == "OK" for _, _, v in named) and GC["all_ok"] \
        else "NG"

    return {
        "forces": F, "welds": W, "lug": LG, "pin_conn": PC,
        "tearout": TO, "bearing": BR, "pin_shear": PS, "flexure": HF,
        "prying": PR, "pin": PN, "geom_check": GC, "shackle": SH,
        "checks": named, "governing_name": gname, "governing_uc": guc,
        "overall": overall,
    }
