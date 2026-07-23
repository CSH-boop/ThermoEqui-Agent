"""Canonical domain schemas for calculations, validation, routing, and chat."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Intent(StrEnum):
    CONCEPT_QA = "CONCEPT_QA"
    MODEL_SELECTION_QA = "MODEL_SELECTION_QA"
    PARAMETER_QUERY = "PARAMETER_QUERY"
    DATA_QUERY = "DATA_QUERY"
    EQUILIBRIUM_CALCULATION = "EQUILIBRIUM_CALCULATION"
    RESULT_INTERPRETATION = "RESULT_INTERPRETATION"
    SENSITIVITY_ANALYSIS = "SENSITIVITY_ANALYSIS"
    PROCESS_RECOMMENDATION = "PROCESS_RECOMMENDATION"
    TASK_CORRECTION = "TASK_CORRECTION"
    UNSUPPORTED_TASK = "UNSUPPORTED_TASK"


class FailureType(StrEnum):
    SEMANTIC_FAILURE = "semantic_failure"
    MISSING_DATA = "missing_data"
    MISSING_PARAMETERS = "missing_parameters"
    UNSUPPORTED_MODEL = "unsupported_model"
    NUMERICAL_NONCONVERGENCE = "numerical_nonconvergence"
    PHYSICAL_VALIDATION_FAILURE = "physical_validation_failure"
    PHASE_INSTABILITY = "phase_instability"
    PARAMETER_OUT_OF_DOMAIN = "parameter_out_of_domain"
    MODEL_CONFLICT = "model_conflict"


class ComponentIdentity(BaseModel):
    component_id: str
    name: str
    cas_number: str | None = None
    aliases: list[str] = Field(default_factory=list)


class ThermodynamicConditions(BaseModel):
    temperature_K: float | None = Field(default=None, gt=0)
    pressure_kPa: float | None = Field(default=None, gt=0)
    liquid_composition: list[float] | None = None
    vapor_composition: list[float] | None = None
    feed_composition: list[float] | None = None

    @model_validator(mode="after")
    def validate_compositions(self) -> ThermodynamicConditions:
        for label in ("liquid_composition", "vapor_composition", "feed_composition"):
            values = getattr(self, label)
            if values is None:
                continue
            if not values or any(value < 0 or value > 1 for value in values):
                raise ValueError(f"{label} must contain mole fractions in [0, 1]")
            if abs(sum(values) - 1.0) > 1e-8:
                raise ValueError(f"{label} must sum to one within 1e-8")
        return self


class TaskManifest(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    equilibrium_type: Literal["VLE", "LLE", "FLASH"]
    calculation_type: str
    components: list[ComponentIdentity] = Field(min_length=1)
    conditions: ThermodynamicConditions
    composition_basis: Literal["mole_fraction", "mass_fraction"] = "mole_fraction"
    requested_outputs: list[str] = Field(default_factory=lambda: ["table", "validation"])
    validation_requirements: list[str] = Field(
        default_factory=lambda: ["composition_balance", "equilibrium_residual", "convergence"]
    )
    assumptions: list[str] = Field(default_factory=list)
    model_name: str | None = None
    points: int = Field(default=21, ge=2, le=501)
    original_question: str | None = None


class SystemProfile(BaseModel):
    component_count: int
    is_electrolyte: bool
    all_hydrocarbons: bool
    is_polar: bool
    association_risk: bool
    pressure_regime: Literal["low", "moderate", "high", "unknown"]
    phase_split_risk: Literal["low", "medium", "high", "unknown"]
    supported: bool
    evidence: list[str] = Field(default_factory=list)


class ModelCard(BaseModel):
    model_name: str
    family: str
    supported_tasks: list[str]
    excluded_systems: list[str]
    requires_binary_parameters: bool
    pressure_regime: list[str]
    validation_requirements: list[str]
    implementation_status: Literal["available", "contract_only", "planned"]


class ParameterSet(BaseModel):
    parameter_set_id: str = Field(default_factory=lambda: str(uuid4()))
    model_name: str
    component_order: list[str]
    parameters: dict[str, float]
    parameter_form: str
    units: dict[str, str]
    temperature_range_K: tuple[float, float] | None = None
    pressure_range_kPa: tuple[float, float] | None = None
    equilibrium_types: list[str]
    source_title: str | None = None
    source_identifier: str | None = None
    source_type: Literal["literature", "database", "user_supplied", "test_fixture", "estimated", "unknown"]
    quality_level: str
    notes: str | None = None


class FailureDetail(BaseModel):
    failure_type: FailureType
    message: str
    recovery_action: str
    details: dict[str, Any] = Field(default_factory=dict)


class EquilibriumPoint(BaseModel):
    temperature_K: float
    pressure_kPa: float
    liquid_composition: list[float]
    vapor_composition: list[float]
    equilibrium_residual: float


class PhaseResult(BaseModel):
    phase: Literal["liquid", "vapor"]
    fraction: float = Field(ge=0, le=1)
    composition: list[float]


class CalculationResult(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    calculation_type: str
    input_snapshot: dict[str, Any]
    model_name: str
    parameter_set_id: str | None = None
    points: list[EquilibriumPoint] = Field(default_factory=list)
    phases: list[PhaseResult] = Field(default_factory=list)
    temperature_K: float | None = None
    pressure_kPa: float | None = None
    vapor_fraction: float | None = None
    phase_state: Literal["liquid", "vapor", "two_phase", "curve", "unknown"] = "unknown"
    converged: bool
    residual: float
    iterations: int
    warnings: list[str] = Field(default_factory=list)
    backend_version: str
    solver_name: str = "unspecified"
    failure: FailureDetail | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CheckResult(BaseModel):
    passed: bool
    metric: float | None = None
    tolerance: float | None = None
    message: str


class ValidationReport(BaseModel):
    overall_status: Literal["passed", "warning", "failed"]
    composition_balance: CheckResult
    material_balance: CheckResult
    equilibrium_residual: CheckResult
    convergence: CheckResult
    parameter_applicability: CheckResult
    phase_stability: CheckResult | None = None
    warnings: list[str] = Field(default_factory=list)
    recommended_action: str | None = None
    maximum_equilibrium_residual: float
    mean_equilibrium_residual: float
    solver_converged: bool


class CalculationEnvelope(BaseModel):
    result: CalculationResult
    validation: ValidationReport
    parameter_sources: list[dict[str, str]] = Field(default_factory=list)
    model_recommendations: list[ModelRecommendation] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    phase_support_score: float
    system_match_score: float
    condition_match_score: float
    parameter_availability_score: float
    evidence_quality_score: float
    extrapolation_penalty: float
    numerical_risk_penalty: float

    @property
    def total(self) -> float:
        return (
            self.phase_support_score
            + self.system_match_score
            + self.condition_match_score
            + self.parameter_availability_score
            + self.evidence_quality_score
            - self.extrapolation_penalty
            - self.numerical_risk_penalty
        )


class ModelRecommendation(BaseModel):
    model_name: str
    score: float
    executable: bool
    reasons: list[str]
    exclusions: list[str] = Field(default_factory=list)
    breakdown: ScoreBreakdown


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


class EvidenceStatement(BaseModel):
    category: Literal["Knowledge", "Database", "Calculation", "Inference", "Estimate", "Warning"]
    text: str


class AgentStep(BaseModel):
    phase: Literal["plan", "execute", "validate", "respond"]
    status: Literal["completed", "failed", "blocked"]
    summary: str
    tool_name: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    intent: Intent
    answer: str
    statements: list[EvidenceStatement]
    execution_steps: list[AgentStep] = Field(default_factory=list)
    task: TaskManifest | None = None
    calculation: CalculationEnvelope | None = None
    request_id: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class RunRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    request_id: str
    task_id: str
    status: str
    input_snapshot: dict[str, Any]
    result: dict[str, Any]
    validation: dict[str, Any]
    created_at: datetime


CalculationEnvelope.model_rebuild()
