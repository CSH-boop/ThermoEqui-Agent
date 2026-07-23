# API

FastAPI publishes OpenAPI at `/docs`. Every response carries `X-Request-ID`; errors use
`{"error":{"code","message","details","request_id"}}`. Calculation routes create immutable run
snapshots. `GET /api/runs/{run_id}/export?format=json|csv` returns a downloadable artifact.

The conversation orchestrator supports `deterministic`, `deepseek`, and `openai` providers through
`LLM_PROVIDER`. DeepSeek uses its OpenAI-compatible `/chat/completions` endpoint; external providers
may structure and explain tasks but never emit thermodynamic calculation values.

Key routes: `/api/chat`, `/api/tasks/parse`, `/api/models/recommend`, `/api/models`,
`/api/parameters`, `/api/parameters/search`, all calculation endpoints (including the typed LLE
contract at `/api/calculations/lle`), `/api/validation`, run query and export, and `/health`.
