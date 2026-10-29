#!/usr/bin/env python3
"""Controleert dat het schap van de winkel de productnaam vervangt waar we dat
afgesproken hebben, en nergens anders.

    python test_schap.py

Ekoplaza lag er in september uit omdat zijn categorie niets zei en het filter
dus uit de naam moest opmaken wat groente was. Elke ronde vroeg een nieuw
naampatroon, en er kwam toch van alles doorheen. Sinds 29 oktober 2026 kijken
we bij die keten naar retailer_category, de indeling van de winkel zelf: staat
het op het AGF-schap, dan is het groente of fruit, en anders niet.

Dat is een uitzondering, en uitzonderingen moeten klein blijven. Dit bestand
toetst alle vier de kanten:

  1. op het AGF-schap komt ook door wat geen trefwoord draagt;
  2. buiten het AGF-schap valt af wat wel een trefwoord draagt;
  3. de tegencheck op _NIET_AGF_PATRONEN geldt nog steeds op dat schap;
  4. bij elke andere winkel verandert er niets — ook niet bij Aldi, die het
     veld helemaal niet vult.

En de vier categorieen die PrijsProfeet in oktober afsplitste, want die regel
is twee keer eerder stilletjes achterhaald geraakt.
"""

import importlib.util
import sys
from pathlib import Path

HIER = Path(__file__).parent
spec = importlib.util.spec_from_file_location("bio", HIER / "fetch_bio_prices.py")
bio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bio)

fouten = 0


def keur(wat, ok, toelichting=""):
    global fouten
    if ok:
        print(f"  ok    {wat}")
    else:
        fouten += 1
        print(f"  FOUT  {wat}" + (f" — {toelichting}" if toelichting else ""))


def actie(naam, retailer="ekoplaza", schap="AGF", categorie="groente-fruit",
          prijs=1.99, normaal=2.59, tags=("bio",)):
    """Een API-record zoals PrijsProfeet het levert, met alleen de velden waar
    _als_bio_agf_actie naar kijkt."""
    return {
        "name": naam, "retailer": retailer, "retailer_category": schap,
        "unified_category": categorie, "price": prijs, "original_price": normaal,
        "dietary_tags": list(tags), "promotion_status": "active",
    }


# ---------------------------------------------------------------------------
# 1. Het schap is ruimer dan de trefwoorden
# ---------------------------------------------------------------------------
print("Op het AGF-schap van Ekoplaza, zonder trefwoord in de naam:")
# Alle vier stonden op 29 oktober 2026 in de aanbieding en werden gemist: geen
# van deze namen draagt een woord uit _AGF_SUBSTRING of _AGF_TAIL.
for naam in ["Soepgroenten", "Paddenstoelenmix", "Butternut pompoenblokjes",
             "Aubergine"]:
    keur(f"{naam!r} komt door", bio._als_bio_agf_actie(actie(naam)) is not None,
         "het schap zegt AGF, dus de naam hoeft niets te bewijzen")
    keur(f"{naam!r} zou op naam alleen afvallen", not bio._is_agf(naam),
         "zo niet, dan bewijst dit geval niets meer en mag het weg")


# ---------------------------------------------------------------------------
# 2. Buiten het schap telt het trefwoord niet
# ---------------------------------------------------------------------------
print("\nBuiten het AGF-schap, met een trefwoord in de naam:")
# De twee kant-en-klaarmaaltijden die het naamfilter op 29 oktober doorliet.
keur("'Taco beans - rode bonen met chipotle & komijn' valt af",
     bio._als_bio_agf_actie(actie(
         "Taco beans - rode bonen met chipotle & komijn",
         schap="VLEES, VLEESWAREN EN VIS",
         categorie="soepen-conserven-sauzen")) is None,
     "komt binnen via 'bonen' als staart")
keur("'Edamame green curry - edamame met citroengras & limoenblad' valt af",
     bio._als_bio_agf_actie(actie(
         "Edamame green curry - edamame met citroengras & limoenblad",
         schap="VLEES, VLEESWAREN EN VIS")) is None,
     "stond bij de bron zelfs onder groente-fruit")
keur("een leeg schap valt af",
     bio._als_bio_agf_actie(actie("Witlof", schap=None)) is None,
     "geen schap is geen bewijs; bij Ekoplaza is het veld altijd gevuld")
keur("'agf' in kleine letters telt ook",
     bio._als_bio_agf_actie(actie("Witlof", schap="agf")) is not None,
     "de winkel schrijft het nu in hoofdletters, dat hoeft niet zo te blijven")


# ---------------------------------------------------------------------------
# 3. De tegencheck blijft gelden
# ---------------------------------------------------------------------------
print("\nDe tegencheck op _NIET_AGF_PATRONEN geldt ook op het AGF-schap:")
# "Siroop aardbei" van EUR 14,35 stond op 1 september een dag als vers fruit op
# de site. Als het schap de naam vervangt, moet dit nog steeds afvallen.
for naam, waarom in [
    ("Siroop aardbei", "siroop"),
    ("Vers geperst sap sinaasappel", "sap als achtervoegsel"),
    ("Tomatensoep", "soep"),
    ("Groentecracker rode biet", "cracker"),
]:
    keur(f"{naam!r} valt af", bio._als_bio_agf_actie(actie(naam)) is None, waarom)


# ---------------------------------------------------------------------------
# 4. Andere winkels merken er niets van
# ---------------------------------------------------------------------------
print("\nBij elke andere winkel verandert er niets:")
keur("AH: naam beslist, niet het schap",
     bio._als_bio_agf_actie(actie(
         "AH Biologisch Pompoen", retailer="albert_heijn",
         schap="VLEES, VLEESWAREN EN VIS")) is not None,
     "een verkeerd schap bij AH mag een echte bio-pompoen niet wegnemen")
keur("Aldi vult het veld niet en werkt gewoon",
     bio._als_bio_agf_actie(actie(
         "Biologische komkommer", retailer="aldi", schap=None)) is not None,
     "0 van 460 Aldi-producten heeft retailer_category")
keur("AH zonder 'bio' in de naam valt af",
     bio._als_bio_agf_actie(actie(
         "Pompoen", retailer="albert_heijn", schap="AGF")) is None,
     "buiten de volledig-bio winkels moet de naam het ook zeggen")
keur("Ekoplaza zonder bio-label valt af",
     bio._als_bio_agf_actie(actie("Witlof", tags=())) is None,
     "het schap vervangt de naam, niet het bio-label")


# ---------------------------------------------------------------------------
# 5. De categorieen die PrijsProfeet in oktober afsplitste
# ---------------------------------------------------------------------------
print("\nCategorieen die in oktober 2026 zijn afgesplitst:")
# 19 oktober: bier-wijn-sterke-drank viel uiteen in drie. 26 oktober: maaltijden
# kwam erbij. Wij sloten alleen de oude verzamelnaam uit — net als bij
# "drogisterij" eind september, en dat kostte toen een douchegel op de homepage.
for categorie in ["bier", "wijn", "sterke-drank", "maaltijden"]:
    keur(f"categorie {categorie!r} is uitgesloten",
         categorie in bio.EXCLUDED_CATEGORIES)
keur("de oude verzamelnaam blijft uitgesloten",
     "bier-wijn-sterke-drank" in bio.EXCLUDED_CATEGORIES,
     "die bestaat nog voor wat niet in te delen valt")
keur("een bio-appelwijn valt af",
     bio._als_bio_agf_actie(actie(
         "Biologische appelwijn", retailer="albert_heijn",
         categorie="wijn")) is None)
keur("groente-fruit blijft er gewoon in",
     "groente-fruit" not in bio.EXCLUDED_CATEGORIES)


print(f"\n{fouten} fout" if fouten else "\nalles goed")
sys.exit(1 if fouten else 0)
