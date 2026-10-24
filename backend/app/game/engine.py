"""Pure, deterministic game engine (§8). No I/O: callers persist state and deliver events.

    start(content, member_ids, seed, now, rules) -> (state, events)
    apply(content, state, action, now)           -> (state, events)
    view(content, state, member_id)              -> per-member projection

`content` is a validated story's `content` dict; `state` is plain JSON (stored as the session's
canonical state). Events are {type, visibility: "public" | "member:<id>", payload}; a private
clue event is only ever addressed to its owner. `apply` never mutates its input.

Rules:
- A scene with a decision is voted on; a scene without one is a "Continue" vote to its `next`.
- A vote resolves when every active seat has voted, or `vote_grace_s` after a majority of seats
  have voted (resolved by a `tick`). The top choice wins; a tie gives the level-1 hint and a revote.
- Votes can change until the decision resolves. A vote for an earlier turn, or one sent with a
  state_version older than the start of the current turn, is STALE_STATE.
- Every member action carries an action_id; repeating one is a no-op (idempotent).
"""

import random
from collections import Counter
from copy import deepcopy
from typing import Any

CONTINUE = "continue"
DEFAULT_RULES = {"vote_grace_s": 45}
MAX_HINT_LEVEL = 3
PROCESSED_LIMIT = 500

State = dict[str, Any]
Event = dict[str, Any]


class GameError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _event(type_: str, payload: dict, to: str | None = None) -> Event:
    return {
        "type": type_,
        "visibility": "public" if to is None else f"member:{to}",
        "payload": payload,
    }


class _Story:
    """Read-only index over a story's content dict."""

    def __init__(self, content: dict) -> None:
        self.content = content
        self.roles = {r["id"]: r for r in content["roles"]}
        self.scenes = {s["id"]: s for s in content["scenes"]}
        self.scene_order = [s["id"] for s in content["scenes"]]
        self.clues = {c["id"]: c for c in content["clues"]}
        self.decisions = {d["id"]: d for d in content["decisions"]}
        self.endings = {e["id"]: e for e in content["endings"]}
        self.hints = {h["scene_id"]: h["levels"] for h in content["hints"]}
        self.variants = {v["id"]: v for v in content["variants"]}

    def clue_text(self, clue_id: str, variant: str) -> str:
        clue = self.clues[clue_id]
        return clue.get("text_by_variant", {}).get(variant, clue["text"])

    def decision_for(self, scene_id: str) -> dict:
        scene = self.scenes[scene_id]
        if scene.get("decision_id"):
            return self.decisions[scene["decision_id"]]
        return {
            "id": CONTINUE,
            "prompt": "",
            "choices": [{"id": CONTINUE, "label": "", "next": scene["next"]}],
        }


# ---- start --------------------------------------------------------------------------------


def start(
    content: dict, member_ids: list[str], seed: int, now: float, rules: dict | None = None
) -> tuple[State, list[Event]]:
    story = _Story(content)
    if not member_ids:
        raise GameError("NO_PLAYERS")
    rng = random.Random(seed)  # noqa: S311 (reproducible game shuffles; the seed is from secrets)
    variant = rng.choice(sorted(story.variants))

    role_ids = [r["id"] for r in content["roles"]]
    optional = content.get("optional_role")
    if len(member_ids) < len(role_ids) and optional in role_ids:
        role_ids.remove(optional)  # 3 players: the optional seat stays empty
    order = list(member_ids)
    rng.shuffle(order)
    seats = [{"member_id": m, "roles": [], "active": True} for m in order]
    for i, role in enumerate(role_ids):  # round-robin if there are more roles than people
        seats[i % len(seats)]["roles"].append(role)
    holder = {role: s["member_id"] for s in seats for role in s["roles"]}

    owner: dict[str, str] = {}
    for clue in content["clues"]:
        if variant not in clue["meaning_by_variant"]:
            continue  # this clue does not exist in this variant
        role = clue["owner_role"]
        if role == "public":
            owner[clue["id"]] = "public"
        elif role in holder:
            owner[clue["id"]] = holder[role]
        else:  # the optional role is unseated: its clues move to a core role
            owner[clue["id"]] = holder[content["redistribution"][clue["id"]]]

    state: State = {
        "variant": variant,
        "seed": seed,
        "rules": {**DEFAULT_RULES, **(rules or {})},
        "status": "active",
        "version": 0,
        "scene": content["start_scene"],
        "turn": 1,
        "turn_version": 0,
        "seats": seats,
        "clue_owner": owner,
        "revealed": [],
        "board": [],
        "votes": {},
        "majority_since": None,
        "hints_used": {},
        "history": [],
        "ending": None,
        "processed": [],
    }
    events = [_event("game.started", {"seats": len(seats)})]
    events += _enter_scene(story, state, content["start_scene"])
    return state, events


def _enter_scene(story: _Story, state: State, scene_id: str) -> list[Event]:
    state["scene"] = scene_id
    events = [_event("game.scene", {"scene_id": scene_id})]
    public, private = [], []
    for clue_id in story.scenes[scene_id]["reveals"]:
        owner = state["clue_owner"].get(clue_id)
        if owner is None or clue_id in state["revealed"]:
            continue
        state["revealed"].append(clue_id)
        if owner == "public":
            state["board"].append({"clue_id": clue_id, "by": None})
            public.append(clue_id)
        else:
            private.append((owner, clue_id))
    if public:
        events.append(_event("game.board.updated", {"added": public, "by": None}))
    for owner, clue_id in private:
        events.append(_event("game.clue.private", {"clue_id": clue_id}, to=owner))
    return events


# ---- apply --------------------------------------------------------------------------------


def apply(content: dict, state: State, action: dict, now: float) -> tuple[State, list[Event]]:
    story = _Story(content)
    if state["status"] != "active":
        raise GameError("GAME_OVER")
    state = deepcopy(state)
    kind = action["type"]

    if kind != "tick":
        member = action["member_id"]
        seat = next((s for s in state["seats"] if s["member_id"] == member), None)
        if seat is None or not seat["active"]:
            raise GameError("NOT_SEATED")
        key = f"{member}:{action['action_id']}"
        if key in state["processed"]:
            return state, []  # a repeat of an action already applied
        state["processed"] = (state["processed"] + [key])[-PROCESSED_LIMIT:]

    if kind == "vote":
        events = _vote(story, state, action, now)
    elif kind == "share":
        events = _share(story, state, action)
    elif kind == "hint":
        events = _hint(story, state)
    elif kind == "leave":
        events = _leave(story, state, action, now)
    elif kind == "tick":
        events = _maybe_resolve(story, state, now)
        if not events:
            return state, []  # nothing due yet: no new version
    else:
        raise GameError("UNKNOWN_ACTION")

    state["version"] += 1
    return state, events


def _active(state: State) -> list[str]:
    return [s["member_id"] for s in state["seats"] if s["active"]]


def _tally(state: State) -> dict[str, int]:
    active = set(_active(state))
    return dict(Counter(c for m, c in state["votes"].items() if m in active))


def _deadline(state: State) -> float | None:
    if state["majority_since"] is None:
        return None
    return state["majority_since"] + state["rules"]["vote_grace_s"]


def _tally_event(state: State, **extra) -> Event:
    return _event(
        "game.vote.tally",
        {
            "turn": state["turn"],
            "tally": _tally(state),
            "voted": sorted(state["votes"]),
            "deadline": _deadline(state),
            **extra,
        },
    )


def _vote(story: _Story, state: State, action: dict, now: float) -> list[Event]:
    if (
        action.get("turn") != state["turn"]
        or action.get("state_version", -1) < state["turn_version"]
    ):
        raise GameError("STALE_STATE")
    decision = story.decision_for(state["scene"])
    if action["choice_id"] not in {c["id"] for c in decision["choices"]}:
        raise GameError("INVALID_CHOICE")
    state["votes"][action["member_id"]] = action["choice_id"]  # replaces an earlier vote
    return _maybe_resolve(story, state, now) or [_tally_event(state)]


def _maybe_resolve(story: _Story, state: State, now: float) -> list[Event]:
    """Resolves the decision if it is due; otherwise only tracks the majority clock."""
    active = _active(state)
    cast = [m for m in state["votes"] if m in active]
    if not active or not cast:
        state["majority_since"] = None
        return []
    if len(cast) < len(active):
        if len(cast) * 2 <= len(active):
            state["majority_since"] = None
            return []
        if state["majority_since"] is None:
            state["majority_since"] = now
            return []
        if now < _deadline(state):
            return []
    return _resolve(story, state)


def _resolve(story: _Story, state: State) -> list[Event]:
    tally = _tally(state)
    top = max(tally.values())
    winners = sorted(c for c, n in tally.items() if n == top)
    decision = story.decision_for(state["scene"])
    state["votes"], state["majority_since"] = {}, None
    state["turn"] += 1
    state["turn_version"] = state["version"] + 1

    if len(winners) > 1:  # tie: a gentle nudge, then vote again
        state["hints_used"][state["scene"]] = max(1, state["hints_used"].get(state["scene"], 0))
        level_one = story.hints[state["scene"]][0]
        return [
            _tally_event(state, tie=winners, previous=tally),
            _event(
                "game.hint",
                {"scene_id": state["scene"], "level": 1, "text": level_one, "tie": True},
            ),
        ]

    choice_id = winners[0]
    choice = next(c for c in decision["choices"] if c["id"] == choice_id)
    target = choice.get("next") or choice["next_by_variant"][state["variant"]]
    state["history"].append(
        {
            "scene_id": state["scene"],
            "decision_id": decision["id"],
            "choice_id": choice_id,
            "tally": tally,
        }
    )
    events = [
        _event(
            "game.decision.resolved",
            {"decision_id": decision["id"], "choice_id": choice_id, "tally": tally},
        )
    ]
    if target in story.endings:
        state["status"], state["ending"] = "completed", target
        ending = story.endings[target]
        events.append(_event("game.completed", {"ending_id": target, "kind": ending["kind"]}))
        return events
    return events + _enter_scene(story, state, target)


def _share(story: _Story, state: State, action: dict) -> list[Event]:
    clue_id = action["clue_id"]
    owner = state["clue_owner"].get(clue_id)
    if owner != action["member_id"]:
        raise GameError("NOT_YOUR_CLUE")
    if clue_id not in state["revealed"]:
        raise GameError("CLUE_NOT_AVAILABLE")
    if any(p["clue_id"] == clue_id for p in state["board"]):
        raise GameError("ALREADY_SHARED")
    state["board"].append({"clue_id": clue_id, "by": action["member_id"]})
    return [_event("game.board.updated", {"added": [clue_id], "by": action["member_id"]})]


def _hint(story: _Story, state: State) -> list[Event]:
    scene = state["scene"]
    level = state["hints_used"].get(scene, 0) + 1
    if level > MAX_HINT_LEVEL:
        raise GameError("NO_MORE_HINTS")
    state["hints_used"][scene] = level
    return [
        _event(
            "game.hint", {"scene_id": scene, "level": level, "text": story.hints[scene][level - 1]}
        )
    ]


def _leave(story: _Story, state: State, action: dict, now: float) -> list[Event]:
    member = action["member_id"]
    for seat in state["seats"]:
        if seat["member_id"] == member:
            seat["active"] = False
    state["votes"].pop(member, None)
    if not _active(state):
        state["status"] = "abandoned"
        return [_event("game.completed", {"ending_id": None, "kind": "abandoned"})]
    return _maybe_resolve(story, state, now) or [_tally_event(state)]


# ---- view ---------------------------------------------------------------------------------


def view(content: dict, state: State, member_id: str) -> dict:
    """What one member may see. Never another member's unshared private clues."""
    story = _Story(content)
    variant = state["variant"]
    scene = story.scenes[state["scene"]]
    seat = next((s for s in state["seats"] if s["member_id"] == member_id), None)
    on_board = {p["clue_id"]: p["by"] for p in state["board"]}

    mine = [
        {"id": cid, "text": story.clue_text(cid, variant), "shared": cid in on_board}
        for cid in state["revealed"]
        if state["clue_owner"].get(cid) == member_id
    ]
    board = [
        {"id": p["clue_id"], "text": story.clue_text(p["clue_id"], variant), "by": p["by"]}
        for p in state["board"]
    ]
    decision = story.decision_for(state["scene"])
    used = state["hints_used"].get(state["scene"], 0)
    completed = state["status"] != "active"
    out = {
        "status": state["status"],
        "version": state["version"],
        "turn": state["turn"],
        "chapter": {
            "index": story.scene_order.index(state["scene"]) + 1,
            "total": len(story.scene_order),
            "scene_id": scene["id"],
            "title": scene["title"],
            "narration": scene["narration_base"],
            "objective": scene["objective"],
        },
        "you": {
            "member_id": member_id,
            "seated": bool(seat and seat["active"]),
            "roles": [
                {"id": r, "name": story.roles[r]["name"], "focus": story.roles[r]["focus"]}
                for r in (seat["roles"] if seat else [])
            ],
        },
        "seats": [
            {
                "member_id": s["member_id"],
                "roles": [story.roles[r]["name"] for r in s["roles"]],
                "active": s["active"],
            }
            for s in state["seats"]
        ],
        "private_clues": mine,
        "board": board,
        "decision": None
        if completed
        else {
            "id": decision["id"],
            "prompt": decision["prompt"],
            "choices": [{"id": c["id"], "label": c["label"]} for c in decision["choices"]],
            "tally": _tally(state),
            "voted": sorted(state["votes"]),
            "your_vote": state["votes"].get(member_id),
            "deadline": _deadline(state),
            "seats": len(_active(state)),
        },
        "hints": [{"level": i + 1, "text": story.hints[state["scene"]][i]} for i in range(used)],
        "hints_left": MAX_HINT_LEVEL - used,
        "ending": None,
    }
    if state["ending"]:
        ending = story.endings[state["ending"]]
        out["ending"] = {
            "id": ending["id"],
            "kind": ending["kind"],
            "title": ending["title"],
            "text": ending["text"],
            "solution": story.variants[variant]["solution_summary"],  # the case is closed now
        }
    return out
