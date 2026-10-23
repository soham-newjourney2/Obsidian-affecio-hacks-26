"""Shared e2e helpers: accounts created over the API, sign-in through the UI."""

import uuid

from playwright.sync_api import APIRequestContext, Page

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
