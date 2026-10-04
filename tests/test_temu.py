"""Temu: de login-muur herkennen en eerlijk melden.

De fixture is de echte pagina die Temu teruggaf aan een niet-ingelogde browser.
"""

from conftest import fixture

from app.stores import temu


def test_echte_loginpagina_wordt_herkend():
    wall = temu.detect_wall(fixture("temu_login.html"))
    assert wall is not None
    assert "login" in wall.lower() or "inlog" in wall.lower()


def test_titel_verraadt_de_muur_ook():
    html = "<html><head><title>Temu | Aanmelden</title></head><body>hallo</body></html>"
    assert temu.detect_wall(html) is not None


def test_gewone_pagina_met_producten_is_geen_muur():
    html = (
        '<html><head><title>Temu</title></head><body>'
        '<a href="/nl/usb-c-kabel-g-601099653345294.html">kabel</a>'
        "</body></html>"
    )
    assert temu.detect_wall(html) is None


def test_deeplink_bevat_de_zoekterm():
    link = temu.deeplink("usb c kabel")
    assert link.startswith("https://www.temu.com/")
    assert "usb+c+kabel" in link or "usb%20c%20kabel" in link


def test_zoeken_op_de_muur_geeft_status_blocked(monkeypatch):
    monkeypatch.setattr(temu, "fetch_search_html", lambda query: fixture("temu_login.html"))
    result = temu.search("usb c kabel")
    assert result.status == "blocked"
    assert result.offers == []
    assert result.note
    assert result.error is None


def test_zoeken_op_een_werkende_pagina_geeft_aanbiedingen(monkeypatch):
    html = (
        '<html><head><title>Temu</title></head><body>'
        '<a href="/nl/usb-c-kabel-100w-g-601099653345294.html">'
        '<img src="https://img.kwcdn.com/product/abc.jpg" alt="USB C kabel 100W">'
        '<span class="price">€ 3,49</span></a>'
        '<a href="/nl/andere-kabel-g-601099653345295.html">'
        '<img src="https://img.kwcdn.com/product/def.jpg" alt="Andere kabel">'
        '<span class="price">€ 4,99</span></a>'
        "</body></html>"
    )
    monkeypatch.setattr(temu, "fetch_search_html", lambda query: html)
    result = temu.search("usb c kabel")
    assert result.status == "ok"
    assert len(result.offers) == 2
    assert {o.price for o in result.offers} == {3.49, 4.99}
    assert all(o.store == "temu" for o in result.offers)
    assert all(o.url.startswith("https://www.temu.com/") for o in result.offers)


def test_pagina_zonder_producten_is_leeg_niet_geblokkeerd(monkeypatch):
    monkeypatch.setattr(temu, "fetch_search_html", lambda query: "<html><body>niets</body></html>")
    result = temu.search("usb c kabel")
    assert result.status == "empty"
    assert result.offers == []


def test_fout_tijdens_ophalen_wordt_gemeld(monkeypatch):
    def kapot(query):
        raise RuntimeError("geen verbinding")

    monkeypatch.setattr(temu, "fetch_search_html", kapot)
    result = temu.search("usb c kabel")
    assert result.status == "error"
    assert "geen verbinding" in (result.error or "")


def test_cookies_lezen_uit_javascriptformaat(tmp_path, monkeypatch):
    pad = tmp_path / "temu-cookies.json"
    pad.write_text('[{"name": "api_uid", "value": "abc", "domain": ".temu.com"}]')
    monkeypatch.setattr(temu.config, "TEMU_COOKIE_FILE", str(pad))
    cookies = temu.load_cookies()
    assert [(c["name"], c["value"]) for c in cookies] == [("api_uid", "abc")]
    assert cookies[0]["domain"] == ".temu.com"


def test_cookies_lezen_uit_platte_tekst(tmp_path, monkeypatch):
    pad = tmp_path / "temu-cookies.txt"
    pad.write_text("api_uid=abc; region=NL\n")
    monkeypatch.setattr(temu.config, "TEMU_COOKIE_FILE", str(pad))
    paren = {(c["name"], c["value"]) for c in temu.load_cookies()}
    assert ("api_uid", "abc") in paren
    assert ("region", "NL") in paren


def test_ontbrekend_cookiebestand_is_geen_fout(tmp_path, monkeypatch):
    monkeypatch.setattr(temu.config, "TEMU_COOKIE_FILE", str(tmp_path / "bestaat-niet.json"))
    assert temu.load_cookies() == []
