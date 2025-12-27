// shear_13_4.ts
// CSA S16 Clause 13.4 (Elastic analysis) — Unstiffened web, W-shapes only
// Vr = φ * Aw * Fs
// Aw = d * tw (rolled W-shapes)
// λ = h/tw, with h = clear web depth (d - 2tf) or use provided "clearDepth"

export type ShearInputs13_4_Unstiffened = {
  // From CSV / section properties (mm)
  d_mm: number;          // overall depth
  tw_mm: number;         // web thickness
  h_mm?: number;         // clear web depth; preferred if you have it
  tf_mm?: number;        // flange thickness (only needed if h_mm not supplied)
  // Material (MPa)
  Fy_MPa: number;        // user input
  // Resistance factor
  phi_v?: number;        // default set below
};

export type ShearResult13_4_Unstiffened = {
  scope: string;
  ok: boolean;
  warnings: string[];

  // Key geometry
  d_mm: number;
  tw_mm: number;
  h_mm: number;

  // Derived
  Aw_mm2: number;
  lambda_h_over_tw: number;

  // Piecewise thresholds
  lambda1: number;
  lambda2: number;

  // Stress and resistance
  Fy_MPa: number;
  Fs_MPa: number;
  phi_v: number;
  Vr_kN: number;

  // Trace for UI
  branchUsed: "A" | "B" | "C";
  trace: string[];
};

function isFinitePositive(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x) && x > 0;
}

export function shear13_4_unstiffened_Wshape_elastic(
  inp: ShearInputs13_4_Unstiffened
): ShearResult13_4_Unstiffened {
  const warnings: string[] = [];
  const trace: string[] = [];

  const phi_v = isFinitePositive(inp.phi_v) ? inp.phi_v : 0.9; // set to your project standard

  // Validate inputs
  if (!isFinitePositive(inp.d_mm)) throw new Error("d_mm must be > 0");
  if (!isFinitePositive(inp.tw_mm)) throw new Error("tw_mm must be > 0");
  if (!isFinitePositive(inp.Fy_MPa)) throw new Error("Fy_MPa must be > 0");

  // Determine clear web depth h
  let h_mm: number | undefined = undefined;

  if (isFinitePositive(inp.h_mm)) {
    h_mm = inp.h_mm;
    trace.push(`Given: h = ${h_mm.toFixed(2)} mm (clear web depth from table)`);
  } else {
    if (!isFinitePositive(inp.tf_mm)) {
      throw new Error("Need either h_mm OR tf_mm to compute h_mm = d_mm - 2*tf_mm");
    }
    h_mm = inp.d_mm - 2 * inp.tf_mm;
    trace.push(`Computed: h = d - 2tf = ${inp.d_mm.toFixed(2)} - 2(${inp.tf_mm.toFixed(2)}) = ${h_mm.toFixed(2)} mm`);
  }

  if (!(h_mm > 0)) throw new Error("Computed/Provided h_mm must be > 0");
  if (h_mm > inp.d_mm) warnings.push("h_mm > d_mm (unexpected). Check section properties.");

  // Aw = d * tw (mm^2)
  const Aw_mm2 = inp.d_mm * inp.tw_mm;
  trace.push(`Aw = d * tw = ${inp.d_mm.toFixed(2)} * ${inp.tw_mm.toFixed(2)} = ${Aw_mm2.toFixed(2)} mm²`);

  // λ = h/tw
  const lambda = h_mm / inp.tw_mm;
  trace.push(`λ = h/tw = ${h_mm.toFixed(2)} / ${inp.tw_mm.toFixed(2)} = ${lambda.toFixed(3)}`);

  // thresholds λ1, λ2
  const sqrtFy = Math.sqrt(inp.Fy_MPa);
  const lambda1 = 1014 / sqrtFy;
  const lambda2 = 1435 / sqrtFy;
  trace.push(`λ1 = 1014/√Fy = 1014/√${inp.Fy_MPa.toFixed(1)} = ${lambda1.toFixed(3)}`);
  trace.push(`λ2 = 1435/√Fy = 1435/√${inp.Fy_MPa.toFixed(1)} = ${lambda2.toFixed(3)}`);

  // Piecewise Fs (MPa)
  let Fs: number;
  let branchUsed: "A" | "B" | "C";

  if (lambda <= lambda1) {
    Fs = 0.66 * inp.Fy_MPa;
    branchUsed = "A";
    trace.push(`Branch A (λ ≤ λ1): Fs = 0.66 Fy = 0.66 * ${inp.Fy_MPa.toFixed(1)} = ${Fs.toFixed(2)} MPa`);
  } else if (lambda <= lambda2) {
    Fs = (670 * sqrtFy) / lambda;
    branchUsed = "B";
    trace.push(`Branch B (λ1 < λ ≤ λ2): Fs = 670√Fy/λ = 670*√${inp.Fy_MPa.toFixed(1)}/${lambda.toFixed(3)} = ${Fs.toFixed(2)} MPa`);
  } else {
    Fs = 961200 / (lambda * lambda);
    branchUsed = "C";
    trace.push(`Branch C (λ > λ2): Fs = 961200/λ² = 961200/${lambda.toFixed(3)}² = ${Fs.toFixed(2)} MPa`);
  }

  // Vr = φ * Aw * Fs
  // Units: Aw(mm^2)*Fs(MPa=N/mm^2)=N ; convert N→kN by /1000
  const Vr_kN = (phi_v * Aw_mm2 * Fs) / 1000;
  trace.push(`Vr = φ Aw Fs = ${phi_v.toFixed(2)} * ${Aw_mm2.toFixed(2)} * ${Fs.toFixed(2)} /1000 = ${Vr_kN.toFixed(2)} kN`);

  // Guardrails (scope warnings)
  warnings.push("Scope: CSA S16 Clause 13.4 elastic, unstiffened web only (no tension-field / stiffened web branch).");
  warnings.push("Assumes rolled W-shape web shear area Aw = d*tw (use your standard’s convention for rolled shapes).");

  return {
    scope: "CSA S16 13.4 — elastic shear, unstiffened web, W-shapes",
    ok: true,
    warnings,
    d_mm: inp.d_mm,
    tw_mm: inp.tw_mm,
    h_mm,
    Aw_mm2,
    lambda_h_over_tw: lambda,
    lambda1,
    lambda2,
    Fy_MPa: inp.Fy_MPa,
    Fs_MPa: Fs,
    phi_v,
    Vr_kN,
    branchUsed,
    trace,
  };
}

export function shearDemandCheck(Vu_kN: number, Vr_kN: number) {
  if (!(Vu_kN >= 0) || !Number.isFinite(Vu_kN)) throw new Error("Vu_kN must be a finite number ≥ 0");
  if (!(Vr_kN > 0) || !Number.isFinite(Vr_kN)) throw new Error("Vr_kN must be a finite number > 0");

  const utilization = Vu_kN / Vr_kN;
  const pass = Vu_kN <= Vr_kN;

  return {
    Vu_kN,
    Vr_kN,
    utilization,
    pass,
    summary: pass ? "PASS (Vu ≤ Vr)" : "FAIL (Vu > Vr)",
  };
}