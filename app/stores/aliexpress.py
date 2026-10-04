"""AliExpress-scraper.

Twee losse stappen, zodat de parsing los te testen is op bewaarde HTML:
`fetch_search_html()` haalt de pagina op met een echte browser,
`parse_search_html()` leest de kaarten eruit.

AliExpress zet naast de DOM ook een JSON-blob in de pagina
(`window._dida_config_`) met per product het *echte* Choice-vlaggetje, de
verkoopaantallen, de korting en de SPU/pic-group-id's. Die blob is leidend:
badges zijn plaatjes en dus niet betrouwbaar te lezen.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse

from .. import config
from ..prices import parse_price
from .base import Offer, StoreResult

BASE = "https://www.aliexpress.com"

from ..browser import UA, render_page  # noqa: E402  (na BASE, zodat de constante leesbaar blijft)

SSR_MARKERS = ('"isChoice"', '"x_object_id"')


def search_url(query: str, choice_only: bool = False, region: str | None = None) -> str:
    slug = urllib.parse.quote_plus(query)
    params = {"region": region or config.ALIEXPRESS_REGION}
    if choice_only:
        params["isChoice"] = "y"
    return f"{BASE}/w/wholesale-{slug}.html?{urllib.parse.urlencode(params)}"


# --- ophalen ----------------------------------------------------------------
def fetch_search_html(query: str, choice_only: bool = False) -> str:
    """Render de zoekpagina en geef de HTML terug."""
    return render_page(search_url(query, choice_only=choice_only), wait_selector="a.search-card-item")


# --- SSR-blob ---------------------------------------------------------------
def _enclosing_object_start(text: str, pos: int, window: int = 20_000) -> int:
    """Zoek de '{' van het object waarin `pos` valt."""
    depth = 0
    i = pos
    limit = max(0, pos - window)
    while i >= limit:
        ch = text[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            if depth == 0:
                return i
            depth -= 1
        i -= 1
    return -1


def _object_end(text: str, start: int, window: int = 20_000) -> int:
    """Zoek de bijbehorende '}' (string-bewust)."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, min(len(text), start + window)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def parse_ssr_items(html: str) -> dict[str, dict]:
    """Lees de ingebedde JSON-blob: {product-id: item-gegevens}.

    De blobs zitten in een JS-literal (geen geldige JSON als geheel), dus elk
    item-object wordt apart uitgelezen en geparseerd.
    """
    items: dict[str, dict] = {}

    for match in re.finditer(r'"x_object_type"\s*:\s*"productV3"', html):
        start = _enclosing_object_start(html, match.start())
        if start < 0:
            continue
        end = _object_end(html, start)
        if end < 0:
            continue
        try:
            obj = json.loads(html[start:end])
        except ValueError:
            continue
        pid = obj.get("x_object_id")
        if pid:
            items[str(pid)] = obj

    return items


# --- DOM-helpers ------------------------------------------------------------
def _text(node) -> str:
    return re.sub(r"\s+", " ", node.text_content() or "").strip()


def _first_text(card, needles: tuple[str, ...]) -> str | None:
    for needle in needles:
        for el in card.xpath(f'.//*[contains(@class, "{needle}")]'):
            txt = _text(el)
            if txt:
                return txt
    return None


def _leaf_texts(card, needle: str) -> list[str]:
    """Tekst van de binnenste elementen met deze class — voorkomt dat
    opeenvolgende badges aan elkaar geplakt worden."""
    out: list[str] = []
    for el in card.xpath(f'.//*[contains(@class, "{needle}")]'):
        if el.xpath(f'.//*[contains(@class, "{needle}")]'):
            continue  # heeft zelf nog een match: niet de binnenste
        txt = _text(el) or (el.get("title") or "").strip()
        if txt and txt not in out and len(txt) <= 60:
            out.append(txt)
    return out


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return BASE + url
    return url


def _int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _free_ship_from(badges: list[str]) -> float | None:
    """'Gratis levering vanaf €10' -> 10.0"""
    for badge in badges:
        low = badge.lower()
        if ("gratis" in low or "free" in low) and ("vanaf" in low or "from" in low or "over" in low):
            price = parse_price(badge)
            if price and price.value > 0:
                return price.value
    return None


# --- parsen -----------------------------------------------------------------
def parse_search_html(html: str, limit: int | None = None) -> list[Offer]:
    """Lees alle productkaarten uit een AliExpress-zoekpagina."""
    import lxml.html

    if limit is None:
        limit = config.MAX_RESULTS_PER_STORE

    doc = lxml.html.fromstring(html)
    ssr = parse_ssr_items(html)
    offers: list[Offer] = []
    seen: set[str] = set()

    for card in doc.xpath('//a[contains(@class, "search-card-item")]'):
        href = card.get("href") or ""
        match = re.search(r"/item/(\d+)\.html", href)
        if not match:
            continue  # bundel- of SSR-link zonder product-id
        pid = match.group(1)
        if pid in seen:
            continue

        title = _first_text(card, ("titleText", "title--")) or ""
        if not title:
            alt = card.xpath(".//img/@alt")
            title = (alt[0] if alt else "").strip()
        if not title:
            continue

        blob = ssr.get(pid, {})

        # Prijs: nette prijs staat in aria-label van het prijsblok.
        price_txt = None
        for el in card.xpath('.//*[contains(@class, "us--price")]'):
            label = el.get("aria-label")
            if label:
                price_txt = label
                break
        if not price_txt:
            price_txt = _first_text(card, ("price-sale", "us--price"))
        price = parse_price(price_txt)
        if price is None and blob.get("formatted_price"):
            price = parse_price(str(blob["formatted_price"]))

        img = None
        for el in card.xpath(".//img"):
            src = el.get("src") or el.get("data-src")
            if src and not src.startswith("data:"):
                img = _absolute(src)
                break

        badges = _leaf_texts(card, "tag--text")
        if not badges:
            badges = _leaf_texts(card, "serviceTag")
        card_text = _text(card)
        card_low = card_text.lower()

        shipping_txt = next(
            (b for b in badges if "verzend" in b.lower() or "levering" in b.lower()
             or "shipping" in b.lower()),
            None,
        )
        if shipping_txt is None and "gratis verzending" in card_low:
            shipping_txt = "Gratis verzending"
        shipping_cost = 0.0 if (shipping_txt and (
            "gratis" in shipping_txt.lower() or "free" in shipping_txt.lower())) else None

        rating = None
        rating_txt = _first_text(card, ("starRating", "Rating--")) or ""
        rmatch = re.search(r"\d[.,]\d", rating_txt)
        if rmatch:
            try:
                rating = float(rmatch.group(0).replace(",", "."))
            except ValueError:
                rating = None
        if rating is None and blob.get("star_rating") is not None:
            try:
                rating = float(blob["star_rating"])
            except (TypeError, ValueError):
                rating = None

        sold_txt = None
        for el in card.xpath('.//*[contains(@class, "us--trade")]'):
            if el.xpath('.//*[contains(@class, "us--trade")]'):
                continue
            sold_txt = _text(el)
            break
        if not sold_txt:
            sold_txt = _first_text(card, ("us--trade",))
        sold_count = _int(blob.get("real_trade_count"))
        sold = sold_txt
        if sold_txt:
            smatch = re.search(r"[\d.,]+\s*(?:\+\s*)?(?:verkocht|sold)", sold_txt, re.I)
            if smatch:
                sold = smatch.group(0).strip()

        # Choice: het blob-vlaggetje is leidend, de badge is de terugvaloptie.
        if "isChoice" in blob:
            choice = bool(blob["isChoice"])
        else:
            choice = "choice" in card_low or any("choice" in b.lower() for b in badges)

        price_before = None
        seller_cents = _int(blob.get("sellerOfferPriceAmount"))
        if seller_cents and price and seller_cents / 100 > price.value:
            price_before = round(seller_cents / 100, 2)

        seen.add(pid)
        offers.append(
            Offer(
                store=config.STORE_ALIEXPRESS,
                pid=pid,
                title=re.sub(r"\s+", " ", title)[:200],
                url=f"{BASE}/item/{pid}.html",
                price=price.value if price else None,
                currency=price.currency if price else "EUR",
                price_max=price.value_max if price else None,
                price_before=price_before,
                image=img,
                rating=rating,
                sold=sold,
                sold_count=sold_count,
                choice=choice,
                badges=badges,
                shipping_text=shipping_txt,
                shipping_cost=shipping_cost,
                free_ship_from=_free_ship_from(badges),
                spu_id=str(blob["spu_id"]) if blob.get("spu_id") else None,
                pic_group_id=(
                    str(blob["pic_group_id"])
                    if blob.get("pic_group_id") and str(blob["pic_group_id"]) != "0"
                    else None
                ),
                spu_replace_id=(
                    str(blob["spu_replace_id"]) if blob.get("spu_replace_id") else None
                ),
            )
        )
        if len(offers) >= limit:
            break

    return offers


def search(query: str, choice_only: bool = False, limit: int | None = None) -> StoreResult:
    """Zoek op AliExpress en geef een eerlijk resultaat terug."""
    started = time.time()
    try:
        html = fetch_search_html(query, choice_only=choice_only)
        offers = parse_search_html(html, limit=limit)
    except Exception as exc:  # noqa: BLE001
        return StoreResult(
            store=config.STORE_ALIEXPRESS,
            status="error",
            error=f"{type(exc).__name__}: {exc}"[:300],
            elapsed_s=round(time.time() - started, 2),
        )

    status = "ok" if offers else "empty"
    note = None
    if not offers:
        note = "Geen kaarten gevonden — mogelijk een andere mark-up of een blokkade."
    return StoreResult(
        store=config.STORE_ALIEXPRESS,
        offers=offers,
        status=status,
        note=note,
        elapsed_s=round(time.time() - started, 2),
    )
