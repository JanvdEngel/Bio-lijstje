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
    keur("zegt dat het alleen groente en fruit is", "groente en fruit" in plat)
    keur("noemt de zes winkels", "Albert Heijn, Jumbo, Lidl, Aldi, Dirk en Plus" in plat)
    keur("vermeldt de bron", "prijsprofeet.nl" in t)
    keur("heeft de bezoekersteller", "gc.zgo.at/count.js" in t)

print()
if fouten:
    sys.exit(f"{fouten} controle(s) niet in orde")
print("de cijfers en het voorbehoud staan er allebei")
