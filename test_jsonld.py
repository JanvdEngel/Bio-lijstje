#!/usr/bin/env python3
"""Controleert de gestructureerde data en de leesbare datum.

    python test_jsonld.py

Op veertien pagina's stond nul JSON-LD, en op de plek waar de versheid van de
lijst hoort te staan las een crawler letterlijk "nog niets geladen" met een leeg
datetime-attribuut.

Eén keuze staat hier expliciet in: nergens Product- of Offer-markup. Die zegt
tegen een zoekmachine dat het product op deze pagina te koop is, en dat is het
niet — wij zijn niet de verkoper en er is niets af te rekenen. De verleiding is
groot omdat er prijzen op de pagina staan, dus deze test houdt dat besluit vast.
"""

import importlib.util
import json
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
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
        print(f"  FOUT  {wat}" + (f" — {extra}" if extra else ""))


# ---------------------------------------------------------------------------
# De leesbare datum
# ---------------------------------------------------------------------------
print("leesbare datum")
# Locale-instellingen zijn geen optie op een kale Alpine-container, dus de
# dag- en maandnamen staan met de hand in de code. Dan moeten ze ook kloppen.
for iso, verwacht in [
    ("2026-01-01T12:00", "donderdag 1 januari 2026 om 12:00"),
    ("2026-09-03T20:42:11", "donderdag 3 september 2026 om 20:42"),
    ("2026-09-07T06:01", "maandag 7 september 2026 om 06:01"),
    ("2026-12-31T23:59", "donderdag 31 december 2026 om 23:59"),
]:
    got = bio._leesbare_datum(iso)
    keur(f"{iso} -> {verwacht}", got == verwacht, f'kreeg "{got}"')

keur("onleesbare invoer geeft geen brok en geen leugen",
     bio._leesbare_datum("nergens") == "nergens")
keur("None geeft geen uitzondering", bio._leesbare_datum(None) is None)

# ---------------------------------------------------------------------------
# De JSON-LD van de voorpagina
# ---------------------------------------------------------------------------
print("\nvoorpagina")
aanb = {
    "AH": [{"naam": "AH Biologisch Witte druiven pitloos", "actieprijs": 1.75,
            "normale_prijs": 3.49, "soort": "vers"}],
    "Jumbo": [],
    "Lidl": [{"naam": "Bio Fairtrade bananen", "actieprijs": 1.49,
              "normale_prijs": 2.19, "soort": "vers"}],
}
script = bio._jsonld(aanb, "2026-09-03T20:42:11")
ruw = script[script.index(">") + 1:script.rindex("</script>")]
try:
    d = json.loads(ruw)
    keur("is geldige JSON", True)
except json.JSONDecodeError as e:
    keur("is geldige JSON", False, str(e))
    sys.exit(1)

keur("@type is CollectionPage", d.get("@type") == "CollectionPage", d.get("@type"))
keur("dateModified is de echte tijd", d.get("dateModified") == "2026-09-03T20:42:11")
keur("taal staat erbij", d.get("inLanguage") == "nl-NL")
keur("hoort bij één website", d.get("isPartOf", {}).get("@type") == "WebSite")
lijst = d.get("mainEntity", {})
keur("mainEntity is een ItemList", lijst.get("@type") == "ItemList")
keur("het aantal klopt met de echte lijst", lijst.get("numberOfItems") == 2,
     str(lijst.get("numberOfItems")))
namen = [i["name"] for i in lijst.get("itemListElement", [])]
keur("de productnamen staan erin",
     any("Fairtrade bananen" in n for n in namen), str(namen[:2]))
keur("de prijs staat erin", any("1,49" in n for n in namen))
keur("de winkel staat erin", any("Lidl" in n for n in namen))
keur("posities lopen vanaf 1",
     [i["position"] for i in lijst.get("itemListElement", [])] == [1, 2])

keur("GEEN Product- of Offer-markup (wij verkopen niets)",
     '"Product"' not in ruw and '"Offer"' not in ruw)
keur("een lege lijst geeft geen verzonnen items",
     json.loads(bio._jsonld({"AH": []}, "2026-09-03T20:42:11")
                .split(">", 1)[1].rsplit("</script>", 1)[0]
                )["mainEntity"]["numberOfItems"] == 0)

# ---------------------------------------------------------------------------
# De veertien gegenereerde pagina's
# ---------------------------------------------------------------------------
print("\ngegenereerde pagina's")
paginas = sorted(HIER.glob("seizoen/*/index.html")) + [
    HIER / "seizoen" / "index.html", HIER / "over" / "index.html"]
paginas = [p for p in paginas if p.exists()]
keur("er zijn veertien pagina's", len(paginas) == 14, f"{len(paginas)}")

zonder = []
kapot = []
zonder_kruimel = []
met_product = []
for p in paginas:
    t = p.read_text(encoding="utf-8")
    blokken = re.findall(r'<script type="application/ld\+json">(.*?)</script>', t, re.S)
    if len(blokken) != 1:
        zonder.append(f"{p.parent.name} ({len(blokken)})")
        continue
    try:
        d = json.loads(blokken[0])
    except json.JSONDecodeError as e:
        kapot.append(f"{p.parent.name}: {e}")
        continue
    if not d.get("breadcrumb", {}).get("itemListElement"):
        zonder_kruimel.append(p.parent.name)
    if '"Product"' in blokken[0] or '"Offer"' in blokken[0]:
        met_product.append(p.parent.name)

keur("elke pagina heeft precies één JSON-LD-blok", not zonder, ", ".join(zonder))
keur("alle blokken zijn geldige JSON", not kapot, "; ".join(kapot))
keur("elke pagina heeft een kruimelpad", not zonder_kruimel, ", ".join(zonder_kruimel))
keur("nergens Product- of Offer-markup", not met_product, ", ".join(met_product))

# De maandpagina's moeten de producten van díe maand opsommen.
data = json.loads((HIER / "seizoen" / "seizoensdata.json").read_text(encoding="utf-8"))
mis = []
for m in data["maanden"]:
    p = HIER / "seizoen" / m["maand"] / "index.html"
    if not p.exists():
        continue
    blok = re.search(r'<script type="application/ld\+json">(.*?)</script>',
                     p.read_text(encoding="utf-8"), re.S)
    lijst = json.loads(blok.group(1)).get("mainEntity", {})
    verwacht = len(m["groente"] + m["fruit"])
    if lijst.get("numberOfItems") != verwacht:
        mis.append(f"{m['maand']}: {lijst.get('numberOfItems')} i.p.v. {verwacht}")
keur("elke maandpagina somt de producten van die maand op", not mis, "; ".join(mis))

print()
if fouten:
    sys.exit(f"{fouten} controle(s) niet in orde")
print("gestructureerde data en datum zijn in orde")
