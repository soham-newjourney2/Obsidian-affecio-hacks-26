import re
from collections.abc import Callable, Iterator

import pytest
from playwright.sync_api import Browser, Page, expect

from backend.tests.e2e.helpers import signed_in

pytestmark = pytest.mark.e2e

POLL = 10_000  # the lobby polls every 3 s until WebSockets (P07)


@pytest.fixture
def player(browser: Browser, base_url: str) -> Iterator[Callable[[str], Page]]:
    """Factory: each call is a separate person (own browser context and sessionStorage)."""
    contexts = []

    def make(name: str) -> Page:
        context = browser.new_context(base_url=base_url)
        contexts.append(context)
        return signed_in(context.new_page(), name)

    yield make
    for context in contexts:
        context.close()


def create_room(host: Page) -> str:
    host.get_by_role("button", name="Open the case file").click()
    host.get_by_role("button", name="Create a room").click()
    expect(host.locator("#room")).to_be_visible()
    code = host.locator("#invite-code").inner_text()
    assert re.fullmatch(r"[A-Z2-7]{4}-[A-Z2-7]{4}", code)
    return code


def join(page: Page, code: str) -> None:
    page.locator("#join-code").fill(code.lower())
    page.get_by_role("button", name="Join the table").click()
    expect(page.locator("#room")).to_be_visible()


def test_three_players_gather_and_start(player) -> None:
    host, bo, cy = player("Ada"), player("Bo"), player("Cy")
    errors: list[str] = []
    for page in (host, bo, cy):
        page.on("pageerror", lambda exc: errors.append(str(exc)))

    code = create_room(host)
    expect(host.locator("#room-status")).to_have_text("Waiting for at least 3 players.")
    join(bo, code)
    join(cy, code)

    # Guests can't see the code (only its hash is stored); the host's list catches up by polling.
    expect(bo.locator("#invite-unknown")).to_be_visible()
    expect(host.locator("#members > li")).to_have_count(3, timeout=POLL)
    expect(host.locator("#members-title")).to_have_text("At the table (3 of 4)")
    expect(cy.locator("#members > li").filter(has_text="Ada")).to_contain_text("host")

    start = host.get_by_role("button", name="Start the case")
    expect(start).to_be_disabled()
    expect(bo.get_by_role("button", name="Start the case")).to_be_hidden()
    for page in (host, bo, cy):
        page.get_by_role("button", name="I'm ready").click()
        expect(page.locator("#ready-toggle")).to_have_attribute("aria-pressed", "true")

    expect(start).to_be_enabled(timeout=POLL)
    waiting = "Waiting for Ada to start the case."
    expect(bo.locator("#room-status")).to_have_text(waiting, timeout=POLL)
    start.click()
    expect(host.locator("#room-started")).to_be_visible()
    for page in (bo, cy):
        expect(page.locator("#room-started")).to_be_visible(timeout=POLL)
        expect(page.locator("#started-body")).to_contain_text("Ada, Bo, Cy")
    assert errors == []


def test_bad_code_and_leaving(player) -> None:
    host, bo = player("Ada"), player("Bo")
    code = create_room(host)

    bo.locator("#join-code").fill("abc")
    bo.get_by_role("button", name="Join the table").click()
    expect(bo.locator("#join-code-error")).to_have_text("Enter the 8-character code.")
    bo.locator("#join-code").fill("ZZZZ-ZZZZ")
    bo.get_by_role("button", name="Join the table").click()
    invalid = "That invite code is invalid or has expired."
    expect(bo.locator("#join-code-error")).to_have_text(invalid)

    join(bo, code)
    expect(host.locator("#members > li")).to_have_count(2, timeout=POLL)
    bo.get_by_role("button", name="Leave the table").click()
    bo.get_by_role("button", name="Leave", exact=True).click()
    expect(bo.locator("#room")).to_be_hidden()
    expect(bo.locator("#catalogue")).to_be_visible()
    expect(host.locator("#members > li")).to_have_count(1, timeout=POLL)


def test_room_survives_reload(player) -> None:
    host = player("Ada")
    code = create_room(host)
    host.reload()
    expect(host.locator("#room")).to_be_visible()
    expect(host.locator("#invite-code")).to_have_text(code)
