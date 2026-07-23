export type Intent =
  | "CONCEPT_QA"
  | "MODEL_SELECTION_QA"
  | "PARAMETER_QUERY"
  | "DATA_QUERY"
  | "EQUILIBRIUM_CALCULATION"
  | "RESULT_INTERPRETATION"
  | "SENSITIVITY_ANALYSIS"
  | "PROCESS_RECOMMENDATION"
  | "TASK_CORRECTION"
  | "UNSUPPORTED_TASK";

export interface ComponentIdentity {
  component_id: string;
  name: string;
  cas_number?: string | null;
  aliases: string[];
}

export interface Conditions {
  temperature_K?: number | null;
  pressure_kPa?: number | null;
  liquid_composition?: number[] | null;
  vapor_composition?: number[] | null;
  feed_composition?: number[] | null;
}

export interface TaskManifest {
  task_id: string;
  equilibrium_type: "VLE" | "LLE" | "FLASH";
  calculation_type: string;
  components: ComponentIdentity[];
  conditions: Conditions;
  composition_basis: "mole_fraction" | "mass_fraction";
  requested_outputs: string[];
  validation_requirements: string[];
  assumptions: string[];
  model_name?: string | null;
  points: number;
  original_question?: string | null;
}

export interface EquilibriumPoint {
  temperature_K: number;
  pressure_kPa: number;
  liquid_composition: number[];
  vapor_composition: number[];
  equilibrium_residual: number;
}

export interface CheckResult {
  passed: boolean;
  metric?: number | null;
  tolerance?: number | null;
  message: string;
}

export interface ValidationReport {
  overall_status: "passed" | "warning" | "failed";
  composition_balance: CheckResult;
  material_balance: CheckResult;
  equilibrium_residual: CheckResult;
  convergence: CheckResult;
  parameter_applicability: CheckResult;
  phase_stability?: CheckResult | null;
  warnings: string[];
  recommended_action?: string | null;
  maximum_equilibrium_residual: number;
  mean_equilibrium_residual: number;
  solver_converged: boolean;
}

export interface ModelRecommendation {
  model_name: string;
  score: number;
  executable: boolean;
  reasons: string[];
  exclusions: string[];
  breakdown: ScoreBreakdown;
}

export interface ScoreBreakdown {
  phase_support_score: number;
  system_match_score: number;
  condition_match_score: number;
  parameter_availability_score: number;
  evidence_quality_score: number;
  extrapolation_penalty: number;
  numerical_risk_penalty: number;
}

export interface PhaseResult {
  phase: "liquid" | "vapor";
  fraction: number;
  composition: number[];
}

export interface CalculationEnvelope {
  result: {
    run_id: string;
    task_id: string;
    calculation_type: string;
    input_snapshot: Record<string, unknown>;
    model_name: string;
    parameter_set_id?: string | null;
    points: EquilibriumPoint[];
    phases: PhaseResult[];
    temperature_K?: number | null;
    pressure_kPa?: number | null;
    vapor_fraction?: number | null;
    phase_state: string;
    converged: boolean;
    residual: number;
    iterations: number;
    warnings: string[];
    backend_version: string;
    solver_name: string;
    failure?: Record<string, unknown> | null;
    created_at: string;
  };
  validation: ValidationReport;
  parameter_sources: Array<Record<string, string>>;
  model_recommendations: ModelRecommendation[];
}

export interface EvidenceStatement {
  category: "Knowledge" | "Database" | "Calculation" | "Inference" | "Estimate" | "Warning";
  text: string;
}

export interface AgentStep {
  phase: "plan" | "execute" | "validate" | "respond";
  status: "completed" | "failed" | "blocked";
  summary: string;
  tool_name?: string | null;
}

export interface ChatResponse {
  conversation_id: string;
  intent: Intent;
  answer: string;
  statements: EvidenceStatement[];
  execution_steps: AgentStep[];
  task?: TaskManifest | null;
  calculation?: CalculationEnvelope | null;
  request_id?: string | null;
}
