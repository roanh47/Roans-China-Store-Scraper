"""Instellingen voor Roans China Store Scraper.

Alles wat je zou willen draaien zonder code te wijzigen staat hier, en kan via
omgevingsvariabelen overschreven worden.
"""

from __future__ import annotations

import os


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _num(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


# --- server -----------------------------------------------------------------
HOST = os.environ.get("CSS_HOST", "127.0.0.1")
PORT = int(_num("CSS_PORT", 8304))

# --- winkels ----------------------------------------------------------------
STORE_ALIEXPRESS = "aliexpress"
STORE_TEMU = "temu"
STORES = (STORE_ALIEXPRESS, STORE_TEMU)
STORE_LABELS = {STORE_ALIEXPRESS: "AliExpress", STORE_TEMU: "Temu"}

# AliExpress regio: 'eu' houdt de prijzen in EUR en toont EU-voorraad.
ALIEXPRESS_REGION = os.environ.get("CSS_ALIEXPRESS_REGION", "eu")

# --- Choice (AliExpress) ----------------------------------------------------
# Choice-artikelen krijgen gratis én snelle verzending zodra de som van alle
# Choice-artikelen in de winkelwagen boven deze drempel uitkomt.
CHOICE_MIN_EUR = _num("CSS_CHOICE_MIN_EUR", 10.0)
# Verzendkosten die AliExpress rekent voor niet-Choice/EU-artikelen als de
# drempel niet gehaald is. Wordt alleen gebruikt als de kaart zelf geen
# verzendtekst toont; anders is de tekst op de kaart leidend.
SHIPPING_FALLBACK_EUR = _num("CSS_SHIPPING_FALLBACK_EUR", 2.99)
# Temu's eigen drempel voor gratis verzending (alleen gebruikt als Temu-data
# beschikbaar is; zie docs/ARCHITECTURE.md).
TEMU_FREE_SHIPPING_EUR = _num("CSS_TEMU_FREE_SHIPPING_EUR", 10.0)
# Regio voor Temu-links (nl = Nederlandse prijzen).
TEMU_REGION = os.environ.get("CSS_TEMU_REGION", "nl")
# Optioneel: cookies van een ingelogd Temu-account. Staat buiten de repo
# (``data/`` in .gitignore) en wordt nooit gelogd.
TEMU_COOKIE_FILE = os.environ.get("CSS_TEMU_COOKIES", "/data/temu-cookies.json")

# --- scrapen ----------------------------------------------------------------
PAGE_TIMEOUT_MS = int(_num("CSS_PAGE_TIMEOUT_MS", 45_000))
RESULT_WAIT_MS = int(_num("CSS_RESULT_WAIT_MS", 15_000))
SETTLE_MS = int(_num("CSS_SETTLE_MS", 4_000))
SCROLL_STEPS = int(_num("CSS_SCROLL_STEPS", 4))
MAX_RESULTS_PER_STORE = int(_num("CSS_MAX_RESULTS", 40))
# Bovengrens aan de lengte van een zoekterm.
MAX_QUERY_LEN = int(_num("CSS_MAX_QUERY_LEN", 120))

# --- matching ---------------------------------------------------------------
# Gemeten op echte resultaten: twee *verschillende* producten halen een
# dHash-gelijkenis tot 0,70 en een titelgelijkenis tot 0,78. Daaronder blijft
# het veilig; daarboven praten we over hetzelfde product.
IMAGE_HAMMING_MAX = int(_num("CSS_IMAGE_HAMMING_MAX", 6))
IMAGE_SIM_MIN = 1.0 - IMAGE_HAMMING_MAX / 64.0
# Titelgelijkenis die nodig is als het beeld ook klopt.
TITLE_SIM_WITH_IMAGE = _num("CSS_TITLE_SIM_WITH_IMAGE", 0.45)
# Titelgelijkenis die op zichzelf genoeg is (bijna identieke titel).
TITLE_SIM_ALONE = _num("CSS_TITLE_SIM_ALONE", 0.85)
# Hoeveel aanbiedingen maximaal in één "zelfde product"-groep mogen.
MAX_GROUP_SIZE = int(_num("CSS_MAX_GROUP_SIZE", 6))
# Minimale gecombineerde score om twee aanbiedingen aan elkaar te koppelen.
MATCH_MIN_SCORE = _num("CSS_MATCH_MIN_SCORE", 0.55)
# Bovengrens aan het aantal beeld+titel-vergelijkingen per zoekopdracht.
MAX_MATCH_PAIRS = int(_num("CSS_MAX_MATCH_PAIRS", 1200))

# --- afbeeldingen -----------------------------------------------------------
IMAGE_TIMEOUT_S = _num("CSS_IMAGE_TIMEOUT_S", 12.0)
IMAGE_MAX_BYTES = int(_num("CSS_IMAGE_MAX_BYTES", 4_000_000))
IMAGE_CACHE_DIR = os.environ.get("CSS_IMAGE_CACHE", "/tmp/css-image-cache")
IMAGE_WORKERS = int(_num("CSS_IMAGE_WORKERS", 8))

# --- cache ------------------------------------------------------------------
SEARCH_CACHE_TTL_S = _num("CSS_SEARCH_CACHE_TTL_S", 300.0)

DEBUG = _flag("CSS_DEBUG", False)
