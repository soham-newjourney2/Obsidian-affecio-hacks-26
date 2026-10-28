"""Story file schema (Pydantic, extra='forbid') and the structural validator.

A story JSON holds catalogue metadata and rights for every story; playable stories also
carry `content`: roles, variants, scenes, clues, decisions, hints and endings. The graph
is: scene --decision choice (per variant)--> scene | ending, or scene --next--> node.
"""

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.content.profile_options import ids as option_ids

Id = str  # snake_case; declared ids are checked against ID_PATTERN
ID_PATTERN = r"^[a-z][a-z0-9_]{0,39}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rights(Strict):
    inspiration_title: str
    inspiration_author: str
    author_death_year: int
    publication_year: int
    original_language: str
    source_url: str = Field(pattern=r"^https://")
    status: Literal["review_required", "verified_public_domain", "excluded"]
    notes: str
    reviewed_at: date


class Role(Strict):
    id: Id = Field(pattern=ID_PATTERN)
    name: str
    focus: str


class Variant(Strict):
    id: Id = Field(pattern=ID_PATTERN)
    solution_summary: str


class Scene(Strict):
    id: Id = Field(pattern=ID_PATTERN)
    title: str
    narration_base: str = Field(max_length=900)
    objective: str
    reveals: list[Id] = Field(default_factory=list)
    decision_id: Id | None = None
    next: Id | None = None  # auto-advance target when the scene has no decision


class Clue(Strict):
    id: Id = Field(pattern=ID_PATTERN)
    text: str = Field(max_length=400)
    # Variant-specific wording; falls back to `text`.
    text_by_variant: dict[Id, str] = Field(default_factory=dict)
    owner_role: Id  # a role id, or "public"
    # The clue appears in a variant only if that variant is a key here.
    meaning_by_variant: dict[Id, Literal["true", "red_herring"]]


class Choice(Strict):
    id: Id = Field(pattern=ID_PATTERN)
    label: str
    next_by_variant: dict[Id, Id]


class Decision(Strict):
    id: Id = Field(pattern=ID_PATTERN)
    prompt: str
    choices: list[Choice] = Field(min_length=2)


class Hint(Strict):
    scene_id: Id
    levels: list[str] = Field(min_length=3, max_length=3)


class Ending(Strict):
    id: Id = Field(pattern=ID_PATTERN)
    kind: Literal["success", "partial", "safe"]
    title: str
    text: str


class StoryContent(Strict):
    premise: str
    roles: list[Role] = Field(min_length=3, max_length=4)
    optional_role: Id | None = None  # the 4th seat; its clues move to others with 3 players
    redistribution: dict[Id, Id] = Field(default_factory=dict)  # clue id -> role id
    variants: list[Variant] = Field(min_length=1)
    start_scene: Id
    scenes: list[Scene] = Field(min_length=1)
    clues: list[Clue]
    decisions: list[Decision]
    hints: list[Hint]
    endings: list[Ending]
    safety_notes: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _structure(self) -> Self:
        errors = validate_content(self)
        if errors:
            raise ValueError("; ".join(errors))
        return self


class StoryFile(Strict):
    story_id: Id = Field(pattern=ID_PATTERN)
    version: int = Field(ge=1)
    title: str = Field(max_length=80)
    description: str = Field(max_length=280)
    genres: list[str] = Field(min_length=1)
    min_players: int = Field(default=3, ge=2, le=4)
    max_players: int = Field(default=4, ge=2, le=4)
    est_minutes: int | None = Field(default=None, ge=5, le=120)  # unknown until playable
    playable: bool
    rights: Rights
    content: StoryContent | None = None

    @model_validator(mode="after")
    def _catalogue_rules(self) -> Self:
        unknown = set(self.genres) - option_ids("genres")
        if unknown:
            raise ValueError(f"unknown genres: {sorted(unknown)}")
        if self.min_players > self.max_players:
            raise ValueError("min_players exceeds max_players")
        if self.playable:
            if self.content is None:
                raise ValueError("a playable story needs content")
            if self.rights.status != "verified_public_domain":
                raise ValueError("only verified public-domain stories can be playable")
            if self.est_minutes is None:
                raise ValueError("a playable story needs est_minutes")
            if len(self.content.roles) != self.max_players:
                raise ValueError("roles must match max_players")
        return self


def validate_content(c: StoryContent) -> list[str]:
    """Returns every structural problem found (empty list means valid)."""
    errors: list[str] = []
    role_ids = [r.id for r in c.roles]
    variant_ids = [v.id for v in c.variants]
    scenes = {s.id: s for s in c.scenes}
    endings = {e.id: e for e in c.endings}
    decisions = {d.id: d for d in c.decisions}
    clues = {cl.id: cl for cl in c.clues}

    # Unique ids (scenes and endings share one node namespace).
    for label, items in (
        ("role", role_ids),
        ("variant", variant_ids),
        ("node", [s.id for s in c.scenes] + [e.id for e in c.endings]),
        ("decision", [d.id for d in c.decisions]),
        ("clue", [cl.id for cl in c.clues]),
    ):
        duplicates = sorted({i for i in items if items.count(i) > 1})
        if duplicates:
            errors.append(f"duplicate {label} ids: {duplicates}")
    if errors:
        return errors

    nodes = set(scenes) | set(endings)
    if c.start_scene not in scenes:
        errors.append(f"start_scene {c.start_scene!r} is not a scene")
    if not any(e.kind == "success" for e in c.endings):
        errors.append("no success ending")

    # References.
    for scene in c.scenes:
        if scene.decision_id and scene.decision_id not in decisions:
            errors.append(f"scene {scene.id}: unknown decision {scene.decision_id!r}")
        if scene.decision_id and scene.next:
            errors.append(f"scene {scene.id}: has both a decision and next")
        if not scene.decision_id and not scene.next:
            errors.append(f"scene {scene.id}: dead end (no decision and no next)")
        if scene.next and scene.next not in nodes:
            errors.append(f"scene {scene.id}: next {scene.next!r} is not a node")
        for clue_id in scene.reveals:
            if clue_id not in clues:
                errors.append(f"scene {scene.id}: reveals unknown clue {clue_id!r}")
    used_decisions = [s.decision_id for s in c.scenes if s.decision_id]
    for decision in c.decisions:
        if decision.id not in used_decisions:
            errors.append(f"decision {decision.id}: not used by any scene")
        elif used_decisions.count(decision.id) > 1:
            errors.append(f"decision {decision.id}: used by more than one scene")
        for choice in decision.choices:
            missing = set(variant_ids) - set(choice.next_by_variant)
            if missing:
                errors.append(f"choice {choice.id}: no target for variants {sorted(missing)}")
            for variant, target in choice.next_by_variant.items():
                if variant not in variant_ids:
                    errors.append(f"choice {choice.id}: unknown variant {variant!r}")
                if target not in nodes:
                    errors.append(f"choice {choice.id}: target {target!r} is not a node")
    for clue in c.clues:
        if clue.owner_role != "public" and clue.owner_role not in role_ids:
            errors.append(f"clue {clue.id}: unknown owner {clue.owner_role!r}")
        for variant in set(clue.meaning_by_variant) | set(clue.text_by_variant):
            if variant not in variant_ids:
                errors.append(f"clue {clue.id}: unknown variant {variant!r}")
    revealed = [cid for s in c.scenes for cid in s.reveals]
    for clue_id in clues:
        if revealed.count(clue_id) != 1:
            errors.append(f"clue {clue_id}: must be revealed in exactly one scene")
    hinted = [h.scene_id for h in c.hints]
    for scene_id in scenes:
        if hinted.count(scene_id) != 1:
            errors.append(f"scene {scene_id}: needs exactly one hint set")
    for scene_id in set(hinted) - set(scenes):
        errors.append(f"hints for unknown scene {scene_id!r}")
    if errors:
        return errors

    # Graph rules, per variant.
    def edges(node: Id, variant: Id) -> list[Id]:
        scene = scenes.get(node)
        if scene is None:
            return []
        if scene.next:
            return [scene.next]
        return [ch.next_by_variant[variant] for ch in decisions[scene.decision_id].choices]

    reachable_any: set[Id] = set()
    for variant in variant_ids:
        seen: set[Id] = set()
        stack = [c.start_scene]
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                stack.extend(edges(node, variant))
        reachable_any |= seen
        if not any(endings[n].kind == "success" for n in seen if n in endings):
            errors.append(f"variant {variant}: no path to a success ending")
        if _has_cycle(c.start_scene, lambda n, v=variant: edges(n, v)):
            errors.append(f"variant {variant}: the story graph has a cycle")
    for node in sorted(nodes - reachable_any):
        errors.append(f"node {node}: unreachable")

    # Every role must hold at least one private clue in every variant.
    for variant in variant_ids:
        for role in role_ids:
            if not any(
                cl.owner_role == role and variant in cl.meaning_by_variant for cl in c.clues
            ):
                errors.append(f"role {role}: no private clue in variant {variant}")

    # 3-player redistribution must keep every clue of the optional role.
    if c.optional_role is not None:
        if c.optional_role not in role_ids:
            errors.append(f"optional_role {c.optional_role!r} is not a role")
        dropped = [
            cl.id
            for cl in c.clues
            if cl.owner_role == c.optional_role and cl.id not in c.redistribution
        ]
        if dropped:
            errors.append(f"3-player redistribution drops clues: {dropped}")
        for clue_id, role in c.redistribution.items():
            if clue_id not in clues or clues[clue_id].owner_role != c.optional_role:
                errors.append(f"redistribution: {clue_id!r} is not an optional-role clue")
            if role not in role_ids or role == c.optional_role:
                errors.append(f"redistribution: {clue_id!r} must go to a core role")
    elif c.redistribution:
        errors.append("redistribution given without an optional_role")
    return errors


def _has_cycle(start: Id, edges) -> bool:
    visiting: set[Id] = set()
    done: set[Id] = set()

    def visit(node: Id) -> bool:
        if node in visiting:
            return True
        if node in done:
            return False
        visiting.add(node)
        cyclic = any(visit(n) for n in edges(node))
        visiting.discard(node)
        done.add(node)
        return cyclic

    return visit(start)
