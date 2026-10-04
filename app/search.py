"""Zoekopdracht over de winkels: parallel scrapen, matchen, cachen.

De resultaten gaan met een tijdstempel in een cache met korte levensduur, zodat
de winkelwagen-endpoint dezelfde aanbiedingen kan terugvinden zonder opnieuw te
scrapen. Wat niet in de cache zit, wordt niet verzonnen: dat meldt de API als
"opnieuw zoeken".
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import config, matching
from .images import hash_many
from .stores import aliexpress, temu
from .stores.base import ALL_STORES, STORE_ALIEXPRESS, STORE_TEMU, Offer, StoreResult

STORE_MODULES = {
    STORE_ALIEXPRESS: aliexpress,
    STORE_TEMU: temu,
}


@dataclass
class SearchOutcome:
    """Alles wat één zoekopdracht opleverde."""

    query: str
    stores: list[str]
    choice_only: bool
    use_images: bool
    offers: list[Offer] = field(default_factory=list)
    groups: list[matching.Group] = field(default_factory=list)
    store_results: list[StoreResult] = field(default_factory=list)
    limit: int = 0
    took_s: float = 0.0
    cached: bool = False
    generated_at: str = ""

    def to_dict(self) -> dict:
        matched = [o for o in self.offers if o.match_id]
        return {
            "query": self.query,
            "stores": self.stores,
            "choice_only": self.choice_only,
            "use_images": self.use_images,
            "limit": self.limit,
            "took_s": self.took_s,
            "cached": self.cached,
            "generated_at": self.generated_at,
            "counts": {
                "offers": len(self.offers),
                "groups": len(self.groups),
                "matched_offers": len(matched),
                "per_store": {
                    result.store: len(result.offers) for result in self.store_results
                },
            },
            "stores": [result.to_dict() for result in self.store_results],
            "deeplinks": {
                STORE_ALIEXPRESS: aliexpress.search_url(self.query, choice_only=self.choice_only),
                STORE_TEMU: temu.deeplink(self.query),
            },
            "groups": [
                {
                    "id": group.gid,
                    "size": len(group.offers),
                    "reasons": group.reasons,
                    "spread": group.spread,
                    "offers": [o.to_dict() for o in group.offers],
                }
                for group in self.groups
            ],
            "offers": [offer.to_dict() for offer in self.offers],
            "meta": {
                "choice_min_eur": config.CHOICE_MIN_EUR,
                "shipping_fallback_eur": config.SHIPPING_FALLBACK_EUR,
                "temu_free_shipping_eur": config.TEMU_FREE_SHIPPING_EUR,
                "image_hamming_max": config.IMAGE_HAMMING_MAX,
            },
        }


_cache: dict[str, tuple[float, SearchOutcome]] = {}
_inflight: dict[str, threading.Event] = {}
_lock = threading.Lock()


def cache_key(
    query: str,
    stores: list[str],
    choice_only: bool,
    limit: int | None = None,
    use_images: bool = True,
) -> str:
    return "|".join(
        [
            query.strip().lower(),
            ",".join(sorted(stores)),
            "choice" if choice_only else "all",
            str(limit or config.MAX_RESULTS_PER_STORE),
            "img" if use_images else "noimg",
        ]
    )


def clean_query(query: str) -> str:
    return " ".join((query or "").split())[: config.MAX_QUERY_LEN]


def normalise_stores(stores: list[str] | str | None) -> list[str]:
    if stores is None:
        return list(ALL_STORES)
    if isinstance(stores, str):
        stores = [part.strip() for part in stores.split(",")]
    wanted = [s for s in stores if s in ALL_STORES]
    return wanted or list(ALL_STORES)


def cached(key: str, max_age_s: float | None = None) -> SearchOutcome | None:
    with _lock:
        hit = _cache.get(key)
    if not hit:
        return None
    max_age = config.SEARCH_CACHE_TTL_S if max_age_s is None else max_age_s
    age = time.time() - hit[0]
    if age > max_age:
        return None
    outcome = hit[1]
    outcome.cached = True
    return outcome


def run_search(
    query: str,
    stores: list[str] | str | None = None,
    *,
    choice_only: bool = False,
    limit: int | None = None,
    use_images: bool = True,
    refresh: bool = False,
) -> SearchOutcome:
    """Zoek in de gekozen winkels, match en onthoud het resultaat."""
    query = clean_query(query)
    store_list = normalise_stores(stores)
    key = cache_key(query, store_list, choice_only, limit, use_images)

    if not refresh:
        hit = cached(key)
        if hit:
            return hit

    # Eén zoekopdracht tegelijk per sleutel: niet twee browsers hetzelfde laten doen.
    while True:
        with _lock:
            wait_event = _inflight.get(key)
            if wait_event is None:
                wait_event = threading.Event()
                _inflight[key] = wait_event
                break
        wait_event.wait(timeout=120)
        hit = cached(key)
        if hit:
            return hit

    started = time.monotonic()
    try:
        store_results: list[StoreResult] = []
        with ThreadPoolExecutor(max_workers=max(1, len(store_list))) as pool:
            futures = {
                store: pool.submit(STORE_MODULES[store].search, query, limit)
                for store in store_list
            }
            for store, future in futures.items():
                try:
                    store_results.append(future.result())
                except Exception as exc:  # noqa: BLE001 - winkel mag de rest niet stukmaken
                    store_results.append(
                        StoreResult(
                            store=store,
                            status="error",
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    )

        offers: list[Offer] = []
        for result in store_results:
            offers.extend(result.offers)

        hashes: dict[str, int] = {}
        if use_images and offers:
            hashes = hash_many([o.image for o in offers])

        groups = matching.group_offers(offers, hashes, use_images=use_images) if offers else []

        outcome = SearchOutcome(
            query=query,
            stores=store_list,
            choice_only=choice_only,
            use_images=use_images,
            offers=offers,
            groups=groups,
            store_results=store_results,
            limit=limit or config.MAX_RESULTS_PER_STORE,
            took_s=round(time.monotonic() - started, 1),
            cached=False,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        with _lock:
            _cache[key] = (time.time(), outcome)
            # Cache niet onbeperkt laten groeien.
            if len(_cache) > 40:
                oldest = sorted(_cache.items(), key=lambda item: item[1][0])[:10]
                for old_key, _ in oldest:
                    _cache.pop(old_key, None)
        return outcome
    finally:
        with _lock:
            event = _inflight.pop(key, None)
        if event:
            event.set()


def lookup_offers(
    query: str,
    stores: list[str] | str | None,
    items: list[dict],
    *,
    choice_only: bool = False,
    limit: int | None = None,
) -> tuple[list[Offer], list[dict]]:
    """Zoek aanbiedingen uit een eerdere zoekopdracht terug voor het mandje.

    Geeft (gevonden, ontbrekend) terug. Ontbrekende regels worden niet geschat:
    die moet je opnieuw zoeken.
    """
    store_list = normalise_stores(stores)
    key = cache_key(query, store_list, choice_only, limit, True)
    found: list[Offer] = []
    missing: list[dict] = []

    for candidate_key in (key, key.replace("|img", "|noimg")):
        outcome = cached(candidate_key, max_age_s=config.SEARCH_CACHE_TTL_S * 3)
        if not outcome:
            continue
        index = {(o.store, o.pid): o for o in outcome.offers}
        for item in items:
            store, pid = str(item.get("store", "")), str(item.get("pid", ""))
            offer = index.get((store, pid))
            if offer:
                found.append(offer)
            else:
                missing.append({"store": store, "pid": pid})
        if found:
            return found, missing

    for item in items:
        entry = {"store": str(item.get("store", "")), "pid": str(item.get("pid", ""))}
        if entry not in missing:
            missing.append(entry)
    return found, missing


def cache_stats() -> dict:
    with _lock:
        return {"entries": len(_cache), "keys": sorted(_cache.keys())[:20]}
