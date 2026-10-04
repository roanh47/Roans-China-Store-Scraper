"""Gedeelde types voor de winkelschrapers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Offer:
    """Eén productaanbieding uit een winkel."""

    store: str
    pid: str
    title: str
    url: str
    price: float | None = None
    currency: str = "EUR"
    price_eur: float | None = None
    price_max: float | None = None
    price_before: float | None = None
    image: str | None = None
    rating: float | None = None
    sold: str | None = None
    sold_count: int | None = None
    choice: bool = False
    badges: list[str] = field(default_factory=list)
    shipping_text: str | None = None
    shipping_cost: float | None = None
    free_ship_from: float | None = None
    # Structuur-signalen van AliExpress zelf (hetzelfde product bij een andere
    # verkoper deelt spu_id / pic_group_id).
    spu_id: str | None = None
    pic_group_id: str | None = None
    spu_replace_id: str | None = None
    # Gevuld door de matcher.
    match_id: str | None = None
    match_size: int = 1
    cheapest: bool = False
    cheapest_overall: bool = False
    saving_eur: float | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["store_label"] = STORE_LABELS.get(self.store, self.store)
        return data


@dataclass
class StoreResult:
    """Uitkomst van één winkel: of het lukte, en wat er misging."""

    store: str
    status: str = "ok"  # ok | empty | blocked | error | skipped
    offers: list[Offer] = field(default_factory=list)
    note: str | None = None
    error: str | None = None
    elapsed_s: float | None = None

    def to_dict(self) -> dict:
        return {
            "store": self.store,
            "store_label": STORE_LABELS.get(self.store, self.store),
            "status": self.status,
            "note": self.note,
            "error": self.error,
            "elapsed_s": self.elapsed_s,
            "count": len(self.offers),
        }


STORE_ALIEXPRESS = "aliexpress"
STORE_TEMU = "temu"

STORE_LABELS = {
    STORE_ALIEXPRESS: "AliExpress",
    STORE_TEMU: "Temu",
}

ALL_STORES = (STORE_ALIEXPRESS, STORE_TEMU)
