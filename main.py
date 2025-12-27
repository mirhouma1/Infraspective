def main():
    print("Hello from repl-nix-workspace!")


if __name__ == "__main__":
    main()

import math
from typing import Any, Dict, List, Optional

def _is_pos(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x) and x > 0

def shear13_4_unstiffened_Wshape_elastic_py(
    d_mm: float,
    tw_mm: float,
    Fy_MPa: float,
    h_mm: Optional[float] = None,
    tf_mm: Optional[float] = None,
    phi_v: float = 0.9,
) -> Dict[str, Any]:
    warnings: List[str] = []
    trace: List[str] = []

    if not _is_pos(d_mm): raise ValueError("d_mm must be > 0")
    if not _is_pos(tw_mm): raise ValueError("tw_mm must be > 0")
    if not _is_pos(Fy_MPa): raise ValueError("Fy_MPa must be > 0")
    if not _is_pos(phi_v): phi_v = 0.9

    # clear web depth h
    if _is_pos(h_mm):
        h = float(h_mm)
        trace.append(f"Given: h = {h:.2f} mm (clear web depth)")
    else:
        if not _is_pos(tf_mm):
            raise ValueError("Need either h_mm OR tf_mm to compute h = d - 2*tf")
        h = float(d_mm) - 2.0 * float(tf_mm)
        trace.append(f"Computed: h = d - 2tf = {d_mm:.2f} - 2({tf_mm:.2f}) = {h:.2f} mm")

    if not (h > 0): raise ValueError("Computed/Provided h must be > 0")
    if h > d_mm: warnings.append("h_mm > d_mm (unexpected). Check section properties.")

    # Aw = d * tw
    Aw_mm2 = float(d_mm) * float(tw_mm)
    trace.append(f"Aw = d*tw = {d_mm:.2f}*{tw_mm:.2f} = {Aw_mm2:.2f} mm²")

    # lambda = h/tw
    lam = h / float(tw_mm)
    trace.append(f"λ = h/tw = {h:.2f}/{tw_mm:.2f} = {lam:.3f}")

    sqrtFy = math.sqrt(float(Fy_MPa))
    lam1 = 1014.0 / sqrtFy
    lam2 = 1435.0 / sqrtFy
    trace.append(f"λ1 = 1014/√Fy = {lam1:.3f}")
    trace.append(f"λ2 = 1435/√Fy = {lam2:.3f}")

    # Fs piecewise
    if lam <= lam1:
        Fs = 0.66 * float(Fy_MPa)
        branch = "A"
        trace.append(f"Branch A: Fs = 0.66Fy = {Fs:.2f} MPa")
    elif lam <= lam2:
        Fs = (670.0 * sqrtFy) / lam
        branch = "B"
        trace.append(f"Branch B: Fs = 670√Fy/λ = {Fs:.2f} MPa")
    else:
        Fs = 961200.0 / (lam * lam)
        branch = "C"
        trace.append(f"Branch C: Fs = 961200/λ² = {Fs:.2f} MPa")

    Vr_kN = (phi_v * Aw_mm2 * Fs) / 1000.0
    trace.append(f"Vr = φAwFs/1000 = {Vr_kN:.2f} kN")

    warnings.append("Scope: CSA S16 13.4 elastic shear, unstiffened web only.")
    warnings.append("Assumes rolled W-shape Aw = d*tw (project convention).")

    return {
        "d_mm": d_mm, "tw_mm": tw_mm, "h_mm": h,
        "Aw_mm2": Aw_mm2,
        "lambda_h_over_tw": lam,
        "lambda1": lam1, "lambda2": lam2,
        "Fy_MPa": Fy_MPa, "Fs_MPa": Fs,
        "phi_v": phi_v, "Vr_kN": Vr_kN,
        "branchUsed": branch,
        "warnings": warnings,
        "trace": trace,
        "ok": True,
        "scope": "CSA S16 13.4 — elastic shear, unstiffened web, W-shapes",
    }

def shearDemandCheck_py(Vu_kN: float, Vr_kN: float) -> Dict[str, Any]:
    if not (isinstance(Vu_kN, (int, float)) and math.isfinite(Vu_kN) and Vu_kN >= 0):
        raise ValueError("Vu_kN must be finite and ≥ 0")
    if not (isinstance(Vr_kN, (int, float)) and math.isfinite(Vr_kN) and Vr_kN > 0):
        raise ValueError("Vr_kN must be finite and > 0")
    utilization = Vu_kN / Vr_kN
    pass_ok = Vu_kN <= Vr_kN
    return {
        "Vu_kN": Vu_kN,
        "Vr_kN": Vr_kN,
        "utilization": utilization,
        "pass": pass_ok,
        "summary": "PASS (Vu ≤ Vr)" if pass_ok else "FAIL (Vu > Vr)",
    }

import math
import pandas as pd


# ----------------------------
# Load CSA W table (your CSV)
# ----------------------------
def load_csa_w_table(csv_path: str) -> pd.DataFrame:
    # file is cp1252 encoded (not utf-8)
    df = pd.read_csv(csv_path, encoding="cp1252")

    # normalize designation for matching
    df["Designation_norm"] = (
        df["Designation"].astype(str).str.upper().str.replace(" ", "", regex=False)
    )
    return df


def get_w_shape(df: pd.DataFrame, designation: str) -> dict:
    key = str(designation).upper().replace(" ", "")
    row = df.loc[df["Designation_norm"] == key]
    if row.empty:
        # helpful fallback: contains search
        sug = df.loc[df["Designation_norm"].str.contains(key, na=False), "Designation"].head(10).tolist()
        raise ValueError(f"Shape '{designation}' not found. Suggestions: {sug}")

    r = row.iloc[0].to_dict()

    # Extract what we need for shear calcs
    tw = float(r["Web Thickness w (mm)"])     # web thickness
    dw = float(r["d-2t (mm)"])                # clear web depth between flanges
    hw_over_tw = float(r["h/w"])              # already in your table

    # For W-shapes, CSA uses Aw = dw * tw
    Aw = dw * tw

    return {
        "Designation": r["Designation"],
        "Fy_default_note": "Fy is NOT in the table; supply from material input.",
        "tw_mm": tw,
        "dw_mm": dw,
        "Aw_mm2": Aw,
        "hw_over_tw": hw_over_tw,
        # keep anything else you want:
        "d_mm": float(r["Depth d (mm)"]),
        "bf_mm": float(r["Flange Width b (mm)"]),
        "tf_mm": float(r["Flange Thickness t (mm)"]),
    }


# ----------------------------
# CSA S16-14 13.4.1.1 (stiffened webs)
# ----------------------------
def kv_from_a_over_h(a_over_h: float) -> float:
    if a_over_h <= 0:
        raise ValueError("a_over_h must be > 0")
    if a_over_h < 1.0:
        return 4.0 + 5.34 / (a_over_h ** 2)
    return 5.34 + 4.0 / (a_over_h ** 2)


def k0_from_a_over_h(a_over_h: float) -> float:
    if a_over_h <= 0:
        raise ValueError("a_over_h must be > 0")
    return 1.0 / math.sqrt(1.0 + a_over_h ** 2)


def stiffened_web_shear_CSA13_4(
    Fy_MPa: float,
    hw_over_tw: float,
    a_over_h: float,
    Aw_mm2: float,
    phi_v: float = 0.9,
) -> dict:
    if Fy_MPa <= 0 or hw_over_tw <= 0 or Aw_mm2 <= 0:
        raise ValueError("Fy_MPa, hw_over_tw, and Aw_mm2 must be > 0")

    kv = kv_from_a_over_h(a_over_h)
    k0 = k0_from_a_over_h(a_over_h)

    # MPa
    Fcri = 290.0 * math.sqrt(Fy_MPa * kv) / hw_over_tw
    Fcre = 180000.0 * k0 / (hw_over_tw ** 2)

    root = math.sqrt(kv / Fy_MPa)
    t1 = 439.0 * root
    t2 = 502.0 * root
    t3 = 621.0 * root

    if hw_over_tw <= t1:
        Fs = 0.66 * Fy_MPa
        region = "b(i)"
    elif hw_over_tw <= t2:
        Fs = Fcri
        region = "b(ii)"
    elif hw_over_tw <= t3:
        Fs = Fcri + k0 * (0.50 * Fy_MPa - 0.866 * Fcri)
        region = "b(iii)"
    else:
        Fs = Fcre + k0 * (0.50 * Fy_MPa - 0.866 * Fcre)
        region = "b(iv)"

    # Vr = phi * Aw * Fs  => (N/mm^2)*(mm^2) = N
    Vr_N = phi_v * Aw_mm2 * Fs

    return {
        "Vr_N": Vr_N,
        "Vr_kN": Vr_N / 1000.0,
        "Fs_MPa": Fs,
        "region": region,
        "kv": kv,
        "k0": k0,
        "Fcri_MPa": Fcri,
        "Fcre_MPa": Fcre,
        "thresholds_hw_over_tw": {
            "439*sqrt(kv/Fy)": t1,
            "502*sqrt(kv/Fy)": t2,
            "621*sqrt(kv/Fy)": t3,
        },
    }


# ----------------------------
# Example: wire it together
# ----------------------------
if __name__ == "__main__":
    df = load_csa_w_table("/mnt/data/CSA_W_Section_Tables_2_clean.csv")

    shape = get_w_shape(df, "W310x60")  # example designation
    Fy = 350.0                         # MPa (user input)
    a_over_h = 0.75                    # = stiffener spacing / web depth (your UI input)

    out = stiffened_web_shear_CSA13_4(
        Fy_MPa=Fy,
        hw_over_tw=shape["hw_over_tw"],
        a_over_h=a_over_h,
        Aw_mm2=shape["Aw_mm2"],
        phi_v=0.9,
    )

    print(shape)
    print(out)