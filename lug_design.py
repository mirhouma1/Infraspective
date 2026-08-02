"""
lug_design.py

CSA S16 lifting lug design engine. Pure Python, no Streamlit, no numpy,
so it can be unit tested and reused.

Traced from lifting_lug_PM630-05A_r01.xlsm, sheet "Lifting Lug Design".
Every clause reference below is the one written on the source sheet.

Check groups
------------
A  Design forces                 TR-45-SPC-00-021-01 H2.1, H2.2, H3.1.1
B  Lug to cap plate weld         cl 13.13.2.2 (a) base metal, (b) weld metal
C  Lug plate at cap plate        cl 13.9(a), 13.5(b), 13.2(a)(i)
D  Cap plate and bolt prying     CISC Handbook 9th ed p3-20, eq 1 to 7
E  Pin                           cl 13.12.1.1(b), 13.10(c), 13.11(a)(ii)

Deviation from the source workbook
----------------------------------
Cell J142 is labelled  a' = a + Db/2  but is written  =J139-K22/2, that is
a' = a - Db/2. The label follows the CISC prying formulation and the
formula does not. This module uses the CISC form, a' = a + Db/2, and also
applies the a <= 1.25 b limit that goes with it.

The effect is confined to the connection capacity check: a larger a'
raises alpha and therefore Fr, so the unity check falls from 0.315 to
0.301 on the source geometry. The bolt prying check is unchanged there
because alpha computes negative and is clamped to zero, and b'/a' only
enters once alpha is positive.

Set prying_mode="sheet" to reproduce the workbook exactly instead.
"""

import math

GRAVITY = 9.807          # kN per tonne
LOAD_FACTOR = 1.30       # service to factored


def _uc(demand, capacity):
    """Unity check, guarding a zero or missing capacity."""
    if capacity in (None, 0) or capacity <= 0:
        return None
    return demand / capacity


def _verdict(uc):
    if uc is None:
        return "n/a"
    return "OK" if uc < 1.0 else "NG"


# ---------------------------------------------------------------------
# A. Design forces
# ---------------------------------------------------------------------
def design_forces(T_tons, LDf, If, Sf, H2, tp1, shear_ratio=0.10):
    """Service sling load in tonnes to factored forces in kN and kN-m."""
    total_factor = max(float(LDf), float(If) * float(Sf))
    Ts_tons = float(T_tons) * total_factor
    Tf = Ts_tons * LOAD_FACTOR * GRAVITY

    Vfx = shear_ratio * Tf
    Vfy = shear_ratio * Tf
    Rf = math.sqrt(Vfx ** 2 + Vfy ** 2)

    return {
        "total_factor": total_factor,
        "Ts_tons": Ts_tons,
        "Tf_kN": Tf,
        "Vfx_kN": Vfx,
        "Vfy_kN": Vfy,
        "Rf_kN": Rf,
        # at the bottom of the lug, where it meets the cap plate
        "Mfx_lug_kNm": H2 * Vfy / 1000.0,
        "Mfy_lug_kNm": H2 * Vfx / 1000.0,
        # at the top of the beam, one cap plate thickness lower down
        "Mfx_beam_kNm": (H2 + tp1) * Vfy / 1000.0,
        "Mfy_beam_kNm": (H2 + tp1) * Vfx / 1000.0,
    }


# ---------------------------------------------------------------------
# B. Lug to cap plate weld
#
# Two fillet welds, one each side of the lug plate, running the full
# length L2. The same stress assembly is used twice: once on the weld
# throat with the directional strength increase of cl 13.13.2.2(b), and
# once on the fusion face with the plain base metal limit of (a).
# ---------------------------------------------------------------------
def _weld_stresses(leg, L2, tp2, Tf, Rf, Mfx, Mfy):
    A = 2.0 * leg * L2
    Ixx = 2.0 * leg * L2 ** 3 / 12.0
    Sxx = Ixx / (L2 / 2.0)
    Iyy = 2.0 * L2 * leg ** 3 / 12.0 + A * ((leg + tp2) / 2.0) ** 2
    Syy = Iyy / (leg + tp2 / 2.0)

    sigma1 = Mfy / Syy * 1e6 + Mfx / Sxx * 1e6      # kN-m and mm3 to MPa
    sigma2 = Tf / A * 1000.0
    sigma_n = sigma1 + sigma2
    tau = Rf / A * 1000.0
    sigma_t = math.sqrt(sigma_n ** 2 + tau ** 2)
    theta = math.degrees(math.atan2(sigma_n, tau)) if tau > 0 else 90.0

    return {
        "a_mm": leg, "A_mm2": A, "Ixx_mm4": Ixx, "Sxx_mm3": Sxx,
        "Iyy_mm4": Iyy, "Syy_mm3": Syy,
        "sigma1_MPa": sigma1, "sigma2_MPa": sigma2,
        "sigma_n_MPa": sigma_n, "tau_MPa": tau,
        "sigma_t_MPa": sigma_t, "theta_deg": theta,
    }


def weld_checks(w1, L2, tp2, Xu, Fup, phiw, Tf, Rf, Mfx, Mfy):
    metal = _weld_stresses(0.707 * w1, L2, tp2, Tf, Rf, Mfx, Mfy)
    th = math.radians(metal["theta_deg"])
    metal["sigma_all_MPa"] = 0.67 * phiw * Xu * (1.0 + 0.5 * math.sin(th) ** 1.5)
    metal["uc"] = _uc(metal["sigma_t_MPa"], metal["sigma_all_MPa"])
    metal["verdict"] = _verdict(metal["uc"])
    metal["clause"] = "cl 13.13.2.2(b)"

    base = _weld_stresses(w1, L2, tp2, Tf, Rf, Mfx, Mfy)
    base["sigma_all_MPa"] = 0.67 * phiw * Fup
    base["uc"] = _uc(base["sigma_t_MPa"], base["sigma_all_MPa"])
    base["verdict"] = _verdict(base["uc"])
    base["clause"] = "cl 13.13.2.2(a)"

    return {"weld_metal": metal, "base_metal": base}


# ---------------------------------------------------------------------
# C. Lug plate at the cap plate, combined axial and biaxial bending
# ---------------------------------------------------------------------
def lug_section_check(L2, tp2, Fy, phi, Tf, Mfx, Mfy):
    A = L2 * tp2
    Sxx = tp2 * L2 ** 2 / 6.0
    Syy = tp2 ** 2 * L2 / 6.0

    Mrx = phi * Sxx * Fy / 1e6
    Mry = phi * Syy * Fy / 1e6
    Tr = phi * A * Fy / 1000.0

    uc = Tf / Tr + Mfx / Mrx + Mfy / Mry
    return {
        "A_mm2": A, "Sxx_mm3": Sxx, "Syy_mm3": Syy,
        "Mrx_kNm": Mrx, "Mry_kNm": Mry, "Tr_kN": Tr,
        "uc": uc, "verdict": _verdict(uc), "clause": "cl 13.9(a)",
    }


# ---------------------------------------------------------------------
# D. Cap plate thickness and bolt prying
# ---------------------------------------------------------------------
def prying_checks(W1, L1, g, tp1, tp2, Db, Nrow, Fyp, Fub, phi, phib, Tf,
                  mode="cisc"):
    a = (W1 - g) / 2.0
    b = (W1 - tp2) / 2.0 - a
    d_hole = Db + 2.0

    if mode == "sheet":
        a_eff = a
        a_p = a - Db / 2.0
    else:
        # CISC caps the outer distance that can be mobilised at 1.25b
        a_eff = min(a, 1.25 * b)
        a_p = a_eff + Db / 2.0
    b_p = b - Db / 2.0

    p = L1 / Nrow
    delta = 1.0 - d_hole / p
    K = 4.0 * b_p * 1e3 / (phi * p * Fyp)

    n_bolts = 2.0 * Nrow
    Pfb = Tf / n_bolts

    t_min = math.sqrt(K * Pfb / (1.0 + delta * 1.0))
    t_max = math.sqrt(K * Pfb / (1.0 + delta * 0.0))

    Trb = 0.75 * phib * (math.pi * Db ** 2 / 4.0) * Fub / 1000.0

    alpha_conn = (K * Trb / tp1 ** 2 - 1.0) * (a_p / (delta * (a_p + b_p)))
    alpha_conn_used = min(max(alpha_conn, 0.0), 1.0)
    Fr = (tp1 ** 2 / K) * (1.0 + delta * alpha_conn_used) * n_bolts
    uc_conn = _uc(Tf, Fr)

    alpha_bolt = (K * Pfb / tp1 ** 2 - 1.0) / delta
    alpha_bolt_used = min(max(alpha_bolt, 0.0), 1.0)
    Tfb = Pfb * (1.0 + (b_p / a_p) * delta * alpha_bolt_used
                 / (1.0 + delta * alpha_bolt_used))
    uc_bolt = _uc(Tfb, Trb)

    return {
        "mode": mode,
        "a_mm": a, "a_eff_mm": a_eff, "b_mm": b,
        "d_hole_mm": d_hole, "a_prime_mm": a_p, "b_prime_mm": b_p,
        "p_mm": p, "delta": delta, "K": K,
        "n_bolts": n_bolts, "Pfb_kN": Pfb,
        "t_min_mm": t_min, "t_max_mm": t_max, "tp1_mm": tp1,
        "plate_verdict": "OK" if t_max < tp1 else "NG",
        "Trb_kN": Trb,
        "alpha_conn": alpha_conn, "alpha_conn_used": alpha_conn_used,
        "Fr_kN": Fr, "uc_conn": uc_conn, "conn_verdict": _verdict(uc_conn),
        "alpha_bolt": alpha_bolt, "alpha_bolt_used": alpha_bolt_used,
        "Tfb_kN": Tfb, "uc_bolt": uc_bolt, "bolt_verdict": _verdict(uc_bolt),
        "clause": "CISC Handbook 9th ed p3-20",
    }


# ---------------------------------------------------------------------
# E. Pin
# ---------------------------------------------------------------------
def pin_checks(Dpin, Dhole, Dcheekp, H1, tp2, tp3, Fypin, Fupin, Fup,
               phi, phib, phibr, Tf, n=1.0, m=2.0):
    Apin = Dpin ** 2 * math.pi / 4.0
    Vr1 = 0.66 * phib * n * m * Apin * Fypin / 1000.0

    t_bear = 2.0 * tp3 + tp2
    Vr2 = 3.0 * phibr * t_bear * Dpin * n * Fupin / 1000.0

    Vr3 = (2.0 * 0.60 * phi
           * ((Dcheekp / 2.0 - Dhole / 2.0) * t_bear
              + (H1 - Dcheekp / 2.0) * tp2) * Fup / 1000.0)

    Vr = min(Vr1, Vr2, Vr3)
    which = "shear" if Vr == Vr1 else ("bearing" if Vr == Vr2 else "tear-out")
    uc = _uc(Tf, Vr)

    return {
        "Apin_mm2": Apin, "t_bearing_mm": t_bear,
        "Vr1_kN": Vr1, "Vr2_kN": Vr2, "Vr3_kN": Vr3,
        "Vr_kN": Vr, "governing": which, "Vf_kN": Tf,
        "uc": uc, "verdict": _verdict(uc),
        "clauses": "cl 13.12.1.1(b), 13.10(c), 13.11(a)(ii)",
    }


# ---------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------
def design_lug(inp, prying_mode="cisc"):
    """inp is a flat dict of the input panel. Returns every check group
    plus a summary naming the governing one."""
    f = design_forces(inp["T_tons"], inp["LDf"], inp["If"], inp["Sf"],
                      inp["H2"], inp["tp1"])

    welds = weld_checks(inp["w1"], inp["L2"], inp["tp2"], inp["Xu"],
                        inp["Fup"], inp["phiw"], f["Tf_kN"], f["Rf_kN"],
                        f["Mfx_lug_kNm"], f["Mfy_lug_kNm"])

    lug = lug_section_check(inp["L2"], inp["tp2"], inp["Fyp"], inp["phi"],
                            f["Tf_kN"], f["Mfx_lug_kNm"], f["Mfy_lug_kNm"])

    pry = prying_checks(inp["W1"], inp["L1"], inp["g"], inp["tp1"],
                        inp["tp2"], inp["Db"], inp["Nrow"], inp["Fyp"],
                        inp["Fub"], inp["phi"], inp["phib"], f["Tf_kN"],
                        mode=prying_mode)

    pin = pin_checks(inp["Dpin"], inp["Dhole"], inp["Dcheekp"], inp["H1"],
                     inp["tp2"], inp["tp3"], inp["Fypin"], inp["Fupin"],
                     inp["Fup"], inp["phi"], inp["phib"], inp["phibr"],
                     f["Tf_kN"])

    checks = [
        ("Weld metal", welds["weld_metal"]["uc"], welds["weld_metal"]["verdict"]),
        ("Weld base metal", welds["base_metal"]["uc"], welds["base_metal"]["verdict"]),
        ("Lug plate section", lug["uc"], lug["verdict"]),
        ("Connection capacity", pry["uc_conn"], pry["conn_verdict"]),
        ("Bolt with prying", pry["uc_bolt"], pry["bolt_verdict"]),
        ("Pin", pin["uc"], pin["verdict"]),
    ]
    rated = [c for c in checks if c[1] is not None]
    gov = max(rated, key=lambda c: c[1]) if rated else ("none", None, "n/a")

    return {
        "forces": f, "welds": welds, "lug": lug, "prying": pry, "pin": pin,
        "checks": checks,
        "governing_name": gov[0], "governing_uc": gov[1],
        "overall": "OK" if all(c[2] == "OK" for c in checks) else "NG",
    }


# Source workbook geometry, kept as the regression case.
SOURCE_CASE = {
    "Dpin": 38.0, "Dhole": 45.0, "Dcheekp": 130.0,
    "Fypin": 300.0, "Fupin": 450.0,
    "tp1": 25.0, "L1": 300.0, "W1": 225.0,
    "Fyp": 300.0, "Fup": 450.0, "phi": 0.9, "phiw": 0.67,
    "Xu": 490.0, "w1": 8.0,
    "tp2": 25.0, "H1": 100.0, "H2": 100.0, "L2": 300.0, "tp3": 12.0,
    "Db": 24.0, "Nrow": 2.0, "s": 120.0, "g": 130.0,
    "Fub": 830.0, "phib": 0.8, "phibr": 0.67,
    "T_tons": 6.21, "If": 1.2, "Sf": 1.4, "LDf": 3.0,
}


if __name__ == "__main__":
    for mode in ("sheet", "cisc"):
        r = design_lug(SOURCE_CASE, prying_mode=mode)
        print("=== prying_mode =", mode, "===")
        print("Tf          %.4f kN" % r["forces"]["Tf_kN"])
        for name, uc, v in r["checks"]:
            print("  %-22s %s  %s"
                  % (name, "  n/a" if uc is None else "%.4f" % uc, v))
        print("  governing: %s at %.4f"
              % (r["governing_name"], r["governing_uc"]))
