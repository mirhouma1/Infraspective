"""
NBCC 2020 - Wind, Snow and Seismic Loads (Buildings)

Infraspective Solutions - structural calculator suite.

Ported from the "Wind, Snow & Seismic (Building)" tab of
Structural_Calculations_Simulation__2025-09-14_.xlsm

References (NBCC 2020, Division B, Part 4, Volume 1):
    Snow    - Article 4.1.6.2
    Wind    - Articles 4.1.7.3, 4.1.7.5, 4.1.7.6, 4.1.7.7
    Seismic - Articles 4.1.8.4, 4.1.8.5, 4.1.8.9, 4.1.8.11
    Climatic data - Table C-2, Appendix C

ASCII only. Straight quotes only. No markdown inside code.
"""

import os
import json
import math

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


def wind_exposure_factor_snow(north_of_treeline, exposure):
    """Cw per Cl. 4.1.6.2.(4). Default 1.0 unless the exposure
    conditions of the Code are satisfied."""
    if north_of_treeline:
        return 0.50
    if exposure == "Rural, fully exposed (Cw = 0.75)":
        return 0.75
    return 1.00


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
    <button class="tb tog" id="xray">X-ray</button>
    <button class="tb tog" id="dims">Dims</button>
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
dim([-hw,0,hl], [hw,0,hl], "W = " + W.toFixed(2) + " m", [0,-o*0.35,o]);
dim([hw,0,-hl], [hw,0,hl], "L = " + L.toFixed(2) + " m", [o,-o*0.35,0]);
dim([hw,0,hl], [hw,He,hl], "He = " + He.toFixed(2) + " m", [o*0.6,0,o*0.6]);
dim([hw,He,hl], [0,ridge,hl], "Hr = " + Hr.toFixed(2) + " m", [o*0.4,0,o*0.6]);
dimGrp.visible = false;
scene.add(dimGrp);

// ---- camera --------------------------------------------------------
camera.position.set(span * 1.7, span * 1.15, span * 1.9);
controls.target.set(0, HT * 0.42, 0);
controls.update();

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
      P.snow.S.toFixed(2) + " kPa</b> &nbsp; (slab thickness is to scale)";
  } else {
    legend.innerHTML =
      "<b>Seismic - Cl. 4.1.8</b><br>V = S(Ta) Mv IE W / (Rd Ro)<br>" +
      "Site Class " + P.seismic.site_class + " &nbsp; Rd = " +
      P.seismic.Rd.toFixed(2) + " &nbsp; Ro = " + P.seismic.Ro.toFixed(2) +
      "<br><b>V / W = " + P.seismic.V_over_W.toFixed(4) + "</b>" +
      " &nbsp; arrows show relative storey force";
  }
}
setLegend("wind");

document.querySelectorAll(".tb[data-mode]").forEach(b => {
  b.onclick = () => {
    document.querySelectorAll(".tb[data-mode]").forEach(
      x => x.classList.remove("active"));
    b.classList.add("active");
    const m = b.dataset.mode;
    windGrp.visible = (m === "wind");
    snowGrp.visible = (m === "snow");
    seisGrp.visible = (m === "seismic");
    setLegend(m);
  };
});
document.getElementById("xray").onclick = function(){
  this.classList.toggle("on");
  const on = this.classList.contains("on");
  skin.opacity = on ? 0.04 : 0.16;
  windGrp.children.forEach(c => {
    if (c.material && c.material.opacity !== undefined && c.isMesh)
      c.material.opacity = on ? 0.45 : 0.80;
  });
};
document.getElementById("dims").onclick = function(){
  this.classList.toggle("on");
  dimGrp.visible = this.classList.contains("on");
};

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
    g1, g2, g3 = st.columns(3)
    with g1:
        W_bldg = st.number_input("W, building width across ridge (m)",
                                 1.0, 300.0, 18.41, 0.01)
        H_eaves = st.number_input("He, eaves height (m)",
                                  1.0, 200.0, 11.40, 0.01)
    with g2:
        L_bldg = st.number_input("L, building length along ridge (m)",
                                 1.0, 600.0, 36.41, 0.01)
        H_roof = st.number_input("Hr, ridge rise above eaves (m)",
                                 0.0, 60.0, 2.907, 0.001)
    with g3:
        W_roof = st.number_input("w, roof tributary width (m)",
                                 1.0, 300.0, 25.00, 0.01)
        L_roof = st.number_input("l, roof length (m)",
                                 1.0, 600.0, 35.62, 0.01)

    H_total = H_eaves + H_roof
    H_ref = (H_total + H_eaves) / 2.0
    alpha = math.degrees(math.atan(H_roof / (0.5 * W_bldg)))
    least_dim = min(W_bldg, L_bldg)
    z_end = end_zone_width(least_dim, H_eaves)

    st.latex(r"\alpha = \arctan\!\left(\frac{H_r}{0.5\,W}\right)"
             r" = \arctan\!\left(\frac{%.3f}{0.5 \times %.2f}\right)"
             r" = %.2f^\circ" % (H_roof, W_bldg, alpha))
    st.latex(r"H_{ref} = \frac{H_{total} + H_{eaves}}{2}"
             r" = \frac{%.3f + %.2f}{2} = %.3f \ \text{m}"
             % (H_total, H_eaves, H_ref))
    st.latex(r"z = \min(0.1 D_{min},\, 0.4 H) \ \ge \ "
             r"\max(0.04 D_{min},\, 1.0) = %.2f \ \text{m}" % z_end)

    # ------------------------------------------------------------------
    st.header("2. Site Climatic Data")
    st.caption("NBCC 2020, Table C-2, Appendix C")

    provinces = sorted(c2["province"].unique().tolist())
    d1, d2 = st.columns(2)
    with d1:
        prov = st.selectbox("Province / Territory", provinces,
                            index=provinces.index("Alberta")
                            if "Alberta" in provinces else 0)
    sub = c2[c2["province"] == prov].sort_values("location")
    with d2:
        locs = sub["location"].tolist()
        default_i = locs.index("Calgary") if "Calgary" in locs else 0
        loc = st.selectbox("Location", locs, index=default_i)

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
        north_tl = st.checkbox("North of the treeline (lat >= 60 deg)",
                               value=False)
        exposure_snow = st.selectbox(
            "Exposure",
            ["Normal / sheltered (Cw = 1.0)",
             "Rural, fully exposed (Cw = 0.75)"], index=0)
    with s3:
        slippery = st.checkbox("Unobstructed slippery roof", value=False)
        Ca = st.number_input("Ca, accumulation factor",
                             0.0, 5.0, 1.0, 0.05,
                             help="1.0 for uniform snow. Use Cl. 4.1.6.5 "
                                  "to 4.1.6.11 for drift, sliding and "
                                  "projection cases.")

    Is = importance_factor_snow(ls_snow, cat_snow)
    Cw = wind_exposure_factor_snow(north_tl, exposure_snow)
    lc = characteristic_length(W_roof, L_roof)
    Cb, cb_limit, cb_branch = basic_roof_snow_factor(lc, Cw)
    Cs, cs_branch = roof_slope_factor(alpha, slippery)
    S_load, S_basic = snow_load(Is, Ss, Sr, Cb, Cw, Cs, Ca)

    st.latex(r"I_s = %.2f \qquad (%s,\ %s)" % (Is, ls_snow, cat_snow))
    st.latex(r"l_c = 2w - \frac{w^2}{l} = 2(%.2f) - \frac{%.2f^2}{%.2f}"
             r" = %.2f \ \text{m}" % (W_roof, W_roof, L_roof, lc))
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

    sp1, sp2, sp3 = st.columns(3)
    with sp1:
        lat = st.number_input("Latitude (deg N)", 41.0, 84.0,
                              51.0500, 0.0001, format="%.4f")
        lon = st.number_input("Longitude (deg E, negative W)",
                              -142.0, -52.0, -114.0700, 0.0001,
                              format="%.4f")
    with sp2:
        site_basis = st.radio("Site designation basis",
                              ["Site Class (Xs)", "Vs30 (Xv)"],
                              key="site_basis")
        if site_basis == "Site Class (Xs)":
            sc_mode = st.selectbox(
                "Determine Site Class from",
                ["Enter directly", "Vs30", "N60", "su"], index=0)
        else:
            sc_mode = "Vs30 designation"
    with sp3:
        if site_basis == "Vs30 (Xv)":
            vs30_in = st.number_input("Vs30 (m/s)", 50.0, 3000.0,
                                      450.0, 1.0)
            site_class = nbcc.site_class_from_vs30(vs30_in)
            site_designation = "X%.0f" % vs30_in
            st.caption("Equivalent Site Class %s" % site_class)
        elif sc_mode == "Vs30":
            vs30_in = st.number_input("Vs30 (m/s)", 50.0, 3000.0,
                                      450.0, 1.0)
            site_class = nbcc.site_class_from_vs30(vs30_in)
            site_designation = "X" + site_class
        elif sc_mode == "N60":
            n60_in = st.number_input("N60 (blows / 0.3 m)", 0.0,
                                     200.0, 60.0, 1.0)
            site_class = nbcc.site_class_from_n60(n60_in)
            site_designation = "X" + site_class
        elif sc_mode == "su":
            su_in = st.number_input("su (kPa)", 0.0, 500.0, 120.0, 1.0)
            site_class = nbcc.site_class_from_su(su_in)
            site_designation = "X" + site_class
        else:
            site_class = st.selectbox("Site Class",
                                      ["A", "B", "C", "D", "E", "F"],
                                      index=2)
            site_designation = "X" + site_class

    st.caption("Site Class %s - %s"
               % (site_class, nbcc.SITE_CLASS_DESC[site_class]))

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

    fetch_ok = st.checkbox("Fetch Sa(T) from the NRCan hazard service",
                           value=True)
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
                    format="%.4f", key="sa_manual_%.1f" % p)

    S = nbcc.design_spectrum(sa_site)
    interp_mode = st.radio("S(T) interpolation (Cl. 4.1.8.4.(6))",
                           ["log-log", "linear"], horizontal=True)

    spec_rows = [{"Period T (s)": "%.1f" % p,
                  "Sa(T,X) (g)": "%.4f" % float(
                      sa_site.get("S(%.1f)" % p, float("nan"))),
                  "S(T) (g)": "%.4f" % S["S(%.1f)" % p]}
                 for p in nbcc.SA_PERIODS]
    st.dataframe(pd.DataFrame(spec_rows), hide_index=True,
                 use_container_width=True)
    st.caption("Table 4.1.8.4-C: S(T) for T <= 0.2 s is the greater "
               "of Sa(0.2,X) and Sa(0.5,X).")

    if sa_450 is not None:
        Fa, Fv = nbcc.site_coefficients(S, sa_450)
        st.latex(r"F_a = \frac{S(0.2)}{S_a(0.2, X_{450})} = %.3f"
                 r" \qquad F_v = \frac{S(1.0)}{S_a(1.0, X_{450})}"
                 r" = %.3f" % (Fa, Fv))
        st.caption("Cl. 4.1.8.4.(7). Fa and Fv are for use in the "
                   "material standards referenced in Section 4.3.")

    # ---- 8.2 Importance factor and Seismic Category -------------------
    st.subheader("8.2  Importance Factor and Seismic Category")
    st.caption("Article 4.1.8.5, Tables 4.1.8.5-A and -B")

    cat_seis = st.selectbox(
        "Importance category",
        ["Low", "Normal", "High", "Post-disaster"], index=1,
        key="cat_seis")
    IE = nbcc.importance_factor(cat_seis)
    SC, ies02, ies10, sc_a, sc_b = nbcc.seismic_category(
        IE, S["S(0.2)"], S["S(1.0)"])

    st.latex(r"I_E = %.1f \qquad I_E S(0.2) = %.4f \ (SC%d)"
             r" \qquad I_E S(1.0) = %.4f \ (SC%d)"
             % (IE, ies02, sc_a, ies10, sc_b))
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
        grp = st.selectbox("Material / standard", nbcc.sfrs_groups(),
                           index=0)
    with sf2:
        opts = nbcc.sfrs_options(grp)
        default_i = 0
        for i, o in enumerate(opts):
            if "Conventional construction" in o and "Other" in o:
                default_i = i
                break
        sfrs_name = st.selectbox("Type of SFRS", opts, index=default_i)

    entry = nbcc.sfrs_lookup(grp, sfrs_name)
    Rd, Ro = entry["Rd"], entry["Ro"]

    hn = st.number_input("hn, height above the base to level n (m)",
                         1.0, 300.0, 10.0, 0.1)
    n_storeys = st.number_input("N, number of storeys above grade",
                                1, 100, 1, 1)

    st.latex(r"R_d = %.1f \qquad R_o = %.1f \qquad R_d R_o = %.2f"
             % (Rd, Ro, Rd * Ro))

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
        period_sys = st.selectbox("Period equation",
                                  nbcc.PERIOD_SYSTEMS, index=3)
        single_storey = st.checkbox("Single-storey with steel deck or "
                                    "wood roof diaphragm "
                                    "(Cl. 4.1.8.11.(4))", value=False)
    with p2:
        L_diaph = st.number_input("L, shortest diaphragm length (m)",
                                  0.0, 300.0, 30.0, 0.1,
                                  disabled=not single_storey)
        Ta_mech = st.number_input("Ta from a mechanics model (s) - "
                                  "0 to skip", 0.0, 20.0, 0.0, 0.001,
                                  format="%.3f")

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

    st.latex(r"%s = %.4f \ \text{s}"
             % (ta_expr.replace("Ta", "T_a").replace("hn", "h_n"),
                Ta_emp))
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
        W_dead = st.number_input("Dead load (kN)", 0.0, 1e7,
                                 4000.0, 10.0)
    with w2:
        W_snow = st.number_input("Specified snow load (kN)", 0.0, 1e7,
                                 800.0, 10.0)
    with w3:
        W_stor = st.number_input("Storage load (kN)", 0.0, 1e7,
                                 0.0, 10.0)
    with w4:
        W_tank = st.number_input("Tank contents (kN)", 0.0, 1e7,
                                 0.0, 10.0)

    W_seis = nbcc.seismic_weight(W_dead, W_snow, W_stor, W_tank)
    st.latex(r"W = D + 0.25 S + 0.60 (\text{storage}) + \text{tanks}"
             r" = %.0f + 0.25(%.0f) + 0.60(%.0f) + %.0f"
             r" = \mathbf{%.1f}\ \text{kN}"
             % (W_dead, W_snow, W_stor, W_tank, W_seis))

    mv_group = st.selectbox(
        "System group for Table 4.1.8.11",
        list(nbcc.MV_J_TABLE.keys()), index=2)
    Mv, Jf, sratio, mv_note = nbcc.mv_and_j(
        mv_group, S["S(0.2)"], S["S(5.0)"], Ta)

    st.latex(r"\frac{S(0.2)}{S(5.0)} = \frac{%.4f}{%.4f} = %.2f"
             r" \qquad M_v = %.3f \qquad J = %.3f"
             % (S["S(0.2)"], S["S(5.0)"], sratio, Mv, Jf))
    if mv_note:
        st.caption(mv_note)

    bs = nbcc.base_shear(S, Ta, Mv, IE, W_seis, Rd, Ro, mv_group,
                         site_designation, interp_mode)

    st.latex(r"V = \frac{S(T_a)\, M_v\, I_E\, W}{R_d R_o}"
             r" = \frac{%.4f \times %.3f \times %.1f \times %.1f}"
             r"{%.1f \times %.1f} = %.2f\ \text{kN}"
             % (bs["S_Ta"], Mv, IE, W_seis, Rd, Ro, bs["V_calc"]))
    st.latex(r"V_{min} = %.2f\ \text{kN}" % bs["V_min"])
    st.caption(bs["min_ref"])
    if bs["V_max"] is not None:
        st.latex(r"V_{max} = %.2f\ \text{kN}" % bs["V_max"])
        st.caption(bs["max_ref"])
    else:
        st.caption("Cl. 4.1.8.11.(2)(c) upper bound does not apply "
                   "(site is XF or Rd < 1.5).")

    V = bs["V"]
    st.success("V = %.2f kN.  %s" % (V, bs["governs"]))
    VW = V / W_seis if W_seis > 0 else float("nan")

    # ---- 8.8 Vertical distribution -----------------------------------
    st.subheader("8.8  Vertical Distribution and Overturning")
    st.caption("Cl. 4.1.8.11.(7) and (8)")

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

        st.latex(r"F_t = %.2f\ \text{kN}" % Ft)
        st.caption(ft_note)
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

        st.latex(r"M_x = J_x \sum_{i=x}^{n} F_i (h_i - h_x)"
                 r" \qquad J_x = 1.0 \ \text{for}\ h_x \ge 0.6 h_n,"
                 r"\quad J_x = J + (1-J)\frac{h_x}{0.6 h_n}"
                 r"\ \text{otherwise}")
        ot_rows = [{"Level": r["level"], "hx (m)": round(r["h"], 2),
                    "Jx": round(r["Jx"], 4),
                    "Mx (kN.m)": round(r["Mx"], 1)} for r in ot]
        st.dataframe(pd.DataFrame(ot_rows), hide_index=True,
                     use_container_width=True)
    else:
        forces, Ft, shears = [], 0.0, []
        st.warning("Enter at least one level with hi > 0.")

    # ---- 8.9 Torsion and drift ---------------------------------------
    st.subheader("8.9  Torsion and Drift")
    st.caption("Cl. 4.1.8.11.(9) to (11), Art. 4.1.8.13")

    t1, t2, t3 = st.columns(3)
    with t1:
        Dnx = st.number_input("Dnx, plan dimension perpendicular to "
                              "the loading (m)", 0.0, 300.0,
                              float(L_bldg), 0.01)
    with t2:
        ex_ecc = st.number_input("ex, eccentricity between the centres "
                                 "of mass and rigidity (m)",
                                 -50.0, 50.0, 0.0, 0.01)
    with t3:
        d_max = st.number_input("d_max, maximum storey displacement "
                                "(mm)", 0.0, 1000.0, 0.0, 0.1)
        d_ave = st.number_input("d_ave, average storey displacement "
                                "(mm)", 0.0, 1000.0, 0.0, 0.1)

    st.latex(r"T_x = F_x (e_x \pm 0.10 D_{nx})"
             r" \qquad 0.10 D_{nx} = %.3f \ \text{m}" % (0.10 * Dnx))
    if forces:
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
    st.latex(r"\text{Interstorey drift limit} = %.3f\, h_s"
             r" \qquad (%s\ \text{Importance Category})"
             % (dl, cat_seis))
    st.caption("Deflections from a linear analysis include torsion "
               "and are multiplied by Rd*Ro/IE = %.3f to obtain "
               "realistic values." % (Rd * Ro / IE))

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
            fs_basis = st.selectbox("Fs basis (Cl. 4.1.8.1.(2)(b))",
                                    ["Rock site", "N60", "su"],
                                    index=0)
        with f2:
            if fs_basis == "N60":
                Fs, fs_why = nbcc.site_coefficient_Fs(
                    n60=st.number_input("N60 below the footings",
                                        0.0, 200.0, 60.0, 1.0,
                                        key="fs_n60"))
            elif fs_basis == "su":
                Fs, fs_why = nbcc.site_coefficient_Fs(
                    su=st.number_input("su below the footings (kPa)",
                                       0.0, 500.0, 120.0, 1.0,
                                       key="fs_su"))
            else:
                Fs, fs_why = nbcc.site_coefficient_Fs(rock=True)

        applies, chk02, chk20 = nbcc.simplified_method_applies(
            IE, Fs, sa_450)
        st.latex(r"F_s = %.1f \quad (%s)" % (Fs, fs_why))
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
                                      value=False)
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
                                     0.0, 1e6, 0.0, 1.0)
            with a2:
                urm_elem = st.checkbox("Unreinforced masonry element "
                                       "(Vsp doubled)", value=False)
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
    st.header("9. Summary")
    st.dataframe(pd.DataFrame({
        "Load": ["Snow, S", "Wind, governing external p",
                 "Wind, internal pi (suction)",
                 "Wind, internal pi (pressure)",
                 "Seismic, Seismic Category", "Seismic, Ta",
                 "Seismic, V", "Seismic, V/W"],
        "Value": ["%.3f kPa" % S_load, "%.3f kPa" % worst[1][1],
                  "%.3f kPa" % pi_neg, "%.3f kPa" % pi_pos,
                  "SC%d" % SC, "%.3f s" % Ta, "%.1f kN" % V,
                  "%.4f" % VW],
        "Reference": ["Cl. 4.1.6.2", "Cl. 4.1.7.6", "Cl. 4.1.7.7",
                      "Cl. 4.1.7.7", "Table 4.1.8.5-B",
                      "Cl. 4.1.8.11.(3)", "Cl. 4.1.8.11.(2)",
                      "Cl. 4.1.8.11.(2)"],
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
