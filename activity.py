"""
Anonymous usage/activity logging — Infraspective Beta.

Collects NO personal information. Each browser session gets a random UUID
(stored only in Streamlit session state, discarded when the session ends).
Events are appended as JSON lines to logs/activity/YYYY-MM-DD.jsonl.

Architecture note: log_event() is the single funnel for all events, so a
future login system or database backend only needs to swap out _write();
call sites never change.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

_LOG_DIR = Path(__file__).parent / "logs" / "activity"


def _session_id() -> str:
    if "_activity_sid" not in st.session_state:
        st.session_state["_activity_sid"] = uuid.uuid4().hex
        st.session_state["_activity_started"] = time.time()
        _write({
            "event": "session_start",
            "sid": st.session_state["_activity_sid"],
            "ts": _now(),
        })
    return st.session_state["_activity_sid"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(rec: dict) -> None:
    """Append one JSON line. Never raises — logging must not break the app."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        fname = _LOG_DIR / (datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl")
        with open(fname, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_event(event: str, **fields) -> None:
    """Record an anonymous event, e.g.:
    log_event("page_view", page="Tension Members")
    log_event("calc_run", calculator="tension", section_type="single_angle", ok=True)
    log_event("calc_error", calculator="tension", error="ValueError: ...")
    """
    try:
        sid = _session_id()
        started = st.session_state.get("_activity_started")
        rec = {
            "event": event,
            "sid": sid,
            "ts": _now(),
            "session_age_s": round(time.time() - started) if started else None,
        }
        rec.update(fields)
        _write(rec)
    except Exception:
        pass


def log_page_view(page: str) -> None:
    """Log a page view once per session per page (avoids rerun spam)."""
    try:
        key = f"_activity_pv_{page}"
        if not st.session_state.get(key):
            st.session_state[key] = True
            log_event("page_view", page=page)
    except Exception:
        pass
