#!/usr/bin/env python3
"""Controleert de gegenereerde seizoenspagina's tegen de databron.

    python seizoen/controleer_seizoen.py

Draai dit na bouw_paginas.py. De generator kan zonder fout draaien en toch
onzin opleveren — een plaatshouder die blijft staan, een canonical die naar de
verkeerde maand wijst, een product dat uit de lijst valt. Dat is precies het
soort fout dat pas opvalt als iemand de pagina bezoekt.
"""

import json
import sys
from pathlib import Path

HIER = Path(__file__).parent
data = json.loads((HIER / "seizoensdata.json").read_text(encoding="utf-8"))
fouten = 0


def keur(waar, checks):
    global fouten
    slecht = [naam for naam, ok in checks if not ok]
    if slecht:
        fouten += 1
        print(f"  FOUT  {waar}: {', '.join(slecht)}")
    else:
        print(f"  ok    {waar}")


for i, m in enumerate(data["maanden"]):
    pad = HIER / m["maand"] / "index.html"
    if not pad.exists():
        fouten += 1
        print(f"  FOUT  {m['maand']}: pagina ontbreekt")
        continue
    t = pad.read_text(encoding="utf-8")
    vorige = data["maanden"][(i - 1) % 12]["maand"]
    volgende = data["maanden"][(i + 1) % 12]["maand"]
    producten = m["groente"] + m["fruit"]
    keur(m["maand"], [
        ("canonical", f'href="https://hetbiolijstje.nl/seizoen/{m["maand"]}/"' in t),
        ("titel", f'<title>{m["maand"].capitalize()}:' in t),
        ("h1", f'<h1 class="name">{m["maand"].capitalize()}</h1>' in t),
        ("intro", m["intro"][:40] in t),
        ("geen plaatshouders", "{{" not in t),
        ("geen richtprijzen", "/ kg" not in t and "/ stuk" not in t and "/ bosje" not in t),
        # Het sjabloon werd uit de oude pagina geknipt en had daardoor twee
        # <title>-tags: de oude bovenaan en de nieuwe eronder. De browser pakt
        # de eerste, dus elke maandpagina heette hetzelfde. Alleen kijken of de
        # goede titel érgens in de pagina staat vond dat niet.
        ("een titel", t.count("<title>") == 1),
        ("een canonical", t.count('rel="canonical"') == 1),
        ("een description", t.count('name="description"') == 1),
        # Let op de afsluitende quote: class="dots" op de nav telt anders mee.
        ("twaalf stippen", t.count('class="dot"') + t.count('class="dot actief"') == 12),
        ("vorige maand", f'/seizoen/{vorige}/' in t),
        ("volgende maand", f'/seizoen/{volgende}/' in t),
        ("alle producten", all(p["naam"] in t for p in producten)),
        ("lege groep weggelaten", ("<h2>Fruit</h2>" in t) == bool(m["fruit"])),
        ("seizoensregel", data["seizoensregel"][:40] in t),
    ])

over = HIER.parent / "over" / "index.html"
if not over.exists():
    fouten += 1
    print("  FOUT  over: pagina ontbreekt")
else:
    t = over.read_text(encoding="utf-8")
    keur("over", [
        ("canonical", 'href="https://hetbiolijstje.nl/over/"' in t),
        ("een titel", t.count("<title>") == 1),
        ("een canonical", t.count('rel="canonical"') == 1),
        ("h1", '<h1 class="eyebrow">Over deze site</h1>' in t),
        ("geen plaatshouders", "{{" not in t),
        ("contactadres", "mailto:jan@styrinth.nl" in t),
        ("prijzen indicatief", "indicatief" in t),
        ("bron PrijsProfeet", "prijsprofeet.nl" in t),
        ("bron PAN-NL", "pan-netherlands.org" in t),
        ("privacy: teller genoemd", "GoatCounter" in t),
        # De nuance waar de hele pagina om begon: het residucijfer gaat over
        # het hele handelskanaal, niet over de biologische variant.
        ("residu niet bio-specifiek", "niet specifiek over biologisch" in t),
    ])

overzicht = HIER / "index.html"
t = overzicht.read_text(encoding="utf-8")
keur("overzicht", [
    ("canonical", 'href="https://hetbiolijstje.nl/seizoen/"' in t),
    ("geen plaatshouders", "{{" not in t),
    ("twaalf maandkaarten", t.count("maandkaart") >= 12),
    ("links naar elke maand", all(f'/seizoen/{m["maand"]}/' in t for m in data["maanden"])),
    # De CSS voor .bio-note staat op elke pagina; het gaat om de kaarten zelf.
    ("geen productkaarten", '<div class="card">' not in t),
    ("wel maandkaarten", 'class="card maandkaart"' in t),
])

print()
if fouten:
    sys.exit(f"{fouten} pagina('s) niet in orde")
print("alle veertien pagina's in orde")
