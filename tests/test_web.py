"""Web-API: invoervalidatie, bedrading en de echte serialisatie."""

import pytest
from conftest import offer

from app import search as search_module
from app.main import app as flask_app
from app.stores.base import StoreResult


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def nep_resultaten(query, limit=None):
    """Twee winkels, zonder netwerk."""
    es = [
        offer("1", price=3.49, spu_id="x", image="i1", store="aliexpress"),
        offer("2", price=3.64, spu_id="x", image="i2", store="aliexpress"),
    ]
    temu = [offer("9", price=9.0, choice=False, image="i3", store="temu")]
    return es, temu


def patch_stores(monkeypatch):
    from app.stores import aliexpress, temu

    es, te = nep_resultaten(None)
    monkeypatch.setattr(aliexpress, "search", lambda query, limit=None: StoreResult(
        store="aliexpress", status="ok", offers=es, elapsed_s=1.0))
    monkeypatch.setattr(temu, "search", lambda query, limit=None: StoreResult(
        store="temu", status="blocked", offers=[], note="Temu vraagt om inloggen", elapsed_s=0.5))
    return es, te


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert "version" in body


def test_pagina_noemt_de_naam_en_de_choice_drempel(client):
    response = client.get("/")
    assert response.status_code == 200
    tekst = response.get_data(as_text=True)
    assert "Roans" in tekst
    assert "China Store Scraper" in tekst
    assert "Choice" in tekst


def test_stores_endpoint(client):
    body = client.get("/api/stores").get_json()
    namen = [item["id"] for item in body["stores"]]
    assert namen == ["aliexpress", "temu"]


def test_zoeken_zonder_zoekterm_is_400(client):
    response = client.get("/api/search")
    assert response.status_code == 400
    assert "zoekterm" in response.get_json()["error"]


def test_onbekende_winkel_is_400(client):
    response = client.get("/api/search?q=kabel&stores=bol")
    assert response.status_code == 400
    assert "bol" in response.get_json()["error"]


def test_te_hoge_limit_is_400(client):
    assert client.get("/api/search?q=kabel&limit=9999").status_code == 400
    assert client.get("/api/search?q=kabel&limit=abc").status_code == 400


def test_vlaggen_worden_doorgegeven(client, monkeypatch):
    gezien = {}

    def fake_run(query, stores, **kwargs):
        gezien["query"] = query
        gezien["stores"] = stores
        gezien.update(kwargs)

        class Stub:
            def to_dict(self):
                return {"ok": True}

        return Stub()

    monkeypatch.setattr(search_module, "run_search", fake_run)
    response = client.get("/api/search?q=usb+c+kabel&stores=temu&choice=1&noimages=1&refresh=1")
    assert response.status_code == 200
    assert gezien["query"] == "usb c kabel"
    assert gezien["stores"] == ["temu"]
    assert gezien["choice_only"] is True
    assert gezien["use_images"] is False
    assert gezien["refresh"] is True


def test_fout_in_de_scraper_geeft_502_met_echte_tekst(client, monkeypatch):
    def ontplof(query, stores, **kwargs):
        raise RuntimeError("Chromium startte niet")

    monkeypatch.setattr(search_module, "run_search", ontplof)
    response = client.get("/api/search?q=kabel")
    assert response.status_code == 502
    assert "Chromium startte niet" in response.get_json()["error"]


def test_echte_serialisatie_met_beide_winkels_en_een_match(client, monkeypatch):
    patch_stores(monkeypatch)
    body = client.get("/api/search?q=een-heel-unieke-zoekterm-1&noimages=1&refresh=1").get_json()

    # Temu is in deze nepwinkel geblokkeerd: hij levert dus geen aanbiedingen.
    assert body["counts"]["offers"] == 2
    assert body["counts"]["per_store"] == {"aliexpress": 2, "temu": 0}
    assert body["choice_only"] is False
    assert body["use_images"] is False
    assert body["limit"] == search_module.config.MAX_RESULTS_PER_STORE
    assert body["meta"]["choice_min_eur"] == 10.0

    statussen = {item["store"]: item["status"] for item in body["stores"]}
    assert statussen == {"aliexpress": "ok", "temu": "blocked"}
    assert body["stores"][1]["note"]

    assert len(body["groups"]) == 1
    groep = body["groups"][0]
    assert groep["size"] == 2
    assert groep["spread"] == 0.15
    assert "spu_id" in " ".join(groep["reasons"])

    eerste = body["offers"][0]
    assert eerste["match_id"]
    assert eerste["cheapest"] is True
    assert eerste["store_label"] == "AliExpress"


def test_choice_filter_en_beeldmatch_staan_aan_in_de_cache_sleutel(client, monkeypatch):
    patch_stores(monkeypatch)
    a = client.get("/api/search?q=unieke-term-2&noimages=1").get_json()
    b = client.get("/api/search?q=unieke-term-2&noimages=1").get_json()
    assert b["cached"] is True
    assert a["stores"][0]["status"] == "ok"


def test_winkelwagen_met_choice_onder_de_drempel(client, monkeypatch):
    offers = [
        offer("1", price=3.49, choice=True),
        offer("2", price=3.64, choice=True),
    ]
    monkeypatch.setattr(
        search_module, "lookup_offers", lambda q, s, items, **kw: (offers, [])
    )
    response = client.post(
        "/api/cart",
        json={
            "query": "kabel",
            "stores": ["aliexpress"],
            "items": [
                {"store": "aliexpress", "pid": "1"},
                {"store": "aliexpress", "pid": "2"},
            ],
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["choice_total"] == 7.13
    assert body["choice_threshold_met"] is False
    assert body["choice_missing"] == 2.87
    assert body["shipping_estimated"] is True
    assert body["notes"]
    assert len(body["lines"]) == 2


def test_winkelwagen_met_choice_boven_de_drempel(client, monkeypatch):
    offers = [offer("1", price=11.0, choice=True)]
    monkeypatch.setattr(
        search_module, "lookup_offers", lambda q, s, items, **kw: (offers, [])
    )
    body = client.post(
        "/api/cart",
        json={"query": "kabel", "items": [{"store": "aliexpress", "pid": "1", "qty": 1}]},
    ).get_json()
    assert body["choice_threshold_met"] is True
    assert body["shipping_total"] == 0.0
    assert body["total"] == 11.0


def test_winkelwagen_meldt_regels_die_uit_de_cache_zijn(client, monkeypatch):
    monkeypatch.setattr(
        search_module,
        "lookup_offers",
        lambda q, s, items, **kw: ([], [{"store": "aliexpress", "pid": "1", "reason": "niet in cache"}]),
    )
    body = client.post(
        "/api/cart",
        json={"query": "kabel", "items": [{"store": "aliexpress", "pid": "1"}]},
    ).get_json()
    assert body["missing"]
    assert any("opnieuw" in note for note in body["notes"])


def test_winkelwagen_zonder_query_is_400(client):
    assert client.post("/api/cart", json={"items": []}).status_code == 400
    assert client.post("/api/cart", json={"query": "k", "items": "geen lijst"}).status_code == 400


def test_zoekterm_wordt_opgeschoond():
    assert search_module.clean_query("  usb   c   kabel  ") == "usb c kabel"
    assert search_module.clean_query("x" * 400).__len__() <= search_module.config.MAX_QUERY_LEN
    assert search_module.clean_query(None) == ""
