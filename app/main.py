"""Web-API en UI van Roans China Store Scraper."""

from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template, request

from . import __version__, cart, config, search
from .stores import aliexpress, temu
from .stores.base import ALL_STORES, STORE_ALIEXPRESS, STORE_LABELS, STORE_TEMU

app = Flask(
    __name__,
    template_folder="web/templates",
    static_folder="web/static",
    static_url_path="/static",
)
app.json.ensure_ascii = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("china-store-scraper")


def _flag(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "ja", "on"}


def _limit(value: str | None) -> int:
    if value is None or value == "":
        return config.MAX_RESULTS_PER_STORE
    try:
        number = int(value)
    except ValueError:
        raise ValueError("limit moet een getal zijn") from None
    if not 1 <= number <= 80:
        raise ValueError("limit moet tussen 1 en 80 liggen")
    return number


def _stores(value: list[str] | str | None) -> list[str]:
    if value is None or value == "":
        return list(ALL_STORES)
    parts = value if isinstance(value, list) else value.split(",")
    wanted = [part.strip() for part in parts if part.strip()]
    unknown = [part for part in wanted if part not in ALL_STORES]
    if unknown:
        raise ValueError(f"onbekende winkel(s): {', '.join(unknown)}; kies uit {', '.join(ALL_STORES)}")
    return wanted or list(ALL_STORES)


# --- pagina's ---------------------------------------------------------------
@app.get("/")
def index():
    return render_template(
        "index.html",
        version=__version__,
        stores=[
            {"id": STORE_ALIEXPRESS, "label": STORE_LABELS[STORE_ALIEXPRESS]},
            {"id": STORE_TEMU, "label": STORE_LABELS[STORE_TEMU]},
        ],
        choice_min=config.CHOICE_MIN_EUR,
        shipping_fallback=config.SHIPPING_FALLBACK_EUR,
        max_results=config.MAX_RESULTS_PER_STORE,
    )


@app.get("/healthz")
def healthz():
    return jsonify(
        {
            "status": "ok",
            "ok": True,
            "version": __version__,
            "stores": list(ALL_STORES),
            "choice_min_eur": config.CHOICE_MIN_EUR,
            "cache": search.cache_stats(),
        }
    )


@app.get("/api/stores")
def api_stores():
    return jsonify(
        {
            "stores": [
                {"id": store, "label": STORE_LABELS[store]} for store in ALL_STORES
            ],
            "notes": {
                STORE_TEMU: (
                    "Temu vraagt een login voor niet-ingelogde bezoekers. Zonder "
                    "sessie-cookies geeft Temu geen prijzen; de zoekopdracht kun je "
                    "wel in één klik zelf openen."
                ),
            },
            "choice_min_eur": config.CHOICE_MIN_EUR,
            "shipping_fallback_eur": config.SHIPPING_FALLBACK_EUR,
            "max_results_per_store": config.MAX_RESULTS_PER_STORE,
        }
    )


# --- zoeken -----------------------------------------------------------------
@app.get("/api/search")
def api_search():
    try:
        query = search.clean_query(request.args.get("q", ""))
        if not query:
            raise ValueError("geef een zoekterm mee (?q=...)")
        stores = _stores(request.args.get("stores"))
        limit = _limit(request.args.get("limit"))
        choice_only = _flag(request.args.get("choice"))
        use_images = not _flag(request.args.get("noimages"))
        refresh = _flag(request.args.get("refresh"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    log.info("zoek '%s' winkels=%s choice=%s", query, stores, choice_only)
    try:
        outcome = search.run_search(
            query,
            stores,
            choice_only=choice_only,
            limit=limit,
            use_images=use_images,
            refresh=refresh,
        )
    except Exception as exc:  # noqa: BLE001 - de UI moet de echte fout zien
        log.exception("zoekopdracht mislukt")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 502

    return jsonify(outcome.to_dict())


# --- winkelwagen ------------------------------------------------------------
@app.post("/api/cart")
def api_cart():
    body = request.get_json(silent=True) or {}
    try:
        query = search.clean_query(body.get("query", ""))
        if not query:
            raise ValueError("query ontbreekt")
        stores = _stores(body.get("stores"))
        limit = _limit(str(body.get("limit")) if body.get("limit") else None)
        choice_only = bool(body.get("choice_only", False))
        items = body.get("items") or []
        if not isinstance(items, list):
            raise ValueError("items moet een lijst zijn")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    offers, missing = search.lookup_offers(
        query, stores, items, choice_only=choice_only, limit=limit
    )
    index = {(offer.store, offer.pid): offer for offer in offers}
    lines = []
    for item in items:
        offer = index.get((str(item.get("store", "")), str(item.get("pid", ""))))
        if offer is None:
            continue
        try:
            qty = max(1, min(99, int(item.get("qty", 1))))
        except (TypeError, ValueError):
            qty = 1
        lines.append(cart.CartLine(offer=offer, qty=qty))

    summary = cart.evaluate(lines)
    payload = summary.to_dict()
    payload["missing"] = missing
    if missing:
        payload["notes"] = list(payload.get("notes", [])) + [
            "Sommige regels staan niet meer in de cache: zoek opnieuw en vink ze aan."
        ]
    return jsonify(payload)


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, threaded=True)
