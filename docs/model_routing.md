# Model routing

Routing applies hard exclusions, then an explainable score composed of phase support, system fit,
conditions, parameter availability, evidence quality, extrapolation penalty, and numerical risk.
Wilson is excluded from LLE. Electrolytes are rejected. Ideal/Wilson are favored for near-ideal
low-pressure VLE, NRTL/UNIQUAC for polar non-ideal low-pressure VLE, and Peng-Robinson for high-
pressure hydrocarbons. A required but missing parameter set makes a candidate non-executable.

Execution uses a separate conservative backend gate. An explicit user model is preserved. When
the model is unset, the current first production rule selects Ideal/Raoult at or below 500 kPa and
Peng-Robinson above 500 kPa. LLE is never guessed: it returns `missing_parameters` until a reviewed
NRTL or UNIQUAC parameter set and production backend are available. Peng-Robinson requires a
reviewed ChemSep PR interaction entry for every binary pair; the adapter does not silently replace
missing values with zero.
