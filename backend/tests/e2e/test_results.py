"""results.html: the ending, the table's recap, a private reflection and the 2-question pulse."""

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
)

pytestmark = pytest.mark.e2e


def first_clue_holder(pages) -> Page:
    """Roles are random; with 3 players the Investigator has no clue in chapter 1."""
    for page in pages:
        if page.locator("#private-clues > li").count():
            return page
    raise AssertionError("nobody holds a clue")


def test_results_flow(person) -> None:
    ada, bo, cy = begin_case(person)
    players = (ada, bo, cy)
    for page in players:
        expect(page.locator("#private-clues > li, #private-empty:visible").first).to_be_visible()
    sharer = first_clue_holder(players)
    sharer.locator("#private-clues > li").first.get_by_role("button", name="Pin to board").click()
    expect(ada.locator("#board > li")).to_have_count(2, timeout=LIVE)

    all_vote(players, D1_ROOM)
    chapter_is(players, 3, "The Room")
    all_vote(players, D2_ANY)
    chapter_is(players, 4, "The Vigil")
    all_vote(players, D3_SAFE)
    for page in players:
        expect(page.locator("#ending")).to_be_visible(timeout=LIVE)

    sharer.get_by_role("link", name="See your results").click()
    expect(sharer).to_have_url(re.compile(r"/results\.html\?session="))
    expect(sharer.locator("#results-stamp")).to_have_text("Safe retreat")
    expect(sharer.locator("#ending-title")).to_have_text("A safe retreat")
    expect(sharer.locator("#solution")).not_to_be_empty()
    expect(sharer.locator("#chapters > li")).to_have_count(3)
    expect(sharer.locator("#team-stats")).to_contain_text("Clues pinned1")
    expect(sharer.locator("#players > li")).to_have_count(3)
    expect(sharer.locator("#badges")).to_contain_text("Clue Sharer")
    expect(sharer.locator("#badges")).to_contain_text("Consensus Builder")
    text = sharer.locator("#results").inner_text()
    assert not re.search(r"\d+\s*%|rank|score|personality", text, re.I)  # no scores or labels

    sharer.locator("#play-again").get_by_text("Yes").click()
    sharer.get_by_role("button", name="Send").click()
    expect(sharer.locator("#pulse-form .form-error")).to_have_text("Please answer both questions.")
    sharer.locator("#ease").get_by_text("4", exact=True).click()
    sharer.get_by_role("button", name="Send").click()
    expect(sharer.locator("#pulse-thanks")).to_be_visible()
    sharer.reload()
    expect(sharer.locator("#pulse-thanks")).to_be_visible()  # one pulse per person
    expect(sharer.locator("#pulse-form")).to_be_hidden()

    other = next(p for p in players if p is not sharer)
    other.get_by_role("link", name="See your results").click()
    expect(other.locator("#badges")).not_to_contain_text("Clue Sharer")  # badges are personal
    expect(other.locator("#pulse-form")).to_be_visible()
    for page in players:
        assert page.errors == [], page.errors


def test_results_before_the_end(person) -> None:
    ada, bo, cy = begin_case(person)
    session = ada.evaluate("JSON.parse(sessionStorage.getItem('echo.room')).id")
    href = ada.locator("#results-link").get_attribute("href")
    assert href.startswith("/results.html?session=") and session
    ada.goto(href)
    expect(ada.locator("#still-playing")).to_be_visible()
    ada.get_by_role("link", name="Back to the table").click()
    expect(ada.locator("#table")).to_have_attribute("data-mode", "game", timeout=LIVE)
