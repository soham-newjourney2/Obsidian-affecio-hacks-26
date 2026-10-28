<p align="center"><img src="frontend/assets/brand/logo.svg" alt="ECHO" width="220"></p>

# ECHO

Meeting new people is awkward, especially when you've just moved to a new campus or city.
A one-to-one chat with a stranger puts all the pressure on the conversation. We wanted
something easier: give a small group a shared problem and let the talking happen on its own.

ECHO is a cooperative mystery game for three or four people. Everyone at the table gets
different clues that nobody else can see, so the only way to solve the case is to talk,
compare notes and decide together. The story is just the excuse. The point is the people
you end up talking to.

![Landing page](docs/screenshots/landing.jpg)

## How it works

You sign up (18+), fill in a short profile with your interests and when you're usually free,
and then either start a table and share the invite code with friends, or let ECHO put you in
a group with people who like similar things.

Once the case starts, an AI narrator sets each scene. You read your private clues, pin the
useful ones to a shared evidence board, chat, and vote on what to do next. If you have a
hunch you can type it in your own words; the AI turns it into one of the options and shows it
to the table, but it never votes for anyone.

At the end you see what really happened, a short recap of how your table got there, and two
quick questions about how it went. If you and someone at the table both want to stay in
touch, you can connect. If they don't, they never see that you asked.

| Lobby | Waiting for the table |
|---|---|
| ![Lobby](docs/screenshots/lobby.jpg) | ![Waiting room](docs/screenshots/table.jpg) |
| **Playing a case** | **After the case** |
| ![Story room](docs/screenshots/story.jpg) | ![Results](docs/screenshots/results.jpg) |

## Things we decided not to do

No match percentages, no personality scores, no leaderboards, no location, no recordings,
and nobody is pushed to share contact details. The app only shows real data. If there's
nothing to show yet, it shows nothing rather than made-up numbers.

## A few details

- Tables are live over WebSockets, so chat, presence and votes update instantly, and a
  dropped connection picks up where it left off.
- The game logic runs on the server. Each case has three possible solutions picked at random,
  so replays aren't the same, and nobody's browser ever receives another player's private
  clues.
- The AI narrator uses Groq, falls back to Gemini, and if both are unavailable the game uses
  the hand-written text. The game never waits on the AI, and everything it writes is checked
  before anyone sees it.
- For quieter moments you can switch on demo mode and fill empty seats with clearly labelled
  AI companions.
- Voice and video are optional (8x8 Jitsi). Text chat always works, whether or not anyone
  joins the call.
- You can block or report someone from the table, and admins can review reports.

## Running it locally

You'll need [uv](https://docs.astral.sh/uv/). It installs Python 3.12 for you.

```bash
cp .env.example .env          # then set SECRET_KEY to a long random string
uv sync
uv run alembic upgrade head
uv run python scripts/seed.py # loads the stories
uv run uvicorn backend.app.main:app --reload
```

Then open <http://127.0.0.1:8000>.

Want to try a full table on your own? `uv run python scripts/demo.py` creates three demo
accounts and a waiting room and prints the login details. Or keep `DEMO_MODE=true` and fill
the empty seats with AI companions.

The defaults in `.env.example` work offline: the AI is mocked and voice/video is off. To use
the real AI, set `AI_PROVIDER=chain` and add a `GROQ_API_KEY` and/or `GEMINI_API_KEY`. For
voice/video, set `ENABLE_VOICE_VIDEO=true` with your JaaS app id, key id and private key path.
SQLite is used out of the box; a `postgres://` URL works too after `uv sync --group postgres`.
Keys only ever live on the server.

## Stories

All the stories are our own adaptations of works that are in the public domain in both India
and the US. They keep the original names and plots, don't copy long passages, and every case
in the app links to the original text.

- **Blackthorn Manor** (playable): from *The Adventure of the Speckled Band*, Arthur Conan Doyle, 1892
- **The Locked Room on the Rue Morgue** (coming soon): from *The Murders in the Rue Morgue*, Edgar Allan Poe, 1841
- **The Traveller's Return** (coming soon): from *The Time Machine*, H. G. Wells, 1895
- **The Road of Yellow Brick** (coming soon): from *The Wonderful Wizard of Oz*, L. Frank Baum, 1900 (the book, not the film)
- **The Palace of Hungry Stones** (coming soon): from *The Hungry Stones*, Rabindranath Tagore, 1895, adapted from the Bengali original

## Tests

```bash
uv run pytest -q                    # unit and integration tests
uv run playwright install chromium
uv run pytest -q -m e2e             # browser tests, several players at once
uv run ruff check .
```

The browser tests play whole cases from start to finish and check that each player only
ever sees their own clues. There's also a Postgres test that runs when you set
`TEST_POSTGRES_URL` to an empty database you don't mind wiping.

More on how the code is laid out: [docs/structure.md](docs/structure.md).

## License

[MIT](LICENSE)
