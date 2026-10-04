"""Winkelwagen-regels van AliExpress en Temu.

AliExpress kent twee gratis-verzendregels:

* **Choice**: zit er voor minstens € 10 aan Choice-artikelen in je wagen, dan
  gaan die artikelen gratis én versneld op de post. Onder die drempel rekenen
  we met een schatting en zeggen we dat ook.
* **Gratis levering vanaf € X**: de kaart zegt zelf vanaf welk bedrag de
  verzending gratis is (meestal € 10, over de hele bestelling).

We verzinnen nooit een verzendbedrag: wat de kaart zegt is leidend, anders volgt
een schatting die als schatting gemarkeerd wordt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .stores.base import Offer


def effective_price(offer: Offer) -> float | None:
    """Prijs inclusief verzendkosten voor zo ver die bekend zijn."""
    if offer.price is None:
        return None
    if offer.shipping_cost is None:
        return offer.price
    return round(offer.price + offer.shipping_cost, 2)


@dataclass
class CartLine:
    offer: Offer
    qty: int = 1


@dataclass
class CartLineResult:
    offer: Offer
    qty: int
    unit_price: float
    subtotal: float
    shipping: float
    shipping_estimated: bool
    note: str | None = None

    @property
    def total(self) -> float:
        return round(self.subtotal + self.shipping, 2)


@dataclass
class CartSummary:
    lines: list[CartLineResult] = field(default_factory=list)
    items_total: float = 0.0
    shipping_total: float = 0.0
    total: float = 0.0
    choice_total: float = 0.0
    choice_threshold: float = 0.0
    choice_threshold_met: bool = False
    choice_missing: float = 0.0
    shipping_estimated: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lines": [
                {
                    "store": line.offer.store,
                    "pid": line.offer.pid,
                    "title": line.offer.title,
                    "qty": line.qty,
                    "unit_price": line.unit_price,
                    "subtotal": line.subtotal,
                    "shipping": line.shipping,
                    "shipping_estimated": line.shipping_estimated,
                    "total": line.total,
                    "note": line.note,
                    "choice": line.offer.choice,
                }
                for line in self.lines
            ],
            "items_total": self.items_total,
            "shipping_total": self.shipping_total,
            "total": self.total,
            "choice_total": self.choice_total,
            "choice_threshold": self.choice_threshold,
            "choice_threshold_met": self.choice_threshold_met,
            "choice_missing": self.choice_missing,
            "shipping_estimated": self.shipping_estimated,
            "notes": self.notes,
        }


def evaluate(lines: list[CartLine], choice_min: float | None = None) -> CartSummary:
    """Reken een mandje door, inclusief de Choice-drempel."""
    choice_min = config.CHOICE_MIN_EUR if choice_min is None else choice_min
    summary = CartSummary(choice_threshold=choice_min)

    priced = [(line, line.offer.price) for line in lines if line.offer.price is not None]
    summary.items_total = round(sum(p * line.qty for line, p in priced), 2)

    choice_total = sum(
        p * line.qty for line, p in priced if line.offer.choice
    )
    summary.choice_total = round(choice_total, 2)
    summary.choice_threshold_met = choice_total >= choice_min
    if not summary.choice_threshold_met:
        summary.choice_missing = round(choice_min - choice_total, 2)

    for line, price in priced:
        offer = line.offer
        subtotal = round(price * line.qty, 2)
        shipping = 0.0
        estimated = False
        note = None

        if offer.shipping_cost == 0.0:
            note = offer.shipping_text or "gratis verzending volgens de kaart"
        elif offer.choice and summary.choice_threshold_met:
            note = "Choice-drempel gehaald: gratis en snelle verzending"
        elif offer.choice:
            shipping = round(config.SHIPPING_FALLBACK_EUR * line.qty, 2)
            estimated = True
            note = (
                f"Choice, maar nog € {summary.choice_missing:.2f} tot de "
                f"€ {choice_min:.0f}-drempel: verzendkosten geschat"
            )
        elif offer.free_ship_from is not None and summary.items_total >= offer.free_ship_from:
            note = f"gratis levering vanaf € {offer.free_ship_from:.0f} gehaald"
        else:
            shipping = round(config.SHIPPING_FALLBACK_EUR * line.qty, 2)
            estimated = True
            note = "verzendkosten onbekend: schatting"

        if estimated:
            summary.shipping_estimated = True

        summary.lines.append(
            CartLineResult(
                offer=offer,
                qty=line.qty,
                unit_price=price,
                subtotal=subtotal,
                shipping=shipping,
                shipping_estimated=estimated,
                note=note,
            )
        )

    summary.shipping_total = round(sum(l.shipping for l in summary.lines), 2)
    summary.total = round(sum(l.total for l in summary.lines), 2)

    if summary.choice_threshold_met:
        summary.notes.append(
            f"Choice-drempel gehaald (€ {summary.choice_total:.2f} ≥ € {choice_min:.2f}): "
            "gratis én snelle verzending op de Choice-artikelen."
        )
    elif summary.choice_total > 0:
        summary.notes.append(
            f"nog € {summary.choice_missing:.2f} aan Choice-artikelen erbij en de verzending "
            "daarvan is gratis én snel."
        )
    if summary.shipping_estimated:
        summary.notes.append(
            "Bedragen met 'geschat' zijn niet door de winkel bevestigd — "
            f"gerekend met € {config.SHIPPING_FALLBACK_EUR:.2f} per regel."
        )
    return summary
