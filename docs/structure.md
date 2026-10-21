# ECHO — structure

Cooperative, AI-guided mysteries that turn solving together into real connection.
FastAPI modular monolith serving a vanilla HTML/CSS/JS frontend from the same origin.

```
echo/
├── .env.example            # every supported env var, safe defaults, no secrets
├── .gitignore
├── .python-version         # 3.12
├── LICENSE
├── README.md               # short intro (full version in P20)
├── pyproject.toml          # deps, pytest and ruff config (uv-managed)
├── uv.lock
├── docs/
│   └── structure.md        # this file
├── backend/
│   ├── app/
│   │   ├── main.py         # app factory: middleware, error handlers, routers, static mount
│   │   ├── core/           # config (settings), errors (standard error shape), logging (request id + access log)
│   │   └── api/v1/         # REST routers per domain (health)
│   └── tests/
│       ├── conftest.py     # settings + TestClient fixtures
│       ├── integration/    # HTTP-level tests: health, error shape, static serving
│       └── e2e/            # Playwright browser tests against a live uvicorn (marker: e2e)
└── frontend/               # served at "/"
    ├── index.html          # landing: hero, how it works, audience, CTA
    ├── auth.html           # holding page until accounts land (P04)
    ├── css/                # tokens (palette, type, space, motion), base, components, effects, pages/
    ├── js/core/            # strings (all UI text), ui (toast, modal, busy state), fx (atmosphere, reduced motion)
    ├── js/pages/           # one module per page
    └── assets/brand/       # logo.svg (wordmark, ripple "O"), favicon.svg
```

## Design system

- Palette: ink/navy base, gaslight gold accent, parchment cards, oxblood wax seal (`css/tokens.css`).
- Type: Cormorant Garamond (display), Inter (UI), Courier Prime (narration) via Google Fonts.
- Motion: GSAP 3 from cdnjs with SRI, optional. Pages render fully without it, and
  `prefers-reduced-motion` skips all GSAP timelines and CSS atmosphere animation.
- Text is bound from `strings.js` through `data-s` attributes and always set with `textContent`.

## Run

```
uv sync
uv run playwright install chromium
uv run uvicorn backend.app.main:app --reload
uv run pytest -q            # unit + integration
uv run pytest -q -m e2e     # browser tests (needs network for CDN fonts/GSAP)
uv run ruff check .
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health/live` | process is up |
| GET | `/api/v1/health/ready` | app can serve (frontend present) |

All errors use `{"error": {"code", "message", "request_id"}}`; every response carries `X-Request-ID`.
