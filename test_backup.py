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
    f._backup_history(tekst, 1)
    check("geen uitzondering als de map ontbreekt", True)
except Exception as e:
    check("geen uitzondering als de map ontbreekt", False, str(e))

print("\nmet /data:")
with tempfile.TemporaryDirectory() as tmp:
    f.ADDON_DATA_DIR = Path(tmp)
    f._backup_history(tekst, 1)
    map_ = Path(tmp) / "geschiedenis-backup"
    check("map aangemaakt", map_.is_dir())
    check("vaste kopie staat er", (map_ / "geschiedenis.json").exists())
    check("inhoud klopt", (map_ / "geschiedenis.json").read_text(encoding="utf-8") == tekst)
    gedateerd = list(map_.glob("geschiedenis-2*.json"))
    check("een gedateerde kopie", len(gedateerd) == 1, f"{len(gedateerd)} gevonden")

    # Meer dagen dan we bewaren: de oudste moeten weg, de nieuwste blijven.
    for dag in range(1, 13):
        (map_ / f"geschiedenis-2026-08-{dag:02d}.json").write_text("oud", encoding="utf-8")
    f._backup_history(tekst, 1)
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
        f._backup_history(tekst, 1)
        check("faalt stil in plaats van te crashen", True)
    except Exception as e:
        check("faalt stil in plaats van te crashen", False, str(e))

print("\nde vaste kopie mag niet krimpen:")
with tempfile.TemporaryDirectory() as tmp:
    f.ADDON_DATA_DIR = Path(tmp)
    groot = json.dumps({f"AH:p{i}": [{"datum": "2026-09-01", "actieprijs": 1.0}] for i in range(50)})
    f._backup_history(groot, 50)
    vast = Path(tmp) / "geschiedenis-backup" / "geschiedenis.json"
    check("grote versie staat er", len(json.loads(vast.read_text(encoding="utf-8"))) == 50)
    f._backup_history(json.dumps({"AH:p0": []}), 1)          # leeggelopen geschiedenis
    over = json.loads(vast.read_text(encoding="utf-8"))
    check("vaste kopie is NIET overschreven door de kleine", len(over) == 50, f"{len(over)}")
    gedateerd = list((Path(tmp) / "geschiedenis-backup").glob("geschiedenis-2*.json"))
    check("gedateerde kopie is wel geschreven", len(gedateerd) == 1)

print("\nherstel uit de back-up:")
with tempfile.TemporaryDirectory() as tmp:
    f.ADDON_DATA_DIR = Path(tmp)
    goed = {"AH:bio peer": [{"datum": "2026-08-20", "actieprijs": 2.5}]}
    f._backup_history(json.dumps(goed), len(goed))
    check("vindt de back-up terug", f._herstel_history() == goed)

    hist = Path(tmp) / "www" / "data" / "geschiedenis.json"
    hist.parent.mkdir(parents=True, exist_ok=True)
    hist.write_text("{ dit is geen geldige json", encoding="utf-8")
    oud_pad = f.HISTORY_PATH
    f.HISTORY_PATH = hist
    try:
        terug = f.load_history()
        check("load_history herstelt in plaats van op nul te beginnen", terug == goed, str(terug))
        check("het beschadigde bestand is bewaard", Path(str(hist) + ".beschadigd").exists())
    finally:
        f.HISTORY_PATH = oud_pad

print("\nzonder back-up valt hij netjes terug op leeg:")
with tempfile.TemporaryDirectory() as tmp:
    f.ADDON_DATA_DIR = Path(tmp) / "leeg"
    check("geen back-up gevonden geeft None", f._herstel_history() is None)

print("\natomair wegschrijven:")
with tempfile.TemporaryDirectory() as tmp:
    f.ADDON_DATA_DIR = Path(tmp) / "geen-data"
    hist = Path(tmp) / "www" / "data" / "geschiedenis.json"
    oud_pad = f.HISTORY_PATH
    f.HISTORY_PATH = hist
    try:
        f.save_history({"AH:bio ui": [{"datum": "2026-09-02", "actieprijs": 1.2}]})
        check("bestand geschreven", hist.exists())
        check("geen tijdelijk bestand achtergebleven",
              not list(hist.parent.glob("*.nieuw")), str(list(hist.parent.glob("*.nieuw"))))
        check("inhoud is geldige json", isinstance(json.loads(hist.read_text(encoding="utf-8")), dict))
    finally:
        f.HISTORY_PATH = oud_pad

f.ADDON_DATA_DIR = origineel
print()
if fouten:
    sys.exit(f"{fouten} controle(s) gefaald")
print("de back-up doet wat hij moet doen, en kan de ronde niet breken")
