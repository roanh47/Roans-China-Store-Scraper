"""De Choice-regel van AliExpress, doorgerekend.

Choice-artikelen gaan gratis én versneld op de post zodra er voor minstens
€ 10 aan Choice-artikelen in de wagen zit. Daaronder is de verzending
onbekend — dan rekenen we een schatting en zeggen we dat.
"""

from conftest import offer

from app import cart, config


def choice_offer(price, **kwargs):
    return offer(pid=str(price), price=price, choice=True, store="aliexpress", **kwargs)


def test_onder_de_drempel_is_verzending_een_schatting():
    summary = cart.evaluate([cart.CartLine(choice_offer(3.49)), cart.CartLine(choice_offer(3.64))])
    assert summary.choice_total == 7.13
    assert summary.choice_threshold == config.CHOICE_MIN_EUR
    assert summary.choice_threshold_met is False
    assert summary.choice_missing == 2.87
    assert summary.shipping_estimated is True
    assert summary.shipping_total == round(2 * config.SHIPPING_FALLBACK_EUR, 2)
    assert summary.total == round(7.13 + summary.shipping_total, 2)
    assert any("2.87" in note for note in summary.notes)
    assert all(line.shipping_estimated for line in summary.lines)


def test_boven_de_drempel_is_verzending_gratis():
    summary = cart.evaluate(
        [
            cart.CartLine(choice_offer(3.49)),
            cart.CartLine(choice_offer(3.64)),
            cart.CartLine(choice_offer(3.99)),
        ]
    )
    assert summary.choice_total == 11.12
    assert summary.choice_threshold_met is True
    assert summary.choice_missing == 0.0
    assert summary.shipping_total == 0.0
    assert summary.total == 11.12
    assert summary.shipping_estimated is False
    assert all("Choice" in (line.note or "") for line in summary.lines)


def test_precies_op_de_drempel_telt_als_gehaald():
    summary = cart.evaluate([cart.CartLine(choice_offer(5.0)), cart.CartLine(choice_offer(5.0))])
    assert summary.choice_total == 10.0
    assert summary.choice_threshold_met is True


def test_gratis_vanaf_drempel_over_de_hele_bestelling():
    lines = [
        cart.CartLine(offer("1", price=9.0, choice=False, free_ship_from=10.0)),
        cart.CartLine(offer("2", price=4.0, choice=False, free_ship_from=10.0)),
    ]
    summary = cart.evaluate(lines)
    assert summary.items_total == 13.0
    assert summary.choice_total == 0.0
    assert summary.shipping_total == 0.0
    assert summary.total == 13.0
    assert all("vanaf" in (line.note or "") for line in summary.lines)


def test_onder_de_gratis_vanaf_drempel_blijft_een_schatting():
    summary = cart.evaluate([cart.CartLine(offer("1", price=4.0, choice=False, free_ship_from=10.0))])
    assert summary.shipping_estimated is True
    assert summary.shipping_total == config.SHIPPING_FALLBACK_EUR


def test_kaart_die_gratis_zegt_krijgt_voorrang():
    line = cart.CartLine(
        offer("1", price=2.5, choice=False, shipping_cost=0.0, shipping_text="Gratis verzending")
    )
    summary = cart.evaluate([line])
    assert summary.shipping_total == 0.0
    assert summary.lines[0].note == "Gratis verzending"
    assert summary.lines[0].shipping_estimated is False


def test_aantal_werkt_mee():
    summary = cart.evaluate([cart.CartLine(choice_offer(6.0), qty=2)])
    assert summary.items_total == 12.0
    assert summary.choice_total == 12.0
    assert summary.choice_threshold_met is True
    assert summary.total == 12.0


def test_aanbieding_zonder_prijs_telt_niet_mee():
    summary = cart.evaluate([cart.CartLine(offer("1", price=None, choice=True))])
    assert summary.total == 0.0
    assert summary.choice_threshold_met is False


def test_lege_wagen():
    summary = cart.evaluate([])
    assert summary.total == 0.0
    assert summary.lines == []
    assert summary.choice_threshold_met is False
