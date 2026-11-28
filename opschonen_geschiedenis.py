#!/usr/bin/env python3
"""Haalt dubbele waarnemingen uit de prijsgeschiedenis.

    python opschonen_geschiedenis.py <bestand>            # toont alleen
    python opschonen_geschiedenis.py <bestand> --schrijf   # past aan

Eenmalige opruiming van rommel van vóór 2 september 2026. Tot die datum schreef
elke ronde een regel bij, ook als de prijs niet was veranderd. Bij meerdere
rondes op een dag leverde dat identieke regels op: op 30 september stonden er
367 regels waarvan 216 uniek per datum, verdeeld over 36 producten.

Sinds de dedupe-fix komen er geen nieuwe bij — de engine schrijft alleen nog
weg als de prijs verandert. Dit script ruimt op wat er al stond.

Wat het wel doet: exacte duplicaten weghalen, dus regels met dezelfde datum
én dezelfde actieprijs én dezelfde normale prijs.

Wat het bewust niet doet: twee verschillende prijzen op één dag samenvoegen.
Dat zijn twee echte waarnemingen. Ze samenvoegen zou betekenen dat we een prijs
weggooien die we wel degelijk gezien hebben, en dat kan "laagste ooit" omhoog
duwen — precies het getal waarvoor deze reeks bestaat.

Daardoor verandert er niets aan wat de site toont, behalve "eerder gezien". Dat
telde dezelfde waarneming meerdere keren mee en was dus te hoog. Het script
controleert die belofte zelf en weigert te schrijven als hij niet klopt.

Draaien kan opnieuw zonder gevolgen: is er niets dubbels, dan gebeurt er niets.
"""

import json
import os
import sys
from pathlib import Path


def ontdubbel(reeks):
    """Houdt de eerste van elke identieke (datum, actieprijs, normale prijs).

    Plus een tweede slag: staat er op dezelfde dag twee keer dezelfde
    actieprijs, en had de ene nog geen van-prijs terwijl de andere die wel
    heeft, dan is dat dezelfde waarneming waarvan we de tweede keer meer wisten.
    Die gaan samen, met de ingevulde van-prijs. Zo stond "Lidl:bio blauwe
    bessen, bramen of frambozen" op 20 augustus twee keer op 1,79: een keer
    zonder en een keer met 2,69 erbij.

    Verschillen de van-prijzen wél van elkaar, dan blijven beide regels staan.
    Dan weten we niet welke klopt, en dat verzinnen we hier niet."""
    gezien, uit = set(), []
    for rij in reeks:
        sleutel = (rij.get("datum"), rij.get("actieprijs"), rij.get("normale_prijs"))
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        uit.append(rij)

    per_dag = {}
    for rij in uit:
        per_dag.setdefault((rij.get("datum"), rij.get("actieprijs")), []).append(rij)
    samen = []
    for rij in uit:
        groep = per_dag[(rij.get("datum"), rij.get("actieprijs"))]
        if len(groep) == 1:
            samen.append(rij)
            continue
        waarden = {r.get("normale_prijs") for r in groep if r.get("normale_prijs") is not None}
        if len(waarden) > 1:
            samen.append(rij)          # echt tegenstrijdig: laat staan
            continue
        if rij is groep[0]:            # een keer, met wat we weten
            beste = dict(rij)
            if waarden:
                beste["normale_prijs"] = waarden.pop()
            samen.append(beste)
    return samen


def kenmerken(history):
    """De dingen die na het opschonen gelijk moeten zijn gebleven."""
    uit = {}
    for sleutel, reeks in history.items():
        prijzen = [r["actieprijs"] for r in reeks if isinstance(r.get("actieprijs"), (int, float))]
        uit[sleutel] = (
            sorted({r.get("datum") for r in reeks}),
            min(prijzen) if prijzen else None,
        )
    return uit


def main():
    argumenten = [a for a in sys.argv[1:] if not a.startswith("--")]
    schrijven = "--schrijf" in sys.argv
    if not argumenten:
        sys.exit(__doc__)
    pad = Path(argumenten[0])
    history = json.loads(pad.read_text(encoding="utf-8"))

    voor_regels = sum(len(r) for r in history.values())
    voor_kenmerk = kenmerken(history)

    schoon = {s: ontdubbel(r) for s, r in history.items()}
    na_regels = sum(len(r) for r in schoon.values())
    geraakt = [s for s in history if len(history[s]) != len(schoon[s])]

    print(f"  producten      : {len(history)}")
    print(f"  regels         : {voor_regels} -> {na_regels}  ({voor_regels - na_regels} weg)")
    print(f"  geraakte reeksen: {len(geraakt)}")
    for s in sorted(geraakt)[:8]:
        print(f"      {s[:52]:54} {len(history[s])} -> {len(schoon[s])}")
    if len(geraakt) > 8:
        print(f"      ... en {len(geraakt) - 8} meer")

    # De belofte controleren voordat er iets wordt weggeschreven.
    na_kenmerk = kenmerken(schoon)
    fout = [s for s in voor_kenmerk if voor_kenmerk[s] != na_kenmerk.get(s)]
    if set(history) != set(schoon) or fout:
        sys.exit(f"  GESTOPT: {len(fout)} reeks(en) veranderden van datums of laagste prijs")
    print("  gecontroleerd  : zelfde producten, zelfde datums, zelfde laagste prijs")

    if not schrijven:
        print("\n  niets weggeschreven; geef --schrijf om het door te voeren")
        return
    if na_regels == voor_regels:
        print("\n  niets te doen")
        return

    tekst = json.dumps(schoon, indent=2, ensure_ascii=False)
    tijdelijk = pad.with_suffix(".json.opschonen")
    tijdelijk.write_text(tekst, encoding="utf-8")
    os.replace(tijdelijk, pad)
    print(f"\n  weggeschreven naar {pad}")


if __name__ == "__main__":
    main()
