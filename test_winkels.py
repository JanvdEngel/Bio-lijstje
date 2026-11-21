#!/usr/bin/env python3
"""Controleert dat elke winkel uit de engine ook op de pagina bestaat.

    python test_winkels.py

Een winkel toevoegen gebeurt op twee plekken: AANBIEDINGEN_STORES in de engine,
en STORE_COLORS/STORE_BADGES in het sjabloon. Vergeet je de tweede, dan valt de
pagina stil terug — `STORE_COLORS[s] || 'var(--muted)'` geeft een grijze bol en
`STORE_BADGES[s] || s[0]` de eerste letter van de naam.

Dat faalt dus niet, het ziet er alleen fout uit. En bij DekaMarkt zou die
terugval een "D" opleveren: dezelfde letter als Dirk, in hetzelfde grijs, op een
pagina die winkels juist uit elkaar moet houden.

Daarom hier de drie dingen die moeten kloppen voor élke winkel:

  1. een kleur in beide paletten, want de donkere en de lichte staan los van
     elkaar in het sjabloon;
  2. een eigen badge, en geen twee winkels met dezelfde;
  3. genoeg contrast tussen die kleur en de achtergrond, want de badgeletter
     krijgt de achtergrondkleur (`color: var(--bg)`).
"""

import importlib.util
import re
import sys
from pathlib import Path

HIER = Path(__file__).parent
spec = importlib.util.spec_from_file_location("bio", HIER / "fetch_bio_prices.py")
bio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bio)

sjabloon = (HIER / "template.html").read_text(encoding="utf-8")
fouten = 0


def keur(wat, ok, toelichting=""):
    global fouten
    if ok:
        print(f"  ok    {wat}")
    else:
        fouten += 1
        print(f"  FOUT  {wat}" + (f" — {toelichting}" if toelichting else ""))


def kaart(naam):
    """Leest een JS-object uit het sjabloon als {winkel: waarde}."""
    m = re.search(naam + r"\s*=\s*\{(.*?)\};", sjabloon, re.S)
    if not m:
        return {}
    return dict(re.findall(r"(\w+)\s*:\s*'([^']*)'", m.group(1)))


def paletten():
    """De winkelkleuren per palet: eerst :root (donker), dan :root.licht."""
    uit = {}
    for sleutel, patroon in (("donker", r":root\{(.*?)\n  \}"),
                             ("licht", r":root\.licht\{(.*?)\n  \}")):
        m = re.search(patroon, sjabloon, re.S)
        blok = m.group(1) if m else ""
        uit[sleutel] = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", blok))
    return uit


def contrast(a, b):
    def kanaal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    def licht(h):
        h = h.lstrip("#")
        r, g, b_ = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * kanaal(r) + 0.7152 * kanaal(g) + 0.0722 * kanaal(b_)

    hoog, laag = max(licht(a), licht(b)), min(licht(a), licht(b))
    return (hoog + 0.05) / (laag + 0.05)


kleuren = kaart("STORE_COLORS")
badges = kaart("STORE_BADGES")
pal = paletten()
winkels = list(bio.AANBIEDINGEN_STORES)

print(f"{len(winkels)} winkels in de engine: " + ", ".join(winkels))

print("\nElke winkel heeft een kleur en een badge:")
for w in winkels:
    keur(f"{w}: kleur", w in kleuren, "ontbreekt in STORE_COLORS")
    keur(f"{w}: badge", w in badges, "ontbreekt in STORE_BADGES")

print("\nGeen twee winkels met dezelfde badge:")
gezien = {}
for w in winkels:
    teken = badges.get(w) or w[0]
    keur(f"{w} draagt {teken!r}", teken not in gezien,
         f"botst met {gezien.get(teken)}")
    gezien[teken] = w

print("\nDe kleur staat in beide paletten en heeft genoeg contrast:")
for w in winkels:
    verwijzing = kleuren.get(w, "")
    naam = re.sub(r"var\(--|\)", "", verwijzing)
    for palet in ("donker", "licht"):
        hex_ = pal[palet].get(naam)
        if not hex_:
            keur(f"{w} in het {palet}e palet", False, f"--{naam} niet gevonden")
            continue
        bg = pal[palet].get("bg", "#000000")
        verhouding = contrast(hex_, bg)
        keur(f"{w} in het {palet}e palet: {hex_} op {bg} = {verhouding:.2f}:1",
             verhouding >= 4.5, "onder de eis van 4,5:1")

print("\nEn de kandidaten zijn geen winkel:")
dubbel = set(bio.AANBIEDINGEN_STORES) & set(bio.KANDIDAAT_WINKELS)
keur("geen winkel staat ook in KANDIDAAT_WINKELS", not dubbel,
     f"dubbel: {', '.join(sorted(dubbel))}")

print(f"\n{fouten} fout" if fouten else "\nalles goed")
sys.exit(1 if fouten else 0)
