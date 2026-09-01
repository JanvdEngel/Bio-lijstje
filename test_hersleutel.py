"""Controleert dat _hersleutel bestaande prijsgeschiedenis correct meeverhuist
naar de nieuwe sleutelvorm, en dat er geen metingen verdwijnen.

Draaien:  python test_hersleutel.py

Geen testframework nodig; dit bestand raakt geen netwerk en geen bestanden.
De reden dat het bestaat: het weghalen van streepjes uit de naamsleutel
verandert de sleutels van bestaande reeksen, en die reeksen zijn precies wat
dit project bewaart. Een migratie die stil metingen laat vallen zou pas maanden
later opvallen.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_bio_prices import _hersleutel, _naamsleutel

fouten = 0


def check(omschrijving, gekregen, verwacht):
    global fouten
    ok = gekregen == verwacht
    if not ok:
        fouten += 1
    print(f"  {'ok    ' if ok else 'FOUT  '} {omschrijving}")
    if not ok:
        print(f"           gekregen: {gekregen}")
        print(f"           verwacht: {verwacht}")


print("naamsleutel:")
check("streepje eruit", _naamsleutel("Bio kastanje-champignons"), "bio kastanjechampignons")
check("gelijk aan de variant zonder streepje", _naamsleutel("Bio kastanjechampignons"), "bio kastanjechampignons")
check("spaties samengevouwen", _naamsleutel("  Bio   Appel  "), "bio appel")
check("en-dash telt ook", _naamsleutel("Bio kastanje\u2013champignons"), "bio kastanjechampignons")
check("laat gewone namen met rust", _naamsleutel("Oesterzwammen"), "oesterzwammen")

print("\nmigratie van twee reeksen die samenvallen:")
history = {
    "Lidl:bio kastanjechampignons": [
        {"datum": "2026-08-20", "actieprijs": 1.79, "normale_prijs": 1.99},
        {"datum": "2026-08-27", "actieprijs": 1.49, "normale_prijs": 1.99},
    ],
    "Lidl:bio kastanje-champignons": [
        {"datum": "2026-08-24", "actieprijs": 1.69, "normale_prijs": 1.99},
    ],
    "AH:ah biologisch witte druiven pitloos": [
        {"datum": "2026-08-31", "actieprijs": 1.75, "normale_prijs": 3.49},
    ],
}
voor = sum(len(v) for v in history.values())
nieuw = _hersleutel(history)
na = sum(len(v) for v in nieuw.values())

check("twee sleutels worden er een", sorted(nieuw), ["AH:ah biologisch witte druiven pitloos", "Lidl:bio kastanjechampignons"])
check("geen enkele meting kwijt", na, voor)
check("op datum gesorteerd", [r["datum"] for r in nieuw["Lidl:bio kastanjechampignons"]],
      ["2026-08-20", "2026-08-24", "2026-08-27"])
check("onaangeraakte reeks blijft gelijk", nieuw["AH:ah biologisch witte druiven pitloos"],
      history["AH:ah biologisch witte druiven pitloos"])

print("\nidempotent (tweede keer draaien verandert niets):")
check("tweede ronde gelijk aan eerste", _hersleutel(nieuw), nieuw)

print("\nopeenvolgende dubbele prijzen worden platgeslagen:")
dubbel = _hersleutel({
    "Plus:bio appel": [{"datum": "2026-08-01", "actieprijs": 1.0, "normale_prijs": 2.0}],
    "Plus:bio-appel": [{"datum": "2026-08-02", "actieprijs": 1.0, "normale_prijs": 2.0}],
})
check("dezelfde prijs op twee dagen wordt een record", len(dubbel["Plus:bio appel"]), 1)
check("de vroegste datum blijft staan", dubbel["Plus:bio appel"][0]["datum"], "2026-08-01")

print(f"\n{'ALLES GOED' if not fouten else str(fouten) + ' CONTROLE(S) GEFAALD'}")
sys.exit(1 if fouten else 0)
