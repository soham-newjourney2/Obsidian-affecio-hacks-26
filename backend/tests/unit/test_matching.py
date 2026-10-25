import pytest

from backend.app.services.matching import (
    WEIGHTS,
    Candidate,
    explain,
    form_group,
    pair_score,
    signals,
)


def cand(uid, interests=(), prefs=(), times=(), roles=(), open_=True) -> Candidate:
    f = frozenset
    return Candidate(uid, f(interests), f(prefs), f(times), f(roles), open_)


A = cand("a", ["books", "puzzles", "film"], ["mystery"], ["weekend_evenings"], ["listener"])


def test_identical_profiles_score_high_and_disjoint_low() -> None:
    same = cand("b", ["books", "puzzles", "film"], ["mystery"], ["weekend_evenings"], ["archivist"])
    other = cand(
        "c", ["sport", "travel", "cooking"], ["fantasy"], ["weekday_mornings"], ["listener"]
    )
    assert pair_score(A, same) == pytest.approx(1.0)
    assert pair_score(A, other) == pytest.approx(0.0)


def test_missing_signals_are_renormalized_not_penalized() -> None:
    # B shares A's interests fully but filled in nothing else.
    b = cand("b", ["books", "puzzles", "film"])
    assert signals(A, b)["availability"] is None and signals(A, b)["roles"] is None
    assert pair_score(A, b) == pytest.approx(1.0)  # only interests count, weight renormalized
    half = cand("b", ["books", "puzzles", "film"], times=["weekday_mornings"])
    expected = (WEIGHTS["interests"] * 1 + WEIGHTS["availability"] * 0) / (
        WEIGHTS["interests"] + WEIGHTS["availability"]
    )
    assert pair_score(A, half) == pytest.approx(expected)


def test_roles_complement() -> None:
    assert signals(A, cand("b", roles=["archivist"]))["roles"] == 1.0
    assert signals(A, cand("b", roles=["listener"]))["roles"] == 0.0


def test_greedy_group_prefers_the_best_fits() -> None:
    fits = [cand(x, ["books", "puzzles", "film"], times=["weekend_evenings"]) for x in "bcd"]
    misfit = cand("z", ["sport"], times=["weekday_mornings"])
    group = form_group([A, misfit, *fits])
    assert {c.user_id for c in group} == {"a", "b", "c", "d"}


def test_blocked_pairs_are_never_grouped() -> None:
    people = [A] + [cand(x, ["books"]) for x in "bcde"]  # 4 people would leave no legal trio
    blocked = {frozenset(("a", "b")), frozenset(("c", "d"))}
    group = form_group(people, blocked)
    ids = {c.user_id for c in group}
    assert len(ids) >= 3
    for pair in blocked:
        assert not pair <= ids
    assert (
        form_group(
            people[:3], {frozenset(("a", "b")), frozenset(("a", "c")), frozenset(("b", "c"))}
        )
        is None
    )


def test_needs_three() -> None:
    assert form_group([A, cand("b")]) is None


def test_explanations_are_labels_never_numbers() -> None:
    b = cand("b", ["books", "puzzles"], times=["weekend_evenings"], roles=["archivist"])
    text = " | ".join(explain(A, [A, b, cand("c", roles=["strategist"])]))
    assert "Shared interests: Books, Puzzles & riddles" in text
    assert "Often free at the same time: Weekend evenings" in text
    assert "complement" in text
    assert "%" not in text and not any(ch.isdigit() for ch in text)


def test_private_profiles_reveal_nothing() -> None:
    private = cand("b", ["books", "puzzles"], times=["weekend_evenings"], open_=False)
    text = " ".join(explain(A, [A, private]))
    assert "Books" not in text and "Weekend" not in text  # their interests stay private
    assert " ".join(explain(private, [private, A])) == "A good mix of people for this case"
