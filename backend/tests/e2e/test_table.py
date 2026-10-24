"""room.html: start/join a table and talk live over WebSocket (3 browser contexts)."""

import pytest
from playwright.sync_api import expect

from backend.tests.e2e.helpers import LIVE, join_table, say, start_table

pytestmark = pytest.mark.e2e


def test_three_people_gather_and_talk_live(person) -> None:
    ada, bo, cy = person("Ada"), person("Bo"), person("Cy")
    code = start_table(ada)
    join_table(bo, code)
    join_table(cy, code)

    for page in (ada, bo, cy):
        expect(page.locator("#members > li")).to_have_count(3, timeout=LIVE)
        expect(page.locator("#members > li").filter(has_text="Ada")).to_contain_text("host")
    expect(bo.locator("#invite-unknown")).to_be_visible()  # only the creating tab knows the code

    say(ada, "Hello, table")
    for page in (bo, cy):
        expect(page.locator("#chat-log .room-msg").last).to_contain_text(
            "Hello, table", timeout=LIVE
        )
    expect(ada.locator("#chat-log .room-msg.is-pending")).to_have_count(0, timeout=LIVE)

    payload = '<img src=x onerror="window.__pwned=1">'
    say(cy, payload)
    expect(bo.locator("#chat-log .room-msg__body").last).to_have_text(payload, timeout=LIVE)
    assert bo.locator("#chat-log img").count() == 0
    assert bo.evaluate("window.__pwned") is None

    start = ada.get_by_role("button", name="Start the case")
    expect(start).to_be_disabled()
    for page in (ada, bo, cy):
        page.get_by_role("button", name="I'm ready").click()
    expect(start).to_be_enabled(timeout=LIVE)
    expect(bo.locator("#table-hint")).to_have_text(
        "Waiting for Ada to start the case.", timeout=LIVE
    )
    start.click()
    for page in (ada, bo, cy):  # the case begins: everyone moves into the story room
        expect(page.locator("#table")).to_have_attribute("data-mode", "game", timeout=LIVE)
        expect(page.locator("#game-story")).to_be_visible()
    say(bo, "Still talking after the start")
    expect(ada.locator("#chat-log .room-msg").last).to_contain_text("Still talking", timeout=LIVE)

    for page in (ada, bo, cy):
        assert page.errors == [], page.errors


def test_reload_resyncs_history_and_presence(person) -> None:
    ada, bo = person("Ada"), person("Bo")
    code = start_table(ada)
    join_table(bo, code)
    say(ada, "Before the reload")
    expect(bo.locator("#chat-log .room-msg").last).to_contain_text(
        "Before the reload", timeout=LIVE
    )

    bo.reload()
    expect(bo.locator("#table")).to_be_visible()
    expect(bo.locator("#conn-text")).to_have_text("Live")
    expect(bo.locator("#chat-log .room-msg")).to_have_count(1)
    expect(bo.locator("#chat-log .room-msg")).to_contain_text("Before the reload")
    bo_row = ada.locator("#members > li").filter(has_text="Bo")
    expect(bo_row).to_contain_text("here", timeout=LIVE)

    bo.context.close()  # closing the tab: Ada sees Bo go away
    expect(bo_row).to_contain_text("away", timeout=LIVE)


def test_leaving_updates_everyone_live(person) -> None:
    ada, bo = person("Ada"), person("Bo")
    code = start_table(ada)
    join_table(bo, code)
    expect(ada.locator("#members > li")).to_have_count(2, timeout=LIVE)
    bo.get_by_role("button", name="Leave the table").click()
    bo.get_by_role("button", name="Leave", exact=True).click()
    expect(bo.locator("#gate")).to_be_visible()
    expect(ada.locator("#members > li")).to_have_count(1, timeout=LIVE)


def test_bad_code_message(person) -> None:
    bo = person("Bo")
    bo.locator("#join-code").fill("abc")
    bo.get_by_role("button", name="Join the table").click()
    expect(bo.locator("#join-code-error")).to_have_text("Enter the 8-character code.")
    bo.locator("#join-code").fill("ZZZZ-ZZZZ")
    bo.get_by_role("button", name="Join the table").click()
    expect(bo.locator("#join-code-error")).to_have_text(
        "That invite code is invalid or has expired."
    )
