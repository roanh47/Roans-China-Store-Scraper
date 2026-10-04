"""Temu-scraper.

**Eerlijk over de grens.** Temu stuurt bezoekers zonder account naar
`/login.html`, ook bij productpagina's. Gemeten op 2026-10-04 vanaf deze
server: zoeken EN productpagina's belanden op de inlogpagina, de interne
`poppy`-API geeft 403/500 zonder `anti-content`-token, en `m.temu.com` met een
mobiele user-agent levert ook niets. Zonder sessie van een ingelogd account is
er dus niets te lezen — en die sessie is aan jou, niet iets wat deze tool zelf
gaat forceren.

Daarom doet deze module drie dingen:

1. **Proberen** met de cookies uit ``CSS_TEMU_COOKIES`` als die er zijn
   (JSON van Playwright, of simpelweg ``naam=waarde; naam2=waarde2``);
2. **Eerlijk melden** dat het geblokkeerd is, in plaats van doen alsof er geen
   producten zijn;
3. **Deeplink** maken zodat je zelf in één klik verder kijkt in je eigen,
   ingelogde browser.

De selectors hieronder zijn de best mogelijke poging; ze zijn nooit op een
onge­blokkeerde pagina gezien. Daarom bepaalt de muurdetectie het eindoordeel en
niet de parser.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse

from .. import config
from ..browser import render_page
from ..prices import parse_price
from .base import STORE_TEMU, Offer, StoreResult

BASE = "https://www.temu.com"

WALL_MARKERS = (
    "/login.html",
    "login?from=",
    "Verify you are human",
    "captcha",
)

# Titels waaraan je de loginpagina herkent.
LOGIN_TITLES = {
    "temu | aanmelden",
    "temu | sign in",
    "temu | log in",
    "temu | inloggen",
}

PRICE_RE = re.compile(r"(?:€|EUR|\$|US\s*\$)\s?\d[\d.,]*")


def search_url(query: str, region: str | None = None) -> str:
    region = region or config.TEMU_REGION
    slug = urllib.parse.quote_plus(query)
    return f"{BASE}/{region}/search_result.html?search_key={slug}"


def deeplink(query: str) -> str:
    """Zoeklink die je zelf opent — daar ben je wél ingelogd."""
    return search_url(query)


def load_cookies() -> list[dict]:
    """Cookies uit ``CSS_TEMU_COOKIES``, als die er zijn.

    Ondersteunt het JSON-formaat van Playwright (``[{"name":..,"value":..}]``
    of ``{"cookies": [...]}``) en het platte ``naam=waarde; naam2=waarde2``.
    """
    path = config.TEMU_COOKIE_FILE
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read().strip()
    except OSError:
        return []
    if not raw:
        return []

    if raw.startswith("[") or raw.startswith("{"):
        try:
            data = json.loads(raw)
        except ValueError:
            return []
        cookies = data.get("cookies", []) if isinstance(data, dict) else data
        out = []
        for item in cookies:
            if isinstance(item, dict) and item.get("name") and item.get("value") is not None:
                out.append(
                    {
                        "name": str(item["name"]),
                        "value": str(item["value"]),
                        "domain": item.get("domain") or ".temu.com",
                        "path": item.get("path") or "/",
                    }
                )
        return out

    out = []
    for part in raw.replace("\n", ";").split(";"):
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        name, value = name.strip(), value.strip()
        if name and value:
            out.append({"name": name, "value": value, "domain": ".temu.com", "path": "/"})
    return out


def fetch_search_html(query: str) -> str:
    """Render de zoekpagina (met cookies als die er zijn)."""
    return render_page(
        search_url(query),
        wait_selector='a[href*="goods.html"], a[href*="-g-"]',
        cookies=load_cookies(),
    )


def detect_wall(html: str) -> str | None:
    """Is dit de inlogpagina of een botcontrole in plaats van resultaten?

    Let op het venster: op de echte loginpagina staat de titel pas rond byte
    42.000 en de verwijzing naar /login.html rond byte 83.000, omdat er veel
    inline scripts vóór staan. Een venster van 60 kB miste dat en meldde
    "geen resultaten" in plaats van "geblokkeerd" — daarom scannen we het hele
    document op de structurele markers, en alleen het begin op botcontroles.
    """
    if not html:
        return "lege pagina ontvangen van Temu"
    low = html.lower()
    start = low[:30_000]

    title = ""
    match = re.search(r"<title[^>]*>(.*?)</title>", low, re.S)
    if match:
        title = re.sub(r"\s+", " ", match.group(1)).strip()

    if "/login.html" in low or "login?from=" in low:
        return (
            "Temu vraagt een login voor deze pagina (doorverwezen naar /login.html). "
            "Zonder sessie van een ingelogd account geeft Temu geen prijzen."
        )
    if "verify you are human" in start or "captcha" in start:
        return "Temu toont een botcontrole; er zijn geen echte resultaten opgehaald."
    if title in LOGIN_TITLES:
        return f"Temu toonde de inlogpagina ({title}) in plaats van resultaten."
    return None


def parse_search_html(html: str, limit: int | None = None) -> list[Offer]:
    """Best mogelijke poging om Temu-kaarten te lezen (zie module-docstring)."""
    import lxml.html

    limit = limit or config.MAX_RESULTS_PER_STORE
    doc = lxml.html.fromstring(html)
    offers: list[Offer] = []
    seen: set[str] = set()

    for anchor in doc.xpath('//a[contains(@href, "goods.html") or contains(@href, "-g-")]'):
        href = anchor.get("href") or ""
        pid_match = re.search(r"-g-(\d+)", href) or re.search(r"goods_id=(\d+)", href)
        if not pid_match:
            continue
        pid = pid_match.group(1)
        if pid in seen:
            continue

        text = re.sub(r"\s+", " ", anchor.text_content() or "").strip()
        title = ""
        images = anchor.xpath(".//img")
        if images:
            title = (images[0].get("alt") or "").strip()
            image = images[0].get("src") or images[0].get("data-src")
        else:
            image = None
        if not title:
            title = text[:120]
        if not title:
            continue

        price_match = PRICE_RE.search(text)
        price = parse_price(price_match.group(0)) if price_match else None

        seen.add(pid)
        offers.append(
            Offer(
                store=STORE_TEMU,
                pid=pid,
                title=title,
                url=urllib.parse.urljoin(BASE, href),
                price=price.value if price else None,
                currency=price.currency if price else "EUR",
                price_eur=price.value if price and price.currency == "EUR" else None,
                image=image,
                badges=[b for b in ("Choice",) if b.lower() in text.lower()],
                shipping_text="gratis verzending" if "gratis" in text.lower() else None,
                free_ship_from=config.TEMU_FREE_SHIPPING_EUR,
            )
        )
        if len(offers) >= limit:
            break
    return offers


def search(query: str, limit: int | None = None) -> StoreResult:
    """Zoek op Temu. Meldt eerlijk als het niet lukt."""
    started = time.monotonic()
    try:
        html = fetch_search_html(query)
    except Exception as exc:  # noqa: BLE001 - netwerk of browser
        return StoreResult(
            store=STORE_TEMU,
            status="error",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_s=round(time.monotonic() - started, 1),
            note="Kon Temu niet bereiken.",
        )

    wall = detect_wall(html)
    elapsed = round(time.monotonic() - started, 1)
    if wall:
        return StoreResult(
            store=STORE_TEMU,
            status="blocked",
            offers=[],
            note=wall,
            elapsed_s=elapsed,
        )

    offers = parse_search_html(html, limit=limit)
    if not offers:
        return StoreResult(
            store=STORE_TEMU,
            status="empty",
            offers=[],
            note="Temu gaf geen leesbare producten terug.",
            elapsed_s=elapsed,
        )
    return StoreResult(store=STORE_TEMU, status="ok", offers=offers, elapsed_s=elapsed)
