---
name: Beta gate & branding decisions
description: How the agreement gate, locked calculators, logo blending, timeout, and activity logging are wired — and the constraints behind them.
---

- **Logo blending is CSS-only; never edit the artwork.** Disclaimer (light bg): `mix-blend-mode: multiply` + radial-gradient mask feather dissolves the JPEG's light plate. Sidebar (dark blue bg): multiply/invert are ruled out by the user — keep original colours, rounded "button" card with border + blue glow. Wordmark file: `static/logo_wordmark.jpg` served as base64 data-URI (`_wordmark_src()` in `_theme.py`).
- **User rejected** an inverted/recoloured sidebar logo ("keep the original logo") and any white rectangle behind the logo anywhere.
- **Only Tension Members is unlocked in Beta.** `_NAV` in `_theme.py` carries an `unlocked` flag; locked entries render as non-clickable rows (lock + "Soon"). Locked pages call `beta_lock_page()` right after `gate_disclaimer()`. `app.py` (Beam Flexure) is itself locked and the disclaimer accept button switch_pages to Tension.
- **Direct URL to any page = fresh Streamlit session**, so the agreement gate reappears — expected, not a bug; e2e tests must click through, not deep-link.
- **10-min inactivity timeout** lives in `gate_disclaimer()` (`_enforce_inactivity_timeout`): clears all session state, user re-accepts. Safe from loops because it requires `accepted_disclaimer=True`.
- **Streamlit "widget default value" warning pattern:** never pass `value=` to a widget whose key a callback also writes; seed `st.session_state[key]` once instead (done for `tm_Fy`/`tm_Fu`).
- **Anonymous activity logging** = `activity.py`, JSONL under `logs/activity/` (gitignored). Single funnel `log_event()`; swap `_write()` for a DB later. Filesystem is ephemeral in deployments — data won't persist across redeploys until a DB backend is added.
- Browser console "Invalid color ... theme.sidebar" warnings persist even with a `[theme.sidebar]` block in `.streamlit/config.toml` — harmless Streamlit noise, not user-visible.
