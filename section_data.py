"""
section_data.py - W shape and single angle properties for the
connection calculators.

Pulls from sst12.load_all_tables(). The table keys in sst12 are not
assumed: every table returned is inspected and classified by the shape
of its designations, so this keeps working if the keys are renamed or
new tables are added.

Falls back to reading the CISC SST12.1 workbook directly if sst12 is
unavailable or has no data loaded.

ASCII only. Straight quotes only.
"""

import os
import re

import pandas as pd

try:
    import sst12
except Exception:
    sst12 = None


W_RE = re.compile(r"^W\s*\d{2,4}\s*[xX]\s*\d+", re.I)
L_RE = re.compile(r"^L\s*\d{2,4}\s*[xX]\s*\d{2,4}\s*[xX]\s*\d+", re.I)

WORKBOOK_NAMES = ["CISC_StructuralSectionTables_SST12_1.xlsx",
                  "SST12_1.xlsx"]

# Column aliases seen across the sst12 tables and the raw workbook.
_ALIAS = {
    "designation": ["designation", "Designation", "Ds_m", "ds_m",
                    "Dsg", "name"],
    "d":    ["d_mm", "D", "d", "Depth_mm"],
    "b":    ["b_mm", "B", "b", "bf_mm", "bf"],
    "t":    ["t_mm", "T", "t", "tf_mm", "tf"],
    "w":    ["w_mm", "W", "w", "tw_mm", "tw"],
    "Ag":   ["Area_mm2", "A_A6", "Ag", "A", "area_mm2"],
    "mass": ["Mass", "mass", "kg_m"],
}


def _pick(df, key):
    for name in _ALIAS[key]:
        if name in df.columns:
            return name
    return None


def _classify(df):
    """Return 'W', 'L' or None based on the designations in a table."""
    col = _pick(df, "designation")
    if col is None:
        return None, None
    s = df[col].astype(str).str.strip()
    if len(s) == 0:
        return None, None
    w_hits = s.str.match(W_RE).sum()
    l_hits = s.str.match(L_RE).sum()
    n = float(len(s))
    if w_hits / n > 0.6:
        return "W", col
    if l_hits / n > 0.6:
        return "L", col
    return None, col


def _from_sst12():
    out = {"W": None, "L": None}
    if sst12 is None or not hasattr(sst12, "load_all_tables"):
        return out
    try:
        tables = sst12.load_all_tables()
    except Exception:
        return out
    if not isinstance(tables, dict):
        return out
    for key, rows in tables.items():
        try:
            df = rows if isinstance(rows, pd.DataFrame) \
                else pd.DataFrame(rows)
        except Exception:
            continue
        if df.empty:
            continue
        kind, _ = _classify(df)
        if kind and out.get(kind) is None:
            out[kind] = df
    return out


def _workbook_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (here, os.path.join(here, "static"),
                 os.path.join(here, "attached_assets"), os.getcwd()):
        for name in WORKBOOK_NAMES:
            p = os.path.normpath(os.path.join(base, name))
            if os.path.isfile(p):
                return p
    return None


def _from_workbook():
    """Read the W and L sheets straight out of the SST12.1 workbook.
    Row 0 holds the field codes, rows 1 and 2 are the title and the
    units, so the data starts at row 3."""
    out = {"W": None, "L": None}
    path = _workbook_path()
    if path is None:
        return out
    for sheet, kind in (("W", "W"), ("L", "L")):
        try:
            raw = pd.read_excel(path, sheet_name=sheet, header=None)
        except Exception:
            continue
        cols = [str(c).strip() for c in raw.iloc[0].tolist()]
        df = raw.iloc[3:].copy()
        df.columns = cols
        col = _pick(df, "designation")
        if col is None:
            continue
        df = df[df[col].notna()]
        df[col] = df[col].astype(str).str.strip()
        rx = W_RE if kind == "W" else L_RE
        df = df[df[col].str.match(rx)]
        if not df.empty:
            out[kind] = df.reset_index(drop=True)
    return out


def _normalise(df, kind):
    """Reduce a table to the fields the connection pages need."""
    if df is None or df.empty:
        return pd.DataFrame()
    col = _pick(df, "designation")
    data = {"designation": df[col].astype(str).str.strip()}
    wanted = (["d", "b", "t", "w", "Ag", "mass"] if kind == "W"
              else ["d", "b", "t", "Ag", "mass"])
    for key in wanted:
        src = _pick(df, key)
        data[key] = (pd.to_numeric(df[src], errors="coerce")
                     if src is not None else pd.NA)
    out = pd.DataFrame(data)
    out = out[out["designation"].str.len() > 0]
    core = ["d", "b"] + (["w", "t"] if kind == "W" else ["t"])
    out = out.dropna(subset=[c for c in core if c in out.columns])
    return out.drop_duplicates("designation").reset_index(drop=True)


_CACHE = {}


def load(kind):
    """kind is 'W' or 'L'. Returns (DataFrame, source_label)."""
    if kind in _CACHE:
        return _CACHE[kind]
    tables = _from_sst12()
    source = "sst12"
    if tables.get(kind) is None:
        tables = _from_workbook()
        source = "SST12.1 workbook"
    df = _normalise(tables.get(kind), kind)
    if df.empty:
        source = "not found"
    _CACHE[kind] = (df, source)
    return _CACHE[kind]


def _nat_key(s):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", str(s))]


def designations(kind):
    df, _ = load(kind)
    if df.empty:
        return []
    return sorted(df["designation"].tolist(), key=_nat_key)


def props(kind, designation):
    df, _ = load(kind)
    if df.empty:
        return None
    hit = df[df["designation"] == designation]
    if hit.empty:
        return None
    row = hit.iloc[0]
    out = {"designation": designation}
    for c in df.columns:
        if c == "designation":
            continue
        try:
            out[c] = float(row[c])
        except (TypeError, ValueError):
            out[c] = None
    return out


def status():
    """Short description of where each table came from, for the UI."""
    lines = []
    for kind, name in (("W", "W shapes"), ("L", "Single angles")):
        df, src = load(kind)
        lines.append("%s: %d sections from %s" % (name, len(df), src))
    return lines
