"""
NBCC 2020 - Wind, Snow and Seismic Loads (Buildings)

Infraspective Solutions - structural calculator suite.

Ported from the "Wind, Snow & Seismic (Building)" tab of
Structural_Calculations_Simulation__2025-09-14_.xlsm

References (NBCC 2020, Division B, Part 4, Volume 1):
    Load combinations - Article 4.1.3.2 and 4.1.3.4
    Snow              - Article 4.1.6.2
    Wind              - Articles 4.1.7.3, 4.1.7.5, 4.1.7.6, 4.1.7.7
    Seismic           - Articles 4.1.8.4, 4.1.8.5, 4.1.8.9, 4.1.8.11
    Climatic data     - Table C-2, Appendix C

Geocoding replaces the modGeo.GetCoordinatesOfficial VBA routine of
the source workbook. Same service (Nominatim / OpenStreetMap), same
treeline rule (latitude 60 N), with reverse geocoding added so that
the location name and the coordinates stay synchronised in both
directions.

ASCII only. Straight quotes only. No markdown inside code.
"""

import os
import json
import math
import difflib

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    import requests
except Exception:
    requests = None

import nbcc_seismic as nbcc

# ----------------------------------------------------------------------
# Theme hook - defensive so the page still runs standalone.
# Replace this block with your normal _theme call.
# ----------------------------------------------------------------------
try:
    import _theme as _th
    for _name in ("apply_theme", "apply", "setup", "init", "page_setup"):
        if hasattr(_th, _name):
            getattr(_th, _name)()
            break
except Exception:
    st.set_page_config(page_title="NBCC 2020 Wind / Snow / Seismic",
                       layout="wide")


# ======================================================================
# SECTION 0 - DATA
# ======================================================================

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
C2_FILENAME = "nbcc2020_table_c2.csv"


def _c2_search_paths():
    """Every place the climatic data file is reasonably allowed to
    live. The app root and the pages folder are both fine, so no new
    folder has to be created."""
    names = [C2_FILENAME, "data/" + C2_FILENAME,
             "attached_assets/" + C2_FILENAME]
    bases = [_HERE, _ROOT, os.getcwd()]
    out = []
    for b in bases:
        for n in names:
            p = os.path.normpath(os.path.join(b, n))
            if p not in out:
                out.append(p)
    return out


def find_table_c2():
    """Locate the CSV. Returns (path, tried). Deliberately not cached,
    so dropping the file in and rerunning is enough to pick it up."""
    tried = _c2_search_paths()
    for p in tried:
        if os.path.isfile(p):
            return p, tried
    # Last resort: walk the project for the file by name.
    for base in (_ROOT, os.getcwd()):
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".")
                           and d not in ("__pycache__", "node_modules",
                                         "venv", ".venv")]
            if C2_FILENAME in filenames:
                return os.path.join(dirpath, C2_FILENAME), tried
    return None, tried


@st.cache_data(show_spinner=False)
def _read_table_c2(path, mtime):
    """Cached on the path and its modification time, so replacing the
    file invalidates the cache instead of serving a stale result."""
    df = pd.read_csv(path)
    df["province"] = df["province"].astype(str).str.strip()
    df["location"] = df["location"].astype(str).str.strip()
    return df


def load_table_c2():
    path, tried = find_table_c2()
    if path is None:
        return pd.DataFrame(), None, tried
    return _read_table_c2(path, os.path.getmtime(path)), path, tried


# NBCC 2020 Table 4.1.7.6 - External peak values of Cg*Cp for low buildings.
# Load Case A rows are keyed by roof slope; Load Case B applies 0 to 90 deg.
CGCP_CASE_A = {
    5.0:  {"1": 0.75, "1E": 1.15, "2": -1.30, "2E": -2.00,
           "3": -0.70, "3E": -1.00, "4": -0.55, "4E": -0.80},
    20.0: {"1": 1.00, "1E": 1.50, "2": -1.30, "2E": -2.00,
           "3": -0.90, "3E": -1.30, "4": -0.80, "4E": -1.20},
    30.0: {"1": 1.05, "1E": 1.30, "2": 0.40, "2E": 0.50,
           "3": -0.80, "3E": -1.00, "4": -0.70, "4E": -0.90},
    90.0: {"1": 1.05, "1E": 1.30, "2": 1.05, "2E": 1.30,
           "3": -0.70, "3E": -0.90, "4": -0.70, "4E": -0.90},
}

CGCP_CASE_B = {
    "1": -0.85, "1E": -0.90, "2": -1.30, "2E": -2.00,
    "3": -0.70, "3E": -1.00, "4": -0.85, "4E": -0.90,
    "5": 0.75, "5E": 1.15, "6": -0.55, "6E": -0.80,
}

SURFACES_A = ["1", "1E", "2", "2E", "3", "3E", "4", "4E"]
SURFACES_B = ["1", "1E", "2", "2E", "3", "3E", "4", "4E",
              "5", "5E", "6", "6E"]



# ======================================================================
# SECTION 0B - ENGINE: GEOCODING AND TREELINE
# ======================================================================
#
# The source workbook resolved a place name to coordinates with
# modGeo.GetCoordinatesOfficial, a Nominatim (OpenStreetMap) query, and
# then applied a plain latitude test for the treeline. The same service
# is used here. Reverse geocoding is added so that a pair of
# coordinates resolves back to a place name, which is then matched
# against the Table C-2 catalogue. Nothing is hard-coded per location.

GEO_UA = "InfraspectiveSolutions-NBCC2020/1.0 (structural calculator)"
TREELINE_LAT = 60.0


@st.cache_data(show_spinner=False, ttl=604800)
def geocode_forward(place, province=""):
    """Place name to coordinates. Returns (lat, lon, label, error).

    Primary service is Nominatim, matching the workbook. Open-Meteo is
    used as a fallback if Nominatim is unreachable or returns nothing.
    """
    if requests is None:
        return None, None, "", "requests is not installed"
    query = ", ".join([p for p in (str(place).strip(),
                                   str(province).strip(),
                                   "Canada") if p])

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1,
                    "countrycodes": "ca"},
            headers={"User-Agent": GEO_UA}, timeout=20)
        resp.raise_for_status()
        hits = resp.json()
        if hits:
            h = hits[0]
            return (float(h["lat"]), float(h["lon"]),
                    h.get("display_name", query), "")
    except Exception as exc:
        nom_err = str(exc)
    else:
        nom_err = "no match returned by Nominatim"

    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": str(place).strip(), "count": 10,
                    "language": "en", "format": "json"}, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        results = [r for r in results if r.get("country_code") == "CA"]
        if province:
            pref = [r for r in results
                    if str(r.get("admin1", "")).lower()
                    == str(province).lower()]
            results = pref or results
        if results:
            r = results[0]
            label = ", ".join([str(r.get("name", "")),
                               str(r.get("admin1", "")), "Canada"])
            return float(r["latitude"]), float(r["longitude"]), label, ""
    except Exception as exc:
        return None, None, "", "%s; fallback failed: %s" % (nom_err, exc)

    return None, None, "", nom_err


@st.cache_data(show_spinner=False, ttl=604800)
def geocode_reverse(lat, lon):
    """Coordinates to place name. Returns (place, province, label, err)."""
    if requests is None:
        return "", "", "", "requests is not installed"
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": float(lat), "lon": float(lon),
                    "format": "json", "zoom": 10},
            headers={"User-Agent": GEO_UA}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return "", "", "", "reverse geocoding failed: %s" % exc

    addr = data.get("address", {}) or {}
    place = ""
    for key in ("city", "town", "village", "hamlet", "municipality",
                "county", "city_district", "suburb", "region"):
        if addr.get(key):
            place = str(addr[key])
            break
    province = str(addr.get("state", "") or addr.get("territory", ""))
    return place, province, data.get("display_name", ""), ""


PROVINCE_ALIASES = {
    "quebec": "Quebec", "que": "Quebec", "qc": "Quebec",
    "newfoundland": "Newfoundland and Labrador",
    "newfoundland and labrador": "Newfoundland and Labrador",
    "nl": "Newfoundland and Labrador",
    "british columbia": "British Columbia", "bc": "British Columbia",
    "alberta": "Alberta", "ab": "Alberta",
    "saskatchewan": "Saskatchewan", "sk": "Saskatchewan",
    "manitoba": "Manitoba", "mb": "Manitoba",
    "ontario": "Ontario", "on": "Ontario",
    "new brunswick": "New Brunswick", "nb": "New Brunswick",
    "nova scotia": "Nova Scotia", "ns": "Nova Scotia",
    "prince edward island": "Prince Edward Island",
    "pe": "Prince Edward Island", "pei": "Prince Edward Island",
    "yukon": "Yukon", "yukon territory": "Yukon", "yt": "Yukon",
    "northwest territories": "Northwest Territories",
    "nt": "Northwest Territories", "nwt": "Northwest Territories",
    "nunavut": "Nunavut", "nu": "Nunavut",
}


def normalise_province(name, available):
    """Map whatever the geocoder returned onto a Table C-2 province."""
    raw = str(name or "").strip()
    hit = PROVINCE_ALIASES.get(raw.lower())
    if hit and hit in available:
        return hit
    for p in available:
        if p.lower() == raw.lower():
            return p
    close = difflib.get_close_matches(raw, list(available), n=1,
                                      cutoff=0.6)
    return close[0] if close else None


def match_c2_location(df, place, province=None):
    """Fuzzy-match a geocoded place onto the Table C-2 catalogue.

    Returns (province, location, score) or (None, None, 0.0). The match
    is textual, so it is offered to the user rather than forced."""
    place = str(place or "").strip()
    if not place or df.empty:
        return None, None, 0.0

    sub = df
    if province:
        maybe = df[df["province"] == province]
        if not maybe.empty:
            sub = maybe

    best, best_score = None, 0.0
    for _, r in sub.iterrows():
        loc = str(r["location"])
        score = difflib.SequenceMatcher(
            None, place.lower(), loc.lower()).ratio()
        # A catalogue entry truncated by the Table C-2 export, such as
        # "Saint-Jean-sur-", should still match its full name.
        if loc.lower() and place.lower().startswith(loc.lower()):
            score = max(score, 0.92)
        if score > best_score:
            best, best_score = r, score
    if best is None:
        return None, None, 0.0
    return str(best["province"]), str(best["location"]), best_score


def north_of_treeline(lat):
    """Cl. 4.1.6.2.(4) refers to exposed areas north of the treeline.
    The workbook applied a latitude test at 60 N; the same rule is
    applied here, as an aid rather than a substitute for judgement."""
    try:
        return float(lat) >= TREELINE_LAT
    except (TypeError, ValueError):
        return False


# ======================================================================
# SECTION 1 - ENGINE: IMPORTANCE FACTORS
# ======================================================================

def importance_factor_snow(limit_state, category):
    if limit_state == "SLS":
        return 0.90
    return {"Low": 0.80, "Normal": 1.00,
            "High": 1.15, "Post-Disaster": 1.25}[category]


def importance_factor_wind(limit_state, category):
    if limit_state == "SLS":
        return 0.75
    return {"Low": 0.80, "Normal": 1.00,
            "High": 1.15, "Post-Disaster": 1.25}[category]


# ======================================================================
# SECTION 2 - ENGINE: SNOW LOAD (Article 4.1.6.2)
# ======================================================================

def characteristic_length(w, l):
    """lc = 2w - w^2/l  (Cl. 4.1.6.2)."""
    if l <= 0:
        return 0.0
    return 2.0 * w - (w * w) / l


def wind_exposure_factor_snow(category, requested, north, cond_a,
                              cond_b, cond_c):
    """Cw per Cl. 4.1.6.2.(3) and (4).

    Sentence (3) sets Cw = 1.0. Sentence (4) permits 0.75 for rural
    areas, or 0.50 for exposed areas north of the treeline, but only
    for Low and Normal Importance Category buildings and only where
    Clauses (a), (b) and (c) are all satisfied.

    Returns (Cw, reason).
    """
    if abs(requested - 1.00) < 1e-9:
        return 1.00, "Cl. 4.1.6.2.(3): Cw = 1.0"

    if category not in ("Low", "Normal"):
        return 1.00, ("Cl. 4.1.6.2.(4) applies only to the Low and "
                      "Normal Importance Categories, so Cw reverts "
                      "to 1.0")

    missing = []
    if not cond_a:
        missing.append("(a) exposed on all sides to wind over open "
                       "terrain")
    if not cond_b:
        missing.append("(b) roof area free of significant obstructions")
    if not cond_c:
        missing.append("(c) no accumulation by drifting")
    if missing:
        return 1.00, ("Cl. 4.1.6.2.(4) not satisfied - " +
                      "; ".join(missing) + " - so Cw = 1.0")

    if abs(requested - 0.50) < 1e-9:
        if not north:
            return 0.75, ("Cw = 0.50 is limited to exposed areas north "
                          "of the treeline; 0.75 used instead")
        return 0.50, ("Cl. 4.1.6.2.(4): exposed area north of the "
                      "treeline")
    return 0.75, "Cl. 4.1.6.2.(4): rural area"


def basic_roof_snow_factor(lc, cw):
    """Cb per Cl. 4.1.6.2.(3).

    Cb = 0.8                                   for lc <= 70 / Cw^2
    Cb = (1/Cw)[1 - (1 - 0.8Cw) exp(-(lc Cw^2 - 70)/(100 Cw^2))]
                                               for lc >  70 / Cw^2
    """
    if cw <= 0:
        return 0.80, 0.0, "invalid Cw"
    limit = 70.0 / (cw ** 2)
    if lc <= limit:
        return 0.80, limit, "lc <= 70/Cw^2"
    arg = -(lc * cw ** 2 - 70.0) / (100.0 * cw ** 2)
    cb = (1.0 / cw) * (1.0 - (1.0 - 0.8 * cw) * math.exp(arg))
    return cb, limit, "lc > 70/Cw^2"


def roof_slope_factor(alpha_deg, slippery):
    """Cs per Cl. 4.1.6.2.(5)."""
    a = alpha_deg
    if slippery:
        if a <= 15.0:
            return 1.0, "alpha <= 15 deg (slippery)"
        if a < 60.0:
            return (60.0 - a) / 45.0, "15 < alpha < 60 deg (slippery)"
        return 0.0, "alpha >= 60 deg (slippery)"
    if a <= 30.0:
        return 1.0, "alpha <= 30 deg"
    if a < 70.0:
        return (70.0 - a) / 40.0, "30 < alpha < 70 deg"
    return 0.0, "alpha >= 70 deg"


def snow_load(is_f, ss, sr, cb, cw, cs, ca):
    """S = Is [ Ss (Cb Cw Cs Ca) + Sr ]."""
    basic = ss * cb * cw * cs * ca
    return is_f * (basic + sr), basic


# ======================================================================
# SECTION 3 - ENGINE: WIND LOAD (Article 4.1.7)
# ======================================================================

def velocity_from_q(q):
    """Table C-1 relationship, q = 0.00064645 V^2."""
    if q <= 0:
        return 0.0
    return math.sqrt(q / 0.00064645)


def exposure_factor(href, terrain):
    """Ce per Cl. 4.1.7.3.(5)."""
    h = max(href, 0.001)
    if terrain == "Open":
        return max((h / 10.0) ** 0.2, 0.9), "(h/10)^0.2 >= 0.9"
    return max(0.7 * (h / 12.0) ** 0.3, 0.7), "0.7(h/12)^0.3 >= 0.7"


def end_zone_width(least_horiz_dim, h):
    """z per Cl. 4.1.7.6.(5): lesser of 0.1*least dim and 0.4*H,
    but not less than 0.04*least dim or 1 m."""
    z = min(0.10 * least_horiz_dim, 0.40 * h)
    z = max(z, 0.04 * least_horiz_dim, 1.0)
    return z


def _interp(x, x0, x1, y0, y1):
    if abs(x1 - x0) < 1e-12:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def cgcp_case_a(alpha_deg):
    """Interpolate Table 4.1.7.6 Load Case A on roof slope."""
    a = max(0.0, min(90.0, alpha_deg))
    keys = [5.0, 20.0, 30.0, 90.0]
    if a <= 5.0:
        return dict(CGCP_CASE_A[5.0]), "0 to 5 deg (tabulated)"
    if a >= 90.0:
        return dict(CGCP_CASE_A[90.0]), "90 deg (tabulated)"
    if 30.0 <= a <= 45.0:
        return dict(CGCP_CASE_A[30.0]), "30 to 45 deg (tabulated)"
    lo = max([k for k in keys if k <= a])
    hi = min([k for k in keys if k >= a])
    if lo == hi:
        return dict(CGCP_CASE_A[lo]), "%.0f deg (tabulated)" % lo
    lo_eff, hi_eff = lo, hi
    if lo == 30.0 and a > 45.0:
        lo_eff = 45.0
    out = {}
    for s in SURFACES_A:
        out[s] = _interp(a, lo_eff, hi_eff,
                         CGCP_CASE_A[lo][s], CGCP_CASE_A[hi][s])
    return out, "interpolated between %.0f and %.0f deg" % (lo_eff, hi_eff)


def internal_gust_factor(volume, area, large_volume):
    """Cgi per Cl. 4.1.7.3. 2.0 normally; the reduced value applies
    to large unpartitioned volumes with few openings."""
    if not large_volume:
        return 2.0, "Cgi = 2.0"
    if area <= 0:
        return 2.0, "Cgi = 2.0 (invalid area)"
    cgi = 1.0 + 1.0 / math.sqrt(1.0 + volume / (6.95 * area))
    return cgi, "Cgi = 1 + 1/sqrt(1 + Vo/(6.95 A))"


def wind_pressure(iw, q, ce, ct, cgcp):
    """p = Iw q Ce Ct (Cg Cp)."""
    return iw * q * ce * ct * cgcp


# ======================================================================
# SECTION 3B - ENGINE: LOAD COMBINATIONS (Article 4.1.3)
# ======================================================================

def _fmt_term(factor, symbol):
    if abs(factor) < 1e-12:
        return ""
    return "%.2f%s" % (factor, symbol)


def _assemble(terms):
    """terms is a list of (factor, symbol). Build a readable string."""
    out = []
    for f, s in terms:
        if abs(f) < 1e-12:
            continue
        sign = "-" if f < 0 else "+"
        piece = "%s%.2f%s" % ("" if not out and f > 0 else sign + " ",
                              abs(f), s)
        out.append(piece)
    return " ".join(out) if out else "0"


def uls_combinations(D, L, S, W, E, storage=False, liquids=False):
    """Table 4.1.3.2-A, load combinations without crane loads.

    Sentence (3) requires the principal loads to be checked with the
    companion loads taken as zero, so a zero companion is enumerated
    for every case. Sentence (5) requires the counteracting dead load
    (0.9D, or 1.0D in case 5) to be considered. Sentence (6) permits
    the 1.5 principal factor on L to drop to 1.25 for liquids in tanks.
    Sentence (7) increases the companion factor on L by 0.5 for storage
    areas, equipment areas and service rooms.
    """
    aL = 1.25 if liquids else 1.50          # principal factor on L
    bump = 0.5 if storage else 0.0          # companion increase on L

    rows = []

    def add(case, dead_f, principal, companions):
        for comp in companions:
            terms = [(dead_f, "D")] + list(principal) + list(comp)
            effect = (dead_f * D
                      + sum(f * {"D": D, "L": L, "S": S, "W": W,
                                 "E": E}[s]
                            for f, s in list(principal) + list(comp)))
            rows.append({"Case": case,
                         "Combination": _assemble(terms),
                         "Effect": effect})

    # Case 1 - 1.4D
    add(1, 1.40, [], [[]])

    # Case 2 - (1.25D or 0.9D) + 1.5L, companion 1.0S or 0.4W
    for dead_f in (1.25, 0.90):
        add(2, dead_f, [(aL, "L")],
            [[], [(1.00, "S")], [(0.40, "W")], [(-0.40, "W")]])

    # Case 3 - (1.25D or 0.9D) + 1.5S, companion 1.0L or 0.4W
    for dead_f in (1.25, 0.90):
        add(3, dead_f, [(1.50, "S")],
            [[], [(1.00 + bump, "L")], [(0.40, "W")], [(-0.40, "W")]])

    # Case 4 - (1.25D or 0.9D) + 1.4W, companion 0.5L or 0.5S
    for dead_f in (1.25, 0.90):
        for wf in (1.40, -1.40):
            add(4, dead_f, [(wf, "W")],
                [[], [(0.50 + bump, "L")], [(0.50, "S")]])

    # Case 5 - 1.0D + 1.0E, companion 0.5L + 0.25S
    for ef in (1.00, -1.00):
        add(5, 1.00, [(ef, "E")],
            [[], [(0.50 + bump, "L"), (0.25, "S")]])

    return rows


def sls_combinations(D, L, S, W, storage=False):
    """Table 4.1.3.4, deflection for materials not subject to creep.
    The companion factor of 0.35 on L rises to 0.5 for storage areas,
    equipment areas and service rooms (Note (2) to the Table)."""
    cL = 0.50 if storage else 0.35
    rows = []

    def add(case, principal, companions):
        for comp in companions:
            terms = [(1.00, "D")] + list(principal) + list(comp)
            effect = (D + sum(f * {"D": D, "L": L, "S": S, "W": W}[s]
                              for f, s in list(principal) + list(comp)))
            rows.append({"Case": case,
                         "Combination": _assemble(terms),
                         "Effect": effect})

    add(1, [(1.00, "L")],
        [[], [(0.30, "W")], [(-0.30, "W")], [(0.35, "S")]])
    for wf in (1.00, -1.00):
        add(2, [(wf, "W")], [[], [(cL, "L")], [(0.35, "S")]])
    add(3, [(1.00, "S")],
        [[], [(0.30, "W")], [(-0.30, "W")], [(cL, "L")]])
    return rows


# ======================================================================
# SECTION 4 - ENGINE: SEISMIC (Article 4.1.8)
# ======================================================================

@st.cache_data(show_spinner=False, ttl=86400)
def fetch_nbcc_spectrum(lat, lon, site):
    """Query the NRCan CanSHM GraphQL service for NBCC 2020 5%-damped
    spectral accelerations, 2% probability of exceedance in 50 years.

    site is either a Site Class letter (A to F), which uses the
    siteDesignationsXs branch, or a numeric Vs30 in m/s, which uses
    the siteDesignationsXv branch. Pass 450 to obtain Sa(T, X450).
    """
    if requests is None:
        return None, "requests is not installed"
    url = "https://www.earthquakescanada.nrcan.gc.ca/api/canshm/graphql"
    try:
        vs30 = float(site)
        designation = "siteDesignationsXv(vs30:%.0f, poe50:[2.0])" % vs30
    except (TypeError, ValueError):
        designation = ("siteDesignationsXs(siteClass:%s, poe50:[2.0])"
                       % str(site).upper())
    query = ("{ NBC2020(latitude:%.3f, longitude:%.3f) "
             "{ X: %s "
             "{ sa0p2 sa0p5 sa1p0 sa2p0 sa5p0 sa10p0 pga }}}"
             % (float(lat), float(lon), designation))
    try:
        resp = requests.post(url, json={"query": query}, timeout=25)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        return None, "API request failed: %s" % exc

    found = _find_spectrum(payload)
    if found is None:
        return None, "No spectral values in the API response"
    return found, ""


def _find_spectrum(node):
    """Walk an arbitrary JSON structure and return the first dict
    that carries the expected spectral keys."""
    if isinstance(node, dict):
        if "sa0p2" in node:
            return {
                "S(0.2)": _num(node.get("sa0p2")),
                "S(0.5)": _num(node.get("sa0p5")),
                "S(1.0)": _num(node.get("sa1p0")),
                "S(2.0)": _num(node.get("sa2p0")),
                "S(5.0)": _num(node.get("sa5p0")),
                "S(10.0)": _num(node.get("sa10p0")),
                "PGA": _num(node.get("pga")),
            }
        for value in node.values():
            hit = _find_spectrum(value)
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for value in node:
            hit = _find_spectrum(value)
            if hit is not None:
                return hit
    return None


def _num(value):
    if isinstance(value, list):
        value = value[0] if value else None
    try:
        return float(value)
    except Exception:
        return float("nan")


# ======================================================================
# SECTION 5 - 3D VIEWER PAYLOAD
# ======================================================================

def build_payload(geom, wind, snow, seismic):
    """Assemble the geometry + results payload consumed by the
    Three.js viewer. Same spirit as viewer_3d.build_payload()."""
    return {
        "geom": geom,
        "wind": wind,
        "snow": snow,
        "seismic": seismic,
    }


VIEWER_HTML = r"""
<div id="wrap">
  <div id="bar">
    <button class="tb active" data-mode="wind">Wind</button>
    <button class="tb" data-mode="snow">Snow</button>
    <button class="tb" data-mode="seismic">Seismic</button>
    <span class="sp"></span>
    <button class="tb tog" id="spin">Spin</button>
    <button class="tb tog" id="dims">Dims</button>
    <button class="tb" id="fit">Fit</button>
  </div>
  <div id="cv"></div>
  <div id="leg"></div>
</div>
<style>
  #wrap{position:relative;width:100%;height:__H__px;
        background:#0d1117;border-radius:10px;overflow:hidden;
        font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
  #cv{position:absolute;inset:0;}
  #bar{position:absolute;top:0;left:0;right:0;z-index:5;display:flex;
       gap:6px;padding:8px;align-items:center;
       background:linear-gradient(#0d1117ee,#0d111700);}
  .tb{background:#1f2733;color:#9fb0c4;border:1px solid #2d3949;
      border-radius:6px;padding:5px 11px;font-size:12px;cursor:pointer;}
  .tb.active{background:#1d4ed8;color:#fff;border-color:#3b82f6;}
  .tb.on{background:#0f766e;color:#fff;border-color:#14b8a6;}
  .sp{flex:1;}
  #leg{position:absolute;left:10px;bottom:10px;z-index:5;color:#9fb0c4;
       font-size:11px;line-height:1.6;background:#0d1117cc;padding:8px 10px;
       border-radius:6px;border:1px solid #1f2733;max-width:62%;}
  #leg b{color:#e6edf3;}
  .sw{display:inline-block;width:10px;height:10px;border-radius:2px;
      margin-right:5px;vertical-align:-1px;}
</style>
<script type="importmap">
{"imports":{
  "three":"https://unpkg.com/three@0.160.0/build/three.module.js",
  "three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"
}}
</script>
<script type="module">
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const P = __PAYLOAD__;
const G = P.geom;

// ---- view-state persistence ---------------------------------------
// Streamlit rebuilds this iframe on every rerun, so the camera, the
// active layer and the toggles are saved to sessionStorage on every
// interaction and restored on the next mount. Camera coordinates are
// stored as ratios of the model size so a geometry change still
// frames sensibly.
const SKEY = "ifs_wsz_viewer_v1";
let SAVED = null;
try { SAVED = JSON.parse(sessionStorage.getItem(SKEY) || "null"); }
catch (e0) { SAVED = null; }
let curMode = (SAVED && SAVED.mode) || "wind";
if (["wind", "snow", "seismic"].indexOf(curMode) < 0) curMode = "wind";
let saveTimer = null;
function persist(){
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      sessionStorage.setItem(SKEY, JSON.stringify({
        mode: curMode,
        spin: document.getElementById("spin")
              .classList.contains("on"),
        dims: document.getElementById("dims")
              .classList.contains("on"),
        cam: {
          px: camera.position.x / span,
          py: camera.position.y / span,
          pz: camera.position.z / span,
          tx: controls.target.x / span,
          ty: controls.target.y / span,
          tz: controls.target.z / span
        }
      }));
    } catch (e1) {}
  }, 150);
}

const host = document.getElementById("cv");
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);

const camera = new THREE.PerspectiveCamera(
  45, host.clientWidth / host.clientHeight, 0.1, 4000);
const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(host.clientWidth, host.clientHeight);
host.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.AmbientLight(0xffffff, 0.62));
const key = new THREE.DirectionalLight(0xffffff, 0.85);
key.position.set(1, 1.4, 0.8);
scene.add(key);
const rim = new THREE.DirectionalLight(0x88aaff, 0.35);
rim.position.set(-1, 0.5, -0.9);
scene.add(rim);

const W = G.W, L = G.L, He = G.He, Hr = G.Hr;
const HT = He + Hr;
const span = Math.max(W, L, HT);

// ---- grid ----------------------------------------------------------
const grid = new THREE.GridHelper(span * 3, 30, 0x2d3949, 0x1a2130);
grid.position.y = 0;
scene.add(grid);

// ---- helpers -------------------------------------------------------
function ramp(t){
  // -1 (suction, blue) .. 0 (grey) .. +1 (pressure, red)
  t = Math.max(-1, Math.min(1, t));
  const c = new THREE.Color();
  if (t >= 0) c.setHSL(0.02, 0.85, 0.30 + 0.28 * t);
  else        c.setHSL(0.58, 0.85, 0.30 + 0.28 * (-t));
  return c;
}

function label(text, color){
  const cv = document.createElement("canvas");
  const ctx = cv.getContext("2d");
  const pad = 12, fs = 46;
  ctx.font = "600 " + fs + "px -apple-system, Segoe UI, sans-serif";
  cv.width = ctx.measureText(text).width + pad * 2;
  cv.height = fs + pad * 2;
  const c2 = cv.getContext("2d");
  c2.font = "600 " + fs + "px -apple-system, Segoe UI, sans-serif";
  c2.fillStyle = "rgba(13,17,23,0.82)";
  c2.fillRect(0, 0, cv.width, cv.height);
  c2.fillStyle = color || "#e6edf3";
  c2.textBaseline = "middle";
  c2.fillText(text, pad, cv.height / 2);
  const tex = new THREE.CanvasTexture(cv);
  tex.minFilter = THREE.LinearFilter;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, depthTest: false, transparent: true}));
  sp.scale.set(cv.width / cv.height * span * 0.055, span * 0.055, 1);
  sp.renderOrder = 999;
  return sp;
}

function quad(a, b, c, d, colour, opacity){
  const g = new THREE.BufferGeometry();
  const v = new Float32Array([
    a[0],a[1],a[2], b[0],b[1],b[2], c[0],c[1],c[2],
    a[0],a[1],a[2], c[0],c[1],c[2], d[0],d[1],d[2]]);
  g.setAttribute("position", new THREE.BufferAttribute(v, 3));
  g.computeVertexNormals();
  const m = new THREE.MeshStandardMaterial({
    color: colour, side: THREE.DoubleSide, transparent: true,
    opacity: opacity === undefined ? 0.92 : opacity,
    roughness: 0.75, metalness: 0.05});
  return new THREE.Mesh(g, m);
}

function edges(pts, colour){
  const g = new THREE.BufferGeometry().setFromPoints(
    pts.map(p => new THREE.Vector3(p[0], p[1], p[2])));
  return new THREE.Line(g, new THREE.LineBasicMaterial({color: colour}));
}

// ---- building shell ------------------------------------------------
const hw = W / 2, hl = L / 2;
const shell = new THREE.Group();
const skin = new THREE.MeshStandardMaterial({
  color: 0x8899aa, transparent: true, opacity: 0.16,
  side: THREE.DoubleSide, roughness: 0.9});

const wallGeo = new THREE.BoxGeometry(W, He, L);
const walls = new THREE.Mesh(wallGeo, skin);
walls.position.y = He / 2;
shell.add(walls);

// gable roof
const ridge = He + Hr;
const roofA = quad([-hw, He, -hl], [-hw, He, hl], [0, ridge, hl],
                   [0, ridge, -hl], 0x8899aa, 0.16);
const roofB = quad([hw, He, -hl], [hw, He, hl], [0, ridge, hl],
                   [0, ridge, -hl], 0x8899aa, 0.16);
shell.add(roofA, roofB);
const gableN = quad([-hw, He, -hl], [hw, He, -hl], [0, ridge, -hl],
                    [0, ridge, -hl], 0x8899aa, 0.16);
const gableS = quad([-hw, He, hl], [hw, He, hl], [0, ridge, hl],
                    [0, ridge, hl], 0x8899aa, 0.16);
shell.add(gableN, gableS);

const outline = new THREE.Group();
[[[-hw,0,-hl],[hw,0,-hl],[hw,0,hl],[-hw,0,hl],[-hw,0,-hl]],
 [[-hw,He,-hl],[hw,He,-hl],[hw,He,hl],[-hw,He,hl],[-hw,He,-hl]],
 [[0,ridge,-hl],[0,ridge,hl]],
 [[-hw,He,-hl],[0,ridge,-hl],[hw,He,-hl]],
 [[-hw,He,hl],[0,ridge,hl],[hw,He,hl]],
 [[-hw,0,-hl],[-hw,He,-hl]],[[hw,0,-hl],[hw,He,-hl]],
 [[hw,0,hl],[hw,He,hl]],[[-hw,0,hl],[-hw,He,hl]]
].forEach(p => outline.add(edges(p, 0x5b7290)));
shell.add(outline);
scene.add(shell);

// ---- WIND layer ----------------------------------------------------
const windGrp = new THREE.Group();
const z = G.z;
const maxP = Math.max(0.001, P.wind.pmax_abs);

function face(name, corners){
  const rec = P.wind.surfaces[name];
  if (!rec) return;
  const t = rec.p / maxP;
  const m = quad(corners[0], corners[1], corners[2], corners[3],
                 ramp(t), 0.80);
  m.userData = {name: name, p: rec.p, cgcp: rec.cgcp};
  windGrp.add(m);
  const cx = (corners[0][0] + corners[2][0]) / 2;
  const cy = (corners[0][1] + corners[2][1]) / 2;
  const cz = (corners[0][2] + corners[2][2]) / 2;
  const lb = label(name + "  " + rec.p.toFixed(2) + " kPa",
                   rec.p >= 0 ? "#ffb4a8" : "#a8d0ff");
  lb.position.set(cx * 1.04, cy + span * 0.03, cz * 1.04);
  windGrp.add(lb);
}

// windward wall (-X face), split into end zone 1E and interior 1
const zc = Math.min(z, L * 0.45);
face("1",  [[-hw,0,-hl+zc],[-hw,0,hl-zc],[-hw,He,hl-zc],[-hw,He,-hl+zc]]);
face("1E", [[-hw,0,-hl],[-hw,0,-hl+zc],[-hw,He,-hl+zc],[-hw,He,-hl]]);
// windward roof plane (2 / 2E)
face("2",  [[-hw,He,-hl+zc],[-hw,He,hl-zc],[0,ridge,hl-zc],[0,ridge,-hl+zc]]);
face("2E", [[-hw,He,-hl],[-hw,He,-hl+zc],[0,ridge,-hl+zc],[0,ridge,-hl]]);
// leeward roof plane (3 / 3E)
face("3",  [[hw,He,-hl+zc],[hw,He,hl-zc],[0,ridge,hl-zc],[0,ridge,-hl+zc]]);
face("3E", [[hw,He,-hl],[hw,He,-hl+zc],[0,ridge,-hl+zc],[0,ridge,-hl]]);
// leeward wall (+X face) 4 / 4E
face("4",  [[hw,0,-hl+zc],[hw,0,hl-zc],[hw,He,hl-zc],[hw,He,-hl+zc]]);
face("4E", [[hw,0,-hl],[hw,0,-hl+zc],[hw,He,-hl+zc],[hw,He,-hl]]);
// side walls 5 / 6 (Load Case B)
face("5",  [[-hw,0,-hl],[hw,0,-hl],[hw,He,-hl],[-hw,He,-hl]]);
face("6",  [[-hw,0,hl],[hw,0,hl],[hw,He,hl],[-hw,He,hl]]);

// wind direction arrow
const dir = new THREE.ArrowHelper(
  new THREE.Vector3(1, 0, 0),
  new THREE.Vector3(-hw - span * 0.55, He * 0.55, 0),
  span * 0.36, 0x38bdf8, span * 0.09, span * 0.05);
windGrp.add(dir);
const dl = label("WIND  q = " + P.wind.q.toFixed(3) + " kPa", "#7dd3fc");
dl.position.set(-hw - span * 0.55, He * 0.55 + span * 0.10, 0);
windGrp.add(dl);
scene.add(windGrp);

// ---- SNOW layer ----------------------------------------------------
const snowGrp = new THREE.Group();
const sThick = Math.max(span * 0.012, P.snow.S * 0.42);
const snowMat = new THREE.MeshStandardMaterial({
  color: 0xdfe9f5, roughness: 0.95, metalness: 0.0,
  side: THREE.DoubleSide,
  transparent: true, opacity: 0.94});
function slab(x0, x1, y0, y1){
  const g = new THREE.BufferGeometry();
  const nx = -(y1 - y0), ny = (x1 - x0);
  const nl = Math.hypot(nx, ny) || 1;
  const ox = nx / nl * sThick, oy = ny / nl * sThick;
  const pts = [];
  const A=[x0,y0,-hl], B=[x1,y1,-hl], C=[x1+ox,y1+oy,-hl], D=[x0+ox,y0+oy,-hl];
  const A2=[x0,y0,hl], B2=[x1,y1,hl], C2=[x1+ox,y1+oy,hl], D2=[x0+ox,y0+oy,hl];
  function push(a,b,c){ pts.push(a[0],a[1],a[2], b[0],b[1],b[2], c[0],c[1],c[2]); }
  push(A,B,C); push(A,C,D);
  push(A2,B2,C2); push(A2,C2,D2);
  push(D,C,C2); push(D,C2,D2);
  push(A,B,B2); push(A,B2,A2);
  push(B,C,C2); push(B,C2,B2);
  g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pts),3));
  g.computeVertexNormals();
  return new THREE.Mesh(g, snowMat);
}
snowGrp.add(slab(-hw, 0, He, ridge));
snowGrp.add(slab(0, hw, ridge, He));

// Distributed load: a run of downward arrows over each slope, drawn
// on a grid so the intensity reads from every viewing angle.
const nAcross = 7, nAlong = 5;
const arrowLen = span * 0.10 + span * 0.16 *
                 Math.min(1, P.snow.S / 4.0);
function snowArrows(x0, y0, x1, y1){
  for (let i = 0; i < nAcross; i++){
    const t = (i + 0.5) / nAcross;
    const x = x0 + (x1 - x0) * t;
    const y = y0 + (y1 - y0) * t;
    for (let j = 0; j < nAlong; j++){
      const zz = -hl + L * (j + 0.5) / nAlong;
      const ar = new THREE.ArrowHelper(
        new THREE.Vector3(0, -1, 0),
        new THREE.Vector3(x, y + sThick + arrowLen, zz),
        arrowLen, 0x7dd3fc, arrowLen * 0.30, arrowLen * 0.18);
      snowGrp.add(ar);
    }
  }
  // load line joining the arrow tails, the usual drafting convention
  const top = [];
  for (let j = 0; j <= 1; j++){
    top.push(new THREE.Vector3(j ? x1 : x0,
                               (j ? y1 : y0) + sThick + arrowLen, -hl));
  }
  snowGrp.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(top),
    new THREE.LineBasicMaterial({color: 0x38bdf8})));
  const top2 = top.map(p => new THREE.Vector3(p.x, p.y, hl));
  snowGrp.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(top2),
    new THREE.LineBasicMaterial({color: 0x38bdf8})));
}
snowArrows(-hw, He, 0, ridge);
snowArrows(0, ridge, hw, He);

const sl = label("S = " + P.snow.S.toFixed(2) + " kPa", "#dfe9f5");
sl.position.set(0, ridge + span * 0.12, 0);
snowGrp.add(sl);
const sl2 = label("Cb=" + P.snow.Cb.toFixed(2) + "  Cw=" + P.snow.Cw.toFixed(2) +
                  "  Cs=" + P.snow.Cs.toFixed(2) + "  Ca=" + P.snow.Ca.toFixed(2),
                  "#9fb0c4");
sl2.position.set(0, ridge + span * 0.05, 0);
snowGrp.add(sl2);
snowGrp.visible = false;
scene.add(snowGrp);

// ---- SEISMIC layer -------------------------------------------------
const seisGrp = new THREE.Group();
const VW = P.seismic.V_over_W;
const FS = P.seismic.forces || [];
let fmax = 0.001;
FS.forEach(f => { fmax = Math.max(fmax, Math.abs(f.Fx)); });

if (FS.length){
  // storey forces to scale, plus the Fx profile envelope
  const prof = [];
  FS.forEach(f => {
    const len = span * 0.06 + span * 0.32 * (Math.abs(f.Fx) / fmax);
    const ar = new THREE.ArrowHelper(
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(-hw - len, f.h, 0),
      len, 0xf59e0b, span * 0.05, span * 0.028);
    seisGrp.add(ar);
    prof.push(new THREE.Vector3(-hw - len, f.h, 0));
    const lb = label(f.level + "  " + f.Fx.toFixed(1) + " kN", "#fcd34d");
    lb.position.set(-hw - len - span * 0.16, f.h, 0);
    seisGrp.add(lb);
  });
  prof.unshift(new THREE.Vector3(-hw, 0, 0));
  prof.push(new THREE.Vector3(-hw, FS[FS.length - 1].h, 0));
  seisGrp.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(prof),
    new THREE.LineBasicMaterial({color: 0xfbbf24})));
} else {
  const ar = new THREE.ArrowHelper(
    new THREE.Vector3(1, 0, 0),
    new THREE.Vector3(-hw - span * 0.3, He * 0.6, 0),
    span * 0.3, 0xf59e0b, span * 0.05, span * 0.028);
  seisGrp.add(ar);
}

const base = new THREE.Mesh(
  new THREE.BoxGeometry(W * 1.12, span * 0.012, L * 1.12),
  new THREE.MeshStandardMaterial({color: 0xf59e0b, transparent: true,
                                  opacity: 0.55}));
base.position.y = 0;
seisGrp.add(base);
const vl = label("V = " + P.seismic.V.toFixed(1) + " kN   (V/W = " +
                 VW.toFixed(4) + ")", "#fcd34d");
vl.position.set(0, -span * 0.09, 0);
seisGrp.add(vl);
const vl2 = label("SC" + P.seismic.SC + "   Ta = " +
                  P.seismic.Ta.toFixed(3) + " s   S(Ta) = " +
                  P.seismic.S_Ta.toFixed(4) + " g   Mv = " +
                  P.seismic.Mv.toFixed(2), "#9fb0c4");
vl2.position.set(0, -span * 0.16, 0);
seisGrp.add(vl2);
seisGrp.visible = false;
scene.add(seisGrp);

// ---- dimensions ----------------------------------------------------
const dimGrp = new THREE.Group();
function dim(a, b, text, off){
  const A = new THREE.Vector3(a[0]+off[0], a[1]+off[1], a[2]+off[2]);
  const B = new THREE.Vector3(b[0]+off[0], b[1]+off[1], b[2]+off[2]);
  const mat = new THREE.LineBasicMaterial({color: 0x64748b});
  dimGrp.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([A, B]), mat));
  dimGrp.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(
    [new THREE.Vector3(a[0],a[1],a[2]), A]), mat));
  dimGrp.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(
    [new THREE.Vector3(b[0],b[1],b[2]), B]), mat));
  const lb = label(text, "#cbd5e1");
  lb.position.copy(A.clone().add(B).multiplyScalar(0.5));
  dimGrp.add(lb);
}
const o = span * 0.14;
dim([-hw,0,hl], [hw,0,hl],
    "W (transverse) = " + W.toFixed(2) + " m", [0,-o*0.35,o]);
dim([hw,0,-hl], [hw,0,hl],
    "L (longitudinal) = " + L.toFixed(2) + " m", [o,-o*0.35,0]);
dim([hw,0,hl], [hw,He,hl],
    "He (eaves) = " + He.toFixed(2) + " m", [o*0.6,0,o*0.6]);
dim([hw,He,hl], [0,ridge,hl],
    "Hr (roof) = " + Hr.toFixed(2) + " m", [o*0.4,0,o*0.6]);
if (G.ws){
  dim([-hw,He,-hl], [0,ridge,-hl],
      "sloped w/2 = " + (G.ws / 2).toFixed(2) + " m", [0,o*0.25,-o*0.5]);
}
dimGrp.visible = false;
scene.add(dimGrp);

// ---- camera --------------------------------------------------------
camera.position.set(span * 1.7, span * 1.15, span * 1.9);
controls.target.set(0, HT * 0.42, 0);
if (SAVED && SAVED.cam && isFinite(SAVED.cam.px)){
  camera.position.set(SAVED.cam.px * span, SAVED.cam.py * span,
                      SAVED.cam.pz * span);
  controls.target.set(SAVED.cam.tx * span, SAVED.cam.ty * span,
                      SAVED.cam.tz * span);
}
controls.update();
controls.addEventListener("change", persist);

// ---- UI ------------------------------------------------------------
const legend = document.getElementById("leg");
function setLegend(mode){
  if (mode === "wind"){
    legend.innerHTML =
      "<b>Wind - Cl. 4.1.7</b><br>" +
      "<span class='sw' style='background:#c0392b'></span>positive (pressure) &nbsp; " +
      "<span class='sw' style='background:#1f6feb'></span>negative (suction)<br>" +
      "End zone z = " + G.z.toFixed(2) + " m &nbsp; Ce = " + P.wind.Ce.toFixed(3) +
      " &nbsp; Cg = " + P.wind.Cg.toFixed(2) + "<br>" +
      "Peak |p| = " + P.wind.pmax_abs.toFixed(3) + " kPa (external, Load Case " +
      P.wind.governing_case + ")";
  } else if (mode === "snow"){
    legend.innerHTML =
      "<b>Snow - Cl. 4.1.6.2</b><br>S = Is [ Ss (Cb Cw Cs Ca) + Sr ]<br>" +
      "Ss = " + P.snow.Ss.toFixed(2) + " kPa &nbsp; Sr = " + P.snow.Sr.toFixed(2) +
      " kPa &nbsp; Is = " + P.snow.Is.toFixed(2) + "<br><b>S = " +
      P.snow.S.toFixed(2) + " kPa</b> uniformly distributed over both " +
      "slopes<br>Slab depth and arrow length scale with S. " +
      "Cb = " + P.snow.Cb.toFixed(2) + " &nbsp; Cw = " +
      P.snow.Cw.toFixed(2) + " &nbsp; Cs = " + P.snow.Cs.toFixed(2) +
      " &nbsp; Ca = " + P.snow.Ca.toFixed(2);
  } else {
    legend.innerHTML =
      "<b>Seismic - Cl. 4.1.8</b><br>V = S(Ta) Mv IE W / (Rd Ro)<br>" +
      "Site Class " + P.seismic.site_class + " &nbsp; Rd = " +
      P.seismic.Rd.toFixed(2) + " &nbsp; Ro = " + P.seismic.Ro.toFixed(2) +
      "<br><b>V / W = " + P.seismic.V_over_W.toFixed(4) + "</b>" +
      " &nbsp; arrows show relative storey force";
  }
}
function applyMode(m){
  curMode = m;
  document.querySelectorAll(".tb[data-mode]").forEach(
    x => x.classList.toggle("active", x.dataset.mode === m));
  windGrp.visible = (m === "wind");
  snowGrp.visible = (m === "snow");
  seisGrp.visible = (m === "seismic");
  setLegend(m);
  persist();
}
applyMode(curMode);

document.querySelectorAll(".tb[data-mode]").forEach(b => {
  b.onclick = () => applyMode(b.dataset.mode);
});
document.getElementById("spin").onclick = function(){
  this.classList.toggle("on");
  controls.autoRotate = this.classList.contains("on");
  controls.autoRotateSpeed = 1.2;
  persist();
};
document.getElementById("dims").onclick = function(){
  this.classList.toggle("on");
  dimGrp.visible = this.classList.contains("on");
  persist();
};
if (SAVED){
  if (SAVED.spin){
    const sb = document.getElementById("spin");
    sb.classList.add("on");
    controls.autoRotate = true;
    controls.autoRotateSpeed = 1.2;
  }
  if (SAVED.dims){
    document.getElementById("dims").classList.add("on");
    dimGrp.visible = true;
  }
}
function fitView(){
  camera.position.set(span * 1.7, span * 1.15, span * 1.9);
  controls.target.set(0, HT * 0.42, 0);
  controls.update();
}
document.getElementById("fit").onclick = fitView;

addEventListener("resize", () => {
  camera.aspect = host.clientWidth / host.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(host.clientWidth, host.clientHeight);
});

(function loop(){
  requestAnimationFrame(loop);
  controls.update();
  renderer.render(scene, camera);
})();
</script>
"""


def render_viewer(payload, height=620):
    html = VIEWER_HTML.replace("__PAYLOAD__", json.dumps(payload))
    html = html.replace("__H__", str(height))
    components.html(html, height=height + 10, scrolling=False)


# ======================================================================
# SECTION 5B - SYMBOL GLOSSARY
#
# Plain-language definitions surfaced two ways: as help= tooltips on the
# input widgets (the little grey question mark), and as hover "?" marks
# beside computed symbols via explain(). Keyed by the display label.
# ======================================================================

GLOSS = {
    "Vs30": ("Time-averaged shear-wave velocity of the top 30 m of "
             "ground, in m/s, from the geotechnical or geophysical "
             "investigation. Stiffer ground has a higher Vs30 and "
             "amplifies shaking less. Roughly: rock is above 760, "
             "very dense soil 360 to 760, stiff soil 180 to 360, "
             "soft soil below 180. The hazard model reference ground "
             "is Vs30 = 450 m/s."),
    "N60": ("Standard Penetration Test blow count corrected to 60 "
            "percent hammer energy: the number of hammer blows to "
            "drive the split-spoon sampler 0.3 m, averaged over the "
            "top 30 m. It comes from the boreholes in the geotech "
            "report. Higher = denser soil: N60 above 50 reads as "
            "Site Class C, 15 to 50 as D, 10 to 15 as E."),
    "su": ("Undrained shear strength of cohesive soil (clay), in "
           "kPa, from lab or vane tests in the geotech report. "
           "Higher = stiffer clay: above 100 kPa reads as Site "
           "Class C, 50 to 100 as D, 40 to 50 as E."),
    "Sa(T,X)": ("5 percent damped spectral acceleration at period T "
                "for site designation X, in units of g, at a 2 "
                "percent in 50 year probability of exceedance. This "
                "is what a single-degree-of-freedom oscillator with "
                "period T would feel at this site."),
    "S(T)": ("The design spectral acceleration at period T, Table "
             "4.1.8.4-C. Equal to Sa(T,X) at the tabulated periods, "
             "except that S(0.2) takes the greater of Sa(0.2) and "
             "Sa(0.5)."),
    "X450": ("The reference ground condition of the 2020 hazard "
             "model: Vs30 = 450 m/s. Sa(T,X450) is the hazard on "
             "reference ground, used for Fa, Fv and the simplified "
             "method."),
    "Fa": ("Short-period site coefficient, Cl. 4.1.8.4.(7): "
           "S(0.2) on this site divided by Sa(0.2) on reference "
           "ground. Used by the material standards of Section 4.3, "
           "not by the base shear here."),
    "Fv": ("Long-period site coefficient, Cl. 4.1.8.4.(7): S(1.0) "
           "over Sa(1.0,X450). Companion to Fa."),
    "IE": ("Earthquake importance factor, Table 4.1.8.5-A: 0.8 Low, "
           "1.0 Normal, 1.3 High (schools, community centres), 1.5 "
           "Post-disaster (hospitals, fire stations). Scales the "
           "design force by the consequence of failure."),
    "SC": ("Seismic Category, Table 4.1.8.5-B: SC1 (lowest) to SC4 "
           "(highest), from IE times S(0.2) and IE times S(1.0), "
           "taking the more severe. Gates which analysis methods "
           "and SFRS restrictions apply."),
    "Ta": ("Fundamental lateral period of the building, in seconds: "
           "the time for one full sway cycle in its first mode. "
           "Estimated from the empirical formulas of Cl. "
           "4.1.8.11.(3), or from a mechanics model capped against "
           "them. Longer period generally means lower spectral "
           "acceleration."),
    "hn": ("Height in metres from the base (grade) to the roof "
           "level n, the uppermost level of the main structure."),
    "Rd": ("Ductility-related force modification factor, Table "
           "4.1.8.9. How much the SFRS can yield and dissipate "
           "energy without losing strength: 1.0 for brittle systems "
           "up to 5.0 for ductile moment frames. The elastic demand "
           "is divided by Rd because a yielding system rides out "
           "the shaking at lower force."),
    "Ro": ("Overstrength-related force modification factor, Table "
           "4.1.8.9. The dependable reserve beyond the design "
           "point: material overstrength, oversizing, strain "
           "hardening. Typically 1.3 to 1.7."),
    "Mv": ("Higher-mode factor, Table 4.1.8.11. Long-period "
           "buildings respond in more than the first sway mode, "
           "which raises the base shear above the S(Ta) estimate; "
           "Mv scales it back up. 1.0 for short buildings."),
    "J": ("Base overturning reduction factor, Table 4.1.8.11. The "
          "peak storey forces do not all act in the same instant, "
          "so summing full Fx values overstates the base moment; "
          "J trims it (Jx varies over height per Cl. 4.1.8.11.(8))."),
    "W": ("Seismic weight, Art. 4.1.8.2: dead load, plus 25 percent "
          "of the snow load, plus 60 percent of storage loads, plus "
          "the full contents of tanks. The mass that actually "
          "shakes."),
    "V": ("Design base shear from the Equivalent Static Force "
          "Procedure: the total lateral earthquake force at the "
          "base, shared out over the height as the Fx forces."),
    "Ft": ("Concentrated top force, Cl. 4.1.8.11.(7)(a): a slice "
           "of V applied at the roof to stand in for whip-like "
           "higher-mode response. Zero for Ta up to 0.7 s, "
           "otherwise 0.07 Ta V, capped at 0.25 V."),
    "Fx": ("Lateral force applied at level x: the level's share of "
           "V in proportion to its weight times height, plus Ft at "
           "the top."),
    "Dnx": ("Plan dimension of the building at level x "
            "perpendicular to the direction of the earthquake "
            "loading, in metres, Cl. 4.1.8.2. Sets the accidental "
            "eccentricity 0.10 Dnx."),
    "ex": ("Computed eccentricity between the centre of mass (where "
           "the inertia force acts) and the centre of rigidity "
           "(where the SFRS pushes back) at level x. A torsionally "
           "balanced plan has ex near zero."),
    "Bx": ("Torsional sensitivity ratio, Cl. 4.1.8.11.(10): the "
           "worst corner displacement over the average of the two "
           "extreme corners, with the forces applied at plus and "
           "minus 0.10 Dnx. B above 1.7 is a Type 7 irregularity."),
    "Fs": ("Site coefficient for the simplified method, Cl. "
           "4.1.8.1.(2)(b): 1.0 rock, 1.6 medium, 2.8 soft, from "
           "N60 or su in the top 30 m below the foundations."),
    "Rs": ("Combined force reduction for the simplified method: "
           "1.5 normally, 1.0 where a storey is weaker than the "
           "one above or the SFRS is unreinforced masonry."),
    "Ts": ("Fundamental period estimate for the simplified method, "
           "Cl. 4.1.8.1.(7). Same empirical forms as Ta."),
    "Vs": ("Simplified-method base shear, Cl. 4.1.8.1.(7)."),
    "Wp": ("Weight of the appendage or cantilevered element being "
           "checked: a parapet, a canopy, a rooftop unit."),
    "hs": ("Interstorey height: floor-to-floor height of the "
           "storey being checked, in mm here."),
    "delta": ("Interstorey deflection from the elastic analysis "
              "under the reduced seismic forces, in mm: the "
              "difference in lateral displacement between the top "
              "and bottom of the storey, including torsion."),
}


def qmark(text):
    safe = str(text).replace('"', "'")
    return ("<sup><span title=\"%s\" style='cursor:help;"
            "color:#1f6feb;font-weight:700'>&nbsp;?</span></sup>"
            % safe)


def explain(*symbols):
    """A line of symbols, each with a hover question mark."""
    parts = []
    for s in symbols:
        if s in GLOSS:
            parts.append("<b>%s</b>%s" % (s, qmark(GLOSS[s])))
    if not parts:
        return
    st.markdown("<p style='margin:0.1rem 0 0.5rem 0;font-size:0.86rem;"
                "opacity:0.85'>Hover a ? for what each symbol means: "
                + " &nbsp;&nbsp; ".join(parts) + "</p>",
                unsafe_allow_html=True)


# ======================================================================
# SECTION 6 - PAGE
# ======================================================================

st.title("NBCC 2020 - Wind, Snow and Seismic Loads")
st.caption("Division B, Part 4, Volume 1. Buildings. "
           "Climatic data from Table C-2, Appendix C.")

c2, c2_path, c2_tried = load_table_c2()
if c2.empty:
    st.error("%s was not found. Put it either beside app.py in the "
             "project root, or in the pages/ folder. No data/ folder "
             "is needed." % C2_FILENAME)
    with st.expander("Paths searched"):
        st.caption("Working directory: %s" % os.getcwd())
        st.caption("This page: %s" % _HERE)
        st.code("\n".join(c2_tried))
    st.stop()

LEFT, RIGHT = st.columns([1.25, 1.0], gap="large")

with LEFT:

    # ------------------------------------------------------------------
    st.header("1. Building Geometry")

    st.markdown("**Building envelope**")
    g1, g2 = st.columns(2)
    with g1:
        W_bldg = st.number_input(
            "W, transverse length of the building, across the ridge (m)",
            1.0, 300.0, 18.41, 0.01,
            help="Plan dimension perpendicular to the ridge line.")
        H_eaves = st.number_input(
            "He, height of the eaves above ground level (m)",
            1.0, 200.0, 11.40, 0.01,
            help="Measured from grade to the eaves line.")
    with g2:
        L_bldg = st.number_input(
            "L, longitudinal length of the building, along the ridge (m)",
            1.0, 600.0, 36.41, 0.01,
            help="Plan dimension parallel to the ridge line.")
        H_roof = st.number_input(
            "Hr, roof height, eaves to ridge (m)",
            0.0, 60.0, 2.907, 0.001,
            help="Vertical rise from the eaves line up to the ridge. "
                 "Not the total building height.")

    st.markdown("**Roof dimensions**")
    r1, r2, r3 = st.columns(3)
    with r1:
        W_roof_h = st.number_input(
            "w_h, roof horizontal (plan) width across the ridge (m)",
            1.0, 300.0, 17.59, 0.01,
            help="Horizontal projection of the roof, eaves to eaves. "
                 "This is the plan dimension used for the snow "
                 "characteristic length.")
    with r2:
        L_roof = st.number_input(
            "l, roof plan length along the ridge (m)",
            1.0, 600.0, 35.62, 0.01)
    with r3:
        use_sloped = st.checkbox("Enter the sloped width instead",
                                 value=False,
                                 help="Tick this if the roof is "
                                      "dimensioned up the slope rather "
                                      "than in plan.")

    H_total = H_eaves + H_roof
    least_dim = min(W_bldg, L_bldg)

    if use_sloped:
        W_roof_s = st.number_input(
            "w_s, roof sloped width, eaves to eaves over the ridge (m)",
            1.0, 400.0, 25.00, 0.01)
        # Slope is set by the rise and the sloped half-width.
        half_s = max(W_roof_s / 2.0, 1e-6)
        ratio = min(max(H_roof / half_s, -1.0), 1.0)
        alpha = math.degrees(math.asin(ratio))
        W_roof_h = 2.0 * math.sqrt(max(half_s ** 2 - H_roof ** 2, 0.0))
        alpha_expr = (r"\alpha = \arcsin\!\left(\frac{H_r}"
                      r"{0.5\,w_s}\right)")
        alpha_sub = (r"\arcsin\!\left(\frac{%.3f}{0.5 \times %.2f}"
                     r"\right)" % (H_roof, W_roof_s))
    else:
        alpha = math.degrees(math.atan(H_roof / (0.5 * W_roof_h)))
        W_roof_s = W_roof_h / math.cos(math.radians(alpha))
        alpha_expr = (r"\alpha = \arctan\!\left(\frac{H_r}"
                      r"{0.5\,w_h}\right)")
        alpha_sub = (r"\arctan\!\left(\frac{%.3f}{0.5 \times %.2f}"
                     r"\right)" % (H_roof, W_roof_h))

    slope_pct = 100.0 * math.tan(math.radians(alpha))
    A_plan = W_roof_h * L_roof
    A_slope = W_roof_s * L_roof

    st.latex(alpha_expr + r" = " + alpha_sub +
             r" = %.2f^\circ \quad (%.1f\%%\ \text{slope})"
             % (alpha, slope_pct))
    st.latex(r"w_h = %.2f\ \text{m (horizontal)} \qquad "
             r"w_s = \frac{w_h}{\cos\alpha} = %.2f\ \text{m (sloped)}"
             % (W_roof_h, W_roof_s))
    st.latex(r"\text{Half slope length} = \frac{w_s}{2} = %.2f\ "
             r"\text{m} \qquad A_{plan} = %.1f\ \text{m}^2 \qquad "
             r"A_{slope} = %.1f\ \text{m}^2"
             % (W_roof_s / 2.0, A_plan, A_slope))
    st.caption("Snow loads act on the horizontal projection, so the "
               "plan dimensions w_h and l govern Cl. 4.1.6.2. The "
               "sloped width w_s is what you sheet and purlin for.")

    # Reference height, Cl. 4.1.7.3.(6) and Note (3) to Fig. 4.1.7.6-A
    H_mid = (H_total + H_eaves) / 2.0
    href_basis = st.radio(
        "Reference height basis (Cl. 4.1.7.3.(6), Note (3) to "
        "Fig. 4.1.7.6-A)",
        ["Mid-height of the roof", "Eaves height (roof slope < 7 deg)"],
        horizontal=True, index=0)
    if href_basis.startswith("Eaves") and alpha >= 7.0:
        st.warning("The eaves height may only be substituted where the "
                   "roof slope is less than 7 deg. Slope is %.2f deg, "
                   "so the mid-height of the roof is used."
                   % alpha)
        href_basis = "Mid-height of the roof"

    H_ref_raw = H_mid if href_basis.startswith("Mid") else H_eaves
    H_ref = max(H_ref_raw, 6.0)
    z_end = end_zone_width(least_dim, H_eaves)

    if href_basis.startswith("Mid"):
        st.latex(r"h = \frac{H_e + (H_e + H_r)}{2}"
                 r" = \frac{%.2f + %.3f}{2} = %.3f \ \text{m}"
                 % (H_eaves, H_total, H_mid))
    else:
        st.latex(r"h = H_e = %.3f \ \text{m}"
                 r"\quad (\alpha = %.2f^\circ < 7^\circ)"
                 % (H_eaves, alpha))
    if H_ref > H_ref_raw + 1e-9:
        st.info("The reference height is taken as 6 m, the minimum of "
                "Cl. 4.1.7.3.(6)(a).")
    st.latex(r"h_{ref} = \max(%.3f,\ 6.0) = %.3f \ \text{m}"
             % (H_ref_raw, H_ref))
    st.latex(r"z = \min(0.1 D_{min},\, 0.4 H) \ \ge \ "
             r"\max(0.04 D_{min},\, 1.0) = %.2f \ \text{m}" % z_end)
    st.caption("Total building height H = He + Hr = %.3f m. "
               "Least horizontal dimension D_min = %.2f m."
               % (H_total, least_dim))

    # Kept for the snow characteristic length, which uses plan values.
    W_roof = W_roof_h

    # ------------------------------------------------------------------
    st.header("2. Site Location and Climatic Data")
    st.caption("NBCC 2020, Table C-2, Appendix C. The place name and "
               "the coordinates stay synchronised automatically: "
               "change the location and the coordinates are looked "
               "up, change the coordinates and the location is "
               "identified.")

    provinces = sorted(c2["province"].unique().tolist())

    # ---- synchronisation callbacks -----------------------------------
    # These run before the widgets are rebuilt on the next script pass,
    # which is the only point at which a widget key may be written.

    def _sync_from_place():
        df, _, _ = load_table_c2()
        provs = sorted(df["province"].unique().tolist())
        p = st.session_state.get("prov_sel", provs[0])
        here = sorted(df[df["province"] == p]["location"].tolist())
        if st.session_state.get("loc_sel") not in here:
            st.session_state["loc_sel"] = here[0]
        place = st.session_state["loc_sel"]
        glat, glon, glabel, gerr = geocode_forward(place, p)
        if glat is None:
            st.session_state["geo_label"] = ""
            st.session_state["geo_msg"] = (
                "warn", "Could not resolve %s, %s. %s Enter the "
                        "coordinates directly." % (place, p, gerr))
        else:
            st.session_state["site_lat"] = round(float(glat), 4)
            st.session_state["site_lon"] = round(float(glon), 4)
            st.session_state["geo_label"] = glabel
            st.session_state["geo_msg"] = (
                "ok", "Coordinates set from %s, %s." % (place, p))

    def _sync_from_coords():
        df, _, _ = load_table_c2()
        provs = sorted(df["province"].unique().tolist())
        glat = st.session_state.get("site_lat")
        glon = st.session_state.get("site_lon")
        place, gprov, glabel, gerr = geocode_reverse(glat, glon)
        st.session_state["geo_label"] = glabel
        if gerr or not place:
            st.session_state["geo_msg"] = (
                "warn", "Could not identify %.4f, %.4f. %s Select the "
                        "governing Table C-2 location manually."
                        % (glat, glon, gerr or "no place returned"))
            return
        norm_prov = normalise_province(gprov, provs)
        m_prov, m_loc, score = match_c2_location(df, place, norm_prov)
        if m_loc and score >= 0.60:
            st.session_state["prov_sel"] = m_prov
            st.session_state["loc_sel"] = m_loc
            st.session_state["geo_msg"] = (
                "ok", "%.4f, %.4f is %s. Nearest Table C-2 entry: "
                      "%s, %s." % (glat, glon, place, m_loc, m_prov))
        else:
            st.session_state["geo_msg"] = (
                "warn", "%.4f, %.4f is %s%s, which does not match a "
                        "Table C-2 entry closely enough to select "
                        "automatically. Closest entry is %s, %s. "
                        "Choose the governing location manually."
                        % (glat, glon, place,
                           ", " + norm_prov if norm_prov else "",
                           m_loc or "none", m_prov or "-"))

    # ---- defaults, set before any widget is instantiated --------------
    if "prov_sel" not in st.session_state:
        st.session_state["prov_sel"] = ("Alberta" if "Alberta"
                                        in provinces else provinces[0])
    if "loc_sel" not in st.session_state:
        st.session_state["loc_sel"] = "Calgary"
    if "site_lat" not in st.session_state:
        st.session_state["site_lat"] = 51.0500
    if "site_lon" not in st.session_state:
        st.session_state["site_lon"] = -114.0700
    if "geo_label" not in st.session_state:
        st.session_state["geo_label"] = ""
    if "geo_msg" not in st.session_state:
        st.session_state["geo_msg"] = None

    # First pass only: pull the coordinates for the default location so
    # that the two halves agree before anything is displayed.
    if not st.session_state.get("geo_first_done"):
        st.session_state["geo_first_done"] = True
        _sync_from_place()

    d1, d2 = st.columns(2)
    with d1:
        prov = st.selectbox("Province / Territory", provinces,
                            key="prov_sel", on_change=_sync_from_place)
    sub = c2[c2["province"] == prov].sort_values("location")
    locs = sub["location"].tolist()
    if st.session_state.get("loc_sel") not in locs:
        st.session_state["loc_sel"] = locs[0]
    with d2:
        loc = st.selectbox("Location", locs, key="loc_sel",
                           on_change=_sync_from_place)

    gc1, gc2 = st.columns(2)
    with gc1:
        lat = st.number_input("Latitude (deg N)", min_value=41.0,
                              max_value=84.0, step=0.0001,
                              format="%.4f", key="site_lat",
                              on_change=_sync_from_coords)
    with gc2:
        lon = st.number_input("Longitude (deg E, negative W)",
                              min_value=-142.0, max_value=-52.0,
                              step=0.0001, format="%.4f",
                              key="site_lon",
                              on_change=_sync_from_coords)

    msg = st.session_state.get("geo_msg")
    if msg:
        kind, text = msg
        (st.caption if kind == "ok" else st.warning)(text)
    if st.session_state.get("geo_label"):
        st.caption("Geocoder: %s" % st.session_state["geo_label"])

    st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=6)

    north_tl = north_of_treeline(lat)
    if north_tl:
        st.info("Latitude %.4f N is at or above %.0f N, so the site is "
                "taken as north of the treeline for Cl. 4.1.6.2.(4)."
                % (lat, TREELINE_LAT))
    else:
        st.caption("Latitude %.4f N is below %.0f N: south of the "
                   "treeline for Cl. 4.1.6.2.(4)."
                   % (lat, TREELINE_LAT))

    row = sub[sub["location"] == loc].iloc[0]
    Ss = float(row["Ss_kPa"])
    Sr = float(row["Sr_kPa"])
    q10 = float(row["q_1_10_kPa"])
    q50 = float(row["q_1_50_kPa"])

    if "name_ok" in row.index and not bool(row["name_ok"]):
        st.warning("The name of this entry is truncated in the source "
                   "Table C-2 export. The numeric design data is intact, "
                   "but confirm the location against your printed copy.")

    st.dataframe(pd.DataFrame({
        "Parameter": ["Elevation", "Ss (1/50)", "Sr (1/50)",
                      "q (1/10)", "q (1/50)", "Degree-days below 18 C"],
        "Value": ["%.0f m" % row["elev_m"], "%.1f kPa" % Ss,
                  "%.1f kPa" % Sr, "%.2f kPa" % q10, "%.2f kPa" % q50,
                  "%.0f" % row["degree_days_below_18"]],
    }), hide_index=True, use_container_width=True)

    # ------------------------------------------------------------------
    st.header("3. Snow Load")
    st.caption("NBCC 2020, Article 4.1.6.2")

    s1, s2, s3 = st.columns(3)
    with s1:
        ls_snow = st.radio("Limit state", ["ULS", "SLS"],
                           horizontal=True, key="ls_snow")
        cat_snow = st.selectbox("Importance category",
                                ["Low", "Normal", "High", "Post-Disaster"],
                                index=1, key="cat_snow")
    with s2:
        cw_choices = ["1.00 - Cl. 4.1.6.2.(3), default",
                      "0.75 - rural, Cl. 4.1.6.2.(4)",
                      "0.50 - exposed, north of the treeline"]
        cw_pick = st.selectbox("Cw, wind exposure factor", cw_choices,
                               index=2 if north_tl else 0)
        cw_req = float(cw_pick.split(" ")[0])
    with s3:
        slippery = st.checkbox("Unobstructed slippery roof", value=False)
        Ca = st.number_input("Ca, accumulation factor",
                             0.0, 5.0, 1.0, 0.05,
                             help="1.0 for uniform snow. Use Cl. 4.1.6.5 "
                                  "to 4.1.6.11 for drift, sliding and "
                                  "projection cases.")

    if cw_req < 1.0:
        st.caption("Cl. 4.1.6.2.(4) permits the reduction only for Low "
                   "and Normal Importance Category buildings and only "
                   "where all three of the following hold:")
        cwa, cwb, cwc = st.columns(3)
        with cwa:
            cond_a = st.checkbox("(a) Exposed on all sides to wind "
                                 "over open terrain, and expected to "
                                 "remain so", value=False)
        with cwb:
            cond_b = st.checkbox("(b) Roof area exposed on all sides, "
                                 "no significant obstructions within "
                                 "10x the obstruction height", value=False)
        with cwc:
            cond_c = st.checkbox("(c) Loading does not involve snow "
                                 "accumulation by drifting from "
                                 "adjacent surfaces", value=False)
    else:
        cond_a = cond_b = cond_c = False

    Is = importance_factor_snow(ls_snow, cat_snow)
    Cw, cw_why = wind_exposure_factor_snow(cat_snow, cw_req, north_tl,
                                           cond_a, cond_b, cond_c)
    if abs(Cw - cw_req) > 1e-9:
        st.warning("Cw = %.2f. %s" % (Cw, cw_why))
    else:
        st.caption("Cw = %.2f. %s" % (Cw, cw_why))

    lc = characteristic_length(W_roof, L_roof)
    Cb, cb_limit, cb_branch = basic_roof_snow_factor(lc, Cw)
    Cs, cs_branch = roof_slope_factor(alpha, slippery)
    S_load, S_basic = snow_load(Is, Ss, Sr, Cb, Cw, Cs, Ca)

    st.latex(r"I_s = %.2f \qquad (%s,\ %s)" % (Is, ls_snow, cat_snow))
    st.latex(r"l_c = 2w - \frac{w^2}{l} = 2(%.2f) - \frac{%.2f^2}{%.2f}"
             r" = %.2f \ \text{m}" % (W_roof, W_roof, L_roof, lc))
    st.caption("w and l are the smaller and larger plan dimensions of "
               "the roof, Cl. 4.1.6.2.(2)(a): w = w_h = %.2f m "
               "(horizontal), l = %.2f m. The sloped width w_s = "
               "%.2f m is not used here."
               % (W_roof, L_roof, W_roof_s))
    st.latex(r"\frac{70}{C_w^2} = \frac{70}{%.2f^2} = %.2f \ \text{m}"
             r" \quad \Rightarrow \quad %s"
             % (Cw, cb_limit, cb_branch.replace("^2", "^{2}")))
    st.latex(r"C_b = %.3f \qquad C_w = %.2f \qquad C_s = %.3f"
             r" \quad (%s) \qquad C_a = %.2f"
             % (Cb, Cw, Cs, cs_branch.replace(">", r"\gt ")
                .replace("<", r"\lt "), Ca))
    st.latex(r"S = I_s\left[S_s\,(C_b C_w C_s C_a) + S_r\right]")
    st.latex(r"S = %.2f\left[%.2f\,(%.3f \times %.2f \times %.3f "
             r"\times %.2f) + %.2f\right] = \mathbf{%.3f}\ \text{kPa}"
             % (Is, Ss, Cb, Cw, Cs, Ca, Sr, S_load))

    if Sr <= S_basic:
        st.success("Sr = %.2f kPa <= Ss(Cb Cw Cs Ca) = %.3f kPa. "
                   "Rain load limit satisfied." % (Sr, S_basic))
    else:
        st.error("Sr = %.2f kPa exceeds Ss(Cb Cw Cs Ca) = %.3f kPa. "
                 "Cl. 4.1.6.2 limits the rain component - review."
                 % (Sr, S_basic))

    if Cb > 0.8001:
        st.info("The lc > 70/Cw^2 branch of Cb governs. The source "
                "workbook only implemented the Cb = 0.8 branch, so this "
                "result will not match the spreadsheet. Verify against "
                "Cl. 4.1.6.2.(3)(b).")

    # ------------------------------------------------------------------
    st.header("4. Wind Load - Velocity Pressure and Factors")
    st.caption("NBCC 2020, Article 4.1.7.3")

    w1, w2, w3 = st.columns(3)
    with w1:
        ls_wind = st.radio("Limit state", ["ULS", "SLS"],
                           horizontal=True, key="ls_wind")
        cat_wind = st.selectbox("Importance category",
                                ["Low", "Normal", "High", "Post-Disaster"],
                                index=1, key="cat_wind")
    with w2:
        ret = st.radio("Return period", ["1/50", "1/10"],
                       horizontal=True)
        terrain = st.selectbox("Terrain", ["Open", "Rough"], index=0)
    with w3:
        Ct = st.number_input("Ct, topographic factor",
                             0.5, 3.0, 1.0, 0.05)
        member = st.selectbox("Member type",
                              ["Primary structural members (Cg = 2.0)",
                               "Secondary members / cladding (Cg = 2.5)"],
                              index=0)

    Iw = importance_factor_wind(ls_wind, cat_wind)
    q_ref = q50 if ret == "1/50" else q10
    V_ref = velocity_from_q(q_ref)
    Ce, ce_expr = exposure_factor(H_ref, terrain)
    Cg = 2.0 if member.startswith("Primary") else 2.5

    st.latex(r"I_w = %.2f \qquad q_{%s} = %.3f \ \text{kPa}"
             % (Iw, ret.replace("/", "/"), q_ref))
    st.latex(r"V = \sqrt{\frac{q}{0.00064645}}"
             r" = \sqrt{\frac{%.3f}{0.00064645}} = %.1f \ \text{m/s}"
             % (q_ref, V_ref))
    st.latex(r"C_e = %s = %.3f \qquad (H_{ref} = %.3f\ \text{m},\ %s)"
             % (ce_expr.replace(">=", r"\ge").replace("^", "^"),
                Ce, H_ref, terrain))
    st.latex(r"C_t = %.2f \qquad C_g = %.1f" % (Ct, Cg))

    # ------------------------------------------------------------------
    st.header("5. Wind Load - External Pressures")
    st.caption("NBCC 2020, Article 4.1.7.6 (low buildings) - "
               "Table 4.1.7.6 and Figure 4.1.7.6-A")

    low_ok = (H_ref <= 20.0) and (H_ref < W_bldg)
    if low_ok:
        st.success("Href = %.2f m <= 20 m and < W = %.2f m. "
                   "Article 4.1.7.6 applies." % (H_ref, W_bldg))
    else:
        st.warning("Href = %.2f m does not satisfy Href <= 20 m and "
                   "Href < W = %.2f m. Article 4.1.7.6 does not strictly "
                   "apply - use Article 4.1.7.5 (Cp from Fig. 4.1.7.5) "
                   "for this geometry." % (H_ref, W_bldg))

    cgcp_A, interp_note = cgcp_case_a(alpha)
    st.caption("Load Case A roof slope: %s" % interp_note)

    rows = []
    p_all = {}
    for s in SURFACES_A:
        val = cgcp_A[s]
        p = wind_pressure(Iw, q_ref, Ce, Ct, val)
        rows.append({"Surface": s, "Case": "A", "Cg*Cp": round(val, 3),
                     "p (kPa)": round(p, 3)})
        p_all[("A", s)] = (val, p)
    for s in SURFACES_B:
        val = CGCP_CASE_B[s]
        p = wind_pressure(Iw, q_ref, Ce, Ct, val)
        rows.append({"Surface": s, "Case": "B", "Cg*Cp": round(val, 3),
                     "p (kPa)": round(p, 3)})
        p_all[("B", s)] = (val, p)

    st.dataframe(pd.DataFrame(rows), hide_index=True,
                 use_container_width=True)
    st.latex(r"p = I_w\, q\, C_e\, C_t\, (C_g C_p)"
             r" = %.2f \times %.3f \times %.3f \times %.2f \times (C_g C_p)"
             % (Iw, q_ref, Ce, Ct))
    st.latex(r"p = %.4f \times (C_g C_p) \ \text{kPa}"
             % (Iw * q_ref * Ce * Ct))

    worst = max(p_all.items(), key=lambda kv: abs(kv[1][1]))
    st.info("Governing external pressure: surface %s, Load Case %s, "
            "Cg*Cp = %.2f, p = %.3f kPa"
            % (worst[0][1], worst[0][0], worst[1][0], worst[1][1]))

    # ------------------------------------------------------------------
    st.header("6. Wind Load - Internal Pressures")
    st.caption("NBCC 2020, Articles 4.1.7.3.(3) and 4.1.7.7")

    i1, i2 = st.columns(2)
    with i1:
        opening = st.selectbox(
            "Opening category (Cl. 4.1.7.7.(1))",
            ["a) Small uniform openings < 0.1% of surface "
             "(-0.15 <= Cpi <= 0)",
             "b) Non-uniform openings (-0.45 <= Cpi <= 0.30)",
             "c) Large openings likely to remain open "
             "(-0.70 <= Cpi <= 0.70)"], index=2)
        large_vol = st.checkbox("Large unpartitioned volume, "
                                "few overhead doors", value=False)
    with i2:
        V_int = st.number_input("Vo, internal volume (m3)",
                                0.0, 5e6, 8080.0, 10.0,
                                disabled=not large_vol)
        A_open = st.number_input("A, total opening area (m2)",
                                 0.0, 1e5, 49.58, 0.1,
                                 disabled=not large_vol)

    cpi_map = {"a": (-0.15, 0.0), "b": (-0.45, 0.30), "c": (-0.70, 0.70)}
    Cpi_neg, Cpi_pos = cpi_map[opening[0]]
    Cgi, cgi_expr = internal_gust_factor(V_int, A_open, large_vol)
    Cei = Ce

    pi_neg = Iw * q_ref * Cei * Ct * Cgi * Cpi_neg
    pi_pos = Iw * q_ref * Cei * Ct * Cgi * Cpi_pos

    st.latex(r"p_i = I_w\, q\, C_{ei}\, C_t\, C_{gi}\, C_{pi}")
    st.latex(r"C_{ei} = C_e = %.3f \qquad C_{gi} = %.3f"
             % (Cei, Cgi))
    st.caption(cgi_expr)
    st.latex(r"p_{i,-} = %.2f \times %.3f \times %.3f \times %.2f "
             r"\times %.3f \times (%.2f) = \mathbf{%.3f}\ \text{kPa}"
             % (Iw, q_ref, Cei, Ct, Cgi, Cpi_neg, pi_neg))
    st.latex(r"p_{i,+} = %.2f \times %.3f \times %.3f \times %.2f "
             r"\times %.3f \times (%.2f) = \mathbf{%.3f}\ \text{kPa}"
             % (Iw, q_ref, Cei, Ct, Cgi, Cpi_pos, pi_pos))

    if H_ref < 6.0:
        st.warning("Href < 6 m. Confirm the Cei provisions of "
                   "Cl. 4.1.7.3.(7) for this building.")

    # ------------------------------------------------------------------
    st.header("7. Net Design Pressures")
    st.caption("p_net = p_external - p_internal, worst-case pairing")

    net_rows = []
    for (case, s), (cgcp, p) in p_all.items():
        n1 = p - pi_neg
        n2 = p - pi_pos
        gov = n1 if abs(n1) >= abs(n2) else n2
        net_rows.append({
            "Surface": s, "Case": case,
            "p ext (kPa)": round(p, 3),
            "p net, Cpi-": round(n1, 3),
            "p net, Cpi+": round(n2, 3),
            "Governing (kPa)": round(gov, 3),
        })
    net_df = pd.DataFrame(net_rows).sort_values(
        "Governing (kPa)", key=lambda s: s.abs(), ascending=False)
    st.dataframe(net_df, hide_index=True, use_container_width=True)

    # ------------------------------------------------------------------
    st.header("8. Seismic Load")
    st.caption("NBCC 2020, Subsection 4.1.8")

    # ---- 8.1 Site properties -----------------------------------------
    st.subheader("8.1  Site Properties")
    st.caption("Article 4.1.8.4")

    st.success("Site coordinates %.4f N, %.4f E, taken from Section 2. "
               "Change them there and every seismic value below "
               "follows." % (lat, lon))

    sp1, sp2, sp3 = st.columns(3)
    with sp1:
        st.metric("Latitude", "%.4f" % lat)
        st.metric("Longitude", "%.4f" % lon)
    with sp2:
        site_basis = st.radio(
            "Site designation basis",
            ["Site Class (Xs)", "Vs30 (Xv)"],
            key="site_basis",
            help="Two ways to tell the hazard model what the ground "
                 "is like. Xs uses a Site Class letter (A hard rock "
                 "to F soft/problem soils) from Table 4.1.8.4-B. Xv "
                 "uses the measured Vs30 directly, with no rounding "
                 "to a class - preferred when a measured Vs30 "
                 "exists.")
        if site_basis == "Site Class (Xs)":
            sc_mode = st.selectbox(
                "Determine Site Class from",
                ["Enter directly", "Vs30", "N60", "su"], index=0,
                help="Table 4.1.8.4-B assigns the class from any of "
                     "three soil measurements: shear-wave velocity "
                     "Vs30, SPT blow count N60, or undrained shear "
                     "strength su. Use whichever the geotech report "
                     "provides; Vs30 governs when more than one is "
                     "available.")
        else:
            sc_mode = "Vs30 designation"
    with sp3:
        if site_basis == "Vs30 (Xv)":
            vs30_in = st.number_input("Vs30 (m/s)", 50.0, 3000.0,
                                      450.0, 1.0, help=GLOSS["Vs30"])
            site_class = nbcc.site_class_from_vs30(vs30_in)
            site_designation = "X%.0f" % vs30_in
            st.caption("Equivalent Site Class %s" % site_class)
        elif sc_mode == "Vs30":
            vs30_in = st.number_input("Vs30 (m/s)", 50.0, 3000.0,
                                      450.0, 1.0, help=GLOSS["Vs30"])
            site_class = nbcc.site_class_from_vs30(vs30_in)
            site_designation = "X" + site_class
        elif sc_mode == "N60":
            n60_in = st.number_input("N60 (blows / 0.3 m)", 0.0,
                                     200.0, 60.0, 1.0,
                                     help=GLOSS["N60"])
            site_class = nbcc.site_class_from_n60(n60_in)
            site_designation = "X" + site_class
        elif sc_mode == "su":
            su_in = st.number_input("su (kPa)", 0.0, 500.0, 120.0, 1.0,
                                    help=GLOSS["su"])
            site_class = nbcc.site_class_from_su(su_in)
            site_designation = "X" + site_class
        else:
            site_class = st.selectbox(
                "Site Class", ["A", "B", "C", "D", "E", "F"], index=2,
                help="Table 4.1.8.4-B: A hard rock, B rock, C very "
                     "dense soil / soft rock, D stiff soil, E soft "
                     "soil, F problem soils needing site-specific "
                     "evaluation. Softer ground amplifies shaking, "
                     "so the letter matters a lot to the loads.")
            site_designation = "X" + site_class

    st.caption("Site Class %s - %s"
               % (site_class, nbcc.SITE_CLASS_DESC[site_class]))
    explain("Vs30", "N60", "su")

    with st.expander("Table 4.1.8.4-A exceptions (Cl. 4.1.8.4.(2))"):
        ex1, ex2, ex3 = st.columns(3)
        with ex1:
            soft_over_rock = st.checkbox(
                "More than 3 m of softer material between rock and the "
                "underside of the footing or mat", value=False)
        with ex2:
            soft_clay = st.checkbox(
                "More than 3 m of soil with PI > 20, w >= 40% and "
                "su < 25 kPa", value=False)
        with ex3:
            collapse = st.checkbox(
                "Liquefiable, quick or sensitive clay, peat, highly "
                "plastic soil, or thick soft clay", value=False)
        vs30_for_exc = locals().get("vs30_in", 450.0)
        exc, exc_why = nbcc.site_designation_exception(
            vs30_for_exc, soft_over_rock, soft_clay, collapse)
        if exc:
            site_designation = exc
            st.error("Site designation revised to %s. %s" % (exc, exc_why))

    if site_class == "F" or site_designation == "XF":
        st.error("Site designation XF. Cl. 4.1.8.4.(4) requires a "
                 "site-specific geotechnical evaluation to determine "
                 "PGA, PGV and Sa(T). The values below are not valid "
                 "for this site.")

    fetch_ok = st.checkbox(
        "Fetch Sa(T) from the NRCan hazard service", value=True,
        help="Downloads the 5 percent damped spectral accelerations "
             "for these exact coordinates from Natural Resources "
             "Canada's 2020 seismic hazard model - the same numbers "
             "the online NBCC Seismic Hazard Tool reports. Untick to "
             "type the values in manually.")
    st.caption("Cl. 4.1.8.4.(1): Sa(T,X) at 0.2, 0.5, 1.0, 2.0, 5.0 "
               "and 10.0 s, 2% probability of exceedance in 50 years, "
               "per Subsection 1.1.3. Source: "
               "earthquakescanada.nrcan.gc.ca CanSHM.")

    sa_site = None
    sa_450 = None
    if fetch_ok:
        with st.spinner("Querying the NRCan seismic hazard service..."):
            sa_site, err1 = fetch_nbcc_spectrum(lat, lon, site_class)
            sa_450, err2 = fetch_nbcc_spectrum(lat, lon, 450)
        if sa_site is None:
            st.error("Could not retrieve Sa(T,X). %s" % err1)
        if sa_450 is None:
            st.warning("Could not retrieve Sa(T,X450). %s Fa, Fv and "
                       "the Art. 4.1.8.1 check will be unavailable."
                       % err2)

    if sa_site is None:
        st.caption("Manual entry - Sa(T,X) from the 2020 NBCC Seismic "
                   "Hazard Tool.")
        mcols = st.columns(6)
        sa_site = {}
        for col, p in zip(mcols, nbcc.SA_PERIODS):
            with col:
                sa_site["S(%s)" % ("%.1f" % p)] = st.number_input(
                    "Sa(%.1f)" % p, 0.0, 5.0, 0.0, 0.0001,
                    format="%.4f", key="sa_manual_%.1f" % p,
                    help=GLOSS["Sa(T,X)"])

    S = nbcc.design_spectrum(sa_site)
    interp_mode = st.radio(
        "S(T) interpolation (Cl. 4.1.8.4.(6))",
        ["log-log", "linear"], horizontal=True,
        help="The spectrum is only tabulated at 0.2, 0.5, 1, 2, 5 "
             "and 10 s, but the building's period Ta lands between "
             "those points, so S(Ta) has to be interpolated. "
             "Log-log interpolates on the logarithms of period and "
             "acceleration, which follows the smooth decay of a "
             "real spectrum; linear joins the tabulated points with "
             "straight lines. The full interpolation work is shown "
             "in Section 8.7.")

    spec_rows = [{"Period T (s)": "%.1f" % p,
                  "Sa(T,X) (g)": "%.4f" % float(
                      sa_site.get("S(%.1f)" % p, float("nan"))),
                  "S(T) (g)": "%.4f" % S["S(%.1f)" % p]}
                 for p in nbcc.SA_PERIODS]
    st.dataframe(pd.DataFrame(spec_rows), hide_index=True,
                 use_container_width=True)
    st.caption("Table 4.1.8.4-C: S(T) for T <= 0.2 s is the greater "
               "of Sa(0.2,X) and Sa(0.5,X).")
    explain("Sa(T,X)", "S(T)", "X450")

    if sa_450 is not None:
        Fa, Fv = nbcc.site_coefficients(S, sa_450)
        st.latex(r"F_a = \frac{S(0.2)}{S_a(0.2, X_{450})} = %.3f"
                 r" \qquad F_v = \frac{S(1.0)}{S_a(1.0, X_{450})}"
                 r" = %.3f" % (Fa, Fv))
        st.caption("Cl. 4.1.8.4.(7). Fa and Fv are for use in the "
                   "material standards referenced in Section 4.3.")
        explain("Fa", "Fv")

    # ---- 8.2 Importance factor and Seismic Category -------------------
    st.subheader("8.2  Importance Factor and Seismic Category")
    st.caption("Article 4.1.8.5, Tables 4.1.8.5-A and -B")

    cat_seis = st.selectbox(
        "Importance category",
        ["Low", "Normal", "High", "Post-disaster"], index=1,
        key="cat_seis",
        help="Table 4.1.8.5-A, by consequence of failure. Low: "
             "farm and low-occupancy buildings (IE = 0.8). Normal: "
             "most buildings (1.0). High: schools, community "
             "centres and buildings sheltering many people (1.3). "
             "Post-disaster: hospitals, fire and police stations, "
             "control centres that must work after the earthquake "
             "(1.5).")
    IE = nbcc.importance_factor(cat_seis)
    SC, ies02, ies10, sc_a, sc_b = nbcc.seismic_category(
        IE, S["S(0.2)"], S["S(1.0)"])

    st.latex(r"I_E = %.1f \qquad I_E S(0.2) = %.4f \ (SC%d)"
             r" \qquad I_E S(1.0) = %.4f \ (SC%d)"
             % (IE, ies02, sc_a, ies10, sc_b))
    explain("IE", "SC")

    with st.expander("Where SC comes from - Table 4.1.8.5-B, "
                     "step by step"):
        st.latex(r"I_E\,S(0.2) = %.1f \times %.4f = %.4f"
                 % (IE, S["S(0.2)"], ies02))

        def _band(val, cuts):
            # cuts = [c1, c2, c3] splitting SC1..SC4
            if val < cuts[0]:
                return (r"%.4f < %.2f \Rightarrow SC1"
                        % (val, cuts[0]))
            if val < cuts[1]:
                return (r"%.2f \leq %.4f < %.2f \Rightarrow SC2"
                        % (cuts[0], val, cuts[1]))
            if val <= cuts[2]:
                return (r"%.2f \leq %.4f \leq %.2f \Rightarrow SC3"
                        % (cuts[1], val, cuts[2]))
            return r"%.4f > %.2f \Rightarrow SC4" % (val, cuts[2])

        st.caption("Short-period test, bands at 0.20 / 0.35 / 0.75:")
        st.latex(_band(ies02, [0.20, 0.35, 0.75]))
        st.latex(r"I_E\,S(1.0) = %.1f \times %.4f = %.4f"
                 % (IE, S["S(1.0)"], ies10))
        st.caption("Long-period test, bands at 0.10 / 0.20 / 0.30:")
        st.latex(_band(ies10, [0.10, 0.20, 0.30]))
        st.latex(r"SC = \max(SC%d,\ SC%d) = \mathbf{SC%d}"
                 % (sc_a, sc_b, SC))

    st.info("Seismic Category SC%d. Table 4.1.8.5-B takes the more "
            "severe of the two categories, irrespective of Ta." % SC)

    # ---- 8.3 Structural configuration --------------------------------
    st.subheader("8.3  Structural Configuration")
    st.caption("Article 4.1.8.6, Table 4.1.8.6")

    irr_labels = ["Type %d - %s" % (t, name)
                  for t, name, _ in nbcc.IRREGULARITIES]
    picked = st.multiselect("Irregularities present (leave empty for "
                            "a regular structure)", irr_labels)
    irr_types = [int(p.split()[1]) for p in picked]
    is_irregular = len(irr_types) > 0

    with st.expander("Table 4.1.8.6 - definitions"):
        for t, name, desc in nbcc.IRREGULARITIES:
            st.markdown("**Type %d - %s**" % (t, name))
            st.caption(desc)

    if is_irregular:
        st.warning("Structure is designated irregular: types %s. "
                   "Where SC is SC3 or SC4, Cl. 4.1.8.6.(3) requires "
                   "the provisions referenced in Table 4.1.8.6 to be "
                   "satisfied." % sorted(irr_types))
    else:
        st.success("No irregularities selected. The structure may be "
                   "considered regular per Cl. 4.1.8.6.(2).")

    if 6 in irr_types and SC != 1:
        st.error("Cl. 4.1.8.10.(1): a Type 6 weak-storey irregularity "
                 "is not permitted unless SC is SC1 and the SFRS "
                 "design forces are multiplied by Rd*Ro.")
    if cat_seis == "Post-disaster":
        bad = sorted(set(irr_types) & set([1, 3, 4, 5, 7, 9, 10]))
        if bad and SC in (3, 4):
            st.error("Cl. 4.1.8.10.(2)(a): post-disaster buildings in "
                     "SC%d shall not have Type %s irregularities."
                     % (SC, bad))
        if 6 in irr_types:
            st.error("Cl. 4.1.8.10.(2)(b): post-disaster buildings "
                     "shall not have a Type 6 irregularity.")
    if cat_seis == "High":
        bad = sorted(set(irr_types) & set([1, 3, 4, 5, 7, 9, 10]))
        if bad and SC == 4:
            st.error("Cl. 4.1.8.10.(3)(a): High Importance Category "
                     "buildings in SC4 shall not have Type %s "
                     "irregularities." % bad)

    # ---- 8.4 SFRS ----------------------------------------------------
    st.subheader("8.4  SFRS Force Modification Factors")
    st.caption("Article 4.1.8.9, Table 4.1.8.9")

    sf1, sf2 = st.columns([1, 2])
    with sf1:
        grp = st.selectbox(
            "Material / standard", nbcc.sfrs_groups(), index=0,
            help="The material standard the Seismic Force Resisting "
                 "System is designed to. Each material's detailing "
                 "rules earn the Rd and Ro values in Table 4.1.8.9.")
    with sf2:
        opts = nbcc.sfrs_options(grp)
        default_i = 0
        for i, o in enumerate(opts):
            if "Conventional construction" in o and "Other" in o:
                default_i = i
                break
        sfrs_name = st.selectbox(
            "Type of SFRS", opts, index=default_i,
            help="The SFRS is the part of the structure that "
                 "resists earthquake forces: the braced bays, "
                 "moment frames or shear walls. Pick the row of "
                 "Table 4.1.8.9 that matches what is actually "
                 "detailed on the drawings - the ductility class "
                 "(ductile / moderately ductile / limited / "
                 "conventional) must match the detailing, not just "
                 "the geometry.")

    entry = nbcc.sfrs_lookup(grp, sfrs_name)
    Rd, Ro = entry["Rd"], entry["Ro"]

    hn = st.number_input("hn, height above the base to level n (m)",
                         1.0, 300.0, 10.0, 0.1, help=GLOSS["hn"])
    n_storeys = st.number_input(
        "N, number of storeys above grade", 1, 100, 1, 1,
        help="Storey count above grade, used by the Ta = 0.1 N "
             "period formula for moment frames other than steel "
             "or concrete.")

    st.latex(r"R_d = %.1f \qquad R_o = %.1f \qquad R_d R_o = %.2f"
             % (Rd, Ro, Rd * Ro))
    explain("Rd", "Ro")
    st.caption("The base shear divides by Rd Ro = %.2f, so this "
               "choice of SFRS cuts the elastic demand by a factor "
               "of %.2f. A fully elastic (Rd = Ro = 1.0) design of "
               "the same building would see %.0f%% more force."
               % (Rd * Ro, Rd * Ro, 100.0 * (Rd * Ro - 1.0)))

    lim_ok, lim_msg = nbcc.check_height_limit(entry, SC, hn)
    (st.success if lim_ok else st.error)(lim_msg)

    if "Unreinforced masonry" in sfrs_name:
        ok_urm, msg_urm = nbcc.unreinforced_masonry_check(IE, hn)
        if not ok_urm:
            st.error(msg_urm)
    if "Cold-formed" in grp:
        ok_cfs, msg_cfs = nbcc.cold_formed_height_check(hn)
        if not ok_cfs:
            st.error(msg_cfs)
    if cat_seis == "Post-disaster" and Rd < 2.0:
        st.error("Cl. 4.1.8.10.(2)(c): post-disaster buildings shall "
                 "have an SFRS with Rd of 2.0 or greater.")
    if cat_seis == "High":
        need = 2.0 if SC == 4 else 1.5
        if Rd < need:
            st.error("Cl. 4.1.8.10.(3)(c): High Importance Category "
                     "buildings in SC%d require Rd of at least %.1f."
                     % (SC, need))

    # ---- 8.5 Period --------------------------------------------------
    st.subheader("8.5  Fundamental Lateral Period")
    st.caption("Cl. 4.1.8.11.(3) and (4)")

    p1, p2 = st.columns(2)
    with p1:
        period_sys = st.selectbox(
            "Period equation", nbcc.PERIOD_SYSTEMS, index=3,
            help="Which empirical formula of Cl. 4.1.8.11.(3) "
                 "estimates the fundamental period. Pick the one "
                 "matching the SFRS: moment frames sway more (longer "
                 "period) than braced frames, which sway more than "
                 "shear walls.")
        single_storey = st.checkbox(
            "Single-storey with steel deck or wood roof diaphragm "
            "(Cl. 4.1.8.11.(4))", value=False,
            help="A flexible roof diaphragm adds sway of its own, so "
                 "single-storey buildings with steel deck or wood "
                 "roofs get a longer period that grows with the "
                 "diaphragm span L.")
    with p2:
        L_diaph = st.number_input(
            "L, shortest diaphragm length (m)", 0.0, 300.0, 30.0, 0.1,
            disabled=not single_storey,
            help="Shortest span of the roof diaphragm between "
                 "vertical elements of the SFRS, in metres.")
        Ta_mech = st.number_input(
            "Ta from a mechanics model (s) - 0 to skip",
            0.0, 20.0, 0.0, 0.001, format="%.3f",
            help="Period from a modal analysis or other structural "
                 "model, if one exists. Cl. 4.1.8.11.(3)(d) lets it "
                 "be used, but caps it at 1.5x (moment frames) or "
                 "2.0x (braced frames, walls) the empirical value, "
                 "because a long analytical period can "
                 "unconservatively shrink the force.")

    if single_storey:
        Ta_emp, ta_expr = nbcc.single_storey_period(
            period_sys, hn, L_diaph)
    else:
        Ta_emp, ta_expr = nbcc.fundamental_period(
            period_sys, hn, n_storeys)

    Ta = Ta_emp
    ta_note = ""
    if Ta_mech > 0:
        Ta, ta_note = nbcc.cap_mechanics_period(period_sys, Ta_mech,
                                                Ta_emp)

    # substituted form of whichever empirical expression applies
    if single_storey:
        if period_sys in ("Steel moment frame", "Braced frame"):
            ta_sub = (r"0.035(%.2f) + 0.004(%.2f)" % (hn, L_diaph))
        else:
            ta_sub = (r"0.05\,(%.2f)^{3/4} + 0.004(%.2f)"
                      % (hn, L_diaph))
    elif period_sys == "Steel moment frame":
        ta_sub = r"0.085\,(%.2f)^{3/4}" % hn
    elif period_sys == "Concrete moment frame":
        ta_sub = r"0.075\,(%.2f)^{3/4}" % hn
    elif period_sys == "Other moment frame":
        ta_sub = r"0.1 \times %d" % int(n_storeys)
    elif period_sys == "Braced frame":
        ta_sub = r"0.025 \times %.2f" % hn
    else:
        ta_sub = r"0.05\,(%.2f)^{3/4}" % hn

    st.latex(r"%s = %s = %.4f \ \text{s}"
             % (ta_expr.replace("Ta", "T_a").replace("hn", "h_n"),
                ta_sub, Ta_emp))
    explain("Ta", "hn")
    if ta_note:
        st.info(ta_note + "  Ta = %.4f s used." % Ta)

    # ---- 8.6 Method of analysis --------------------------------------
    st.subheader("8.6  Method of Analysis")
    st.caption("Article 4.1.8.7")

    esfp_ok, esfp_why = nbcc.esfp_permitted(SC, hn, Ta, is_irregular,
                                            irr_types)
    (st.success if esfp_ok else st.error)(esfp_why)
    if not esfp_ok:
        st.caption("The results below are still computed for "
                   "reference, but Art. 4.1.8.12 governs the design.")

    # ---- 8.7 Base shear ----------------------------------------------
    st.subheader("8.7  Equivalent Static Force Procedure")
    st.caption("Article 4.1.8.11")

    st.markdown("**Seismic weight, W** (Art. 4.1.8.2)")
    w1, w2, w3, w4 = st.columns(4)
    with w1:
        W_dead = st.number_input(
            "Dead load (kN)", 0.0, 1e7, 4000.0, 10.0,
            help="Total specified (unfactored) dead load of the "
                 "building: structure, finishes, partitions, fixed "
                 "equipment. All of it shakes, so all of it counts.")
    with w2:
        W_snow = st.number_input(
            "Specified snow load (kN)", 0.0, 1e7, 800.0, 10.0,
            help="Total specified snow load on the roof (S from "
                 "Section 3 times the roof area). Only 25 percent "
                 "counts toward W - a design blizzard and a design "
                 "earthquake are unlikely to coincide in full.")
    with w3:
        W_stor = st.number_input(
            "Storage load (kN)", 0.0, 1e7, 0.0, 10.0,
            help="Live load in storage areas. 60 percent counts "
                 "toward W, since racks and stock are usually "
                 "there.")
    with w4:
        W_tank = st.number_input(
            "Tank contents (kN)", 0.0, 1e7, 0.0, 10.0,
            help="Full weight of the contents of any tanks. Counts "
                 "at 100 percent.")

    W_seis = nbcc.seismic_weight(W_dead, W_snow, W_stor, W_tank)
    st.latex(r"W = D + 0.25 S + 0.60 (\text{storage}) + \text{tanks}"
             r" = %.0f + 0.25(%.0f) + 0.60(%.0f) + %.0f"
             r" = \mathbf{%.1f}\ \text{kN}"
             % (W_dead, W_snow, W_stor, W_tank, W_seis))
    explain("W")

    mv_group = st.selectbox(
        "System group for Table 4.1.8.11",
        list(nbcc.MV_J_TABLE.keys()), index=2,
        help="The row family of Table 4.1.8.11 matching the SFRS: "
             "braced frames for CBFs and EBFs, walls for shear "
             "walls, moment frames for MRFs. It sets the "
             "higher-mode factor Mv and the overturning reduction "
             "J, because each system type carries higher modes "
             "differently.")
    Mv, Jf, sratio, mv_note = nbcc.mv_and_j(
        mv_group, S["S(0.2)"], S["S(5.0)"], Ta)

    st.latex(r"\frac{S(0.2)}{S(5.0)} = \frac{%.4f}{%.4f} = %.2f"
             r" \qquad M_v = %.3f \qquad J = %.3f"
             % (S["S(0.2)"], S["S(5.0)"], sratio, Mv, Jf))
    explain("Mv", "J")
    if mv_note:
        st.caption(mv_note)

    with st.expander("Where Mv and J come from - Table 4.1.8.11, "
                     "step by step"):
        st.caption("The table is entered twice over: once on the "
                   "spectral ratio S(0.2)/S(5.0) (which measures "
                   "how fast the spectrum decays at this site, and "
                   "therefore how much the higher modes matter), "
                   "and once on the period Ta. Both entries "
                   "interpolate linearly, Notes (1) and (2).")
        _row = nbcc._row_at_ratio(mv_group, sratio)
        _mv_anch = _row[0:4]
        _j_anch = _row[4:8]
        _anch_rows = []
        for _p, _m, _j in zip(nbcc.MV_TA_ANCHORS, _mv_anch, _j_anch):
            _anch_rows.append({
                "Ta anchor (s)": "%.1f" % _p,
                "Mv": "-" if _m is None else "%.3f" % _m,
                "J": "-" if _j is None else "%.3f" % _j})
        st.caption("Row values at the ratio %.2f (after the ratio "
                   "interpolation; '-' marks the Note (5) cells, "
                   "where the 2.0 s values are used for Ta > 2 s):"
                   % sratio)
        st.dataframe(pd.DataFrame(_anch_rows), hide_index=True,
                     use_container_width=True)
        _T_eff = min(Ta, 2.0) if _mv_anch[3] is None else Ta
        _usable = [(p, m, j) for p, m, j in
                   zip(nbcc.MV_TA_ANCHORS, _mv_anch, _j_anch)
                   if m is not None]
        if _T_eff <= _usable[0][0]:
            st.latex(r"T_a = %.3f \leq %.1f\ \text{s, so the first "
                     r"column applies:}\ M_v = %.3f,\ J = %.3f"
                     % (Ta, _usable[0][0], _usable[0][1],
                        _usable[0][2]))
        elif _T_eff >= _usable[-1][0]:
            st.latex(r"T_a\ \text{at or beyond the last anchor: }"
                     r"M_v = %.3f,\ J = %.3f"
                     % (_usable[-1][1], _usable[-1][2]))
        else:
            for _i in range(len(_usable) - 1):
                _p0, _m0, _j0 = _usable[_i]
                _p1, _m1, _j1 = _usable[_i + 1]
                if _p0 <= _T_eff <= _p1:
                    st.latex(
                        r"M_v = %.3f + (%.3f - %.3f)"
                        r"\frac{%.3f - %.1f}{%.1f - %.1f} = %.3f"
                        % (_m0, _m1, _m0, _T_eff, _p0, _p1, _p0, Mv))
                    st.latex(
                        r"J = %.3f + (%.3f - %.3f)"
                        r"\frac{%.3f - %.1f}{%.1f - %.1f} = %.3f"
                        % (_j0, _j1, _j0, _T_eff, _p0, _p1, _p0, Jf))
                    break

    bs = nbcc.base_shear(S, Ta, Mv, IE, W_seis, Rd, Ro, mv_group,
                         site_designation, interp_mode)

    with st.expander("Where S(Ta) comes from - Cl. 4.1.8.4.(6) "
                     "interpolation, step by step"):
        _pts = [(p, S["S(%.1f)" % p]) for p in nbcc.SA_PERIODS
                if not math.isnan(S["S(%.1f)" % p])]
        if not _pts:
            st.caption("No spectral values available.")
        elif Ta <= _pts[0][0]:
            st.latex(r"T_a = %.3f \leq %.1f\ \text{s, so } S(T_a) "
                     r"= S(%.1f) = %.4f"
                     % (Ta, _pts[0][0], _pts[0][0], _pts[0][1]))
        elif Ta >= _pts[-1][0]:
            st.latex(r"T_a = %.3f \geq %.1f\ \text{s, so } S(T_a) "
                     r"= S(%.1f) = %.4f"
                     % (Ta, _pts[-1][0], _pts[-1][0], _pts[-1][1]))
        else:
            for _i in range(len(_pts) - 1):
                _p0, _v0 = _pts[_i]
                _p1, _v1 = _pts[_i + 1]
                if _p0 <= Ta <= _p1:
                    st.caption("Ta = %.3f s falls between the "
                               "tabulated periods %.1f s and %.1f s:"
                               % (Ta, _p0, _p1))
                    st.latex(r"S(%.1f) = %.4f \qquad S(%.1f) = %.4f"
                             % (_p0, _v0, _p1, _v1))
                    if (interp_mode == "log-log" and _v0 > 0
                            and _v1 > 0):
                        _lp = ((math.log(Ta) - math.log(_p0))
                               / (math.log(_p1) - math.log(_p0)))
                        st.latex(
                            r"\lambda = \frac{\ln T_a - \ln %.1f}"
                            r"{\ln %.1f - \ln %.1f} = \frac{%.4f - "
                            r"%.4f}{%.4f - %.4f} = %.4f"
                            % (_p0, _p1, _p0, math.log(Ta),
                               math.log(_p0), math.log(_p1),
                               math.log(_p0), _lp))
                        st.latex(
                            r"S(T_a) = e^{\,\ln %.4f + \lambda"
                            r"(\ln %.4f - \ln %.4f)} = %.4f"
                            % (_v0, _v1, _v0, bs["S_Ta"]))
                        st.caption("Log-log interpolation: straight "
                                   "line between the two points on "
                                   "log(period) - log(acceleration) "
                                   "axes, which matches the smooth "
                                   "decay of a real spectrum.")
                    else:
                        st.latex(
                            r"S(T_a) = %.4f + (%.4f - %.4f)"
                            r"\frac{%.3f - %.1f}{%.1f - %.1f} = %.4f"
                            % (_v0, _v1, _v0, Ta, _p0, _p1, _p0,
                               bs["S_Ta"]))
                    break

    st.latex(r"V = \frac{S(T_a)\, M_v\, I_E\, W}{R_d R_o}"
             r" = \frac{%.4f \times %.3f \times %.1f \times %.1f}"
             r"{%.1f \times %.1f} = %.2f\ \text{kN}"
             % (bs["S_Ta"], Mv, IE, W_seis, Rd, Ro, bs["V_calc"]))
    explain("V", "Ta", "Mv", "IE", "W", "Rd", "Ro")

    _wall_like = mv_group in ("Walls, Wall-Frame Systems",
                              "Coupled Walls")
    _pmin = 4.0 if _wall_like else 2.0
    st.latex(r"V_{min} = \frac{S(%.1f)\, M_v\, I_E\, W}{R_d R_o}"
             r" = \frac{%.4f \times %.3f \times %.1f \times %.1f}"
             r"{%.1f \times %.1f} = %.2f\ \text{kN}"
             % (_pmin, bs["S_min"], Mv, IE, W_seis, Rd, Ro,
                bs["V_min"]))
    st.caption(bs["min_ref"] + ". A floor on the force for "
               "long-period buildings, since the hazard model's "
               "long-period tail is less certain.")
    if bs["V_max"] is not None:
        _cap_a = (2.0 / 3.0) * S["S(0.2)"] * IE * W_seis / (Rd * Ro)
        _cap_b = S["S(0.5)"] * IE * W_seis / (Rd * Ro)
        st.latex(r"\tfrac{2}{3}\,\frac{S(0.2)\, I_E\, W}{R_d R_o}"
                 r" = \tfrac{2}{3}\,\frac{%.4f \times %.1f \times "
                 r"%.1f}{%.2f} = %.2f\ \text{kN}"
                 % (S["S(0.2)"], IE, W_seis, Rd * Ro, _cap_a))
        st.latex(r"\frac{S(0.5)\, I_E\, W}{R_d R_o}"
                 r" = \frac{%.4f \times %.1f \times %.1f}{%.2f}"
                 r" = %.2f\ \text{kN}"
                 % (S["S(0.5)"], IE, W_seis, Rd * Ro, _cap_b))
        st.latex(r"V_{max} = \max(%.2f,\ %.2f) = %.2f\ \text{kN}"
                 % (_cap_a, _cap_b, bs["V_max"]))
        st.caption("Cl. 4.1.8.11.(2)(c): short, stiff buildings "
                   "need not be designed for the full short-period "
                   "spike. Applies because the site is not XF and "
                   "Rd >= 1.5.")
    else:
        st.caption("Cl. 4.1.8.11.(2)(c) upper bound does not apply "
                   "(site is XF or Rd < 1.5).")

    V = bs["V"]
    st.success("V = %.2f kN.  %s" % (V, bs["governs"]))
    VW = V / W_seis if W_seis > 0 else float("nan")

    # ---- 8.8 Vertical distribution -----------------------------------
    st.subheader("8.8  Vertical Distribution and Overturning")
    st.caption("Cl. 4.1.8.11.(7) and (8)")

    st.markdown(
        "The base shear V found above is the total horizontal force "
        "on the structure. It now has to be handed out to the floors, "
        "because that is where the mass sits and where the diaphragms "
        "can deliver it into the SFRS. Two things happen:")
    st.markdown(
        "1. **A top force, Ft.** A tall, flexible building whips at "
        "the top under higher modes, so Cl. 4.1.8.11.(7)(a) pulls a "
        "slice of V off the top of the distribution and applies it at "
        "level n. Ft = 0.07 Ta V, capped at 0.25V, and taken as zero "
        "when Ta does not exceed 0.7 s.\n"
        "2. **The remainder, V - Ft, is shared out by Wx hx.** Each "
        "level gets a share in proportion to its weight times its "
        "height above the base, which is the inverted-triangle shape "
        "of a first-mode response. A heavy low floor and a light high "
        "floor can end up with similar forces.")
    st.latex(r"F_t = 0.07\,T_a V \le 0.25V, \qquad F_t = 0 "
             r"\ \text{if}\ T_a \le 0.7\ \text{s}")
    st.latex(r"F_x = (V - F_t)\,\frac{W_x h_x}{\sum_{i=1}^{n} W_i h_i}")
    st.markdown(
        "The **storey shear** at any level is the sum of all the "
        "forces above it, so it grows from Fx at the roof to V at the "
        "base. The **overturning moment** Mx is the same forces times "
        "their lever arm above level x. Cl. 4.1.8.11.(8) then applies "
        "Jx, a reduction that recognises the peak storey forces do "
        "not all occur in the same instant, so summing them as if they "
        "did overstates the base moment. Jx is 1.0 in the upper part "
        "of the building and tapers to J at the base:")
    st.latex(r"M_x = J_x \sum_{i=x}^{n} F_i (h_i - h_x), \qquad "
             r"J_x = 1.0 \ \text{for}\ h_x \ge 0.6h_n, \quad "
             r"J_x = J + (1-J)\frac{h_x}{0.6h_n} \ \text{otherwise}")

    n_lv = st.number_input("Number of levels to distribute over",
                           1, 60, max(1, int(n_storeys)), 1)
    default_levels = pd.DataFrame({
        "Level": [("Roof" if i == int(n_lv) - 1 else str(i + 1))
                  for i in range(int(n_lv))],
        "Wi (kN)": [round(W_seis / max(1, int(n_lv)), 1)] * int(n_lv),
        "hi (m)": [round(hn * (i + 1) / max(1, int(n_lv)), 2)
                   for i in range(int(n_lv))],
    })
    lv_df = st.data_editor(default_levels, hide_index=True,
                           use_container_width=True,
                           num_rows="fixed", key="levels_editor")

    levels = [{"level": str(r["Level"]), "W": float(r["Wi (kN)"]),
               "h": float(r["hi (m)"])}
              for _, r in lv_df.iterrows()]
    levels = [l for l in levels if l["h"] > 0]

    if levels:
        forces, Ft, ft_note, sum_wh = nbcc.distribute(V, Ta, levels)
        shears = nbcc.storey_shears(forces)
        ot = nbcc.overturning(forces, Jf, hn)

        if Ta <= 0.7:
            st.latex(r"T_a = %.3f \leq 0.7\ \text{s} \Rightarrow "
                     r"F_t = 0" % Ta)
        else:
            st.latex(r"F_t = 0.07\,T_a V = 0.07 \times %.3f \times "
                     r"%.2f = %.2f\ \text{kN}"
                     % (Ta, V, 0.07 * Ta * V))
            if Ft < 0.07 * Ta * V - 1e-9:
                st.latex(r"F_t \leq 0.25V = %.2f\ \text{kN (cap "
                         r"governs)}" % (0.25 * V))
        st.latex(r"F_t = %.2f\ \text{kN}" % Ft)
        st.caption(ft_note)
        explain("Ft", "Fx")
        st.latex(r"F_x = (V - F_t)\,\frac{W_x h_x}"
                 r"{\sum W_i h_i} \qquad \sum W_i h_i = %.1f" % sum_wh)

        dist_rows = []
        for f, sh in zip(forces, shears):
            dist_rows.append({
                "Level": f["level"], "Wi (kN)": round(f["W"], 1),
                "hi (m)": round(f["h"], 2),
                "Wi*hi": round(f["Wh"], 1),
                "Fx (kN)": round(f["Fx"], 2),
                "Storey shear (kN)": round(sh, 2),
            })
        st.dataframe(pd.DataFrame(dist_rows), hide_index=True,
                     use_container_width=True)

        top = forces[-1]
        st.markdown("**Worked check at the top level, %s**"
                    % top["level"])
        st.latex(r"F_{%s} = (%.2f - %.2f)\times\frac{%.1f \times %.2f}"
                 r"{%.1f} = %.2f\ \text{kN}"
                 % (top["level"].replace(" ", r"\,"), V, Ft,
                    top["W"], top["h"], sum_wh, top["Fx"] - (
                        Ft if abs(Ft) > 1e-9 else 0.0)))
        if abs(Ft) > 1e-9:
            st.caption("Ft = %.2f kN is added at this level, giving "
                       "Fx = %.2f kN in the table above."
                       % (Ft, top["Fx"]))
        st.caption("Check: the storey forces sum to %.2f kN against "
                   "V = %.2f kN."
                   % (sum(f["Fx"] for f in forces), V))

        ot_rows = [{"Level": r["level"], "hx (m)": round(r["h"], 2),
                    "Jx": round(r["Jx"], 4),
                    "Mx (kN.m)": round(r["Mx"], 1)} for r in ot]
        st.dataframe(pd.DataFrame(ot_rows), hide_index=True,
                     use_container_width=True)

        M_base_raw = sum(f["Fx"] * f["h"] for f in forces)
        Jx_base = Jf
        st.markdown("**Overturning at the base**")
        st.latex(r"\sum F_i h_i = %.1f\ \text{kN}\cdot\text{m}"
                 r" \qquad J = %.3f \qquad "
                 r"M_0 = J \sum F_i h_i = %.1f\ \text{kN}\cdot\text{m}"
                 % (M_base_raw, Jx_base, Jx_base * M_base_raw))
        st.caption("This is the demand the foundation and the SFRS "
                   "hold-downs have to resist, before the "
                   "counteracting dead load of Cl. 4.1.3.2.(5) is "
                   "taken against it. hn = %.2f m, so Jx reaches 1.0 "
                   "above %.2f m." % (hn, 0.6 * hn))
    else:
        forces, Ft, shears = [], 0.0, []
        st.warning("Enter at least one level with hi > 0.")

    # ---- 8.9 Torsion and drift ---------------------------------------
    st.subheader("8.9  Torsion and Drift")
    st.caption("Cl. 4.1.8.11.(9) to (11), Art. 4.1.8.13")

    st.markdown(
        "The storey force Fx acts through the centre of mass, but the "
        "SFRS resists it through the centre of rigidity. If those two "
        "points do not coincide, the offset ex produces a twist on "
        "the floor plate. On top of that, Cl. 4.1.8.11.(9) requires "
        "an **accidental** eccentricity of 0.10 Dnx, applied both "
        "ways, to cover mass and stiffness that do not sit where the "
        "drawings say. Each element is designed for whichever sign is "
        "worse:")
    st.latex(r"T_x = F_x\,(e_x \pm 0.10\,D_{nx})")
    st.markdown(
        "**Torsional sensitivity, B.** Push the building with the "
        "forces applied at plus and minus 0.10 Dnx from the centres "
        "of mass and compare the displacement at the worst corner "
        "with the average of the two extreme corners. A ratio above "
        "1.7 means the plan twists enough that a static treatment is "
        "no longer trustworthy, and in SC3 or SC4 a dynamic analysis "
        "is required:")
    st.latex(r"B_x = \frac{\delta_{max}}{\delta_{ave}}, \qquad "
             r"B = \max(B_x)\ \text{over both orthogonal directions}")
    st.markdown(
        "**Drift.** An elastic analysis under the reduced force "
        "V = S(Ta) Mv IE W / (Rd Ro) gives displacements that are far "
        "too small, because the real structure is expected to yield. "
        "Art. 4.1.8.13 multiplies them back up by Rd Ro / IE to get "
        "the anticipated deflections, and the interstorey value is "
        "then checked against the limits below.")

    t1, t2, t3 = st.columns(3)
    with t1:
        Dnx = st.number_input("Dnx, plan dimension perpendicular to "
                              "the loading (m)", 0.0, 300.0,
                              float(L_bldg), 0.01, help=GLOSS["Dnx"])
    with t2:
        ex_ecc = st.number_input("ex, eccentricity between the centres "
                                 "of mass and rigidity (m)",
                                 -50.0, 50.0, 0.0, 0.01,
                                 help=GLOSS["ex"])
    with t3:
        d_max = st.number_input(
            "d_max, maximum storey displacement (mm)",
            0.0, 1000.0, 0.0, 0.1,
            help="Largest lateral displacement at any corner of the "
                 "storey, from the elastic analysis with the forces "
                 "applied at plus and minus 0.10 Dnx from the "
                 "centres of mass. Enter 0 to skip the B check.")
        d_ave = st.number_input(
            "d_ave, average storey displacement (mm)",
            0.0, 1000.0, 0.0, 0.1,
            help="Average of the displacements at the two extreme "
                 "corners of the same storey, from the same "
                 "analysis.")

    st.latex(r"T_x = F_x (e_x \pm 0.10 D_{nx})"
             r" \qquad 0.10 D_{nx} = 0.10 \times %.2f = %.3f \ "
             r"\text{m}" % (Dnx, 0.10 * Dnx))
    explain("Dnx", "ex", "Fx")
    if forces:
        _ftop = forces[-1]
        _tp, _tm = nbcc.torsional_moments(_ftop["Fx"], ex_ecc, Dnx)
        st.markdown("**Worked example at the top level, %s**"
                    % _ftop["level"])
        st.latex(r"T_{%s} = %.2f\,(%.3f + %.3f) = %.2f\ "
                 r"\text{kN}\cdot\text{m} \qquad "
                 r"T_{%s} = %.2f\,(%.3f - %.3f) = %.2f\ "
                 r"\text{kN}\cdot\text{m}"
                 % (str(_ftop["level"]).replace(" ", r"\,"),
                    _ftop["Fx"], ex_ecc, 0.10 * Dnx, _tp,
                    str(_ftop["level"]).replace(" ", r"\,"),
                    _ftop["Fx"], ex_ecc, 0.10 * Dnx, _tm))
        st.caption("Each element of the SFRS is designed for "
                   "whichever sign of the accidental term is worse "
                   "for it - a stiff wall on the far side of the "
                   "plan can pick up more force from the twist than "
                   "from the direct shear.")
        tor_rows = []
        for f in forces:
            tp, tm = nbcc.torsional_moments(f["Fx"], ex_ecc, Dnx)
            tor_rows.append({"Level": f["level"],
                             "Fx (kN)": round(f["Fx"], 2),
                             "Tx, +0.1Dnx (kN.m)": round(tp, 2),
                             "Tx, -0.1Dnx (kN.m)": round(tm, 2)})
        st.dataframe(pd.DataFrame(tor_rows), hide_index=True,
                     use_container_width=True)

    if d_ave > 0:
        Bx = nbcc.torsional_sensitivity(d_max, d_ave)
        st.latex(r"B_x = \frac{\delta_{max}}{\delta_{ave}}"
                 r" = \frac{%.2f}{%.2f} = %.3f" % (d_max, d_ave, Bx))
        explain("Bx")
        if Bx > 1.7:
            st.error("B = %.3f exceeds 1.7. This is a Type 7 "
                     "torsional sensitivity irregularity. Where SC is "
                     "SC3 or SC4, Cl. 4.1.8.11.(11)(b) requires a "
                     "Dynamic Analysis Procedure." % Bx)
        else:
            st.success("B = %.3f does not exceed 1.7. Torsion may be "
                       "handled by the static load cases of "
                       "Cl. 4.1.8.11.(11)(a)." % Bx)

    dl = nbcc.drift_limit(cat_seis)
    st.markdown("**Drift check** (Art. 4.1.8.13)")
    dr1, dr2 = st.columns(2)
    with dr1:
        hs_mm = st.number_input(
            "hs, interstorey height (mm)", 0.0, 20000.0, 0.0, 50.0,
            help=GLOSS["hs"] + " Enter 0 to skip the worked drift "
                 "check.")
    with dr2:
        d_elastic = st.number_input(
            "Elastic interstorey deflection (mm)",
            0.0, 1000.0, 0.0, 0.1,
            help=GLOSS["delta"] + " This is the number straight out "
                 "of the analysis run with the reduced forces - "
                 "before the Rd Ro / IE amplification.")

    st.latex(r"\text{Interstorey drift limit} = %.3f\, h_s"
             r" \qquad (%s\ \text{Importance Category})"
             % (dl, cat_seis))
    explain("hs", "delta", "Rd", "Ro", "IE")
    if hs_mm > 0 and d_elastic > 0:
        _amp = Rd * Ro / IE
        _d_real = d_elastic * _amp
        _d_allow = dl * hs_mm
        st.caption("The elastic analysis was run with forces already "
                   "divided by Rd Ro, so its deflections are far too "
                   "small - the real structure yields and sways "
                   "further. Multiply back up:")
        st.latex(r"\delta_{anticipated} = \delta_{elastic}\,"
                 r"\frac{R_d R_o}{I_E} = %.2f \times \frac{%.1f "
                 r"\times %.1f}{%.1f} = %.2f\ \text{mm}"
                 % (d_elastic, Rd, Ro, IE, _d_real))
        st.latex(r"\delta_{allow} = %.3f\,h_s = %.3f \times %.0f"
                 r" = %.2f\ \text{mm}" % (dl, dl, hs_mm, _d_allow))
        if _d_real <= _d_allow:
            st.success("Drift PASS: %.2f mm <= %.2f mm (%.0f%% of "
                       "the limit)."
                       % (_d_real, _d_allow,
                          100.0 * _d_real / _d_allow))
        else:
            st.error("Drift FAIL: %.2f mm exceeds the %.2f mm limit "
                     "by %.0f%%. Stiffen the SFRS or accept a "
                     "dynamic analysis."
                     % (_d_real, _d_allow,
                        100.0 * (_d_real / _d_allow - 1.0)))
    else:
        st.caption("Enter hs and the elastic interstorey deflection "
                   "above to run the worked drift check. Deflections "
                   "from the linear analysis include torsion and are "
                   "multiplied by Rd Ro / IE = %.3f to obtain "
                   "anticipated values." % (Rd * Ro / IE))

    # ---- 8.10 Simplified method --------------------------------------
    st.subheader("8.10  Simplified Method for Low Seismicity")
    st.caption("Cl. 4.1.8.1.(2) to (15)")

    if sa_450 is None:
        st.info("Sa(T,X450) is required for this check and was not "
                "retrieved. Enable the NRCan fetch to evaluate "
                "Cl. 4.1.8.1.(2).")
    else:
        f1, f2 = st.columns(2)
        with f1:
            fs_basis = st.selectbox(
                "Fs basis (Cl. 4.1.8.1.(2)(b))",
                ["Rock site", "N60", "su"], index=0,
                help="Fs is the simplified method's whole-site "
                     "coefficient: 1.0 rock, 1.6 medium ground, 2.8 "
                     "soft ground, judged from the top 30 m below "
                     "the foundations using N60 (granular soils) or "
                     "su (clays) from the geotech report.")
        with f2:
            if fs_basis == "N60":
                Fs, fs_why = nbcc.site_coefficient_Fs(
                    n60=st.number_input("N60 below the footings",
                                        0.0, 200.0, 60.0, 1.0,
                                        key="fs_n60",
                                        help=GLOSS["N60"]))
            elif fs_basis == "su":
                Fs, fs_why = nbcc.site_coefficient_Fs(
                    su=st.number_input("su below the footings (kPa)",
                                       0.0, 500.0, 120.0, 1.0,
                                       key="fs_su",
                                       help=GLOSS["su"]))
            else:
                Fs, fs_why = nbcc.site_coefficient_Fs(rock=True)

        applies, chk02, chk20 = nbcc.simplified_method_applies(
            IE, Fs, sa_450)
        st.latex(r"F_s = %.1f \quad (%s)" % (Fs, fs_why))
        explain("Fs", "Rs", "Ts", "Vs")
        st.latex(r"I_E F_s S_a(0.2, X_{450}) = %.4f \ (< 0.16?)"
                 r" \qquad I_E F_s S_a(2.0, X_{450}) = %.4f \ (< 0.03?)"
                 % (chk02, chk20))

        if applies:
            st.success("Cl. 4.1.8.1.(2) is satisfied. The simplified "
                       "method of Sentences (3) to (15) is permitted.")
            Ts, ts_expr = nbcc.simplified_period(period_sys, hn,
                                                 n_storeys)
            weak_storey = st.checkbox("Storey strength less than the "
                                      "storey above, or unreinforced "
                                      "masonry SFRS (Rs = 1.0)",
                                      value=False,
                                      help=GLOSS["Rs"])
            Rs = 1.0 if weak_storey else 1.5
            sa_ts = nbcc.sa_Ts(sa_450, Ts)
            sa05 = float(sa_450.get("S(0.5)",
                                    sa_450.get("Sa(0.5)", 0.0)))
            Vs, Vs_raw, Vs_cap = nbcc.simplified_base_shear(
                Fs, sa_ts, IE, W_seis, Rs, sa_05=sa05)

            st.latex(r"%s = %.4f \ \text{s} \qquad "
                     r"S_a(T_s, X_{450}) = %.4f"
                     % (ts_expr.replace("Ta", "T_s")
                        .replace("hn", "h_n"), Ts, sa_ts))
            st.latex(r"V_s = \frac{F_s S_a(T_s, X_{450}) I_E W}{R_s}"
                     r" = \frac{%.1f \times %.4f \times %.1f "
                     r"\times %.1f}{%.1f} = %.2f\ \text{kN}"
                     % (Fs, sa_ts, IE, W_seis, Rs, Vs_raw))
            if Vs_cap is not None and Vs < Vs_raw:
                st.info("Rs = 1.5, so Vs need not exceed "
                        "Fs Sa(0.5,X450) IE W / Rs = %.2f kN. "
                        "This cap governs." % Vs_cap)
            st.success("Vs = %.2f kN" % Vs)

            if levels:
                sf, sum_wh_s = nbcc.simplified_distribute(Vs, levels)
                st.latex(r"F_x = V_s W_x h_x / \sum W_i h_i"
                         r" \qquad \text{(no } F_t "
                         r"\text{ term in this method)}")
                st.dataframe(pd.DataFrame([{
                    "Level": f["level"], "Wi (kN)": round(f["W"], 1),
                    "hi (m)": round(f["h"], 2),
                    "Fx (kN)": round(f["Fx"], 2)} for f in sf]),
                    hide_index=True, use_container_width=True)

            if abs(Rs - 1.5) < 1e-9:
                st.warning("Cl. 4.1.8.1.(12): with Rs = 1.5, design "
                           "forces due to earthquake effects must be "
                           "increased by 33% for: "
                           + "; ".join(nbcc.CONNECTION_UPLIFT_ELEMENTS)
                           + ".")

            st.markdown("**Appendages and cantilever elements** "
                        "(Cl. 4.1.8.1.(13) and (14))")
            a1, a2 = st.columns(2)
            with a1:
                Wp = st.number_input("Wp, weight of the element (kN)",
                                     0.0, 1e6, 0.0, 1.0,
                                     help=GLOSS["Wp"])
            with a2:
                urm_elem = st.checkbox(
                    "Unreinforced masonry element (Vsp doubled)",
                    value=False,
                    help="Unreinforced masonry is brittle - no "
                         "rebar means no ductility - so Cl. "
                         "4.1.8.1.(14) doubles the design force on "
                         "such elements.")
            if Wp > 0:
                sa02_450 = float(sa_450.get("S(0.2)",
                                            sa_450.get("Sa(0.2)", 0.0)))
                Vsp, vsp_note = nbcc.appendage_force(
                    sa02_450, Fs, IE, Wp, urm_elem)
                st.latex(r"V_{sp} = 0.9 S_a(0.2, X_{450}) F_s I_E W_p"
                         r" = 0.9 \times %.4f \times %.1f \times %.1f"
                         r" \times %.1f = \mathbf{%.2f}\ \text{kN}"
                         % (sa02_450, Fs, IE, Wp, Vsp))
                if vsp_note:
                    st.caption(vsp_note)

            st.caption("Cl. 4.1.8.1.(11) drift limit for this method: "
                       "%.3f hs, with deflections multiplied by "
                       "Rs/IE = %.3f." % (dl, Rs / IE))
        else:
            st.info("Cl. 4.1.8.1.(2) is not satisfied. The full "
                    "requirements of Articles 4.1.8.2 to 4.1.8.23 "
                    "apply, as computed above.")

    # ------------------------------------------------------------------
    st.header("9. Load Combinations")
    st.caption("NBCC 2020, Article 4.1.3.2 (ULS, Table 4.1.3.2-A) and "
               "Article 4.1.3.4 (SLS, Table 4.1.3.4). Combinations "
               "without crane loads.")

    st.markdown(
        "Enter the effect of each specified load on the member or "
        "connection you are checking, in one consistent unit. The "
        "snow and wind effects are pre-filled from the loads computed "
        "above, so if you are checking a load on a roof surface in "
        "kPa they can be used directly; for a member force, replace "
        "them with the corresponding reaction.")

    lcu = st.text_input("Units of the effects below", value="kPa",
                        max_chars=12)

    e1, e2, e3 = st.columns(3)
    with e1:
        eD = st.number_input("D, dead load effect", -1e7, 1e7,
                             0.0, 0.01, format="%.4f")
        eL = st.number_input("L, live load effect", -1e7, 1e7,
                             0.0, 0.01, format="%.4f")
    with e2:
        eS = st.number_input("S, snow load effect", -1e7, 1e7,
                             float(round(S_load, 4)), 0.01,
                             format="%.4f")
        eW = st.number_input("W, wind load effect", -1e7, 1e7,
                             float(round(net_df["Governing (kPa)"]
                                         .iloc[0], 4))
                             if len(net_df) else 0.0,
                             0.01, format="%.4f")
    with e3:
        eE = st.number_input("E, earthquake load effect", -1e7, 1e7,
                             0.0, 0.01, format="%.4f")
        st.caption("E is the effect of the seismic force V computed in "
                   "Section 8, resolved into the member you are "
                   "checking. V = %.1f kN." % V)

    m1, m2 = st.columns(2)
    with m1:
        storage_area = st.checkbox(
            "Storage area, equipment area or service room "
            "(Cl. 4.1.3.2.(7): companion factor on L increased by 0.5)",
            value=False)
    with m2:
        liquid_tank = st.checkbox(
            "Liquids in tanks (Cl. 4.1.3.2.(6): principal factor on L "
            "reduced from 1.5 to 1.25)", value=False)

    st.markdown("**Ultimate limit states - Table 4.1.3.2-A**")
    st.caption("Each case is listed with the alternative dead load "
               "factors of Cl. 4.1.3.2.(5) - 1.25D or the "
               "counteracting 0.9D, and 1.0D in Case 5 - and with the "
               "companion load taken as zero as required by "
               "Cl. 4.1.3.2.(3). Wind and earthquake are enumerated in "
               "both directions.")

    uls_rows = uls_combinations(eD, eL, eS, eW, eE,
                                storage=storage_area,
                                liquids=liquid_tank)

    uls_df = pd.DataFrame([{
        "Case": r["Case"],
        "Load combination": r["Combination"],
        "Effect (%s)" % lcu: round(r["Effect"], 4)} for r in uls_rows])
    uls_df = uls_df.sort_values("Effect (%s)" % lcu,
                                key=lambda s: s.abs(), ascending=False)
    st.dataframe(uls_df, hide_index=True, use_container_width=True,
                 height=380)

    if len(uls_df):
        gov = uls_df.iloc[0]
        st.success("Governing ULS combination: Case %d, %s, "
                   "effect = %.4f %s"
                   % (gov["Case"], gov["Load combination"],
                      gov["Effect (%s)" % lcu], lcu))
        gmax = uls_df["Effect (%s)" % lcu].max()
        gmin = uls_df["Effect (%s)" % lcu].min()
        st.caption("Envelope: %.4f %s to %.4f %s. Where the two have "
                   "opposite signs the member sees a full reversal, "
                   "and the counteracting 0.9D cases are the ones to "
                   "watch for uplift, sliding and anchorage."
                   % (gmin, lcu, gmax, lcu))

    st.markdown("**Serviceability limit states - Table 4.1.3.4**")
    st.caption("Deflection for materials not subject to creep. Load "
               "factors of 1.0 on the principal load throughout.")

    sls_rows = sls_combinations(eD, eL, eS, eW, storage=storage_area)
    sls_df = pd.DataFrame([{
        "Case": r["Case"],
        "Load combination": r["Combination"],
        "Effect (%s)" % lcu: round(r["Effect"], 4)} for r in sls_rows])
    sls_df = sls_df.sort_values("Effect (%s)" % lcu,
                                key=lambda s: s.abs(), ascending=False)
    st.dataframe(sls_df, hide_index=True, use_container_width=True,
                 height=300)

    with st.expander("Notes carried from Article 4.1.3.2"):
        st.markdown(
            "- Sentence (4): where lateral earth pressure H, "
            "pre-stress P or imposed deformation T affect structural "
            "safety, apply them with factors of 1.5, 1.0 and 1.25 "
            "respectively. They are not enumerated above.\n"
            "- Sentence (8): the 1.25 factor on dead load from soil, "
            "superimposed earth, plants and trees rises to 1.5, except "
            "that for soil deeper than 1.2 m it may be reduced to "
            "1 + 0.6/hs but not below 1.25.\n"
            "- Sentence (10): the earthquake load E in Case 5 includes "
            "horizontal earth pressure due to earthquake per "
            "Cl. 4.1.8.16.(7).\n"
            "- Sentence (12): sway effects from vertical loads acting "
            "on the displaced structure must be included, using the "
            "deflections of Cl. 4.1.8.13.(2).\n"
            "- Crane loads are covered by Table 4.1.3.2-B, which is "
            "not implemented on this page.")

    # ------------------------------------------------------------------
    st.header("10. Summary")
    st.dataframe(pd.DataFrame({
        "Load": ["Site", "Snow, S", "Wind, governing external p",
                 "Wind, internal pi (suction)",
                 "Wind, internal pi (pressure)",
                 "Seismic, Seismic Category", "Seismic, Ta",
                 "Seismic, V", "Seismic, V/W",
                 "Governing ULS combination"],
        "Value": ["%s, %s (%.4f, %.4f)" % (loc, prov, lat, lon),
                  "%.3f kPa" % S_load, "%.3f kPa" % worst[1][1],
                  "%.3f kPa" % pi_neg, "%.3f kPa" % pi_pos,
                  "SC%d" % SC, "%.3f s" % Ta, "%.1f kN" % V,
                  "%.4f" % VW,
                  ("%s = %.4f %s" % (uls_df.iloc[0]["Load combination"],
                                     uls_df.iloc[0]["Effect (%s)" % lcu],
                                     lcu)) if len(uls_df) else "-"],
        "Reference": ["Table C-2", "Cl. 4.1.6.2", "Cl. 4.1.7.6",
                      "Cl. 4.1.7.7", "Cl. 4.1.7.7", "Table 4.1.8.5-B",
                      "Cl. 4.1.8.11.(3)", "Cl. 4.1.8.11.(2)",
                      "Cl. 4.1.8.11.(2)", "Table 4.1.3.2-A"],
    }), hide_index=True, use_container_width=True)


# ----------------------------------------------------------------------
# Viewer
# ----------------------------------------------------------------------
with RIGHT:
    st.subheader("3D Model")

    surf_payload = {}
    for s in SURFACES_B:
        key_a = ("A", s)
        key_b = ("B", s)
        if key_a in p_all:
            cgcp, p = p_all[key_a]
        else:
            cgcp, p = p_all[key_b]
        surf_payload[s] = {"cgcp": round(cgcp, 3), "p": round(p, 4)}

    payload = build_payload(
        geom={"W": W_bldg, "L": L_bldg, "He": H_eaves, "Hr": H_roof,
              "wh": round(W_roof_h, 3), "ws": round(W_roof_s, 3),
              "lr": round(L_roof, 3),
              "alpha": round(alpha, 2), "z": round(z_end, 3)},
        wind={"surfaces": surf_payload,
              "q": q_ref, "Ce": Ce, "Cg": Cg, "Ct": Ct, "Iw": Iw,
              "pmax_abs": round(max(abs(v["p"]) for v in
                                    surf_payload.values()), 4),
              "governing_case": worst[0][0]},
        snow={"S": round(S_load, 3), "Ss": Ss, "Sr": Sr, "Is": Is,
              "Cb": round(Cb, 3), "Cw": Cw, "Cs": round(Cs, 3), "Ca": Ca},
        seismic={"V_over_W": round(VW, 5) if VW == VW else 0.0,
                 "V": round(V, 2), "W": round(W_seis, 1),
                 "Ta": round(Ta, 4),
                 "S_Ta": round(bs["S_Ta"], 5)
                 if bs["S_Ta"] == bs["S_Ta"] else 0.0,
                 "Rd": Rd, "Ro": Ro, "IE": IE, "Mv": round(Mv, 3),
                 "SC": SC, "site_class": site_class,
                 "forces": [{"level": f["level"], "h": f["h"],
                             "Fx": round(f["Fx"], 3)}
                            for f in forces],
                 "hn": hn},
    )
    render_viewer(payload, height=640)

    st.caption("Wind surfaces follow Figure 4.1.7.6-A. Surfaces 1 to 4 "
               "are the Load Case A values across the ridge; 5 and 6 are "
               "the Load Case B side walls. Red is positive pressure, "
               "blue is suction.")