# Agent and thermodynamics integrations

## Decision

ThermoEqui-Agent keeps its FastAPI/Next.js product shell and selectively adopts the tool-oriented
agent boundary demonstrated by
[datamllab/CAi_copilot](https://github.com/datamllab/CAi_copilot). No CAi_copilot source code is
vendored. DeepSeek classifies and formulates a typed task, then selects one tool from registry
metadata using a JSON-only allowlisted contract. The current bounded loop permits one tool
execution per turn. Arbitrary Bash, Python, and notebook tools are intentionally excluded.

Deterministic Peng-Robinson calculations use the pinned
[`thermo==0.6.1`](https://github.com/CalebBell/thermo) package through a local adapter. Upstream
objects never cross the application boundary: the adapter maps them to `CalculationResult`, adds
source evidence, and sends every result through `validate_equilibrium_result`.

## Think-execute contract

1. **Plan** — DeepSeek returns a `TaskManifest` matching the supplied JSON Schema. It may leave
   `model_name` null for deterministic routing and must not calculate equilibrium values.
2. **Execute** — `EngineeringToolRegistry` permits only the `phase_equilibrium` tool. The backend
   registry resolves a reviewed model adapter.
3. **Validate** — compositions, phase fractions, material balance, equilibrium residual,
   convergence, applicability, and available phase-stability evidence are checked independently.
4. **Respond** — DeepSeek may explain only the tool result and validation report. Ungrounded
   numbers and citations are withheld.

The UI exposes these four high-level audit steps. It does not expose model chain-of-thought.

## Production implementation matrix

| Model | Backend | Current executable scope | Parameter policy | Status |
|---|---|---|---|---|
| Ideal/Raoult | Internal deterministic solver | Binary bubble/dew, isobaric/isothermal VLE, TP flash, azeotrope candidate search | Reviewed local pure-property correlations | Available, low-pressure baseline |
| Peng-Robinson | CalebBell/thermo adapter | Hydrocarbon/allowlisted light-gas bubble/dew, binary VLE curves, TP flash, phase-state classification, azeotrope candidate search | Pure properties from thermo; every binary pair must exist in ChemSep PR; exact matrix/order/form/units/version are snapshotted and hashed; engineering applicability review remains required | Available |
| Wilson | Planned activity-coefficient adapter | VLE contract | Reviewed directional binary parameters required | Contract only |
| NRTL | Planned activity-coefficient adapter | VLE/LLE contract | Reviewed directional binary parameters required | Contract only |
| UNIQUAC | Planned activity-coefficient adapter | VLE/LLE contract | Reviewed binary parameters and structural constants required | Contract only |

“Contract only” models remain visible for recommendation and schema design but cannot emit
calculation results. They fail with structured `missing_parameters` instead of synthetic defaults.

## Extension seam

Add another model or engine by implementing `ThermodynamicBackend`, registering its aliases and
supported calculations in `ThermodynamicBackendRegistry`, providing evidence-bearing parameter
sources, and adding behavioral tests at `calculate_equilibrium` or the HTTP calculation endpoint.
Do not couple DeepSeek prompts or frontend components to an upstream engine object.

## Deliberate v0.1 boundary

Electrolytes, reactive equilibrium, SLE, polymers, hydrates, petroleum pseudocomponents,
polymorphs, VLLE, and flowsheet design are rejected explicitly. LLE currently has a typed contract
but no production numerical backend.
