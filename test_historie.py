#!/usr/bin/env python3
"""Controleert dat de prijsnotitie alleen vergelijkt wat vergelijkbaar is.

    python test_historie.py

De geschiedenis is het enige wat deze site zegt dat de supermarkt zelf niet
zegt: "dit heb ik eerder goedkoper gezien". Op 12 november 2026 bleek elk van
de acht notities op de voorpagina onjuist of ongefundeerd. Twee oorzaken.

**De stapelkorting ging niet mee de geschiedenis in.** Alleen datum, actieprijs
en normale prijs werden bewaard. "AH Biologisch Snoepgroente wortel" stond op
EUR 1,67 bij drie stuks; maanden later kreeg de tomaat onder bijna dezelfde
naam te horen dat hij "eerder EUR 1,67" was geweest. Dat is nooit een
stuksprijs geweest.

**De lopende actie telde zichzelf mee.** De oude code sloot alleen vandaag uit
— "anders vergelijk je met jezelf" stond er al bij — maar omdat de reeks alleen
bij een prijswijziging schrijft, staat de startdag van de lopende actie er
vanaf dag twee gewoon in. "AH Biologisch Mandarijnen" kreeg zo een trofee voor
EUR 2,30, tegen de EUR 2,30 van zijn eigen actie van drie dagen eerder.

Dit bestand toetst beide, plus de overgang: records van voor die datum hebben
geen 'vanaf' en zijn dus van onbekende soort.
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


def item(naam="Bio pompoen", prijs=2.00, normaal=3.00, vanaf=None):
    it = {"naam": naam, "actieprijs": prijs, "normale_prijs": normaal, "soort": "vers"}
    if vanaf is not None:
        it["vanaf"] = vanaf
    return it


def record(datum, prijs, normaal=3.00, vanaf="laat weg"):
    r = {"datum": datum, "actieprijs": prijs, "normale_prijs": normaal}
    if vanaf != "laat weg":
        r["vanaf"] = vanaf
    return r


def draai(eerdere, it, vandaag="2026-11-12"):
    """Eén product door de verrijking, met een eigen geschiedenis."""
    hist = {bio._history_key("AH", it["naam"]): list(eerdere)}
    bio.enrich_and_record_history("AH", [it], hist, vandaag)
    return it, hist[bio._history_key("AH", it["naam"])]


# ---------------------------------------------------------------------------
# 1. Een stapelprijs is geen stuksprijs
# ---------------------------------------------------------------------------
print("Een prijs die bij drie stuks gold telt niet mee voor een los stuk:")
it, _ = draai([record("2026-09-28", 1.67, 2.29, vanaf=3)], item(prijs=2.99, normaal=3.99))
keur("losse prijs vergelijkt niet met een 'vanaf 3'-record",
     "laagste_ooit_prijs" not in it,
     f"kreeg {it.get('laagste_ooit_prijs')}")

it, _ = draai([record("2026-09-28", 1.67, 2.29, vanaf=3)], item(prijs=2.00, normaal=2.29, vanaf=3))
keur("dezelfde voorwaarde vergelijkt wel", it.get("laagste_ooit_prijs") == 1.67)

it, _ = draai([record("2026-09-28", 1.67, 2.29, vanaf=2)], item(prijs=2.00, normaal=2.29, vanaf=3))
keur("een andere voorwaarde valt af", "laagste_ooit_prijs" not in it)


# ---------------------------------------------------------------------------
# 2. De lopende actie vergelijkt niet met zichzelf
# ---------------------------------------------------------------------------
print("\nDe lopende actie telt zichzelf niet mee:")
# Zoals mandarijnen op 12 november: actie begon op de 9e op 2,30 en staat er nog.
eerdere = [record("2026-10-01", 2.79), record("2026-11-09", 2.30)]
it, _ = draai(eerdere, item(prijs=2.30))
keur("de startdag van de eigen actie valt af",
     it.get("laagste_ooit_prijs") != 2.30,
     f"kreeg {it.get('laagste_ooit_prijs')} van {it.get('laagste_ooit_datum')}")
keur("wat overblijft is het oudere, hogere record",
     it.get("laagste_ooit_prijs") == 2.79)
keur("en dus is het er maar één", it.get("eerder_gezien") == 1,
     "met één eerder record toont de pagina geen trofee")

# Dezelfde prijs maanden eerder is wél een echte waarneming.
eerdere = [record("2026-06-01", 2.30), record("2026-11-09", 2.30)]
it, _ = draai(eerdere, item(prijs=2.30))
keur("een oudere waarneming van dezelfde prijs blijft tellen",
     it.get("laagste_ooit_prijs") == 2.30 and it.get("laagste_ooit_datum") == "2026-06-01")

# Een echte prijsdaling moet gewoon zichtbaar blijven.
eerdere = [record("2026-10-01", 1.50), record("2026-11-09", 2.30)]
it, _ = draai(eerdere, item(prijs=2.30))
keur("een echte eerdere lagere prijs blijft staan",
     it.get("laagste_ooit_prijs") == 1.50)


# ---------------------------------------------------------------------------
# 3. Records van voor de wijziging zijn van onbekende soort
# ---------------------------------------------------------------------------
print("\nEen record zonder 'vanaf' komt van voor 12 november 2026:")
it, _ = draai([record("2026-10-01", 1.50, 3.00)], item(prijs=2.00, normaal=3.00))
keur("bruikbaar als beide geen voorwaarde hebben en de normale prijs klopt",
     it.get("laagste_ooit_prijs") == 1.50)

it, _ = draai([record("2026-10-01", 1.50, 3.00)], item(prijs=2.00, normaal=3.00, vanaf=2))
keur("onbruikbaar zodra het huidige item een voorwaarde heeft",
     "laagste_ooit_prijs" not in it)

# 2,29 tegen 3,99 is 74% verschil: een andere verpakking onder dezelfde naam.
it, _ = draai([record("2026-09-28", 1.67, 2.29)], item(prijs=2.99, normaal=3.99))
keur("onbruikbaar bij een sterk afwijkende normale prijs",
     "laagste_ooit_prijs" not in it,
     "dit is precies het tomatengeval van 12 november")

it, _ = draai([record("2026-10-01", 1.50, 3.20)], item(prijs=2.00, normaal=3.00))
keur("een klein verschil in normale prijs is geen bezwaar",
     it.get("laagste_ooit_prijs") == 1.50)

it, _ = draai([record("2026-10-01", 1.50, None)], item(prijs=2.00, normaal=3.00))
keur("zonder normale prijs valt het oude record af",
     "laagste_ooit_prijs" not in it)


# ---------------------------------------------------------------------------
# 4. Wat er vanaf nu wordt weggeschreven
# ---------------------------------------------------------------------------
print("\nNieuwe records dragen de voorwaarde, ook als die er niet is:")
_, reeks = draai([], item(prijs=2.00))
keur("de sleutel staat er altijd in", "vanaf" in reeks[-1],
     "de aanwezigheid van de sleutel bewijst dat het record nieuw is")
keur("zonder voorwaarde is hij None", reeks[-1]["vanaf"] is None)

_, reeks = draai([], item(prijs=2.00, vanaf=3))
keur("met voorwaarde staat het aantal erin", reeks[-1]["vanaf"] == 3)

print("\nEen gewijzigde voorwaarde is een nieuw record:")
eerdere = [record("2026-11-01", 2.00, 3.00, vanaf=None)]
_, reeks = draai(eerdere, item(prijs=2.00, normaal=3.00))
keur("zelfde prijs en zelfde voorwaarde schrijft niets bij", len(reeks) == 1)

eerdere = [record("2026-11-01", 2.00, 3.00, vanaf=None)]
_, reeks = draai(eerdere, item(prijs=2.00, normaal=3.00, vanaf=2))
keur("zelfde prijs maar nu bij 2 stuks schrijft wel bij", len(reeks) == 2,
     "anders verdwijnt het verschil tussen stuks- en stapelprijs")


# ---------------------------------------------------------------------------
# 5. Het getal onder de trofee slaat op de vergelijkbare records
# ---------------------------------------------------------------------------
print("\n'Laagste van N prijzen' telt alleen wat meedeed:")
eerdere = [record("2026-06-01", 3.00, 4.00, vanaf=3),   # andere voorwaarde
           record("2026-07-01", 2.50),                   # oud, normale prijs klopt
           record("2026-08-01", 2.60)]                   # idem
it, _ = draai(eerdere, item(prijs=2.00, normaal=4.00))
keur("de voorwaardelijke en de ver afwijkende tellen niet mee",
     it.get("eerder_gezien") == 0 or "eerder_gezien" not in it,
     f"kreeg {it.get('eerder_gezien')}")

eerdere = [record("2026-07-01", 2.50, 3.00), record("2026-08-01", 2.60, 3.00)]
it, _ = draai(eerdere, item(prijs=2.00, normaal=3.00))
keur("twee bruikbare records geven er ook twee", it.get("eerder_gezien") == 2)
keur("en de laagste daarvan is de laagste", it.get("laagste_ooit_prijs") == 2.50)


print(f"\n{fouten} fout" if fouten else "\nalles goed")
sys.exit(1 if fouten else 0)
