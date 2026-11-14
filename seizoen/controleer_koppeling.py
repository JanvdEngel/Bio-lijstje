#!/usr/bin/env python3
"""Controleert de handmatige koppeltabel tussen seizoensdata en Eetwijzer.

    python seizoen/controleer_koppeling.py

Een handmatige tabel is alleen betrouwbaar als hij volledig is. Deze controle
eist dat elk seizoensproduct precies één keer voorkomt — gekoppeld of met een
reden — en dat elke koppeling naar een naam wijst die echt in de Eetwijzer
staat. Zo kan er niets stilletjes uit vallen als de data verandert.
"""

import json
import sys
from pathlib import Path

HIER = Path(__file__).parent
seizoen = json.loads((HIER / "seizoensdata.json").read_text(encoding="utf-8"))
eetwijzer = json.loads((HIER / "eetwijzer-2026.json").read_text(encoding="utf-8"))
kop = json.loads((HIER / "koppeling_eetwijzer.json").read_text(encoding="utf-8"))

seizoensnamen = sorted({p["naam"] for m in seizoen["maanden"] for p in m["groente"] + m["fruit"]})
eetnamen = {p["naam"] for p in eetwijzer["fruit"] + eetwijzer["groente"] + eetwijzer["overig"]}
gekoppeld, niet = kop["gekoppeld"], kop["niet_gekoppeld"]

fouten = []

ontbreekt = [n for n in seizoensnamen if n not in gekoppeld and n not in niet]
if ontbreekt:
    fouten.append(f"niet in de tabel: {', '.join(ontbreekt)}")

dubbel = sorted(set(gekoppeld) & set(niet))
if dubbel:
    fouten.append(f"staat in beide lijsten: {', '.join(dubbel)}")

onbekend = sorted(set(gekoppeld) | set(niet) - set(seizoensnamen))
onbekend = [n for n in onbekend if n not in seizoensnamen]
if onbekend:
    fouten.append(f"kent de seizoensdata niet: {', '.join(onbekend)}")

kapot = sorted(v for v in gekoppeld.values() if v not in eetnamen)
if kapot:
    fouten.append(f"bestaat niet in de Eetwijzer: {', '.join(kapot)}")

for naam in kop["kanttekeningen"]:
    if naam not in gekoppeld:
        fouten.append(f"kanttekening bij een niet-gekoppeld product: {naam}")

print(f"seizoensproducten : {len(seizoensnamen)}")
print(f"gekoppeld         : {len(gekoppeld)}")
print(f"bewust niet       : {len(niet)}")
print(f"Eetwijzer-namen   : {len(eetnamen)}")

if fouten:
    print()
    for f in fouten:
        print(f"  FOUT  {f}")
    sys.exit(f"\n{len(fouten)} probleem/problemen in de koppeltabel")

print("\ntabel is volledig en elke koppeling bestaat")

# Wat levert het op per maand?
lookup = {p["naam"]: p["residuen"] for p in eetwijzer["fruit"] + eetwijzer["groente"] + eetwijzer["overig"]}
print("\nmaand        met cijfer / totaal")
for m in seizoen["maanden"]:
    producten = m["groente"] + m["fruit"]
    met = [p for p in producten if p["naam"] in gekoppeld]
    print(f"  {m['maand']:<11} {len(met):>2} / {len(producten):<2}")
