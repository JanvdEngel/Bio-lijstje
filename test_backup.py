#!/usr/bin/env python3
"""Controleert de back-up van de prijsgeschiedenis.

    python test_backup.py

De geschiedenis is het enige onvervangbare bestand in dit project, dus het
vangnet eromheen moet twee dingen doen: kopieën maken waar de nachtelijke
Home Assistant-back-up ze meeneemt, en nooit de ronde laten klappen als dat
niet lukt. Dat tweede is het belangrijkste: een vangnet dat zelf de boel
sloopt is erger dan geen vangnet.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fetch_bio_prices as f

fouten = 0


def check(omschrijving, ok, detail=""):
    global fouten
    if not ok:
        fouten += 1
    print(f"  {'ok    ' if ok else 'FOUT  '} {omschrijving}{'  — ' + detail if detail and not ok else ''}")


tekst = json.dumps({"AH:bio appel": [{"datum": "2026-09-01", "actieprijs": 1.0}]}, indent=2)

print("zonder /data (zoals op de laptop):")
origineel = f.ADDON_DATA_DIR
try:
    f.ADDON_DATA_DIR = Path(tempfile.gettempdir()) / "bestaat-echt-niet-xyz"
    f._backup_history(tekst)
    check("geen uitzondering als de map ontbreekt", True)
except Exception as e:
    check("geen uitzondering als de map ontbreekt", False, str(e))

print("\nmet /data:")
with tempfile.TemporaryDirectory() as tmp:
    f.ADDON_DATA_DIR = Path(tmp)
    f._backup_history(tekst)
    map_ = Path(tmp) / "geschiedenis-backup"
    check("map aangemaakt", map_.is_dir())
    check("vaste kopie staat er", (map_ / "geschiedenis.json").exists())
    check("inhoud klopt", (map_ / "geschiedenis.json").read_text(encoding="utf-8") == tekst)
    gedateerd = list(map_.glob("geschiedenis-2*.json"))
    check("een gedateerde kopie", len(gedateerd) == 1, f"{len(gedateerd)} gevonden")

    # Meer dagen dan we bewaren: de oudste moeten weg, de nieuwste blijven.
    for dag in range(1, 13):
        (map_ / f"geschiedenis-2026-08-{dag:02d}.json").write_text("oud", encoding="utf-8")
    f._backup_history(tekst)
    over = sorted(p.name for p in map_.glob("geschiedenis-2*.json"))
    check(f"rotatie houdt er {f.HISTORY_BACKUPS} over", len(over) == f.HISTORY_BACKUPS,
          f"{len(over)}: {over}")
    check("de nieuwste is bewaard", any("2026-09" in n for n in over), str(over))
    check("de oudste is opgeruimd", "geschiedenis-2026-08-01.json" not in over)

print("\nbij een onbeschrijfbare map:")
with tempfile.TemporaryDirectory() as tmp:
    dwars = Path(tmp) / "geschiedenis-backup"
    dwars.write_text("dit is een bestand, geen map")   # mkdir zal hierop stuklopen
    f.ADDON_DATA_DIR = Path(tmp)
    try:
        f._backup_history(tekst)
        check("faalt stil in plaats van te crashen", True)
    except Exception as e:
        check("faalt stil in plaats van te crashen", False, str(e))

f.ADDON_DATA_DIR = origineel
print()
if fouten:
    sys.exit(f"{fouten} controle(s) gefaald")
print("de back-up doet wat hij moet doen, en kan de ronde niet breken")
