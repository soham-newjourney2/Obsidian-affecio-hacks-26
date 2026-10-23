import re

import pytest
from playwright.sync_api import Browser, Page, expect

from backend.tests.e2e.helpers import PASSWORD, create_user, sign_in, unique_email

pytestmark = pytest.mark.e2e

def test_register_onboard_lobby(page: Page, console_errors: list[str]) -> None:
    page.goto("/")
    page.locator("#cta-start").click()

    page.locator("#register-name").fill("  Ada  ")
    page.locator("#register-email").fill(unique_email())
    page.locator("#register-password").fill(PASSWORD)
    page.locator("#register-age").check()
    page.get_by_role("button", name="Create account", exact=True).click()

    expect(page).to_have_url(re.compile(r"/onboarding\.html$"))
    expect(page.locator("#user-name")).to_have_text("Ada")
    interests = page.locator("#field-interests")
    for label in ("Books", "Puzzles & riddles", "Coffee & tea"):
        interests.get_by_text(label, exact=True).click()
    expect(interests.locator(".counter")).to_have_text("3 of 8 chosen")
    page.locator("#field-interaction_style").get_by_text("Thoughtful").click()
    page.locator("#field-availability").get_by_text("Weekday evenings").click()
    # Private is preselected; the summary is optional.
    expect(page.locator('input[name="visibility"][value="private"]')).to_be_checked()
    page.locator("#summary").fill("New in town.")
    page.get_by_role("button", name="Save and continue").click()

    expect(page).to_have_url(re.compile(r"/lobby\.html$"))
    expect(page.locator("#welcome")).to_have_text("Welcome, Ada.")
    assert console_errors == []

    # Editing shows the saved choices.
    page.get_by_role("link", name="Edit your case file").click()
    expect(page.locator('input[name="interests"][value="puzzles"]')).to_be_checked()
    expect(page.locator("#summary")).to_have_value("New in town.")
    expect(page.get_by_role("button", name="Save changes")).to_be_visible()


def test_register_validation_messages(page: Page) -> None:
    page.goto("/auth.html#register")
    page.get_by_role("button", name="Create account", exact=True).click()
    expect(page.locator("#register-name-error")).to_be_visible()
    expect(page.locator("#register-email-error")).to_have_text("Enter a valid email address.")
    expect(page.locator("#register-password-error")).to_have_text("Use 10–128 characters.")
    expect(page.locator("#register-age-error")).to_contain_text("18 or older")
    expect(page.locator("#register-name")).to_be_focused()


def test_duplicate_email_shown_on_field(page: Page) -> None:
    email = create_user(page.request, with_profile=False)
    page.goto("/auth.html#register")
    page.locator("#register-name").fill("Ada")
    page.locator("#register-email").fill(email)
    page.locator("#register-password").fill(PASSWORD)
    page.locator("#register-age").check()
    page.get_by_role("button", name="Create account", exact=True).click()
    expect(page.locator("#register-email-error")).to_contain_text("already exists")


def test_onboarding_enforces_limits(page: Page) -> None:
    email = create_user(page.request, with_profile=False)
    page.goto("/auth.html")
    sign_in(page, email)
    expect(page).to_have_url(re.compile(r"/onboarding\.html$"))

    interests = page.locator("#field-interests")
    boxes = interests.locator('input[type="checkbox"]')
    for i in range(8):
        interests.locator(".chip").nth(i).click()
    expect(boxes.nth(8)).to_be_disabled()
    expect(interests.locator(".counter")).to_have_text("8 of 8 chosen")
    roles = page.locator("#field-preferred_roles")
    roles.get_by_text("Listener").click()
    roles.get_by_text("Archivist").click()
    expect(roles.locator('input[value="strategist"]')).to_be_disabled()
    for i in range(6):  # back down to 2
        interests.locator(".chip").nth(i).click()
    page.get_by_role("button", name="Save and continue").click()
    expect(page.locator("#field-interests-error")).to_have_text("Choose at least 3.")
    expect(page.locator("#field-interaction_style-error")).to_have_text("Choose one.")
    expect(page).to_have_url(re.compile(r"/onboarding\.html$"))


def test_login_error_is_generic(page: Page) -> None:
    email = create_user(page.request, with_profile=True)
    page.goto("/auth.html")
    sign_in(page, email, password="wrong password!")
    expect(page.locator("#panel-login .form-error")).to_have_text("Incorrect email or password.")


def test_guard_redirects_then_returns(page: Page) -> None:
    email = create_user(page.request, with_profile=True)
    page.goto("/lobby.html")
    expect(page).to_have_url(re.compile(r"/auth\.html\?next=%2Flobby\.html$"))
    sign_in(page, email)
    expect(page).to_have_url(re.compile(r"/lobby\.html$"))
    expect(page.locator("#welcome")).to_have_text("Welcome, Wren.")


def test_next_param_cannot_leave_site(page: Page) -> None:
    email = create_user(page.request, with_profile=True)
    page.goto("/auth.html?next=//evil.example/")
    sign_in(page, email)
    expect(page).to_have_url(re.compile(r"/lobby\.html$"))


def test_session_is_per_tab_and_sign_out_works(browser: Browser, base_url: str) -> None:
    context = browser.new_context(base_url=base_url)
    page = context.new_page()
    email = create_user(page.request, with_profile=True)
    page.goto("/auth.html")
    sign_in(page, email)
    expect(page).to_have_url(re.compile(r"/lobby\.html$"))

    other_tab = context.new_page()  # same browser profile, fresh sessionStorage
    other_tab.goto("/lobby.html")
    expect(other_tab).to_have_url(re.compile(r"/auth\.html"))

    page.get_by_role("button", name="Sign out").click()
    expect(page).to_have_url(re.compile(r"/$"))
    page.goto("/lobby.html")
    expect(page).to_have_url(re.compile(r"/auth\.html"))
    context.close()
