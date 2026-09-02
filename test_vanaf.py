#!/usr/bin/env python3
"""Controleert het uitlezen van het minimum-aantal uit een actievoorwaarde.

    python test_vanaf.py

Dit is de plek waar de site een bezoeker kan misleiden. De API levert per
product één prijs — de beste — en die geldt soms pas bij twee stuks. Komt het
aantal er niet uit, dan staat er een prijs op de pagina die je zo niet krijgt.
De labels hieronder zijn allemaal echt langsgekomen in de live data.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_bio_prices import _vanaf_aantal

GEVALLEN = [
    # label,                    verwacht, waarom
    ("1+1 gratis", 2, "twee meenemen, een betalen — dit ging fout en stond live"),
    ("1 + 1 gratis", 2, "zelfde met spaties"),
    ("2+1 gratis", 3, "drie meenemen"),
    ("5 + 1 GRATIS", 6, "zes meenemen"),
    ("2 STAPELEN TOT 50%", 2, "eerste getal"),
    ("2 voor 2,00", 2, "eerste getal"),
    ("3 voor 5,00", 3, "eerste getal"),
    ("2e halve prijs", 2, "tweede stuk halve prijs, dus twee nodig"),
    ("Actie", None, "geen aantal, geen bewering"),
    ("OP=OP", None, "geen aantal"),
    ("20% korting", None, "20 valt buiten de grens van 12 — geen minimum-aantal"),
    ("1 stuk", None, "een is geen minimum"),
    ("", None, "leeg label"),
]

fouten = 0
for label, verwacht, waarom in GEVALLEN:
    uit = _vanaf_aantal(label)
    ok = uit == verwacht
    if not ok:
        fouten += 1
    print(f"  {'ok    ' if ok else 'FOUT  '} {label!r:26} -> {str(uit):5} "
          f"{'' if ok else f'(verwacht {verwacht}) '}· {waarom}")

print()
if fouten:
    sys.exit(f"{fouten} van {len(GEVALLEN)} gevallen fout")
print(f"alle {len(GEVALLEN)} gevallen goed")
