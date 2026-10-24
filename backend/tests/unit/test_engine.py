import copy
import itertools
import json

import pytest

from backend.app.game import engine
from backend.app.game.engine import CONTINUE, GameError
from backend.app.services.stories import load_story_files

CONTENT = next(s for s in load_story_files() if s.story_id == "blackthorn_manor").content
C = CONTENT.model_dump(mode="json")
FOUR = ["m1", "m2", "m3", "m4"]
THREE = ["m1", "m2", "m3"]
_ids = itertools.count()


def seed_for(variant: str, members=FOUR) -> int:
    for seed in range(1000):
        state, _ = engine.start(C, members, seed, now=0)
        if state["variant"] == variant:
            return seed
    raise AssertionError(variant)


def act(state, kind, member=None, now=0.0, **kw):
    action = {"type": kind, **kw}
    if member is not None:
        action |= {"member_id": member, "action_id": f"a{next(_ids)}"}
    return engine.apply(C, state, action, now)


def vote_all(state, choice, members=None, now=0.0):
    events = []
    for m in members or [s["member_id"] for s in state["seats"] if s["active"]]:
        state, ev = act(
            state,
            "vote",
            m,
            now,
            choice_id=choice,
            turn=state["turn"],
            state_version=state["version"],
        )
        events += ev
    return state, events


def types(events):
    return [e["type"] for e in events]


# --- start ---------------------------------------------------------------------------------


def test_start_is_deterministic_per_seed() -> None:
    a, events_a = engine.start(C, FOUR, 42, now=0)
    b, events_b = engine.start(C, FOUR, 42, now=0)
    assert a == b and events_a == events_b
    variants = {engine.start(C, FOUR, s, now=0)[0]["variant"] for s in range(60)}
    assert variants == {"v1", "v2", "v3"}  # every variant is reachable by seed


def test_four_players_get_one_role_each() -> None:
    state, events = engine.start(C, FOUR, 1, now=0)
    roles = sorted(r for s in state["seats"] for r in s["roles"])
    assert roles == ["archivist", "investigator", "listener", "strategist"]
    assert all(len(s["roles"]) == 1 for s in state["seats"])
    assert types(events)[:2] == ["game.started", "game.scene"]


def test_three_players_redistribute_strategist_clues() -> None:
    state, _ = engine.start(C, THREE, 1, now=0)
    roles = sorted(r for s in state["seats"] for r in s["roles"])
    assert roles == ["archivist", "investigator", "listener"]
    holder = {r: s["member_id"] for s in state["seats"] for r in s["roles"]}
    assert state["clue_owner"]["c_floorplan"] == holder["archivist"]
    assert state["clue_owner"]["c_timeline"] == holder["listener"]
    # Every clue of the story still has an owner: nothing dropped.
    assert set(state["clue_owner"]) == {c["id"] for c in C["clues"]}


def test_first_scene_reveals_private_clues_to_owners_only() -> None:
    state, events = engine.start(C, FOUR, 3, now=0)
    private = [e for e in events if e["type"] == "game.clue.private"]
    assert private
    for e in private:
        assert e["visibility"] == f"member:{state['clue_owner'][e['payload']['clue_id']]}"
    board = [e for e in events if e["type"] == "game.board.updated"]
    assert board[0]["payload"]["added"] == ["c_whistle"]


# --- scripted play-throughs ----------------------------------------------------------------

SUCCESS_PLAN = {"v1": "c_watch", "v2": "c_lamp_store", "v3": "c_gas_main"}


@pytest.mark.parametrize("variant", ["v1", "v2", "v3"])
@pytest.mark.parametrize("members", [FOUR, THREE], ids=["4p", "3p"])
@pytest.mark.parametrize("route", ["grounds", "room"])
def test_every_variant_scripted_to_success(variant, members, route) -> None:
    state, _ = engine.start(C, members, seed_for(variant, members), now=0)
    if route == "grounds":
        state, events = vote_all(state, "c_grounds")
        assert state["scene"] == "s2_grounds"
        state, events = vote_all(state, CONTINUE)
    else:
        state, events = vote_all(state, "c_room")
    assert state["scene"] == "s3_room"
    state, _ = vote_all(state, "c_creature")
    assert state["scene"] == "s4_vigil"
    state, events = vote_all(state, SUCCESS_PLAN[variant])
    assert state["status"] == "completed"
    assert types(events)[-1] == "game.completed"
    assert events[-1]["payload"]["kind"] == "success"
    view = engine.view(C, state, members[0])
    assert view["ending"]["kind"] == "success" and view["decision"] is None
    assert view["ending"]["solution"]


def test_safe_retreat_from_every_variant() -> None:
    for variant in ("v1", "v2", "v3"):
        state, _ = engine.start(C, FOUR, seed_for(variant), now=0)
        for choice in ("c_room", "c_leak", "c_inn"):
            state, events = vote_all(state, choice)
        assert events[-1]["payload"]["kind"] == "safe"


# --- voting rules --------------------------------------------------------------------------


def test_votes_can_change_until_resolved() -> None:
    state, _ = engine.start(C, FOUR, 5, now=0)
    t, v = state["turn"], state["version"]
    state, _ = act(state, "vote", "m1", choice_id="c_grounds", turn=t, state_version=v)
    state, events = act(state, "vote", "m1", choice_id="c_room", turn=t, state_version=v)
    assert events[-1]["payload"]["tally"] == {"c_room": 1}
    state, _ = vote_all(state, "c_room", ["m2", "m3", "m4"])
    assert state["scene"] == "s3_room"


def test_tie_gives_level_one_hint_and_revote() -> None:
    state, _ = engine.start(C, FOUR, 5, now=0)
    turn = state["turn"]
    state, _ = vote_all(state, "c_grounds", ["m1", "m2"])
    state, events = vote_all(state, "c_room", ["m3", "m4"])
    assert types(events)[-2:] == ["game.vote.tally", "game.hint"]
    assert events[-2]["payload"]["tie"] == ["c_grounds", "c_room"]
    assert events[-1]["payload"] == {
        "scene_id": "s1_visit",
        "level": 1,
        "text": C["hints"][0]["levels"][0],
        "tie": True,
    }
    assert state["scene"] == "s1_visit" and state["turn"] == turn + 1 and state["votes"] == {}
    state, _ = vote_all(state, "c_room")  # the revote resolves
    assert state["scene"] == "s3_room"


def test_majority_then_grace_resolves_on_tick() -> None:
    state, _ = engine.start(C, FOUR, 5, now=0, rules={"vote_grace_s": 45})
    state, events = vote_all(state, "c_room", ["m1", "m2", "m3"], now=100)
    assert events[-1]["payload"]["deadline"] == 145  # 3 of 4 is a majority: clock starts
    state, events = act(state, "tick", now=144)
    assert events == [] and state["scene"] == "s1_visit"
    state, events = act(state, "tick", now=145)
    assert state["scene"] == "s3_room"
    assert "game.decision.resolved" in types(events)


def test_half_is_not_a_majority() -> None:
    state, _ = engine.start(C, FOUR, 5, now=0)
    state, events = vote_all(state, "c_room", ["m1", "m2"], now=10)
    assert events[-1]["payload"]["deadline"] is None
    state, events = act(state, "tick", now=10_000)
    assert events == [] and state["scene"] == "s1_visit"


def test_stale_votes_rejected() -> None:
    state, _ = engine.start(C, FOUR, 5, now=0)
    old_turn, old_version = state["turn"], state["version"]
    state, _ = vote_all(state, "c_room")
    with pytest.raises(GameError) as exc:
        act(state, "vote", "m1", choice_id="c_leak", turn=old_turn, state_version=old_version)
    assert exc.value.code == "STALE_STATE"
    with pytest.raises(GameError) as exc:  # right turn, but a version from before the turn began
        act(state, "vote", "m1", choice_id="c_leak", turn=state["turn"], state_version=old_version)
    assert exc.value.code == "STALE_STATE"


def test_invalid_choice_rejected() -> None:
    state, _ = engine.start(C, FOUR, 5, now=0)
    with pytest.raises(GameError, match="INVALID_CHOICE"):
        act(state, "vote", "m1", choice_id="ending_success", turn=1, state_version=0)


def test_duplicate_action_is_idempotent() -> None:
    state, _ = engine.start(C, FOUR, 5, now=0)
    action = {
        "type": "vote",
        "member_id": "m1",
        "action_id": "same",
        "choice_id": "c_room",
        "turn": 1,
        "state_version": 0,
    }
    once, events = engine.apply(C, state, action, 0)
    twice, again = engine.apply(C, once, action, 0)
    assert events and again == [] and twice == once


def test_apply_never_mutates_its_input() -> None:
    state, _ = engine.start(C, FOUR, 5, now=0)
    before = copy.deepcopy(state)
    act(state, "vote", "m1", choice_id="c_room", turn=1, state_version=0)
    assert state == before


def test_non_seated_member_rejected() -> None:
    state, _ = engine.start(C, FOUR, 5, now=0)
    with pytest.raises(GameError, match="NOT_SEATED"):
        act(state, "hint", "intruder")


# --- clues, board and hints ----------------------------------------------------------------


def test_projections_never_contain_others_private_clues() -> None:
    state, _ = engine.start(C, FOUR, 9, now=0)
    state, _ = vote_all(state, "c_room")  # reveal the room's clues too
    owner = state["clue_owner"]
    for member in FOUR:
        dumped = json.dumps(engine.view(C, state, member))
        for clue_id, who in owner.items():
            if who in ("public", member) or clue_id not in state["revealed"]:
                continue
            assert clue_id not in dumped
            assert engine._Story(C).clue_text(clue_id, state["variant"]) not in dumped
        mine = {c["id"] for c in engine.view(C, state, member)["private_clues"]}
        assert mine == {c for c, w in owner.items() if w == member and c in state["revealed"]}


def test_sharing_pins_a_clue_for_everyone() -> None:
    state, _ = engine.start(C, FOUR, 9, now=0)
    owner = state["clue_owner"]
    clue = next(c for c in state["revealed"] if owner[c] != "public")
    holder = owner[clue]
    other = next(m for m in FOUR if m != holder)
    with pytest.raises(GameError, match="NOT_YOUR_CLUE"):
        act(state, "share", other, clue_id=clue)
    state, events = act(state, "share", holder, clue_id=clue)
    assert events == [
        {
            "type": "game.board.updated",
            "visibility": "public",
            "payload": {"added": [clue], "by": holder},
        }
    ]
    assert clue in {c["id"] for c in engine.view(C, state, other)["board"]}
    flags = {c["id"]: c["shared"] for c in engine.view(C, state, holder)["private_clues"]}
    assert flags[clue] is True
    with pytest.raises(GameError, match="ALREADY_SHARED"):
        act(state, "share", holder, clue_id=clue)


def test_unrevealed_clue_cannot_be_shared() -> None:
    state, _ = engine.start(C, FOUR, 9, now=0)
    future = next(
        c for c, w in state["clue_owner"].items() if w != "public" and c not in state["revealed"]
    )
    with pytest.raises(GameError, match="CLUE_NOT_AVAILABLE"):
        act(state, "share", state["clue_owner"][future], clue_id=future)


def test_three_hint_levels_then_none() -> None:
    state, _ = engine.start(C, FOUR, 9, now=0)
    levels = []
    for _ in range(3):
        state, events = act(state, "hint", "m1")
        levels.append(events[0]["payload"]["level"])
    assert levels == [1, 2, 3]
    assert "Listener" in engine.view(C, state, "m2")["hints"][1]["text"]  # L2 nudges a role
    assert engine.view(C, state, "m2")["hints_left"] == 0
    with pytest.raises(GameError, match="NO_MORE_HINTS"):
        act(state, "hint", "m1")


# --- seats leaving -------------------------------------------------------------------------


def test_leaving_seat_lets_the_rest_resolve() -> None:
    state, _ = engine.start(C, FOUR, 9, now=0)
    state, _ = vote_all(state, "c_room", ["m1", "m2", "m3"])
    state, events = act(state, "leave", "m4")
    assert state["scene"] == "s3_room"  # all remaining seats had voted
    with pytest.raises(GameError, match="NOT_SEATED"):
        act(state, "hint", "m4")


def test_everyone_leaving_abandons() -> None:
    state, _ = engine.start(C, THREE, 9, now=0)
    for m in THREE:
        state, events = act(state, "leave", m)
    assert state["status"] == "abandoned"
    with pytest.raises(GameError, match="GAME_OVER"):
        act(state, "tick", now=1)
