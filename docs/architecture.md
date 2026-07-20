# Architecture

```mermaid
flowchart LR
  UI[Next.js workbench] --> API[FastAPI]
  API --> ORCH[Conversation orchestrator]
  ORCH --> LLM[LLM provider]
  ORCH --> ROUTER[Rule model router]
  ORCH --> EXEC[Calculation executor]
  EXEC --> BACKEND[ThermodynamicBackend]
  BACKEND --> IDEAL[Ideal/Raoult adapter]
  EXEC --> VALIDATE[Validation controller]
  API --> DB[(SQLite/PostgreSQL)]
  ROUTER --> CARDS[Model cards]
  EXEC --> PARAMS[Parameter repository]
```

Only the deterministic backend emits thermodynamic numbers. API, agent, and UI exchange Pydantic
contracts and immutable run snapshots. Third-party engines can be added behind the backend protocol
without leaking their internal object model into the service layer.
