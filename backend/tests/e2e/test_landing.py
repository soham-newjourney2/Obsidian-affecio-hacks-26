import re

import pytest
from playwright.sync_api import Browser, Page, expect

pytestmark = pytest.mark.e2e

GSAP_CHILDREN = "() => window.gsap.globalTimeline.getChildren(true, true, true).length"


def test_landing_renders_without_console_errors(page: Page, console_errors: list[str]) -> None:
    page.goto("/", wait_until="networkidle")

    expect(page.locator("h1")).to_have_text("Every clue is half a conversation.")
    expect(page.locator(".steps > li")).to_have_count(3)
    expect(page.locator("#cta-start")).to_be_visible()
    # Every string binding resolved (no raw keys, no empty bound nodes).
    empty = page.eval_on_selector_all("[data-s]", "els => els.filter(e => !e.textContent.trim())")
    assert empty == []
    assert "landing." not in page.locator("body").inner_text()
    # Atmosphere layers present and hidden from assistive tech.
    expect(page.locator(".fx-grain[aria-hidden='true']")).to_have_count(1)
    assert console_errors == []


def test_no_fake_stats_on_landing(page: Page) -> None:
    page.goto("/")
    text = page.locator("body").inner_text()
    # Stat-style claims: percentages, "N+", or counts of 10 or more people/sessions.
    stat = r"\d+\s*%|\d\+|\d{2,}[\d,]*\s+(players|users|people|sessions|matches|friends)"
    assert not re.search(stat, text, re.I)


def test_primary_cta_opens_auth(page: Page, console_errors: list[str]) -> None:
    page.goto("/")
    page.locator("#cta-start").click()
    expect(page).to_have_url(re.compile(r"/auth\.html#register$"))
    register_tab = page.get_by_role("tab", name="Create account")
    expect(register_tab).to_have_attribute("aria-selected", "true")
    expect(page.locator("#register-name")).to_be_visible()
    expect(page.locator("#panel-login")).to_be_hidden()
    assert console_errors == []


def test_how_it_works_link_scrolls(page: Page) -> None:
    page.goto("/")
    page.locator(".hero__actions").get_by_role("link", name="How it works").click()
    expect(page).to_have_url(re.compile(r"#how$"))
    expect(page.locator("#how-title")).to_be_in_viewport()


def test_full_motion_runs_gsap(page: Page) -> None:
    page.goto("/", wait_until="networkidle")
    assert page.evaluate("document.documentElement.dataset.motion") == "full"
    assert page.evaluate(GSAP_CHILDREN) > 0


def test_reduced_motion_skips_gsap_timelines(browser: Browser, base_url: str) -> None:
    context = browser.new_context(base_url=base_url, reduced_motion="reduce")
    page = context.new_page()
    page.goto("/", wait_until="networkidle")

    assert page.evaluate("typeof window.gsap") == "object"  # loaded, but unused
    assert page.evaluate("document.documentElement.dataset.motion") == "reduced"
    assert page.evaluate(GSAP_CHILDREN) == 0
    opacity = page.eval_on_selector(".hero__title", "e => getComputedStyle(e).opacity")
    assert opacity == "1"
    context.close()


def test_ui_helpers_render_text_inertly(page: Page) -> None:
    page.goto("/", wait_until="networkidle")
    payload = '<img src=x onerror="window.__pwned=1">'
    page.evaluate(
        """async (p) => {
            const ui = await import('/js/core/ui.js');
            ui.toast(p);
            ui.openModal({ title: p, body: p });
        }""",
        payload,
    )
    expect(page.locator(".toast")).to_have_text(payload)
    expect(page.locator("dialog.modal h2")).to_have_text(payload)
    assert page.locator(".toast img, dialog img").count() == 0
    assert page.evaluate("window.__pwned") is None
    page.keyboard.press("Escape")
    expect(page.locator("dialog.modal")).to_have_count(0)
