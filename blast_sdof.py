"""
blast_sdof.py

Single degree of freedom blast response engine.

This is the calculation engine behind pages/11_Blast_SDOF.py. It owns
every number on that page and every number the 3D viewer plays back, so
the animation and the arithmetic can never tell different stories.

What this implements
--------------------
The SDOF method of Chapter 6 of the ASCE report on blast resistant
design of petrochemical facilities, which is itself a presentation of
the method set out in TM 5-856, Biggs and UFC 3-340-02:

    a real member with distributed mass and load is replaced by a single
    mass on a single spring, chosen so that the equivalent system has
    the same kinetic energy, the same strain energy and the same work
    done by the applied load as the real member deflecting in an assumed
    shape. The factors that do the replacing are the transformation
    factors K_L and K_M.

Sequence:

    1  dynamic material strength      F_dy = SIF x DIF x Fy
    2  section capacity               Mp = F_dy Z
    3  resistance function            R(y), elastic then plastic, from
                                      the transformation tables
    4  equivalent system              K_LM M ybardotdot + R(y) = F(t)
    5  natural period                 t_n = 2 pi sqrt(K_LM M / K_E)
    6  time integration               central difference, the recurrence
                                      used by Biggs, or Newmark constant
                                      average acceleration
    7  response                       y_max, ductility mu = y_max / y_E
    8  dynamic reactions              V(t) = c1 R(t) + c2 F(t)
    9  closed form cross checks       the impulsive and quasi static
                                      asymptotes and the ASCE Manual 42
                                      transition formula

Units
-----
Everything inside this module is SI base: newtons, metres, kilograms,
seconds. Conversion happens at the page boundary, once, so there is
exactly one place where a factor of 1000 can go wrong.

On the transformation tables
----------------------------
The tabulated factors originate in TM 5-856, a US Army technical manual
in the public domain, and are reproduced in Biggs, in UFC 3-340-02 and
in Tables 6.1 to 6.3 of the ASCE report. Only the simply supported and
fixed end tables are encoded here. The simple-fixed table is deliberately
NOT encoded: its resistance column could not be read with confidence
from the scan available, and a transformation factor guessed from a
blurred table is worse than an honest gap.

ASCII only. Straight quotes only. No markdown inside code.
"""

import math

G_ACC = 9.807
E_STEEL = 200.0e9          # Pa
RHO_STEEL = 7850.0         # kg/m3


# ---------------------------------------------------------------------
# 1. Transformation tables
#
# Each entry describes one support condition and one load case. The
# resistance function is built from `stages`, in order, each of which
# carries the stiffness that applies over it and the resistance at which
# it ends. A single stage is a bilinear resistance function; two stages
# is the trilinear elastic, elastic-plastic, plastic form that a fixed
# end member under uniform load actually follows, because the support
# hinges form before the midspan one.
#
# reaction coefficients are (c1, c2) in V = c1 R + c2 F, taken from the
# Dynamic Reaction column of the same table row.
# ---------------------------------------------------------------------
CASES = {
    ("simple", "uniform"): {
        "label": "Simply supported, uniform load",
        "table": "Table 6.1",
        "stages": [
            {"name": "elastic", "KL": 0.64, "KM": 0.50, "KLM": 0.78,
             "K": lambda EI, L: 384.0 * EI / (5.0 * L ** 3),
             "R": lambda Mpc, Mps, L: 8.0 * Mpc / L,
             "V": (0.39, 0.11)},
        ],
        "plastic": {"KL": 0.50, "KM": 0.33, "KLM": 0.66, "V": (0.38, 0.12)},
        "hinges": lambda L: [0.5 * L],
        "shape_elastic": "ss_uniform",
        "note": "The elastic shape is the deflected shape of a simply "
                "supported beam under uniform load. One hinge forms, at "
                "midspan, and the member is a mechanism the moment it "
                "does.",
    },
    ("simple", "point"): {
        "label": "Simply supported, point load at midspan",
        "table": "Table 6.1",
        "stages": [
            {"name": "elastic", "KL": 1.00, "KM": 0.49, "KLM": 0.49,
             "K": lambda EI, L: 48.0 * EI / L ** 3,
             "R": lambda Mpc, Mps, L: 4.0 * Mpc / L,
             "V": (0.78, -0.28)},
        ],
        "plastic": {"KL": 1.00, "KM": 0.33, "KLM": 0.33, "V": (0.75, -0.25)},
        "hinges": lambda L: [0.5 * L],
        "shape_elastic": "ss_point",
        "note": "The uniform mass factors are used. If the mass is "
                "genuinely lumped at the load point, K_M is 1.00 in both "
                "ranges and K_LM follows.",
    },
    ("simple", "third"): {
        "label": "Simply supported, two point loads at the third points",
        "table": "Table 6.1",
        "stages": [
            {"name": "elastic", "KL": 0.87, "KM": 0.52, "KLM": 0.60,
             "K": lambda EI, L: 56.4 * EI / L ** 3,
             "R": lambda Mpc, Mps, L: 6.0 * Mpc / L,
             "V": (0.525, -0.025)},
        ],
        "plastic": {"KL": 1.00, "KM": 0.56, "KLM": 0.56, "V": (0.52, -0.02)},
        "hinges": lambda L: [L / 3.0, 2.0 * L / 3.0],
        "shape_elastic": "ss_third",
        "note": "Two hinges form, one under each load, and the middle "
                "third translates without bending.",
    },
    ("fixed", "uniform"): {
        "label": "Fixed both ends, uniform load",
        "table": "Table 6.2",
        "stages": [
            {"name": "elastic", "KL": 0.53, "KM": 0.41, "KLM": 0.77,
             "K": lambda EI, L: 384.0 * EI / L ** 3,
             "R": lambda Mpc, Mps, L: 12.0 * Mps / L,
             "V": (0.36, 0.14)},
            {"name": "elastic-plastic", "KL": 0.64, "KM": 0.50, "KLM": 0.78,
             "K": lambda EI, L: 384.0 * EI / (5.0 * L ** 3),
             "R": lambda Mpc, Mps, L: 8.0 * (Mps + Mpc) / L,
             "V": (0.39, 0.11)},
        ],
        "plastic": {"KL": 0.50, "KM": 0.33, "KLM": 0.66, "V": (0.38, 0.12)},
        "hinges": lambda L: [0.0, 0.5 * L, L],
        "shape_elastic": "fx_uniform",
        "note": "Under uniform load the support moment is twice the "
                "midspan moment, so the support hinges form first and "
                "the member spends a while as a propped system before "
                "the midspan hinge turns it into a mechanism. That "
                "middle stage is the elastic-plastic range.",
    },
    ("fixed", "point"): {
        "label": "Fixed both ends, point load at midspan",
        "table": "Table 6.2",
        "stages": [
            {"name": "elastic", "KL": 1.00, "KM": 0.37, "KLM": 0.37,
             "K": lambda EI, L: 192.0 * EI / L ** 3,
             "R": lambda Mpc, Mps, L: 4.0 * (Mps + Mpc) / L,
             "V": (0.71, -0.21)},
        ],
        "plastic": {"KL": 1.00, "KM": 0.33, "KLM": 0.33, "V": (0.75, -0.25)},
        "hinges": lambda L: [0.0, 0.5 * L, L],
        "shape_elastic": "fx_point",
        "note": "With a central point load the support and midspan "
                "moments are equal, so for a prismatic member all three "
                "hinges form together and there is no elastic-plastic "
                "range. That is why Table 6.2 lists only two rows for "
                "this case.",
    },
}

SUPPORTS = {"simple": "Simply supported", "fixed": "Fixed both ends"}
LOADCASES = {"uniform": "Uniform pressure",
             "point": "Point load at midspan",
             "third": "Point loads at the third points"}


def case_key(support, loadcase):
    return (support, loadcase)


def available_cases():
    return sorted(CASES.keys())


# ---------------------------------------------------------------------
# 2. Resistance function
# ---------------------------------------------------------------------
def resistance_function(EI, L, Mpc, Mps, case):
    """Build the multi-linear resistance function.

    Returns the breakpoints as lists of deflection and resistance, the
    ultimate resistance R_u, the equivalent elastic deflection y_E and
    the equivalent elastic stiffness K_E = R_u / y_E.

    y_E is the deflection at which the member becomes a mechanism, so
    for a trilinear function it is the end of the elastic-plastic range,
    not the end of the elastic one. That is the deflection ductility is
    measured against, and it is what makes the equivalent bilinear
    system used for the dynamics have the same area under it up to R_u.
    """
    ys, Rs, stages = [0.0], [0.0], []
    y, R_prev = 0.0, 0.0
    for st in case["stages"]:
        K = st["K"](EI, L)
        R_end = st["R"](Mpc, Mps, L)
        dR = R_end - R_prev
        dy = dR / K if K > 0 else 0.0
        y += dy
        ys.append(y)
        Rs.append(R_end)
        stages.append({"name": st["name"], "K": K, "R_end": R_end,
                       "y_end": y, "V": st["V"],
                       "KL": st["KL"], "KM": st["KM"], "KLM": st["KLM"]})
        R_prev = R_end

    Ru = Rs[-1]
    yE = ys[-1]
    KE = Ru / yE if yE > 0 else 0.0
    return {"y_pts": ys, "R_pts": Rs, "stages": stages,
            "Ru_N": Ru, "yE_m": yE, "KE_Npm": KE,
            "plastic": case["plastic"]}


# ---------------------------------------------------------------------
# 3. Blast load, the straight line pulse of Section 3.3.6
# ---------------------------------------------------------------------
def force_at(t, Fo, td):
    """Triangular pulse: peak at t = 0, linear to zero at t = td."""
    if td <= 0.0 or t >= td:
        return 0.0
    if t < 0.0:
        return 0.0
    return Fo * (1.0 - t / td)


# ---------------------------------------------------------------------
# 4. Time integration
#
# Two methods, on purpose. They are solving the same equation and should
# land on the same answer; when they do not, the time step is too coarse
# and that is worth seeing rather than hiding.
#
#   central     y_{i+1} = 2 y_i - y_{i-1} + a_i dt^2, the recurrence used
#               by Biggs and in the appendix of the ASCE report. Explicit,
#               transparent, conditionally stable, needs dt < t_n / pi.
#
#   newmark     constant average acceleration, gamma = 1/2, beta = 1/4,
#               with fixed point iteration on the nonlinear spring.
#               Unconditionally stable for a linear system.
# ---------------------------------------------------------------------
class ElastoPlasticSpring(object):
    """Elastic, perfectly plastic spring with unloading.

    Unloading from the plastic plateau runs back down a line of slope
    K_E, which is what lets the member spring back and go into reverse.
    Rebound is bounded by -R_u, since the member has the same capacity
    the other way, and rebound is one of the four things the analysis is
    supposed to deliver.
    """

    def __init__(self, KE, Ru):
        self.KE = KE
        self.Ru = Ru
        self.yp = 0.0            # plastic offset accumulated so far
        self.yielded = False
        self.first_yield_t = None

    def R(self, y, t=None):
        if self.KE <= 0.0:
            return 0.0
        R = self.KE * (y - self.yp)
        if R > self.Ru:
            self.yp = y - self.Ru / self.KE
            R = self.Ru
            if not self.yielded:
                self.yielded = True
                self.first_yield_t = t
        elif R < -self.Ru:
            self.yp = y + self.Ru / self.KE
            R = -self.Ru
            if not self.yielded:
                self.yielded = True
                self.first_yield_t = t
        return R

    def probe(self, y):
        """Resistance at y without committing any plastic flow."""
        if self.KE <= 0.0:
            return 0.0
        return max(-self.Ru, min(self.Ru, self.KE * (y - self.yp)))


def integrate(Me, res, Fo, td, dt, t_end, method="central"):
    """Solve Me ybardotdot + R(y) = F(t) from rest.

    Me is the equivalent mass K_LM M. Returns the full history, which is
    what both the tables and the animation are drawn from.
    """
    KE, Ru = res["KE_Npm"], res["Ru_N"]
    spring = ElastoPlasticSpring(KE, Ru)

    n = max(2, int(round(t_end / dt)))
    T = [0.0] * (n + 1)
    Y = [0.0] * (n + 1)
    V = [0.0] * (n + 1)
    A = [0.0] * (n + 1)
    R = [0.0] * (n + 1)
    F = [0.0] * (n + 1)

    F[0] = force_at(0.0, Fo, td)
    R[0] = spring.R(0.0, 0.0)
    A[0] = (F[0] - R[0]) / Me if Me > 0 else 0.0

    if method == "central":
        y_prev = 0.0 - 0.0 * dt + 0.5 * A[0] * dt * dt   # y at -dt, from rest
        for i in range(n):
            T[i + 1] = (i + 1) * dt
            y_next = 2.0 * Y[i] - y_prev + A[i] * dt * dt
            Y[i + 1] = y_next
            V[i] = (y_next - y_prev) / (2.0 * dt)
            F[i + 1] = force_at(T[i + 1], Fo, td)
            R[i + 1] = spring.R(y_next, T[i + 1])
            A[i + 1] = (F[i + 1] - R[i + 1]) / Me if Me > 0 else 0.0
            y_prev = Y[i]
        V[n] = (Y[n] - Y[n - 1]) / dt
    else:
        # Newmark, constant average acceleration
        beta, gamma = 0.25, 0.5
        for i in range(n):
            t1 = (i + 1) * dt
            T[i + 1] = t1
            F[i + 1] = force_at(t1, Fo, td)
            # predictor, then a few passes on the nonlinear resistance
            y1 = Y[i] + dt * V[i] + dt * dt * (0.5 - beta) * A[i]
            a1 = A[i]
            for _ in range(30):
                y_try = y1 + beta * dt * dt * a1
                R_try = spring.probe(y_try)
                a_new = (F[i + 1] - R_try) / Me if Me > 0 else 0.0
                if abs(a_new - a1) <= 1.0e-10 * (1.0 + abs(a1)):
                    a1 = a_new
                    break
                a1 = a_new
            Y[i + 1] = y1 + beta * dt * dt * a1
            R[i + 1] = spring.R(Y[i + 1], t1)          # commit plastic flow
            A[i + 1] = (F[i + 1] - R[i + 1]) / Me if Me > 0 else 0.0
            V[i + 1] = V[i] + dt * ((1.0 - gamma) * A[i] + gamma * A[i + 1])

    return {"t": T, "y": Y, "v": V, "a": A, "R": R, "F": F,
            "yielded": spring.yielded, "t_yield": spring.first_yield_t}


# ---------------------------------------------------------------------
# 5. Dynamic reactions, Section 6.4.6
#
# The spring force in the SDOF system is NOT the support reaction. The
# reaction has to account for how the inertia force is distributed along
# the real member, which is what the coefficients in the Dynamic
# Reaction column of the tables encode.
# ---------------------------------------------------------------------
def reactions(hist, res, tol=1.0e-9):
    Ru = res["Ru_N"]
    el = res["stages"][-1]["V"]
    pl = res["plastic"]["V"]
    out = []
    for R, F in zip(hist["R"], hist["F"]):
        if abs(abs(R) - Ru) <= tol * max(1.0, Ru):
            c1, c2 = pl
            out.append(c1 * (Ru if R >= 0 else -Ru) + c2 * F)
        else:
            c1, c2 = el
            out.append(c1 * R + c2 * F)
    return out


# ---------------------------------------------------------------------
# 6. Closed form cross checks, Section 6.4.4
# ---------------------------------------------------------------------
def mu_impulsive(Io, f, Rm):
    """Eq 6.9. Valid when td / tn is small, under about 0.1, where only
    the impulse matters and the shape of the pulse does not."""
    if Rm <= 0.0:
        return None
    return 0.5 * ((Io * 2.0 * math.pi * f / Rm) ** 2 + 1.0)


def mu_quasi_static(Fo, Rm):
    """Eq 6.10. Valid when td / tn is large, over about 10, where the
    load may as well have been switched on and left there."""
    if Rm <= 0.0:
        return None
    r = Fo / Rm
    if r >= 1.0:
        return None                      # no bounded response
    return 1.0 / (2.0 * (1.0 - r))


def mu_manual42(Fo, Rm, tau, lo=0.5, hi=1000.0):
    """Eq 6.11, the ASCE Manual 42 transition formula, solved for mu.

    F_o/R_m = sqrt(2 mu - 1) / (pi tau)
              + (2 mu - 1) tau / (2 mu (tau + 0.7))

    which tends to the impulsive relation of Eq 6.9 as tau goes to zero
    and to the quasi static relation of Eq 6.10 as tau grows.
    The right hand side rises monotonically with mu, so a bisection
    finds the ductility that matches the demand. The chapter quotes it
    as good to about 5 percent across the whole range, which makes it a
    fair independent check on the time integration.
    """
    if Rm <= 0.0 or tau <= 0.0:
        return None
    target = Fo / Rm

    def rhs(mu):
        if mu <= 0.5:
            return 0.0
        # The tau in the numerator of the second term is not decoration.
        # Without it the term dies away as tau grows instead of tending
        # to 1 - 1/(2 mu), and the formula stops reproducing the quasi
        # static asymptote of Eq 6.10 entirely. Both limits are checked
        # in the test suite for exactly this reason.
        return (math.sqrt(2.0 * mu - 1.0) / (math.pi * tau)
                + (2.0 * mu - 1.0) * tau / (2.0 * mu * (tau + 0.7)))

    if rhs(hi) < target:
        return None
    if rhs(lo) > target:
        return lo
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if rhs(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------
# 7. Top level
# ---------------------------------------------------------------------
def analyse(inp):
    """Run the whole sequence. inp is SI base throughout.

    Required keys:
        L_m, EI_Nm2, Z_m3, A_m2, support, loadcase
        Fy_Pa, SIF, DIF
        Po_Pa, td_s, b_m, mass_sup_kgm2
        method, dt_ratio, n_periods
    """
    L = float(inp["L_m"])
    support = inp.get("support", "simple")
    loadcase = inp.get("loadcase", "uniform")
    case = CASES[(support, loadcase)]

    EI = float(inp["EI_Nm2"])
    Z = float(inp["Z_m3"])
    A = float(inp["A_m2"])
    b = float(inp.get("b_m", 1.0))

    # 1. dynamic material strength, the Chapter 5 quantities
    Fy = float(inp["Fy_Pa"])
    SIF = float(inp.get("SIF", 1.0))
    DIF = float(inp.get("DIF", 1.0))
    Fdy = SIF * DIF * Fy

    # 2. section capacity. For a prismatic member the support and
    #    midspan capacities are the same section, so Mps = Mpc.
    Mpc = Fdy * Z
    Mps = Mpc

    # 3. resistance function
    res = resistance_function(EI, L, Mpc, Mps, case)

    # 4. mass and the equivalent system
    m_self = A * RHO_STEEL                     # kg per metre of member
    m_sup = float(inp.get("mass_sup_kgm2", 0.0)) * b
    m_line = m_self + m_sup
    M = m_line * L                             # kg
    KLM_el = case["stages"][0]["KLM"]
    KLM_pl = case["plastic"]["KLM"]
    KLM = float(inp["KLM"]) if inp.get("KLM") else 0.5 * (KLM_el + KLM_pl)
    Me = KLM * M

    # 5. period
    KE = res["KE_Npm"]
    tn = 2.0 * math.pi * math.sqrt(Me / KE) if KE > 0 and Me > 0 else 0.0
    f = 1.0 / tn if tn > 0 else 0.0

    # 6. load
    Po = float(inp["Po_Pa"])
    td = float(inp["td_s"])
    Fo = Po * b * L if loadcase == "uniform" else Po * b * L
    Io = 0.5 * Fo * td                          # impulse of the pulse, N s

    # 7. integration
    ratio = float(inp.get("dt_ratio", 200.0))
    base = min(tn, td) if (tn > 0 and td > 0) else max(tn, td)
    dt = base / ratio if base > 0 else 1.0e-5
    n_per = float(inp.get("n_periods", 3.0))
    t_end = max(n_per * tn, 2.0 * td, 4.0 * dt) if tn > 0 else 2.0 * td
    method = inp.get("method", "central")
    hist = integrate(Me, res, Fo, td, dt, t_end, method=method)
    hist["V"] = reactions(hist, res)

    # 8. response quantities
    y = hist["y"]
    ymax = max(y)
    imax = y.index(ymax)
    ymin = min(y)
    imin = y.index(ymin)
    yE = res["yE_m"]
    mu = ymax / yE if yE > 0 else None
    theta = math.degrees(math.atan(2.0 * ymax / L)) if L > 0 else None
    Vmax = max(abs(v) for v in hist["V"]) if hist["V"] else 0.0

    # 9. cross checks
    tau = td / tn if tn > 0 else None
    chk = {
        "tau": tau,
        "mu_impulsive": mu_impulsive(Io, f, res["Ru_N"]),
        "mu_quasi_static": mu_quasi_static(Fo, res["Ru_N"]),
        "mu_manual42": (mu_manual42(Fo, res["Ru_N"], tau)
                        if tau else None),
        "regime": ("impulsive" if tau is not None and tau < 0.1 else
                   "quasi-static" if tau is not None and tau > 10.0 else
                   "dynamic"),
    }
    if chk["mu_manual42"] and mu:
        chk["manual42_diff_pct"] = 100.0 * (chk["mu_manual42"] - mu) / mu
    else:
        chk["manual42_diff_pct"] = None

    stable = (dt < tn / math.pi) if tn > 0 else True

    return {
        "case": case, "support": support, "loadcase": loadcase,
        "material": {"Fy_Pa": Fy, "SIF": SIF, "DIF": DIF, "Fdy_Pa": Fdy},
        "section": {"EI_Nm2": EI, "Z_m3": Z, "A_m2": A,
                    "Mpc_Nm": Mpc, "Mps_Nm": Mps},
        "resistance": res,
        "mass": {"m_self_kgm": m_self, "m_sup_kgm": m_sup,
                 "m_line_kgm": m_line, "M_kg": M, "Me_kg": Me,
                 "KLM": KLM, "KLM_elastic": KLM_el, "KLM_plastic": KLM_pl},
        "dynamics": {"tn_s": tn, "f_Hz": f, "dt_s": dt, "t_end_s": t_end,
                     "method": method, "stable": stable},
        "load": {"Po_Pa": Po, "td_s": td, "Fo_N": Fo, "Io_Ns": Io,
                 "b_m": b, "L_m": L},
        "history": hist,
        "response": {"ymax_m": ymax, "tmax_s": hist["t"][imax],
                     "ymin_m": ymin, "tmin_s": hist["t"][imin],
                     "yE_m": yE, "mu": mu, "theta_deg": theta,
                     "Vmax_N": Vmax, "yielded": hist["yielded"],
                     "t_yield_s": hist["t_yield"]},
        "checks": chk,
    }


# ---------------------------------------------------------------------
# 8. Deflected shapes, phi(x), normalised to 1.0 at the control point
#
# These are the shape functions the transformation factors were derived
# from, which is why the model has to bend through them rather than
# through something that merely looks like a bent beam.
# ---------------------------------------------------------------------
def shape(name, xi):
    """xi runs 0 to 1 along the span."""
    x = min(1.0, max(0.0, xi))
    if name == "ss_uniform":
        # 16/5 (x - 2x^3 + x^4), the uniform load elastic curve
        return (16.0 / 5.0) * (x - 2.0 * x ** 3 + x ** 4)
    if name == "ss_point":
        # central point load, x <= 1/2 branch mirrored
        u = x if x <= 0.5 else 1.0 - x
        return (3.0 * u - 4.0 * u ** 3)
    if name == "ss_third":
        return _third_pt(x if x <= 0.5 else 1.0 - x)
    if name == "fx_uniform":
        return 16.0 * x ** 2 * (1.0 - x) ** 2
    if name == "fx_point":
        u = x if x <= 0.5 else 1.0 - x
        return 16.0 * u ** 2 * (0.75 - u)
    if name == "plastic":
        return 2.0 * x if x <= 0.5 else 2.0 * (1.0 - x)
    if name == "plastic_third":
        if x <= 1.0 / 3.0:
            return 3.0 * x
        if x >= 2.0 / 3.0:
            return 3.0 * (1.0 - x)
        return 1.0
    return 0.0


def _third_pt(u):
    """Elastic curve for two loads at the third points, half span,
    normalised to unity at midspan."""
    a = 1.0 / 3.0
    if u <= a:
        v = u * (3.0 * a * (1.0 - a) - u * u / 1.0) / 1.0
    else:
        v = a * (3.0 * u * (1.0 - u) - a * a) / 1.0
    vmid = a * (3.0 * 0.5 * 0.5 - a * a)
    return v / vmid if vmid else 0.0
