"""The story room (room.html in game mode): three players play Blackthorn Manor end to end."""

import re

import pytest
from playwright.sync_api import Page, expect

from backend.tests.e2e.helpers import (
    D1_ROOM,
    D2_ANY,
    D3_SAFE,
    LIVE,
    all_vote,
    begin_case,
    chapter_is,
    vote,
)

pytestmark = pytest.mark.e2e


def private_clues(page: Page) -> dict[str, str]:
    items = page.locator("#private-clues > li")
    return {
        items.nth(i).get_attribute("data-clue"): items.nth(i)
        .locator(".game-clue__text")
        .inner_text()
        for i in range(items.count())
    }


def test_three_players_finish_blackthorn_manor(person) -> None:
    ada, bo, cy = begin_case(person)
    players = (ada, bo, cy)
    roles = {p.locator(".game-role__name").first.inner_text() for p in players}
    assert len(roles) == 3  # one distinct role each (3 players: the Strategist's clues move)
    expect(ada.locator("#board > li")).to_have_count(1)  # the public whistle clue

    all_vote(players, D1_ROOM)
    chapter_is(players, 3, "The Room")

    ada.locator("#hint-request").click()
    for page in players:
        expect(page.locator("#hints > li")).to_have_count(1, timeout=LIVE)
        expect(page.locator("#hint-request")).to_have_text("Ask for a hint (2 left)")

    pin = ada.locator("#private-clues > li").first
    clue_id = pin.get_attribute("data-clue")
    clue_text = pin.locator(".game-clue__text").inner_text()
    pin.get_by_role("button", name="Pin to board").click()
    pinned = bo.locator(f'#board > li[data-clue="{clue_id}"]')
    expect(pinned).to_contain_text(clue_text, timeout=LIVE)
    expect(pinned).to_contain_text("Pinned by Ada")
    expect(ada.locator(f'#private-clues > li[data-clue="{clue_id}"]')).to_contain_text("Shared")
    expect(bo.locator("#board-strings path")).to_have_count(1)  # red string between 2 pins

    all_vote(players, D2_ANY)
    chapter_is(players, 4, "The Vigil")
    all_vote(players, D3_SAFE)
    for page in players:
        expect(page.locator("#ending")).to_be_visible(timeout=LIVE)
        expect(page.locator("#ending-stamp")).to_have_text("Safe retreat")
        expect(page.locator("#ending-title")).to_have_text("A safe retreat")
        expect(page.locator("#ending-solution")).not_to_be_empty()
        expect(page.locator("#decision")).to_be_hidden()
    for page in players:
        assert page.errors == [], page.errors


def test_each_player_holds_only_their_own_private_clues(person) -> None:
    ada, bo, cy = begin_case(person)
    players = {"ada": ada, "bo": bo, "cy": cy}
    all_vote(players.values(), D1_ROOM)  # reveal the room's clues as well
    chapter_is(players.values(), 3, "The Room")
    for page in players.values():
        expect(page.locator("#private-clues > li").first).to_be_visible()
    held = {name: private_clues(page) for name, page in players.items()}
    for name, page in players.items():
        body = page.locator("body").inner_text()
        frames = "".join(page.ws_frames)
        for other, clues in held.items():
            if other == name:
                continue
            for clue_id, text in clues.items():
                assert text not in body, (name, "DOM", other, clue_id)
                assert f'"{clue_id}"' not in frames, (name, "WS", other, clue_id)


def test_refresh_mid_vote_keeps_the_vote_without_duplicating_it(person) -> None:
    ada, bo, cy = begin_case(person)
    vote(bo, D1_ROOM)
    expect(ada.locator("#decision-status")).to_contain_text("1 of 3 voted", timeout=LIVE)

    bo.reload()
    expect(bo.locator("#table")).to_have_attribute("data-mode", "game", timeout=LIVE)
    mine = bo.locator("#choices").get_by_role("button", name=re.compile(re.escape(D1_ROOM)))
    expect(mine).to_have_attribute("aria-pressed", "true")
    expect(mine).to_contain_text("1 vote(s)")
    expect(bo.locator("#decision-status")).to_contain_text("1 of 3 voted")
    expect(ada.locator("#decision-status")).to_contain_text("1 of 3 voted")  # still one vote

    vote(ada, D1_ROOM)
    vote(cy, D1_ROOM)
    chapter_is((ada, bo, cy), 3, "The Room")


def test_reconnect_overlay(person) -> None:
    ada, bo, cy = begin_case(person)
    bo.context.set_offline(True)
    expect(bo.locator("#reconnect")).to_be_visible(timeout=LIVE)
    bo.context.set_offline(False)
    expect(bo.locator("#reconnect")).to_be_hidden(timeout=20_000)
    expect(bo.locator("#conn-text")).to_have_text("Live")
    expect(bo.locator("#chapter-label")).to_have_text("Chapter 1 of 4")  # resynced, same place
