import copy
import json
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from backend.app.game.story_schema import StoryContent, StoryFile
from backend.app.services.stories import STORIES_DIR, load_story_files

RIGHTS = {
    "inspiration_title": "Original",
    "inspiration_author": "Author",
    "author_death_year": 1900,
    "publication_year": 1890,
    "original_language": "English",
    "source_url": "https://example.org/original",
    "status": "verified_public_domain",
    "notes": "test",
    "reviewed_at": "2026-10-23",
}


def minimal_content() -> dict:
    """Smallest valid story: 4 roles (one optional), 2 variants, 2 scenes, 2 endings."""
    both = {"v1": "true", "v2": "true"}
    return {
        "premise": "p",
        "roles": [{"id": r, "name": r, "focus": "f"} for r in ("a", "b", "c", "d")],
        "optional_role": "d",
        "redistribution": {"k_d": "a"},
        "variants": [
            {"id": "v1", "solution_summary": "s1"},
            {"id": "v2", "solution_summary": "s2"},
        ],
        "start_scene": "s1",
        "scenes": [
            {
                "id": "s1",
                "title": "t",
                "narration_base": "n",
                "objective": "o",
                "reveals": ["k_pub", "k_a"],
                "next": "s2",
            },
            {
                "id": "s2",
                "title": "t",
                "narration_base": "n",
                "objective": "o",
                "reveals": ["k_b", "k_c", "k_d"],
                "decision_id": "d1",
            },
        ],
        "clues": [
            {"id": "k_pub", "text": "x", "owner_role": "public", "meaning_by_variant": both},
            {"id": "k_a", "text": "x", "owner_role": "a", "meaning_by_variant": both},
            {"id": "k_b", "text": "x", "owner_role": "b", "meaning_by_variant": both},
            {"id": "k_c", "text": "x", "owner_role": "c", "meaning_by_variant": both},
            {"id": "k_d", "text": "x", "owner_role": "d", "meaning_by_variant": both},
        ],
        "decisions": [
            {
                "id": "d1",
                "prompt": "?",
                "choices": [
                    {
                        "id": "x1",
                        "label": "one",
                        "next_by_variant": {"v1": "e_win", "v2": "e_safe"},
                    },
                    {
                        "id": "x2",
                        "label": "two",
                        "next_by_variant": {"v1": "e_safe", "v2": "e_win"},
                    },
                ],
            },
        ],
        "hints": [{"scene_id": s, "levels": ["1", "2", "3"]} for s in ("s1", "s2")],
        "endings": [
            {"id": "e_win", "kind": "success", "title": "t", "text": "x"},
            {"id": "e_safe", "kind": "safe", "title": "t", "text": "x"},
        ],
        "safety_notes": ["none"],
    }


def errors_for(mutate: Callable[[dict], None]) -> str:
    content = minimal_content()
    mutate(content)
    with pytest.raises(ValidationError) as exc:
        StoryContent.model_validate(content)
    return str(exc.value)


def test_minimal_story_is_valid() -> None:
    StoryContent.model_validate(minimal_content())


def _unreachable_scene(c: dict) -> None:
    c["scenes"].append(
        {
            "id": "s3",
            "title": "t",
            "narration_base": "n",
            "objective": "o",
            "reveals": [],
            "next": "e_safe",
        }
    )
    c["hints"].append({"scene_id": "s3", "levels": ["1", "2", "3"]})


def _dead_end(c: dict) -> None:
    del c["scenes"][0]["next"]


def _no_success_for_v2(c: dict) -> None:
    for choice in c["decisions"][0]["choices"]:
        choice["next_by_variant"]["v2"] = "e_safe"


def _role_without_clue_in_v2(c: dict) -> None:
    c["clues"][2]["meaning_by_variant"] = {"v1": "true"}  # k_b missing from v2


def _redistribution_drops(c: dict) -> None:
    c["redistribution"] = {}


def _redistribution_to_optional(c: dict) -> None:
    c["redistribution"] = {"k_d": "d"}


def _cycle(c: dict) -> None:
    c["decisions"][0]["choices"][0]["next_by_variant"]["v2"] = "s1"


def _choice_missing_variant(c: dict) -> None:
    del c["decisions"][0]["choices"][0]["next_by_variant"]["v2"]


def _unknown_target(c: dict) -> None:
    c["decisions"][0]["choices"][0]["next_by_variant"]["v1"] = "nowhere"


def _clue_never_revealed(c: dict) -> None:
    c["scenes"][0]["reveals"].remove("k_pub")


def _clue_revealed_twice(c: dict) -> None:
    c["scenes"][1]["reveals"].append("k_pub")


def _scene_without_hints(c: dict) -> None:
    c["hints"].pop()


def _duplicate_node_ids(c: dict) -> None:
    c["endings"][1]["id"] = "s1"


def _unknown_owner(c: dict) -> None:
    c["clues"][1]["owner_role"] = "ghost"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (_unreachable_scene, "node s3: unreachable"),
        (_dead_end, "dead end"),
        (_no_success_for_v2, "variant v2: no path to a success ending"),
        (_role_without_clue_in_v2, "role b: no private clue in variant v2"),
        (_redistribution_drops, "redistribution drops clues: ['k_d']"),
        (_redistribution_to_optional, "must go to a core role"),
        (_cycle, "has a cycle"),
        (_choice_missing_variant, "no target for variants ['v2']"),
        (_unknown_target, "is not a node"),
        (_clue_never_revealed, "k_pub: must be revealed in exactly one scene"),
        (_clue_revealed_twice, "k_pub: must be revealed in exactly one scene"),
        (_scene_without_hints, "needs exactly one hint set"),
        (_duplicate_node_ids, "duplicate node ids"),
        (_unknown_owner, "unknown owner"),
    ],
)
def test_validator_rejects(mutate: Callable[[dict], None], message: str) -> None:
    assert message in errors_for(mutate)


def test_hints_need_three_levels() -> None:
    assert "levels" in errors_for(lambda c: c["hints"][0].update(levels=["1", "2"]))


def test_unknown_fields_rejected() -> None:
    assert "extra" in errors_for(lambda c: c["scenes"][0].update(secret=True)).lower()


def _story(**overrides) -> dict:
    return {
        "story_id": "test_story",
        "version": 1,
        "title": "T",
        "description": "D",
        "genres": ["mystery"],
        "est_minutes": 20,
        "playable": True,
        "rights": dict(RIGHTS),
        "content": minimal_content(),
        **overrides,
    }


def test_playable_story_needs_verified_rights() -> None:
    with pytest.raises(ValidationError, match="verified public-domain"):
        StoryFile.model_validate(_story(rights={**RIGHTS, "status": "review_required"}))


def test_playable_story_needs_content() -> None:
    with pytest.raises(ValidationError, match="needs content"):
        StoryFile.model_validate(_story(content=None))


def test_unknown_genre_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown genres"):
        StoryFile.model_validate(_story(genres=["romance"]))


def test_stub_story_is_valid_without_content() -> None:
    StoryFile.model_validate(_story(playable=False, content=None, est_minutes=None))


# --- the shipped catalogue -------------------------------------------------------------


def test_catalogue_files_are_valid() -> None:
    stories = {s.story_id: s for s in load_story_files()}
    assert set(stories) == {
        "blackthorn_manor",
        "rue_morgue",
        "time_machine",
        "wizard_of_oz",
        "hungry_stones",
    }
    assert [s.story_id for s in stories.values() if s.playable] == ["blackthorn_manor"]
    for story in stories.values():
        assert story.rights.source_url.startswith("https://")
        assert "Sherlock" not in json.dumps(story.model_dump(mode="json"))


def test_blackthorn_manor_shape() -> None:
    story = next(s for s in load_story_files() if s.story_id == "blackthorn_manor")
    c = story.content
    assert len(c.variants) == 3
    assert len(c.scenes) == 4
    assert 9 <= len(c.clues) <= 12
    assert len(c.decisions) == 3
    assert sorted(e.kind for e in c.endings) == ["partial", "safe", "success"]
    assert [r.id for r in c.roles] == ["investigator", "archivist", "listener", "strategist"]


def test_blackthorn_final_plan_has_one_right_answer_per_variant() -> None:
    story = next(s for s in load_story_files() if s.story_id == "blackthorn_manor")
    c = story.content
    endings = {e.id: e.kind for e in c.endings}
    final = next(d for d in c.decisions if d.id == "d3_plan")
    winners = {
        v.id: [ch.id for ch in final.choices if endings[ch.next_by_variant[v.id]] == "success"]
        for v in c.variants
    }
    assert all(len(w) == 1 for w in winners.values())
    assert len({w[0] for w in winners.values()}) == 3  # each variant needs a different plan
    # A safe retreat is always available.
    always_safe = [
        ch for ch in final.choices if all(endings[t] == "safe" for t in ch.next_by_variant.values())
    ]
    assert len(always_safe) == 1


def test_blackthorn_clues_differ_between_variants() -> None:
    """Replays must be deducible: enough clue wording changes with the variant."""
    story = next(s for s in load_story_files() if s.story_id == "blackthorn_manor")
    varying = [cl for cl in story.content.clues if cl.text_by_variant]
    assert len(varying) >= 6


def test_story_id_must_match_file_name(tmp_path) -> None:
    source = json.loads((STORIES_DIR / "rue_morgue.json").read_text(encoding="utf-8"))
    (tmp_path / "other_name.json").write_text(json.dumps(copy.deepcopy(source)), encoding="utf-8")
    with pytest.raises(ValueError, match="must match file name"):
        load_story_files(tmp_path)
