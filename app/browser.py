"""Echte browser (Playwright) voor de winkelschrapers.

AliExpress en Temu delen dezelfde aanpak: één Chromium, één context met
Nederlandse locale, even scrollen zodat de luie kaarten geladen worden, en dan
de HTML ophalen om *buiten* de browser te parsen. Zo blijft het netwerk het
enige trage stuk en is de parsing met bewaarde HTML te testen.
"""

from __future__ import annotations

from . import config

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

ARGV = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
]


def render_page(
    url: str,
    *,
    wait_selector: str | None = None,
    cookies: list[dict] | None = None,
    scroll_steps: int | None = None,
    settle_ms: int | None = None,
) -> str:
    """Render een pagina en geef de HTML terug. Gooit door wat de browser zegt."""
    from playwright.sync_api import sync_playwright

    steps = config.SCROLL_STEPS if scroll_steps is None else scroll_steps
    settle = config.SETTLE_MS if settle_ms is None else settle_ms

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=ARGV)
        try:
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="nl-NL",
                timezone_id="Europe/Amsterdam",
                user_agent=UA,
                extra_http_headers={"Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8"},
            )
            if cookies:
                try:
                    ctx.add_cookies(cookies)
                except Exception:  # noqa: BLE001 - onbruikbare cookies mogen niet blokkeren
                    pass
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
            except Exception:  # noqa: BLE001 - zelfs een halve pagina kan bruikbaar zijn
                pass
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=config.RESULT_WAIT_MS)
                except Exception:  # noqa: BLE001 - leeg, geblokkeerd of traag
                    page.wait_for_timeout(settle)
            for _ in range(steps):
                page.evaluate("window.scrollBy(0, 900)")
                page.wait_for_timeout(600)
            return page.content()
        finally:
            browser.close()
