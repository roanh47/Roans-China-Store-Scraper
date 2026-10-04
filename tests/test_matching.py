"""Matchen van hetzelfde product: streng waar het moet, niet plakkerig.

De drempels in deze tests komen uit metingen op echte resultaten (zie
docs/ARCHITECTURE.md): twee *verschillende* producten halen een
titelgelijkenis tot 0,78 en een beeldgelijkenis tot 0,70.
"""

from conftest import fixture, offer

import hashlib

from app import images, matching
from app.stores import aliexpress


def hashes_for(*offers):
    """Elke foto een eigen hash, ver uit elkaar (zoals echte verschillende foto's).

    Let op: niet ophogen met 1 — bit 1 verschil is voor een perceptuele hash
    juist *wel* dezelfde foto.
    """
    out = {}
    for offer_ in offers:
        if offer_.image:
            out[offer_.image] = int.from_bytes(
                hashlib.sha1(offer_.image.encode()).digest()[:8], "big"
            )
    return out


def test_zelfde_spu_id_is_een_match():
    a = offer("1", spu_id="spu-9", price=3.49)
    b = offer("2", spu_id="spu-9", price=3.64)
    evidence = matching.pair_evidence(a, b, {}, use_images=False)
    assert evidence.matched
    assert "spu_id" in " ".join(evidence.reasons)

    groups = matching.group_offers([a, b], {}, use_images=False)
    assert len(groups) == 1
    assert groups[0].match_size == 2
    assert groups[0].cheapest.pid == "1"
    assert groups[0].saving_eur == 0.15


def test_generieke_titels_van_andere_producten_matchen_niet():
    a = offer("1", title="240W nylon kabel USB Type C supersnelle Oplaadkabel", image="img-a")
    b = offer("2", title="240W Nylon USB Type-C Supersnelle Oplaadkabel voor Samsung", image="img-b")
    # Dit is precies het koppel dat een te losse drempel wél zou plakken.
    assert matching.title_similarity(a.title, b.title) >= 0.7
    assert not matching.pair_evidence(a, b, hashes_for(a, b)).matched
    assert matching.group_offers([a, b], hashes_for(a, b)) == []


def test_identieke_foto_alleen_is_niet_genoeg():
    """Meerdere ongerelateerde producten kunnen dezelfde placeholder-foto delen."""
    a = offer("1", title="120Gbps Thunderbolt 5 datakabel", image="zelfde")
    b = offer("2", title="Snelle Oplader Platte Telefoonlader 240W", image="zelfde")
    hashes = {"zelfde": 0b1010101010101010101010101010101010101010101010101010101010101010}
    evidence = matching.pair_evidence(a, b, hashes)
    assert evidence.image_similarity == 1.0
    assert not evidence.matched


def test_identieke_foto_plus_lijkende_titel_is_een_match():
    a = offer("1", title="UGREEN USB C kabel 100W nylon grijs CD137", image="foto")
    b = offer("2", title="UGREEN USB C kabel 100W nylon grijs CD137 2 meter", image="foto")
    hashes = {"foto": 1234567}
    assert matching.pair_evidence(a, b, hashes).matched


def test_bijna_identieke_titel_is_genoeg():
    a = offer("1", title="Toocki USB C kabel 100W 2 meter", image="a")
    b = offer("2", title="Toocki USB C kabel 100W 2 meter", image="b")
    evidence = matching.pair_evidence(a, b, hashes_for(a, b))
    assert evidence.matched
    assert "titel" in " ".join(evidence.reasons)


def test_clustering_weigert_ketens(monkeypatch):
    """A-B en B-C mogen A en C niet alsnog samen in één groep stoppen."""
    a, b, c = offer("a"), offer("b"), offer("c")
    sterke_koppels = {frozenset({id(a), id(b)}), frozenset({id(b), id(c)})}

    def fake_pair(x, y, hashes, use_images=True):
        matched = frozenset({id(x), id(y)}) in sterke_koppels
        return matching.MatchEvidence(score=1.0 if matched else 0.0, matched=matched)

    monkeypatch.setattr(matching, "pair_evidence", fake_pair)
    groups = matching.group_offers([a, b, c], {}, use_images=False)
    assert max((g.match_size for g in groups), default=0) <= 2


def test_echte_fixture_geeft_precies_een_duo():
    offers = aliexpress.parse_search_html(fixture("aliexpress_cards.html"))
    groups = matching.group_offers(offers, {}, use_images=False)
    assert len(groups) == 1
    duo = groups[0]
    assert duo.match_size == 2
    assert {o.price for o in duo.offers} == {3.49, 3.64}
    assert duo.cheapest.price == 3.49
    assert duo.saving_eur == 0.15


def test_matchvelden_komen_op_de_aanbieding():
    a = offer("1", spu_id="s", price=2.0)
    b = offer("2", spu_id="s", price=1.5)
    groups = matching.group_offers([a, b], {}, use_images=False)
    assert a.match_id == b.match_id == groups[0].gid
    assert b.cheapest is True
    assert a.cheapest is False
    assert a.match_size == 2


def test_beeldmaten_zijn_symmetrisch():
    assert images.image_similarity(42, 42) == 1.0
    assert images.image_similarity(None, 42) is None
    assert images.image_similarity(0, (1 << 64) - 1) == 0.0
