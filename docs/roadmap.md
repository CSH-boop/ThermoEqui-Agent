# Roadmap

Phase 4 will add evidence-backed parameter regression, production NRTL/UNIQUAC binary LLE,
multi-model comparison, sensitivity analysis, PDF reports, and DWSIM/Aspen configuration support.
Later research may evaluate SRK, Dortmund-UNIFAC, CPA, PC-SAFT, eNRTL, and Pitzer adapters. Scope
expansion only follows verification coverage; electrolytes, SLE, VLLE, and full flowsheets remain
out of scope for the current release.

Potential engine adapters include Phasepy for activity-coefficient/EOS mixing workflows,
Clapeyron.jl for broader research-grade equations of state, and NeqSim for industrial JVM
workflows. Each remains isolated behind `ThermodynamicBackend` and must pass the same parameter
evidence and validation gates before being marked available.
