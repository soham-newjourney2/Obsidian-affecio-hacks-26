"""Results and reflection, built only from recorded events (game_events + votes), never from
inferences about people (§8). Badges are private and never ranked. Plus the 2-question pulse."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AppError
from backend.app.models import GameEvent, GameSession, PulseResponse, RoomMember, Story, User, Vote
from backend.app.models.room import PRESENT_STATUSES
from backend.app.services.rooms import member_of

CONSENSUS_MIN = 2  # decisions where your vote matched the table's choice


async def _member_for(session: AsyncSession, game: GameSession, user: User) -> RoomMember:
    member = await member_of(session, game.room_id, user.id)
    if member is None or member.status not in PRESENT_STATUSES:
        raise AppError(403, "NOT_A_MEMBER", "You are not in this game.")
    return member


async def load_finished(session: AsyncSession, session_id: uuid.UUID, user: User):
    game = await session.get(GameSession, session_id)
    if game is None:
        raise AppError(404, "SESSION_NOT_FOUND", "Game not found.")
    member = await _member_for(session, game, user)
    if game.status == "active":
        raise AppError(409, "SESSION_ACTIVE", "The case is still being played.")
    return game, member


def _choice_label(content: dict, decision_id: str, choice_id: str) -> str | None:
    for decision in content["decisions"]:
        if decision["id"] == decision_id:
            return next((c["label"] for c in decision["choices"] if c["id"] == choice_id), None)
    return None  # the "continue" step between scenes


@dataclass
class _Facts:
    """Table-level facts, all derived from recorded events and votes."""

    story: Story
    content: dict[str, Any]
    events: list[GameEvent]
    votes: list[Vote]
    visited: list[str] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    pins_by: dict[str, int] = field(default_factory=dict)
    hints_by: dict[str, int] = field(default_factory=dict)
    ending: dict[str, Any] | None = None
    players: list[dict[str, Any]] = field(default_factory=list)

    @property
    def team(self) -> dict[str, Any]:
        return {
            "chapters": len(self.visited),
            "decisions": len(self.chapters),
            "clues_pinned": sum(self.pins_by.values()),
            "hints_used": sum(self.hints_by.values()),
            "players": self.players,
        }


async def _collect(session: AsyncSession, game: GameSession) -> _Facts:
    story = await session.get(Story, game.story_id)
    content = story.config["content"]
    scenes = {s["id"]: s for s in content["scenes"]}
    decisions = {d["id"]: d for d in content["decisions"]}
    endings = {e["id"]: e for e in content["endings"]}
    facts = _Facts(
        story=story,
        content=content,
        events=list(
            await session.scalars(
                select(GameEvent).where(GameEvent.session_id == game.id).order_by(GameEvent.seq)
            )
        ),
        votes=list(
            await session.scalars(
                select(Vote).where(Vote.session_id == game.id, Vote.status == "active")
            )
        ),
    )
    for event in facts.events:
        payload = event.payload
        if event.type == "game.scene" and payload["scene_id"] not in facts.visited:
            facts.visited.append(payload["scene_id"])
        elif event.type == "game.decision.resolved":
            if payload["decision_id"] in decisions:  # skip the "continue" steps
                facts.chapters.append(
                    {
                        "scene_id": payload["scene_id"],
                        "title": scenes[payload["scene_id"]]["title"],
                        "prompt": decisions[payload["decision_id"]]["prompt"],
                        "choice": _choice_label(
                            content, payload["decision_id"], payload["choice_id"]
                        ),
                        "votes": sum(payload["tally"].values()),
                        "turn": payload["turn"],
                        "choice_id": payload["choice_id"],
                    }
                )
        elif event.type == "game.board.updated" and payload.get("by"):
            by = payload["by"]
            facts.pins_by[by] = facts.pins_by.get(by, 0) + len(payload["added"])
        elif event.type == "game.hint" and not payload.get("tie") and event.actor_member_id:
            key = str(event.actor_member_id)
            facts.hints_by[key] = facts.hints_by.get(key, 0) + 1
        elif event.type == "game.completed" and payload.get("ending_id"):
            facts.ending = endings[payload["ending_id"]]

    rows = await session.execute(
        select(RoomMember, User.display_name)
        .join(User, User.id == RoomMember.user_id)
        .where(RoomMember.room_id == game.room_id, RoomMember.role.is_not(None))
        .order_by(RoomMember.joined_at, RoomMember.id)
    )
    roles = {r["id"]: r["name"] for r in content["roles"]}
    facts.players = [
        {
            "user_id": str(m.user_id),
            "display_name": name,
            "roles": [roles[r] for r in (m.role or "").split(",") if r in roles],
        }
        for m, name in rows.all()
    ]
    return facts


async def table_facts(session: AsyncSession, game: GameSession) -> dict[str, Any]:
    """The AI summary's whole input: facts only, display names only, no IDs or clues."""
    facts = await _collect(session, game)
    return {
        "story": facts.story.title,
        "ending": facts.ending["title"] if facts.ending else None,
        "chapters": [{"title": c["title"], "choice": c["choice"]} for c in facts.chapters],
        "counts": {k: v for k, v in facts.team.items() if k != "players"},
        "players": [p["display_name"] for p in facts.players],  # names only, never ids
        "base": _recap(facts.story.title, facts.team, facts.ending),
    }


async def build_summary(session: AsyncSession, game: GameSession, member: RoomMember) -> dict:
    facts = await _collect(session, game)
    me = str(member.id)
    my_votes = {v.turn: v.choice_id for v in facts.votes if str(v.member_id) == me}
    matched = sum(1 for c in facts.chapters if my_votes.get(c["turn"]) == c["choice_id"])
    voted_in = sum(1 for c in facts.chapters if c["turn"] in my_votes)
    theories = sum(
        1
        for e in facts.events
        if e.type == "game.theory.suggestion"
        and str(e.actor_member_id or "") == me
        and e.payload.get("choice_id")
    )
    badges = []
    if facts.pins_by.get(me):
        badges.append({"id": "clue_sharer", "count": facts.pins_by[me]})
    if matched >= CONSENSUS_MIN:
        badges.append({"id": "consensus_builder", "count": matched})
    if theories:
        badges.append({"id": "theory_crafter", "count": theories})

    variant = next(v for v in facts.content["variants"] if v["id"] == game.variant_id)
    pulse = await session.scalar(
        select(PulseResponse.id).where(
            PulseResponse.session_id == game.id, PulseResponse.user_id == member.user_id
        )
    )
    ai_recap = (game.canonical_state.get("ai_text") or {}).get("summary")
    ending = facts.ending
    return {
        "session_id": str(game.id),
        "status": game.status,
        "story": {"title": facts.story.title},
        "ending": {k: ending[k] for k in ("id", "kind", "title", "text")} if ending else None,
        "solution": variant["solution_summary"],
        "chapters": [
            {k: c[k] for k in ("title", "prompt", "choice", "votes")} for c in facts.chapters
        ],
        "team": facts.team,
        "you": {
            "clues_pinned": facts.pins_by.get(me, 0),
            "hints_asked": facts.hints_by.get(me, 0),
            "votes_matched": matched,
            "decisions_voted": voted_in,
            "badges": badges,
        },
        # The AI recap (validated) once it has arrived; the factual one until then.
        "recap": ai_recap or _recap(facts.story.title, facts.team, ending),
        "recap_source": "ai" if ai_recap else "facts",
        "pulse_submitted": pulse is not None,
        "you_user_id": str(member.user_id),
    }


def _recap(title: str, team: dict[str, Any], ending: dict | None) -> str:
    """A plain, factual recap (P11 may rephrase it with AI; the facts stay the same)."""
    people = len(team["players"])
    outcome = ending["title"] if ending else "the case was closed early"
    return (
        f"A table of {people} worked through {team['chapters']} chapters of {title}, "
        f"made {team['decisions']} decisions together, pinned {team['clues_pinned']} "
        f"clue{'s' if team['clues_pinned'] != 1 else ''} to the board and asked for "
        f"{team['hints_used']} hint{'s' if team['hints_used'] != 1 else ''}. Outcome: {outcome}."
    )


async def save_pulse(
    session: AsyncSession, game: GameSession, member: RoomMember, play_again: str, ease: int
) -> None:
    session.add(
        PulseResponse(
            session_id=game.id, user_id=member.user_id, play_again=play_again, ease_of_talking=ease
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(
            409, "PULSE_ALREADY_SENT", "You've already answered for this case."
        ) from None
