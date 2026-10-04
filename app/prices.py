"""Prijs- en valuta-parsing.

AliExpress levert per regio een ander notatie: "€2,11" (NL/EU), "US $3.19",
"€ 1.234,56", of een bereik "€2,11 - €5,67". Alles moet naar één float in EUR
zodat winkels vergelijkbaar zijn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CURRENCY_SYMBOLS = {
    "€": "EUR",
    "eur": "EUR",
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "£": "GBP",
    "gbp": "GBP",
    "¥": "CNY",
    "cny": "CNY",
    "rmb": "CNY",
}

_NUMBER = re.compile(r"\d[\d\s.,]*")


@dataclass(frozen=True)
class Price:
    """Een geparseerde prijs. `value` is het laagste bedrag uit de tekst."""

    value: float
    currency: str
    value_max: float | None = None

    @property
    def is_range(self) -> bool:
        return self.value_max is not None and self.value_max > self.value


def detect_currency(text: str) -> str:
    low = text.lower().replace(" ", "")
    if "€" in low or "eur" in low:
        return "EUR"
    if "us$" in low or "usd" in low:
        return "USD"
    if "$" in low:
        return "USD"
    if "£" in low or "gbp" in low:
        return "GBP"
    if "¥" in low or "cny" in low or "rmb" in low:
        return "CNY"
    return "EUR"


def _to_float(raw: str) -> float | None:
    """Zet "1.234,56" / "3.19" / "12,5" om naar een float.

    Heuristiek: staan beide scheidingstekens er, dan is de laatste het
    decimaalteken. Anders: een komma met 1-2 decimalen is decimaal, net als een
    punt met 1-2 decimalen als er geen andere punt in zit.
    """
    txt = raw.replace(" ", "").replace("\u00a0", "")
    txt = txt.strip(".,")
    if not txt:
        return None

    has_dot = "." in txt
    has_comma = "," in txt

    if has_dot and has_comma:
        if txt.rfind(",") > txt.rfind("."):
            txt = txt.replace(".", "").replace(",", ".")
        else:
            txt = txt.replace(",", "")
    elif has_comma:
        head, _, tail = txt.rpartition(",")
        txt = txt.replace(",", ".") if len(tail) in (1, 2) else txt.replace(",", "")
    elif has_dot:
        head, _, tail = txt.rpartition(".")
        if len(tail) == 3 and head.replace(".", "").isdigit() and head:
            txt = txt.replace(".", "")

    try:
        return float(txt)
    except ValueError:
        return None


def parse_price(text: str | None) -> Price | None:
    """Haal de eerste (en eventueel tweede) prijs uit een tekst."""
    if not text:
        return None
    text = text.replace("\u00a0", " ")
    currency = detect_currency(text)

    matches = _NUMBER.findall(text)
    values = [v for v in (_to_float(m) for m in matches) if v is not None and v > 0]
    if not values:
        return None

    low = min(values)
    high = max(values)
    return Price(value=low, currency=currency, value_max=high if high > low else None)


def format_eur(value: float | None) -> str:
    """€ 1.234,56 — Nederlandse notatie, of '—' als er niets is."""
    if value is None:
        return "—"
    return "€ " + f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")
