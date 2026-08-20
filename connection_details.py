"""
connection_details.py - Standard beam connection details and their
bolt, plate and weld schedules.

A library of common beam-to-column connection arrangements and the
kind of first-pass schedule an office standard would carry: minimum
plate thickness, bolt call-up and fillet leg by nominal beam depth.

These are STARTING POINTS for study, not design values. Every number
here is fed into the CSA S16 checks in shear_connection.py and has to
pass on its own merit. Nothing in this file is a capacity.

ASCII only. Straight quotes only.
"""

# ======================================================================
# METRIC BOLTS USED BY THE STANDARD DETAILS
# ======================================================================
# M19, M22 and M25 are the soft metric equivalents of 3/4, 7/8 and
# 1 inch diameter bolts and appear on many office standards.

METRIC_BOLT_MAP = {
    "M19": "A325 (3/4 in)",
    "M22": "A325 (7/8 in)",
    "M25": "A325 (1 in)",
    "M16": "A325 (5/8 in)",
}


# ======================================================================
# BOLTS AND CONNECTION PLATES, BY NOMINAL BEAM DEPTH
# ======================================================================
# key: nominal depth label
# value: dict per detail family
#   t_plate  minimum plate or angle thickness, mm
#   n_bolts  number of bolts, per side where the detail says so
#   bolt     bolt call-up
#   w_weld   fillet leg W or W2, mm

_SCHEDULE_STD = {
    # Shared by the shear tab and end plate arrangements.
    "W200": {"t_plate": 8.0,  "n_bolts": 2, "bolt": "M19", "w_weld": 6.0},
    "W250": {"t_plate": 8.0,  "n_bolts": 2, "bolt": "M19", "w_weld": 6.0},
    "W310": {"t_plate": 8.0,  "n_bolts": 3, "bolt": "M22", "w_weld": 6.0},
    "W360": {"t_plate": 10.0, "n_bolts": 3, "bolt": "M22", "w_weld": 8.0},
    "W410": {"t_plate": 10.0, "n_bolts": 4, "bolt": "M25", "w_weld": 8.0},
    "W610": {"t_plate": 13.0, "n_bolts": 6, "bolt": "M25", "w_weld": 10.0},
}

# The moment arrangements schedule the connection plate and weld only,
# with no bolt group in the shear plane.
_SCHEDULE_MOMENT = {
    "W200": {"t_plate": 8.0,  "n_bolts": 0, "bolt": "M19", "w_weld": 6.0},
    "W250": {"t_plate": 8.0,  "n_bolts": 0, "bolt": "M19", "w_weld": 6.0},
    "W310": {"t_plate": 8.0,  "n_bolts": 0, "bolt": "M19", "w_weld": 6.0},
    "W360": {"t_plate": 10.0, "n_bolts": 0, "bolt": "M22", "w_weld": 8.0},
    "W410": {"t_plate": 10.0, "n_bolts": 0, "bolt": "M22", "w_weld": 8.0},
    "W610": {"t_plate": 13.0, "n_bolts": 0, "bolt": "M25", "w_weld": 10.0},
}

# Slotted hole arrangement: slot size and the c dimension.
SLOT_SCHEDULE = {
    "W200": {"slot": "21 x 50", "c": 15.0},
    "W250": {"slot": "21 x 50", "c": 15.0},
    "W310": {"slot": "24 x 55", "c": 15.0},
    "W360": {"slot": "24 x 55", "c": 15.0},
    "W410": {"slot": "27 x 60", "c": 20.0},
    "W610": {"slot": "27 x 60", "c": 20.0},
}

DEPTH_ORDER = ["W200", "W250", "W310", "W360", "W410", "W610"]


# ======================================================================
# STIFFENER PLATE AND WELD SCHEDULE, BY FLANGE THICKNESS
# ======================================================================
# Applies to the stiffened arrangements. Keyed on the beam or column flange
# thickness in mm. Each entry is (upper bound, T1 mm, W1 mm); the last
# entry has no upper bound.

STIFF_SCHEDULE = [
    (10.0, 8.0, 6.0),
    (12.0, 10.0, 6.0),
    (16.0, 13.0, 8.0),
    (None, 16.0, 10.0),
]


def stiffener_and_weld(flange_t):
    """Return (T1, W1, band) for a given flange thickness in mm."""
    prev = 0.0
    for upper, t1, w1 in STIFF_SCHEDULE:
        if upper is None:
            return t1, w1, "flange thickness > %.0f mm" % prev
        if flange_t <= upper:
            if prev == 0.0:
                band = "flange thickness <= %.0f mm" % upper
            else:
                band = ("flange thickness > %.0f mm and <= %.0f mm"
                        % (prev, upper))
            return t1, w1, band
        prev = upper
    return 16.0, 10.0, "flange thickness > 16 mm"


# ======================================================================
# THE DETAILS
# ======================================================================
# kind drives which limit states the page runs:
#   "end_plate"  bolts in tension and shear through an end plate
#   "shear_tab"  bolts in shear through the beam web into a gusset or
#                shear plate welded to the support
#   "moment"     welded flange moment connection, shear carried by a
#                gusset plate and erection bolt

DETAILS = {
    "1": {
        "title": "Beam to column web with gusset plate",
        "kind": "shear_tab",
        "schedule": _SCHEDULE_STD,
        "bolts_per_side": True,
        "stiffeners": True,
        "slotted": False,
        "note": "Shear plate welded to the column web all round, "
                "with stiffener plates opposite the beam flanges. The "
                "beam web bolts to the plate in single shear.",
        "learn": "The classic shear tab. The plate is welded to the "
                 "support and the beam web bolts to it, so the bolt "
                 "group sits away from the support face and picks up "
                 "an eccentricity equal to that distance.",
    },
    "2": {
        "title": "Beam to column flange with end plate",
        "kind": "end_plate",
        "schedule": _SCHEDULE_STD,
        "bolts_per_side": True,
        "stiffeners": False,
        "slotted": False,
        "note": "End plate shop welded to the beam web, bolted to "
                "the column flange with the scheduled number of bolts "
                "each side of the web.",
        "learn": "Bolts here carry shear and any axial tension, and "
                 "the plate bends between the bolt lines, so prying "
                 "matters. This is the case the calculator was first "
                 "built around.",
    },
    "3": {
        "title": "Beam to column web with end plate",
        "kind": "end_plate",
        "schedule": _SCHEDULE_STD,
        "bolts_per_side": True,
        "stiffeners": False,
        "slotted": False,
        "note": "As detail 2 but landing on the column web rather "
                "than the flange, so the supporting element is much "
                "more flexible.",
        "learn": "Same bolt and plate checks as detail 2, but the "
                 "prying model assumes an infinitely stiff support. "
                 "A column web is not stiff, so treat the prying "
                 "result as optimistic unless stiffeners are added.",
    },
    "4": {
        "title": "Beam to column web, slotted sliding connection",
        "kind": "shear_tab",
        "schedule": _SCHEDULE_STD,
        "bolts_per_side": False,
        "stiffeners": True,
        "slotted": True,
        "note": "Double shear plate with slotted holes, stiffener "
                "plates opposite the flanges, beam coped. Bolts take "
                "washers and double nuts: first nut finger tight, "
                "second as a lock nut.",
        "learn": "Slots let the beam move, which means the connection "
                 "must not be relied on for axial restraint. Slotted "
                 "and oversize holes also reduce bearing capacity, "
                 "and the beam is coped, so coped-section checks "
                 "apply on top of the usual ones.",
    },
    "5": {
        "title": "Beam to existing column web, moment connection",
        "kind": "moment",
        "schedule": _SCHEDULE_MOMENT,
        "bolts_per_side": False,
        "stiffeners": True,
        "slotted": False,
        "note": "Flanges welded, shear plate carries the reaction, "
                "erection bolt only. No erection bolt where the "
                "connection is made in the shop.",
        "learn": "The erection bolt is not a design element. Shear "
                 "goes through the plate and its welds, moment "
                 "through the flange welds.",
    },
    "6": {
        "title": "Beam to HSS column",
        "kind": "shear_tab",
        "schedule": _SCHEDULE_STD,
        "bolts_per_side": False,
        "stiffeners": False,
        "slotted": False,
        "note": "Plate welded to the face of the HSS column, beam "
                "web bolted to it.",
        "learn": "An HSS face is a flexible plate, not a rigid "
                 "support. The wall of the HSS has to be checked for "
                 "local yielding under the plate, which is outside "
                 "this calculator.",
    },
    "7": {
        "title": "Beam to column web, moment connection",
        "kind": "moment",
        "schedule": _SCHEDULE_MOMENT,
        "bolts_per_side": False,
        "stiffeners": True,
        "slotted": False,
        "note": "Flanges welded three sides, stiffener plates "
                "opposite the flanges where there is no beam on the "
                "far side, shear plate carries the reaction.",
        "learn": "Same idea as the retrofit case but for new work. The "
                 "stiffener schedule keys off the flange thickness, "
                 "not the beam depth.",
    },
}

DETAIL_ORDER = ["1", "2", "3", "4", "5", "6", "7"]


def detail_options():
    return ["Arrangement %s - %s" % (k, DETAILS[k]["title"])
            for k in DETAIL_ORDER]


def detail_from_label(label):
    key = label.split()[1]
    return key, DETAILS[key]


def nominal_depth(designation):
    """Map a W designation such as W250x39 to its nominal depth band.
    Sections deeper than the scheduled range fall to the deepest
    entry, which is flagged to the user rather than silently used."""
    try:
        core = str(designation).upper().split("X")[0].replace("W", "")
        d = float(core)
    except Exception:
        return None, False
    bands = [(200.0, "W200"), (250.0, "W250"), (310.0, "W310"),
             (360.0, "W360"), (410.0, "W410"), (610.0, "W610")]
    for limit, name in bands:
        if d <= limit:
            return name, True
    return "W610", False


def schedule_for(detail_key, designation):
    """Return (row, band, in_range) for an arrangement and a W
    designation."""
    det = DETAILS[detail_key]
    band, in_range = nominal_depth(designation)
    if band is None:
        return None, None, False
    return dict(det["schedule"][band]), band, in_range
