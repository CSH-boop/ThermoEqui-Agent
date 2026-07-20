# API

FastAPI publishes OpenAPI at `/docs`. Every response carries `X-Request-ID`; errors use
`{"error":{"code","message","details","request_id"}}`. Calculation routes create immutable run
snapshots. `GET /api/runs/{run_id}/export?format=json|csv` returns a downloadable artifact.

Key routes: `/api/chat`, `/api/tasks/parse`, `/api/models/recommend`, `/api/models`,
`/api/parameters`, `/api/parameters/search`, all calculation endpoints (including the typed LLE
contract at `/api/calculations/lle`), `/api/validation`, run query and export, and `/health`.
