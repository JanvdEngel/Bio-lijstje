#!/usr/bin/env python3
"""Controleert de cijfers achter /cijfers/.

    python test_cijfers.py

Deze pagina is bedoeld om naar te verwijzen als iemand vraagt hoe vaak bio in
de aanbieding is. Dan moet het getal kloppen, en moet het voorbehoud erbij
staan: het gaat over aanbiedingen en niet over wat er in het schap ligt.
"""

import importlib.util
import sys
from pathlib import Path

HIER = Path(__file__).parent
spec = importlib.util.spec_from_file_location("bio", HIER / "fetch_bio_prices.py")
bio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bio)

fouten = 0


def keur(wat, ok, extra=""):
    global fouten
    if ok:
        print(f"  ok    {wat}")
    else:
        fouten += 1
        print(f"  FOUT  {wat}" + (f" - {extra}" if extra else ""))


print("rekenen")
dagen = {
    "2026-09-01": {"AH": 2, "Jumbo": 0, "Lidl": 0},
    "2026-09-02": {"AH": 4, "Jumbo": 0, "Lidl": 0},
    "2026-09-03": {"AH": 0, "Jumbo": 3, "Lidl": 0},
    "2026-09-04": {"AH": 6, "Jumbo": 1, "Lidl": 2},
}
c = bio.cijfers_uit_dagtellingen(dagen)
keur("vier dagen geteld", c["dagen"] == 4, str(c["dagen"]))
keur("gemiddelde klopt (18/4)", abs(c["gemiddeld"] - 4.5) < 1e-9, str(c["gemiddeld"]))
keur("laagste dag is 2 op 2026-09-01",
     c["laagste"] == 2 and c["laagste_datum"] == "2026-09-01",
     f'{c["laagste"]} op {c["laagste_datum"]}')
keur("hoogste dag is 9", c["hoogste"] == 9, str(c["hoogste"]))
per = {r["winkel"]: r for r in c["per_winkel"]}
keur("Lidl heeft drie nuldagen", per["Lidl"]["nuldagen"] == 3)
keur("Lidl's langste reeks is 3", per["Lidl"]["langste_reeks"] == 3)
keur("Jumbo heeft twee nuldagen, reeks 2", per["Jumbo"]["nuldagen"] == 2
     and per["Jumbo"]["langste_reeks"] == 2)
keur("AH heeft een nuldag maar geen reeks van 2", per["AH"]["nuldagen"] == 1
     and per["AH"]["langste_reeks"] == 1)
keur("meest lege winkel staat bovenaan", c["per_winkel"][0]["winkel"] == "Lidl")

# Een dag waarop een winkel ontbreekt telt niet mee: die nul zegt niets over
# die winkel, net als "geen acties" tegenover "niet opgehaald" op de voorpagina.
half = dict(dagen)
half["2026-09-05"] = {"AH": 1}
keur("onvolledige dag telt niet mee",
     bio.cijfers_uit_dagtellingen(half)["dagen"] == 4)
keur("zonder dagen geen cijfers", bio.cijfers_uit_dagtellingen({}) is None)

print("\nde pagina")
blok = bio.cijferblok_html(c)
keur("kerngetal staat erin", "kerngetal" in blok)
keur("komma en geen punt", "4,5" in blok and "4.5" not in blok)
keur("diagram staat erin", 'class="diagram"' in blok)
keur("diagram heeft een aria-label", "aria-label=" in blok)
keur("tabel staat erin", "cijfertabel" in blok)
keur("leeg geeft geen verzonnen getal",
     "nog niet genoeg gemeten" in bio.cijferblok_html(None))

sjabloon = HIER / "cijfers-sjabloon.html"
keur("het sjabloon bestaat", sjabloon.exists())
if sjabloon.exists():
    t = sjabloon.read_text(encoding="utf-8")
    # Zonder dit valt de test over een zin die in de HTML over twee regels
    # is gewikkeld, en dat zegt niets over de pagina.
    plat = " ".join(t.split())
    keur("heeft de merktekens", bio.CIJFERS_START in t and bio.CIJFERS_EINDE in t)
    keur("geen plaatshouders blijven staan", "{{" not in t)
    keur("canonical wijst naar /cijfers/",
         'href="https://hetbiolijstje.nl/cijfers/"' in t)
    keur("het voorbehoud staat erop",
         "niet over wat er in het schap ligt" in plat)
    # De bronvermelding is contractueel verplicht op de gratis sleutel, en deze
    # pagina heeft een andere voettekst dan de seizoenspagina's: daar staat hij
    # niet in. Haalt iemand de bronregel weg, dan valt dat hier om.
    keur("vermeldt de bron (verplicht)", "prijsprofeet.nl" in t)
    keur("heeft de bezoekersteller", "gc.zgo.at/count.js" in t)

# ---------------------------------------------------------------------------
# Een storing is geen nuldag
# ---------------------------------------------------------------------------
# cijfers_uit_dagtellingen() liet altijd al een dag vallen waarop een winkel
# ontbrak, en de docstring beloofde "alleen dagen waarop alle winkels zijn
# opgehaald". Maar werk_dagtellingen_bij() schreef simpelweg len(acties) voor
# elke winkel en kende de status niet, dus een onbereikbare winkel kwam binnen
# als een echte nul. De belofte en de code liepen uiteen.
print("\nde telling van vandaag")
import tempfile

_tmp = Path(tempfile.mkdtemp())
_echt_pad = bio.DAGTELLINGEN_PATH
try:
    aanbiedingen = {"AH": [1, 2, 3], "Aldi": [], "Jumbo": [1]}

    bio.DAGTELLINGEN_PATH = _tmp / "alles-ok.json"
    dag = bio.werk_dagtellingen_bij(aanbiedingen, "2026-11-12")["2026-11-12"]
    keur("zonder status telt alles mee", dag == {"AH": 3, "Aldi": 0, "Jumbo": 1},
         f"kreeg {dag}")

    bio.DAGTELLINGEN_PATH = _tmp / "aldi-stuk.json"
    dag = bio.werk_dagtellingen_bij(
        aanbiedingen, "2026-11-12",
        {"AH": "ok", "Aldi": "mislukt", "Jumbo": "ok"})["2026-11-12"]
    keur("een mislukte winkel komt er niet in", "Aldi" not in dag, f"kreeg {dag}")
    keur("de rest wel", dag == {"AH": 3, "Jumbo": 1}, f"kreeg {dag}")

    bio.DAGTELLINGEN_PATH = _tmp / "aldi-half.json"
    dag = bio.werk_dagtellingen_bij(
        aanbiedingen, "2026-11-12",
        {"AH": "ok", "Aldi": "onvolledig", "Jumbo": "ok"})["2026-11-12"]
    keur("een half opgehaalde winkel ook niet", "Aldi" not in dag, f"kreeg {dag}")

    # En dan laat de berekening die dag vanzelf vallen.
    c = bio.cijfers_uit_dagtellingen({
        "2026-11-10": {"AH": 2, "Aldi": 0, "Jumbo": 1},
        "2026-11-11": {"AH": 3, "Aldi": 0, "Jumbo": 1},
        "2026-11-12": {"AH": 3, "Jumbo": 1},
    })
    keur("een dag met een ontbrekende winkel telt niet mee", c["dagen"] == 2,
         f"kreeg {c['dagen']}")
    keur("en een echte nul telt nog gewoon als nuldag",
         next(r["nuldagen"] for r in c["per_winkel"] if r["winkel"] == "Aldi") == 2)
finally:
    bio.DAGTELLINGEN_PATH = _echt_pad

print()
if fouten:
    sys.exit(f"{fouten} controle(s) niet in orde")
print("de cijfers en het voorbehoud staan er allebei")
