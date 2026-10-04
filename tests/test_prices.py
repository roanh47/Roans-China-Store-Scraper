"""Prijsnotaties van AliExpress en Temu."""

from app.prices import detect_currency, format_eur, parse_price


def test_nederlandse_notatie():
    price = parse_price("€2,11")
    assert price is not None
    assert price.value == 2.11
    assert price.currency == "EUR"


def test_spatie_en_teken_achter():
    assert parse_price("€ 2,11").value == 2.11
    assert parse_price("2,11 €").value == 2.11


def test_duizendscheiding():
    assert parse_price("€ 1.234,56").value == 1234.56
    # Alleen een punt met drie cijfers erachter is duizendtal, geen decimaal.
    assert parse_price("€1.234").value == 1234.0


def test_amerikaanse_notatie():
    price = parse_price("US $3.19")
    assert price is not None
    assert price.value == 3.19
    assert price.currency == "USD"
    assert parse_price("$1,299.00").value == 1299.00


def test_bereik_geeft_ondergrens_en_bovengrens():
    price = parse_price("€2,11 - €5,67")
    assert price is not None
    assert price.value == 2.11
    assert price.value_max == 5.67


def test_geen_prijs():
    assert parse_price("gratis verzending") is None
    assert parse_price("") is None
    assert parse_price(None) is None


def test_valutaherkenning():
    assert detect_currency("€ 3,49") == "EUR"
    assert detect_currency("3,49 EUR") == "EUR"
    assert detect_currency("$4.99") == "USD"


def test_formatteren():
    assert "3,49" in format_eur(3.49)
    assert format_eur(None) != ""
