"""Geen geheimen in de repo.

Deze repo is publiek, dus sessies en sleutels horen er niet in. De test faalt
zodra er iets met een sleutelpatroon in de werkmap staat dat meegecommit zou
worden.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

PATTERNS = [
    re.compile(r"ci_live_[A-Za-z0-9]"),
    re.compile(r"APCA[A-Z0-9]{10}"),
    re.compile(r"sk-[A-Za-z0-9]{20}"),
    re.compile(r"BEGIN (RSA|OPENSSH|EC) PRIVATE KEY"),
    re.compile(r"PK[A-Z0-9]{10}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20}"),
    re.compile(r"\bsk_live_[A-Za-z0-9]"),
]

SKIP_DIRS = {".git", "data", "secrets", "__pycache__", ".pytest_cache", ".venv", "node_modules"}
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".woff", ".woff2", ".ico"}


def repo_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIX:
            continue
        yield path


def test_geen_sleutelpatronen_in_de_repo():
    hits = []
    for path in repo_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                hits.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert hits == [], f"mogelijke sleutels gevonden: {hits}"


def test_geen_echte_env_of_cookies_in_de_repo():
    assert not (ROOT / ".env").exists(), ".env hoort niet in de repo (.env.example wel)"
    assert not (ROOT / "secrets").exists(), "secrets/ hoort niet in de repo"
    tracked = [p.name for p in repo_files()]
    assert not [n for n in tracked if "cookie" in n.lower()]


def test_gitignore_dekt_data_en_secrets():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for rule in ("secrets/", "data/", ".env"):
        assert rule in text
