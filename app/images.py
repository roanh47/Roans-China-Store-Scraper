"""Afbeeldingen ophalen en vergelijken met een perceptuele hash.

Twee foto's van hetzelfde product (andere winkel, andere uitsnede, andere
compressie) geven bijna dezelfde dHash. Zo vinden we hetzelfde product terug
zonder op titels te vertrouwen.
"""

from __future__ import annotations

import hashlib
import io
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_memo: dict[str, int | None] = {}


def cache_path(url: str, suffix: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(config.IMAGE_CACHE_DIR, digest + suffix)


def download(url: str, timeout: float | None = None, max_bytes: int | None = None) -> bytes | None:
    """Haal een afbeelding op (met schijfcache)."""
    timeout = timeout or config.IMAGE_TIMEOUT_S
    max_bytes = max_bytes or config.IMAGE_MAX_BYTES
    path = cache_path(url, ".img")

    if os.path.exists(path):
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError:
            pass

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = resp.read(max_bytes + 1)
    except (urllib.error.URLError, OSError, ValueError):
        return None

    if not data or len(data) > max_bytes:
        return None

    try:
        os.makedirs(config.IMAGE_CACHE_DIR, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError:
        pass
    return data


def dhash(data: bytes | None, size: int = 8) -> int | None:
    """64-bits difference-hash: elk bit is 'volgende pixel donkerder'."""
    if not data:
        return None
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow hoort in de image te zitten
        return None

    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    except Exception:  # noqa: BLE001 - kapotte/onbekende afbeelding
        return None

    pixels = list(img.getdata())
    bits = 0
    for row in range(size):
        offset = row * (size + 1)
        for col in range(size):
            bits = (bits << 1) | int(pixels[offset + col] > pixels[offset + col + 1])
    return bits


def ahash(data: bytes | None, size: int = 8) -> int | None:
    """64-bits average-hash: bit = pixel boven of onder het gemiddelde."""
    if not data:
        return None
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None

    try:
        img = Image.open(io.BytesIO(data)).convert("L").resize((size, size), Image.LANCZOS)
    except Exception:  # noqa: BLE001
        return None

    pixels = list(img.getdata())
    average = sum(pixels) / len(pixels)
    bits = 0
    for value in pixels:
        bits = (bits << 1) | int(value > average)
    return bits


def phash(data: bytes | None, size: int = 8) -> int | None:
    """64-bits pHash (DCT), het meest robuust tegen uitsnede/compressie."""
    if not data:
        return None
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None

    try:
        img = Image.open(io.BytesIO(data)).convert("L").resize((size * 4, size * 4), Image.LANCZOS)
    except Exception:  # noqa: BLE001
        return None

    pixels = list(img.getdata())
    n = size * 4
    # 2D DCT-II, maar alleen de laagste frequenties zijn nodig.
    import math

    cos = [[math.cos((2 * x + 1) * u * math.pi / (2 * n)) for u in range(size)] for x in range(n)]
    rows = []
    for y in range(size):
        row = pixels[y * n : (y + 1) * n]
        rows.append([sum(row[x] * cos[x][u] for x in range(n)) for u in range(size)])
    cols = []
    for v in range(size):
        for u in range(size):
            cols.append(sum(rows[y][u] * cos[y][v] for y in range(size)))
    low = cols[1:]
    median = sorted(low)[len(low) // 2]
    bits = 0
    for value in low:
        bits = (bits << 1) | int(value > median)
    return bits


def hash_url(url: str | None, kind: str = "dhash") -> int | None:
    """Hash van een afbeeldings-URL, met memo + schijfcache."""
    if not url:
        return None
    key = f"{kind}:{url}"
    if key in _memo:
        return _memo[key]

    path = cache_path(url, f".{kind}")
    if os.path.exists(path):
        try:
            with open(path) as fh:
                value = int(fh.read().strip())
            _memo[key] = value
            return value
        except (OSError, ValueError):
            pass

    func = {"dhash": dhash, "ahash": ahash, "phash": phash}.get(kind, dhash)
    value = func(download(url))
    _memo[key] = value
    if value is not None:
        try:
            os.makedirs(config.IMAGE_CACHE_DIR, exist_ok=True)
            with open(path, "w") as fh:
                fh.write(str(value))
        except OSError:
            pass
    return value


def hash_many(urls: list[str | None], workers: int | None = None, kind: str = "dhash") -> dict[str, int]:
    """Hashes voor veel URL's tegelijk (netwerk is de bottleneck)."""
    wanted = [u for u in dict.fromkeys(urls) if u]
    workers = workers or config.IMAGE_WORKERS
    out: dict[str, int] = {}
    if not wanted:
        return out
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for url, value in zip(wanted, pool.map(lambda u: hash_url(u, kind), wanted)):
            if value is not None:
                out[url] = value
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def image_similarity(a: int | None, b: int | None) -> float | None:
    """1.0 = identiek, 0.0 = maximaal verschillend. None = geen beeld."""
    if a is None or b is None:
        return None
    return 1.0 - hamming(a, b) / 64.0
