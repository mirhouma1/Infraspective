"""
moment_connection.py - Bolted extended end plate moment connection,
and the column side checks that go with any moment connection, to
CSA S16-19.

Infraspective Solutions - structural calculator suite.
Learning module. Pure calculation, no Streamlit imports.

THE CONNECTION
--------------
The beam is shop welded to a plate that runs past its flanges, and
that plate is field bolted to the column flange. Four bolts straddle
the tension flange, two outside it and two inside, which is the
configuration the literature calls 4E, four bolt extended unstiffened.

WHAT MAKES A MOMENT CONNECTION DIFFERENT FROM A SHEAR ONE
---------------------------------------------------------
A shear connection has one force to deliver and one load path. A
moment connection has to turn a moment into a couple, deliver each half
of that couple separately, and then convince the column to accept two
large opposed point loads on a flange that was never meant to take
them. So the checks come in two families:

    beam side     the couple is formed and carried: bolts, end plate,
                  welds
    column side   the couple is received: flange bending, web yielding,
                  web crippling, web buckling, panel zone shear, and
                  whatever stiffening those demand

The load path, which is the order the checks below follow:

    beam flange  ->  weld  ->  end plate  ->  bolts in tension
                 ->  column flange  ->  column web
                 ->  panel zone  ->  out of the joint

The compression flange short circuits most of that: it bears more or
less directly, so it drives web crippling and buckling rather than
bolt tension.

RESISTANCE FACTORS, Cl. 13.1
    phi    = 0.90   structural steel, yielding
    phi_u  = 0.75   fracture and block shear
    phi_b  = 0.80   bolts
    phi_br = 0.80   bearing
    phi_w  = 0.67   weld metal

These match shear_connection.py exactly, on purpose: the two engines
have to agree about what a bolt can do or the app contradicts itself.

ON THE 1994 WORKBOOK
--------------------
The source spreadsheet this page was checked against is CSA-S16.1-94.
Several constants moved between that edition and S16-19, and the bolt
ones moved a long way:

    bolt tension    1994: Tr = 0.50 Ab Fu
                    S16-19 Cl. 13.12.1.3: Tr = 0.75 phi_b Ab Fu
                                             = 0.60 Ab Fu

    bolt shear      1994: Vr = 0.28 Ab Fu
                    S16-19 Cl. 13.12.1.2: Vr = 0.60 phi_b Ab Fu
                                             = 0.48 Ab Fu, and 0.336
                                             Ab Fu with threads in the
                                             shear plane

So a 1994 sheet is CONSERVATIVE on tension by 20 percent and, with
threads excluded, conservative on shear by about 40 percent. The
comparison is computed in legacy_1994() so the difference can be shown
rather than left to surprise someone reconciling the two.

WHAT IS NOT A CLAUSE
--------------------
S16 has no end plate design clause. The plate thickness and the bolt
prying force come from the moment end plate literature, which is
American in origin: yield line analysis as set out in AISC Design
Guide 4 and AISC 358, and the older Krishnamurthy alpha_m fit that the
source workbook uses. Both are computed. Neither is a code rule, and
every function that uses one says so in its clause field, which reads
"not an S16 clause" rather than a number.

Every check carries a `confidence` field. Where the clause number is
one this module is certain of, it is "confirmed". Where the mechanics
are standard but the exact clause reference should be checked against a
current copy of S16 before the page is relied on, it is "verify". The
page collects the "verify" ones into a panel, because a wrong clause
number in a calculation set is worse than no clause number at all.

ASCII only. Straight quotes only.
"""

import math

PHI = 0.90
PHI_U = 0.75
PHI_B = 0.80
PHI_BR = 0.80
PHI_W = 0.67

E_STEEL = 200000.0        # MPa


# ======================================================================
# BOLT DATA
# ======================================================================
# Imported from shear_connection so there is one bolt table in the app.
# If that module is not importable the table is rebuilt here, identical
# in content, so this engine can still be unit tested on its own.
try:
    from shear_connection import BOLTS, bolt_props          # noqa: F401
except Exception:                                            # pragma: no cover
    BOLTS = {
        "A325 (3/4 in)":   (0.750, 19.05, 285.0, 830.0, 32.0, 25.0),
        "A325 (7/8 in)":   (0.875, 22.23, 388.0, 830.0, 38.0, 28.0),
        "A325 (1 in)":     (1.000, 25.40, 507.0, 830.0, 44.0, 32.0),
        "A325 (1 1/8 in)": (1.125, 28.58, 641.0, 725.0, 51.0, 38.0),
        "A325 (1 1/4 in)": (1.250, 31.75, 792.0, 725.0, 57.0, 41.0),
        "A490 (3/4 in)":   (0.750, 19.05, 285.0, 1035.0, 32.0, 25.0),
        "A490 (7/8 in)":   (0.875, 22.23, 388.0, 1035.0, 38.0, 28.0),
        "A490 (1 in)":     (1.000, 25.40, 507.0, 1035.0, 44.0, 32.0),
        "A490 (1 1/8 in)": (1.125, 28.58, 641.0, 1035.0, 51.0, 38.0),
        "A490 (1 1/4 in)": (1.250, 31.75, 792.0, 1035.0, 57.0, 41.0),
    }

    def bolt_props(name):
        d_in, db, ab, fub, eds, edc = BOLTS[name]
        return {"name": name, "d_in": d_in, "db": db, "Ab": ab,
                "Fub": fub, "ed_sheared": eds, "ed_cut": edc}


def _result(key, name, clause, demand, capacity, formula, subs, why,
            note="", confidence="confirmed", family="beam"):
    """Same contract as shear_connection._result, plus two fields.

    confidence  "confirmed" or "verify", see the module docstring
    family      "beam", "column" or "detail", so the page can group the
                checks the way the load path splits them
    """
    ratio = (demand / capacity) if capacity > 0 else float("inf")
    return {"key": key, "name": name, "clause": clause,
            "demand": demand, "capacity": capacity, "ratio": ratio,
            "ok": ratio <= 1.0, "formula": formula, "subs": subs,
            "why": why, "note": note, "confidence": confidence,
            "family": family}


# ======================================================================
# 0 - APPLIED FORCES: TURNING THE MOMENT INTO A COUPLE
# ======================================================================

def flange_forces(Mf_kNm, Vf_kN, Nf_kN, d, tf):
    """Resolve the beam end actions into the flange couple.

    The moment is delivered as equal and opposite flange forces acting
    at the flange centroids, so the lever arm is d - tf, not d. Axial
    load is split equally between the two flanges and signed so that
    tension adds to the tension flange.

    This one step is where most of the conservatism in a moment
    connection is decided. Using d instead of d - tf understates the
    flange force by a few percent, which sounds harmless until it moves
    a bolt size.
    """
    arm = d - tf
    if arm <= 0:
        arm = max(d, 1.0)
    # Mf in kN m -> N mm is x 10^6; divide by the arm in mm to get N;
    # back to kN is / 10^3.
    Ff_moment = Mf_kNm * 1.0e6 / arm / 1.0e3           # kN
    Ff_axial = Nf_kN / 2.0
    Ff_tension = Ff_moment + Ff_axial
    Ff_compression = Ff_moment - Ff_axial
    return {"arm_mm": arm, "Ff_moment_kN": Ff_moment,
            "Ff_axial_kN": Ff_axial,
            "Ff_tension_kN": Ff_tension,
            "Ff_compression_kN": Ff_compression,
            "Ff_max_kN": max(abs(Ff_tension), abs(Ff_compression)),
            "Vf_kN": Vf_kN, "Mf_kNm": Mf_kNm, "Nf_kN": Nf_kN}


def beam_capacity(Zx_mm3, d, tw, Fy, Mf_kNm, Vf_kN):
    """The beam's own resistances, for reference.

    A connection stronger than the member it joins is usually a sign
    that the member is the wrong size, and a connection weaker than the
    member cannot develop it. Both facts are worth having on screen
    before any connection check is read.
    """
    Mr = PHI * Fy * Zx_mm3 / 1.0e6                      # kN m
    Aw = d * tw
    Vr = 0.66 * PHI * Aw * Fy / 1.0e3                   # kN, Fs = 0.66 Fy
    return {
        "Mr_kNm": Mr, "Vr_kN": Vr,
        "M_ratio": (Mf_kNm / Mr) if Mr > 0 else float("inf"),
        "V_ratio": (Vf_kN / Vr) if Vr > 0 else float("inf"),
        "pct_of_Mr": 100.0 * Mf_kNm / Mr if Mr > 0 else 0.0,
    }


# ======================================================================
# 1 - BOLT TENSION, WITH PRYING
# ======================================================================
# The tension flange force is shared by the bolts that straddle it. In
# a 4E end plate that is four bolts, two outside the flange and two
# inside, and the usual simplification is that all four share equally.
# That is not exactly true - the inner pair is stiffer - but it is the
# basis the yield line equations were calibrated against, so mixing a
# more refined bolt force with those equations would be inconsistent.
#
# Prying is the extra bolt force created when the plate levers against
# the column flange outboard of the bolt line. A thick plate barely
# pries; a thin one can add half again to the bolt force. The model
# used here is the standard split tee form, which is what CISC and AISC
# both present, with the plate treated as a tee stub of the same
# thickness.

def bolt_tension(bolt, n_tension, Ff_tension_kN, tp, bp, pf, g, db,
                 Fyp, d_hole):
    """Bolt tension including prying, split tee model.

    b   bolt line to the face of the flange the plate is bending about
    a   bolt line to the edge of the plate, capped at 1.25 b because a
        longer overhang cannot mobilise more prying
    delta  net section ratio at the bolt line, the material actually
        left between holes
    """
    Ab, Fub = bolt["Ab"], bolt["Fub"]
    Tr = 0.75 * PHI_B * Ab * Fub / 1.0e3                # kN, Cl. 13.12.1.3

    Tf = Ff_tension_kN / max(1, n_tension)

    b = max(pf, 1.0)
    a_raw = max((bp - g) / 2.0, 1.0)
    a = min(a_raw, 1.25 * b)
    b_prime = b - db / 2.0
    a_prime = a + db / 2.0

    # tributary length per bolt across the plate width
    p_trib = max(bp / max(1, n_tension / 2.0), 1.0)
    delta = 1.0 - d_hole / p_trib if p_trib > 0 else 0.0
    delta = min(max(delta, 0.05), 1.0)

    rho = b_prime / a_prime if a_prime > 0 else 0.0

    # alpha: how much of the plate's bending capacity is being used
    if tp > 0 and delta > 0:
        t_c = math.sqrt(4.0 * Tr * 1.0e3 * b_prime
                        / (PHI * p_trib * Fyp)) if p_trib > 0 else 0.0
        ratio = (t_c / tp) ** 2 if tp > 0 else 0.0
        alpha = (1.0 / delta) * (ratio * (Tr / Tf if Tf > 0 else 0.0) - 1.0) \
            if Tf > 0 else 0.0
        alpha = min(max(alpha, 0.0), 1.0)
    else:
        t_c, alpha = 0.0, 1.0

    q = rho * delta * alpha / (1.0 + delta * alpha) if (1.0 + delta * alpha) else 0.0
    q = max(q, 0.0)
    Tf_pry = Tf * (1.0 + q)

    subs = (r"T_f = \frac{%.1f}{%d} = %.1f\ \text{kN}\quad "
            r"b' = %.1f\ \text{mm}\quad a' = %.1f\ \text{mm}\quad "
            r"\delta = %.3f\quad q = %.3f"
            % (Ff_tension_kN, n_tension, Tf, b_prime, a_prime, delta, q))
    subs += (r"\\[4pt] T_f(1+q) = %.1f\ \text{kN}\qquad "
             r"T_r = 0.75 \times %.2f \times %.0f \times %.0f / 10^3 "
             r"= %.1f\ \text{kN}"
             % (Tf_pry, PHI_B, Ab, Fub, Tr))

    res = _result(
        "bolt_tension", "Bolt tension including prying",
        "Cl. 13.12.1.3", Tf_pry, Tr,
        r"T_r = 0.75\,\phi_b\, A_b\, F_u \qquad "
        r"T_f^{*} = \frac{F_{f,t}}{n_t}\,(1+q)", subs,
        "The tension flange force is shared by the bolts straddling it, "
        "and then increased by prying: the end plate levers on the "
        "column flange outboard of the bolt line and pulls the bolt "
        "harder than statics alone suggests. Thicken the plate and q "
        "falls away; thin it and q can add half again to the bolt "
        "force.",
        "Split tee prying model. Not an S16 clause, only Tr is.",
        confidence="confirmed", family="beam")
    res.update({"Tf_kN": Tf, "Tf_pry_kN": Tf_pry, "Tr_kN": Tr,
                "q": q, "delta": delta, "alpha": alpha, "rho": rho,
                "b_prime": b_prime, "a_prime": a_prime, "tc": t_c,
                "p_trib": p_trib})
    return res


# ======================================================================
# 2 - BOLT SHEAR
# ======================================================================

def bolt_shear(bolt, n_shear, Vf_kN, threads_intercepted=True,
               n_planes=1):
    """Vr = 0.60 phi_b n m Ab Fu, times 0.70 for threads in the plane.

    In an extended end plate every bolt in the connection is available
    to carry the beam reaction, not just the tension bolts, because the
    shear is delivered by the plate bearing on the whole bolt group.
    """
    Ab, Fub = bolt["Ab"], bolt["Fub"]
    vr = 0.60 * PHI_B * n_shear * n_planes * Ab * Fub / 1.0e3
    factor = 0.70 if threads_intercepted else 1.0
    vr *= factor
    subs = (r"V_r = 0.60 \times %.2f \times %d \times %d \times %.0f "
            r"\times %.0f%s / 10^3 = %.1f\ \text{kN}"
            % (PHI_B, n_shear, n_planes, Ab, Fub,
               (r" \times 0.70" if threads_intercepted else ""), vr))
    return _result(
        "bolt_shear", "Bolt shear", "Cl. 13.12.1.2 (c)",
        Vf_kN, vr,
        r"V_r = 0.60\,\phi_b\, n\, m\, A_b\, F_u", subs,
        "The beam reaction crosses the interface in shear across the "
        "bolt shanks. In a moment connection this is usually the easy "
        "check, because the bolts were sized by the flange force long "
        "before the reaction became a problem.",
        "0.70 applied for threads intercepted" if threads_intercepted
        else "shear plane clear of the threads",
        confidence="confirmed", family="beam")


def bolt_interaction(Vf_kN, n_shear, Vr_total_kN, Tf_pry_kN, Tr_kN):
    """(Vf/Vr)^2 + (Tf/Tr)^2 <= 1.0, per bolt, Cl. 13.12.1.4.

    This is the check that catches a moment connection where each
    individual check passed comfortably. Both terms are squared, so two
    checks at 75 percent give 1.13 and the connection fails.
    """
    vf = Vf_kN / n_shear if n_shear > 0 else 0.0
    vr = Vr_total_kN / n_shear if n_shear > 0 else 1.0
    term_v = (vf / vr) ** 2 if vr > 0 else float("inf")
    term_t = (Tf_pry_kN / Tr_kN) ** 2 if Tr_kN > 0 else float("inf")
    total = term_v + term_t
    subs = (r"\left(\frac{%.1f}{%.1f}\right)^2 + "
            r"\left(\frac{%.1f}{%.1f}\right)^2 = %.3f + %.3f = %.3f"
            % (vf, vr, Tf_pry_kN, Tr_kN, term_v, term_t, total))
    return _result(
        "bolt_interaction", "Bolt shear and tension interaction",
        "Cl. 13.12.1.4", total, 1.0,
        r"\left(\frac{V_f}{V_r}\right)^2 + "
        r"\left(\frac{T_f}{T_r}\right)^2 \le 1.0", subs,
        "A bolt carrying shear and tension at once fails before either "
        "check on its own would say so. Because both terms are squared, "
        "the penalty arrives suddenly: 70 percent in each term is "
        "already 0.98.",
        confidence="confirmed", family="beam")


# ======================================================================
# 3 - END PLATE THICKNESS
# ======================================================================
# Two methods, deliberately both computed.
#
# YIELD LINE is current practice. The plate is assumed to develop a
# pattern of plastic hinges, and the pattern's internal work is
# equated to the work done by the flange force. All of the geometry
# collapses into one parameter Yp with units of length, and the
# required thickness follows from Mpl = Fy tp^2 Yp / 4.
#
# ALPHA_M is the Krishnamurthy fit the source workbook uses. It reaches
# the same kind of answer through a regression on finite element runs
# from the early 1980s, with an effective moment alpha_m Ff pe / 4.
#
# Neither is an S16 clause. Showing both means a disagreement between
# them is visible on the page instead of hidden in whichever one was
# chosen.

def yield_line_4E(bp, g, pfo, pfi, h0, h1, Fyp, Mf_plate_Nmm, tp):
    """Four bolt extended unstiffened, the 4E pattern.

        Yp = (bp/2)[h1 (1/pfi + 1/pfo)] + (2/g)[h1 (pfi + s)]

    with s = 0.5 sqrt(bp g), and pfi capped at s because a bolt further
    from the flange than s cannot be reached by the yield line pattern
    the equation assumes.

    h0  compression flange centroid to the OUTER bolt row
    h1  compression flange centroid to the INNER bolt row
    """
    s = 0.5 * math.sqrt(max(bp * g, 0.0))
    pfi_eff = min(pfi, s) if s > 0 else pfi
    if pfi_eff <= 0 or pfo <= 0 or g <= 0:
        return None

    # Both bolt rows contribute, each at its own lever arm from the
    # compression flange. Yp carries those arms inside it, so it has
    # units of length and the equation it feeds is a MOMENT balance:
    #
    #     M_r,plate = phi Fyp tp^2 Yp / 4          [N mm]
    #
    # Getting that wrong is easy and expensive. An earlier draft of
    # this function compared Yp against the flange FORCE, which is
    # dimensionally nonsense and returned a 1.8 mm plate for a 250 kN m
    # connection. The demand passed in is therefore a moment in N mm,
    # and the parameter is named to say so.
    Yp = (bp / 2.0) * (h1 / pfi_eff + h0 / pfo) \
        + (2.0 / g) * (h1 * (pfi_eff + s) + h0 * (pfo + s))

    tp_req = (math.sqrt(4.0 * Mf_plate_Nmm / (PHI * Fyp * Yp))
              if Yp > 0 else 0.0)
    Mr_plate = PHI * Fyp * tp * tp * Yp / 4.0 / 1.0e6    # kN m

    subs = (r"s = \tfrac{1}{2}\sqrt{b_p g} = %.1f\ \text{mm}\quad "
            r"p_{fi,eff} = %.1f\ \text{mm}\quad h_1 = %.1f\ \text{mm}"
            % (s, pfi_eff, h1))
    subs += (r"\\[4pt] Y_p = \frac{%.0f}{2}\left[\frac{%.0f}{%.1f}"
             r"+\frac{%.0f}{%.1f}\right] + \frac{2}{%.0f}"
             r"\left[%.0f(%.1f+%.1f) + %.0f(%.1f+%.1f)\right] "
             r"= %.0f\ \text{mm}"
             % (bp, h1, pfi_eff, h0, pfo, g, h1, pfi_eff, s, h0, pfo,
                s, Yp))
    subs += (r"\\[4pt] M_{f,plate} = %.1f\ \text{kN m}\qquad "
             r"t_{p,req} = \sqrt{\frac{4 M_{f}}"
             r"{\phi F_{yp} Y_p}} = %.1f\ \text{mm}"
             r"\qquad t_p = %.1f\ \text{mm}"
             % (Mf_plate_Nmm / 1.0e6, tp_req, tp))

    res = _result(
        "plate_yieldline", "End plate thickness, yield line",
        "not an S16 clause", tp_req, tp,
        r"Y_p = \frac{b_p}{2}\left[\frac{h_1}{p_{fi}}"
        r"+\frac{h_0}{p_{fo}}\right] "
        r"+ \frac{2}{g}\left[h_1(p_{fi}+s) + h_0(p_{fo}+s)\right]"
        r"\qquad t_{p,req}=\sqrt{\frac{4M_f}{\phi F_{yp} Y_p}}", subs,
        "The plate is assumed to fold along a pattern of plastic "
        "hinges. Equating the work done by those hinges to the work "
        "done by the flange force collapses all of the geometry into "
        "one length, Yp. Move a bolt closer to the flange and Yp goes "
        "up, because the yield lines get shorter and the plate is "
        "working harder per unit of fold.",
        "4E pattern, AISC Design Guide 4 and AISC 358. Verify the "
        "expression against your copy before relying on it.",
        confidence="verify", family="beam")
    res.update({"Yp_mm": Yp, "s_mm": s, "pfi_eff": pfi_eff,
                "tp_req_mm": tp_req, "Mr_plate_kNm": Mr_plate})
    return res


def alpha_m_thickness(bp, bf, tf, d, tw, pf, db, w_weld, Fy_beam, Fyp,
                      Ff_tension_kN, tp, bolt_grade_a325=True, bfc=None):
    """Krishnamurthy alpha_m, the method in the source workbook.

    Reproduced so the two methods can be compared, not because it is
    recommended over yield line. Kept in the workbook's own form:

        pe    = pf - db/4 - 0.707 w
        Ca    = 1.2 (1.29) (Favg/641)^0.4 (Fbt/Fb)^0.5     A325
        Cb    = min( sqrt(bf/bp), 1 )
        alpha = Ca Cb (Af/Aw)^(1/3) (pe/db)^(1/4)
        Meu   = alpha Ff pe / 4
        tp    = sqrt( 4 Meu / (phi Fyp bp) )
    """
    # The workbook caps the plate width used in the calculation at the
    # narrower of the beam flange and the column flange, each plus an
    # inch. Width beyond that is not mobilised by the yield pattern, so
    # counting it would overstate the plate.
    bp = min(bp, min(bf + 25.4, bfc + 25.4)) if bfc else bp
    pe = pf - db / 4.0 - 0.707 * w_weld
    if pe <= 0:
        return None
    Favg = 0.5 * (Fy_beam + Fyp)
    Fb = 0.75 * Fyp
    Fbt = 303.0 if bolt_grade_a325 else 372.0
    ref = 641.0 if bolt_grade_a325 else 793.0
    Ca = 1.2 * 1.29 * (Favg / ref) ** 0.4 * (Fbt / Fb) ** 0.5
    Cb = min(math.sqrt(bf / bp) if bp > 0 else 1.0, 1.0)
    Af = bf * tf
    Aw = (d - 2.0 * tf) * tw
    if Aw <= 0:
        return None
    alpha = Ca * Cb * (Af / Aw) ** (1.0 / 3.0) * (pe / db) ** 0.25
    Meu = alpha * (Ff_tension_kN * 1.0e3) * pe / 4.0     # N mm
    tp_req = math.sqrt(4.0 * Meu / (PHI * Fyp * bp)) if bp > 0 else 0.0

    subs = (r"p_e = %.1f - \tfrac{%.1f}{4} - 0.707(%.0f) = %.1f\ "
            r"\text{mm}\quad C_a = %.3f\quad C_b = %.3f\quad "
            r"A_f/A_w = %.2f" % (pf, db, w_weld, pe, Ca, Cb, Af / Aw))
    subs += (r"\\[4pt] \alpha_m = %.3f \qquad M_{eu} = "
             r"\frac{\alpha_m F_f p_e}{4} = %.2f\ \text{kN m}"
             % (alpha, Meu / 1.0e6))
    subs += (r"\\[4pt] t_p = \sqrt{\frac{4 M_{eu}}{\phi F_{yp} b_p}} "
             r"= %.1f\ \text{mm}\qquad t_p\ \text{used} = %.1f\ "
             r"\text{mm}" % (tp_req, tp))

    res = _result(
        "plate_alpham", "End plate thickness, Krishnamurthy alpha_m",
        "not an S16 clause", tp_req, tp,
        r"\alpha_m = C_a C_b \left(\frac{A_f}{A_w}\right)^{1/3}"
        r"\left(\frac{p_e}{d_b}\right)^{1/4}\qquad "
        r"t_p=\sqrt{\frac{4\,\alpha_m F_f p_e}{4\,\phi F_{yp} b_p}}",
        subs,
        "The method in the source workbook. It reaches the plate "
        "thickness through a regression fitted to finite element runs "
        "rather than through a collapse mechanism, and it folds prying "
        "into alpha_m instead of reporting it separately. Shown beside "
        "the yield line answer so the two can be compared.",
        "Krishnamurthy. Retained for comparison with the 1994 "
        "workbook, not recommended as the primary method.",
        confidence="verify", family="beam")
    res.update({"pe_mm": pe, "Ca": Ca, "Cb": Cb, "alpha_m": alpha,
                "Meu_kNm": Meu / 1.0e6, "tp_req_mm": tp_req})
    return res


# ======================================================================
# 4 - WELDS, BEAM TO END PLATE
# ======================================================================

def flange_weld(Ff_kN, bf, tw, D_mm, Xu, cjp=False):
    """Fillet weld all round the tension flange, or a CJP groove.

    A CJP groove weld develops the flange, so there is nothing to
    check: the flange itself becomes the limit. A fillet weld has to be
    sized, and the effective length is the flange perimeter less the
    web thickness, which is the part of the flange that actually has
    plate behind it on both sides.
    """
    if cjp:
        return _result(
            "flange_weld", "Beam flange to end plate weld",
            "Cl. 13.13.3", 0.0, 1.0,
            r"\text{CJP groove weld develops the flange}",
            r"\text{No calculation: the flange governs, not the weld.}",
            "A complete joint penetration groove weld makes the flange "
            "and the plate continuous, so the weld cannot be the weak "
            "link. This is what the standard details call for at a "
            "moment connection flange, and it is why they specify the "
            "weld rather than sizing it.",
            "CJP selected", confidence="confirmed", family="beam")

    Lw = 2.0 * bf - tw
    Aw = 0.707 * D_mm * Lw
    # Cl. 13.13.2.2, transverse loading: theta = 90 deg, so the
    # directional term is (1.00 + 0.50 sin^1.5 90) = 1.50
    Vr = 0.67 * PHI_W * Aw * Xu * 1.50 / 1.0e3
    subs = (r"L_w = 2 b_f - t_w = 2(%.0f) - %.1f = %.0f\ \text{mm}"
            r"\quad A_w = 0.707(%.0f)(%.0f) = %.0f\ \text{mm}^2"
            % (bf, tw, Lw, D_mm, Lw, Aw))
    subs += (r"\\[4pt] V_r = 0.67 \times %.2f \times %.0f \times %.0f "
             r"\times 1.50 / 10^3 = %.0f\ \text{kN}"
             % (PHI_W, Aw, Xu, Vr))
    return _result(
        "flange_weld", "Beam flange to end plate weld",
        "Cl. 13.13.2.2", Ff_kN, Vr,
        r"V_r = 0.67\,\phi_w A_w X_u\,(1.00 + 0.50\sin^{1.5}\theta)",
        subs,
        "The whole flange force crosses this weld. It is loaded square "
        "on, theta = 90 degrees, which is the most efficient direction "
        "for a fillet and earns the full 1.5 directional factor.",
        confidence="confirmed", family="beam")


def web_weld(Vf_kN, Ff_web_kN, d, tf, tw, D_mm, Xu, Fy_beam):
    """Web fillet welds, both sides.

    Two demands, and they are not the same length of weld:

        the beam reaction, carried on the full web depth between
        flanges

        the part of the flange couple carried by the web, which for a
        rolled section is small but is the reason the web weld is
        sometimes larger than the reaction alone would suggest
    """
    Lw = d - 2.0 * tf
    Aw = 2.0 * 0.707 * D_mm * Lw
    # longitudinal loading, theta = 0, no directional increase
    Vr = 0.67 * PHI_W * Aw * Xu / 1.0e3
    subs = (r"L_w = d - 2t_f = %.0f\ \text{mm}\quad "
            r"A_w = 2(0.707)(%.0f)(%.0f) = %.0f\ \text{mm}^2"
            % (Lw, D_mm, Lw, Aw))
    subs += (r"\\[4pt] V_r = 0.67 \times %.2f \times %.0f \times %.0f "
             r"/ 10^3 = %.0f\ \text{kN}" % (PHI_W, Aw, Xu, Vr))
    return _result(
        "web_weld", "Beam web to end plate weld",
        "Cl. 13.13.2.2", Vf_kN, Vr,
        r"V_r = 0.67\,\phi_w A_w X_u \qquad (\theta = 0)", subs,
        "The reaction runs down the web and crosses this weld along "
        "its length, so theta is zero and there is no directional "
        "increase to claim. The weld is sized on the reaction, but it "
        "should never be smaller than the minimum for the plate "
        "thickness it joins.",
        confidence="confirmed", family="beam")


def min_fillet(t_thicker):
    """Cl. 13.13.2.5 minimum fillet size, driven by the thicker part."""
    if t_thicker <= 12.0:
        return 5.0
    if t_thicker <= 20.0:
        return 6.0
    return 8.0


# ======================================================================
# 5 - COLUMN SIDE
# ======================================================================
# Everything from here on is about the column's willingness to accept
# two large opposed point loads on a flange that was rolled to carry
# axial load. Four separate things can go wrong, and they are genuinely
# different mechanisms rather than four versions of the same one:
#
#   flange bending    the tension flange force bends the column flange
#                     out of plane, and the bolts near the web pick up
#                     far more than the ones near the flange tip
#
#   web yielding      the compression force spreads through the flange
#                     at roughly 1:2.5 and squashes a band of web
#
#   web crippling     the same force buckles the web locally, right
#                     under the flange, before the whole web goes
#
#   panel zone shear  the two opposed flange forces are a couple acting
#                     on the web panel between the flanges, and that
#                     panel has to carry the resulting shear
#
# Each has its own remedy, and they are not interchangeable: stiffeners
# fix the first three, a doubler plate fixes the fourth.

def column_flange_bending(Ff_tension_kN, tfc, g, db, Fyc, bfc, pf, tfb):
    """Column flange bending under the tension flange force.

    The classic result is that the effective width of column flange
    working on each bolt is about 3.5 times the bolt pitch from the
    web, and the whole thing reduces to a compact expression in the
    flange thickness squared. The version used here is the yield line
    form usually written as

        Tr = phi (6.25) tfc^2 Fyc         approximately

    with the 6.25 coming out of the yield line pattern for a bolt group
    straddling a web. Different texts publish coefficients between 6
    and 7 for the same mechanism.
    """
    coeff = 6.25
    Tr = PHI * coeff * tfc * tfc * Fyc / 1.0e3
    subs = (r"T_r = %.2f \times %.2f \times %.1f^2 \times %.0f / 10^3 "
            r"= %.0f\ \text{kN}" % (PHI, coeff, tfc, Fyc, Tr))
    subs += (r"\\[4pt] F_{f,t} = %.0f\ \text{kN}" % Ff_tension_kN)
    return _result(
        "col_flange_bend", "Column flange bending",
        "Cl. 21.3 / not an S16 clause", Ff_tension_kN, Tr,
        r"T_r \approx \phi\,(6.25)\,t_{fc}^{2}\,F_{yc}", subs,
        "The tension flange pulls on the column flange between the "
        "bolts and the web. A thin flange folds outwards, the bolts "
        "near the web take almost all of the load and the ones near "
        "the tip take almost none. Because the resistance goes as the "
        "flange thickness squared, this check moves faster than any "
        "other on the column side: a column one size heavier often "
        "removes the need for stiffeners entirely.",
        "Coefficients between 6 and 7 are published for this same "
        "mechanism. Verify against your copy of S16 and the CISC "
        "handbook before use.",
        confidence="verify", family="column")


def column_web_yielding(Ff_kN, twc, tfb, tp, kc, Fyc, at_column_end=False):
    """Web local yielding under a concentrated flange force.

    The force spreads out of the flange at about 1 in 2.5 through the
    column flange and its fillet, so the length of web actually
    resisting it is the flange thickness plus the plate, plus 2.5k each
    side. At the end of a column the spread only happens one way.
    """
    spread = 2.5 * kc * (1.0 if at_column_end else 2.0)
    N = tfb + 2.0 * tp
    Lb = N + spread
    Br = PHI * twc * Lb * Fyc / 1.0e3
    subs = (r"L_b = (t_{fb} + 2t_p) + %s(2.5 k) = (%.1f + 2 \times %.1f)"
            r" + %.1f = %.0f\ \text{mm}"
            % ("1" if at_column_end else "2", tfb, tp, spread, Lb))
    subs += (r"\\[4pt] B_r = %.2f \times %.1f \times %.0f \times %.0f "
             r"/ 10^3 = %.0f\ \text{kN}" % (PHI, twc, Lb, Fyc, Br))
    return _result(
        "col_web_yield", "Column web local yielding",
        "Cl. 14.3.2", Ff_kN, Br,
        r"B_r = \phi\, t_{wc}\, \left[(t_{fb}+2t_p) + 5k\right] F_{yc}",
        subs,
        "The flange force does not arrive on a knife edge: it spreads "
        "through the column flange and the fillet before it reaches "
        "the web. The 2.5:1 spread each side is what sets the length "
        "of web doing the work. Near the top of a column the force can "
        "only spread one way, which halves the length and is why end "
        "conditions matter here.",
        "One-sided spread assumed" if at_column_end else "",
        confidence="verify", family="column")


def column_web_crippling(Ff_compression_kN, twc, tfc, dc, Fyc, N,
                         at_column_end=False):
    """Web crippling, compression side only.

    A local buckle of the web directly under the loaded flange. The
    expression is the standard one, with the end-of-member reduction
    applied when the load is close to the end of the column.
    """
    if twc <= 0 or tfc <= 0 or dc <= 0:
        return None
    ratio = N / dc if dc > 0 else 0.0
    # 0.80 interior, halved to 0.40 where the load is near the end of
    # the member: a web there has no material beyond to share the
    # wrinkle with. These are the coefficients of the standard web
    # crippling expression, which is written in a unit-consistent form
    # (E and Fy both appear under the root) so it needs no imperial
    # conversion factors.
    coeff = 0.40 if at_column_end else 0.80
    Br = (coeff * PHI_BR * twc ** 2
          * (1.0 + 3.0 * ratio * (twc / tfc) ** 1.5)
          * math.sqrt(E_STEEL * Fyc * tfc / twc) / 1.0e3)
    subs = (r"N/d_c = %.3f\quad t_{wc}/t_{fc} = %.3f" % (ratio, twc / tfc))
    subs += (r"\\[4pt] B_r = %.2f\,\phi_{br} t_{wc}^2\left[1+3\frac{N}"
             r"{d_c}\left(\frac{t_{wc}}{t_{fc}}\right)^{1.5}\right]"
             r"\sqrt{\frac{E F_{yc} t_{fc}}{t_{wc}}} = %.0f\ \text{kN}"
             % (coeff, Br))
    return _result(
        "col_web_cripple", "Column web crippling",
        "Cl. 14.3.2", Ff_compression_kN, Br,
        r"B_r = C\,\phi_{br} t_{wc}^{2}\left[1+3\frac{N}{d_c}"
        r"\left(\frac{t_{wc}}{t_{fc}}\right)^{1.5}\right]"
        r"\sqrt{\frac{E F_{yc} t_{fc}}{t_{wc}}}", subs,
        "Compression side only. This is a local buckle of the web just "
        "under the loaded flange, and it is a different failure from "
        "web yielding even though the two are checked with the same "
        "force. Yielding is a squash over a length; crippling is a "
        "wrinkle at a point.",
        "Coefficient halved for a load near the column end"
        if at_column_end else "",
        confidence="verify", family="column")


def column_web_buckling(Ff_compression_kN, twc, dc, tfc, Fyc):
    """Compression buckling of the unstiffened web between flanges.

    Relevant when a beam frames in on both sides so the web has an
    opposed pair of compression forces on it, with no way to shed them.
    """
    h = dc - 2.0 * tfc
    if h <= 0 or twc <= 0:
        return None
    # Unit consistent form. The 4100 tw^3 sqrt(Fy) / h that appears in
    # older sheets is an IMPERIAL expression: it wants inches, ksi and
    # returns kips. Dropping millimetres and megapascals into it and
    # reading the answer as kilonewtons is wrong twice over, once for
    # the units inside and once for the units out. The equivalent
    # SI-safe form carries E under the root, which makes it
    # dimensionless in the coefficient and correct in any consistent
    # set of units.
    Br = PHI * 24.0 * (twc ** 3) * math.sqrt(E_STEEL * Fyc) / h / 1.0e3
    subs = (r"h = d_c - 2t_{fc} = %.0f\ \text{mm}" % h)
    subs += (r"\\[4pt] B_r = \frac{%.2f \times 24 \times %.1f^3 "
             r"\sqrt{%.0f \times %.0f}}{%.0f} / 10^3 = %.0f\ \text{kN}"
             % (PHI, twc, E_STEEL, Fyc, h, Br))
    return _result(
        "col_web_buckle", "Column web compression buckling",
        "Cl. 14.3.2", Ff_compression_kN, Br,
        r"B_r = \frac{\phi\,(24)\,t_{wc}^{3}\sqrt{E F_{yc}}}{h}", subs,
        "The web is a slender plate held along two edges by the "
        "flanges. Push on both flanges at once and it can buckle out "
        "of plane over its whole depth. This governs only where beams "
        "frame in from both sides at the same level; with a beam one "
        "side the web can lean on the other half.",
        "Applies where beams frame both sides at the same level. "
        "Written in the unit-consistent 24 tw^3 sqrt(E Fy)/h form, not "
        "the imperial 4100 tw^3 sqrt(Fy)/h of the older sheets.",
        confidence="verify", family="column")


def panel_zone_shear(Mf_kNm, Vf_col_kN, dc, twc, tfc, db_beam, Fyc,
                     tdp=0.0, Fydp=None):
    """Panel zone shear, and the doubler plate that fixes it.

    The two flange forces are a couple acting on the web panel bounded
    by the column flanges and the beam flanges. The shear in that panel
    is the flange force less whatever the column shear above the joint
    already carries.

        Vf,panel = Mf / (db - tfb) - Vf,column
        Vr       = 0.55 phi dc tw Fyc

    A doubler plate adds its own thickness to tw. Note the 0.55, not
    the 0.66 used for a beam web: the panel is a short deep element in
    a different stress state, and the lower coefficient is the one the
    moment connection literature and the source workbook both use.
    """
    arm = max(db_beam, 1.0)
    Vf_panel = Mf_kNm * 1.0e6 / arm / 1.0e3 - Vf_col_kN
    t_eff = twc + (tdp if tdp else 0.0)
    Vr = 0.55 * PHI * dc * t_eff * Fyc / 1.0e3
    tw_req = (Vf_panel * 1.0e3) / (0.55 * PHI * dc * Fyc) if dc > 0 else 0.0

    subs = (r"V_{f,panel} = \frac{M_f}{d_b - t_{fb}} - V_{f,col} = "
            r"\frac{%.1f \times 10^6}{%.0f} / 10^3 - %.0f = %.0f\ "
            r"\text{kN}" % (Mf_kNm, arm, Vf_col_kN, Vf_panel))
    subs += (r"\\[4pt] V_r = 0.55 \times %.2f \times %.0f \times %.1f "
             r"\times %.0f / 10^3 = %.0f\ \text{kN}"
             % (PHI, dc, t_eff, Fyc, Vr))
    subs += (r"\\[4pt] t_{w,req} = %.1f\ \text{mm}\quad "
             r"t_{wc} = %.1f\ \text{mm}%s"
             % (tw_req, twc,
                (r"\quad t_{dp} = %.1f\ \text{mm}" % tdp) if tdp else ""))

    res = _result(
        "panel_zone", "Column panel zone shear",
        "Cl. 13.4.1.1 / 27.2.4.2", Vf_panel, Vr,
        r"V_{f,panel} = \frac{M_f}{d_b - t_{fb}} - V_{f,col}"
        r"\qquad V_r = 0.55\,\phi\, d_c\, t_w\, F_{yc}", subs,
        "The flange couple does not just push and pull on the flanges: "
        "it shears the web panel between them. This is the check that "
        "the standard details answer with a web doubler plate, and it "
        "is the one most often forgotten, because nothing about it "
        "looks like a connection check. It is a member check happening "
        "inside a joint.",
        "0.55 coefficient per moment connection practice, not the 0.66 "
        "of a beam web. Verify against your copy of S16.",
        confidence="verify", family="column")
    res.update({"Vf_panel_kN": Vf_panel, "tw_req_mm": tw_req,
                "t_eff_mm": t_eff,
                "doubler_req_mm": max(0.0, tw_req - twc)})
    return res


# ======================================================================
# 6 - STIFFENERS
# ======================================================================

def stiffener_design(deficits_kN, bfc, twc, tfc, dc, kc, Fys, n_pairs=2):
    """Size the stiffeners from whichever column check fell short.

    Only the deficit is carried by the stiffener: the column web and
    flange keep whatever they could already do. This is why a column
    that is only slightly short gets a thin stiffener rather than one
    sized for the whole flange force.
    """
    deficit = max([d for d in deficits_kN if d is not None] + [0.0])
    w = 0.5 * (bfc - twc) - 5.0                 # width to the flange tip
    if w <= 0:
        w = max(bfc * 0.35, 25.0)
    L = dc - 2.0 * tfc
    ts_req = (deficit * 1.0e3) / (PHI * Fys * 2.0 * w) if w > 0 else 0.0
    ts_min_local = w / 8.0        # outstand limit, so the stiffener
                                  # yields before it buckles
    ts = max(ts_req, ts_min_local)

    subs = (r"\text{deficit} = %.0f\ \text{kN}\quad w = \tfrac{1}{2}"
            r"(b_{fc}-t_{wc}) - 5 = %.0f\ \text{mm}\quad L = d_c - "
            r"2t_{fc} = %.0f\ \text{mm}" % (deficit, w, L))
    subs += (r"\\[4pt] t_{s,req} = \frac{\text{deficit}}"
             r"{\phi F_{ys}\,(2w)} = %.1f\ \text{mm}\qquad "
             r"\frac{w}{8} = %.1f\ \text{mm}\qquad \text{use } t_s "
             r"\ge %.1f\ \text{mm}" % (ts_req, ts_min_local, ts))

    res = _result(
        "stiffeners", "Transverse stiffener sizing",
        "Cl. 14.4.2 / not an S16 clause",
        ts_req, max(ts, 1.0e-9),
        r"t_{s} = \frac{F_{f} - B_{r,column}}{\phi F_{ys}\,(2w)}"
        r"\qquad t_s \ge \frac{w}{8}", subs,
        "Stiffeners only make up the shortfall. Whatever the column "
        "web and flange could already carry stays carried by them, so "
        "the stiffener is sized on the deficit, not on the whole "
        "flange force. The w/8 limit is there so the stiffener does "
        "not buckle before it yields.",
        "Four stiffeners, two each side, as the standard details show.",
        confidence="verify", family="column")
    res.update({"deficit_kN": deficit, "w_mm": w, "L_mm": L,
                "ts_req_mm": ts_req, "ts_min_mm": ts_min_local,
                "ts_use_mm": ts, "required": deficit > 0.0})
    return res


# ======================================================================
# 7 - DETAILING
# ======================================================================

def detailing(bp, bf_beam, bfc, g, pf, db, tp, d_hole, bolt):
    """Geometry rules. Not strength, but they decide buildability, and
    a connection that cannot be assembled has failed just as surely as
    one that cannot carry the load."""
    items = []

    def add(name, value, low, high, unit="mm", why=""):
        ok = True
        if low is not None and value < low - 1e-9:
            ok = False
        if high is not None and value > high + 1e-9:
            ok = False
        items.append({"item": name, "value": value, "min": low,
                      "max": high, "unit": unit, "ok": ok, "why": why})

    add("End plate width bp", bp, bf_beam, min(bf_beam + 25.4, bfc + 25.4),
        why="Wide enough to hold the flange, no wider than the column "
            "flange plus an inch: extra width does nothing but sit "
            "there and collect an entry on the cut list.")
    add("Bolt pitch pf, flange face to bolt", pf, db + 12.7, 2.5 * 25.4,
        why="Far enough for a wrench, close enough that the plate is "
            "not levering on a long arm. Every millimetre added here "
            "goes straight into the prying force.")
    add("Bolt gauge g", g, 2.0 * (12.7 + db), min(bp - 2.5 * db,
                                                  bfc - 2.5 * db),
        why="Wide enough to clear the beam web and get a wrench in, "
            "narrow enough that the bolts stay on the column flange.")
    add("Edge distance, plate", 0.5 * (bp - g), bolt["ed_cut"], None,
        why="Cl. 22.3.2 minimum edge distance for the bolt size and "
            "the cut condition.")
    add("Plate thickness vs bolt", tp, 0.5 * db, None,
        why="A plate much thinner than half the bolt diameter will "
            "pry hard whatever the strength check says.")

    all_ok = all(i["ok"] for i in items)
    return {"items": items, "all_ok": all_ok}


# ======================================================================
# 8 - THE 1994 COMPARISON
# ======================================================================

def legacy_1994(bolt, n_tension, n_shear, Ff_tension_kN, Vf_kN):
    """The bolt resistances the source workbook would have produced.

    Shown so a reconciliation against the old sheet has somewhere to
    land. These are NOT used in any check on the page.
    """
    Ab, Fub = bolt["Ab"], bolt["Fub"]
    Tr_94 = 0.50 * Fub * Ab / 1.0e3
    Vr_94 = 0.28 * Fub * Ab / 1.0e3
    Tr_19 = 0.75 * PHI_B * Ab * Fub / 1.0e3
    Vr_19_thr = 0.60 * PHI_B * Ab * Fub * 0.70 / 1.0e3
    Vr_19_exc = 0.60 * PHI_B * Ab * Fub / 1.0e3
    return {
        "Tr_94_kN": Tr_94, "Vr_94_kN": Vr_94,
        "Tr_19_kN": Tr_19, "Vr_19_thr_kN": Vr_19_thr,
        "Vr_19_exc_kN": Vr_19_exc,
        "T_change_pct": 100.0 * (Tr_19 - Tr_94) / Tr_94 if Tr_94 else 0.0,
        "V_change_thr_pct": (100.0 * (Vr_19_thr - Vr_94) / Vr_94
                             if Vr_94 else 0.0),
        "V_change_exc_pct": (100.0 * (Vr_19_exc - Vr_94) / Vr_94
                             if Vr_94 else 0.0),
        "Tbf_kN": Ff_tension_kN / max(1, n_tension),
        "Vbf_kN": Vf_kN / max(1, n_shear),
    }


# ======================================================================
# 9 - RUN EVERYTHING
# ======================================================================

def run_all(inp):
    """Run the whole sequence and return everything the page needs.

    inp keys, all SI with mm and kN and MPa:
        beam:   db_d, db_tw, db_bf, db_tf, db_Zx, Fy_beam
        column: dc, twc, bfc, tfc, kc, Fy_col
        plate:  tp, bp, pf_o, pf_i, g, Fy_plate
        bolts:  bolt_name, n_tension, n_shear, threads_intercepted
        welds:  cjp_flange, D_flange, D_web, Xu
        loads:  Mf, Vf, Nf, Vf_col
        flags:  at_column_end, beams_both_sides, tdp
    """
    b = bolt_props(inp["bolt_name"])
    db = b["db"]
    d_hole = db + 2.0

    F = flange_forces(inp["Mf"], inp["Vf"], inp.get("Nf", 0.0),
                      inp["db_d"], inp["db_tf"])
    beam = beam_capacity(inp["db_Zx"], inp["db_d"], inp["db_tw"],
                         inp["Fy_beam"], inp["Mf"], inp["Vf"])

    checks = []

    # -- beam side ----------------------------------------------------
    bt = bolt_tension(b, inp["n_tension"], F["Ff_tension_kN"],
                      inp["tp"], inp["bp"], inp["pf_i"], inp["g"], db,
                      inp["Fy_plate"], d_hole)
    checks.append(bt)

    bs = bolt_shear(b, inp["n_shear"], inp["Vf"],
                    inp.get("threads_intercepted", True))
    checks.append(bs)

    checks.append(bolt_interaction(inp["Vf"], inp["n_shear"],
                                   bs["capacity"], bt["Tf_pry_kN"],
                                   bt["Tr_kN"]))

    # lever arms measured from the compression flange centroid
    h_comp = inp["db_d"] - inp["db_tf"] / 2.0
    h1 = h_comp - inp["db_tf"] / 2.0 - inp["pf_i"]      # inner row
    h0 = h_comp + inp["db_tf"] / 2.0 + inp["pf_o"]      # outer row
    # demand on the plate is the flange force acting at the couple arm
    Mf_plate = F["Ff_tension_kN"] * 1.0e3 * F["arm_mm"]       # N mm
    yl = yield_line_4E(inp["bp"], inp["g"], inp["pf_o"], inp["pf_i"],
                       h0, h1, inp["Fy_plate"], Mf_plate, inp["tp"])
    if yl:
        checks.append(yl)

    am = alpha_m_thickness(inp["bp"], inp["db_bf"], inp["db_tf"],
                           inp["db_d"], inp["db_tw"], inp["pf_i"], db,
                           0.0 if inp.get("cjp_flange") else inp["D_flange"],
                           inp["Fy_beam"], inp["Fy_plate"],
                           F["Ff_tension_kN"], inp["tp"],
                           b["Fub"] <= 900.0, inp["bfc"])
    if am:
        checks.append(am)

    checks.append(flange_weld(F["Ff_max_kN"], inp["db_bf"], inp["db_tw"],
                              inp["D_flange"], inp["Xu"],
                              inp.get("cjp_flange", False)))
    checks.append(web_weld(inp["Vf"], 0.0, inp["db_d"], inp["db_tf"],
                           inp["db_tw"], inp["D_web"], inp["Xu"],
                           inp["Fy_beam"]))

    # -- column side --------------------------------------------------
    cfb = column_flange_bending(F["Ff_tension_kN"], inp["tfc"], inp["g"],
                                db, inp["Fy_col"], inp["bfc"],
                                inp["pf_i"], inp["db_tf"])
    checks.append(cfb)

    cwy = column_web_yielding(F["Ff_max_kN"], inp["twc"], inp["db_tf"],
                              inp["tp"], inp["kc"], inp["Fy_col"],
                              inp.get("at_column_end", False))
    checks.append(cwy)

    N_bearing = inp["db_tf"] + 2.0 * inp["tp"]
    # A tensile axial force genuinely relieves the compression flange,
    # but the source workbook does not take that credit and neither
    # does this page: the compression checks use at least the pure
    # moment couple. Axial load in a moment frame reverses.
    Ff_comp_check = max(F["Ff_compression_kN"], F["Ff_moment_kN"])
    cwc = column_web_crippling(Ff_comp_check, inp["twc"],
                               inp["tfc"], inp["dc"], inp["Fy_col"],
                               N_bearing, inp.get("at_column_end", False))
    if cwc:
        checks.append(cwc)

    cwb = None
    if inp.get("beams_both_sides", False):
        cwb = column_web_buckling(Ff_comp_check, inp["twc"],
                                  inp["dc"], inp["tfc"], inp["Fy_col"])
        if cwb:
            checks.append(cwb)

    pz = panel_zone_shear(inp["Mf"], inp.get("Vf_col", 0.0), inp["dc"],
                          inp["twc"], inp["tfc"],
                          inp["db_d"] - inp["db_tf"], inp["Fy_col"],
                          inp.get("tdp", 0.0))
    checks.append(pz)

    # stiffeners sized on whichever column check fell short
    deficits = []
    for c in (cfb, cwy, cwc, cwb):
        if c and c["demand"] > c["capacity"]:
            deficits.append(c["demand"] - c["capacity"])
    stf = stiffener_design(deficits, inp["bfc"], inp["twc"], inp["tfc"],
                           inp["dc"], inp["kc"], inp["Fy_plate"])
    checks.append(stf)

    det = detailing(inp["bp"], inp["db_bf"], inp["bfc"], inp["g"],
                    inp["pf_i"], db, inp["tp"], d_hole, b)

    # The stiffener entry is a sizing output, not a pass/fail check, so
    # it is kept out of the governing search: it would otherwise always
    # sit at exactly 1.000 and pretend to govern.
    real = [c for c in checks if c["key"] not in ("stiffeners",)]
    gov = max(real, key=lambda c: c["ratio"]) if real else None

    return {
        "bolt": b, "forces": F, "beam": beam, "checks": checks,
        "detailing": det, "governing": gov,
        # Strength and buildability are reported separately. A
        # connection can be perfectly strong and still be undetailable,
        # and rolling the two into one verdict hides which is which.
        "overall_strength": all(c["ok"] for c in real),
        "overall_detailing": det["all_ok"],
        "overall": all(c["ok"] for c in real) and det["all_ok"],
        "legacy": legacy_1994(b, inp["n_tension"], inp["n_shear"],
                              F["Ff_tension_kN"], inp["Vf"]),
        "geometry": {"h0": h0, "h1": h1, "d_hole": d_hole,
                     "N_bearing": N_bearing},
        "verify_list": [c for c in checks if c["confidence"] == "verify"],
    }


# ======================================================================
# 10 - SELF TEST AGAINST THE SOURCE WORKBOOK
# ======================================================================

def selftest_alpha_m():
    """Reproduce the alpha_m calculation from the CSA workbook.

    The workbook was last saved with a worked case in it, and its
    cached results are reproduced here as a regression test. If this
    function stops returning "pass", something in alpha_m_thickness has
    drifted away from the method the workbook implements, and the
    comparison shown on the page is no longer trustworthy.

    Workbook case: W250x?? column 203 x 203 x 11, beam 266 deep,
    Mf = 50 kN m, Tf = 30 kN, 3/4 in bolts, pf = 44, g = 130,
    bp entered 203.2 and capped to 173.4.

    Run it with:   python3 -c "import moment_connection as m;
                               print(m.selftest_alpha_m())"
    """
    expected = {"pe": 33.5815, "Ca": 1.3648, "Cb": 0.9239,
                "alpha_m": 1.4790, "Meu_kNm": 2.6401, "tp_req": 15.0187}

    d, tw, bf, tf = 266.0, 7.6, 148.0, 13.0
    bfc = 203.0
    Ffu_N = 212628.458498024          # the workbook's own flange force

    res = alpha_m_thickness(
        bp=203.2, bf=bf, tf=tf, d=d, tw=tw, pf=44.0, db=19.05,
        w_weld=8.0, Fy_beam=345.0, Fyp=300.0,
        Ff_tension_kN=Ffu_N / 1.0e3, tp=25.4,
        bolt_grade_a325=True, bfc=bfc)

    got = {"pe": res["pe_mm"], "Ca": res["Ca"], "Cb": res["Cb"],
           "alpha_m": res["alpha_m"], "Meu_kNm": res["Meu_kNm"],
           "tp_req": res["tp_req_mm"]}

    lines, ok = [], True
    for k in expected:
        e, g = expected[k], got[k]
        good = abs(g - e) <= max(2.0e-4 * abs(e), 5.0e-4)
        ok = ok and good
        lines.append("  %-10s workbook %12.4f   engine %12.4f   %s"
                     % (k, e, g, "match" if good else "DRIFT"))
    return ("pass" if ok else "FAIL") + "\n" + "\n".join(lines)
