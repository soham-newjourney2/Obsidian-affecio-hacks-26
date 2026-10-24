"""Shared e2e helpers: accounts created over the API, sign-in through the UI."""

import re
import uuid

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

# Teammate pages are incomplete in the repo (strings.js keys and storybook-theme.css not pushed,
# lobby.js crashes on load). Tests of those pages are expected to fail until that lands.
TEAMMATE_UI = (
    "teammate frontend incomplete in repo: missing strings.js keys + storybook-theme.css "
    "(see planning_final.md §13 P07)"
)
teammate_ui = pytest.mark.xfail(reason=TEAMMATE_UI, strict=False)

# API responses that are part of normal flows (browsers log every 4xx fetch as an error).
EXPECTED_HTTP_ERRORS = (
    "/api/v1/users/me/profile",  # 404 until onboarding is done
    # TEMPORARY (2026-10-25): teammate pages link this file but it isn't in the repo yet.
    # Remove once they push it.
    "/css/storybook-theme.css",
)


def watch_console(page: Page) -> list[str]:
    """Starts collecting console errors and uncaught page errors; returns the live list."""
    errors: list[str] = []

    def on_console(msg) -> None:
        if msg.type != "error":
            return
        url = msg.location.get("url", "")
        if msg.text.startswith("Failed to load resource") and url.endswith(EXPECTED_HTTP_ERRORS):
            return
        errors.append(f"{msg.text} @ {url}")

    page.on("console", on_console)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    return errors


PASSWORD = "correct horse battery"
PROFILE = {
    "interests": ["books", "puzzles", "coffee_tea"],
    "interaction_style": "playful",
    "availability": ["weekend_evenings"],
}


def unique_email() -> str:
    return f"e2e-{uuid.uuid4().hex[:10]}@example.com"


def create_user(
    request: APIRequestContext, *, with_profile: bool, display_name: str = "Wren"
) -> str:
    """Creates an account over the API (no browser session) and returns its email."""
    email = unique_email()
    res = request.post(
        "/api/v1/auth/register",
        data={
            "email": email,
            "password": PASSWORD,
            "display_name": display_name,
            "age_confirmed": True,
        },
    )
    assert res.ok
    if with_profile:
        token = res.json()["access_token"]
        put = request.put(
            "/api/v1/users/me/profile",
            data=PROFILE,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert put.ok
    return email


def sign_in(page: Page, email: str, password: str = PASSWORD) -> None:
    page.locator("#login-email").fill(email)
    page.locator("#login-password").fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()


def signed_in(page: Page, name: str = "Wren") -> Page:
    """Signs a fresh account (with profile) into `page` and waits for the lobby."""
    email = create_user(page.request, with_profile=True, display_name=name)
    page.goto("/auth.html")
    sign_in(page, email)
    page.wait_for_url("**/lobby.html")
    page.wait_for_selector("#catalogue > li")
    return page


def session_page(page: Page, name: str) -> Page:
    """Signs a fresh account (with profile) into this tab without going through the auth UI.

    Uses the same sessionStorage shape as js/core/auth.js, so tests of new pages don't depend
    on the teammate-owned sign-in screens.
    """
    email = create_user(page.request, with_profile=True, display_name=name)
    res = page.request.post("/api/v1/auth/login", data={"email": email, "password": PASSWORD})
    assert res.ok
    body = res.json()
    session = {"token": body["access_token"], "user": body["user"], "expiresAt": 0}
    page.goto("/assets/brand/favicon.svg")  # any same-origin page, to reach sessionStorage
    page.evaluate(
        """(s) => sessionStorage.setItem("echo.session",
            JSON.stringify({ ...s, expiresAt: Date.now() + 3600 * 1000 }))""",
        session,
    )
    return page


LIVE = 3_000  # room.html has no polling: anything slower would mean the WebSocket isn't working


def start_table(host: Page) -> str:
    """Host starts a table on room.html; returns the invite code."""
    expect(host.locator("#story-select")).to_have_value("blackthorn_manor")
    host.get_by_role("button", name="Start the table").click()
    expect(host.locator("#table")).to_be_visible()
    expect(host.locator("#conn-text")).to_have_text("Live")
    code = host.locator("#invite-code")
    expect(code).to_have_text(re.compile(r"^[A-Z2-7]{4}-[A-Z2-7]{4}$"))
    return code.inner_text()


def join_table(page: Page, code: str) -> None:
    page.locator("#join-code").fill(code.lower())
    page.get_by_role("button", name="Join the table").click()
    expect(page.locator("#table")).to_be_visible()
    expect(page.locator("#conn-text")).to_have_text("Live")


def say(page: Page, text: str) -> None:
    page.locator("#chat-input").fill(text)
    page.locator("#chat-input").press("Enter")


D1_ROOM = "Go straight to Marian's room"
D2_ANY = "Something living is sent through it"
D3_SAFE = "Take Elinor to the village inn for the night"  # safe in every variant


def begin_case(person) -> tuple[Page, Page, Page]:
    """Three people gather on room.html, get ready and start the case."""
    ada, bo, cy = person("Ada"), person("Bo"), person("Cy")
    code = start_table(ada)
    join_table(bo, code)
    join_table(cy, code)
    expect(ada.locator("#members > li")).to_have_count(3, timeout=LIVE)
    for page in (ada, bo, cy):
        page.get_by_role("button", name="I'm ready").click()
    start = ada.get_by_role("button", name="Start the case")
    expect(start).to_be_enabled(timeout=LIVE)
    start.click()
    for page in (ada, bo, cy):
        expect(page.locator("#table")).to_have_attribute("data-mode", "game", timeout=LIVE)
        expect(page.locator("#chapter-label")).to_have_text("Chapter 1 of 4")
    return ada, bo, cy


def vote(page: Page, label: str) -> None:
    page.locator("#choices").get_by_role("button", name=re.compile(re.escape(label))).click()


def all_vote(pages, label: str) -> None:
    for page in pages:
        vote(page, label)


def chapter_is(pages, index: int, title: str) -> None:
    for page in pages:
        expect(page.locator("#chapter-label")).to_have_text(f"Chapter {index} of 4", timeout=LIVE)
        expect(page.locator("#chapter-title")).to_have_text(title)
