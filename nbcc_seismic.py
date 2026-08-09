"""
nbcc_seismic.py - NBCC 2020 Division B, Subsection 4.1.8 seismic engine.

Pure calculation module for the Infraspective Solutions calculator suite.
No Streamlit imports, so it can be unit tested and reused by other pages.

Covers:
    4.1.8.1  Analysis - simplified method for low seismicity
    4.1.8.2  Notation - W, hs, Dnx
    4.1.8.4  Site properties - Tables 4.1.8.4-A, -B, -C; Fa and Fv
    4.1.8.5  Importance factor and Seismic Category - Tables -A and -B
    4.1.8.6  Structural configuration - Table 4.1.8.6 irregularities
    4.1.8.7  Methods of analysis - when ESFP is permitted
    4.1.8.8  Direction of loading
    4.1.8.9  Table 4.1.8.9 - Rd, Ro and height restrictions
    4.1.8.10 Additional system restrictions
    4.1.8.11 Equivalent Static Force Procedure - Table 4.1.8.11 Mv and J

ASCII only. Straight quotes only.
"""

import math

NL = "NL"   # no height limit
NP = "NP"   # system not permitted


# ======================================================================
# 4.1.8.4 - SITE PROPERTIES
# ======================================================================

# Table 4.1.8.4-B, Site Classes S for site designation Xs
SITE_CLASS_TABLE = [
    # class, profile, vs30 range text, N60 text, su text
    ("A", "Hard rock", "vs30 > 1500", "n/a", "n/a"),
    ("B", "Rock", "760 < vs30 <= 1500", "n/a", "n/a"),
    ("C", "Very dense soil and soft rock", "360 < vs30 <= 760",
     "N60 > 50", "su > 100"),
    ("D", "Stiff soil", "180 < vs30 <= 360", "15 < N60 <= 50",
     "50 < su <= 100"),
    ("E", "Soft soil", "140 < vs30 <= 180", "10 < N60 <= 15",
     "40 < su <= 50"),
    ("F", "Other soils - site specific evaluation required",
     "vs30 <= 140", "N60 <= 10", "su <= 40"),
]

SITE_CLASS_DESC = dict((c, "%s (%s)" % (p, v))
                       for c, p, v, n, s in SITE_CLASS_TABLE)


def site_class_from_vs30(vs30):
    """Table 4.1.8.4-B, first column. Returns the Site Class letter."""
    if vs30 > 1500.0:
        return "A"
    if vs30 > 760.0:
        return "B"
    if vs30 > 360.0:
        return "C"
    if vs30 > 180.0:
        return "D"
    if vs30 > 140.0:
        return "E"
    return "F"


def site_class_from_n60(n60):
    """Table 4.1.8.4-B, N60 column."""
    if n60 > 50.0:
        return "C"
    if n60 > 15.0:
        return "D"
    if n60 > 10.0:
        return "E"
    return "F"


def site_class_from_su(su):
    """Table 4.1.8.4-B, undrained shear strength column, in kPa."""
    if su > 100.0:
        return "C"
    if su > 50.0:
        return "D"
    if su > 40.0:
        return "E"
    return "F"


def site_designation_exception(vs30, soft_over_rock=False,
                               soft_clay_profile=False,
                               collapse_susceptible=False):
    """Table 4.1.8.4-A. Returns (designation, reason) or (None, "")
    where no exception applies and Xv may be used directly."""
    if collapse_susceptible or vs30 <= 140.0:
        return ("XF", "Table 4.1.8.4-A: liquefiable, peat, highly "
                      "plastic or soft clay profile, or vs30 <= 140")
    if vs30 > 140.0 and soft_clay_profile:
        return ("XE", "Table 4.1.8.4-A: more than 3 m of soil with "
                      "PI > 20, w >= 40% and su < 25 kPa")
    if vs30 > 760.0 and soft_over_rock:
        return ("X760", "Table 4.1.8.4-A: more than 3 m of softer "
                        "material between rock and the underside of "
                        "the footing or mat foundation")
    return (None, "")


SA_PERIODS = [0.2, 0.5, 1.0, 2.0, 5.0, 10.0]


def design_spectrum(sa):
    """Table 4.1.8.4-C. Build S(T) from the Sa(T,X) values.

    sa is a dict keyed 'Sa(0.2)', 'Sa(0.5)', ... or the equivalent
    'S(0.2)' keys returned by the hazard API.

    Note the T <= 0.2 s entry: S(0.2) is the GREATER of Sa(0.2,X)
    and Sa(0.5,X).
    """
    def g(p):
        for k in ("Sa(%s)" % _fp(p), "S(%s)" % _fp(p)):
            if k in sa and sa[k] is not None:
                try:
                    v = float(sa[k])
                except (TypeError, ValueError):
                    continue
                if not math.isnan(v):
                    return v
        return float("nan")

    s02, s05 = g(0.2), g(0.5)
    if math.isnan(s02):
        top = s05
    elif math.isnan(s05):
        top = s02
    else:
        top = max(s02, s05)
    return {
        "S(0.2)": top,
        "S(0.5)": s05,
        "S(1.0)": g(1.0),
        "S(2.0)": g(2.0),
        "S(5.0)": g(5.0),
        "S(10.0)": g(10.0),
    }


def _fp(p):
    return "%.1f" % p


def s_of_T(S, T, method="log-log"):
    """S(T) at an arbitrary period, per Cl. 4.1.8.4.(6):
    log-log or linear interpolation between the tabulated periods."""
    pts = []
    for p in SA_PERIODS:
        v = S.get("S(%s)" % _fp(p))
        if v is not None and not math.isnan(v):
            pts.append((p, v))
    if not pts:
        return float("nan")
    if T <= pts[0][0]:
        return pts[0][1]
    if T >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        p0, v0 = pts[i]
        p1, v1 = pts[i + 1]
        if p0 <= T <= p1:
            if method == "log-log" and v0 > 0 and v1 > 0:
                lp = (math.log(T) - math.log(p0)) / \
                     (math.log(p1) - math.log(p0))
                return math.exp(math.log(v0) +
                                lp * (math.log(v1) - math.log(v0)))
            return v0 + (v1 - v0) * (T - p0) / (p1 - p0)
    return pts[-1][1]


def site_coefficients(S, sa_x450):
    """Cl. 4.1.8.4.(7): Fa = S(0.2)/Sa(0.2,X450),
    Fv = S(1.0)/Sa(1.0,X450)."""
    s450 = design_spectrum(sa_x450)
    fa = fv = float("nan")
    a = s450.get("S(0.2)")
    v = s450.get("S(1.0)")
    if a and not math.isnan(a) and a != 0:
        fa = S["S(0.2)"] / a
    if v and not math.isnan(v) and v != 0:
        fv = S["S(1.0)"] / v
    return fa, fv


# ======================================================================
# 4.1.8.5 - IMPORTANCE FACTOR AND SEISMIC CATEGORY
# ======================================================================

# Table 4.1.8.5-A
IE_TABLE = {"Low": 0.8, "Normal": 1.0, "High": 1.3, "Post-disaster": 1.5}


def importance_factor(category):
    return IE_TABLE[category]


def seismic_category(ie, s02, s10):
    """Table 4.1.8.5-B. The SC is the MORE SEVERE of the categories
    from IE*S(0.2) and IE*S(1.0), irrespective of Ta."""
    a = ie * s02
    b = ie * s10

    if a < 0.2:
        sc_a = 1
    elif a < 0.35:
        sc_a = 2
    elif a <= 0.75:
        sc_a = 3
    else:
        sc_a = 4

    if b < 0.1:
        sc_b = 1
    elif b < 0.2:
        sc_b = 2
    elif b <= 0.3:
        sc_b = 3
    else:
        sc_b = 4

    sc = max(sc_a, sc_b)
    return sc, a, b, sc_a, sc_b


# ======================================================================
# 4.1.8.6 - STRUCTURAL IRREGULARITIES (Table 4.1.8.6)
# ======================================================================

IRREGULARITIES = [
    (1, "Vertical Stiffness Irregularity",
     "Concrete and masonry shear walls: SFRS lateral stiffness in any "
     "storey less than 70% of an adjacent storey, or less than 80% of "
     "the average of the three storeys above or below. All other SFRS: "
     "interstorey deflection divided by hs in any storey greater than "
     "130% of that of an adjacent storey."),
    (2, "Weight (mass) Irregularity",
     "Weight Wi of any storey more than 150% of an adjacent storey. "
     "A roof lighter than the floor below need not be considered."),
    (3, "Vertical Geometric Irregularity",
     "Horizontal dimension of the SFRS in any storey more than 130% "
     "of that in an adjacent storey."),
    (4, "In-Plane Discontinuity in Vertical Lateral-Force-Resisting "
        "Element",
     "Except for braced frames and moment-resisting frames, an offset "
     "of a lateral-force-resisting element of the SFRS or a reduction "
     "in lateral stiffness of the resisting element in the storey "
     "below."),
    (5, "Out-of-Plane Offsets",
     "Discontinuities in a lateral force path, such as out-of-plane "
     "offsets of the vertical elements of the SFRS."),
    (6, "Discontinuity in Capacity - Weak Storey",
     "A storey in which the storey shear strength is less than that "
     "in the storey above."),
    (7, "Torsional Sensitivity",
     "To be considered when diaphragms are not flexible. Exists when "
     "B calculated per Cl. 4.1.8.11.(10) exceeds 1.7."),
    (8, "Non-orthogonal Systems",
     "The SFRS is not oriented along a set of orthogonal axes."),
    (9, "Gravity-Induced Lateral Demand Irregularity",
     "The ratio alpha per Cl. 4.1.8.10.(7) exceeds 0.1 for an SFRS "
     "with self-centering characteristics, and 0.03 for other "
     "systems."),
    (10, "Sloped Column Irregularity",
     "A vertical member inclined more than 2 degrees from the "
     "vertical supports a portion of the building weight in axial "
     "compression."),
]


# ======================================================================
# 4.1.8.7 - METHODS OF ANALYSIS
# ======================================================================

def esfp_permitted(sc, hn, Ta, irregular, irregular_types):
    """Cl. 4.1.8.7.(1). Returns (permitted, reason)."""
    if sc in (1, 2):
        return True, "Cl. 4.1.8.7.(1)(a): Seismic Category is SC%d" % sc
    if (not irregular) and hn < 60.0 and Ta < 2.0:
        return True, ("Cl. 4.1.8.7.(1)(b): regular structure, "
                      "hn = %.1f m < 60 m, Ta = %.3f s < 2 s" % (hn, Ta))
    allowed = set([2, 3, 4, 5, 6, 8])
    types = set(irregular_types)
    if types and types.issubset(allowed) and hn < 20.0 and Ta < 0.5:
        return True, ("Cl. 4.1.8.7.(1)(c): irregularity types %s only, "
                      "hn = %.1f m < 20 m, Ta = %.3f s < 0.5 s"
                      % (sorted(types), hn, Ta))
    return False, ("None of Cl. 4.1.8.7.(1)(a) to (c) is satisfied. "
                   "The Dynamic Analysis Procedure of Art. 4.1.8.12 "
                   "is required.")


# ======================================================================
# 4.1.8.9 - Rd, Ro AND HEIGHT RESTRICTIONS (Table 4.1.8.9)
# ======================================================================
# (material group, SFRS description, Rd, Ro, SC1, SC2, SC3, SC4)
# Height limits are maximum heights above grade in metres.

SFRS_TABLE = [
    ("Steel (CSA S16)", "Ductile moment-resisting frames",
     5.0, 1.5, NL, NL, NL, NL),
    ("Steel (CSA S16)", "Moderately ductile moment-resisting frames",
     3.5, 1.5, NL, NL, NL, NL),
    ("Steel (CSA S16)", "Limited ductility moment-resisting frames",
     2.0, 1.3, NL, NL, 60, 30),
    ("Steel (CSA S16)", "Moderately ductile truss moment-resisting frames",
     3.5, 1.6, NL, NL, 50, 30),
    ("Steel (CSA S16)", "Moderately ductile CBF - tension-compression "
     "braces", 3.0, 1.3, NL, NL, 40, 40),
    ("Steel (CSA S16)", "Moderately ductile CBF - tension only braces",
     3.0, 1.3, NL, NL, 20, 20),
    ("Steel (CSA S16)", "Limited ductility CBF - tension-compression "
     "braces", 2.0, 1.3, NL, NL, 60, 60),
    ("Steel (CSA S16)", "Limited ductility CBF - tension only braces",
     2.0, 1.3, NL, NL, 40, 40),
    ("Steel (CSA S16)", "Ductile buckling-restrained braced frames",
     4.0, 1.2, NL, NL, 40, 40),
    ("Steel (CSA S16)", "Ductile eccentrically braced frames",
     4.0, 1.5, NL, NL, NL, NL),
    ("Steel (CSA S16)", "Ductile plate walls", 5.0, 1.6, NL, NL, NL, NL),
    ("Steel (CSA S16)", "Moderately ductile plate walls",
     3.5, 1.3, NL, NL, 40, 40),
    ("Steel (CSA S16)", "Limited ductility plate walls",
     2.0, 1.3, NL, NL, 60, 60),
    ("Steel (CSA S16)", "Conventional construction of MRF, braced "
     "frames or plate walls - Assembly occupancies",
     1.5, 1.3, NL, NL, 15, 15),
    ("Steel (CSA S16)", "Conventional construction of MRF, braced "
     "frames or plate walls - Other occupancies",
     1.5, 1.3, NL, NL, 60, 40),
    ("Steel (CSA S16)", "Other steel SFRSs not defined above",
     1.0, 1.0, 15, 15, NP, NP),

    ("Concrete (CSA A23.3)", "Ductile moment-resisting frames",
     4.0, 1.7, NL, NL, NL, NL),
    ("Concrete (CSA A23.3)", "Moderately ductile moment-resisting frames",
     2.5, 1.4, NL, NL, 60, 40),
    ("Concrete (CSA A23.3)", "Ductile coupled walls",
     4.0, 1.7, NL, NL, NL, NL),
    ("Concrete (CSA A23.3)", "Moderately ductile coupled walls",
     2.5, 1.4, NL, NL, NL, 60),
    ("Concrete (CSA A23.3)", "Ductile partially coupled walls",
     3.5, 1.7, NL, NL, NL, NL),
    ("Concrete (CSA A23.3)", "Moderately ductile partially coupled walls",
     2.0, 1.4, NL, NL, NL, 60),
    ("Concrete (CSA A23.3)", "Ductile shear walls",
     3.5, 1.6, NL, NL, NL, NL),
    ("Concrete (CSA A23.3)", "Moderately ductile shear walls",
     2.0, 1.4, NL, NL, NL, 60),
    ("Concrete (CSA A23.3)", "Conventional construction - "
     "moment-resisting frames", 1.5, 1.3, NL, NL, 20, 10),
    ("Concrete (CSA A23.3)", "Conventional construction - shear walls",
     1.5, 1.3, NL, NL, 40, 30),
    ("Concrete (CSA A23.3)", "Conventional construction - two-way slabs "
     "without beams", 1.3, 1.3, 20, 15, NP, NP),
    ("Concrete (CSA A23.3)", "Tilt-up - moderately ductile walls and "
     "frames", 2.0, 1.3, 30, 25, 25, 25),
    ("Concrete (CSA A23.3)", "Tilt-up - limited ductility walls and "
     "frames", 1.5, 1.3, 30, 25, 20, 20),
    ("Concrete (CSA A23.3)", "Tilt-up - conventional walls and frames",
     1.3, 1.3, 25, 20, NP, NP),
    ("Concrete (CSA A23.3)", "Other concrete SFRSs not listed above",
     1.0, 1.0, 15, 15, NP, NP),

    ("Timber (CSA O86)", "Nailed shear walls - wood-based panel",
     3.0, 1.7, NL, NL, 30, 20),
    ("Timber (CSA O86)", "Shear walls - wood-based and gypsum panels "
     "in combination", 2.0, 1.7, NL, NL, 20, 20),
    ("Timber (CSA O86)", "Moderately ductile CLT shear walls - "
     "platform-type construction", 2.0, 1.5, 30, 30, 30, 20),
    ("Timber (CSA O86)", "Limited ductility CLT shear walls - "
     "platform-type construction", 1.0, 1.3, 30, 30, 30, 20),
    ("Timber (CSA O86)", "Braced or MRF with ductile connections - "
     "moderately ductile", 2.0, 1.5, NL, NL, 20, 20),
    ("Timber (CSA O86)", "Braced or MRF with ductile connections - "
     "limited ductility", 1.5, 1.5, NL, NL, 15, 15),
    ("Timber (CSA O86)", "Other wood- or gypsum-based SFRSs not listed "
     "above", 1.0, 1.0, 15, 15, NP, NP),

    ("Masonry (CSA S304)", "Ductile shear walls",
     3.0, 1.5, NL, NL, 60, 40),
    ("Masonry (CSA S304)", "Moderately ductile shear walls",
     2.0, 1.5, NL, NL, 60, 40),
    ("Masonry (CSA S304)", "Conventional construction - shear walls",
     1.5, 1.5, NL, 60, 30, 15),
    ("Masonry (CSA S304)", "Conventional construction - "
     "moment-resisting frames", 1.5, 1.5, NL, 30, NP, NP),
    ("Masonry (CSA S304)", "Unreinforced masonry",
     1.0, 1.0, 30, 15, NP, NP),
    ("Masonry (CSA S304)", "Other masonry SFRSs not listed above",
     1.0, 1.0, 15, NP, NP, NP),

    ("Cold-formed steel (CSA S136)", "Screw-connected shear walls - "
     "wood-based panels", 2.5, 1.7, 20, 20, 20, 20),
    ("Cold-formed steel (CSA S136)", "Screw-connected shear walls - "
     "wood-based and gypsum panels in combination",
     1.5, 1.7, 20, 20, 20, 20),
    ("Cold-formed steel (CSA S136)", "Diagonal strap concentrically "
     "braced walls - limited ductility", 1.9, 1.3, 20, 20, 20, 20),
    ("Cold-formed steel (CSA S136)", "Diagonal strap concentrically "
     "braced walls - conventional construction",
     1.2, 1.3, 15, 15, NP, NP),
    ("Cold-formed steel (CSA S136)", "Other cold-formed SFRSs not "
     "defined above", 1.0, 1.0, 15, 15, NP, NP),
]


def sfrs_groups():
    seen = []
    for row in SFRS_TABLE:
        if row[0] not in seen:
            seen.append(row[0])
    return seen


def sfrs_options(group):
    return [r[1] for r in SFRS_TABLE if r[0] == group]


def sfrs_lookup(group, name):
    for r in SFRS_TABLE:
        if r[0] == group and r[1] == name:
            return {"group": r[0], "name": r[1], "Rd": r[2], "Ro": r[3],
                    "limits": {1: r[4], 2: r[5], 3: r[6], 4: r[7]}}
    return None


def check_height_limit(entry, sc, hn):
    """Table 4.1.8.9 restrictions. Returns (ok, message)."""
    lim = entry["limits"][sc]
    if lim == NP:
        return False, ("Table 4.1.8.9: this SFRS is not permitted in "
                       "Seismic Category SC%d." % sc)
    if lim == NL:
        return True, ("Table 4.1.8.9: no height limit for this SFRS in "
                      "SC%d." % sc)
    if hn > float(lim):
        return False, ("Table 4.1.8.9: hn = %.1f m exceeds the %s m "
                       "limit for this SFRS in SC%d." % (hn, lim, sc))
    return True, ("Table 4.1.8.9: hn = %.1f m is within the %s m limit "
                  "for SC%d." % (hn, lim, sc))


def unreinforced_masonry_check(ie, hn):
    """Cl. 4.1.8.1.(4)."""
    if ie > 1.0:
        return False, ("Cl. 4.1.8.1.(4)(a): unreinforced masonry SFRS "
                       "is not permitted where IE > 1.0.")
    if hn >= 30.0:
        return False, ("Cl. 4.1.8.1.(4)(b): unreinforced masonry SFRS "
                       "is not permitted where the height above grade "
                       "is 30 m or more.")
    return True, ""


def cold_formed_height_check(hn):
    """Cl. 4.1.8.1.(5)."""
    if hn >= 15.0:
        return False, ("Cl. 4.1.8.1.(5): an SFRS designed to CSA S136 "
                       "shall be less than 15 m above grade.")
    return True, ""


# ======================================================================
# 4.1.8.11 - EQUIVALENT STATIC FORCE PROCEDURE
# ======================================================================

# Table 4.1.8.11 - Mv and J.
# Keyed by system group, then by S(0.2)/S(5.0) ratio.
# Each entry is (Mv at Ta<=0.5, 1.0, 2.0, >=5.0, J at 0.5, 1.0, 2.0, 5.0)
# None marks the note (5) cells: for Ta > 2.0 s use the 2.0 s values.

MV_J_TABLE = {
    "Moment-Resisting Frames": {
        5:  (1.0, 1.0, 1.0, None, 1.00, 1.00, 0.95, None),
        20: (1.0, 1.0, 1.0, None, 1.00, 0.97, 0.88, None),
        40: (1.0, 1.0, 1.0, None, 1.00, 0.90, 0.79, None),
        70: (1.0, 1.0, 1.0, None, 0.98, 0.88, 0.70, None),
    },
    "Coupled Walls": {
        5:  (1.0, 1.0, 1.0, 1.00, 1.00, 1.00, 0.95, 0.80),
        20: (1.0, 1.0, 1.0, 1.09, 1.00, 0.97, 0.88, 0.66),
        40: (1.0, 1.0, 1.0, 1.33, 1.00, 0.90, 0.79, 0.52),
        70: (1.0, 1.0, 1.0, 1.90, 0.98, 0.88, 0.70, 0.40),
    },
    "Braced Frames": {
        5:  (1.0, 1.0, 1.00, None, 1.00, 0.98, 0.93, None),
        20: (1.0, 1.0, 1.00, None, 1.00, 0.91, 0.80, None),
        40: (1.0, 1.0, 1.00, None, 0.91, 0.82, 0.72, None),
        70: (1.0, 1.0, 1.19, None, 0.91, 0.77, 0.61, None),
    },
    "Walls, Wall-Frame Systems": {
        5:  (1.0, 1.00, 1.00, 1.30, 1.00, 1.00, 0.85, 0.59),
        20: (1.0, 1.00, 1.18, 2.50, 1.00, 0.80, 0.60, 0.35),
        40: (1.0, 1.25, 1.85, 4.10, 0.80, 0.59, 0.42, 0.23),
        70: (1.0, 1.25, 2.30, 6.40, 0.80, 0.56, 0.30, 0.18),
    },
    "Other Systems": {
        5:  (1.0, 1.00, 1.00, None, 1.00, 1.00, 0.85, None),
        20: (1.0, 1.00, 1.18, None, 1.00, 0.80, 0.60, None),
        40: (1.0, 1.25, 1.85, None, 0.80, 0.59, 0.44, None),
        70: (1.0, 1.37, 2.30, None, 0.80, 0.56, 0.30, None),
    },
}

MV_TA_ANCHORS = [0.5, 1.0, 2.0, 5.0]


def _lin(x, x0, x1, y0, y1):
    if abs(x1 - x0) < 1e-12:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _row_at_ratio(group, ratio):
    """Note (1) to Table 4.1.8.11: linear interpolation on the
    spectral ratio. Below 5 the values interpolate toward 1.0 at a
    ratio of 0. Above 70 the ratio-70 values are used."""
    tab = MV_J_TABLE[group]
    keys = sorted(tab.keys())
    if ratio >= keys[-1]:
        return list(tab[keys[-1]])
    if ratio <= keys[0]:
        base = tab[keys[0]]
        out = []
        for v in base:
            out.append(None if v is None
                       else _lin(ratio, 0.0, float(keys[0]), 1.0, v))
        return out
    for i in range(len(keys) - 1):
        r0, r1 = keys[i], keys[i + 1]
        if r0 <= ratio <= r1:
            a, b = tab[r0], tab[r1]
            out = []
            for va, vb in zip(a, b):
                if va is None or vb is None:
                    out.append(None)
                else:
                    out.append(_lin(ratio, float(r0), float(r1), va, vb))
            return out
    return list(tab[keys[-1]])


def mv_and_j(group, s02, s50, Ta):
    """Table 4.1.8.11. Returns (Mv, J, ratio, note)."""
    if s50 and s50 > 0 and not math.isnan(s50):
        ratio = s02 / s50
    else:
        ratio = 70.0
    row = _row_at_ratio(group, ratio)
    mv_vals = row[0:4]
    j_vals = row[4:8]

    note = ""
    T = Ta
    if mv_vals[3] is None:
        # Note (5): for Ta > 2.0 s use the 2.0 s values.
        if T > 2.0:
            note = ("Note (5) to Table 4.1.8.11: Ta > 2.0 s, so the "
                    "2.0 s values are used.")
            T = 2.0
        anchors = MV_TA_ANCHORS[0:3]
        mv_vals = mv_vals[0:3]
        j_vals = j_vals[0:3]
    else:
        anchors = MV_TA_ANCHORS

    mv = _interp_on_Ta(T, anchors, mv_vals)
    j = _interp_on_Ta(T, anchors, j_vals)
    return mv, j, ratio, note


def _interp_on_Ta(T, anchors, vals):
    if T <= anchors[0]:
        return vals[0]
    if T >= anchors[-1]:
        return vals[-1]
    for i in range(len(anchors) - 1):
        a0, a1 = anchors[i], anchors[i + 1]
        if a0 <= T <= a1:
            return _lin(T, a0, a1, vals[i], vals[i + 1])
    return vals[-1]


# --- Fundamental lateral period, Cl. 4.1.8.11.(3) and (4) -------------

PERIOD_SYSTEMS = [
    "Steel moment frame",
    "Concrete moment frame",
    "Other moment frame",
    "Braced frame",
    "Shear wall or other structure",
]


def fundamental_period(system, hn, n_storeys=1):
    """Cl. 4.1.8.11.(3)(a) to (c). Returns (Ta, expression)."""
    if system == "Steel moment frame":
        return 0.085 * hn ** 0.75, "Ta = 0.085 (hn)^(3/4)"
    if system == "Concrete moment frame":
        return 0.075 * hn ** 0.75, "Ta = 0.075 (hn)^(3/4)"
    if system == "Other moment frame":
        return 0.1 * float(n_storeys), "Ta = 0.1 N"
    if system == "Braced frame":
        return 0.025 * hn, "Ta = 0.025 hn"
    return 0.05 * hn ** 0.75, "Ta = 0.05 (hn)^(3/4)"


def single_storey_period(system, hn, L):
    """Cl. 4.1.8.11.(4): single-storey buildings with steel deck or
    wood roof diaphragms. L is the shortest diaphragm length in m."""
    if system in ("Steel moment frame", "Braced frame"):
        return (0.035 * hn + 0.004 * L,
                "Ta = 0.035 hn + 0.004 L")
    return (0.05 * hn ** 0.75 + 0.004 * L,
            "Ta = 0.05 (hn)^(3/4) + 0.004 L")


PERIOD_CAP = {
    "Steel moment frame": 1.5,
    "Concrete moment frame": 1.5,
    "Other moment frame": 1.5,
    "Braced frame": 2.0,
    "Shear wall or other structure": 2.0,
}


def cap_mechanics_period(system, Ta_mech, Ta_empirical):
    """Cl. 4.1.8.11.(3)(d)(i) to (iv). Caps a period from a
    mechanics model against the empirical value."""
    factor = PERIOD_CAP.get(system, 1.0)
    cap = factor * Ta_empirical
    if Ta_mech > cap:
        return cap, ("Ta capped at %.1f x the empirical value per "
                     "Cl. 4.1.8.11.(3)(d)." % factor)
    return Ta_mech, ""


# --- Base shear, Cl. 4.1.8.11.(2) -------------------------------------

def base_shear(S, Ta, mv, ie, W, rd, ro, system_group,
               site_designation="XC", interp="log-log"):
    """Cl. 4.1.8.11.(2). Returns a dict with V and the governing
    bound.

    V = S(Ta) Mv IE W / (Rd Ro)

    Minimum:
      (a) walls, coupled walls, wall-frame systems:
          S(4.0) Mv IE W / (Rd Ro)
      (b) moment-resisting frames, braced frames, other systems:
          S(2.0) Mv IE W / (Rd Ro)

    Maximum, where the site is other than XF and Rd >= 1.5, V need not
    exceed the LARGER of:
          (2/3) S(0.2) IE W / (Rd Ro)   and   S(0.5) IE W / (Rd Ro)
    """
    denom = rd * ro
    s_ta = s_of_T(S, Ta, interp)
    v_calc = s_ta * mv * ie * W / denom

    wall_like = system_group in ("Walls, Wall-Frame Systems",
                                 "Coupled Walls")
    if wall_like:
        s_min = s_of_T(S, 4.0, interp)
        v_min = s_min * mv * ie * W / denom
        min_ref = "Cl. 4.1.8.11.(2)(a), S(4.0)"
    else:
        s_min = S.get("S(2.0)", float("nan"))
        v_min = s_min * mv * ie * W / denom
        min_ref = "Cl. 4.1.8.11.(2)(b), S(2.0)"

    v_max = None
    max_ref = ""
    if site_designation.upper() != "XF" and rd >= 1.5:
        cap_a = (2.0 / 3.0) * S["S(0.2)"] * ie * W / denom
        cap_b = S["S(0.5)"] * ie * W / denom
        v_max = max(cap_a, cap_b)
        max_ref = ("Cl. 4.1.8.11.(2)(c), larger of (2/3)S(0.2) and "
                   "S(0.5): %.1f and %.1f" % (cap_a, cap_b))

    v = v_calc
    governs = "Cl. 4.1.8.11.(2), V = S(Ta) Mv IE W / (Rd Ro)"
    if v_min > v:
        v = v_min
        governs = min_ref + " minimum governs"
    if v_max is not None and v > v_max:
        v = v_max
        governs = "Cl. 4.1.8.11.(2)(c) maximum governs"

    return {"V": v, "V_calc": v_calc, "V_min": v_min, "V_max": v_max,
            "S_Ta": s_ta, "S_min": s_min, "governs": governs,
            "min_ref": min_ref, "max_ref": max_ref}


# --- Vertical distribution, Cl. 4.1.8.11.(7) --------------------------

def top_force(V, Ta):
    """Ft = 0.07 Ta V, need not exceed 0.25 V, taken as zero where
    Ta does not exceed 0.7 s."""
    if Ta <= 0.7:
        return 0.0, "Ft = 0 since Ta <= 0.7 s"
    ft = 0.07 * Ta * V
    if ft > 0.25 * V:
        return 0.25 * V, "Ft capped at 0.25 V"
    return ft, "Ft = 0.07 Ta V"


def distribute(V, Ta, levels):
    """Cl. 4.1.8.11.(7)(b). levels is a list of dicts with keys
    'level', 'W' and 'h', ordered from the lowest level upward.

    Fx = (V - Ft) Wx hx / sum(Wi hi), with Ft added at the top level.
    """
    ft, ft_note = top_force(V, Ta)
    total = sum(l["W"] * l["h"] for l in levels)
    out = []
    for i, l in enumerate(levels):
        share = 0.0 if total <= 0 else (l["W"] * l["h"]) / total
        fx = (V - ft) * share
        if i == len(levels) - 1:
            fx += ft
        out.append({"level": l["level"], "W": l["W"], "h": l["h"],
                    "Wh": l["W"] * l["h"], "share": share, "Fx": fx})
    return out, ft, ft_note, total


def storey_shears(forces):
    """Storey shear at each level = sum of Fx at and above."""
    n = len(forces)
    shears = [0.0] * n
    run = 0.0
    for i in range(n - 1, -1, -1):
        run += forces[i]["Fx"]
        shears[i] = run
    return shears


# --- Overturning, Cl. 4.1.8.11.(8) -----------------------------------

def overturning(forces, J, hn):
    """Mx = Jx * sum over i >= x of Fi (hi - hx)

    Jx = 1.0 for hx >= 0.6 hn
    Jx = J + (1 - J)(hx / 0.6 hn) for hx < 0.6 hn
    """
    out = []
    n = len(forces)
    for x in range(n):
        hx = forces[x]["h"]
        raw = sum(forces[i]["Fx"] * (forces[i]["h"] - hx)
                  for i in range(x, n))
        if hx >= 0.6 * hn:
            jx = 1.0
        else:
            jx = J + (1.0 - J) * (hx / (0.6 * hn))
        out.append({"level": forces[x]["level"], "h": hx,
                    "Jx": jx, "M_raw": raw, "Mx": jx * raw})
    # base overturning moment, hx = 0
    raw_base = sum(f["Fx"] * f["h"] for f in forces)
    jx_base = J if 0.0 < 0.6 * hn else 1.0
    out.append({"level": "Base", "h": 0.0, "Jx": jx_base,
                "M_raw": raw_base, "Mx": jx_base * raw_base})
    return out


# --- Torsion, Cl. 4.1.8.11.(9) to (11) -------------------------------

def torsional_sensitivity(d_max, d_ave):
    """Bx = d_max / d_ave. B > 1.7 is a Type 7 irregularity."""
    if d_ave <= 0:
        return float("nan")
    return d_max / d_ave


def torsional_moments(Fx, ex, Dnx):
    """Tx = Fx (ex + 0.10 Dnx) and Fx (ex - 0.10 Dnx)."""
    return Fx * (ex + 0.10 * Dnx), Fx * (ex - 0.10 * Dnx)


# --- Drift, Cl. 4.1.8.13 / 4.1.8.1.(11) ------------------------------

DRIFT_LIMITS = {"Post-disaster": 0.010, "High": 0.020,
                "Normal": 0.025, "Low": 0.025}


def drift_limit(category):
    return DRIFT_LIMITS[category]


# ======================================================================
# 4.1.8.1 - SIMPLIFIED METHOD FOR LOW SEISMICITY
# ======================================================================

def site_coefficient_Fs(n60=None, su=None, rock=False):
    """Cl. 4.1.8.1.(2)(b). Fs for the top 30 m of soil below the
    footings, pile caps or mat foundations."""
    if rock:
        return 1.0, "rock site"
    if n60 is not None:
        if n60 > 50.0:
            return 1.0, "N60 > 50"
        if 15.0 <= n60 <= 50.0:
            return 1.6, "15 <= N60 <= 50"
        return 2.8, "all other cases"
    if su is not None:
        if su > 100.0:
            return 1.0, "su > 100 kPa"
        if 50.0 <= su <= 100.0:
            return 1.6, "50 kPa <= su <= 100 kPa"
        return 2.8, "all other cases"
    return 2.8, "all other cases (no N60 or su supplied)"


def simplified_method_applies(ie, fs, sa_x450):
    """Cl. 4.1.8.1.(2): permitted where IE Fs Sa(0.2,X450) < 0.16
    and IE Fs Sa(2.0,X450) < 0.03."""
    a = ie * fs * float(sa_x450.get("Sa(0.2)",
                                    sa_x450.get("S(0.2)", float("nan"))))
    b = ie * fs * float(sa_x450.get("Sa(2.0)",
                                    sa_x450.get("S(2.0)", float("nan"))))
    ok = (a < 0.16) and (b < 0.03)
    return ok, a, b


def simplified_period(system, hn, n_storeys=1):
    """Ts per Cl. 4.1.8.1.(7). Same forms as Ta."""
    return fundamental_period(system, hn, n_storeys)


def sa_Ts(sa_x450, Ts):
    """Sa(Ts,X450) per Cl. 4.1.8.1.(7): linear interpolation between
    Sa(0.2), Sa(0.5) and Sa(1.0); Sa(0.2) for Ts <= 0.2 s and
    Sa(1.0) for Ts >= 1.0 s."""
    def g(p):
        for k in ("Sa(%s)" % _fp(p), "S(%s)" % _fp(p)):
            if k in sa_x450:
                try:
                    return float(sa_x450[k])
                except (TypeError, ValueError):
                    pass
        return float("nan")
    a, b, c = g(0.2), g(0.5), g(1.0)
    if Ts <= 0.2:
        return a
    if Ts >= 1.0:
        return c
    if Ts <= 0.5:
        return _lin(Ts, 0.2, 0.5, a, b)
    return _lin(Ts, 0.5, 1.0, b, c)


def simplified_base_shear(fs, sa_ts, ie, W, rs, sa_05=None):
    """Vs = Fs Sa(Ts,X450) IE W / Rs, Cl. 4.1.8.1.(7).

    Where Rs = 1.5, Vs need not be greater than
    Fs Sa(0.5,X450) IE W / Rs.
    """
    vs = fs * sa_ts * ie * W / rs
    cap = None
    if abs(rs - 1.5) < 1e-9 and sa_05 is not None:
        cap = fs * sa_05 * ie * W / rs
        if vs > cap:
            return cap, vs, cap
    return vs, vs, cap


def simplified_distribute(Vs, levels):
    """Fx = Vs Wx hx / sum(Wi hi), Cl. 4.1.8.1.(8). No Ft term."""
    total = sum(l["W"] * l["h"] for l in levels)
    out = []
    for l in levels:
        share = 0.0 if total <= 0 else (l["W"] * l["h"]) / total
        out.append({"level": l["level"], "W": l["W"], "h": l["h"],
                    "Wh": l["W"] * l["h"], "share": share,
                    "Fx": Vs * share})
    return out, total


def appendage_force(sa_02_x450, fs, ie, Wp, unreinforced_masonry=False):
    """Vsp = 0.9 Sa(0.2,X450) Fs IE Wp, Cl. 4.1.8.1.(13).
    Doubled for unreinforced masonry elements per Sentence (14)."""
    vsp = 0.9 * sa_02_x450 * fs * ie * Wp
    if unreinforced_masonry:
        return 2.0 * vsp, "doubled for unreinforced masonry, Cl. (14)"
    return vsp, ""


CONNECTION_UPLIFT_ELEMENTS = [
    "Diaphragms and their chords, connections, struts and collectors",
    "Tie downs in wood or drywall shear walls",
    "Connections and anchor bolts in steel- and wood-braced frames",
    "Connections in precast concrete",
    "Connections in steel moment frames",
]


def seismic_weight(dead_kN, snow_kN, storage_kN=0.0, tanks_kN=0.0):
    """W per Art. 4.1.8.2: specified dead load, plus 25% of the
    specified snow load, plus 60% of the storage load, plus the full
    contents of any tanks."""
    return dead_kN + 0.25 * snow_kN + 0.60 * storage_kN + tanks_kN
