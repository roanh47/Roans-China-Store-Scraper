"""Gedeelde test-hulpjes."""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

from app.stores.base import Offer  # noqa: E402


def fixture(name: str) -> str:
    path = FIXTURES / name
    if not path.exists():
        pytest.skip(f"fixture {name} ontbreekt")
    return path.read_text(encoding="utf-8", errors="replace")


def offer(
    pid: str,
    *,
    store: str = "aliexpress",
    title: str = "usb c kabel",
    price: float | None = 3.49,
    image: str | None = None,
    spu_id: str | None = None,
    pic_group_id: str | None = None,
    choice: bool = True,
    shipping_cost: float | None = None,
    shipping_text: str | None = None,
    free_ship_from: float | None = None,
    price_before: float | None = None,
) -> Offer:
    return Offer(
        store=store,
        pid=pid,
        title=title,
        url=f"https://example.invalid/item/{pid}.html",
        price=price,
        image=image or f"https://example.invalid/img/{pid}.jpg",
        spu_id=spu_id,
        pic_group_id=pic_group_id,
        choice=choice,
        shipping_cost=shipping_cost,
        shipping_text=shipping_text,
        free_ship_from=free_ship_from,
        price_before=price_before,
    )


@pytest.fixture(autouse=True)
def _no_real_image_downloads(monkeypatch):
    """Nooit het netwerk op tijdens tests: hashes komen uit de test zelf."""
    from app import images

    monkeypatch.setattr(images, "download", lambda *args, **kwargs: None, raising=False)
