"""
Infraspective Solutions - Global UI Theme
Apply to every page:  from _theme import apply_theme, render_sidebar_logo, render_footer

ASCII only. Straight quotes only.
"""
from __future__ import annotations
import base64
# base64 is used to encode binary data into ASCII characters
import io
import os
from pathlib import Path
import streamlit as st

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    _HAS_PIL = True
    _PIL_ERR = ""
except Exception as _e:
    _HAS_PIL = False
    _PIL_ERR = str(_e)


# ---- Logo helpers ---------------------------------------------------------
# Bump this when the knockout logic changes, to bust the cache.
_KNOCKOUT_VERSION = "3"

_HERE = Path(__file__).parent

# Searched in order. The first file that exists wins.
_BRAND_CANDIDATES = [
    _HERE / "static" / "logo_wordmark.jpg",
    _HERE / "static" / "logo_wordmark.png",
    _HERE / "static" / "logo_wordmark.jpeg",
    _HERE / "static" / "logo_mark.png",
    _HERE / "static" / "logo.png",
    _HERE / "static" / "logo.jpg",
    _HERE / "attached_assets" / "logo_wordmark.jpg",
    _HERE / "attached_assets" / "logo.png",
    _HERE / "attached_assets" / "logo.jpg",
]

_LOGO_PATH = _HERE / "static" / "logo_mark.png"

# Sentinel colour used to flag the flooded background. Cannot occur in a
# greyscale wordmark.
_KEY_RGB = (255, 0, 255)

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _brand_file() -> Path | None:
    """First brand image that actually exists on disk."""
    for p in _BRAND_CANDIDATES:
        try:
            if p.exists():
                return p
        except OSError:
            continue
    # Last resort: any image in static/ whose name mentions the brand.
    sdir = _HERE / "static"
    if sdir.is_dir():
        try:
            for n in sorted(os.listdir(sdir)):
                low = n.lower()
                if low.endswith(tuple(_MIME_BY_EXT)) and (
                        "logo" in low or "infraspective" in low
                        or "wordmark" in low or "brand" in low):
                    return sdir / n
        except OSError:
            pass
    return None


def _raw_src(p: Path) -> str:
    """A file as a data-URI, untouched."""
    try:
        mime = _MIME_BY_EXT.get(p.suffix.lower(), "image/png")
        with open(p, "rb") as f:
            return "data:" + mime + ";base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return ""


def _logo_b64() -> str:
    for p in (
        _HERE / "static" / "logo_mark.png",
        _HERE / "static" / "logo.png",
        _HERE / "static" / "logo.jpg",
    ):
        if p.exists():
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return ""


def _wordmark_src() -> str:
    """The brand image as a data-URI, exactly as supplied. Used in the
    sidebar, where the artwork sits on a deliberate rounded plate."""
    p = _brand_file()
    return _raw_src(p) if p else ""


def _flood_alpha(base, thresh):
    """Flood the outer field with the sentinel, return (alpha, fraction).

    fraction is how much of the image was keyed out. Used to tell a good
    knockout from a flood that stalled on texture (fraction near 0) or one
    that leaked through the artwork (fraction near 1).
    """
    trial = base.copy()
    w, h = trial.size
    seeds = [
        (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
        (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2),
        (w // 4, 0), (3 * w // 4, 0), (w // 4, h - 1), (3 * w // 4, h - 1),
    ]
    for xy in seeds:
        try:
            ImageDraw.floodfill(trial, xy, _KEY_RGB, thresh=int(thresh))
        except Exception:
            pass

    key_plane = Image.new("RGB", (w, h), _KEY_RGB)
    diff = ImageChops.difference(trial, key_plane).convert("L")
    alpha = diff.point(lambda v: 0 if v < 8 else 255)

    removed = alpha.histogram()[0]
    return alpha, float(removed) / float(w * h)


@st.cache_data(show_spinner=False)
def _knockout(path_str: str, mtime: float, version: str,
              feather: float = 0.8, max_width: int = 900) -> tuple:
    """Return (data_uri, note). data_uri is "" when the knockout failed.

    The source is usually a JPEG, so the off-white field around the mark is
    part of the pixel data and no amount of CSS will hide it. This floods
    inward from the edges and keys out only that contiguous outer field,
    which leaves anything enclosed by dark strokes - the silver SPEC box -
    intact. A global colour match would eat that box.

    The threshold escalates because the artwork has a paper texture and a
    soft vignette; a single fixed threshold can stall partway across the
    background.
    """
    if not _HAS_PIL:
        return "", "Pillow unavailable: " + _PIL_ERR

    p = Path(path_str)
    if not p.exists():
        return "", "file not found: " + path_str

    try:
        src = Image.open(p).convert("RGB")
    except Exception as e:
        return "", "could not open: " + str(e)

    if max_width and src.width > max_width:
        ratio = float(max_width) / float(src.width)
        src = src.resize((max_width, int(src.height * ratio)), Image.LANCZOS)

    best = None
    best_frac = 0.0
    tried = []
    for th in (36, 55, 80, 110, 145):
        try:
            alpha, frac = _flood_alpha(src, th)
        except Exception:
            tried.append(str(th) + ":err")
            continue
        tried.append(str(th) + ":" + "{:.2f}".format(frac))
        if 0.12 <= frac <= 0.88:
            best = alpha
            best_frac = frac
            break
        if frac > best_frac and frac < 0.88:
            best = alpha
            best_frac = frac

    if best is None or best_frac < 0.05:
        return "", "flood removed too little (" + ", ".join(tried) + ")"

    if feather > 0:
        try:
            best = best.filter(ImageFilter.GaussianBlur(radius=float(feather)))
        except Exception:
            pass

    out = src.convert("RGBA")
    out.putalpha(best)

    buf = io.BytesIO()
    try:
        out.save(buf, format="PNG", optimize=True)
    except Exception as e:
        return "", "PNG save failed: " + str(e)

    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return uri, "ok, removed {:.0%} at thresholds [{}]".format(
        best_frac, ", ".join(tried))


def _wordmark_blended_src() -> tuple:
    """(src, is_transparent, note) for the disclaimer gate.

    Prefers the keyed-out PNG. Falls back to the raw file, in which case the
    caller applies the multiply blend so the rectangle at least softens.
    """
    p = _brand_file()
    if p is None:
        return "", False, "no brand file found under static/"

    try:
        mt = p.stat().st_mtime
    except OSError:
        mt = 0.0

    uri, note = _knockout(str(p), mt, _KNOCKOUT_VERSION)
    if uri:
        return uri, True, "using " + p.name + " - " + note

    raw = _raw_src(p)
    return raw, False, "fallback to raw " + p.name + " - " + note


def _brand_b64() -> str:
    return _logo_b64()


def _logo_debug_on() -> bool:
    """True when ?logodebug=1 is on the URL."""
    try:
        v = st.query_params.get("logodebug")
    except Exception:
        try:
            v = (st.experimental_get_query_params().get("logodebug") or [None])[0]
        except Exception:
            v = None
    return str(v) in ("1", "true", "yes")


# ---- Palette --------------------------------------------------------------
BLUE_DARK   = "#0F172A"
BLUE_NAV    = "#1E3A8A"
BLUE_MID    = "#1E40AF"
BLUE        = "#2563EB"
BLUE_LIGHT  = "#BFDBFE"
BLUE_XLIGHT = "#EFF6FF"
RED         = "#DC2626"
WHITE       = "#FFFFFF"
GREY_MID    = "#64748B"

# ---- CSS ------------------------------------------------------------------
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');

/* ===== GLOBAL TYPE + BASE ============================================== */
html, body, [class*="css"], .stApp,
button, input, select, textarea, .stMarkdown {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    -webkit-font-smoothing: antialiased;
}
.stApp {
    background:
        radial-gradient(1200px 600px at 100% -10%, rgba(37,99,235,0.06), transparent 60%),
        radial-gradient(900px 500px at -10% 110%, rgba(30,58,138,0.05), transparent 55%),
        #F8FAFC !important;
}
/* no horizontal scroll anywhere */
[data-testid="stAppViewContainer"] { overflow-x: hidden !important; }
[data-testid="stMarkdownContainer"] img,
[data-testid="stMarkdownContainer"] svg { max-width: 100% !important; height: auto !important; }

/* ===== SIDEBAR ========================================================= */
[data-testid="stSidebar"] {
    background: linear-gradient(175deg,#0B1220 0%,#0F172A 42%,#1E3A8A 100%) !important;
    border-right: 1px solid rgba(37,99,235,0.55) !important;
    box-shadow: 4px 0 24px rgba(15,23,42,0.18) !important;
}
/* subtle blueprint grid overlay */
[data-testid="stSidebar"]::before {
    content: "";
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(rgba(147,197,253,0.045) 1px, transparent 1px),
        linear-gradient(90deg, rgba(147,197,253,0.045) 1px, transparent 1px);
    background-size: 26px 26px;
    pointer-events: none;
}
[data-testid="stSidebar"] > div { padding-top: 0.4rem !important; }
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label { color: #CBD5E1 !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #FFFFFF !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* -- Sidebar brand plate. The dark navy needs a light card behind the
   artwork, so the plate is kept here on purpose. -- */
.ins-logo {
    text-align: center;
    padding: 14px 10px 0;
    margin: 4px 4px 0;
}
.ins-logo img {
    width: 100%;
    max-width: 235px;
    height: auto;
    display: block;
    margin: 0 auto;
    border-radius: 18px;
    border: 1px solid rgba(147,197,253,0.35);
    box-shadow: 0 0 0 1px rgba(255,255,255,0.06),
                0 10px 26px rgba(6,12,34,0.55),
                0 0 22px rgba(37,99,235,0.35),
                inset 0 1px 0 rgba(255,255,255,0.4);
    transition: transform .22s ease, box-shadow .22s ease;
    cursor: pointer;
}
.ins-logo img:hover {
    transform: translateY(-2px) scale(1.015);
    box-shadow: 0 0 0 1px rgba(255,255,255,0.10),
                0 14px 32px rgba(6,12,34,0.6),
                0 0 34px rgba(96,165,250,0.55),
                inset 0 1px 0 rgba(255,255,255,0.5);
}
.ins-tagline {
    text-align: center;
    color: #7FA9F0 !important;
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    margin: 2px 0 14px;
}
.ins-sidebar-divider {
    height: 1px;
    margin: 2px 14px 14px;
    background: linear-gradient(90deg, transparent, rgba(127,169,240,0.5), transparent);
}
.ins-nav-label {
    color: #7FA9F0 !important;
    font-size: 0.60rem;
    font-weight: 800;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    padding: 2px 12px 8px;
    margin: 0;
}

/* -- Custom page-link nav (icons + smooth hover) -- */
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"],
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
    color: #CBD5E1 !important;
    font-weight: 600 !important;
    border-radius: 11px !important;
    padding: 0.62rem 0.85rem !important;
    margin: 3px 4px !important;
    display: flex !important;
    align-items: center !important;
    gap: 11px !important;
    border: 1px solid transparent !important;
    transition: transform .18s ease, background .18s ease,
                border-color .18s ease, color .18s ease !important;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover,
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {
    background: rgba(37,99,235,0.18) !important;
    border-color: rgba(37,99,235,0.45) !important;
    color: #FFFFFF !important;
    transform: translateX(4px) !important;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"],
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {
    background: linear-gradient(90deg, rgba(37,99,235,0.42), rgba(37,99,235,0.14)) !important;
    border-color: rgba(96,165,250,0.6) !important;
    color: #FFFFFF !important;
    box-shadow: inset 3px 0 0 #60A5FA, 0 6px 16px rgba(37,99,235,0.25) !important;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] span[data-testid="stIconMaterial"] {
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p,
[data-testid="stSidebar"] [data-testid="stPageLink"] a p {
    font-weight: 600 !important;
    color: inherit !important;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] span[data-testid="stIconMaterial"] {
    color: #7FA9F0 !important;
    transition: color .18s ease !important;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover span[data-testid="stIconMaterial"] {
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] svg { fill: #93C5FD !important; }

/* -- Locked (coming-soon) calculators -- */
.ins-nav-locked {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 0.62rem 0.85rem;
    margin: 3px 4px;
    border-radius: 11px;
    color: #5B6B85 !important;
    font-weight: 600;
    font-size: 0.875rem;
    cursor: not-allowed;
    border: 1px dashed rgba(91,107,133,0.35);
    background: rgba(15,23,42,0.25);
}
.ins-nav-locked .lock-ic {
    font-family: 'Material Symbols Outlined';
    font-size: 1.05rem;
    color: #5B6B85 !important;
}
.ins-nav-locked .lk-label { flex: 1; color: #5B6B85 !important; }
.ins-nav-locked .lk-soon {
    font-size: 0.55rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #7FA9F0 !important;
    background: rgba(37,99,235,0.18);
    border: 1px solid rgba(37,99,235,0.35);
    padding: 2px 7px;
    border-radius: 10px;
}

/* ===== TOP HEADER BAR - clean and minimal ============================== */
[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
    height: 3rem !important;
}
[data-testid="stHeader"] button svg { fill: #1E3A8A !important; color: #1E3A8A !important; }

/* -- Obvious, tappable sidebar toggle (hamburger) -- */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stExpandSidebarButton"] {
    background: linear-gradient(135deg,#1E3A8A 0%,#2563EB 100%) !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
    border-radius: 12px !important;
    box-shadow: 0 6px 18px rgba(37,99,235,0.40) !important;
    padding: 6px !important;
}
[data-testid="collapsedControl"] svg,
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stExpandSidebarButton"] svg {
    fill: #FFFFFF !important;
    color: #FFFFFF !important;
    width: 1.35rem !important;
    height: 1.35rem !important;
}

/* ===== MAIN CONTAINER ================================================== */
.block-container {
    padding-top: 2.2rem !important;
    padding-bottom: 4.5rem !important;
    max-width: 1440px !important;
}

/* ===== HEADINGS ======================================================== */
h1 {
    color: #0F172A !important;
    font-weight: 800 !important;
    letter-spacing: -0.03em !important;
    border-bottom: 3px solid transparent !important;
    border-image: linear-gradient(90deg,#2563EB 0%,#60A5FA 45%,transparent 100%) 1 !important;
    padding-bottom: 0.5rem !important;
    margin-bottom: 1.35rem !important;
}
h2 {
    color: #1E3A8A !important;
    font-weight: 700 !important;
    letter-spacing: -0.015em !important;
    margin-top: 0.5rem !important;
}
h3 {
    color: #1E40AF !important;
    font-weight: 700 !important;
    border-left: 4px solid #2563EB !important;
    padding-left: 0.7rem !important;
    margin-top: 1.5rem !important;
    letter-spacing: -0.01em !important;
}
h4 { color: #1E40AF !important; font-weight: 600 !important; }

/* ===== METRIC CARDS ==================================================== */
[data-testid="metric-container"], [data-testid="stMetric"] {
    background: linear-gradient(150deg,#FFFFFF 0%,#EFF6FF 100%) !important;
    border: 1px solid #DBEAFE !important;
    border-top: 3px solid #2563EB !important;
    border-radius: 14px !important;
    padding: 1.05rem 1.25rem !important;
    box-shadow: 0 6px 18px rgba(37,99,235,0.10) !important;
    transition: transform .2s ease, box-shadow .2s ease !important;
}
[data-testid="metric-container"]:hover, [data-testid="stMetric"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 12px 26px rgba(37,99,235,0.18) !important;
}
[data-testid="stMetricLabel"] p {
    color: #1E40AF !important;
    font-weight: 700 !important;
    font-size: 0.70rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.10em !important;
}
[data-testid="stMetricValue"] {
    color: #0F172A !important;
    font-weight: 800 !important;
    font-variant-numeric: tabular-nums !important;
}

/* ===== BUTTONS ========================================================= */
.stButton > button, .stDownloadButton > button {
    background: linear-gradient(135deg,#1E40AF 0%,#2563EB 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
    letter-spacing: 0.03em !important;
    padding: 0.6rem 1.8rem !important;
    transition: transform .2s ease, box-shadow .2s ease, background .2s ease !important;
    box-shadow: 0 6px 16px rgba(37,99,235,0.28) !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: linear-gradient(135deg,#1E3A8A 0%,#3B82F6 100%) !important;
    box-shadow: 0 10px 24px rgba(37,99,235,0.42) !important;
    transform: translateY(-2px) !important;
}
.stButton > button:active { transform: translateY(0) !important; }
.stButton > button:focus-visible {
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.35) !important;
}
.stButton > button:disabled {
    background: #94A3B8 !important;
    box-shadow: none !important;
    transform: none !important;
}

/* ===== ALERTS ========================================================== */
[data-testid="stAlert"] { border-radius: 12px !important; }
[data-testid="stAlert"][data-type="success"], .stSuccess {
    background: #EFF6FF !important;
    border-left: 4px solid #2563EB !important;
    color: #1E40AF !important;
}
[data-testid="stAlert"][data-type="error"], .stError {
    background: #FEF2F2 !important;
    border-left: 4px solid #DC2626 !important;
    color: #991B1B !important;
}
[data-testid="stAlert"][data-type="warning"], .stWarning {
    background: #FFFBEB !important;
    border-left: 4px solid #D97706 !important;
}
[data-testid="stAlert"][data-type="info"], .stInfo {
    background: #EFF6FF !important;
    border-left: 4px solid #3B82F6 !important;
}

/* ===== EXPANDERS ======================================================= */
[data-testid="stExpander"] {
    border: 1px solid #DBEAFE !important;
    border-radius: 14px !important;
    overflow: hidden !important;
    box-shadow: 0 4px 14px rgba(15,23,42,0.06) !important;
    background: #FFFFFF !important;
}
[data-testid="stExpander"] details summary {
    background: linear-gradient(90deg,#EFF6FF 0%,#F8FAFC 100%) !important;
    border-bottom: 1px solid #DBEAFE !important;
    padding: 0.75rem 1.1rem !important;
    font-weight: 700 !important;
    color: #1E40AF !important;
    transition: background .18s ease !important;
}
[data-testid="stExpander"] details summary:hover { background: #DBEAFE !important; }

/* ===== CODE BLOCKS ===================================================== */
[data-testid="stCode"] pre, .stCode pre {
    background: #0F172A !important;
    color: #E2E8F0 !important;
    border-radius: 12px !important;
    border: 1px solid #1E3A8A !important;
    font-size: 0.82rem !important;
    line-height: 1.6 !important;
    font-family: 'JetBrains Mono','Fira Code','Cascadia Code',monospace !important;
}

/* ===== DIVIDERS ======================================================== */
hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg,#2563EB 0%,#BFDBFE 60%,transparent 100%) !important;
    margin: 1.8rem 0 !important;
}

/* ===== INPUTS / SELECTS ================================================ */
input[type="number"], input[type="text"],
[data-baseweb="input"], [data-baseweb="select"] > div {
    border-radius: 11px !important;
    font-variant-numeric: tabular-nums !important;
    transition: border-color .15s, box-shadow .15s !important;
}
[data-baseweb="input"], [data-baseweb="select"] > div {
    border-color: #CBD5E1 !important;
    background: #FFFFFF !important;
}
input:focus,
[data-baseweb="input"]:focus-within,
[data-baseweb="select"] > div:focus-within {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.16) !important;
}
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] > div > div { border-radius: 11px !important; }
[data-testid="stTextInput"] label, [data-testid="stNumberInput"] label,
[data-testid="stSelectbox"] label, [data-testid="stRadio"] label {
    font-weight: 600 !important;
    color: #334155 !important;
}
/* radio / tabs polish */
[data-baseweb="tab-list"] { gap: 4px !important; }
[data-baseweb="tab"] { border-radius: 10px 10px 0 0 !important; }

/* ===== DATAFRAMES ====================================================== */
[data-testid="stDataFrame"] { border-radius: 12px !important; overflow: hidden !important; }
[data-testid="stDataFrame"] thead th {
    background: #1E3A8A !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
}
[data-testid="stDataFrame"] tbody tr:nth-child(even) td { background: #EFF6FF !important; }

/* ===== CAPTIONS ======================================================== */
[data-testid="stCaptionContainer"] p, .stCaption {
    color: #64748B !important;
    font-size: 0.77rem !important;
    font-variant-numeric: tabular-nums !important;
}

/* ===== SIDEBAR NAV - auto nav hidden; replaced by custom st.page_link === */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"] { display: none !important; }

/* ===== SCROLLBAR ======================================================= */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #F1F5F9; border-radius: 3px; }
::-webkit-scrollbar-thumb { background: #BFDBFE; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #2563EB; }

/* ===== FOOTER BANNER =================================================== */
.ins-footer {
    position: fixed;
    bottom: 0; left: 0;
    width: 100%;
    background: rgba(15,23,42,0.96);
    backdrop-filter: blur(6px);
    border-top: 1px solid rgba(37,99,235,0.6);
    padding: 7px 22px;
    font-size: 0.70rem;
    color: #94A3B8;
    z-index: 9999;
    letter-spacing: 0.02em;
    display: flex;
    align-items: center;
    gap: 12px;
}
.ins-footer b { color: #93C5FD; font-weight: 800; letter-spacing: 0.06em; }
.ins-footer .sep { color: #334155; }
.block-container { padding-bottom: 4rem !important; }

/* ===== PAGE BANNER ===================================================== */
.page-banner {
    background: linear-gradient(90deg,#0F172A 0%,#1E3A8A 100%);
    border-radius: 14px;
    padding: 1rem 1.5rem;
    margin-bottom: 1.4rem;
    border-left: 5px solid #2563EB;
    display: flex;
    align-items: center;
    gap: 14px;
    box-shadow: 0 8px 22px rgba(15,23,42,0.15);
}
.page-banner .pb-title {
    font-size: 1.25rem;
    font-weight: 800;
    color: #FFFFFF;
    letter-spacing: -0.01em;
}
.page-banner .pb-sub {
    font-size: 0.78rem;
    color: #93C5FD;
    margin-top: 2px;
    letter-spacing: 0.03em;
}

/* ===== DISCLAIMER PAGE ================================================= */
.dis-wrap { max-width: 840px; margin: 0 auto; padding: 0 1rem; }
.dis-logo-block {
    text-align: center;
    padding: 1.6rem 1rem 1rem;
    background: transparent;
}

/* The soft blue plate. The pad lives on this wrapper, not on the image,
   so the wordmark - which is keyed to transparency in _theme.py before it
   ever reaches the browser - sits directly ON the blue instead of bringing
   its own grey rectangle along. */
.dis-logo-plate {
    display: inline-block;
    box-sizing: border-box;
    padding: 1.5rem 2rem;
    border-radius: 24px;
    background: linear-gradient(160deg,#FFFFFF 0%,#F3F7FE 55%,#E8F0FC 100%);
    border: 1px solid #DBEAFE;
    box-shadow:
        0 10px 28px rgba(37,99,235,0.12),
        0 2px 6px rgba(15,23,42,0.06),
        inset 0 1px 0 rgba(255,255,255,0.9);
    transition: transform .25s ease, box-shadow .25s ease;
}
.dis-logo-plate:hover {
    transform: translateY(-2px);
    box-shadow:
        0 16px 36px rgba(37,99,235,0.18),
        0 3px 8px rgba(15,23,42,0.08),
        inset 0 1px 0 rgba(255,255,255,0.9);
}
.dis-logo-plate img.wm {
    width: 68vw;
    max-width: 360px;
    height: auto;
    margin: 0 auto;
    display: block;
    padding: 0 !important;
    border: none !important;
    border-radius: 0 !important;
    background: transparent !important;
    background-image: none !important;
    box-shadow: none !important;
    mix-blend-mode: normal !important;
}

/* Fallback only: reached when the knockout could not run and the raw file
   has to be shown. Multiply at least softens the plate edge. */
.dis-logo-block img.wm-raw {
    max-width: 420px;
    width: 78vw;
    margin: 0 auto;
    display: block;
    box-sizing: border-box;
    padding: 1.1rem 1.6rem;
    border-radius: 22px;
    background: linear-gradient(160deg,#FFFFFF 0%,#F3F7FE 55%,#E8F0FC 100%);
    border: 1px solid #DBEAFE;
    mix-blend-mode: multiply;
    box-shadow:
        0 10px 28px rgba(37,99,235,0.12),
        0 2px 6px rgba(15,23,42,0.06),
        inset 0 1px 0 rgba(255,255,255,0.9);
}
.dis-beta {
    display: inline-block;
    background: linear-gradient(135deg,#1E40AF,#2563EB);
    color: #FFFFFF;
    font-size: 0.62rem;
    font-weight: 800;
    padding: 3px 12px;
    border-radius: 20px;
    letter-spacing: 0.16em;
    margin-top: 0.9rem;
    box-shadow: 0 4px 12px rgba(37,99,235,0.35);
}
.dis-box {
    background: #FFFFFF;
    border: 1px solid #DBEAFE;
    border-top: 3px solid #2563EB;
    border-radius: 16px;
    padding: 1.7rem 2rem;
    max-height: 50vh;
    overflow-y: auto;
    font-size: 0.87rem;
    line-height: 1.75;
    color: #0F172A;
    margin: 0.8rem 0;
    box-shadow: 0 8px 24px rgba(15,23,42,0.07);
}
.dis-box h1 {
    font-size: 0.95rem !important;
    font-weight: 800 !important;
    color: #0F172A !important;
    border: none !important;
    border-bottom: 1px solid #DBEAFE !important;
    padding-bottom: 0.35rem !important;
    margin-bottom: 0.8rem !important;
    letter-spacing: 0.05em !important;
}
.dis-box strong { color: #1E3A8A; }
.dis-box hr { background: #DBEAFE !important; margin: 0.9rem 0 !important; }

/* ===== RESPONSIVE / MOBILE ============================================= */
@media (max-width: 640px) {
    .block-container {
        padding-top: 3.2rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    h1 { font-size: 1.5rem !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.05rem !important; }
    .page-banner { padding: 0.85rem 1rem; }
    .page-banner .pb-title { font-size: 1.05rem; }
    .ins-footer {
        font-size: 0.62rem;
        padding: 6px 12px;
        gap: 7px;
        line-height: 1.3;
    }
    .dis-box { padding: 1.1rem 1.1rem; font-size: 0.83rem; }
    .dis-logo-plate { padding: 1.15rem 1.4rem; border-radius: 20px; }
    .dis-logo-plate img.wm { width: 62vw; max-width: 260px; }
    .dis-logo-block img.wm-raw { max-width: 300px; }
    /* keep the mobile toggle prominent */
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"] {
        top: 0.55rem !important;
        left: 0.55rem !important;
    }
    /* let long tables / diagrams scroll internally, never the page */
    [data-testid="stDataFrame"] { overflow-x: auto !important; }
}
</style>
"""


def apply_theme() -> None:
    """Inject global CSS. Call once per page before any UI."""
    st.markdown(_CSS, unsafe_allow_html=True)


# Sidebar navigation - single source of truth.
# (path, label, material icon, unlocked?)
_NAV = [
    ("pages/1_Tension_Members.py",     "Tension Members",      ":material/open_in_full:",           True),
    ("app.py",                         "Beam Flexure",         ":material/architecture:",           True),
    ("pages/2_Compression.py",         "Compression",          ":material/compress:",               True),
    ("pages/4_Beam_Column_Members.py", "Beam-Column Members",  ":material/view_column:",            True),
    ("pages/5_Bolted_Connections.py",  "Bolted Connections",   ":material/build:",                  False),
    ("pages/6_Welded_Connections.py",  "Welded Connections",   ":material/local_fire_department:",  True),
    ("pages/7_Lifting_Lug.py",         "Lifting Lug",          ":material/link:",                   True),
]


def render_sidebar_logo() -> None:
    """Brand wordmark on its plate + navigation. Locked calculators are
    shown greyed-out with a lock icon so users see what is coming."""
    src = _wordmark_src()
    if not src:
        b64 = _logo_b64()
        src = "data:image/png;base64," + b64 if b64 else ""
    if src:
        st.sidebar.markdown(
            '<div class="ins-logo">'
            '<img src="' + src + '" alt="Infraspective Solutions"/>'
            '</div>'
            '<div class="ins-tagline">Structural Suite</div>'
            '<div class="ins-sidebar-divider"></div>',
            unsafe_allow_html=True,
        )
    st.sidebar.markdown('<p class="ins-nav-label">Calculators</p>', unsafe_allow_html=True)
    for path, label, icon, unlocked in _NAV:
        if unlocked:
            st.sidebar.page_link(path, label=label, icon=icon)
        else:
            _lock_svg = (
                '<svg class="lock-ic" width="15" height="15" viewBox="0 0 24 24" '
                'fill="none" stroke="#5B6B85" stroke-width="2" stroke-linecap="round" '
                'stroke-linejoin="round" style="flex:none;">'
                '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>'
                '<path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>'
            )
            st.sidebar.markdown(
                '<div class="ins-nav-locked" title="Coming soon">'
                + _lock_svg
                + '<span class="lk-label">' + label + '</span>'
                '<span class="lk-soon">Soon</span>'
                '</div>',
                unsafe_allow_html=True,
            )


def render_footer() -> None:
    """Sticky branded footer bar."""
    st.markdown(
        '<div class="ins-footer">'
        '<b>INFRASPECTIVE SOLUTIONS</b>'
        '<span class="sep">|</span>'
        'Beta Software &mdash; All outputs must be independently verified by a licensed P.Eng. '
        'Not for direct project use without professional review.'
        '</div>',
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str = "") -> None:
    """Full-width branded header card with page title."""
    sub_html = (
        '<div style="font-size:0.82rem;color:#475569;margin-top:5px;">'
        + subtitle + '</div>'
    ) if subtitle else ""
    st.markdown(
        '<div style="background:linear-gradient(135deg,#FFFFFF 0%,#F1F5F9 100%);'
        'border-radius:16px;box-shadow:0 8px 24px rgba(15,23,42,0.08);'
        'border:1px solid #E2E8F0;border-left:5px solid #2563EB;'
        'padding:16px 24px;margin-bottom:1.5rem;">'
        '<div style="font-size:0.62rem;font-weight:800;letter-spacing:0.14em;'
        'color:#2563EB;text-transform:uppercase;margin-bottom:4px;">'
        'CSA S16 &nbsp;&middot;&nbsp; Infraspective Solutions'
        '</div>'
        '<div style="font-size:1.4rem;font-weight:800;color:#0F172A;'
        'line-height:1.1;letter-spacing:-0.02em;">'
        + title +
        '</div>'
        + sub_html +
        '</div>',
        unsafe_allow_html=True,
    )


def render_page_banner(title: str, subtitle: str = "") -> None:
    """Blue branded banner below the page title."""
    sub = '<div class="pb-sub">' + subtitle + '</div>' if subtitle else ""
    st.markdown(
        '<div class="page-banner"><div><div class="pb-title">'
        + title + '</div>' + sub + '</div></div>',
        unsafe_allow_html=True,
    )


def disclaimer_page() -> None:
    """
    Render the full disclaimer gate UI (branding + scrollable agreement +
    accept button). Hides the sidebar page-navigation so users cannot bypass
    the gate. Auto-scrolls the browser to the accept button on load.
    """
    import re
    import streamlit.components.v1 as _comp

    apply_theme()

    # The agreement stands alone: hide the sidebar (and its expand control)
    # until the user has accepted.
    st.markdown(
        '<style>'
        '[data-testid="stSidebar"] { display: none !important; }'
        '[data-testid="collapsedControl"],'
        '[data-testid="stSidebarCollapsedControl"],'
        '[data-testid="stExpandSidebarButton"] { display: none !important; }'
        '</style>',
        unsafe_allow_html=True,
    )

    src, is_transparent, dbg_note = _wordmark_blended_src()
    if src and is_transparent:
        # Keyed-out artwork sits inside the blue plate.
        logo_img = ('<div class="dis-logo-plate">'
                    '<img class="wm" src="' + src
                    + '" alt="Infraspective Solutions"/></div>')
    elif src:
        # Raw file carries its own plate via the wm-raw class.
        logo_img = ('<img class="wm-raw" src="' + src
                    + '" alt="Infraspective Solutions"/>')
    else:
        logo_img = (
            '<div style="font-size:1.8rem;font-weight:900;color:#0F172A;'
            'letter-spacing:0.06em">'
            'INFRASPECTIVE<br><span style="color:#2563EB">SOLUTIONS</span>'
            '</div>'
        )

    st.markdown(
        '<div class="dis-logo-block">'
        + logo_img
        + '<div><span class="dis-beta">BETA</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if _logo_debug_on():
        st.info("Logo diagnostics: " + dbg_note)
        found = _brand_file()
        st.caption("Resolved brand file: " + (str(found) if found else "none"))
        sdir = _HERE / "static"
        try:
            listing = ", ".join(sorted(os.listdir(sdir))) if sdir.is_dir() \
                else "static/ does not exist"
        except OSError as e:
            listing = "could not list static/: " + str(e)
        st.caption("static/ contains: " + listing)
        st.caption("Pillow available: " + str(_HAS_PIL)
                   + ("" if _HAS_PIL else " - " + _PIL_ERR))

    st.markdown(
        "<h3 style='text-align:center;font-size:1.05rem;color:#1E3A8A;"
        "letter-spacing:0.08em;border:none;padding:0;margin-bottom:0.5rem'>"
        "USER ACCESS AGREEMENT</h3>"
        "<p style='text-align:center;font-size:0.8rem;color:#64748B;margin-bottom:0.3rem'>"
        "Please read the full agreement below before proceeding.</p>",
        unsafe_allow_html=True,
    )

    # Agreement box (scrollable HTML)
    md = _DISCLAIMER_TEXT()
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", md, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"^---$", r"<hr>", html, flags=re.MULTILINE)
    html = re.sub(r"^\*(.+?)\*$", r"<em>\1</em>", html, flags=re.MULTILINE)
    st.markdown('<div class="dis-box">' + html + '</div>', unsafe_allow_html=True)

    accept = st.checkbox(
        "I have read and agree to the User Access Agreement. "
        "I understand this is Beta software and will independently verify "
        "all outputs before any reliance.",
        key="_dis_accept",
    )
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button("Enter Application", type="primary",
                     disabled=not accept, use_container_width=True,
                     key="_dis_enter"):
            st.session_state["accepted_disclaimer"] = True
            try:
                from activity import log_event
                log_event("agreement_accepted")
            except Exception:
                pass
            # Beta: Tension Members is the only unlocked calculator - open it.
            try:
                st.switch_page("pages/1_Tension_Members.py")
            except Exception:
                st.rerun()
    if not accept:
        st.caption("You must read and accept the agreement to continue.")

    # -- Auto-scroll to the accept area on every load --------------------
    _comp.html(
        """
        <script>
        (function() {
            function scrollToAccept() {
                try {
                    var doc = window.parent.document;
                    var btn = doc.querySelector('[data-testid="stButton"] button');
                    if (!btn) {
                        var allBtns = doc.querySelectorAll('button');
                        for (var i = 0; i < allBtns.length; i++) {
                            if (allBtns[i].innerText.includes('Enter')) {
                                btn = allBtns[i]; break;
                            }
                        }
                    }
                    if (btn) {
                        btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    } else {
                        var main = doc.querySelector('[data-testid="stAppViewContainer"]')
                                || doc.querySelector('.main')
                                || doc.body;
                        main.scrollTop = main.scrollHeight;
                    }
                } catch(e) {}
            }
            setTimeout(scrollToAccept, 300);
            setTimeout(scrollToAccept, 800);
        })();
        </script>
        """,
        height=0,
    )


INACTIVITY_TIMEOUT_S = 10 * 60  # 10 minutes


def _enforce_inactivity_timeout() -> None:
    """If more than INACTIVITY_TIMEOUT_S has passed since the last
    interaction, clear all session state (inputs, results, acceptance) so
    the user is returned to the agreement page."""
    import time
    now = time.time()
    last = st.session_state.get("_last_activity_ts")
    if (
        st.session_state.get("accepted_disclaimer", False)
        and last is not None
        and (now - last) > INACTIVITY_TIMEOUT_S
    ):
        try:
            from activity import log_event
            log_event("session_timeout")
        except Exception:
            pass
        st.session_state.clear()
    st.session_state["_last_activity_ts"] = now


def beta_lock_page(label: str) -> None:
    """Coming-soon panel for calculators that are locked during Beta.
    Call after gate_disclaimer(); halts the page."""
    st.markdown(
        '<div style="max-width:640px;margin:8vh auto 0;text-align:center;'
        'background:linear-gradient(135deg,#FFFFFF 0%,#F1F5F9 100%);'
        'border:1px solid #E2E8F0;border-radius:18px;'
        'box-shadow:0 12px 32px rgba(15,23,42,0.10);padding:2.6rem 2rem;">'
        '<div style="font-size:2rem;">&#128274;</div>'
        '<div style="font-size:1.25rem;font-weight:800;color:#0F172A;margin-top:.4rem;">'
        + label + '</div>'
        '<div style="font-size:0.85rem;color:#475569;margin-top:.6rem;line-height:1.6;">'
        'This calculator is <b>coming soon</b>. During the Beta, only '
        '<b>Tension Members</b> is available.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        st.write("")
        if st.button("Open Tension Members", type="primary",
                     use_container_width=True, key="_lock_go_tension"):
            st.switch_page("pages/1_Tension_Members.py")
    st.stop()


def gate_disclaimer() -> None:
    """
    Page-level disclaimer gate. Call at the top of every page (after
    apply_theme). Enforces the 10-minute inactivity timeout, then shows the
    agreement page if the user has not (or no longer) accepted it.
    """
    _enforce_inactivity_timeout()
    if not st.session_state.get("accepted_disclaimer", False):
        disclaimer_page()
        st.stop()


def _DISCLAIMER_TEXT() -> str:
    """Return DISCLAIMER_MD from app.py without circular import."""
    try:
        import re
        root = _HERE / "app.py"
        src = root.read_text(encoding="utf-8")
        m = re.search(r'DISCLAIMER_MD\s*=\s*"""(.*?)"""', src, re.DOTALL)
        return m.group(1) if m else ""
    except Exception:
        return ""
