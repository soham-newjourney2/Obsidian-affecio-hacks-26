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
├── alembic.ini             # migrations config (URL comes from DATABASE_URL)
├── pyproject.toml          # deps, pytest and ruff config (uv-managed)
├── uv.lock
├── docs/
│   └── structure.md        # this file
├── backend/
│   ├── app/
│   │   ├── main.py         # app factory: settings, engine, limiters, middleware, routers, static mount
│   │   ├── core/           # config, errors (standard shape), logging (request id), security (Argon2, JWT, denylist), ratelimit
│   │   ├── db/             # base (naming convention, UTC datetime type), session (engine, SQLite pragmas), migrations/
│   │   ├── models/         # SQLAlchemy tables (users, profiles)
│   │   ├── schemas/        # Pydantic I/O (auth, profile)
│   │   ├── services/       # business logic (auth, profiles)
│   │   ├── content/        # curated data: profile options (interests, genres, roles, …)
│   │   └── api/            # deps (session, current user), v1/ routers (health, auth, users, meta)
│   └── tests/
│       ├── conftest.py     # runtime secret, per-test migrated SQLite, TestClient
│       ├── unit/           # security, rate limiter, settings, schemas
│       ├── integration/    # HTTP + DB: health, errors, static, auth, profile, migrations
│       └── e2e/            # Playwright browser tests against a live uvicorn (marker: e2e)
└── frontend/               # served at "/"
    ├── index.html          # landing: hero, how it works, audience, CTA
    ├── auth.html           # sign in / create account (tabs)
    ├── onboarding.html     # profile case file (create or edit)
    ├── lobby.html          # signed-in home (catalogue arrives in P05)
    ├── css/                # tokens (palette, type, space, motion), base, components, effects, pages/
    ├── js/core/            # strings (all UI text), api (bearer, errors), auth (session, guards), ui, fx
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
cp .env.example .env        # then set SECRET_KEY to 32+ random bytes
uv sync
uv run playwright install chromium
uv run alembic upgrade head
uv run uvicorn backend.app.main:app --reload
uv run pytest -q            # unit + integration
uv run pytest -q -m e2e     # browser tests (needs network for CDN fonts/GSAP)
uv run ruff check .
```

## Endpoints (`/api/v1`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health/live` | – | process is up |
| GET | `/health/ready` | – | frontend present and database reachable |
| POST | `/auth/register` | – | create account (18+ confirmed); returns a token. 5/h per IP |
| POST | `/auth/login` | – | returns a token; one generic error. 10/15 min per IP+email |
| POST | `/auth/logout` | bearer | revokes the current token |
| GET | `/auth/me` | bearer | id, email, display name, created_at |
| GET | `/users/me/profile` | bearer | own profile; 404 `PROFILE_NOT_FOUND` until onboarding |
| PUT | `/users/me/profile` | bearer | create/replace profile (curated ids only, bounded lists) |
| GET | `/meta/interests` | – | all profile option lists + limits |

- Tokens: HS256 JWT, 60 min, claims `sub`, `jti`, `iat`, `exp`; send as `Authorization: Bearer …`.
- Browser session lives in `sessionStorage` (per tab). Signed-in pages redirect to `/auth.html?next=…`;
  `next` accepts same-origin paths only.
- All errors use `{"error": {"code", "message", "request_id"}}`; every response carries `X-Request-ID`.
