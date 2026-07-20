# Model routing

Routing applies hard exclusions, then an explainable score composed of phase support, system fit,
conditions, parameter availability, evidence quality, extrapolation penalty, and numerical risk.
Wilson is excluded from LLE. Electrolytes are rejected. Ideal/Wilson are favored for near-ideal
low-pressure VLE, NRTL/UNIQUAC for polar non-ideal low-pressure VLE, and Peng-Robinson for high-
pressure hydrocarbons. A required but missing parameter set makes a candidate non-executable.
