# Het Bio Lijstje

Elke ochtend de lopende biologische groente- en fruitaanbiedingen van AH,
Jumbo, Lidl, Aldi, Dirk en Plus, naast elkaar op één pagina. Geen
tabs, geen doorklikken, geen advertenties.

**Live: [hetbiolijstje.nl](https://hetbiolijstje.nl/)** — en de seizoenskalender
op [hetbiolijstje.nl/seizoen](https://hetbiolijstje.nl/seizoen/).

Dit is de broncode. Je kunt hem zelf draaien op een Raspberry Pi: geen account,
geen centrale server, geen winstoogmerk. MIT-licentie.

## Hoe het werkt

Een Python-script draait één keer per dag op een Raspberry Pi met Home
Assistant OS. Het haalt per winkel de volledige actiecatalogus op bij de
[PrijsProfeet-API](https://www.prijsprofeet.nl/), filtert daar de biologische
groente en het fruit uit, en schrijft het resultaat naar `bio_prices.json`.
Voor Lidl komt er nog een scrape van Folderz.nl bij, want PrijsProfeet heeft
daar maar ~180 producten. Daarna pusht de Pi het resultaat naar deze repo, en
GitHub Pages serveert het.

Twee bestanden, elk met één eigenaar: **jij** bewerkt `template.html`, de **Pi**
genereert daar `index.html` uit. Dat klinkt omslachtig maar is er met reden —
toen beide bestanden door beide partijen werden aangeraakt, overschreef de
dagelijkse push drie keer een ontwerpwijziging.

## Wat er moeilijk aan is

Filteren op "biologisch" en "groente of fruit" klinkt simpeler dan het is. De
lastigste beslissingen, met de reden erbij, staan als commentaar in
[`fetch_bio_prices.py`](fetch_bio_prices.py). De kern:

- **Het bio-label van de bron alleen is niet genoeg.** PrijsProfeet tagt een
  reeks Jumbo-huismerkproducten als bio die dat niet zijn, waaronder
  "Pastasaus Tomaat Spekjes". Vijftien niet-biologische producten stonden
  daardoor live. Nu moeten het label én de productnaam allebei "bio" zeggen.
  Uitzondering: bij een volledig biologische keten zegt geen enkele
  productnaam "bio", dus daar zou het label volstaan (`VOLLEDIG_BIO_WINKELS`).
- **Een gerecht met groente erin is geen groente.** Soep, saus, pesto, quiche,
  hummus, chips — allemaal geweerd op naam, want de categorie van de bron redt
  het niet: één keten zette aardappelchips, honing en knäckebröd zelf onder
  "groente-fruit". Die staat er daarom niet meer in — zie hieronder.
- **Elk trefwoord en elk filter is eerst gemeten** tegen de volledige catalogus
  van alle ketens, vóór het in de code kwam. Wat niets opleverde, is er
  niet in gegaan. Dat is niet perfectionisme: "sla" als voorvoegsel matchte
  vrolijk Slavinken, en "appel" haalde appelsap binnen.
- **Verse producten en voorraadproducten staan apart**, want een blik tomaten
  hoort niet tussen de losse tomaten.

## Wat het niet doet

- **Geen prijsvergelijking tussen winkels.** Er zijn simpelweg te weinig
  bio-acties om zinnige overlap te vinden — vaak een handvol per winkel per
  week — en de EAN-dekking die daarvoor nodig is ontbreekt bij Aldi en Lidl.
- **Geen bedrag bij stapelkortingen.** Als een aanbieding pas vanaf twee stuks
  geldt, staat dat er wel bij, maar wat één stuk kost weten we niet: die
  tussentrap zit niet in de brondata, en de winkelsites blokkeren het uitlezen.
  Liever een gat benoemen dan een getal verzinnen.
- **Geen live prijzen**, alleen aanbiedingen. Een doorlopende prijslijst zou
  een bron vereisen die er niet is.

## Zelf draaien

Je hebt een Raspberry Pi met **Home Assistant OS** nodig (niet kale Raspberry
Pi OS) en SSH-toegang.

```bash
# vanaf je eigen machine, in de repo
scp fetch_bio_prices.py root@<pi-ip>:/addons/bio_bord/
scp hass_addon/* root@<pi-ip>:/addons/bio_bord/
scp template.html manifest.json icon.png sw.js root@<pi-ip>:/addons/bio_bord/www/
```

Daarna op de Pi:

```bash
ha store reload && ha apps install local_bio_bord && ha apps start local_bio_bord
```

De pagina staat dan op `http://<pi-ip>:8099/`. De fetch draait bij elke start en
daarna dagelijks om 06:00; de data staat persistent in `/share/bio_bord/data/`,
dus een rebuild gooit je prijsgeschiedenis niet weg.

### Drie dingen die echt fout gaan als je ze vergeet

1. **`ha apps rebuild`, niet `restart`.** Een restart start het bestaande image
   opnieuw op zónder je gewijzigde broncode in te bouwen. Je zit dan naar oude
   code te kijken en snapt niet waarom je fix niets doet.
2. **Regeleindes moeten LF zijn.** CRLF in `run.sh` laat de add-on niet starten
   ("exec /run.sh: no such file or directory" — de kernel zoekt een interpreter
   `sh\r`), en in de `Dockerfile` belandt het in de crontab-regel waardoor de
   cron stil niet draait. Er staat een `.gitattributes` die LF afdwingt; na een
   `scp` vanaf Windows is `tr -d '\r'` een verstandige gordel.
3. **Kopieer wijzigingen ook naar de Pi.** Een aanpassing die alleen in deze
   repo staat, wordt bij de eerstvolgende push overschreven door wat de Pi nog
   heeft.

### Optioneel: publiceren via GitHub Pages

De add-on kan na elke fetch naar een GitHub-repo pushen die je aan GitHub Pages
koppelt. Maak een fine-grained token met Contents-rechten op alleen die repo, en
zet het via de add-on-configuratie in Home Assistant (Instellingen > Add-ons >
Het Bio Lijstje > Configuratie), of via de Supervisor-API:

```bash
curl -X POST -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"options":{"github_token":"<token>","github_repo":"<gebruiker>/<repo>"}}' \
  http://supervisor/addons/local_bio_bord/options
```

Het token staat nooit in de broncode: het komt uit de door Supervisor beheerde
optie-opslag en gaat als omgevingsvariabele mee naar de fetch.

## Aanpassen

De knoppen die je waarschijnlijk zoekt, staan bovenin `fetch_bio_prices.py`:
`AANBIEDINGEN_STORES` (welke winkels), `AGF_KEYWORDS` (wat als groente of fruit
telt), `EXCLUDED_CATEGORIES` en `_NIET_AGF_PATRONEN` (wat er juist uit moet). Het
uiterlijk zit in `template.html`.

De seizoenskalender en `/over/` zijn geen losse bestanden maar generaties: pas
`seizoen/seizoensdata.json` aan, draai `python seizoen/bouw_paginas.py`, en
controleer met `python seizoen/controleer_seizoen.py` en
`python seizoen/sitemap_regels.py`. Die controle bestaat omdat de generator
zonder fout kan draaien en toch onzin kan opleveren — een plaatshouder die
blijft staan, of een canonical die naar de verkeerde maand wijst.

Voeg je een winkel of een trefwoord toe? **Meet eerst wat het doet tegen de hele
catalogus, niet tegen de lijst van vandaag.** Twee keer ging dat mis:

- Ekoplaza leverde 23 treffers waarvan 21 quiche en chips. Na twee rondes extra
  filters kwamen er alsnog honing, crackers, knäckebröd en kombucha door. Hun
  `unified_category` zegt niets, dus dat bleef terugkomen; de keten staat nu in
  `KANDIDAAT_WINKELS` in plaats van in de lijst.
- Een regel die alles met een hoeveelheid in milliliters zou weren, kostte niets
  tegen de aanbiedingen van dat moment. Tegen de hele catalogus haalde hij één
  product weg dat er wél hoort: "Bio appelmoes".

## Bijdragen

Issues en pull requests zijn welkom — vooral voor extra winkels, betere
filtering, of een supermarkt die je mist. Prijsdata komt van
[PrijsProfeet](https://www.prijsprofeet.nl/); bronvermelding is daar verplicht
en dat is hier dus geen vrijblijvendheid.

## Licentie

MIT — zie [LICENSE](LICENSE).
