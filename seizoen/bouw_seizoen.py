#!/usr/bin/env python3
"""
Bouwt de seizoenspagina's uit één databron.

    python seizoen/bouw_seizoen.py

Uit `seizoensdata.json` en `_sjabloon.html` komen dertien bestanden:

    seizoen/index.html            overzicht met twaalf maandkaarten
    seizoen/<maand>/index.html    twaalf maandpagina's

Waarom gegenereerd en niet met de hand: twaalf pagina's die dezelfde kop, CSS
en voettekst delen lopen anders binnen een maand uit elkaar. En waarom niet
door de Pi: deze data verandert hooguit één keer per jaar, dus dagelijks
opnieuw bouwen zou alleen ruis in de git-geschiedenis geven. Draai dit met de
hand na een wijziging in de data en commit het resultaat.

Twee dingen die bewust niet op de pagina's staan:

- De richtprijzen. Die staan nog wél in de JSON, maar zijn een eigen
  inschatting: zeventien unieke bedragen over honderddertig vermeldingen. Op
  één pagina achter een knop was dat verdedigbaar; op twaalf pagina's die
  bedoeld zijn om gevonden te worden is het dat niet.
- Een volledige productlijst op /seizoen zelf. Die zou woordelijk gelijk zijn
  aan de maandpagina van dat moment, en dan concurreren twee adressen van
  dezelfde site met elkaar op dezelfde inhoud.
"""

import html
import json
import re
import sys
from pathlib import Path

HIER = Path(__file__).parent
DATA = HIER / "seizoensdata.json"
SJABLOON = HIER / "_sjabloon.html"
BASIS_URL = "https://hetbiolijstje.nl/seizoen"


def esc(tekst):
    return html.escape(str(tekst), quote=True)


def residutabel():
    """Zet de handmatige koppeltabel om in wat de kaarten nodig hebben:
    per seizoensproduct het gemeten cijfer, het gemiddelde van zijn categorie
    ter vergelijking, en of het bij de vijf hoogste van die categorie hoort.

    De top vijf is bewust per categorie en niet over alles heen: groente scoort
    structureel lager dan fruit (gemiddeld 1,3 tegen 2,6), dus een gezamenlijke
    ranglijst zou alleen fruit markeren."""
    eet = json.loads((HIER / "eetwijzer-2026.json").read_text(encoding="utf-8"))
    kop = json.loads((HIER / "koppeling_eetwijzer.json").read_text(encoding="utf-8"))

    bron = {}
    for categorie, sleutel, gemiddelde in (
        ("fruit", "fruit", eet["gemiddelde_fruit"]),
        ("groente", "groente", eet["gemiddelde_groente"]),
    ):
        gesorteerd = sorted(eet[sleutel], key=lambda p: -p["residuen"])
        top5 = {p["naam"] for p in gesorteerd[:5]}
        for p in eet[sleutel]:
            bron[p["naam"]] = {
                "residuen": p["residuen"],
                "gemiddelde": gemiddelde,
                "soort": categorie,
                "top5": p["naam"] in top5,
            }
    for p in eet["overig"]:
        bron[p["naam"]] = {
            "residuen": p["residuen"],
            "gemiddelde": eet["gemiddelde_groente"],
            "soort": "groente",
            "top5": False,
        }

    tabel = {}
    for seizoensnaam, eetnaam in kop["gekoppeld"].items():
        if eetnaam not in bron:
            sys.exit(f"koppeling wijst naar een naam die niet in de Eetwijzer staat: {eetnaam}")
        tabel[seizoensnaam] = {**bron[eetnaam], "eetwijzer_naam": eetnaam}
    return tabel


def kaart(product, residu):
    """Eén product. Het uitklapje zit in de HTML en niet in JavaScript, zodat een
    crawler en een bezoeker zonder JavaScript het ook zien.

    Het 🧴 staat alleen bij de vijf hoogst scorende soorten per categorie. Bij de
    rest staat het cijfer zonder waarschuwing: een markering bij ruim de helft
    van de lijst zegt niets meer, en het getal is informatiever dan een
    pictogram. Producten die de NVWA niet apart meet krijgen geen van beide —
    geen cijfer is beter dan het cijfer van een ander gewas."""
    r = residu.get(product["naam"])
    vlag = regel = uitleg = ""
    if r:
        getal = f'{r["residuen"]:.1f}'.replace(".", ",")
        vergelijk = f'{r["gemiddelde"]:.1f}'.replace(".", ",")
        if r["top5"]:
            vlag = ('<button class="bio-flag" type="button" '
                    'aria-label="Waarom dit icoon?">\U0001F9F4</button>')
        regel = (f'\n        <p class="residu{" hoog" if r["top5"] else ""}">'
                 f'gem. {getal} bestrijdingsmiddelen</p>')
        uitleg = (
            f'\n        <p class="bio-note">In monsters van '
            f'{esc(r["eetwijzer_naam"].lower())} vond de NVWA gemiddeld {getal} '
            f'verschillende bestrijdingsmiddelen; het gemiddelde voor {r["soort"]} '
            f'is {vergelijk}. Bron: PesticidenEetwijzer van PAN-NL, '
            f'NVWA-data 2023–2025.</p>'
        )
    return (
        '      <div class="card">\n'
        f'        <p class="item-name"><span class="name-text">{esc(product["naam"])}</span>{vlag}</p>\n'
        f'        <p class="item-tip">{esc(product["tip"])}</p>'
        f'{regel}{uitleg}\n'
        '      </div>'
    )


def groep(titel, producten, residu):
    """Een lege groep wordt weggelaten in plaats van als leeg kopje getoond:
    april en mei hebben geen Nederlands fruit, en 'Fruit — 0 soorten' leest als
    een storing in plaats van als een feit."""
    if not producten:
        return ""
    woord = "soort" if len(producten) == 1 else "soorten"
    kaarten = "\n".join(kaart(p, residu) for p in producten)
    return (
        f'  <section class="group">\n'
        f'    <div class="group-title"><h2>{titel}</h2>'
        f'<span class="count">{len(producten)} {woord}</span></div>\n'
        f'    <div class="grid">\n{kaarten}\n    </div>\n'
        f'  </section>\n'
    )


def stippen(maanden, huidige_index):
    """De twaalf stippen uit het oorspronkelijke ontwerp, nu als links. Dat is
    meteen de onderlinge verwijzing tussen de twaalf pagina's."""
    uit = ['  <nav class="dots" aria-label="Kies een maand">']
    for i, m in enumerate(maanden):
        actief = ' class="dot actief"' if i == huidige_index else ' class="dot"'
        uit.append(
            f'    <a href="/seizoen/{m["maand"]}/"{actief} data-maand="{m["nummer"]}" '
            f'title="{esc(m["maand"].capitalize())}"><span class="sr">{esc(m["maand"])}</span></a>'
        )
    uit.append("  </nav>")
    return "\n".join(uit)


def maandpagina(data, index, residu):
    m = data["maanden"][index]
    maanden = data["maanden"]
    vorige = maanden[(index - 1) % 12]
    volgende = maanden[(index + 1) % 12]
    naam = m["maand"].capitalize()
    totaal = len(m["groente"]) + len(m["fruit"])

    inhoud = f"""{stippen(maanden, index)}

  <div class="hero">
    <a class="nav-btn" href="/seizoen/{vorige['maand']}/" aria-label="{esc(vorige['maand'].capitalize())}">&#8592;</a>
    <div class="month-stamp">
      <h1 class="name">{esc(naam)}</h1>
      <span class="tag" data-maand="{m['nummer']}">Nu in het schap</span>
    </div>
    <a class="nav-btn" href="/seizoen/{volgende['maand']}/" aria-label="{esc(volgende['maand'].capitalize())}">&#8594;</a>
  </div>

  <p class="intro">{esc(m['intro'])}</p>

{groep("Groente", m["groente"], residu)}
{groep("Fruit", m["fruit"], residu)}
  <p class="verder">
    Vorige maand: <a href="/seizoen/{vorige['maand']}/">{esc(vorige['maand'])}</a> &middot;
    Volgende maand: <a href="/seizoen/{volgende['maand']}/">{esc(volgende['maand'])}</a> &middot;
    <a href="/seizoen/">alle maanden</a>
  </p>
"""
    return {
        "pad": HIER / m["maand"] / "index.html",
        "titel": f"{naam}: seizoensgroente en -fruit uit Nederland",
        "og_titel": f"Wat is er in {m['maand']} van het seizoen?",
        "beschrijving": (
            f"{totaal} soorten groente en fruit die in {m['maand']} in Nederland "
            f"van het seizoen zijn, met bewaartip per product. {m['intro'][:110].rsplit(' ', 1)[0]}…"
        ),
        "canonical": f"{BASIS_URL}/{m['maand']}/",
        "inhoud": inhoud,
    }


def overzichtspagina(data):
    maanden = data["maanden"]
    kaarten = []
    for i, m in enumerate(maanden):
        totaal = len(m["groente"]) + len(m["fruit"])
        voorbeelden = [p["naam"] for p in (m["groente"] + m["fruit"])[:3]]
        kaarten.append(
            f'      <a class="card maandkaart" href="/seizoen/{m["maand"]}/" data-maand="{m["nummer"]}">\n'
            f'        <p class="item-name"><span class="name-text">{esc(m["maand"].capitalize())}</span></p>\n'
            f'        <p class="item-tip">{esc(", ".join(voorbeelden))} en meer</p>\n'
            f'        <span class="count">{totaal} soorten</span>\n'
            f'      </a>'
        )
    inhoud = (
        '  <div class="hero">\n'
        '    <div class="month-stamp">\n'
        '      <h1 class="name">Seizoenswijzer</h1>\n'
        '    </div>\n'
        '  </div>\n\n'
        '  <p class="intro">Welke groente en welk fruit in Nederland van het seizoen zijn, '
        'maand voor maand. Kies een maand voor de volledige lijst met bewaartips.</p>\n\n'
        '  <section class="group">\n'
        '    <div class="grid grid-maanden">\n' + "\n".join(kaarten) + "\n    </div>\n"
        '  </section>\n'
    )
    return {
        "pad": HIER / "index.html",
        "titel": "Seizoenswijzer — welke groente en fruit zijn nu van het seizoen?",
        "og_titel": "Seizoenswijzer — per maand wat er van het seizoen is",
        "beschrijving": (
            "Per maand welke groente en welk fruit in Nederland van het seizoen zijn: "
            "vers geoogst of uit de bewaring van een Nederlandse oogst, met bewaartip per product."
        ),
        "canonical": f"{BASIS_URL}/",
        "inhoud": inhoud,
    }


def schrijf(pagina, sjabloon, seizoensregel):
    tekst = sjabloon
    for sleutel, waarde in (
        ("{{TITEL}}", esc(pagina["titel"])),
        ("{{OG_TITEL}}", esc(pagina["og_titel"])),
        ("{{BESCHRIJVING}}", esc(pagina["beschrijving"])),
        ("{{CANONICAL}}", pagina["canonical"]),
        ("{{SEIZOENSREGEL}}", esc(seizoensregel)),
        ("{{INHOUD}}", pagina["inhoud"]),
    ):
        tekst = tekst.replace(sleutel, waarde)
    resterend = re.findall(r"\{\{[A-Z_]+\}\}", tekst)
    if resterend:
        sys.exit(f"plaatshouder niet ingevuld in {pagina['pad'].name}: {resterend}")
    pagina["pad"].parent.mkdir(parents=True, exist_ok=True)
    pagina["pad"].write_text(tekst, encoding="utf-8", newline="\n")
    return len(tekst)


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    sjabloon = SJABLOON.read_text(encoding="utf-8")
    residu = residutabel()
    regel = data["seizoensregel"]

    paginas = [overzichtspagina(data)]
    paginas += [maandpagina(data, i, residu) for i in range(12)]

    for p in paginas:
        n = schrijf(p, sjabloon, regel)
        rel = p["pad"].relative_to(HIER.parent)
        print(f"  {str(rel).replace(chr(92), '/'):34} {n:6} bytes   {p['titel'][:52]}")
    print(f"\n{len(paginas)} pagina's gebouwd uit {DATA.name}")


if __name__ == "__main__":
    main()
