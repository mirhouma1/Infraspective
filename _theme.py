"""
Insfraspective Solutions — Global UI Theme
Apply to every page:  from _theme import apply_theme, render_sidebar_logo, render_footer
"""
from __future__ import annotations
import base64
from pathlib import Path
import streamlit as st

# ── Logo helpers ─────────────────────────────────────────────────────────────
_LOGO_PATH       = Path(__file__).parent / "static" / "logo.png"
_BRAND_LOGO_PATH = Path(__file__).parent / "static" / "logo_brand.jpg"


def _logo_b64() -> str:
    if _LOGO_PATH.exists():
        with open(_LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""


def _brand_b64() -> str:
    path = _BRAND_LOGO_PATH if _BRAND_LOGO_PATH.exists() else _LOGO_PATH
    if path.exists():
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""


# ── Palette ─────────────────────────────────────────────────────────────────
BLUE_DARK   = "#0F172A"
BLUE_NAV    = "#1E3A8A"
BLUE_MID    = "#1E40AF"
BLUE        = "#2563EB"
BLUE_LIGHT  = "#BFDBFE"
BLUE_XLIGHT = "#EFF6FF"
RED         = "#DC2626"
WHITE       = "#FFFFFF"
GREY_MID    = "#64748B"

# ── CSS ──────────────────────────────────────────────────────────────────────
_CSS = """
<style>
/* ═══ SIDEBAR ════════════════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: linear-gradient(170deg,#0F172A 0%,#1E3A8A 100%) !important;
    border-right: 2px solid #2563EB !important;
}
/* subtle blueprint grid overlay */
[data-testid="stSidebar"]::before {
    content: "";
    position: absolute;
    inset: 0;
    background-image:
        linear-gradient(rgba(147,197,253,0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(147,197,253,0.04) 1px, transparent 1px);
    background-size: 28px 28px;
    pointer-events: none;
}
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
[data-testid="stSidebarNav"] a {
    color: #93C5FD !important;
    font-weight: 500 !important;
    border-radius: 6px !important;
    padding: 6px 10px !important;
    transition: all 0.15s !important;
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(255,255,255,0.08) !important;
    color: #FFFFFF !important;
}
[data-testid="stSidebarNavLink"][aria-current="page"],
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: rgba(37,99,235,0.30) !important;
    border-left: 3px solid #2563EB !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] svg { fill: #93C5FD !important; }

/* ═══ TOP HEADER BAR ══════════════════════════════════════════════════ */
[data-testid="stHeader"] {
    background: #0F172A !important;
    border-bottom: 2px solid #2563EB !important;
}
[data-testid="stHeader"] button {
    background: transparent !important;
    border: none !important;
    outline: none !important;
    opacity: 1 !important;
    visibility: visible !important;
}
[data-testid="stHeader"] button svg,
[data-testid="stHeader"] button span svg,
[data-testid="stHeader"] [data-testid="baseButton-headerNoPadding"] svg,
[data-testid="stHeader"] [data-testid="baseButton-header"] svg {
    fill: #93C5FD !important;
    color: #93C5FD !important;
    opacity: 1 !important;
}
/* Collapsed sidebar expand button */
[data-testid="collapsedControl"] {
    background: #0F172A !important;
    border-right: 2px solid #2563EB !important;
}
[data-testid="collapsedControl"] svg {
    fill: #93C5FD !important;
}

/* ═══ MAIN CONTAINER ═════════════════════════════════════════════════ */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 4.5rem !important;
    max-width: 1440px !important;
}

/* ═══ HEADINGS ═══════════════════════════════════════════════════════ */
h1 {
    color: #0F172A !important;
    font-weight: 800 !important;
    letter-spacing: -0.025em !important;
    border-bottom: 3px solid #2563EB !important;
    padding-bottom: 0.45rem !important;
    margin-bottom: 1.2rem !important;
}
h2 {
    color: #1E3A8A !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em !important;
}
h3 {
    color: #1E40AF !important;
    font-weight: 600 !important;
    border-left: 4px solid #2563EB !important;
    padding-left: 0.65rem !important;
    margin-top: 1.3rem !important;
}
h4 { color: #1E40AF !important; font-weight: 600 !important; }

/* ═══ METRIC CARDS ═══════════════════════════════════════════════════ */
[data-testid="metric-container"] {
    background: linear-gradient(135deg,#EFF6FF 0%,#DBEAFE 100%) !important;
    border: 1px solid #BFDBFE !important;
    border-top: 3px solid #2563EB !important;
    border-radius: 8px !important;
    padding: 1rem 1.2rem !important;
    box-shadow: 0 2px 8px rgba(37,99,235,0.10) !important;
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

/* ═══ BUTTONS ════════════════════════════════════════════════════════ */
.stButton > button {
    background: linear-gradient(135deg,#1E40AF 0%,#2563EB 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em !important;
    padding: 0.55rem 1.7rem !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 8px rgba(37,99,235,0.30) !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg,#1E3A8A 0%,#1E40AF 100%) !important;
    box-shadow: 0 5px 16px rgba(37,99,235,0.40) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:active  { transform: translateY(0) !important; }
.stButton > button:disabled {
    background: #94A3B8 !important;
    box-shadow: none !important;
    transform: none !important;
}

/* ═══ ALERTS ══════════════════════════════════════════════════════════ */
[data-testid="stAlert"][data-type="success"], .stSuccess {
    background: #EFF6FF !important;
    border-left: 4px solid #2563EB !important;
    border-radius: 6px !important;
    color: #1E40AF !important;
}
[data-testid="stAlert"][data-type="error"], .stError {
    background: #FEF2F2 !important;
    border-left: 4px solid #DC2626 !important;
    border-radius: 6px !important;
    color: #991B1B !important;
}
[data-testid="stAlert"][data-type="warning"], .stWarning {
    background: #FFFBEB !important;
    border-left: 4px solid #D97706 !important;
    border-radius: 6px !important;
}
[data-testid="stAlert"][data-type="info"], .stInfo {
    background: #EFF6FF !important;
    border-left: 4px solid #3B82F6 !important;
    border-radius: 6px !important;
}

/* ═══ EXPANDERS ═══════════════════════════════════════════════════════ */
[data-testid="stExpander"] {
    border: 1px solid #BFDBFE !important;
    border-radius: 8px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
}
[data-testid="stExpander"] details summary {
    background: linear-gradient(90deg,#EFF6FF 0%,#F8FAFC 100%) !important;
    border-bottom: 1px solid #BFDBFE !important;
    padding: 0.65rem 1rem !important;
    font-weight: 600 !important;
    color: #1E40AF !important;
}
[data-testid="stExpander"] details summary:hover { background: #DBEAFE !important; }

/* ═══ CODE BLOCKS ════════════════════════════════════════════════════ */
[data-testid="stCode"] pre, .stCode pre {
    background: #0F172A !important;
    color: #E2E8F0 !important;
    border-radius: 8px !important;
    border: 1px solid #1E3A8A !important;
    font-size: 0.82rem !important;
    line-height: 1.6 !important;
    font-family: 'JetBrains Mono','Fira Code','Cascadia Code',monospace !important;
}

/* ═══ DIVIDERS ═══════════════════════════════════════════════════════ */
hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg,#2563EB 0%,#BFDBFE 60%,transparent 100%) !important;
    margin: 1.8rem 0 !important;
}

/* ═══ INPUTS / SELECTS ═══════════════════════════════════════════════ */
input[type="number"], input[type="text"] {
    border-radius: 6px !important;
    border-color: #BFDBFE !important;
    font-variant-numeric: tabular-nums !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
input:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 2px rgba(37,99,235,0.18) !important;
}
[data-testid="stSelectbox"] > div > div { border-radius: 6px !important; }

/* ═══ DATAFRAMES ════════════════════════════════════════════════════ */
[data-testid="stDataFrame"] thead th {
    background: #1E3A8A !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
}
[data-testid="stDataFrame"] tbody tr:nth-child(even) td { background: #EFF6FF !important; }

/* ═══ CAPTIONS ═══════════════════════════════════════════════════════ */
[data-testid="stCaptionContainer"] p, .stCaption {
    color: #64748B !important;
    font-size: 0.77rem !important;
    font-variant-numeric: tabular-nums !important;
}

/* ═══ SIDEBAR NAV — hidden; replaced by custom st.page_link nav ════ */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"] { display: none !important; }

/* ═══ SCROLLBAR ══════════════════════════════════════════════════════ */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #F1F5F9; border-radius: 3px; }
::-webkit-scrollbar-thumb { background: #BFDBFE; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #2563EB; }

/* ═══ FOOTER BANNER ══════════════════════════════════════════════════ */
.ins-footer {
    position: fixed;
    bottom: 0; left: 0;
    width: 100%;
    background: #0F172A;
    border-top: 2px solid #2563EB;
    padding: 6px 20px;
    font-size: 0.70rem;
    color: #94A3B8;
    z-index: 9999;
    letter-spacing: 0.02em;
    display: flex;
    align-items: center;
    gap: 12px;
}
.ins-footer b { color: #93C5FD; }
.ins-footer .sep { color: #1E3A8A; }
.block-container { padding-bottom: 4rem !important; }

/* ═══ PAGE BANNER ════════════════════════════════════════════════════ */
.page-banner {
    background: linear-gradient(90deg,#0F172A 0%,#1E3A8A 100%);
    border-radius: 8px;
    padding: 1rem 1.5rem;
    margin-bottom: 1.4rem;
    border-left: 5px solid #2563EB;
    display: flex;
    align-items: center;
    gap: 14px;
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

/* ═══ DISCLAIMER PAGE ════════════════════════════════════════════════ */
.dis-wrap {
    max-width: 840px;
    margin: 0 auto;
    padding: 0 1rem;
}
.dis-logo-block {
    text-align: center;
    padding: 2rem 1rem 1.2rem;
}
.dis-logo-block img {
    max-width: 320px;
    width: 75%;
    margin: 0 auto;
    display: block;
}
.dis-beta {
    display: inline-block;
    background: #2563EB;
    color: #FFFFFF;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 10px;
    border-radius: 10px;
    letter-spacing: 0.12em;
    margin-top: 0.6rem;
}
.dis-box {
    background: #F8FAFC;
    border: 1px solid #BFDBFE;
    border-top: 3px solid #2563EB;
    border-radius: 10px;
    padding: 1.6rem 2rem;
    max-height: 50vh;
    overflow-y: auto;
    font-size: 0.87rem;
    line-height: 1.75;
    color: #0F172A;
    margin: 0.8rem 0;
}
.dis-box h1 {
    font-size: 0.95rem !important;
    font-weight: 800 !important;
    color: #0F172A !important;
    border-bottom: 1px solid #BFDBFE !important;
    padding-bottom: 0.35rem !important;
    margin-bottom: 0.8rem !important;
    letter-spacing: 0.05em !important;
}
.dis-box strong { color: #1E3A8A; }
.dis-box hr { background: #BFDBFE !important; margin: 0.9rem 0 !important; }
</style>
"""


def apply_theme() -> None:
    """Inject global CSS. Call once per page before any UI."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_sidebar_logo() -> None:
    """Display logo and custom page navigation at the top of the sidebar."""
    if _LOGO_PATH.exists():
        st.sidebar.image(str(_LOGO_PATH), use_container_width=True)
        st.sidebar.markdown(
            "<div style='border-bottom:1px solid rgba(147,197,253,0.2);margin:4px 0 10px'></div>",
            unsafe_allow_html=True,
        )
    # Custom nav — replaces the auto-generated nav (which is hidden via CSS)
    _NAV = [
        ("app.py",                           "Beam Flexure"),
        ("pages/1_Tension_Members.py",       "Tension Members"),
        ("pages/2_Compression.py",           "Compression"),
        ("pages/4_Beam_Column_Members.py",   "Beam-Column Members"),
        ("pages/5_Bolted_Connections.py",    "Bolted Connections"),
        ("pages/6_Welded_Connections.py",    "Welded Connections"),
    ]
    for path, label in _NAV:
        st.sidebar.page_link(path, label=label)


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
    """Full-width branded header card with company logo and page title."""
    b64  = _brand_b64()
    mime = "jpeg" if _BRAND_LOGO_PATH.exists() else "png"
    img_tag = (
        f'<img src="data:image/{mime};base64,{b64}" '
        f'style="height:54px;width:auto;display:block;" alt="Infraspective Solutions"/>'
        if b64 else
        '<span style="font-size:1rem;font-weight:900;color:#0F172A;">INFRASPECTIVE</span>'
    )
    sub_html = (
        f'<div style="font-size:0.78rem;color:#475569;margin-top:4px;">{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(
        f"""<div style="display:flex;align-items:center;background:#FFFFFF;
              border-radius:10px;box-shadow:0 2px 16px rgba(15,23,42,0.09);
              border:1px solid #E2E8F0;overflow:hidden;margin-bottom:1.5rem;">
          <div style="background:#F1F5F9;padding:14px 22px;
                      border-right:4px solid #2563EB;
                      display:flex;align-items:center;flex-shrink:0;">
            {img_tag}
          </div>
          <div style="padding:12px 22px;flex:1;">
            <div style="font-size:0.60rem;font-weight:700;letter-spacing:0.13em;
                        color:#2563EB;text-transform:uppercase;margin-bottom:3px;">
              CSA S16 &nbsp;·&nbsp; Infraspective Solutions
            </div>
            <div style="font-size:1.25rem;font-weight:800;color:#0F172A;
                        line-height:1.1;letter-spacing:-0.02em;">
              {title}
            </div>
            {sub_html}
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_page_banner(title: str, subtitle: str = "") -> None:
    """Blue branded banner below the page title."""
    sub = f'<div class="pb-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="page-banner"><div><div class="pb-title">{title}</div>{sub}</div></div>',
        unsafe_allow_html=True,
    )


def disclaimer_page() -> None:
    """
    Render the full disclaimer gate UI (branding + scrollable agreement + accept button).
    Hides the sidebar page-navigation so users cannot bypass the gate.
    Auto-scrolls the browser to the accept button on load.
    """
    import re
    import streamlit.components.v1 as _comp

    apply_theme()

    b64 = _logo_b64()
    logo_img = (
        f'<img src="data:image/png;base64,{b64}" alt="Infraspective Solutions"/>'
        if b64 else
        '<div style="font-size:1.8rem;font-weight:900;color:#0F172A;letter-spacing:0.06em">'
        'INFRASPECTIVE<br><span style="color:#2563EB">SOLUTIONS</span></div>'
    )

    st.markdown(
        f'<div class="dis-logo-block">'
        f'{logo_img}'
        f'<div class="dis-beta">BETA</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        "<h3 style='text-align:center;font-size:1rem;color:#1E3A8A;"
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
    st.markdown(f'<div class="dis-box">{html}</div>', unsafe_allow_html=True)

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
            st.rerun()
    if not accept:
        st.caption("You must read and accept the agreement to continue.")

    # ── Auto-scroll to the accept area on every load ─────────────────────────
    _comp.html(
        """
        <script>
        (function() {
            function scrollToAccept() {
                try {
                    var doc = window.parent.document;
                    // Find the Enter Application button or the checkbox
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
                        // fallback: scroll to bottom of main content
                        var main = doc.querySelector('[data-testid="stAppViewContainer"]')
                                || doc.querySelector('.main')
                                || doc.body;
                        main.scrollTop = main.scrollHeight;
                    }
                } catch(e) {}
            }
            // Try immediately then retry to account for render delay
            setTimeout(scrollToAccept, 300);
            setTimeout(scrollToAccept, 800);
        })();
        </script>
        """,
        height=0,
    )


def gate_disclaimer() -> None:
    """
    Page-level disclaimer gate.  Call at the top of every page (after apply_theme).
    If the user has not yet accepted the disclaimer, shows the full disclaimer UI
    and halts the page with st.stop().
    """
    if not st.session_state.get("accepted_disclaimer", False):
        disclaimer_page()
        st.stop()


def _DISCLAIMER_TEXT() -> str:
    """Return DISCLAIMER_MD from app.py without circular import."""
    try:
        import importlib.util, sys
        # Read the DISCLAIMER_MD string directly from the file to avoid circular import
        root = Path(__file__).parent / "app.py"
        src = root.read_text(encoding="utf-8")
        import re
        m = re.search(r'DISCLAIMER_MD\s*=\s*"""(.*?)"""', src, re.DOTALL)
        return m.group(1) if m else ""
    except Exception:
        return ""
