# Roans China Store Scraper

Zoek een product bij **AliExpress** en **Temu** tegelijk, zie welke aanbiedingen
hetzelfde product zijn, en welke daarvan het goedkoopst is — inclusief de
verzendregels zoals AliExpress Choice.

Privé-gereedschap: één gebruiker, draait lokaal in Docker, geen accounts nodig.

## Wat het doet

* **Winkelkeuze**: AliExpress, Temu of beide. AliExpress werkt; Temu zet
  niet-ingelogde bezoekers op een loginpagina (zie *Temu* hieronder).
* **Zelfde product terugvinden**: AliExpress vertelt het zelf — `spu_id` is het
  product, `pic_group_id` de fotoset. Voor aanbiedingen zonder zo'n id
  (bijvoorbeeld Temu) vergelijken we de foto's met een perceptuele hash plus de
  titel, met drempels die op echte resultaten gemeten zijn.
* **Choice-regel**: Choice-artikelen gaan gratis én versneld op de post zodra er
  voor minstens **€ 10** aan Choice-artikelen in je wagen zit. De winkelwagenbalk
  laat zien hoeveel je nog tekortkomt. Daarnaast leest hij de
  `Gratis levering vanaf € 10`-regel van de kaart.
* **Nooit verzinnen**: is een verzendbedrag niet bevestigd door de winkel, dan
  staat er *geschat* bij en zie je waarmee gerekend is.

## Draaien

```bash
cd /home/roan/docker/Roans-China-Store-Scraper
docker compose up -d --build
```

Daarna op **http://127.0.0.1:8304** (poort 8304 is gekozen omdat 8300-8303 al
bezet zijn: OSINT, skin flipper, trading, server-manager).

Extern bereikbaar via Cloudflare? Maak in Zero Trust een Public Hostname
`china-store-scraper.roanheemstra.nl` → `http://127.0.0.1:8304`. De container
publiceert alleen op loopback, dus het LAN ziet hem niet.

Zonder Docker:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && playwright install --with-deps chromium
python -m app.main
```

## Temu

Temu stuurt bezoekers **zonder account** naar `/login.html`, ook bij
productpagina's. Gemeten op 2026-10-04 vanaf deze server, met vier routes
(gewone browser, mobiele user-agent, niet-headless onder xvfb, en de interne
`poppy`-API): alle vier een muur of een 403. Dat is beleid, niet een IP-blokkade.

Daarom doet de Temu-module drie dingen:

1. proberen — en als er cookies van een ingelogd account klaarstaan, die
   gebruiken;
2. **eerlijk "geblokkeerd" melden** in de UI in plaats van doen alsof er geen
   resultaten zijn;
3. een deeplink maken zodat je zelf in één klik verder kijkt.

Wil je echte Temu-prijzen, zet dan cookies van een ingelogd account in
`data/temu-cookies.json` (staat in `.gitignore`, komt nooit in de repo en
wordt niet gelogd). Formaat: de cookies-array van Playwright, of één regel
`naam=waarde; naam2=waarde2`.

## API

```bash
curl 'http://127.0.0.1:8304/api/search?q=usb+c+kabel&stores=aliexpress'
curl 'http://127.0.0.1:8304/api/search?q=usb+c+kabel&choice=1&noimages=1'
curl -X POST http://127.0.0.1:8304/api/cart -H 'content-type: application/json' \
  -d '{"query":"usb c kabel","items":[{"store":"aliexpress","pid":"1005008494569058"}]}'
```

| endpoint | wat |
| --- | --- |
| `GET /` | de UI |
| `GET /healthz` | status, versie, cachegrootte |
| `GET /api/stores` | welke winkels er zijn en hun standaardstatus |
| `GET /api/search` | zoeken (`q`, `stores`, `choice`, `noimages`, `limit`, `refresh`) |
| `POST /api/cart` | mandje doorrekenen, met de Choice-drempel |

Resultaten gaan 5 minuten in een cache; de winkelwagen rekent met dezelfde
aanbiedingen, zodat prijzen in het mandje niet stilletjes veranderen.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

De tests draaien voor een groot deel op **echte bewaarde HTML** in
`tests/fixtures/` (drie onbewerkte AliExpress-kaarten met de echte JSON-blob,
plus de echte Temu-loginpagina). Daarmee staan prijs, Choice-vlag, verkocht,
badges en de muurdetectie vast.

## Indeling

```
app/
  config.py        instellingen en drempels
  browser.py       Playwright: één Chromium, Nederlandse locale
  prices.py        prijsnotaties ("€2,11", "US $3.19", bereiken)
  images.py        foto's ophalen + dHash/aHash
  matching.py      zelfde product: structuur, foto, titel
  cart.py          Choice-drempel en verzendkosten
  search.py        parallel scrapen, matchen, cachen
  main.py          Flask-API en UI
  stores/          aliexpress.py, temu.py, base.py
  web/             index.html, app.js, style.css (zwart/paars)
docs/ARCHITECTURE.md  hoe het werkt en waarom de drempels zo staan
tests/                tests + echte HTML-fixtures
```
