import re

import pytest
from playwright.sync_api import Page, expect

from backend.tests.e2e.helpers import create_user, sign_in

pytestmark = pytest.mark.e2e


@pytest.fixture
def lobby(page: Page) -> Page:
    email = create_user(page.request, with_profile=True)
    page.goto("/auth.html")
    sign_in(page, email)
    expect(page).to_have_url(re.compile(r"/lobby\.html$"))
    return page


def test_catalogue_shows_one_playable_and_four_coming_soon(
    lobby: Page, console_errors: list[str]
) -> None:
    cards = lobby.locator("#catalogue > li")
    expect(cards).to_have_count(5)
    first = cards.first
    expect(first).to_have_attribute("data-slug", "blackthorn_manor")
    expect(first.locator(".game-status")).to_have_text("Case No. 1")
    expect(first).to_contain_text("3–4 players")
    expect(first).to_contain_text("About 30 minutes")
    expect(first).to_contain_text("Inspired by The Adventure of the Speckled Band")
    expect(first.get_by_role("link", name="Find a table")).to_have_attribute(
        "href", "/room.html?story=blackthorn_manor#find-panel"
    )
    soon = lobby.locator(".game-card--coming-soon")
    expect(soon).to_have_count(4)
    for card in soon.all():
        expect(card.locator(".game-status")).to_have_text("Coming soon")
        expect(card.get_by_role("button")).to_have_count(0)  # nothing to click that does nothing
        expect(card).not_to_contain_text("minutes")  # no invented play times
    text = lobby.locator("#catalogue").inner_text()
    assert not re.search(r"\d+\s*%|match", text, re.I)
    assert console_errors == []


def test_open_case_file_dialog(lobby: Page) -> None:
    lobby.get_by_role("button", name="Open the case file").click()
    dialog = lobby.locator("#story-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("#story-title")).to_have_text("Blackthorn Manor")
    expect(dialog.locator("#story-premise")).to_contain_text("Elinor")
    expect(dialog.locator(".story-modal__role")).to_have_count(4)
    source = dialog.locator("#story-source")
    expect(source).to_have_attribute("href", "https://www.gutenberg.org/ebooks/1661")
    expect(source).to_have_attribute("rel", "noopener noreferrer")
    lobby.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    lobby.get_by_role("button", name="Open the case file").click()
    lobby.locator("#story-dialog").get_by_role("button", name="Close").click()
    expect(lobby.locator("#story-dialog")).to_have_count(0)


def test_tagore_story_links_bengali_original(lobby: Page) -> None:
    card = lobby.locator('[data-slug="hungry_stones"]')
    expect(card).to_contain_text("Rabindranath Tagore (1895)")
    link = card.get_by_role("link", name="Read the original (Bengali)")
    expect(link).to_have_attribute("rel", "noopener noreferrer")


def test_search_filters_cards(lobby: Page) -> None:
    lobby.locator("#search input").fill("blackthorn")
    expect(lobby.locator("#catalogue > li:visible")).to_have_count(1)
    lobby.locator("#search input").fill("zzz-nothing")
    expect(lobby.locator("#search-empty")).to_be_visible()
