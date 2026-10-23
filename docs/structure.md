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
├── scripts/
│   └── seed.py             # validate story files and upsert them (idempotent)
├── pyproject.toml          # deps, pytest and ruff config (uv-managed)
├── uv.lock
├── docs/
│   └── structure.md        # this file
├── backend/
│   ├── app/
│   │   ├── main.py         # app factory: settings, engine, limiters, middleware, routers, static mount
│   │   ├── core/           # config, errors (standard shape), logging (request id), security (Argon2, JWT, denylist), ratelimit
│   │   ├── db/             # base (naming convention, UTC datetime type), session (engine, SQLite pragmas), migrations/
│   │   ├── models/         # SQLAlchemy tables (users, profiles, stories, rooms, room_members)
│   │   ├── schemas/        # Pydantic I/O (auth, profile, story cards/detail, rooms)
│   │   ├── services/       # business logic (auth, profiles, stories + seeding, rooms)
│   │   ├── game/           # story_schema (story file model + structural validator)
│   │   ├── content/        # profile options; stories/*.json (1 playable, 4 coming soon)
│   │   └── api/            # deps (session, current user), v1/ routers (health, auth, users, meta, stories, rooms)
│   └── tests/
│       ├── conftest.py     # runtime secret, per-test migrated SQLite, TestClient
│       ├── unit/           # security, rate limiter, settings, schemas, story validator
│       ├── integration/    # HTTP + DB: health, errors, static, auth, profile, stories, rooms (incl. concurrency), migrations
│       └── e2e/            # Playwright tests against a live, seeded uvicorn (marker: e2e); helpers.py
└── frontend/               # served at "/"
    ├── index.html          # landing: hero, how it works, audience, CTA
    ├── auth.html           # sign in / create account (tabs)
    ├── onboarding.html     # profile case file (create or edit)
    ├── lobby.html          # signed-in home: catalogue, case-file dialog, join by code, room panel
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
uv run python scripts/seed.py
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
| GET | `/stories` | – | catalogue cards, playable first (rights-excluded stories hidden) |
| GET | `/stories/{slug}` | – | premise, roles, inspiration + source link; never solutions or clues |
| POST | `/rooms` | bearer | create a room for a playable story; returns the invite code once |
| POST | `/rooms/join` | bearer | join by code (normalized; 20 tries / 15 min per user) |
| GET | `/rooms/{id}` | member | room view: story, members (display names), can_start |
| POST | `/rooms/{id}/ready` | member | `{ready: bool}` while waiting |
| POST | `/rooms/{id}/start` | host | needs 3–4 present members, all ready; revokes the invite |
| POST | `/rooms/{id}/leave` | member | host hands over to the longest-present member; empty room is abandoned |

- Tokens: HS256 JWT, 60 min, claims `sub`, `jti`, `iat`, `exp`; send as `Authorization: Bearer …`.
- Browser session lives in `sessionStorage` (per tab). Signed-in pages redirect to `/auth.html?next=…`;
  `next` accepts same-origin paths only.
- All errors use `{"error": {"code", "message", "request_id"}}`; every response carries `X-Request-ID`.

## Stories

- One JSON file per story in `backend/app/content/stories/`; `story_id` must match the file name.
- `game/story_schema.py` validates metadata and rights for every story, and for playable ones the
  full graph: no unreachable nodes, dead ends or cycles; a success path in every variant; every role
  holds a private clue in every variant; the 3-player redistribution keeps all optional-role clues.
- Clue wording can vary per variant (`text_by_variant`) so each replay is deducible.

## Rooms

- Invite codes: 8 chars of base32 from `secrets`, stored only as sha256, valid 2 hours, revoked on
  start. Unknown, expired and revoked codes all return the same `INVITE_INVALID`.
- Each room mutation first takes the room's write lock (no-op `UPDATE … RETURNING`), so capacity and
  start checks are atomic (SQLite write lock now, row lock on Postgres).
- The lobby polls `GET /rooms/{id}` every 3 s while waiting (replaced by WebSocket updates in P07).
