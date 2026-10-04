"""Hetzelfde product terugvinden bij een andere verkoper of winkel.

Twee soorten bewijs:

1. **Structuur** (alleen AliExpress): `spu_id` is het product zelf,
   `pic_group_id` de fotoset. Gelijk = zelfde product, geen giswerk.
   `spu_replace_id` doet *niet* mee: dat is de herkomst van een SSR-bundel en
   verwijst bij tientallen uiteenlopende artikelen naar hetzelfde id.
2. **Beeld + titel**: perceptuele hash van de hoofdfoto plus titelovereenkomst.
   Dat is wat we nodig hebben zodra Temu (of een andere winkel) meedoet, want
   daar zijn geen AliExpress-id's.

De drempels komen uit metingen op echte AliExpress-resultaten, niet uit een
onderbuik (zie tests/test_matching.py en docs/ARCHITECTURE.md):

* twee verschillende producten halen een titelgelijkenis tot 0,78;
* twee verschillende producten halen een beeldgelijkenis tot 0,70;
* daarom: beeld telt alleen mee samen met een duidelijke titel, en titel alleen
  moet bijna identiek zijn. Liever een gemiste match dan een verkeerde prijs.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from . import config
from .stores.base import Offer

# Verkoopruis die niets zegt over het product zelf.
STOPWORDS = {
    "de", "het", "een", "en", "voor", "van", "met", "the", "for", "and", "with",
    "new", "nieuw", "hot", "sale", "gratis", "free", "shipping", "verzending",
    "korting", "promo", "promotie", "dropshipping", "dropship", "wholesale",
    "high", "quality", "kwaliteit", "best", "beste", "stuk", "stuks", "pcs",
    "pc", "st", "set", "type", "naar", "andere", "andere",
}

_norm_re = re.compile(r"[^0-9a-z]+")


def normalize_title(title: str) -> str:
    return _norm_re.sub(" ", (title or "").lower()).strip()


def tokens(title: str) -> set[str]:
    words = normalize_title(title).split()
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def title_similarity(a: str, b: str) -> float:
    """Tekenreeks-gelijkenis van genormaliseerde titels (0..1).

    Bewust dezelfde maat als waarmee de drempels zijn geijkt: de pure
    difflib-ratio op de genormaliseerde titel. Een eerdere versie mengde er
    tokenoverlap doorheen, en daardoor kwamen twee generieke titels van
    verschillende producten (allebei "240W nylon USB Type C ... kabel")
    boven de drempel uit.
    """
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def structural_reason(a: Offer, b: Offer) -> str | None:
    """AliExpress vertelt zelf welke aanbiedingen hetzelfde product zijn."""
    if a.spu_id and a.spu_id == b.spu_id:
        return "zelfde spu_id"
    if a.pic_group_id and a.pic_group_id == b.pic_group_id:
        return "zelfde fotoset"
    return None


@dataclass
class MatchEvidence:
    score: float
    matched: bool
    reasons: list[str] = field(default_factory=list)
    image_similarity: float | None = None
    title_similarity: float | None = None


def pair_evidence(
    a: Offer, b: Offer, hashes: dict[str, int], *, use_images: bool = True
) -> MatchEvidence:
    """Hoe zeker is het dat a en b hetzelfde product zijn?"""
    reason = structural_reason(a, b)
    if reason:
        return MatchEvidence(score=1.0, matched=True, reasons=[reason])

    title_sim = title_similarity(a.title, b.title)

    image_sim = None
    if use_images:
        from .images import image_similarity

        hash_a = hashes.get(a.image) if a.image else None
        hash_b = hashes.get(b.image) if b.image else None
        # Zonder twee echte hashes is er geen beeldbewijs: twee aanbiedingen
        # zonder foto mogen geen "zelfde foto"-match worden.
        image_sim = (
            image_similarity(hash_a, hash_b)
            if hash_a is not None and hash_b is not None
            else None
        )

    score = title_sim * 0.85 if image_sim is None else 0.7 * image_sim + 0.3 * title_sim

    if image_sim is not None and image_sim >= config.IMAGE_SIM_MIN and title_sim >= config.TITLE_SIM_WITH_IMAGE:
        return MatchEvidence(
            score=score,
            matched=True,
            reasons=["zelfde foto", f"titel {title_sim:.0%}"],
            image_similarity=image_sim,
            title_similarity=title_sim,
        )

    if title_sim >= config.TITLE_SIM_ALONE:
        return MatchEvidence(
            score=score,
            matched=True,
            reasons=[f"titel bijna identiek ({title_sim:.0%})"],
            image_similarity=image_sim,
            title_similarity=title_sim,
        )

    return MatchEvidence(
        score=min(score, config.MATCH_MIN_SCORE - 0.01),
        matched=False,
        reasons=[],
        image_similarity=image_sim,
        title_similarity=title_sim,
    )


@dataclass
class Group:
    """Een set aanbiedingen van hetzelfde product."""

    gid: str
    offers: list[Offer] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def match_size(self) -> int:
        return len(self.offers)

    @property
    def saving_eur(self) -> float | None:
        """Wat je te veel betaalt als je het duurste lid van de groep pakt."""
        return self.spread

    @property
    def cheapest(self) -> Offer | None:
        priced = [o for o in self.offers if o.price is not None]
        return min(priced, key=lambda o: o.price) if priced else None

    @property
    def spread(self) -> float | None:
        prices = [o.price for o in self.offers if o.price is not None]
        if len(prices) < 2:
            return None
        return round(max(prices) - min(prices), 2)


def group_offers(
    offers: list[Offer],
    hashes: dict[str, int] | None = None,
    *,
    use_images: bool = True,
    limit: int | None = None,
) -> list[Group]:
    """Cluster aanbiedingen tot groepen van hetzelfde product.

    Bewust *geen* union-find: één twijfelachtige schakel zou dan hele
    families generieke producten aan elkaar plakken (24 verschillende
    USB-C-kabels in één groep). Elk lid moet daarom aan de anker van zijn
    groep gekoppeld zijn, en elke koppeling moet hard bewijs hebben.
    """
    hashes = hashes or {}
    limit = limit or config.MAX_MATCH_PAIRS
    keys = {id(o): (o.store, o.pid) for o in offers}

    edges: list[tuple[float, Offer, Offer, list[str]]] = []
    checked = 0
    for a, b in itertools.combinations(offers, 2):
        if a.store == b.store and a.pid == b.pid:
            continue
        checked += 1
        if checked > limit:
            break
        evidence = pair_evidence(a, b, hashes, use_images=use_images)
        if evidence.matched:
            edges.append((evidence.score, a, b, evidence.reasons))

    # Sterkste bewijs eerst, zodat het anker van een groep het meest
    # betrouwbare lid is.
    edges.sort(key=lambda item: item[0], reverse=True)

    group_of: dict[tuple[str, str], int] = {}
    members: dict[int, list[Offer]] = {}
    reasons: dict[int, list[str]] = {}
    next_gid = 1

    for score, a, b, why in edges:
        ga, gb = group_of.get(keys[id(a)]), group_of.get(keys[id(b)])

        if ga is None and gb is None:
            gid = next_gid
            next_gid += 1
            group_of[keys[id(a)]] = gid
            group_of[keys[id(b)]] = gid
            members[gid] = [a, b]
            reasons[gid] = list(why)
            continue

        if ga is not None and gb is not None:
            continue  # beide al ingedeeld: geen groepen samenvoegen (kettingen)

        gid = ga if ga is not None else gb
        if len(members[gid]) >= config.MAX_GROUP_SIZE:
            continue

        newcomer = a if ga is not None else b
        # Complete linkage: het nieuwe lid moet bij *alle* bestaande leden
        # passen, niet alleen bij de anker. Anders plakt een tussenproduct dat
        # op twee verschillende artikelen lijkt die twee alsnog aan elkaar.
        if not all(
            pair_evidence(member, newcomer, hashes, use_images=use_images).matched
            for member in members[gid]
        ):
            continue

        group_of[keys[id(newcomer)]] = gid
        members[gid].append(newcomer)
        reasons[gid].extend(why)

    groups: list[Group] = []
    for gid, group_members in members.items():
        group_members.sort(key=lambda o: (o.price is None, o.price or 0.0))
        groups.append(
            Group(gid=f"g{gid}", offers=group_members, reasons=sorted(set(reasons.get(gid, []))))
        )

    # Grootste groepen eerst, daarna de groepen met het meeste prijsverschil.
    groups.sort(key=lambda g: (-len(g.offers), -(g.spread or 0.0)))

    cheapest_overall = min((o.price for o in offers if o.price is not None), default=None)
    for group in groups:
        cheapest = group.cheapest
        spread = group.spread
        for offer in group.offers:
            offer.match_id = group.gid
            offer.match_size = len(group.offers)
            offer.cheapest = cheapest is not None and offer.pid == cheapest.pid
            offer.saving_eur = spread if offer.cheapest else None

    if cheapest_overall is not None:
        global_cheapest = min(
            (o for o in offers if o.price is not None), key=lambda o: o.price
        )
        global_cheapest.cheapest_overall = True

    return groups
