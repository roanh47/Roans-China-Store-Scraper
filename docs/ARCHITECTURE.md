# Hoe het werkt

## Stroom

```
zoekterm
   │
   ├─ AliExpress  ─ Playwright ─ HTML ─ parse ─ aanbiedingen
   └─ Temu        ─ Playwright ─ HTML ─ muur? ─ aanbiedingen of "geblokkeerd"
   │
   ├─ foto's ophalen + dHash/aHash (parallel)
   ├─ matchen: structuur ▸ foto + titel ▸ titel
   ├─ winkelwagenregels (Choice-drempel, gratis-vanaf)
   └─ JSON → UI
```

Alles wat de winkels zelf niet bevestigen wordt als *geschat* gemarkeerd. Er
staat nergens een verzonnen prijs of verzendbedrag in de UI.

## AliExpress: de JSON-blob, niet de badges

De zoekpagina zet `window._dida_config_ = {...}` in de HTML met per product een
object: `x_object_id` (het item-id uit de URL), `formatted_price`, `isChoice`,
`real_trade_count`, `star_rating`, `spu_id`, `pic_group_id`. Dat is de
betrouwbare bron — de DOM-classes zijn gehasht (`us--price-sale--8S2hu0e`) en
veranderen per deploy.

De buitenste blob is géén geldige JSON (het is een JS-literal), dus parsen we
per item: bij elke `"x_object_id"` het omsluitende object opzoeken met
accolade-tellen en dat los json.loaden.

Waarom dit belangrijk is: de **Choice-badge is een plaatje**, niet tekst. Zonder
de blob zou het Choice-vlaggetje bij de meeste artikelen stil leeg blijven.

Voor de DOM-kaarten gebruiken we juist wel prefix-selectors, omdat de
class-suffixen wisselen: `a.search-card-item`, `h3[class*="titleText"]`,
`[class*="us--price"]` (met `aria-label="€2,11"`), `[class*="us--trade"]`,
`[class*="tag--text"]` (met `title`-attribuut). De titel zit ook in `img[alt]`.

## Matchen: drempels uit metingen, niet uit gevoel

Gemeten op 33 echte aanbiedingen (`usb c kabel`, EU):

| signaal | bij échte matches | bij verschillende producten |
| --- | --- | --- |
| titelgelijkenis | 0,23 (gemiddeld) | **tot 0,78** |
| dHash-gelijkenis | 0,5 | **tot 0,70** |
| `pic_group_id` | uniek (24/24) | — |
| `spu_replace_id` | **niet bruikbaar** | verwees bij 253 koppels naar hetzelfde id |

Daaruit volgt:

* **Structuur is hard bewijs**: gelijk `spu_id` of `pic_group_id` = match.
* **`spu_replace_id` doet niet mee.** Dat is de *bundel-herkomst* van AliExpress'
  SSR-mechaniek: tientallen ongerelateerde artikelen verwijzen naar hetzelfde
  herkomst-id. Wie dit als match-signaal gebruikt, plakt het halve zoekresultaat
  aan elkaar. (Dat gebeurde in een eerdere versie: 24 verschillende USB-C-kabels
  in één groep.)
* **Beeld alleen is niet genoeg**: vier ongerelateerde producten deelden exact
  dezelfde (placeholder-)foto, hamming-afstand 0. Daarom moet bij een
  beeldmatch ook de titel genoeg lijken (`IMAGE_SIM_MIN` 0,91 *en*
  `TITLE_SIM_WITH_IMAGE` 0,45).
* **Titel alleen** moet bijna identiek zijn: `TITLE_SIM_ALONE` 0,85, ruim boven
  de gemeten 0,78 van verschillende producten.

Clustering gebeurt met **complete linkage**: een nieuw lid moet bij *alle*
bestaande leden passen. Bij gewone union-find kan A-B en B-C samen A en C in één
groep trekken, ook als A en C niets met elkaar te maken hebben. Er zit een test
op die dat afdwingt (`test_clustering_weigert_ketens`).

Gevolg, eerlijk: op één winkel vind je weinig groepen — in de gemeten steekproef
precies één duo (€ 3,49 vs € 3,64, hetzelfde `spu_id`). Dat is de waarheid van
die resultaten, geen fout in de tool. Het matchen wordt pas echt interessant met
een tweede winkel erbij.

## Winkelwagen

* **Choice** (AliExpress): de som van de Choice-artikelen in de wagen. Vanaf
  € 10 gaan díe artikelen gratis én versneld op de post. Daaronder rekenen we
  `SHIPPING_FALLBACK_EUR` (2,99) per regel en zeggen we dat er nog € X bij moet.
* **Gratis levering vanaf € X**: staat als badge op de kaart en geldt over de
  hele bestelling.
* Zegt de kaart zelf "Gratis verzending", dan is dat leidend (0,00, niet geschat).

## Temu

Geprobeerd op 2026-10-04, alle vier de routes vanaf deze server:

| route | resultaat |
| --- | --- |
| `/search_result.html?search_key=...` | doorverwezen naar `/login.html` |
| productpagina `...-g-<id>.html` | idem, `/login.html?from=...` |
| `m.temu.com` met mobiele user-agent | geen producten |
| niet-headless Chromium onder xvfb | idem |
| `api/poppy/v1/search` | 403/500 (eist `anti-content`-token) |

Dus: **geen gast-scraping mogelijk**. De module meldt dat als status `blocked`,
met een deeplink. Met cookies van een ingelogd account (`data/temu-cookies.json`,
buiten de repo) wordt dezelfde code wél gebruikt; de parselogica staat klaar maar
is nooit op een ongeblokkeerde pagina bewezen — dat staat er ook zo in de code.

## Cache en poorten

Zoekresultaten 5 minuten in het geheugen (`SEARCH_CACHE_TTL_S`), inclusief de
`Offer`-objecten, zodat `/api/cart` met precies dezelfde prijzen rekent als de
zoekopdracht. Dezelfde query tegelijk? Eén run, de rest wacht op het resultaat
(single-flight).

Poort 8304, gepubliceerd op `127.0.0.1` (niet het LAN op). In de container
luistert de app op `0.0.0.0` — dat moet, anders komt de poortmapping er niet
bij; de host-binding is de echte grens.

`dns: [1.1.1.1, 1.0.0.1]` staat expliciet in de compose-file. Reden: de oude
AliExpress-container had een `resolv.conf` van vóór de DNS-wijziging op de host
("no external nameservers"), waardoor hij niets kon resolven en maandenlang dood
was zonder dat iemand het zag.
