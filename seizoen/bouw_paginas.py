#!/usr/bin/env python3
"""
Bouwt de statische pagina's uit één databron en één sjabloon.

    python seizoen/bouw_paginas.py

Uit `seizoensdata.json` en `_sjabloon.html` komen veertien bestanden:

    seizoen/index.html            overzicht met twaalf maandkaarten
    seizoen/<maand>/index.html    twaalf maandpagina's
    over/index.html               over de site, de bronnen en het contact

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


def nav(actief):
    """De sectierij bovenaan. Alleen de twee inhoudelijke delen staan hier;
    "Over" hoort in de voettekst, want dat is geen inhoud maar verantwoording."""
    items = [("/", "Aanbiedingen", "aanbiedingen"), ("/seizoen/", "Seizoen", "seizoen")]
    regels = ['    <nav class="secties" aria-label="Secties">']
    for href, label, sleutel in items:
        if sleutel == actief:
            regels.append(f'      <a href="{href}" class="huidig" aria-current="page">{label}</a>')
        else:
            regels.append(f'      <a href="{href}">{label}</a>')
    regels.append("    </nav>")
    return "\n".join(regels)


# De lange bronvermeldingen stonden in de voettekst van elke pagina. Die staan
# nu voluit op /over/; hier blijft een korte regel met de verwijzing.
def voetnoot_seizoen(regel):
    """Korte bronregel plus de definitie van "van het seizoen".

    Die definitie stond eerst in de lange voettekst. Toen die naar /over/ ging
    verdween hij van alle twaalf maandpagina's, en dat is precies het woord
    waarover een bezoeker op zo'n pagina struikelt. Hij hoort dus hier te staan,
    niet een klik verderop.
    """
    return (
        f"{regel}<br>"
        "Residucijfers uit de "
        '<a href="https://www.pan-netherlands.org/eetwijzer/" rel="noopener">'
        "PesticidenEetwijzer</a> van PAN-NL. Geen live databron.<br>"
        '<a href="/over/">Over deze site en de bronnen</a>'
    )


# Op /over/ zou die link naar zichzelf wijzen. Na 600 woorden tekst staat daar
# liever de weg terug naar waar de bezoeker vandaan kwam.
VOETNOOT_OVER = 'Terug naar <a href="/">de aanbiedingen</a>.'


# Grens waarboven en waaronder een product afwijkt van het gemiddelde van zijn
# categorie. Een kwart eronder of erboven, want kleinere verschillen zeggen bij
# gemiddelden over ~74 monsters per soort weinig.
AFWIJKING = 0.25

OORDEEL = {
    "meer": "meer bestrijdingsmiddelen dan gemiddeld",
    "rond": "gemiddeld aantal bestrijdingsmiddelen",
    "minder": "minder bestrijdingsmiddelen dan gemiddeld",
}


def oordeel(residuen, gemiddelde):
    if residuen > gemiddelde * (1 + AFWIJKING):
        return "meer"
    if residuen < gemiddelde * (1 - AFWIJKING):
        return "minder"
    return "rond"


def residutabel():
    """Zet de handmatige koppeltabel om in wat de kaarten nodig hebben.

    Op de kaart staat geen kaal getal meer. "gem. 3,8 bestrijdingsmiddelen"
    klinkt precies maar zegt niets: de lezer weet niet of dat veel is, en de
    vraag die hij heeft is of hij hier beter biologisch kan kopen. Daarom een
    vergelijking met het gemiddelde van de eigen categorie — de enige maatstaf
    die in dezelfde bron staat. Het exacte cijfer blijft in het uitklapje.

    Vergelijken binnen de categorie en niet over alles heen: groente scoort
    structureel lager dan fruit (gemiddeld 1,3 tegen 2,6), dus tegen één
    gezamenlijk gemiddelde zou vrijwel alle groente er gunstig uitkomen en
    vrijwel al het fruit ongunstig."""
    eet = json.loads((HIER / "eetwijzer-2026.json").read_text(encoding="utf-8"))
    kop = json.loads((HIER / "koppeling_eetwijzer.json").read_text(encoding="utf-8"))

    bron = {}
    for categorie, sleutel, gemiddelde in (
        ("fruit", "fruit", eet["gemiddelde_fruit"]),
        ("groente", "groente", eet["gemiddelde_groente"]),
    ):
        for p in eet[sleutel]:
            bron[p["naam"]] = {
                "residuen": p["residuen"],
                "gemiddelde": gemiddelde,
                "soort": categorie,
                "oordeel": oordeel(p["residuen"], gemiddelde),
            }
    # Aardappel hoort bij geen van beide lijsten maar wordt met groente
    # vergeleken; het is de enige in die categorie.
    for p in eet["overig"]:
        bron[p["naam"]] = {
            "residuen": p["residuen"],
            "gemiddelde": eet["gemiddelde_groente"],
            "soort": "groente",
            "oordeel": oordeel(p["residuen"], eet["gemiddelde_groente"]),
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

    Op de kaart staat een vergelijking, geen kaal getal — zie residutabel().
    Het 🧴 hoort bij dezelfde regel: het staat bij wat boven het gemiddelde
    uitkomt, zodat de markering en de tekst hetzelfde zeggen. Producten die de
    NVWA niet apart meet krijgen niets: geen oordeel is beter dan het oordeel
    van een ander gewas."""
    r = residu.get(product["naam"])
    vlag = regel = uitleg = ""
    if r:
        getal = f'{r["residuen"]:.1f}'.replace(".", ",")
        vergelijk = f'{r["gemiddelde"]:.1f}'.replace(".", ",")
        hoog = r["oordeel"] == "meer"
        if hoog:
            vlag = ('<button class="bio-flag" type="button" '
                    'aria-label="Wat betekent dit?">\U0001F9F4</button>')
        regel = (f'\n        <p class="residu {r["oordeel"]}">'
                 f'{OORDEEL[r["oordeel"]]}</p>')
        uitleg = (
            f'\n        <p class="bio-note">In monsters van '
            f'{esc(r["eetwijzer_naam"].lower())} vond de NVWA gemiddeld {getal} '
            f'verschillende bestrijdingsmiddelen. Voor {r["soort"]} als geheel is '
            f'dat {vergelijk}. Bron: PesticidenEetwijzer van PAN-NL, '
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
    <div class="month-stamp" data-maand="{m['nummer']}">
      <h1 class="name">{esc(naam)}</h1>
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
        # Op een maandpagina is de maand de kop en zegt "Seizoenswijzer" alleen
        # in welk deel van de site je bent.
        "eyebrow": '<p class="eyebrow">Seizoenswijzer</p>',
        "sectie": "seizoen",
        "voetnoot": voetnoot_seizoen(data["seizoensregel"]),
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
    # Geen hero met "Seizoenswijzer" erin: dat woord staat al als bovenschrift
    # in de kop, en twee keer dezelfde naam onder elkaar leest als een fout.
    # Het bovenschrift is hier dus de h1.
    inhoud = (
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
        "eyebrow": '<h1 class="eyebrow">Seizoenswijzer</h1>',
        "sectie": "seizoen",
        "voetnoot": voetnoot_seizoen(data["seizoensregel"]),
        "inhoud": inhoud,
    }


def overpagina(data):
    """Over deze site: wat het is, waar de cijfers vandaan komen, wat de site
    níét doet, en hoe je een fout meldt.

    Dit is de pagina die het langst ontbrak. Er was geen enkele manier om Jan te
    bereiken, terwijl de audit van 2 september zeven producten vond met een
    prijs die pas bij twee stuks gold — precies het soort fout dat een bezoeker
    in de winkel als eerste ziet en niemand kon doorgeven. Daarnaast staan hier
    de dingen die op elke pagina hoorden maar nergens pasten: de verplichte
    bronvermelding, wat de site niet belooft, en wat er met je gegevens gebeurt.
    """
    inhoud = """  <p class="intro">Elke ochtend de lopende biologische groente- en
  fruitaanbiedingen van zes supermarkten op één pagina, plus een
  seizoenskalender. Gemaakt omdat ik ze zelf wilde kunnen vergelijken zonder
  zes apps te openen.</p>

  <section class="group">
    <div class="group-title"><h2>Waar de cijfers vandaan komen</h2></div>
    <div class="prose">
      <p><strong>De aanbiedingen</strong> komen van de
      <a href="https://www.prijsprofeet.nl/" rel="noopener">PrijsProfeet-API</a>,
      die de actiecatalogus van tien Nederlandse ketens ontsluit. Daar filter ik
      zelf de biologische groente en het fruit uit. Voor Lidl komt er een
      aanvulling bij van <a href="https://www.folderz.nl/" rel="noopener">Folderz.nl</a>,
      omdat PrijsProfeet voor die keten weinig producten heeft.</p>

      <p><strong>De seizoenskalender</strong> is met de hand samengesteld op
      basis van de klassieke Nederlandse seizoenslogica — volle grond, plastic
      tunnel, onverwarmde kas — zoals Milieu Centraal en het Voedingscentrum die
      hanteren. Van het seizoen betekent hier: nu in Nederland geoogst, of uit
      de bewaring van een eerdere Nederlandse oogst. Een enkele soort komt in de
      piekmaanden uit Zuid-Europa; dat staat dan bij het product.</p>

      <p><strong>Het aantal bestrijdingsmiddelen</strong> komt uit de
      <a href="https://www.pan-netherlands.org/eetwijzer/" rel="noopener">PesticidenEetwijzer</a>
      van PAN-Nederland, gebaseerd op NVWA-metingen over 2023 tot 2025. Het
      🧴 staat bij de soorten die ruim boven het gemiddelde van hun categorie
      uitkomen. Bij soorten die de NVWA niet apart meet staat geen cijfer.</p>

      <p class="let-op"><strong>Belangrijk bij dat laatste:</strong> die
      metingen gaan over het hele handelskanaal, niet specifiek over biologisch.
      Als hier bij een peer staat dat er meer bestrijdingsmiddelen op zitten dan
      gemiddeld, gaat dat dus over peren in het algemeen — niet over de
      biologische peer die je hiernaast in de aanbieding ziet. Het cijfer is een
      reden om bij dat product eens naar bio te kijken, geen uitspraak over de
      bio-variant zelf.</p>
    </div>
  </section>

  <section class="group">
    <div class="group-title"><h2>Wat deze site niet doet</h2></div>
    <div class="prose">
      <p><strong>Prijzen zijn indicatief.</strong> Ze worden een keer per dag
      opgehaald en kunnen in de winkel anders zijn. Controleer altijd in het
      schap; ik ben niet de winkel en niet de bron.</p>

      <p><strong>Geen prijsvergelijking tussen winkels.</strong> Er zijn te
      weinig biologische acties om zinnige overlap te vinden — vaak een handvol
      per winkel per week — en de productcodes die daarvoor nodig zijn ontbreken
      bij een deel van de ketens.</p>

      <p><strong>Bij een stapelkorting weet ik niet wat één stuk kost.</strong>
      Staat er "vanaf 2 stuks", dan geldt de genoemde prijs pas bij dat aantal.
      Wat je voor één stuk betaalt zit niet in de brondata, en dat verzin ik er
      niet bij.</p>

      <p><strong>Geen advertenties, geen affiliate links.</strong> Er staat geen
      enkele verdienlink naar de winkels die hier vergeleken worden, en de site
      is onafhankelijk van alle genoemde ketens. Merknamen en huisstijlkleuren
      worden alleen gebruikt om de winkels te herkennen.</p>
    </div>
  </section>

  <section class="group">
    <div class="group-title"><h2>Een fout gezien?</h2></div>
    <div class="prose">
      <p>Graag. Staat er een prijs die in de winkel niet klopt, of een product
      dat geen groente of fruit is? Dat gebeurt: de filters werken op
      productnamen en die zijn niet altijd eenduidig. Een mailtje met de naam
      van het product en de winkel is genoeg.</p>
      <p class="contact"><a href="mailto:jan@styrinth.nl?subject=Het%20Bio%20Lijstje">jan@styrinth.nl</a></p>
    </div>
  </section>

  <section class="group">
    <div class="group-title"><h2>Wie en wat</h2></div>
    <div class="prose">
      <p>Gemaakt en onderhouden door Jan van den Engel. Het draait op een
      Raspberry Pi bij mij thuis, die elke ochtend de data ophaalt en
      naar GitHub publiceert. De broncode is openbaar onder de MIT-licentie:
      <a href="https://github.com/JanvdEngel/Bio-lijstje" rel="noopener">github.com/JanvdEngel/Bio-lijstje</a>.
      Die licentie geldt voor de code, niet voor de prijs- en residudata — die
      is van de bronnen hierboven.</p>
    </div>
  </section>

  <section class="group">
    <div class="group-title"><h2>Privacy</h2></div>
    <div class="prose">
      <p>Ik verzamel zelf niets: geen account, geen formulier, geen
      advertentienetwerk. Wat je hier instelt — het lichte of donkere thema,
      welke winkels je uitzet — blijft in je eigen browser en komt nooit bij
      mij.</p>

      <p>Twee dingen gebeuren wel, en die noem ik liever dan dat je ze zelf
      ontdekt. Bezoekaantallen worden geteld met
      <a href="https://www.goatcounter.com/help/privacy" rel="noopener">GoatCounter</a>,
      dat geen cookies plaatst en geen persoonsgegevens bewaart. En de lettertypen
      komen van Google Fonts, waardoor je IP-adres bij Google terechtkomt. Dat
      laatste wil ik nog wegnemen door de lettertypen zelf te hosten.</p>
    </div>
  </section>
"""
    return {
        "pad": HIER.parent / "over" / "index.html",
        "titel": "Over Het Bio Lijstje — bronnen, contact en privacy",
        "og_titel": "Over Het Bio Lijstje",
        "beschrijving": (
            "Waar de biologische aanbiedingen en de seizoensdata vandaan komen, "
            "wat deze site niet belooft, hoe je een fout meldt, en wat er met je "
            "gegevens gebeurt."
        ),
        "canonical": "https://hetbiolijstje.nl/over/",
        "eyebrow": '<h1 class="eyebrow">Over deze site</h1>',
        "sectie": "over",
        "voetnoot": VOETNOOT_OVER,
        "inhoud": inhoud,
    }


def schrijf(pagina, sjabloon):
    tekst = sjabloon
    for sleutel, waarde in (
        ("{{TITEL}}", esc(pagina["titel"])),
        ("{{OG_TITEL}}", esc(pagina["og_titel"])),
        ("{{BESCHRIJVING}}", esc(pagina["beschrijving"])),
        ("{{CANONICAL}}", pagina["canonical"]),
        ("{{EYEBROW}}", pagina["eyebrow"]),
        ("{{NAV}}", nav(pagina["sectie"])),
        ("{{VOETNOOT}}", pagina["voetnoot"]),
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

    paginas = [overzichtspagina(data), overpagina(data)]
    paginas += [maandpagina(data, i, residu) for i in range(12)]

    for p in paginas:
        n = schrijf(p, sjabloon)
        rel = p["pad"].relative_to(HIER.parent)
        print(f"  {str(rel).replace(chr(92), '/'):34} {n:6} bytes   {p['titel'][:52]}")
    print(f"\n{len(paginas)} pagina's gebouwd uit {DATA.name}")


if __name__ == "__main__":
    main()
