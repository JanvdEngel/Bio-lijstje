#!/usr/bin/env python3
"""Vult dagtellingen.json met terugwerkende kracht uit de git-geschiedenis.

    python vul_dagtellingen.py <doelbestand> [--schrijf]

De prijsreeks bewaart alleen prijswijzigingen, dus daaruit valt niet af te
lezen hoeveel aanbiedingen een winkel op een dag had. Dat staat wel in
data/bio_prices.json, en van dat bestand staat elke dagelijkse versie in de
git-geschiedenis van de repo.

Dit script leest die commits eenmalig uit, zodat /cijfers/ niet pas over een
maand iets te zeggen heeft. Daarna houdt fetch_bio_prices.py het bestand zelf
bij: elke ronde schrijft de telling van vandaag erin.

Ekoplaza blijft erbuiten. Die keten stond een paar dagen in de lijst en is er
weer uit; meetellen zou een knik in de reeks geven die niets met de winkels te
maken heeft.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

WINKELS = ["AH", "Jumbo", "Lidl", "Aldi", "Dirk", "Plus"]


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8").stdout


def uit_git():
    """Per dag de telling per winkel, uit de laatste commit van die dag."""
    commits = [r.strip() for r in
               git("log", "--format=%H", "origin/main", "--", "data/bio_prices.json")
               .strip().split("\n") if r.strip()]
    per_dag = {}
    # Oudste eerst, zodat de laatste ronde van een dag wint.
    for h in reversed(commits):
        try:
            j = json.loads(git("show", f"{h}:data/bio_prices.json"))
        except (json.JSONDecodeError, ValueError):
            continue
        dag = (j.get("laatst_bijgewerkt") or "")[:10]
        if len(dag) != 10:
            continue
        aanbiedingen = j.get("aanbiedingen") or {}
        # Alleen dagen waarop alle zes de winkels zijn opgehaald: eerder deden
        # er minder mee, en dan is een nul geen nul maar een ontbrekende winkel.
        if not all(w in aanbiedingen for w in WINKELS):
            continue
        per_dag[dag] = {w: len(aanbiedingen.get(w) or []) for w in WINKELS}
    return per_dag


def main():
    argumenten = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not argumenten:
        sys.exit(__doc__)
    doel = Path(argumenten[0])
    schrijven = "--schrijf" in sys.argv

    nieuw = uit_git()
    bestaand = {}
    if doel.exists():
        bestaand = (json.loads(doel.read_text(encoding="utf-8")) or {}).get("dagen", {})

    samen = {**nieuw, **bestaand}   # wat er al stond wint: dat is de echte meting
    dagen = dict(sorted(samen.items()))

    print(f"  uit git        : {len(nieuw)} dagen")
    print(f"  al in bestand  : {len(bestaand)} dagen")
    print(f"  samen          : {len(dagen)} dagen")
    if dagen:
        eerste, laatste = min(dagen), max(dagen)
        tot = {d: sum(v.values()) for d, v in dagen.items()}
        print(f"  periode        : {eerste} t/m {laatste}")
        print(f"  laagste dag    : {min(tot.values())}, hoogste {max(tot.values())}, "
              f"gemiddeld {sum(tot.values())/len(tot):.1f}")

    if not schrijven:
        print("\n  niets weggeschreven; geef --schrijf om het door te voeren")
        return
    doel.parent.mkdir(parents=True, exist_ok=True)
    doel.write_text(json.dumps({"winkels": WINKELS, "dagen": dagen},
                               indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  weggeschreven naar {doel}")


if __name__ == "__main__":
    main()
