"""A smoke run in a real browser: the address without its trailing slash, sign in, then
every page of the shell in both postures, and the keyboard alone through the navigation.

    make smoke      (starts nothing: run `make up` and create the owner first)

Needs MEMOIR_URL (default http://localhost:8080/memoir), MEMOIR_EMAIL, MEMOIR_PASSWORD.
Runs in the Playwright image; prints one line per check and exits 1 on the first failure.
"""

import os
import re

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("MEMOIR_URL", "http://localhost:8080/memoir").rstrip("/")
EMAIL = os.environ.get("MEMOIR_EMAIL", "owner@example.org")
PASSWORD = os.environ["MEMOIR_PASSWORD"]
SHOTS = os.environ.get("MEMOIR_SHOTS", "/out")
PAGES = {
    "/": r"Hello|Your family's memoir",
    "/record": "Record a memory",
    "/timeline": "Timeline",
    "/people": "People",
    "/questions": "Questions for you",
    "/inbox": "Waiting to be placed",
    "/profile": "Your account",
    "/status": "Memoir",
    "/gallery": "Design pieces",
    "/settings/users": "People with access",
}
POSTURES = {"phone": {"width": 390, "height": 844}, "wide": {"width": 1280, "height": 900}}


def sign_in(page):
    page.goto(f"{BASE}/")
    expect(page.get_by_role("heading", name="Sign in to Memoir")).to_be_visible()
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("heading", name="Sign in to Memoir")).to_be_hidden()
    expect(page.get_by_role("navigation", name="Main")).to_be_visible()
    print("ok   sign in")


def every_page(page, posture):
    for path, title in PAGES.items():
        page.goto(f"{BASE}{path}")
        heading = page.get_by_role("heading", level=1, name=re.compile(title))
        try:
            expect(heading).to_be_visible()
        except AssertionError:
            page.screenshot(path=f"{SHOTS}/failed-{posture}.png", full_page=True)
            raise AssertionError(f"{posture} {path}: no heading matching {title!r}") from None
        assert page.get_by_role("main").count() == 1, f"{path}: one main landmark"
        page.reload()
        expect(heading).to_be_visible()
        print(f"ok   {posture:5} {path} (and after a reload)")
    page.screenshot(path=f"{SHOTS}/shell-{posture}.png", full_page=True)


def keyboard(page, posture):
    """Tab from the top of the page: every navigation link is reached, focus is shown."""
    page.goto(f"{BASE}/")
    page.wait_for_load_state("networkidle")
    nav = page.get_by_role("navigation", name="Main")
    want = set(nav.get_by_role("link").all_inner_texts())
    reached = set()
    for _ in range(40):
        page.keyboard.press("Tab")
        focused = page.evaluate(
            "() => { const a = document.activeElement;"
            " return [a.closest('nav') ? a.innerText : null,"
            " getComputedStyle(a).outlineStyle] }"
        )
        if focused[0]:
            reached.add(focused[0])
            assert focused[1] != "none", "a focused link shows a focus ring"
    assert want <= reached, f"not reached by keyboard: {want - reached}"
    print(f"ok   {posture:5} keyboard reaches all {len(want)} navigation links")


def no_trailing_slash(page):
    """The bare address (…/memoir) lands on the app, at the same origin: a redirect that
    named the container's own port once sent people to another service."""
    page.goto(BASE)
    origin = re.match(r"^https?://[^/]+", BASE).group(0)
    assert page.url.startswith(f"{origin}/"), f"{BASE} went to {page.url}"
    print(f"ok   {BASE} stays on {origin}")


with sync_playwright() as p:
    browser = p.chromium.launch()
    no_trailing_slash(browser.new_page())
    for posture, size in POSTURES.items():
        page = browser.new_page(viewport=size)
        sign_in(page)
        every_page(page, posture)
        keyboard(page, posture)
        page.close()
    browser.close()
print("smoke: OK")
