"""
section_geometry.py

Parametric 2D cross-section outlines for CSA S16 steel sections.

Pure Python. No Streamlit, no numpy, no external dependencies.
Nothing is pre-modelled: every point is computed from d, b, t, w and a
fillet radius, so any section in the workbook renders correctly.

Coordinate system:
    x = horizontal (flange width direction, weak axis)
    y = vertical   (section depth direction, strong axis)
    Origin is the centroid.
    Units are millimetres.

Returned structure:
    {
      "outer":       [[x, y], ...]      closed loop, counter-clockwise
      "holes":       [[[x, y], ...]]    inner loops (hollow sections)
      "extra_loops": [[[x, y], ...]]    separate solids (double angle)
      "kind":        "I" | "TEE" | "CHANNEL" | "RHS" | "CHS" | "ANGLE"
                     | "DOUBLE_ANGLE"
      "zones":       dict describing where the flange and web sit, so a
                     viewer can colour plate elements separately
      "r_mm", "area_polygon_mm2", "area_table_mm2", "area_error_pct",
      "designation"
    }
"""

import math


# -----------------------------------------------------------
# low level helpers
# -----------------------------------------------------------

def _arc(cx, cy, r, a0_deg, a1_deg, segments=8):
    """Points along a circular arc, inclusive of both ends."""
    pts = []
    a0 = math.radians(a0_deg)
    a1 = math.radians(a1_deg)
    for i in range(segments + 1):
        a = a0 + (a1 - a0) * float(i) / float(segments)
        pts.append([cx + r * math.cos(a), cy + r * math.sin(a)])
    return pts


def polygon_area(pts):
    """Shoelace area. Positive for counter-clockwise."""
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return 0.5 * s


def polygon_centroid(pts):
    """Area centroid of a simple polygon."""
    a = polygon_area(pts)
    if abs(a) < 1e-9:
        n = float(len(pts))
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    cx = 0.0
    cy = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx / (6.0 * a), cy / (6.0 * a))


def _dedupe(pts, tol=1e-7):
    """Drop consecutive duplicate points."""
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > tol or abs(p[1] - out[-1][1]) > tol:
            out.append(p)
    if len(out) > 1:
        if (abs(out[0][0] - out[-1][0]) < tol
                and abs(out[0][1] - out[-1][1]) < tol):
            out.pop()
    return out


def _recentre(pts):
    cx, cy = polygon_centroid(pts)
    return [[p[0] - cx, p[1] - cy] for p in pts], cx, cy


# -----------------------------------------------------------
# fillet radius estimation
#
# The workbook does not publish the root radius, so it is backed out of
# the published area. Fillet material at one corner is the square minus
# the quarter circle, r^2 (1 - pi/4).
# -----------------------------------------------------------

def estimate_w_fillet(d, b, t, w, area_table):
    """I-shape: four root fillets."""
    fallback = max(0.0, min(0.5 * w + 6.0, 0.4 * (d - 2.0 * t)))
    if not area_table or area_table <= 0:
        return fallback
    a_rect = 2.0 * b * t + (d - 2.0 * t) * w
    extra = area_table - a_rect
    if extra <= 0:
        return fallback
    r = math.sqrt(extra / (4.0 - math.pi))
    if r <= 0 or r > 0.45 * (d - 2.0 * t) or r > 4.0 * w:
        return fallback
    return r


def estimate_tee_fillet(d, b, t, w, area_table):
    """Tee: two root fillets where the stem meets the flange."""
    fallback = max(0.0, min(0.5 * w + 5.0, 0.3 * (d - t)))
    if not area_table or area_table <= 0:
        return fallback
    a_rect = b * t + (d - t) * w
    extra = area_table - a_rect
    if extra <= 0:
        return fallback
    r = math.sqrt(extra / (2.0 * (1.0 - math.pi / 4.0)))
    if r <= 0 or r > 0.4 * (d - t) or r > 4.0 * w:
        return fallback
    return r


def estimate_channel_fillet(d, b, t, w, area_table):
    """Channel: two root fillets on the inside of the web."""
    fallback = max(0.0, min(0.5 * w + 5.0, 0.3 * (d - 2.0 * t)))
    if not area_table or area_table <= 0:
        return fallback
    a_rect = 2.0 * b * t + (d - 2.0 * t) * w
    extra = area_table - a_rect
    if extra <= 0:
        return fallback
    r = math.sqrt(extra / (2.0 * (1.0 - math.pi / 4.0)))
    if r <= 0 or r > 0.45 * (d - 2.0 * t) or r > 4.0 * w:
        return fallback
    return r


def estimate_angle_fillet(leg1, leg2, t, area_table):
    """Angle: one heel fillet, two toe radii."""
    fallback = 1.5 * t
    if not area_table or area_table <= 0:
        return fallback
    a_rect = (leg1 + leg2 - t) * t
    extra = area_table - a_rect
    if extra <= 0:
        return fallback
    r = math.sqrt(abs(extra) / (1.0 - math.pi / 4.0))
    if r <= 0 or r > 0.5 * min(leg1, leg2):
        return fallback
    return r


# -----------------------------------------------------------
# I shapes: W, S, M, HP
# -----------------------------------------------------------

def w_outline(d, b, t, w, r, segments=8):
    """I-shape with four root fillets, counter-clockwise, starting at the
    bottom right corner of the bottom flange."""
    hd = 0.5 * d
    hb = 0.5 * b
    hw = 0.5 * w
    r = max(0.0, min(r, 0.45 * (d - 2.0 * t)))

    y_bt = -hd + t          # top face of the bottom flange
    y_tb = hd - t           # bottom face of the top flange

    pts = []
    pts.append([hb, -hd])
    pts.append([hb, y_bt])
    pts.append([hw + r, y_bt])
    pts += _arc(hw + r, y_bt + r, r, 270.0, 180.0, segments)
    pts.append([hw, y_tb - r])
    pts += _arc(hw + r, y_tb - r, r, 180.0, 90.0, segments)
    pts.append([hb, y_tb])
    pts.append([hb, hd])
    pts.append([-hb, hd])
    pts.append([-hb, y_tb])
    pts.append([-hw - r, y_tb])
    pts += _arc(-hw - r, y_tb - r, r, 90.0, 0.0, segments)
    pts.append([-hw, y_bt + r])
    pts += _arc(-hw - r, y_bt + r, r, 0.0, -90.0, segments)
    pts.append([-hb, y_bt])
    pts.append([-hb, -hd])
    return _dedupe(pts)


# -----------------------------------------------------------
# WT tee
# -----------------------------------------------------------

def tee_outline(d, b, t, w, r, segments=8):
    """Flange across the top, stem hanging below. Recentred on the
    centroid."""
    hb = 0.5 * b
    hw = 0.5 * w
    y_top = 0.0
    y_fl = -t
    y_bot = -d
    r = max(0.0, min(r, 0.8 * (d - t)))

    pts = []
    pts.append([hb, y_top])
    pts.append([hb, y_fl])
    pts.append([hw + r, y_fl])
    pts += _arc(hw + r, y_fl - r, r, 90.0, 180.0, segments)
    pts.append([hw, y_bot])
    pts.append([-hw, y_bot])
    pts.append([-hw, y_fl - r])
    pts += _arc(-hw - r, y_fl - r, r, 0.0, 90.0, segments)
    pts.append([-hb, y_fl])
    pts.append([-hb, y_top])

    pts = _dedupe(pts)
    pts, _cx, _cy = _recentre(pts)
    return pts


# -----------------------------------------------------------
# C and MC channels
# -----------------------------------------------------------

def channel_outline(d, b, t, w, r, segments=8):
    """Web on the left, two flanges reaching right. Recentred."""
    hd = 0.5 * d
    r = max(0.0, min(r, 0.45 * (d - 2.0 * t)))
    y_bt = -hd + t
    y_tb = hd - t

    pts = []
    pts.append([0.0, -hd])
    pts.append([b, -hd])
    pts.append([b, y_bt])
    pts.append([w + r, y_bt])
    pts += _arc(w + r, y_bt + r, r, 270.0, 180.0, segments)
    pts.append([w, y_tb - r])
    pts += _arc(w + r, y_tb - r, r, 180.0, 90.0, segments)
    pts.append([b, y_tb])
    pts.append([b, hd])
    pts.append([0.0, hd])

    pts = _dedupe(pts)
    pts, _cx, _cy = _recentre(pts)
    return pts


# -----------------------------------------------------------
# rectangular and square HSS
# -----------------------------------------------------------

def _rounded_rect(half_w, half_h, r, segments=8):
    r = max(0.0, min(r, min(half_w, half_h) * 0.99))
    pts = []
    pts += _arc(half_w - r, -half_h + r, r, -90.0, 0.0, segments)
    pts += _arc(half_w - r, half_h - r, r, 0.0, 90.0, segments)
    pts += _arc(-half_w + r, half_h - r, r, 90.0, 180.0, segments)
    pts += _arc(-half_w + r, -half_h + r, r, 180.0, 270.0, segments)
    return _dedupe(pts)


def hss_rect_outline(d, b, t, segments=8):
    """Outer corner radius 2t, inner 1t, which is the cold-formed
    proportion Cl. 11.3.2 b) assumes when it removes 4t."""
    outer = _rounded_rect(0.5 * b, 0.5 * d, 2.0 * t, segments)
    inner = _rounded_rect(0.5 * b - t, 0.5 * d - t, 1.0 * t, segments)
    inner.reverse()
    return outer, inner


# -----------------------------------------------------------
# circular HSS
# -----------------------------------------------------------

def chs_outline(D, t, segments=48):
    ro = 0.5 * D
    ri = max(ro - t, 0.1)
    outer = _arc(0.0, 0.0, ro, 0.0, 360.0, segments)[:-1]
    inner = _arc(0.0, 0.0, ri, 0.0, 360.0, segments)[:-1]
    inner.reverse()
    return outer, inner


# -----------------------------------------------------------
# single and double angles
# -----------------------------------------------------------

def angle_outline(leg_v, leg_h, t, r, segments=8, recentre=True):
    """Heel at the lower left, vertical leg up in +y, horizontal leg out
    in +x, heel fillet of radius r and toe radii of r/2."""
    r = max(0.0, min(r, 0.9 * t))
    rt = 0.5 * r

    pts = []
    pts.append([0.0, 0.0])
    pts.append([leg_h, 0.0])
    if rt > 0:
        pts.append([leg_h, t - rt])
        pts += _arc(leg_h - rt, t - rt, rt, 0.0, 90.0, segments)
    else:
        pts.append([leg_h, t])
    pts.append([t + r, t])
    pts += _arc(t + r, t + r, r, 270.0, 180.0, segments)
    if rt > 0:
        pts.append([t, leg_v - rt])
        pts += _arc(t - rt, leg_v - rt, rt, 0.0, 90.0, segments)
    else:
        pts.append([t, leg_v])
    pts.append([0.0, leg_v])

    pts = _dedupe(pts)
    if recentre:
        pts, _cx, _cy = _recentre(pts)
    return pts


def double_angle_outline(leg_v, leg_h, t, r, gap=10.0, segments=8):
    """A back-to-back pair straddling a gusset gap. Returns two loops."""
    one = angle_outline(leg_v, leg_h, t, r, segments, recentre=False)
    cy = polygon_centroid(one)[1]
    half = 0.5 * gap
    right = [[p[0] + half, p[1] - cy] for p in one]
    left = [[-p[0], p[1]] for p in right][::-1]
    return [right, left]


# -----------------------------------------------------------
# designation parsing for angles
# -----------------------------------------------------------

def parse_angle_legs(designation):
    """(leg_long, leg_short, thickness) from an angle designation."""
    s = str(designation).upper().replace(" ", "")
    s = s.replace("2LE", "").replace("2LL", "").replace("2LS", "")
    s = s.replace("2L", "")
    if s.startswith("L"):
        s = s[1:]
    s = s.replace("\u00d7", "X")
    nums = []
    for part in s.split("X"):
        try:
            nums.append(float(part))
        except ValueError:
            pass
    if len(nums) >= 3:
        return max(nums[0], nums[1]), min(nums[0], nums[1]), nums[2]
    return None, None, None


# -----------------------------------------------------------
# plate-element zones
#
# Tells a viewer which part of the cross-section is flange and which is
# web, so Table 1 and Table 2 elements can be coloured separately. The
# viewer classifies a vertex by testing it against these bands.
# -----------------------------------------------------------

def _zones(kind, d, b, t, w):
    z = {"kind": kind}
    if kind == "I":
        z["flange_y"] = 0.5 * d - t     # abs(y) above this is flange
        z["web_x"] = 0.5 * w
    elif kind == "TEE":
        # recentred, so the flange top sits at d - y_bar
        z["flange_y"] = None            # viewer uses flange_top instead
        z["web_x"] = 0.5 * w
        z["tee_depth"] = d
        z["tee_flange_t"] = t
    elif kind == "CHANNEL":
        z["flange_y"] = 0.5 * d - t
        z["web_x"] = w
    elif kind == "RHS":
        z["flange_y"] = 0.5 * d - t
        z["web_x"] = 0.5 * b - t
    elif kind == "CHS":
        z["radius"] = 0.5 * d
    elif kind in ("ANGLE", "DOUBLE_ANGLE"):
        z["leg_t"] = t
    return z


# -----------------------------------------------------------
# main entry point
# -----------------------------------------------------------

def section_outline(sec, segments=8, gap_mm=10.0):
    """
    Build the 2D outline for a SectionProps object from the compression
    page. Reads: family, designation, d_mm, b_mm, t_mm, w_mm, A_mm2,
    hss_kind.

    Raises ValueError if a needed dimension is missing.
    """
    fam = getattr(sec, "family", "")
    d = getattr(sec, "d_mm", None)
    b = getattr(sec, "b_mm", None)
    t = getattr(sec, "t_mm", None)
    w = getattr(sec, "w_mm", None)
    area = getattr(sec, "A_mm2", None)
    hk = getattr(sec, "hss_kind", None)
    des = getattr(sec, "designation", "")

    holes = []
    extra_loops = []

    if fam in ("W", "WWF"):
        if None in (d, b, t, w):
            raise ValueError("I-section needs d, b, t and w.")
        r = estimate_w_fillet(d, b, t, w, area)
        outer = w_outline(d, b, t, w, r, segments)
        kind = "I"

    elif fam == "WT":
        if None in (d, b, t, w):
            raise ValueError("Tee needs d, b, t and w.")
        r = estimate_tee_fillet(d, b, t, w, area)
        outer = tee_outline(d, b, t, w, r, segments)
        kind = "TEE"

    elif fam == "CHANNEL":
        if None in (d, b, t, w):
            raise ValueError("Channel needs d, b, t and w.")
        r = estimate_channel_fillet(d, b, t, w, area)
        outer = channel_outline(d, b, t, w, r, segments)
        kind = "CHANNEL"

    elif fam == "HSS" and hk == "CHS":
        if None in (d, t):
            raise ValueError("Circular HSS needs D and t.")
        outer, inner = chs_outline(d, t, max(24, segments * 6))
        holes.append(inner)
        r = 0.0
        kind = "CHS"

    elif fam == "HSS":
        if None in (d, b, t):
            raise ValueError("Rectangular HSS needs d, b and t.")
        outer, inner = hss_rect_outline(d, b, t, segments)
        holes.append(inner)
        r = 2.0 * t
        kind = "RHS"

    elif fam == "ANGLE":
        lg, ls, lt = parse_angle_legs(des)
        if lg is None:
            lg, ls, lt = d, b, t
        if None in (lg, ls, lt):
            raise ValueError("Angle needs both leg dimensions and t.")
        r = estimate_angle_fillet(lg, ls, lt, area)
        outer = angle_outline(lg, ls, lt, r, segments)
        kind = "ANGLE"
        d, b, t = lg, ls, lt

    elif fam == "DOUBLE_ANGLE":
        lg, ls, lt = parse_angle_legs(des)
        if lg is None:
            lg, ls, lt = d, b, t
        if None in (lg, ls, lt):
            raise ValueError("Double angle needs both leg dimensions and t.")
        half_area = (area / 2.0) if area else None
        r = estimate_angle_fillet(lg, ls, lt, half_area)
        loops = double_angle_outline(lg, ls, lt, r, gap=gap_mm,
                                     segments=segments)
        outer = loops[0]
        extra_loops = loops[1:]
        kind = "DOUBLE_ANGLE"
        d, b, t = lg, ls, lt

    else:
        raise ValueError("No outline builder for family " + str(fam))

    a_poly = abs(polygon_area(outer))
    for h in holes:
        a_poly -= abs(polygon_area(h))
    for e in extra_loops:
        a_poly += abs(polygon_area(e))

    err = None
    if area:
        err = 100.0 * (a_poly - area) / area

    return {
        "outer": outer,
        "holes": holes,
        "extra_loops": extra_loops,
        "kind": kind,
        "zones": _zones(kind, d, b, t, w),
        "r_mm": r,
        "area_polygon_mm2": a_poly,
        "area_table_mm2": area,
        "area_error_pct": err,
        "designation": des,
    }


def outline_bounds(outline):
    """(min_x, min_y, max_x, max_y) over every loop."""
    xs = []
    ys = []
    for loop in [outline["outer"]] + list(outline.get("extra_loops", [])):
        xs += [p[0] for p in loop]
        ys += [p[1] for p in loop]
    return (min(xs), min(ys), max(xs), max(ys))
