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
│   │   ├── models/         # SQLAlchemy tables (users, profiles, stories, rooms, room_members, messages, game_sessions, game_events, votes)
│   │   ├── schemas/        # Pydantic I/O (auth, profile, story cards/detail, rooms)
│   │   ├── services/       # business logic (auth, profiles, stories + seeding, rooms, chat, game: start/CAS apply/vote timers)
│   │   ├── ws/             # WebSocket: events (envelopes), manager (room sockets), handlers, notify (fan-out)
│   │   ├── game/           # story_schema (story file model + validator), engine (pure start/apply/view)
│   │   ├── content/        # profile options; stories/*.json (1 playable, 4 coming soon)
│   │   └── api/            # deps (session, current user), v1/ routers (health, auth, users, meta, stories, rooms, sessions)
│   └── tests/
│       ├── conftest.py     # runtime secret, per-test migrated SQLite, TestClient
│       ├── wsutil.py       # WebSocket test helpers
│       ├── unit/           # security, rate limiter, settings, schemas, story validator, engine
│       ├── integration/    # HTTP + DB: health, errors, static, auth, profile, stories, rooms, ws, game (incl. concurrency), migrations
│       └── e2e/            # Playwright tests against a live, seeded uvicorn (marker: e2e); helpers.py
└── frontend/               # served at "/"
    ├── index.html          # landing: hero, how it works, audience, CTA
    ├── auth.html           # sign in / create account (tabs)
    ├── onboarding.html     # profile case file (create or edit)
    ├── lobby.html          # signed-in home (teammate-owned)
    ├── room.html           # start/join a table, live waiting room + chat, then the story room (game mode)
    ├── css/                # tokens, base, components, effects, pages/ (teammate-owned); temp.css (new pages, to be merged)
    ├── js/core/            # strings, api, auth, ui, fx; ws (room socket client); strings-temp (new pages, to be merged)
    ├── js/pages/           # one module per page (room.js + room-game.js for the story room)
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
| GET | `/sessions/{id}` | member | the caller's own game projection (never others' private clues) |

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
- Room changes made over REST (join, ready, start, leave) are pushed to connected sockets.

## WebSocket (`/api/v1/ws/rooms/{room_id}`)

- First frame must be `auth {token}` within 5 s, else close 4401. Non-members (or anyone who has
  left) get 4403. Membership, token expiry and revocation are re-checked on every frame.
- Client → server: `presence.ping`, `chat.send{client_message_id, body}`, `player.ready{ready}`, `room.leave`,
  `game.vote{turn, state_version, choice_id, client_action_id}`, `game.hint.request{client_action_id}`,
  `game.clue.share{clue_id, client_action_id}` (game actions 2/s per member).
- Server → client: `room.snapshot` (room view, you, online, last 50 messages) on every (re)connect,
  `room.member{event, member_id, online, room?}` (state events carry each viewer's own room view;
  presence events `online`/`offline` carry only the online list), `chat.message`, `error{code, ref_id}`.
- Limits: frames ≤ 8 KB; chat 1/s with burst 5 per member; body 1–1000 chars. A retried
  `client_message_id` is stored once and echoed only to the sender.
- `js/core/ws.js`: auth-first connect, 20 s heartbeat, backoff reconnect (1–15 s), resync from the
  snapshot; chat sent while offline is resent with the same client id.

## Game engine

- `game/engine.py` is pure: `start(content, members, seed, now)`, `apply(content, state, action, now)`,
  `view(content, state, member)`. The variant and seat order come from a seeded RNG (seed from `secrets`).
- With 3 players the optional role (Strategist) is unseated and its clues move to the roles named in
  `redistribution`. Private clues reach their owner when their scene is entered; public clues go
  straight to the board; owners can pin (share) their clues to the board.
- Votes resolve when every active seat has voted, or 45 s after a majority (a server timer sends a
  `tick`); a tie gives the level-1 hint and a revote. Scenes without a decision are a "continue" vote.
- Actions carry an `action_id` (idempotent). A vote for an earlier turn, or from before the current
  turn began, is `STALE_STATE` (the server then sends a fresh `room.snapshot`).
- `services/game.py` applies actions under a per-session lock and a compare-and-swap on
  `state_version`; events go to `game_events` (seq per session), votes to `votes`.
- Game events reach each socket only if public or addressed to that member, each with that member's
  own `view`. The room snapshot carries the same `game` view for reconnects.

## Story room (room.html, game mode)

- Desktop: private clues | narrative | evidence board + chat; mobile: Story / Your clues / Board / Chat tabs.
- Renders only from the member's own `view` (snapshot or game event), so refresh and reconnect just
  re-render; votes are never re-sent. A reconnect overlay shows while the socket is down.
- Typewriter narration (screen readers get the full text at once; reduced motion shows it whole),
  "clue unlocked" highlight, pin-to-board with red-string SVG, wax-seal vote cards with live tally and
  grace countdown, 3-level hints, chapter progress, ending stamp + solution.
- Private vs shared clues differ by icon and label, not colour.
