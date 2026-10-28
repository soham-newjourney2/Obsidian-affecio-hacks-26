"""AI rewrites hooked into the game: narration, hints and the closing recap."""

import asyncio
import json
import re
import sqlite3
import time

import pytest

from backend.app.ai.base import ProviderError, ProviderResult
from backend.app.ai.chain import AIChain
from backend.app.core.config import Settings
from backend.app.core.ratelimit import TokenBucket
from backend.app.game.engine import _Story
from backend.app.services import ai_hooks
from backend.app.services.stories import load_story_files
from backend.tests.integration.test_game import ROUTE, canonical, start_case, vote
from backend.tests.wsutil import connected, next_of

CONTENT = next(
    s for s in load_story_files() if s.story_id == "blackthorn_manor"
).content.model_dump(mode="json")
UUID = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}")


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"register_rate_limit": 1000})


class FakeModel:
    """Answers like a well-behaved model ("AI: " + the authored text) and records inputs."""

    name, model = "groq", "fake-model"

    def __init__(self, delay: float = 0.0, fail: bool = False) -> None:
        self.delay, self.fail = delay, fail
        self.inputs: list[dict] = []

    async def complete(self, system: str, user: str, max_tokens: int) -> ProviderResult:
        inputs = json.loads(user.split("\n", 1)[1])
        self.inputs.append(inputs)
        await asyncio.sleep(self.delay)
        if self.fail:
            raise ProviderError("error", "down")
        return ProviderResult({"text": "AI: " + inputs["base"]}, "fake-model", 10, 10)

    async def aclose(self) -> None:
        return None


def use(client, model: FakeModel) -> FakeModel:
    client.app.state.ai = AIChain(
        [model], client.app.state.sessionmaker, max_output_tokens=400,
        max_calls_per_session=30, timeout_s=8,
    )  # fmt: skip
    client.app.state.game_bucket = TokenBucket(rate=1000, burst=1000)
    return model


def idle(client) -> None:
    client.portal.call(ai_hooks.wait_idle, client.app)


def snapshot(client, session_id, player) -> dict:
    return client.get(f"/api/v1/sessions/{session_id}", headers=player.headers).json()["view"]


def test_narration_rewrite_arrives_after_the_scene(client, table) -> None:
    model = use(client, FakeModel())
    room, ada, bo, cy, _ = table
    with connected(client, room["id"], ada) as ws:
        session_id = start_case(client, room, [ada, bo, cy])["session_id"]
        scene = next_of(ws, "game.scene")["payload"]["view"]
        assert not scene["chapter"]["narration"].startswith("AI: ")  # authored text first
        rewrite = next_of(ws, "game.ai_text", key="narration:s1_visit")
        assert rewrite["payload"]["view"]["chapter"]["narration"].startswith("AI: Rain streaks")
    assert snapshot(client, session_id, bo)["chapter"]["narration"].startswith("AI: ")
    assert model.inputs[0]["scene"] == "The Visit"


def test_slow_ai_never_blocks_play(client, table) -> None:
    use(client, FakeModel(delay=2.0))
    room, ada, bo, cy, _ = table
    with connected(client, room["id"], ada) as ws:
        started = time.perf_counter()
        start_case(client, room, [ada, bo, cy])
        next_of(ws, "game.scene")
        assert time.perf_counter() - started < 1.5  # the scene went out without waiting


def test_stale_narration_is_dropped(client, table, seeded) -> None:
    use(client, FakeModel(delay=0.5))
    room, ada, bo, cy, _ = table
    with (
        connected(client, room["id"], ada) as wa,
        connected(client, room["id"], bo) as wb,
        connected(client, room["id"], cy) as wc,
    ):
        start_case(client, room, [ada, bo, cy])
        for ws in (wa, wb, wc):  # leave the first scene before its rewrite can land
            vote(ws, next_of(ws, "game.scene")["payload"]["view"], "c_room")
        next_of(wa, "game.decision.resolved")
    idle(client)
    texts = canonical(seeded).get("ai_text", {})
    assert "narration:s1_visit" not in texts  # dropped: the table had moved on
    assert texts["narration:s3_room"].startswith("AI: ")


def test_hint_rewrite(client, table) -> None:
    use(client, FakeModel())
    room, ada, bo, cy, _ = table
    with connected(client, room["id"], ada) as ws:
        session_id = start_case(client, room, [ada, bo, cy])["session_id"]
        next_of(ws, "game.scene")
        ws.send_json({"type": "game.hint.request", "id": "h", "payload": {"client_action_id": "h"}})
        assert next_of(ws, "game.hint")["payload"]["view"]["hints"][0]["level"] == 1
        next_of(ws, "game.ai_text", key="hint:s1_visit:1")
    hint = snapshot(client, session_id, cy)["hints"][0]["text"]
    assert hint.startswith("AI: Every sound Elinor describes")


def test_closing_recap_uses_ai_once_ready(client, table) -> None:
    use(client, FakeModel())
    room, ada, bo, cy, _ = table
    with (
        connected(client, room["id"], ada) as wa,
        connected(client, room["id"], bo) as wb,
        connected(client, room["id"], cy) as wc,
    ):
        session_id = start_case(client, room, [ada, bo, cy])["session_id"]
        views = [next_of(ws, "game.scene")["payload"]["view"] for ws in (wa, wb, wc)]
        for choice in ROUTE:
            for ws, view in zip((wa, wb, wc), views, strict=True):
                vote(ws, view, choice)
            views = [
                next_of(ws, "game.decision.resolved", choice_id=choice)["payload"]["view"]
                for ws in (wa, wb, wc)
            ]
    idle(client)
    summary = client.get(f"/api/v1/sessions/{session_id}/summary", headers=ada.headers).json()
    assert summary["recap_source"] == "ai"
    assert summary["recap"].startswith("AI: A table of 3")


def test_ai_down_play_continues_on_authored_text(client, table, seeded) -> None:
    use(client, FakeModel(fail=True))
    room, ada, bo, cy, _ = table
    session_id = start_case(client, room, [ada, bo, cy])["session_id"]
    idle(client)
    assert not snapshot(client, session_id, ada)["chapter"]["narration"].startswith("AI: ")
    rows = (
        sqlite3.connect(seeded)
        .execute("SELECT provider, status, purpose FROM ai_logs ORDER BY created_at")
        .fetchall()
    )
    assert rows == [("groq", "error", "narrate"), ("fallback", "fallback", "narrate")]


def test_inputs_are_minimal(client, table, seeded) -> None:
    model = use(client, FakeModel())
    room, ada, bo, cy, _ = table
    with (
        connected(client, room["id"], ada) as wa,
        connected(client, room["id"], bo) as wb,
        connected(client, room["id"], cy) as wc,
    ):
        start_case(client, room, [ada, bo, cy])
        for ws in (wa, wb, wc):
            vote(ws, next_of(ws, "game.scene")["payload"]["view"], "c_room")
        next_of(wa, "game.decision.resolved")
        wa.send_json({"type": "game.hint.request", "id": "h", "payload": {"client_action_id": "h"}})
        next_of(wa, "game.hint")
    idle(client)
    state = canonical(seeded)
    sent = json.dumps(model.inputs)
    assert model.inputs and {"Ada", "Bo", "Cy"} <= set(model.inputs[0]["players"])
    assert "@example.com" not in sent  # no emails
    assert not UUID.search(sent)  # no internal ids
    story = _Story(CONTENT)
    for clue_id, owner in state["clue_owner"].items():
        assert clue_id not in sent
        if owner != "public":  # private clues never go to the AI (none were shared here)
            assert story.clue_text(clue_id, state["variant"]) not in sent


def test_ai_logs_record_each_purpose_without_bodies(client, table, seeded) -> None:
    use(client, FakeModel())
    room, ada, bo, cy, _ = table
    with connected(client, room["id"], ada) as ws:
        start_case(client, room, [ada, bo, cy])
        next_of(ws, "game.scene")
        ws.send_json({"type": "game.hint.request", "id": "h", "payload": {"client_action_id": "h"}})
        next_of(ws, "game.hint")
    idle(client)
    db = sqlite3.connect(seeded)
    rows = db.execute("SELECT purpose, status, session_id IS NOT NULL FROM ai_logs").fetchall()
    assert sorted(rows) == [("hint", "success", 1), ("narrate", "success", 1)]
    columns = [c[1] for c in db.execute("PRAGMA table_info(ai_logs)")]
    assert not {"prompt", "response", "body", "input", "output", "text"} & set(columns)
