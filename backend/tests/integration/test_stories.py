import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.services.stories import SeedResult, load_story_files
from backend.tests.conftest import seed, sqlite_url


def run_seed(db_path: Path, stories=None) -> SeedResult:
    return seed(sqlite_url(db_path), stories)


def test_seed_is_idempotent(db_path: Path) -> None:
    assert run_seed(db_path) == SeedResult(created=5)
    assert run_seed(db_path) == SeedResult(unchanged=5)
    stories = load_story_files()
    bumped = [s.model_copy(update={"version": s.version + 1}) if s.playable else s for s in stories]
    assert run_seed(db_path, bumped) == SeedResult(updated=1, unchanged=4)
    count = sqlite3.connect(db_path).execute("SELECT count(*) FROM stories").fetchone()[0]
    assert count == 5


def test_catalogue_lists_playable_first(client: TestClient, seeded: Path) -> None:
    res = client.get("/api/v1/stories")
    assert res.status_code == 200
    cards = res.json()
    assert [c["slug"] for c in cards][0] == "blackthorn_manor"
    assert [c["playable"] for c in cards] == [True, False, False, False, False]
    playable = cards[0]
    assert playable["est_minutes"] == 30
    assert playable["inspiration"]["author"] == "Arthur Conan Doyle"
    assert playable["inspiration"]["source_url"] == "https://www.gutenberg.org/ebooks/1661"
    # Coming-soon cards make no claims about play time.
    assert all(c["est_minutes"] is None for c in cards[1:])
    tagore = next(c for c in cards if c["slug"] == "hungry_stones")
    assert tagore["inspiration"]["language"] == "Bengali"


def test_story_detail_hides_solutions(client: TestClient, seeded: Path) -> None:
    res = client.get("/api/v1/stories/blackthorn_manor")
    assert res.status_code == 200
    body = res.json()
    assert [r["name"] for r in body["roles"]] == [
        "The Investigator",
        "The Archivist",
        "The Listener",
        "The Strategist",
    ]
    assert body["premise"].startswith("Two years ago")
    story = next(s for s in load_story_files() if s.story_id == "blackthorn_manor")
    secrets = (
        [v.solution_summary for v in story.content.variants]
        + [cl.text for cl in story.content.clues]
        + [e.text for e in story.content.endings]
        + [h.levels[2] for h in story.content.hints]
    )
    for secret in secrets:
        assert secret not in res.text
    for key in ("variants", "clues", "decisions", "endings", "hints", "config"):
        assert key not in body


def test_coming_soon_detail(client: TestClient, seeded: Path) -> None:
    body = client.get("/api/v1/stories/wizard_of_oz").json()
    assert body["playable"] is False
    assert body["roles"] == []
    assert body["premise"] is None
    assert "1939 film" in body["rights_notes"]


def test_unknown_story_404(client: TestClient, seeded: Path) -> None:
    res = client.get("/api/v1/stories/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "STORY_NOT_FOUND"


def test_excluded_story_is_hidden(client: TestClient, seeded: Path) -> None:
    with sqlite3.connect(seeded) as conn:
        conn.execute("UPDATE stories SET rights_status = 'excluded' WHERE slug = 'rue_morgue'")
    slugs = [c["slug"] for c in client.get("/api/v1/stories").json()]
    assert "rue_morgue" not in slugs
    assert client.get("/api/v1/stories/rue_morgue").status_code == 404


def test_empty_catalogue(client: TestClient) -> None:
    assert client.get("/api/v1/stories").json() == []
