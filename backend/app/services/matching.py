"""Pure matching: pair scores, group formation and plain-language explanations.

Scores stay internal: players only ever see explanation labels, never a number or a percentage.
Signals a person left empty are skipped and the remaining weights renormalized. Shared interests
are only named when both people chose "match only" visibility; private profiles reveal nothing.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import combinations

from backend.app.content import profile_options as opts

# Weights (config): interests .50, story+activity prefs .25, availability .15, roles .10.
WEIGHTS = {"interests": 0.50, "prefs": 0.25, "availability": 0.15, "roles": 0.10}
GROUP_MIN, GROUP_MAX = 3, 4


@dataclass(frozen=True)
class Candidate:
    user_id: str
    interests: frozenset[str] = field(default_factory=frozenset)
    prefs: frozenset[str] = field(default_factory=frozenset)  # genres + activities
    availability: frozenset[str] = field(default_factory=frozenset)
    roles: frozenset[str] = field(default_factory=frozenset)
    shares_profile: bool = False  # visibility == "match_only"


def _overlap(a: frozenset[str], b: frozenset[str]) -> float | None:
    if not a or not b:
        return None  # missing signal: skipped, not counted as a mismatch
    return len(a & b) / len(a | b)


def signals(a: Candidate, b: Candidate) -> dict[str, float | None]:
    roles = _overlap(a.roles, b.roles)
    return {
        "interests": _overlap(a.interests, b.interests),
        "prefs": _overlap(a.prefs, b.prefs),
        "availability": _overlap(a.availability, b.availability),
        "roles": None if roles is None else 1 - roles,  # different roles complement each other
    }


def pair_score(a: Candidate, b: Candidate) -> float:
    present = {k: v for k, v in signals(a, b).items() if v is not None}
    if not present:
        return 0.0
    total = sum(WEIGHTS[k] for k in present)
    return sum(WEIGHTS[k] * v for k, v in present.items()) / total


def group_score(group: list[Candidate]) -> float:
    pairs = list(combinations(group, 2))
    return sum(pair_score(a, b) for a, b in pairs) / len(pairs) if pairs else 0.0


def form_group(
    waiting: list[Candidate], blocked: Iterable[frozenset[str]] = ()
) -> list[Candidate] | None:
    """Greedy best group around the longest-waiting person (`waiting` is in queue order).
    Never puts a blocked pair together. Returns 3–4 people, or None."""
    blocked = set(blocked)
    for seed in waiting:
        group = [seed]
        pool = [c for c in waiting if c is not seed]
        while len(group) < GROUP_MAX:
            options = [
                c
                for c in pool
                if all(frozenset((c.user_id, g.user_id)) not in blocked for g in group)
            ]
            if not options:
                break
            best = max(options, key=lambda c: (group_score([*group, c]), -pool.index(c)))
            group.append(best)
            pool.remove(best)
        if len(group) >= GROUP_MIN:
            return group
    return None


def _labels(field_name: str, ids: Iterable[str]) -> list[str]:
    names = dict(opts.OPTIONS[field_name])
    return [names[i].split(" — ")[0] for i in sorted(ids) if i in names]


def explain(viewer: Candidate, group: list[Candidate]) -> list[str]:
    """Plain labels for why this table fits the viewer. No numbers, no inferences."""
    others = [c for c in group if c.user_id != viewer.user_id]
    out: list[str] = []
    if viewer.shares_profile:
        open_others = [c for c in others if c.shares_profile]
        shared = set().union(*(viewer.interests & c.interests for c in open_others))
        if shared:
            out.append("Shared interests: " + ", ".join(_labels("interests", shared)[:3]))
        times = set().union(*(viewer.availability & c.availability for c in open_others))
        if times:
            out.append(
                "Often free at the same time: " + ", ".join(_labels("availability", times)[:2])
            )
    if viewer.roles and all(not (viewer.roles & c.roles) for c in others if c.roles):
        out.append("Your preferred roles complement the table")
    return out or ["A good mix of people for this case"]
