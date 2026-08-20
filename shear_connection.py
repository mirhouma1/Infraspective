"""
shear_connection.py - Bolted end plate shear connection to CSA S16.

Infraspective Solutions - structural calculator suite.
Learning module. Pure calculation, no Streamlit imports.

The connection: a plate is shop welded to the end of the supported
beam web with a pair of fillet welds, then field bolted through two
vertical bolt lines to the supporting member.

Load path, which is the order the checks below follow:

    beam web  ->  fillet welds  ->  end plate  ->  bolts
              ->  supporting member

Every element in that chain has to carry the load, so a chain of
limit states is checked in the same order. The weakest link governs.

Resistance factors, CSA S16-19 Cl. 13.1:
    phi   = 0.90  structural steel, yielding
    phi_u = 0.75  fracture and block shear
    phi_b = 0.80  bolts
    phi_br= 0.80  bearing
    phi_w = 0.67  weld metal

ASCII only. Straight quotes only.
"""

import math

PHI = 0.90
PHI_U = 0.75
PHI_B = 0.80
PHI_BR = 0.80
PHI_W = 0.67


# ======================================================================
# BOLT DATA
# ======================================================================
# name: (nominal dia in, nominal dia mm, gross area mm2, Fub MPa,
#        min edge sheared mm, min edge rolled or gas cut mm)
# Fub from ASTM F3125: Grade A325 is 830 MPa up to 1 in diameter and
# 725 MPa above; Grade A490 is 1035 MPa throughout.

BOLTS = {
    "A325 (1/2 in)":     (0.500, 12.70, 127.0, 830.0, 28.0, 22.0),
    "A325 (5/8 in)":     (0.625, 15.88, 198.0, 830.0, 28.0, 22.0),
    "A325 (3/4 in)":     (0.750, 19.05, 285.0, 830.0, 32.0, 25.0),
    "A325 (7/8 in)":     (0.875, 22.23, 388.0, 830.0, 38.0, 28.0),
    "A325 (1 in)":       (1.000, 25.40, 507.0, 830.0, 44.0, 32.0),
    "A325 (1 1/8 in)":   (1.125, 28.58, 641.0, 725.0, 51.0, 38.0),
    "A325 (1 1/4 in)":   (1.250, 31.75, 792.0, 725.0, 57.0, 41.0),
    "A325 (1 1/2 in)":   (1.500, 38.10, 1140.0, 725.0, 67.0, 48.0),
    "A490 (1/2 in)":     (0.500, 12.70, 127.0, 1035.0, 28.0, 22.0),
    "A490 (5/8 in)":     (0.625, 15.88, 198.0, 1035.0, 28.0, 22.0),
    "A490 (3/4 in)":     (0.750, 19.05, 285.0, 1035.0, 32.0, 25.0),
    "A490 (7/8 in)":     (0.875, 22.23, 388.0, 1035.0, 38.0, 28.0),
    "A490 (1 in)":       (1.000, 25.40, 507.0, 1035.0, 44.0, 32.0),
    "A490 (1 1/8 in)":   (1.125, 28.58, 641.0, 1035.0, 51.0, 38.0),
    "A490 (1 1/4 in)":   (1.250, 31.75, 792.0, 1035.0, 57.0, 41.0),
    "A490 (1 1/2 in)":   (1.500, 38.10, 1140.0, 1035.0, 67.0, 48.0),
}

# Fillet weld leg sizes, inches, and the matching electrode strengths.
WELD_SIZES_IN = [0.1875, 0.25, 0.3125, 0.375, 0.4375, 0.5, 0.625, 0.75]
ELECTRODES = {"E41xx (Xu = 410 MPa)": 410.0,
              "E48xx (Xu = 480 MPa)": 480.0,
              "E55xx (Xu = 550 MPa)": 550.0,
              "E62xx (Xu = 620 MPa)": 620.0}


def bolt_props(name):
    d_in, db, ab, fub, ed_sheared, ed_cut = BOLTS[name]
    return {"name": name, "d_in": d_in, "db": db, "Ab": ab, "Fub": fub,
            "ed_sheared": ed_sheared, "ed_cut": ed_cut}


def hole_diameter(db, hole_type="Standard"):
    """S16-19 Cl. 22.3.5.2. Standard holes are 2 mm larger than the
    bolt for bolts up to 24 mm, and 3 mm larger above that."""
    if hole_type == "Standard":
        return db + (2.0 if db <= 24.0 else 3.0)
    if hole_type == "Oversize":
        return db + (5.0 if db <= 24.0 else 8.0)
    return db + (2.0 if db <= 24.0 else 3.0)


def net_hole_allowance(d_hole):
    """S16-19 Cl. 12.3.2: net area is computed with a hole 2 mm
    larger than the actual hole."""
    return d_hole + 2.0


def _result(key, name, clause, demand, capacity, formula, subs, why,
            note=""):
    ratio = (demand / capacity) if capacity > 0 else float("inf")
    return {"key": key, "name": name, "clause": clause,
            "demand": demand, "capacity": capacity, "ratio": ratio,
            "ok": ratio <= 1.0, "formula": formula, "subs": subs,
            "why": why, "note": note}


# ======================================================================
# APPLIED FORCES
# ======================================================================

def resultant_forces(Vf_y, Nf_x, Hf_z=0.0):
    """Vf_y is the beam end reaction, Nf_x the axial force in the beam
    and Hf_z any transverse force. Returns the in-plane resultant on
    the bolt group and the full 3D resultant on the weld."""
    r_plate = math.hypot(Vf_y, Nf_x)
    r_weld = math.sqrt(Vf_y ** 2 + Nf_x ** 2 + Hf_z ** 2)
    return r_plate, r_weld


# ======================================================================
# 1 - BOLT SHEAR (Cl. 13.12.1.2 c)
# ======================================================================

def bolt_shear(bolt, n, threads_intercepted=True, n_planes=1,
               Vf_resultant=0.0, length_gt_760=False):
    """Vr = 0.60 phi_b n m Ab Fub, reduced by 0.70 where the shear
    plane passes through the threads."""
    Ab, Fub = bolt["Ab"], bolt["Fub"]
    vr = 0.60 * PHI_B * n * n_planes * Ab * Fub / 1000.0
    factor = 1.0
    bits = []
    if threads_intercepted:
        factor *= 0.70
        bits.append("0.70 for threads intercepted")
    if length_gt_760:
        factor *= 0.90
        bits.append("0.90 for a joint longer than 760 mm")
    vr *= factor
    subs = (r"V_r = 0.60 \times %.2f \times %d \times %d \times %.0f "
            r"\times %.0f%s = %.1f\ \text{kN}"
            % (PHI_B, n, n_planes, Ab, Fub,
               (r" \times %.3f" % factor) if factor != 1.0 else "", vr))
    return _result(
        "bolt_shear", "Bolt shear", "Cl. 13.12.1.2 (c)",
        Vf_resultant, vr,
        r"V_r = 0.60\,\phi_b\, n\, m\, A_b\, F_u", subs,
        "The bolts cross the interface between the end plate and the "
        "supporting member, so the whole reaction is carried in shear "
        "across the bolt shanks. If the threads fall in the shear "
        "plane the effective area is smaller, which is what the 0.70 "
        "factor represents.",
        "; ".join(bits))


# ======================================================================
# 2 - BOLT BEARING ON THE END PLATE (Cl. 13.12.1.2 a)
# ======================================================================

def bolt_bearing(bolt, n, t, Fu, edge_dist, Vf_resultant=0.0,
                 element="end plate"):
    """Br = 3 phi_br n t d Fu, with the end-distance limit
    Br = phi_br n t Fu min(ed, 1.5 d) x 2 applied where the end
    distance is short."""
    db = bolt["db"]
    br_full = 3.0 * PHI_BR * n * t * db * Fu / 1000.0
    # End tear-out control: the bearing resistance cannot exceed what
    # the material ahead of the bolt can deliver.
    br_edge = 3.0 * PHI_BR * n * t * min(edge_dist, 1.5 * db) * Fu / 1000.0
    br = min(br_full, br_edge)
    gov = ("full bearing, 3 phi_br t d Fu"
           if br_full <= br_edge else
           "end distance controls, ed = %.0f mm < 1.5 d = %.1f mm"
           % (edge_dist, 1.5 * db))
    subs = (r"B_r = 3 \times %.2f \times %d \times %.1f \times %.2f "
            r"\times %.0f = %.1f\ \text{kN}"
            % (PHI_BR, n, t, min(db, min(edge_dist, 1.5 * db)), Fu, br))
    return _result(
        "bearing_%s" % element.replace(" ", "_"),
        "Bolt bearing on the %s" % element, "Cl. 13.12.1.2 (a)",
        Vf_resultant, br,
        r"B_r = 3\,\phi_{br}\, n\, t\, d\, F_u", subs,
        "The bolt shank presses on the side of its hole. If the plate "
        "is thin or the bolt sits close to an edge, the hole "
        "elongates and the material ahead of the bolt tears out. This "
        "is a plate check, not a bolt check, so it uses the plate "
        "thickness and its Fu.",
        gov)


# ======================================================================
# 3 - PLATE SHEAR YIELD ON THE GROSS SECTION (Cl. 13.4.1.1 a)
# ======================================================================

def plate_shear_yield(L, t, Fy, n_planes, Vf_resultant=0.0):
    """Vr = 0.66 phi Ag Fy"""
    ag = n_planes * L * t
    vr = 0.66 * PHI * ag * Fy / 1000.0
    subs = (r"V_r = 0.66 \times %.2f \times (%d \times %.0f \times "
            r"%.1f) \times %.0f = %.1f\ \text{kN}"
            % (PHI, n_planes, L, t, Fy, vr))
    return _result(
        "plate_shear_yield", "End plate shear yield (gross section)",
        "Cl. 13.4.1.1 (a)", Vf_resultant, vr,
        r"V_r = 0.66\,\phi\, A_g\, F_y", subs,
        "The full depth of the plate resists the reaction in shear. "
        "0.66 Fy is the shear yield stress, roughly Fy divided by the "
        "square root of three with a small allowance. This is a "
        "ductile limit state, so it is checked on the gross area with "
        "phi = 0.90.")


# ======================================================================
# 4 - PLATE SHEAR RUPTURE ON THE NET SECTION (Cl. 13.11)
# ======================================================================

def plate_shear_rupture(L, t, Fu, n_rows, d_net, n_planes,
                        Vf_resultant=0.0):
    """Vr = 0.60 phi_u An Fu"""
    an = n_planes * (L - n_rows * d_net) * t
    vr = 0.60 * PHI_U * an * Fu / 1000.0
    subs = (r"A_n = %d (%.0f - %d \times %.1f) \times %.1f = %.0f\ "
            r"\text{mm}^2 \quad V_r = 0.60 \times %.2f \times %.0f "
            r"\times %.0f = %.1f\ \text{kN}"
            % (n_planes, L, n_rows, d_net, t, an, PHI_U, an, Fu, vr))
    return _result(
        "plate_shear_rupture", "End plate shear rupture (net section)",
        "Cl. 13.11", Vf_resultant, vr,
        r"V_r = 0.60\,\phi_u\, A_n\, F_u", subs,
        "Along the bolt line the holes remove material. Rupture is a "
        "brittle limit state reached at Fu rather than Fy, so it "
        "carries the lower phi_u = 0.75. The net length subtracts one "
        "hole per row.")


# ======================================================================
# 5 - PLATE BLOCK SHEAR (Cl. 13.11)
# ======================================================================

def plate_block_shear(t, Fy, Fu, n_rows, pitch, ev, eh, d_net,
                      n_planes, Ut=1.0, Vf_resultant=0.0):
    """Tr + Vr = phi_u [ Ut An Fu + 0.6 Agv (Fy + Fu)/2 ]

    The block tears out below and beside the bolt line: a tension
    face across to the plate edge and a shear face down the bolt line
    to the bottom of the plate.
    """
    lv = (n_rows - 1) * pitch + ev          # gross shear length
    agv = n_planes * lv * t
    ant = n_planes * (eh - 0.5 * d_net) * t
    tr = PHI_U * (Ut * ant * Fu +
                  0.6 * agv * (Fy + Fu) / 2.0) / 1000.0
    subs = (r"A_{gv} = %d \times %.0f \times %.1f = %.0f\ \text{mm}^2"
            r"\quad A_{nt} = %d(%.0f - 0.5 \times %.1f)\times %.1f "
            r"= %.0f\ \text{mm}^2"
            % (n_planes, lv, t, agv, n_planes, eh, d_net, t, ant))
    subs += (r"\\[4pt] T_r + V_r = %.2f\left[%.0f \times %.0f + 0.6 "
             r"\times %.0f \times \frac{%.0f + %.0f}{2}\right] "
             r"= %.1f\ \text{kN}"
             % (PHI_U, ant, Fu, agv, Fy, Fu, tr))
    return _result(
        "block_shear", "End plate block shear", "Cl. 13.11",
        Vf_resultant, tr,
        r"T_r + V_r = \phi_u\left[U_t A_n F_u + 0.6 A_{gv}"
        r"\frac{F_y + F_u}{2}\right]", subs,
        "A U-shaped block of plate tears out as one piece: it pulls "
        "apart on the tension face and shears along the vertical "
        "face. Note that the shear term uses the average of Fy and "
        "Fu, which is S16's way of recognising that the shear face is "
        "somewhere between yielding and rupture when the block "
        "separates.")


# ======================================================================
# 6 - PRYING ACTION AND BOLT TENSION (Cl. 13.12.1.3, CISC Handbook)
# ======================================================================

def prying(bolt, n, t, Fyp, pitch, gage, tw_beam, edge_dist, Nf,
           Vf_bolt):
    """Kulak/Fisher/Struik prying model as adopted by the CISC
    Handbook. Returns the geometry, the prying multipliers and the
    resulting bolt tension."""
    db = bolt["db"]
    b = 0.5 * (gage - tw_beam)
    b_prime = b - 0.5 * db
    a = min(edge_dist, 1.25 * b)
    a_prime = a + 0.5 * db
    d_hole = hole_diameter(db)
    delta = 1.0 - d_hole / pitch if pitch > 0 else 1.0

    n_rows = max(1, int(round(n / 2.0)))
    Tf = Nf / n if n > 0 else 0.0                    # tension per bolt
    Tr = 0.75 * PHI_B * bolt["Ab"] * bolt["Fub"] / 1000.0

    K = (4.0 * b_prime * 1000.0) / (PHI * pitch * Fyp) \
        if (pitch > 0 and Fyp > 0) else 0.0

    # alpha for the bolt force, using the applied tension per bolt
    if t > 0 and delta > 0 and a_prime > 0:
        alpha_b_raw = ((K * Tf / (t ** 2)) - 1.0) * (1.0 / delta)
    else:
        alpha_b_raw = 0.0
    alpha_b = 0.0 if alpha_b_raw < 0 else min(1.0, alpha_b_raw)

    # alpha for the plate capacity, using the bolt tensile resistance
    if t > 0 and delta > 0 and (a_prime + b_prime) > 0:
        alpha_c_raw = (((K * Tr) / (t ** 2)) - 1.0) * \
                      (a_prime / (delta * (a_prime + b_prime)))
    else:
        alpha_c_raw = 0.0
    alpha_c = 0.0 if alpha_c_raw < 0 else min(1.0, alpha_c_raw)

    # bolt force including prying
    if a_prime > 0:
        q = (b_prime / a_prime) * (delta * alpha_b) / \
            (1.0 + delta * alpha_b)
    else:
        q = 0.0
    Tf_pry = Tf * (1.0 + q)

    # plate bending capacity of the connection
    conn_cap = ((t ** 2) / K) * (1.0 + delta * alpha_c) * n \
        if K > 0 else 0.0

    return {"b": b, "b_prime": b_prime, "a": a, "a_prime": a_prime,
            "delta": delta, "K": K, "d_hole": d_hole,
            "alpha_b": alpha_b, "alpha_b_raw": alpha_b_raw,
            "alpha_c": alpha_c, "alpha_c_raw": alpha_c_raw,
            "Tf": Tf, "Tf_pry": Tf_pry, "Tr": Tr, "q": q,
            "conn_cap": conn_cap, "n_rows": n_rows,
            "n_bolts": n}


def plate_bending(pry, Nf, t):
    subs = (r"b' = %.1f\ \text{mm}\quad a' = %.1f\ \text{mm}\quad "
            r"\delta = %.3f \quad K = %.3f \quad \alpha_c = %.2f"
            % (pry["b_prime"], pry["a_prime"], pry["delta"],
               pry["K"], pry["alpha_c"]))
    subs += (r"\\[4pt] T_c = \frac{%.1f^2}{%.3f}\left(1 + %.3f "
             r"\times %.2f\right) \times %d = %.1f\ \text{kN}"
             % (t, pry["K"], pry["delta"], pry["alpha_c"],
                pry["n_bolts"], pry["conn_cap"]))
    return _result(
        "plate_bending", "End plate bending with prying",
        "Cl. 13.12.1.3, CISC Handbook", Nf, pry["conn_cap"],
        r"T_c = \frac{t^2}{K}\left(1 + \delta\alpha\right) n", subs,
        "Axial force in the beam pulls the plate away from the "
        "support. The plate bends in double curvature between the "
        "bolt line and the beam web, and the plate edge levers back "
        "against the support. That lever action, prying, adds tension "
        "to the bolts beyond the applied load. A thicker plate lowers "
        "K and reduces prying.")


def bolt_tension_check(pry):
    subs = (r"T_f = \frac{N_f}{n} = %.1f\ \text{kN} \quad q = %.3f"
            r"\quad T_f(1+q) = %.1f\ \text{kN}"
            % (pry["Tf"], pry["q"], pry["Tf_pry"]))
    subs += (r"\\[4pt] T_r = 0.75 \times %.2f \times A_b F_u "
             r"= %.1f\ \text{kN}" % (PHI_B, pry["Tr"]))
    return _result(
        "bolt_tension", "Bolt tension including prying",
        "Cl. 13.12.1.3", pry["Tf_pry"], pry["Tr"],
        r"T_r = 0.75\,\phi_b\, A_b\, F_u", subs,
        "The bolt has to carry its share of the axial force plus the "
        "prying force q generated by the plate levering on its edge.")


# ======================================================================
# 7 - BOLT SHEAR AND TENSION INTERACTION (Cl. 13.12.1.4)
# ======================================================================

def bolt_interaction(Vf_resultant, n, Vr_total, Tf_pry, Tr):
    """(Vf/Vr)^2 + (Tf/Tr)^2 <= 1.0, evaluated per bolt."""
    vf = Vf_resultant / n if n > 0 else 0.0
    vr = Vr_total / n if n > 0 else 1.0
    term_v = (vf / vr) ** 2 if vr > 0 else float("inf")
    term_t = (Tf_pry / Tr) ** 2 if Tr > 0 else float("inf")
    total = term_v + term_t
    subs = (r"\left(\frac{%.1f}{%.1f}\right)^2 + "
            r"\left(\frac{%.1f}{%.1f}\right)^2 = %.3f + %.3f = %.3f"
            % (vf, vr, Tf_pry, Tr, term_v, term_t, total))
    return _result(
        "interaction", "Bolt shear and tension interaction",
        "Cl. 13.12.1.4", total, 1.0,
        r"\left(\frac{V_f}{V_r}\right)^2 + "
        r"\left(\frac{T_f}{T_r}\right)^2 \le 1.0", subs,
        "A bolt carrying shear and tension at once fails earlier than "
        "either check alone would suggest. The elliptical interaction "
        "captures that coupling. Both terms are squared, so a bolt at "
        "70% in each check is already at 0.98.")


# ======================================================================
# 8 - SUPPORTED BEAM WEB SHEAR (Cl. 13.4.1.1)
# ======================================================================

def beam_web_shear(L, tw, Fy, Vf_resultant=0.0):
    vr = 0.66 * PHI * L * tw * Fy / 1000.0
    subs = (r"V_r = 0.66 \times %.2f \times %.0f \times %.1f \times "
            r"%.0f = %.1f\ \text{kN}" % (PHI, L, tw, Fy, vr))
    return _result(
        "beam_web", "Supported beam web shear", "Cl. 13.4.1.1",
        Vf_resultant, vr,
        r"V_r = 0.66\,\phi\, h\, w\, F_y", subs,
        "The reaction has to get out of the beam web and into the "
        "plate. Only the depth of web covered by the plate is "
        "effective, so a short plate on a thin web often governs the "
        "whole connection. This is the check the source spreadsheet "
        "failed.")


# ======================================================================
# 9 - WELD (Cl. 13.13.2.2)
# ======================================================================

def fillet_weld(D_mm, L, Xu, n_welds=2, theta_deg=0.0,
                Vf_resultant=0.0):
    """Vr = 0.67 phi_w Aw Xu (1.00 + 0.50 sin^1.5 theta)

    Aw is the effective throat area, 0.707 D L for an equal leg
    fillet. theta is the angle between the weld axis and the line of
    action of the force.
    """
    throat = 0.707 * D_mm
    aw = n_welds * throat * L
    th = math.radians(theta_deg)
    mult = 1.0 + 0.50 * (math.sin(th) ** 1.5) if theta_deg > 0 else 1.0
    vr = 0.67 * PHI_W * aw * Xu * mult / 1000.0
    per_mm = vr / (L * n_welds) if L > 0 else 0.0
    subs = (r"A_w = %d \times 0.707 \times %.2f \times %.0f = %.0f\ "
            r"\text{mm}^2" % (n_welds, D_mm, L, aw))
    subs += (r"\\[4pt] V_r = 0.67 \times %.2f \times %.0f \times %.0f"
             r"%s = %.1f\ \text{kN} \quad (%.3f\ \text{kN/mm})"
             % (PHI_W, aw, Xu,
                (r"\times %.3f" % mult) if mult != 1.0 else "",
                vr, per_mm))
    return _result(
        "weld", "Fillet weld to the beam web", "Cl. 13.13.2.2",
        Vf_resultant, vr,
        r"V_r = 0.67\,\phi_w\, A_w\, X_u\left(1.00 + 0.50"
        r"\sin^{1.5}\theta\right)", subs,
        "The fillet welds transfer the whole reaction from the beam "
        "web into the plate. A fillet weld fails on its throat, the "
        "narrowest plane through the weld, which is 0.707 times the "
        "leg for an equal leg fillet. Welds loaded across their axis "
        "are stronger than welds loaded along it, which the sin term "
        "accounts for.",
        "Weld throat = %.2f mm, %.3f kN/mm" % (throat, per_mm))


def weld_leg_limits(t_thinner):
    """S16-19 Cl. 13.13.2.2 and Table 13. Maximum leg along an edge is
    the plate thickness less 2 mm where t >= 6 mm."""
    if t_thinner >= 6.0:
        dmax = t_thinner - 2.0
    else:
        dmax = t_thinner
    if t_thinner <= 13.0:
        dmin = 5.0
    elif t_thinner <= 20.0:
        dmin = 6.0
    else:
        dmin = 8.0
    return dmin, dmax


# ======================================================================
# DETAILING CHECKS
# ======================================================================

def detailing(bolt, pitch, gage, ev, eh, t, plate_L, plate_W,
              edge_condition, n_rows, beam_d):
    """S16-19 Cl. 22.3. Returns a list of (label, value, limit,
    ok, clause) tuples."""
    db = bolt["db"]
    ed_min = (bolt["ed_sheared"] if edge_condition == "Sheared edge"
              else bolt["ed_cut"])
    out = []
    out.append(("Minimum pitch", pitch, 2.7 * db, pitch >= 2.7 * db,
                "Cl. 22.3.1, 2.7 d"))
    out.append(("Minimum gage", gage, 2.7 * db, gage >= 2.7 * db,
                "Cl. 22.3.1, 2.7 d"))
    out.append(("Minimum end distance (vertical)", ev, ed_min,
                ev >= ed_min, "Cl. 22.3.2, Table 6"))
    out.append(("Minimum edge distance (horizontal)", eh, ed_min,
                eh >= ed_min, "Cl. 22.3.2, Table 6"))
    out.append(("Maximum edge distance", max(ev, eh),
                min(12.0 * t, 150.0), max(ev, eh) <= min(12.0 * t, 150.0),
                "Cl. 22.3.3, 12 t or 150 mm"))
    req_L = (n_rows - 1) * pitch + 2.0 * ev
    out.append(("Plate length vs bolt layout", plate_L, req_L,
                plate_L >= req_L - 0.5, "geometry"))
    req_W = gage + 2.0 * eh
    out.append(("Plate width vs bolt layout", plate_W, req_W,
                plate_W >= req_W - 0.5, "geometry"))
    out.append(("Plate length vs beam depth", plate_L, beam_d,
                plate_L <= beam_d, "must fit between the flanges"))
    return out


# ======================================================================
# DRIVER
# ======================================================================

def run_all(inp):
    """inp is a plain dict. Returns (checks, extras)."""
    bolt = bolt_props(inp["bolt_name"])
    db = bolt["db"]
    n = inp["n_bolts"]
    n_rows = max(1, int(round(n / 2.0)))
    d_hole = hole_diameter(db, inp.get("hole_type", "Standard"))
    d_net = net_hole_allowance(d_hole)

    Vf, Nf, Hf = inp["Vf"], inp["Nf"], inp.get("Hf", 0.0)
    r_plate, r_weld = resultant_forces(Vf, Nf, Hf)

    edge_dist = inp["eh"]
    checks = []

    c_shear = bolt_shear(bolt, n, inp["threads_intercepted"],
                         inp.get("n_planes_bolt", 1), r_plate)
    checks.append(c_shear)

    checks.append(bolt_bearing(bolt, n, inp["t_plate"], inp["Fup_u"],
                               inp["ev"], r_plate, "end plate"))
    checks.append(bolt_bearing(bolt, n, inp["t_support"],
                               inp["Fsup_u"], inp["ev"], r_plate,
                               "supporting member"))

    checks.append(plate_shear_yield(inp["plate_L"], inp["t_plate"],
                                    inp["Fyp"], 2, r_plate))
    checks.append(plate_shear_rupture(inp["plate_L"], inp["t_plate"],
                                      inp["Fup_u"], n_rows, d_net, 2,
                                      r_plate))
    checks.append(plate_block_shear(inp["t_plate"], inp["Fyp"],
                                    inp["Fup_u"], n_rows,
                                    inp["pitch"], inp["ev"],
                                    inp["eh"], d_net, 2, 1.0,
                                    r_plate))

    pry = prying(bolt, n, inp["t_plate"], inp["Fyp"], inp["pitch"],
                 inp["gage"], inp["tw_beam"], edge_dist, Nf, r_plate)
    checks.append(plate_bending(pry, Nf, inp["t_plate"]))
    checks.append(bolt_tension_check(pry))
    checks.append(bolt_interaction(r_plate, n, c_shear["capacity"],
                                   pry["Tf_pry"], pry["Tr"]))

    checks.append(beam_web_shear(inp["plate_L"], inp["tw_beam"],
                                 inp["Fy_beam"], r_plate))

    checks.append(fillet_weld(inp["weld_D"], inp["plate_L"],
                              inp["Xu"], 2, inp.get("weld_theta", 0.0),
                              r_weld))

    governing = max(checks, key=lambda c: c["ratio"])
    extras = {"bolt": bolt, "pry": pry, "d_hole": d_hole,
              "d_net": d_net, "n_rows": n_rows,
              "r_plate": r_plate, "r_weld": r_weld,
              "governing": governing,
              "detailing": detailing(bolt, inp["pitch"], inp["gage"],
                                     inp["ev"], inp["eh"],
                                     inp["t_plate"], inp["plate_L"],
                                     inp["plate_W"],
                                     inp.get("edge_condition",
                                             "Gas cut edge"),
                                     n_rows, inp.get("beam_d", 1e9))}
    return checks, extras
