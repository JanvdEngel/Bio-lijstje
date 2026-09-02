#!/usr/bin/env python3
"""Controleert het AGF-trefwoordfilter op Nederlandse meervouden en
samenstellingen.

    python test_agf.py

Dit bestand bestaat omdat "Bio Fairtrade bananen" (EUR 1,49, was 2,19) drie
weken lang in de API stond en niet op de site. Het trefwoord was "banaan", en
Nederlands verkort de klinker in het meervoud: banaan -> bananen. Het trefwoord
zit letterlijk niet in het meervoud. Datzelfde gold voor "Snoeptomaten"
(tomaat -> tomaten) en "Veldsla" (sla staat er niet los in).

De drie matchklassen zijn niet beredeneerd maar gemeten tegen de volledige
catalogus van 9.165 producten over zeven ketens. De gevallen hieronder zijn de
uitkomst van die meting; wie een klasse verschuift, ziet hier wat dat kost.
"""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "bio", Path(__file__).parent / "fetch_bio_prices.py"
)
bio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bio)

# (naam, moet als AGF gelden, waarom dit geval in de test staat)
GEVALLEN = [
    # Meervoud met klinkerverkorting: het trefwoord zit niet in het meervoud
    ("Bio Fairtrade bananen", True, "banaan -> bananen, de vondst die dit begon"),
    ("Jumbo Biologisch Snoeptomaten 400 g", True, "tomaat -> tomaten, én samenstelling"),
    ("AH Sperziebonen", True, "sperzieboon -> sperziebonen"),
    ("Plus Handperen Conference", True, "peer -> peren, én samenstelling"),
    ("Wortelen", True, "wortel als substring, niet als staart"),

    # Samenstelling met het trefwoord aan het eind
    ("Jumbo Biologisch Veldsla 40 g", True, "sla als staart"),
    ("Plus IJsbergsla fijn", True, "sla als staart"),
    ("Plus Spitskool gesneden", True, "kool als staart"),
    ("AH Boerenkool kleinverpakking", True, "kool als staart"),
    ("Bleekselderij", True, "selderij als substring"),
    ("Plus Watermeloen blokjes", True, "meloen als substring"),
    ("Plus Snackworteltjes", True, "wortel als substring"),
    ("Plus Puntpaprika rood", True, "paprika als substring"),
    ("Plus Snoepkomkommer", True, "komkommer als substring"),
    ("Jumbo Bospeen 2-3 Personen", True, "peen als staart"),
    ("Bio winterpostelein", True, "postelein als substring"),
    ("AH Bloedsinaasappelen", True, "sinaasappel als substring"),

    # Producten die eerst in geen enkel trefwoord stonden
    ("Ananas", True, "stond in geen trefwoord"),
    ("Paksoi", True, "stond in geen trefwoord"),
    ("Jumbo Pruimen 500 g", True, "stond in geen trefwoord"),
    ("Plus Nectarines", True, "stond in geen trefwoord"),
    ("Bio rabarber", True, "staat wel in onze seizoenskalender"),
    ("Bio spruitjes", True, "staat wel in onze seizoenskalender"),
    ("Bio doperwten", True, "staat wel in onze seizoenskalender"),

    # Bonen die bonen zijn: horen onder Voorraad, net als de Hak bio bieten
    ("Rode kidneybonen", True, "een boon is een boon"),
    ("Zwarte bonen", True, "stond al op de site"),
    ("AH Slaverrijker sojabonen", True, "een boon is een boon"),
    ("Hak Sperziebonen Bio 185 g", True, "groente uit blik hoort onder Voorraad"),

    # Bonen die geen boon zijn
    ("Cacaobonen", False, "cacao, geen groente"),
    ("Café Intención Crema aromatico koffiebonen", False, "koffie, geen groente"),
    ("Alpro Sojamelk bio", False, "melk, geen boon"),

    # De korte trefwoorden mogen niet middenin een woord matchen
    ("AH Vakslager Angus diamanthaas", False, "sla in Vakslager"),
    ("AH Pindakaashagelslag kruidnoten", False, "sla in hagelslag"),
    ("AH Chocolate chip kruidnoten", False, "ui in kruidnoten"),
    ("AH Slaverrijker quinoa", False, "ui in quinoa"),
    ("Bio houtskool", False, "kool in houtskool"),

    # Wat al werd geweerd en dat moet blijven
    ("Bio bananenchips", False, "chips"),
    ("Bio appelciderazijn", False, "azijn"),
    ("Dadelstroop", False, "stroop"),
    ("Groene thee citroengras", False, "thee"),
    ("AH Vers geperst sap sinaasappel", False, "sap"),
    ("Plus Pompoensoep", False, "soep"),
    ("Bonensticks paprika", False, "vastgeplakte sticks is een snack"),
    ("Hak Rode Bieten Sticks Bio 355 g", True, "losse sticks is de groente zelf"),
]


def main():
    fouten = 0
    for naam, verwacht, waarom in GEVALLEN:
        werkelijk = bio._is_agf(naam)
        if werkelijk != verwacht:
            fouten += 1
            hoe = "wel" if verwacht else "niet"
            print(f"  FOUT  {naam!r} moet {hoe} als AGF gelden ({waarom})")
    print(f"\n{len(GEVALLEN)} gevallen gecontroleerd, {fouten} fout")
    if fouten:
        sys.exit(1)

    # De seizoenskalender is de tweede toets: wat we op /seizoen/ van het
    # seizoen noemen, moeten we in een aanbieding ook herkennen.
    import json
    pad = Path(__file__).parent / "seizoen" / "seizoensdata.json"
    if pad.exists():
        data = json.loads(pad.read_text(encoding="utf-8"))
        namen = sorted({p["naam"] for m in data["maanden"]
                        for p in m["groente"] + m["fruit"]})
        mist = [n for n in namen if not bio._is_agf("Bio " + n)]
        print(f"seizoenskalender: {len(namen) - len(mist)}/{len(namen)} herkend")
        if mist:
            print("  niet herkend: " + ", ".join(mist))
            sys.exit(1)


if __name__ == "__main__":
    main()
