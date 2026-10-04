"""Parsing van AliExpress op echte bewaarde markup.

De fixture bestaat uit drie onbewerkte kaarten uit een echte zoekopdracht plus
de echte JSON-blob van precies die producten. Daarmee testen we de dingen die
op deze site het makkelijkst stil kapotgaan: prijs, Choice-vlag, verkocht,
badges en de gratis-vanaf-drempel.
"""

from conftest import fixture

from app.stores import aliexpress

SPU_PAIR = "6000000003175120"


def offers():
    return aliexpress.parse_search_html(fixture("aliexpress_cards.html"))


def test_drie_kaarten_met_prijs_en_beeld():
    parsed = offers()
    assert len(parsed) == 3
    assert {o.price for o in parsed} == {3.49, 3.64, 3.99}
    for offer in parsed:
        assert offer.title
        assert offer.url.startswith("https://www.aliexpress.com/item/")
        assert offer.image and offer.image.startswith("http")
        assert offer.currency == "EUR"


def test_choice_komt_uit_de_json_blob_niet_uit_een_badge():
    parsed = offers()
    assert all(o.choice for o in parsed)
    # De Choice-badge is een plaatje; zonder blob zou dit veld leeg blijven.
    assert not any("choice" in " ".join(o.badges).lower() for o in parsed)


def test_verkoopaantallen_zijn_getallen():
    counts = sorted(o.sold_count for o in parsed_ok() if o.sold_count)
    assert counts == [1199, 1285, 23480]
    assert all(o.sold for o in parsed_ok())


def parsed_ok():
    return offers()


def test_gratis_vanaf_drempel_uit_de_badge():
    parsed = offers()
    assert all(o.free_ship_from == 10.0 for o in parsed)
    assert any("Gratis levering vanaf €10" in o.badges for o in parsed)


def test_twee_kaarten_delen_hetzelfde_spu_id():
    parsed = offers()
    same = [o for o in parsed if o.spu_id == SPU_PAIR]
    assert len(same) == 2
    assert {o.price for o in same} == {3.49, 3.64}


def test_zoekurl_zet_de_choice_filter_erop():
    plain = aliexpress.search_url("usb c kabel")
    choice = aliexpress.search_url("usb c kabel", choice_only=True)
    assert "isChoice=y" in choice
    assert "isChoice" not in plain
    assert "usb+c+kabel" in plain


def test_geen_kaarten_geeft_lege_lijst():
    assert aliexpress.parse_search_html("<html><body>leeg</body></html>") == []
