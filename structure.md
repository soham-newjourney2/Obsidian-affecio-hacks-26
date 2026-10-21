# ECHO — structure

Cooperative, AI-guided mysteries that turn solving together into real connection.
FastAPI modular monolith serving a vanilla HTML/CSS/JS frontend from the same origin.

```
echo/
├── .env.example            # every supported env var, safe defaults, no secrets
├── .gitignore
├── .python-version         # 3.12
├── LICENSE
├── pyproject.toml          # deps, pytest and ruff config (uv-managed)
├── uv.lock
├── structure.md            # this file
├── backend/
│   ├── app/
│   │   ├── main.py         # app factory: middleware, error handlers, routers, static mount
│   │   ├── core/           # config (settings), errors (standard error shape), logging (request id + access log)
│   │   └── api/v1/         # REST routers per domain (health)
│   └── tests/
│       ├── conftest.py     # settings + TestClient fixtures
│       └── integration/    # HTTP-level tests: health, error shape, static serving
└── frontend/               # served at "/"
    └── index.html          # placeholder landing (replaced in P02)
```

## Run

```
uv sync
uv run uvicorn backend.app.main:app --reload
uv run pytest -q
uv run ruff check .
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health/live` | process is up |
| GET | `/api/v1/health/ready` | app can serve (frontend present) |

All errors use `{"error": {"code", "message", "request_id"}}`; every response carries `X-Request-ID`.
