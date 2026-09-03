#!/usr/bin/env python3
"""
Bio Groente & Fruit — AH / Jumbo / Lidl / Aldi / Dirk / Plus
=====================================================================
Standalone script (GEEN Home Assistant nodig). Draait via cron, 1x per week,
en schrijft een JSON-bestand dat de telefoon-app (www/index.html) uitleest.

Eén feature (zie README voor de achtergrond van deze opzet): "aanbiedingen"
— lopende bio AGF-acties per winkel, via twee gecombineerde bronnen:

1. De publieke PrijsProfeet-API. We halen per winkel de volledige
   actiecatalogus op via /products (gepagineerd) en filteren die zelf. Dat is
   bewust géén /search meer: zoeken vereist dat je het juiste woord raadt, en
   dat bleek producten stil te missen — "Jumbo Biologisch Voorgekookte
   Maïskolven" kwam bij geen enkele zoekterm terug maar staat wel in
   /products. Bulk geeft ~3,5x meer bio-treffers per winkel.
2. Folderz.nl (scraping) als aanvulling, alléén voor Lidl: PrijsProfeet heeft
   voor Lidl maar ~180 producten tegen ~2400 voor AH, en vrijwel al het verse
   groente/fruit op de pagina komt uit deze bron.

Resultaten worden samengevoegd en op naam gededupliceerd. Geen cross-store
matching — acties zijn te schaars om een zinnig prijsverschil-overzicht op te
bouwen (soms enkele bio-items per winkel per week), en de EAN-dekking die
daarvoor nodig is ontbreekt bij Aldi en Lidl.

Gebruik:
    python3 fetch_bio_prices.py

Installatie & cron: zie README.md.
"""

import os
import re
import json
import time
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bio_prices")

# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------

AGF_KEYWORDS = [
    "appel", "banaan", "bananen", "tomaat", "tomaten", "komkommer", "paprika",
    "ui", "uien", "bosui", "aardappel", "wortel", "peen", "sla", "spinazie",
    "avocado", "citroen", "courgette", "champignon", "oesterzwam", "shiitake",
    "portobello", "kastanjechampignon", "druif", "druiven", "sinaasappel",
    "peer", "peren", "broccoli", "bloemkool", "prei", "aardbei", "framboos",
    "frambozen", "blauwe bes", "bosbes", "bessen", "kruisbes", "braam",
    "bramen", "kiwi", "mandarijn", "radijs", "witlof", "boon", "bonen",
    "snijboon", "knoflook", "venkel", "asperge", "mango", "meloen",
    "sperzieboon", "rucola", "andijvie", "koolraap", "pompoen", "biet",
    "selderij", "gember", "limoen", "kool", "mais", "maïs",
    # Onze eigen seizoenskalender noemt 51 producten; 24 daarvan herkende dit
    # filter niet. Als /seizoen/ zegt dat rabarber nu van het seizoen is, moet
    # "Bio rabarber" in een aanbieding hier ook binnenkomen.
    "pruim", "pruimen", "nectarine", "perzik", "kersen", "rabarber",
    "doperwt", "spruit", "pastinaak", "koolrabi", "postelein", "raapstelen",
    "walnoot", "knolselderij",
    # Gemeten tegen de catalogus: kwamen langs als echte AGF-aanbiedingen maar
    # stonden in geen enkel trefwoord.
    "ananas", "vijg", "dadel", "kaki", "grapefruit", "bimi", "romaine",
    "paksoi", "tauge", "granaatappel", "sugar snap",
]

# Matcht "bio", maar ook "biologisch"/"biologische" — AH, Jumbo en Plus noemen
# hun bio-huismerk namelijk "Biologisch" ("AH Biologisch Blauwe bessen"), en met
# een kale \bbio\b vielen die allemaal buiten de boot. De optionele staart is
# bewust smal: "biobrandstof" of "bioscoop" matcht nog steeds niet, want daar
# ontbreekt de woordgrens na "bio" én de "logisch"-tussenstap.
BIO_PATTERN = re.compile(r"\bbio(?:logisch\w*)?\b", re.IGNORECASE)

# Categorieën van PrijsProfeet (slugs uit /api/v1/categories) waar een
# AGF-trefwoord vrijwel altijd een valse treffer is: "Lavazza Bio Bonen" is
# koffie, "Bonbebe pompoen aardappel kip" is babyvoeding, en wijn heet nu eenmaal
# vaak naar fruit. Uitbreidbaar — "frisdrank" (vruchtensap) en "huishouden"
# (diervoer met groente erin) zijn logische volgende kandidaten.
EXCLUDED_CATEGORIES = {
    # Toegevoegd toen het filter samenstellingen ging herkennen: "ananas" haalt
    # dan ook "DubbelDrank Ananas & guave" binnen en "granaatappel" de kombucha.
    # Het commentaar hieronder noemde beide al als logische kandidaat.
    "frisdrank",
    "huishouden",
    "koffie-thee",
    "drogisterij",
    "bier-wijn-sterke-drank",
    # Vlees, vis en kaas/vleeswaren horen per definitie niet in een
    # groente&fruit-lijst; hier kwamen bij het testen o.a. biologische
    # hamburgers, olijven en tomatentapenade uit.
    "vlees",
    "vis",
    "kaas",
    # Snoep/koek/chips: hier zaten "Zonnatura Maiswafel chocolade" (via "mais")
    # en "Leev Linzenwafels paprika" (via "paprika"). Dit is ook de reden dat
    # "mais" wél een voorvoegsel mag blijven, anders dan "sla": "Maïskolven"
    # heeft die voorvoegselregel nodig, en de wafels vangen we hier op.
    "snoep-koek-chips",
    # Pasta en wereldkeuken: hier zaten gevulde pasta's die via een
    # ingrediëntwoord binnenkwamen ("Tortelloni ricotta spinazie"). Gemeten wat
    # dit kost: de enige andere bio-treffer in deze categorie was een
    # gembershot. Blikken tomaten en Hak-bieten zitten in
    # soepen-conserven-sauzen en blijven dus staan.
    "pasta-rijst-wereldkeuken",
    # Toegevoegd bij het opnemen van Ekoplaza (augustus 2026). Zelfde redenering
    # als vlees/vis/kaas hierboven: een bereiding met groente erin is geen
    # groente. Brood-bakkerij gaf "Bruschetta tomaat", zuivel-eieren gaf de
    # roomkefirs, vega gaf "Hummus zongedroogde tomaat". Gemeten over alle zeven
    # ketens: samen 53 treffers weg, geen enkele bij de zes winkels die er al
    # stonden.
    "brood-bakkerij",
    "zuivel-eieren",
    "vega",
    # "Siroop aardbei" van €14,35 stond op 1 september live als vers fruit: het
    # matchte op "aardbei", Ekoplaza is een volledig-bio winkel dus het label
    # volstond, en de categorie stond niet in deze lijst. Ontbijtproducten zijn
    # net als vlees en zuivel per definitie geen groente of fruit.
    "ontbijt",
}

# Nederlandse samenstellingen plakken vast (bv. "tomatenpulp", "appelmoes"), dus de
# meeste keywords mogen als voorvoegsel matchen (alleen een woordgrens vóór het
# keyword, geen grens erna). Een paar korte keywords zijn dat te riskant voor —
# "ui" zou dan ook "uitverkoop" matchen, "kool" ook "koolzuurhoudend" — die
# blijven hele-woord-only.
#
# "sla" hoort hier ook bij (augustus 2026): als voorvoegsel matchte het
# "Slavinken" en "Slagershamburgers" — allebei vlees. En het kostte niets, want
# de echte samenstellingen ("kropsla", "veldsla") eindigen op "sla" en werden
# door een voorvoegselregel toch al niet gevonden.
# Drie klassen, want Nederlands plakt zelfstandige naamwoorden aan elkaar en
# verkort daarbij de klinker. "banaan" zit niet in "bananen" (aa -> a), en
# "sla" staat niet los in "veldsla". Tot nu toe matchte elk trefwoord alleen
# aan het begin van een woord, waardoor "Bio Fairtrade bananen" (€1,49, was
# €2,19), "Jumbo Biologisch Snoeptomaten" en "Jumbo Biologisch Veldsla" niet op
# de site kwamen terwijl ze wél in de API stonden.
#
# Welk trefwoord in welke klasse hoort is gemeten tegen de hele catalogus van
# 9.165 producten, niet beredeneerd:
#
# - SUBSTRING: lang genoeg om overal in een woord te mogen staan. "tomaten"
#   pakt zo "Snoeptomaten" én "tomatenpulp"; nul valse treffers gemeten.
# - TAIL: mag een woord vóór zich hebben maar moet op een woordgrens eindigen.
#   Een kale substring-match op "sla" vindt "Vakslager" en "hagelslag" (62
#   valse treffers), met de woordgrens erachter nul.
# - WHOLE: alleen als los woord. "ui" als substring vindt "kruidnoten",
#   "quinoa" en "Grapefruits" — 615 valse treffers, nul echte winst.
_AGF_WHOLE_WORD_ONLY = {"ui", "uien"}
# "wortel" en "postelein" horen in SUBSTRING en niet hier: de staart-klasse
# eist een woordgrens ná het trefwoord, en daardoor viel "Wortelen" eraf.
_AGF_TAIL = {"sla", "kool", "peen", "bonen", "boon", "bes", "bessen"}
_AGF_SUBSTRING = {
    "tomaat", "tomaten", "komkommer", "paprika", "spinazie", "sinaasappel",
    "peren", "meloen", "selderij", "wortel", "bananen", "granaatappel",
    "postelein",
}

# Producten die een AGF-trefwoord in de naam hebben maar toch geen groente of
# fruit zijn. Nodig omdat de categorie van PrijsProfeet hier niet helpt: AH zet
# ook thee en vruchtensap onder "groente-fruit", vermoedelijk omdat het in het
# AGF-schap ligt. Zo kwamen "Groene thee citroengras" (via "citroen") en "Vers
# geperst sap appel aardbei" (via "appel") in de lijst.
#
# Gedroogd fruit en notenmixen blijven bewust wél staan: dat ís fruit.
#
# Let op de woordgrenzen. "sap" mag alleen als achtervoegsel of los woord
# matchen — als kale substring sneuvelt "sinaaSAPpel" ook, en dat is precies
# wél groente/fruit.
_NIET_AGF_PATRONEN = (
    re.compile(r"sap\b", re.IGNORECASE),          # "appelsap", "vers geperst sap"
    re.compile(r"\bthee|thee\b", re.IGNORECASE),  # "groene thee", "kruidenthee"
    # Samengestelde gerechten waar een groente in zit, in plaats van de groente
    # zelf. Deze staan in categorie soepen-conserven-sauzen, en die kan niet
    # uitgesloten worden: daar zitten Hak rode bieten, Bonduelle maïs en Heinz
    # tomatenblokjes ook in, en dat zijn wél gewoon groenten uit blik.
    re.compile(r"soep\b", re.IGNORECASE),         # "Unox Biologische pompoensoep"
    re.compile(r"saus\b|\bsauzen\b", re.IGNORECASE),  # "pastasaus", "tomatensaus"
    re.compile(r"ketchup", re.IGNORECASE),
    re.compile(r"\bpesto\b", re.IGNORECASE),
    re.compile(r"azijn\b", re.IGNORECASE),        # "appelciderazijn"
    re.compile(r"tapenade|dressing|\bfrito\b", re.IGNORECASE),
    # Achtervoegsel, niet los woord: in "gembershot" staat geen woordgrens vóór
    # "shot". Zelfde valkuil als bij "sap" in "appelsap".
    re.compile(r"shot\b", re.IGNORECASE),         # "Bio gembershot" — een drankje
    # Onderstaande kwamen bij Ekoplaza binnen, waar de categorie niet redt:
    # die keten zet quiche, chips en kaasbolletjes zélf onder "groente-fruit".
    # Elk patroon hieronder is gemeten en verwijdert daadwerkelijk iets; wat
    # niets deed ("salade", "taart", "wafel", "burger") staat er bewust niet in.
    # "salade" is er ook uit gelaten omdat een zak slamix wél verse groente is.
    re.compile(r"quiche", re.IGNORECASE),
    re.compile(r"chips\b", re.IGNORECASE),        # "Aardappelchips truffel"
    re.compile(r"dip\b", re.IGNORECASE),          # "Tomaten- basilicumdip"
    re.compile(r"hummus", re.IGNORECASE),
    re.compile(r"kefir", re.IGNORECASE),
    re.compile(r"yog(?:h)?urt", re.IGNORECASE),
    re.compile(r"olij(?:f|ven)", re.IGNORECASE),  # olijven staan al niet in de lijst
    re.compile(r"biscuit", re.IGNORECASE),
    re.compile(r"bruschetta", re.IGNORECASE),
    re.compile(r"kaas", re.IGNORECASE),           # "Goudse kaasbolletjes ui"
    # "Siroop aardbei" van €14,35 stond op 1 september een dag lang als vers
    # fruit op de site. Eerst geprobeerd met een bredere regel — alles met een
    # hoeveelheid in milliliters weren — maar gemeten bleek die precies één
    # product te raken dat we wél willen: "Bio appelmoes" (370 ml). Appelmoes is
    # één product van appels, net als de Hak-bieten die we bewust houden. Dus op
    # naam, en dat vangt beide siropen in de catalogi ongeacht hun categorie.
    re.compile(r"siroop", re.IGNORECASE),
    # "stroop" naast "siroop": dadelstroop en appelstroop kwamen binnen via de
    # trefwoorden "dadel" en "appel".
    re.compile(r"stroop", re.IGNORECASE),
    # Bonen die geen boon zijn. Nodig sinds "bonen" ook aan het eind van een
    # samenstelling mag matchen: dat haalt "sperziebonen" binnen, maar ook
    # "cacaobonen" en "koffiebonen". Kidney-, zwarte en sojabonen blijven er
    # bewust wél in: dat zijn bonen, en ze horen onder Voorraad net als de Hak
    # bio bieten die al op de site staan. Sojamelk is weer geen boon.
    # Bij Ekoplaza is de naam de enige verdediging, want daar volstaat het
    # bio-label; en Folderz levert helemaal geen categorie.
    re.compile(r"cacaobo|koffiebo|sojabo\w*\s*(?:melk|drink)", re.IGNORECASE),
    # Kool die geen kool is. "kool" mag nu ook een samenstelling afsluiten, dus
    # houtskool matcht. Zuurkool blijft er bewust wél in: dat is bewaarde
    # groente, net als de Hak bio bieten die al op de site staan.
    re.compile(r"houtskool", re.IGNORECASE),
    # Derde ronde Ekoplaza-lekken (2 september). Die keten zet honing, crackers
    # en knäckebröd onder "groente-fruit", en kombucha onder "frisdrank" — de
    # categorie zegt daar dus vrijwel niets, en dat is de reden dat deze lijst
    # blijft groeien. Gemeten over alle zeven verse catalogi: samen halen deze
    # zeven regels 11 van de 32 doorgekomen producten weg, en de 21 die
    # overblijven zijn allemaal echt groente of fruit, vers of uit blik.
    re.compile(r"honing", re.IGNORECASE),         # "Spaanse sinaasappelhoning"
    re.compile(r"cracker", re.IGNORECASE),        # "Groentecracker rode biet"
    re.compile(r"kn[aä]ckebr|knekkebr", re.IGNORECASE),
    re.compile(r"kombucha", re.IGNORECASE),
    re.compile(r"\breep\b", re.IGNORECASE),       # "Zonnatura Reep noten appel"
    re.compile(r"pittenpasta|notenpasta", re.IGNORECASE),
    # Let op de \w+ ervoor. Vastgeplakt is het een snack ("Bonensticks"), los is
    # het een vorm van de groente zelf ("Hak Rode Bieten Sticks"). Een kaal
    # \bsticks\b zou dat tweede product ten onrechte weggooien.
    re.compile(r"\w+sticks\b", re.IGNORECASE),
)

def _agf_klasse(k):
    if k in _AGF_WHOLE_WORD_ONLY:
        return "whole"
    if k in _AGF_TAIL:
        return "tail"
    if k in _AGF_SUBSTRING:
        return "substring"
    return "prefix"


_agf_groepen = {"whole": [], "tail": [], "substring": [], "prefix": []}
for _k in AGF_KEYWORDS:
    _agf_groepen[_agf_klasse(_k)].append(_k)


def _agf_deel(sleutels, voor, na):
    if not sleutels:
        return None
    return voor + r"(?:" + "|".join(re.escape(k) for k in sleutels) + r")" + na


AGF_PATTERN = re.compile(
    "|".join(
        deel for deel in (
            # los woord: \bui\b
            _agf_deel(_agf_groepen["whole"], r"\b", r"\b"),
            # eind van een samenstelling: veldsla, spitskool, sperziebonen
            _agf_deel(_agf_groepen["tail"], r"(?:\b|\w)", r"\b"),
            # overal in het woord: Snoeptomaten, tomatenpulp
            _agf_deel(_agf_groepen["substring"], r"", r""),
            # begin van een woord: appel -> appels, appelmoes
            _agf_deel(_agf_groepen["prefix"], r"\b", r""),
        ) if deel
    ),
    re.IGNORECASE,
)

# Welke winkels meedoen: store_label -> (prijsprofeet_retailer_slug,
# folderz_winkel_slug of None om Folderz voor die winkel over te slaan).
#
# Folderz staat alleen aan voor Lidl. Bij AH en Jumbo leverde de volledige
# paginering vrijwel nooit iets op dat PrijsProfeet niet al had — puur tijd
# kosten zonder toegevoegde waarde. Hertest augustus 2026 bevestigt dat: 2040
# AH-producten over 60 pagina's gaven 7 bio-treffers, allemaal wijn, thee en
# crackers.
#
# Bij Lidl was de redenering dat Folderz een structurele blinde vlek vult: daar
# heeft PrijsProfeet maar ~200 producten en zou vrijwel al het verse
# groente/fruit uit Folderz komen. Nagemeten op 2 september 2026 klopt dat niet
# meer. PrijsProfeet leest dezelfde Lidl-folders (folder_id "lidl_2026-09-02",
# vier folders naast elkaar) en had er 3 van de 4, waaronder de bananen die
# Folderz óók had. Folderz droeg er precies één bij die PrijsProfeet niet had:
# "Alesto Bio Mango", gedroogd fruit uit hun snacklijn. Andersom had
# PrijsProfeet "Bio appelmoes" die Folderz niet had.
#
# Kosten van die ene: 35 pagina's per dag op andermans site, zonder gevraagde
# toestemming. Zie het werkplan — dit staat open als beslissing.
#
# PrijsProfeet ontsluit 10 ketens; nog niet in gebruik: DekaMarkt, Hoogvliet,
# Vomar.
#
# Ekoplaza stond eerder uit omdat hun items geen echte acties waren (actieprijs
# gelijk aan de normale prijs, valid_from uit 2024). Hertest augustus 2026: die
# oude records staan er nog steeds, maar er staan nu wél lopende acties naast
# met een valid_from van deze week. Daarom weer aan, met twee nieuwe filters die
# hiervoor nodig waren — zie de naampatronen en de kortingscheck. Zonder die
# twee leverde Ekoplaza 23 items op waarvan 21 quiche, chips, kefir en olijven;
# mét die twee blijven de 2 over die er horen.
AANBIEDINGEN_STORES = {
    "AH": ("albert_heijn", None),
    "Jumbo": ("jumbo", None),
    # Folderz staat uit sinds 2 september 2026. Zie de toelichting hieronder:
    # PrijsProfeet leest dezelfde Lidl-folders en had er 3 van de 4, waaronder
    # de bananen die de reden waren om Folderz erbij te houden. Folderz droeg
    # er één bij: gedroogd fruit uit Lidl's snacklijn. Dat is geen 35 pagina's
    # per dag op andermans site waard. De code blijft staan: één slug terug op
    # "lidl" en het werkt weer.
    "Lidl": ("lidl", None),
    "Aldi": ("aldi", None),
    "Dirk": ("dirk", None),
    "Plus": ("plus", None),
}

# Winkels waar het hele assortiment biologisch is. Daar volstaat het
# dietary_tags-label, want hun productnamen zeggen vaak niet "bio" — bij een
# 100%-bio winkel is dat immers geen onderscheid. Bij alle andere winkels eisen
# we het label én het woord in de naam, omdat het label alleen niet betrouwbaar
# genoeg bleek (zie _als_bio_agf_actie). Sinds Ekoplaza meedoet is dit geen
# lege voorbereiding meer: van hun 23 bio-AGF-treffers had er nul "bio" in de
# naam staan. Zonder deze uitzondering zou de keten dus niets opleveren.
VOLLEDIG_BIO_WINKELS = {"ekoplaza"}

# Ketens die PrijsProfeet wél ontsluit maar die hier niet meedoen, omdat ze
# geen biologische producten in hun data hebben. Gemeten op 31 augustus 2026:
#
#   Hoogvliet   473 producten, 40 met een dieet-label (allemaal "vegetarisch"),
#               nul met een bio-label en nul met "bio" in de naam.
#   DekaMarkt  1118 producten, 2 met een bio-label, geen daarvan groente/fruit.
#   Vomar       167 producten, geen enkel dieet-label.
#
# Bij Hoogvliet is dat dus geen toevallig magere week: de labels wórden gezet,
# alleen nooit "bio". Maar dat kan veranderen zonder dat iemand het meldt, en
# elk kwartaal handmatig opnieuw uitzoeken is zonde. Daarom controleert
# controleer_kandidaten() ze elke ronde en zegt het als er iets verschijnt.
KANDIDAAT_WINKELS = {
    # Ekoplaza deed van 1 tot 2 september mee en is er weer uit. Niet omdat de
    # keten niets levert — vier echte producten per dag — maar omdat hun
    # unified_category niets zegt: honing, crackers, knäckebröd en quiche staan
    # daar onder "groente-fruit" en kombucha onder "frisdrank". In drie rondes
    # kwamen er 21 quiche/chips, 1 siroop en 6 snacks door, en elke ronde vroeg
    # nieuwe naampatronen. Vier producten per dag is dat onderhoud niet waard.
    # Blijft als kandidaat staan, dus de wachter meldt het als hun data verbetert.
    # Zie het werkplan: een andere ingang voor Ekoplaza (Folderz of een eigen
    # bron) staat op de lange baan.
    "Ekoplaza": "ekoplaza",
    "Hoogvliet": "hoogvliet",
    "DekaMarkt": "dekamarkt",
    "Vomar": "vomar",
}

PRIJSPROFEET_PRODUCTS_URL = "https://www.prijsprofeet.nl/api/v1/products"
PRIJSPROFEET_PAGE_SIZE = 100  # harde grens van de API; 200 en 500 geven 0 resultaten
PRIJSPROFEET_MAX_PAGES = 60  # veiligheidsgrens; AH is de grootste met ~24 pagina's
# Zonder API-key geldt 30 requests/min op de bulk-endpoints, en dan per IP. 2,5s
# pauze houdt ons op ~24/min, dus met marge — maar niet genoeg marge: over één
# week kregen 18 van 175 verzoeken alsnog een 429, allemaal op het doorpagineren.
#
# Met een gratis key telt de limiet op de key in plaats van het IP en gaat hij
# naar 150/min. 0,5s pauze is dan ~120/min, weer met marge, en de hele ronde gaat
# van ruim vijf minuten naar ongeveer één. De key komt uit de add-on-opties; is
# hij er niet, dan valt alles terug op het trage tempo en werkt het gewoon.
PRIJSPROFEET_PAGE_PAUZE = 2.5
PRIJSPROFEET_PAGE_PAUZE_KEY = 0.5
# Hoe vaak we een snelheidsgrens op dezelfde pagina accepteren voordat we die
# winkel opgeven. Zonder deze grens kon de lus oneindig doordraaien.
PRIJSPROFEET_MAX_429 = 3
FOLDERZ_MAX_PAGES = 120  # veiligheidsgrens; Lidl had er ~34-36 tijdens het bouwen
MAX_ITEMS_PER_STORE = 15  # cap na dedup, grootste korting eerst — houdt winkels in verhouding

OUTPUT_PATH = Path(__file__).parent / "www" / "data" / "bio_prices.json"
HISTORY_PATH = Path(__file__).parent / "www" / "data" / "geschiedenis.json"
# 30 prijs*wijzigingen* per product, niet 30 fetches — zie
# enrich_and_record_history(). Bij een actie die per week wisselt is dat jaren.
HISTORY_MAX_PER_PRODUCT = 30

# De prijsgeschiedenis is het enige in dit project dat niet opnieuw op te halen
# is. De code staat in git, de aanbiedingen komen van de API, maar deze reeks
# bestaat maar één keer — hij groeit elke dag met wat we die dag zagen.
#
# Hij leeft in /share (blijft staan, ook als de add-on verwijderd wordt), maar
# /share zit níét in de nachtelijke Home Assistant-back-up: daar staat bij
# folders alleen "ssl". De eigen /data van de add-on zit er wél in, als
# local_bio_bord.tar.gz. Daarom na elke geslaagde ronde een kopie daarheen, plus
# een handvol gedateerde kopieën — die vangen het geval waarin het bestand
# vandaag stuk is geschreven en dat pas over een week opvalt.
#
# Let op wat dit NIET oplost: alles staat nog op dezelfde SD-kaart. Tegen een
# stukke kaart helpt alleen een kopie buiten de Pi.
ADDON_DATA_DIR = Path("/data")
HISTORY_BACKUPS = 7
WWW_DIR = Path(__file__).parent / "www"
# Alleen de data pushen, niet de website-bestanden. Die stonden hier eerst ook
# in (index.html, manifest.json, icon.png, sw.js), en dat heeft in augustus 2026
# drie keer het ontwerp overschreven: een wijziging die naar GitHub was gepusht
# maar nog niet naar de Pi, werd de volgende ochtend teruggedraaid door de kopie
# die de Pi nog had. De data is het enige dat hier daadwerkelijk verandert.
#
# Gevolg: website-wijzigingen zijn nu puur een git-push. Wil je ze ook op de
# lokale pagina (http://<pi-ip>:8099) zien, kopieer ze dan alsnog naar
# /addons/bio_bord/www/ en draai een rebuild — maar vergeten kan de publieke
# site niet meer stukmaken.
GITHUB_PUBLISH_FILES = ["index.html", "data/bio_prices.json"]

# index.html wordt gegenereerd uit template.html, en template.html wordt door dit
# script nooit aangeraakt. Die scheiding is er met een reden: eerder was
# index.html tegelijk handwerk én machinewerk, en toen overschreef de Pi drie
# keer een ontwerpwijziging die alleen naar GitHub was gepusht. Nu is er per
# bestand precies één eigenaar.
TEMPLATE_PATH = Path(__file__).parent / "www" / "template.html"
HTML_OUTPUT_PATH = Path(__file__).parent / "www" / "index.html"
JSONLD_START = "<!--JSONLD-->"
JSONLD_EINDE = "<!--/JSONLD-->"
DATUM_START = "<!--DATUM-->"
DATUM_EINDE = "<!--/DATUM-->"
PRODUCTEN_START = "<!--PRODUCTEN-->"
PRODUCTEN_EINDE = "<!--/PRODUCTEN-->"


# ---------------------------------------------------------------------------
# Feature 1: bio-aanbiedingen per winkel (PrijsProfeet-API + Folderz.nl)
# ---------------------------------------------------------------------------

def fetch_aanbiedingen(store_label, retailer_slug, folderz_slug):
    """Combineert twee bronnen voor de bio-aanbiedingen van één winkel:
    - PrijsProfeet-API: schoon, gratis, sleutelloos JSON.
    - Folderz.nl: trager (scraping, pagineert door alle lopende acties),
      maar vult structurele gaten van PrijsProfeet op. Alleen ingeschakeld
      voor winkels waar dat nodig bleek (folderz_slug niet None) — zie
      AANBIEDINGEN_STORES hierboven.
    Resultaten van beide worden samengevoegd en op (genormaliseerde) naam
    gededupliceerd, zodat een product dat in beide bronnen voorkomt maar
    één keer getoond wordt.

    Geeft (items, status) terug. De status is "ok", "onvolledig" of "mislukt"
    en reist mee tot in de HTML, zodat een storing er op de pagina niet uitziet
    als een week zonder aanbiedingen."""
    resultaten, status = fetch_aanbiedingen_prijsprofeet(store_label, retailer_slug)
    if folderz_slug:
        # Folderz is een aanvulling; als die faalt blijft de winkel bruikbaar.
        # De status wordt er dus niet slechter van dan "onvolledig".
        aanvulling = fetch_aanbiedingen_folderz(store_label, folderz_slug)
        resultaten += aanvulling
        if aanvulling and status == "mislukt":
            status = "onvolledig"

    gezien = set()
    gededupliceerd = []
    for item in resultaten:
        sleutel = _naamsleutel(item["naam"])
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        gededupliceerd.append(item)

    # Cap per winkel, grootste korting eerst — anders kan een winkel met een
    # grote catalogus (AH en Plus hebben er elk ~2300) de pagina domineren
    # t.o.v. de andere winkels.
    def _korting(item):
        if item.get("normale_prijs"):
            return item["normale_prijs"] - item["actieprijs"]
        return 0
    gededupliceerd.sort(key=_korting, reverse=True)
    gededupliceerd = gededupliceerd[:MAX_ITEMS_PER_STORE]

    log.info(f"{store_label} aanbiedingen totaal: {len(gededupliceerd)} bio AGF-acties (na dedupliceren)")
    return gededupliceerd, status


# Patronen die verraden dat een actieprijs pas geldt bij méér dan één stuk.
# Zonder dit tonen we een halveprijs-actie als gewone stuksprijs: "AH Biologisch
# Blauwe bessen" stond op 2,19 van 4,39, maar de voorwaarde was "4 STAPELEN TOT
# 50%" — één bakje kost dus meer. De velden multi_buy_quantity/multi_buy_price
# van de API zijn bij die actie leeg, dus de voorwaarde staat alléén in de vrije
# tekst van promotional_keywords; daarom kijken we daar zelf naar.
#
# Het moet een aantal-patroon zijn, niet los een cijfer plus een trefwoord: het
# label "voor 1,00" is gewoon een prijs ("nu voor 1,00") en géén voorwaarde,
# terwijl "2 VOOR 2.99" dat wél is. Daar zit een cijfer vóór het woord.
_VOORWAARDE_PATRONEN = (
    re.compile(r"\b\d+\s*x?\s*voor\b", re.IGNORECASE),   # "2 voor 2.99"
    re.compile(r"\b\d+\s*\+\s*\d+", re.IGNORECASE),      # "5 + 1 gratis"
    re.compile(r"\b\d+\s*stapel", re.IGNORECASE),        # "4 stapelen tot 50%"
    re.compile(r"\b\d+\s*e?\s*halve\b", re.IGNORECASE),  # "2e halve prijs"
    re.compile(r"\b\d+\s*hal(?:en|f)\b", re.IGNORECASE), # "3 halen 2 betalen"
)


def _actievoorwaarde(item):
    """Geeft een korte, leesbare voorwaarde terug ("5 + 1 gratis") als de
    actieprijs pas bij meerdere stuks geldt, of None als er niets aan de hand is.
    Zuivere labels als "Actie", "OP=OP" of "20% korting" tellen niet als
    voorwaarde: die zeggen niets over een minimum-aantal."""
    aantal = item.get("multi_buy_quantity")
    prijs = item.get("multi_buy_price")
    if isinstance(aantal, int) and aantal > 1 and isinstance(prijs, (int, float)):
        return f"{aantal} voor {_euro(prijs)}"

    for label in item.get("promotional_keywords") or []:
        if not isinstance(label, str):
            continue
        if any(p.search(label) for p in _VOORWAARDE_PATRONEN):
            return label.strip()
    return None


# Signalen dat een product niet vers is maar uit blik, pot, zak of vriezer komt.
# "Voorraad" dekt die vier bewust samen: zo koopt iemand het ook — vers voor deze
# week, voorraad als het goedkoop is.
_VOORRAAD_PATRONEN = (
    re.compile(r"gedroogd|\bgedr\.", re.IGNORECASE),
    re.compile(r"\bblik\b|\bpot\b|\bglas\b", re.IGNORECASE),
    re.compile(r"diepvries|ingevroren|\bbevroren\b", re.IGNORECASE),
    re.compile(r"zoetzuur|\bconserven\b", re.IGNORECASE),
    re.compile(r"gekookt|voorgekookt", re.IGNORECASE),
)
# Categorieën van PrijsProfeet die de indeling kunnen bepalen als de naam niets
# verraadt. Folderz levert geen categorie, dus daar blijft het bij de naam.
_VOORRAAD_CATEGORIEEN = {"soepen-conserven-sauzen", "diepvries"}
_VERS_CATEGORIEEN = {"groente-fruit"}


def _soort(naam, categorie=None):
    """Bepaalt of een product bij "Vers" of bij "Voorraad" hoort.

    De naam gaat voor op de categorie: "AH Biologisch Rode bieten gekookt" staat
    bij de bron in groente-fruit, maar is voorgekookt en dus voorraad. Zegt de
    naam niets en is er geen categorie (alle Folderz-items), dan wordt het vers —
    dat is daar vrijwel altijd juist, want de verse Lidl-producten komen uit die
    bron."""
    for patroon in _VOORRAAD_PATRONEN:
        if patroon.search(naam):
            return "voorraad"
    if categorie in _VOORRAAD_CATEGORIEEN:
        return "voorraad"
    if categorie in _VERS_CATEGORIEEN:
        return "vers"
    return "vers"


def _vanaf_aantal(voorwaarde):
    """Haalt het minimum-aantal uit een voorwaarde-label, of None.

    Nodig omdat de API per product maar één prijs levert: de beste. Bij "AH
    Biologisch Witte druiven pitloos" is dat €1,75 van €3,49, met als label
    "2 STAPELEN TOT 50%" — terwijl één doos in de winkel al 25% korting had. Die
    tussentrap zit niet in de data (multi_buy_quantity en promotion zijn leeg),
    dus we kunnen hem niet tonen. Wat we wél kunnen: het aantal naast de prijs
    zetten, zodat die prijs niet als losse stuksprijs gelezen wordt.

    Meestal is het eerste getal in het label dat aantal: "2 STAPELEN",
    "2 VOOR 2.99", "2e halve prijs".

    Behalve bij "X+Y gratis". Daar is het benodigde aantal de SOM, niet het
    eerste getal: bij "1+1 gratis" neem je twee mee en betaal je er één. Dat
    ging fout — het eerste getal was 1, dat viel onder de ondergrens van 2, en
    dus kwam er geen aantal uit. Gevolg: zeven Hak-producten stonden op de site
    met een prijs die pas bij twee stuks geldt en niets erbij. Precies de klacht
    over de witte druiven, in een andere vorm. Gemeten in de live data: €1,50
    tegen een normale prijs van €2,99, dus de bron rekent inderdaad met twee."""
    plus = re.search(r"\b(\d+)\s*\+\s*(\d+)\b", voorwaarde)
    if plus:
        aantal = int(plus.group(1)) + int(plus.group(2))
    else:
        match = re.search(r"\b(\d+)", voorwaarde)
        if not match:
            return None
        aantal = int(match.group(1))
    return aantal if 2 <= aantal <= 12 else None


def _euro(bedrag, entity=False):
    """Nederlandse notatie: 1,75 en niet 1.75. Python's opmaak geeft altijd een
    punt, ongeacht de locale-instelling van de machine, dus dat moet hier.
    De template doet hetzelfde in JavaScript; deze twee horen gelijk te blijven,
    anders leest een bezoeker met JavaScript iets anders dan een crawler."""
    tekst = f"{bedrag:.2f}".replace(".", ",")
    return f"&euro;{tekst}" if entity else f"€{tekst}"


def _als_bio_agf_actie(item):
    """Beoordeelt één PrijsProfeet-record en geeft het terug in ons eigen
    formaat, of None als het niet door de filters komt. Vijf checks:

    1. AGF-trefwoord in de naam (AGF_PATTERN);
    2. categorie niet in EXCLUDED_CATEGORIES — weert koffie, wijn, vlees en
       babyvoeding die toevallig een AGF-woord in de naam hebben;
    3. bio volgens het dietary_tags-label ÉN volgens de naam. Eerder volstond
       één van de twee, met als redenering dat het label betrouwbaarder is dan
       de naam. Dat bleek fout: PrijsProfeet tagt een reeks Jumbo-huismerk-
       producten als "bio" die dat niet zijn, waaronder "Jumbo's Pastasaus
       Tomaat Spekjes". Veertien niet-biologische pasta's en pastasauzen stonden
       daardoor live op een site over biologische groente en fruit. Beide eisen
       haalt precies die veertien eruit en laat alle echte bio-producten staan
       (gemeten tegen de volledige catalogus van alle zes winkels). Bij winkels
       in VOLLEDIG_BIO_WINKELS volstaat het label, want daar zegt geen enkele
       productnaam "bio";
    4. promotion_status niet 'upcoming' of 'historical' — de API levert ook
       nog-niet-geldige en verlopen acties (Aldi's bio-items stonden bij het
       testen allebei op 'upcoming'). Ontbreekt het veld helemaal, dan laten we
       het item door: liever dat dan een lege pagina als de API van vorm
       verandert;
    5. de actieprijs moet lager zijn dan de normale prijs, als die bekend is.
       Anders staat er een gewone schapprijs tussen de aanbiedingen."""
    naam = item.get("name") or ""
    if not naam or not _is_agf(naam):
        return None
    if item.get("unified_category") in EXCLUDED_CATEGORIES:
        return None
    tags = item.get("dietary_tags") or []
    label_zegt_bio = "bio" in tags
    naam_zegt_bio = bool(BIO_PATTERN.search(naam))
    if (item.get("retailer") or "") in VOLLEDIG_BIO_WINKELS:
        # Daar is het label genoeg; zie de toelichting bij die set.
        if not label_zegt_bio:
            return None
    elif not (label_zegt_bio and naam_zegt_bio):
        return None
    status = item.get("promotion_status")
    if status is not None and status != "active":
        return None
    actieprijs = item.get("price")
    if not isinstance(actieprijs, (int, float)):
        return None
    # Geen korting is geen aanbieding. De API levert ook gewone schapprijzen
    # met promotion_status "active"; bij Ekoplaza stond zo "Gemengde sla" op
    # €2,59 van €2,59. Alleen vergelijken als de normale prijs bekend is —
    # Folderz levert die nooit, en daar is dit dus geen test.
    normale_prijs = item.get("original_price")
    if isinstance(normale_prijs, (int, float)) and actieprijs >= normale_prijs:
        return None
    actie = {
        "naam": naam,
        "actieprijs": float(actieprijs),
        "normale_prijs": normale_prijs,
        "soort": _soort(naam, item.get("unified_category")),
    }
    voorwaarde = _actievoorwaarde(item)
    if voorwaarde:
        actie["voorwaarde"] = voorwaarde
        vanaf = _vanaf_aantal(voorwaarde)
        if vanaf:
            actie["vanaf"] = vanaf
    return actie


def fetch_aanbiedingen_prijsprofeet(store_label, retailer_slug):
    """Haalt de volledige actiecatalogus van één winkel op via de publieke
    PrijsProfeet-API (prijsprofeet.nl/api) — gratis en sleutelloos, met
    producten al getagd op dietary_tags (o.a. "bio") en op categorie.
    Bronvermelding conform hun gebruiksvoorwaarden staat in index.html.

    We pagineren door /products en filteren zelf, in plaats van /search met
    zoektermen te bevragen. Zoeken vereist namelijk dat je het juiste woord
    raadt: "Jumbo Biologisch Voorgekookte Maïskolven" kwam bij geen enkele
    zoekterm terug, maar staat wel in de bulk-lijst. Bij Jumbo gaf bulk 39
    bio-getagde items tegen 11 via zoeken.

    Let op: PrijsProfeet bevat alleen lopende acties, geen volledige
    prijscatalogus — er is dus geen doorlopende "normale prijs" beschikbaar
    voor producten die deze week niet in de actie staan (zie README)."""
    import requests

    headers = dict(_prijsprofeet_headers())
    pauze = PRIJSPROFEET_PAGE_PAUZE_KEY if _prijsprofeet_key() else PRIJSPROFEET_PAGE_PAUZE
    resultaten = []
    pagina = 1
    pogingen_429 = 0
    onvolledig = False
    stukgelopen = False
    try:
        while pagina <= PRIJSPROFEET_MAX_PAGES:
            resp = requests.get(
                PRIJSPROFEET_PRODUCTS_URL,
                headers=headers,
                timeout=20,
                params={
                    "retailer": retailer_slug,
                    "page": pagina,
                    "page_size": PRIJSPROFEET_PAGE_SIZE,
                },
            )
            # Een 429 is geen storing maar een snelheidsgrens, en die verdient
            # een adempauze in plaats van het opgeven van de hele winkel. Dat
            # deed dit blok eerder wél: raise_for_status() sprong naar de except
            # eronder, en dan stopte de paginering. Bij AH betekende dat pagina
            # 12 tot en met 28 stilzwijgend weg, met een logregel die er normaal
            # uitzag. PrijsProfeet mailde ons dat 18 van 175 verzoeken in een
            # week een 429 kregen, allemaal op deze paginering.
            if resp.status_code == 429:
                # Zonder bovengrens draaide dit oneindig: `continue` verhoogt de
                # pagina niet, dus bij een API die blijft weigeren bleef de ronde
                # eeuwig wachten en hangen. Nu drie pogingen per pagina, daarna
                # opgeven met wat we hebben — net als bij elke andere fout.
                pogingen_429 += 1
                if pogingen_429 > PRIJSPROFEET_MAX_429:
                    log.warning(
                        f"{store_label}: {PRIJSPROFEET_MAX_429}x een snelheidsgrens op "
                        f"pagina {pagina}; deze winkel is niet compleet opgehaald"
                    )
                    onvolledig = True
                    break
                wacht = _retry_after(resp, standaard=pauze * 4)
                log.info(
                    f"{store_label}: snelheidsgrens op pagina {pagina} "
                    f"(poging {pogingen_429}), {wacht:.0f}s wachten"
                )
                time.sleep(wacht)
                continue
            pogingen_429 = 0
            resp.raise_for_status()
            # /products zet de lijst onder "products", /search onder "results".
            # Beide accepteren, zodat een verkeerde aanname hier niet stil tot
            # een lege pagina leidt (precies wat er bij het bouwen gebeurde).
            body = resp.json()
            producten = body.get("products") or body.get("results") or []
            if not producten:
                break
            for item in producten:
                actie = _als_bio_agf_actie(item)
                if actie:
                    resultaten.append(actie)
            pagina += 1
            time.sleep(pauze)
    except Exception as e:
        # Wat we tot hier hadden houden we: een halve winkel is beter dan geen.
        # Wel als waarschuwing loggen, want een afgebroken winkel is aan het
        # aantal pagina's alleen te zien als je weet hoeveel het er horen te zijn.
        stukgelopen = True
        log.warning(f"Aanbiedingen ophalen mislukt voor {store_label} (PrijsProfeet, pagina {pagina}): {e}")
    log.info(f"{store_label} aanbiedingen: {len(resultaten)} bio AGF-acties (PrijsProfeet, {pagina - 1} pagina's)")

    # Het verschil tussen "niets gevonden" en "niets kunnen ophalen" bestond tot
    # nu toe alleen in het log. Op de pagina zag een bezoeker in beide gevallen
    # "Vandaag geen bio-acties bij Jumbo", en dat is bij een storing gewoon
    # onwaar. Vandaar dat de status meereist tot in de HTML.
    if stukgelopen and pagina == 1:
        status = "mislukt"      # geen enkele pagina gelukt
    elif stukgelopen or onvolledig:
        status = "onvolledig"   # halverwege afgebroken of op de snelheidsgrens
    else:
        status = "ok"
    return resultaten, status


def fetch_aanbiedingen_folderz(store_label, folderz_slug):
    """Vult PrijsProfeet aan met een volledige doorzoeking van Folderz.nl,
    een reclamefolder-aggregator. Live geverifieerd: gewone requests werken
    hier prima op de daadwerkelijke aanbiedingen-pagina's (geen headless
    browser nodig) — een AWS-botcheck bleek alleen op /robots.txt te zitten,
    niet op de content zelf. We pagineren tot een lege of 404-pagina.

    Hier is de productnaam de enige beschikbare informatie: Folderz geeft geen
    categorie of dieetlabel, dus de bio-check kan alleen op de naam. Vandaar dat
    _als_bio_agf_actie() hier niet gebruikt wordt."""
    import requests
    from bs4 import BeautifulSoup

    # Hier stond een nagemaakte Mac-browser. Dat is precies hoe je een blokkade
    # op User-Agent omzeilt, en niets aan wat we doen rechtvaardigt dat: we
    # halen één pad op, één keer per etmaal, met een seconde ertussen. Hun
    # robots.txt staat dat pad expliciet toe ("Allow: /winkels/*?page=*"), dus
    # er is niets te verbergen. Dezelfde identiteit als bij PrijsProfeet, zodat
    # Folderz ons kan herkennen, kan vinden wie we zijn, en ons kan blokkeren
    # als ze dat willen.
    headers = {
        "User-Agent": "BioBordPi/1.0 (+https://hetbiolijstje.nl)",
        "Accept-Language": "nl-NL,nl;q=0.9",
    }
    url = f"https://www.folderz.nl/winkels/{folderz_slug}/aanbiedingen"
    resultaten = []
    page = 1
    try:
        while page <= FOLDERZ_MAX_PAGES:
            resp = requests.get(url, headers=headers, timeout=15, params={"page": page})
            if resp.status_code in (202, 429):
                time.sleep(5)
                continue
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            if len(resp.text) < 500:
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.product")
            if not cards:
                break
            for card in cards:
                name_el = card.select_one(".product__name")
                price_el = card.select_one(".product__price-offer")
                if not name_el or not price_el:
                    continue
                title = name_el.get_text(strip=True)
                if not BIO_PATTERN.search(title) or not _is_agf(title):
                    continue
                actieprijs = _parse_price_string(price_el.get_text(strip=True))
                if actieprijs is None:
                    continue
                normal_el = card.select_one(".product__price-normal")
                normale_prijs = _parse_price_string(normal_el.get_text(strip=True)) if normal_el else None
                resultaten.append({
                    "naam": title,
                    "actieprijs": actieprijs,
                    "normale_prijs": normale_prijs,
                    # Geen categorie beschikbaar bij Folderz; alleen de naam.
                    "soort": _soort(title),
                })
            page += 1
            time.sleep(1)  # niet te hard achter elkaar op andermans site
    except Exception as e:
        log.warning(f"Aanbiedingen ophalen mislukt voor {store_label} (Folderz, pagina {page}): {e}")
    log.info(f"{store_label} aanbiedingen: {len(resultaten)} bio AGF-acties (Folderz, {page - 1} pagina's)")
    return resultaten


def _parse_price_string(text):
    match = re.search(r"(\d+[.,]\d+)", text)
    return float(match.group(1).replace(",", ".")) if match else None


# ---------------------------------------------------------------------------
# Prijsgeschiedenis: "was ik genaaid?" — was deze aanbieding al eens goedkoper?
# ---------------------------------------------------------------------------

def _prijsprofeet_key():
    """De gratis API-key, uit de add-on-opties. Staat bewust niet in deze
    broncode: de repo is publiek. Zonder key werkt alles gewoon, alleen met een
    lagere snelheidsgrens."""
    return (os.environ.get("PRIJSPROFEET_KEY") or "").strip()


def _prijsprofeet_headers():
    """User-Agent volgens hun eigen conventie: naam, versie en een adres waarop
    ze ons kunnen bereiken als er iets aan de data verandert. Zonder key krijgt
    een User-Agent met 'bot', 'crawler', 'spider' of 'slurp' erin een 403 — die
    woorden staan hier dus niet in."""
    headers = {"User-Agent": "BioBordPi/1.0 (+https://hetbiolijstje.nl)"}
    key = _prijsprofeet_key()
    if key:
        headers["X-API-Key"] = key
    return headers


def _retry_after(resp, standaard):
    """Leest de Retry-After-header als die er is. Ontbreekt hij of staat er iets
    onverwachts in, dan de meegegeven standaard. Bovengrens van een minuut,
    zodat een rare waarde de ronde niet laat hangen."""
    waarde = resp.headers.get("Retry-After")
    try:
        return min(float(waarde), 60.0)
    except (TypeError, ValueError):
        return standaard


def _naamsleutel(naam):
    """Brengt een productnaam terug tot iets waarop je twee bronnen kunt
    vergelijken. Wordt op twee plekken gebruikt en moet daar hetzelfde zijn:
    bij het dedupliceren binnen een winkel, en als sleutel in de
    prijsgeschiedenis. Liepen die uiteen, dan zou hetzelfde product twee
    geschiedenissen krijgen.

    Streepjes gaan eruit en worden niet vervangen door een spatie: PrijsProfeet
    en Folderz schreven hetzelfde Lidl-product als "Bio kastanjechampignons" en
    "Bio kastanje-champignons", en die stonden allebei op de pagina, met dezelfde
    prijs. Weglaten maakt ze gelijk; een spatie zou dat juist niet doen."""
    kern = naam.strip().lower()
    kern = re.sub(r"[-‐-―]", "", kern)   # koppelteken en de streepjesfamilie
    return re.sub(r"\s+", " ", kern).strip()


def _history_key(store, naam):
    return f"{store}:{_naamsleutel(naam)}"


def _hersleutel(history):
    """Brengt bestaande geschiedenis onder de huidige sleutelvorm.

    Toen streepjes uit _naamsleutel gingen, veranderde de sleutel van elk
    product met een streepje in de naam. Zonder deze stap zouden die reeksen
    wees worden en zou de teller opnieuw bij nul beginnen — precies de data die
    dit bestand moet bewaren. Vallen twee oude sleutels op dezelfde nieuwe
    (bijvoorbeeld dezelfde champignons uit twee bronnen), dan worden de reeksen
    samengevoegd op datum.

    Draait elke keer mee en is daarna een no-op: nieuwe sleutels zijn al goed.
    """
    nieuw = {}
    verplaatst = 0
    for sleutel, records in history.items():
        store, _, naam = sleutel.partition(":")
        doel = f"{store}:{_naamsleutel(naam)}"
        if doel != sleutel:
            verplaatst += 1
        if doel in nieuw:
            samen = nieuw[doel] + records
            samen.sort(key=lambda r: r.get("datum") or "")
            # Opeenvolgende dubbele prijzen weer platslaan, zoals bij het
            # wegschrijven: de reeks bewaart prijswijzigingen, geen metingen.
            ontdubbeld = []
            for r in samen:
                vorige = ontdubbeld[-1] if ontdubbeld else None
                if (vorige and vorige.get("actieprijs") == r.get("actieprijs")
                        and vorige.get("normale_prijs") == r.get("normale_prijs")):
                    continue
                ontdubbeld.append(r)
            nieuw[doel] = ontdubbeld[-HISTORY_MAX_PER_PRODUCT:]
        else:
            nieuw[doel] = records
    if verplaatst:
        log.info(f"Geschiedenis: {verplaatst} sleutel(s) genormaliseerd naar de huidige vorm")
    return nieuw


def load_history():
    if HISTORY_PATH.exists():
        try:
            return _hersleutel(json.loads(HISTORY_PATH.read_text()))
        except (json.JSONDecodeError, OSError) as e:
            # Hier stond "begin opnieuw", en dat was het stilste soort dataverlies
            # dat dit project kende: de teller ging naar nul, de site zag er
            # normaal uit, en pas weken later zou opvallen dat er niets meer werd
            # vergeleken. Nu eerst de nieuwste back-up proberen.
            log.error(f"Geschiedenis onleesbaar ({e}) — probeer de back-up")
            hersteld = _herstel_history()
            if hersteld is not None:
                log.warning(
                    f"Geschiedenis hersteld uit de back-up: {len(hersteld)} producten. "
                    f"Het beschadigde bestand staat nog als {HISTORY_PATH}.beschadigd"
                )
                try:
                    os.replace(HISTORY_PATH, Path(str(HISTORY_PATH) + ".beschadigd"))
                except OSError:
                    pass
                return _hersleutel(hersteld)
            log.error("Geen bruikbare back-up gevonden; de geschiedenis begint opnieuw")
    return {}


def _herstel_history():
    """Zoekt de meest recente bruikbare back-up in de add-on-map. Geeft None als
    er niets te herstellen is."""
    if not ADDON_DATA_DIR.is_dir():
        return None
    map_ = ADDON_DATA_DIR / "geschiedenis-backup"
    if not map_.is_dir():
        return None
    # Nieuwste eerst: de vaste kopie, dan de gedateerde van nieuw naar oud.
    kandidaten = [map_ / "geschiedenis.json"] + sorted(
        map_.glob("geschiedenis-2*.json"), reverse=True
    )
    for pad in kandidaten:
        if not pad.exists():
            continue
        try:
            data = json.loads(pad.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and data:
            log.info(f"Back-up gebruikt: {pad.name}")
            return data
    return None


def save_history(history):
    """Schrijft de geschiedenis atomair weg: eerst naar een tijdelijk bestand in
    dezelfde map, dan één os.replace(). Dat was het niet — write_text() kapt het
    bestand eerst af en schrijft daarna, dus een stroomstoring of een gedode
    container midden in die schrijfactie liet een half of leeg bestand achter.
    En dat werd bij de volgende ronde stil vervangen door een lege geschiedenis:
    de teller begon opnieuw en niemand zag het. Bij 32 kB is dat één blok, dus in
    de praktijk zeldzaam, maar dit bestand is het enige onvervangbare hier."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tekst = json.dumps(history, indent=2, ensure_ascii=False)
    tijdelijk = HISTORY_PATH.with_suffix(".json.nieuw")
    tijdelijk.write_text(tekst, encoding="utf-8")
    os.replace(tijdelijk, HISTORY_PATH)
    _backup_history(tekst, len(history))


def _backup_history(tekst, aantal):
    """Legt een kopie van de geschiedenis in de eigen /data van de add-on, zodat
    hij meegaat in de nachtelijke Home Assistant-back-up. Zie de toelichting bij
    ADDON_DATA_DIR waarom dat nodig is en wat het niet oplost.

    Faalt bewust stil: dit is een vangnet, en een vangnet dat de ronde kan laten
    klappen is erger dan geen vangnet. Buiten de add-on (bij een lokale
    --dry-run) bestaat /data niet en gebeurt er niets.

    Een gedateerde kopie per dag, de laatste zeven bewaard. Bij 32 kB per stuk
    is dat een kwart megabyte, en het geeft een week om te merken dat er iets
    misging voordat de goede versie uit beeld is."""
    if not ADDON_DATA_DIR.is_dir():
        return
    try:
        map_ = ADDON_DATA_DIR / "geschiedenis-backup"
        map_.mkdir(exist_ok=True)

        # De vaste kopie mag nooit krimpen. De geschiedenis groeit alleen —
        # producten komen erbij, oude sleutels blijven staan — dus minder
        # producten dan de vorige keer betekent dat er iets stuk is. Zonder deze
        # grens zou precies de ronde ná een leeggelopen geschiedenis de goede
        # back-up overschrijven met de lege. De gedateerde kopie gaat wel door,
        # zodat het spoor van wat er misging bewaard blijft.
        vast = map_ / "geschiedenis.json"
        vorig = None
        if vast.exists():
            try:
                vorig = len(json.loads(vast.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                vorig = None
        if vorig is not None and aantal < vorig:
            log.warning(
                f"Geschiedenis kromp van {vorig} naar {aantal} producten; de vaste "
                f"back-up blijft staan. Controleer {vast}"
            )
        else:
            vast.write_text(tekst, encoding="utf-8")

        vandaag = datetime.now().date().isoformat()
        (map_ / f"geschiedenis-{vandaag}.json").write_text(tekst, encoding="utf-8")
        oud = sorted(map_.glob("geschiedenis-2*.json"))[:-HISTORY_BACKUPS]
        for pad in oud:
            pad.unlink()
        log.info(
            f"Geschiedenis geback-upt naar {map_} "
            f"({len(sorted(map_.glob('geschiedenis-2*.json')))} gedateerde kopieën)"
        )
    except Exception as e:
        log.warning(f"Back-up van de geschiedenis mislukt ({e}); de ronde gaat gewoon door")


def enrich_and_record_history(store, items, history, vandaag):
    """Zet per product de laagste ooit geziene prijs erbij (voordat we
    vandaag's prijs meetellen, anders vergelijk je met jezelf), en schrijft
    daarna vandaag's prijs bij in de geschiedenis. Zo kun je zien of een
    'aanbieding' eigenlijk duurder is dan wat je hem al eerder zag — de
    normale_prijs die de winkel toont is een claim, dit is de check.

    We schrijven alleen weg als de prijs is veranderd. Sinds de fetch dagelijks
    draait zou anders elke dag hetzelfde record erbij komen: de limiet van
    HISTORY_MAX_PER_PRODUCT zou dan nog maar een maand omvatten in plaats van
    jaren, en "eerder 7x gezien" zou betekenen "7 dagen dezelfde actie". Nu meet
    de geschiedenis prijs*wijzigingen* en is hij onafhankelijk van hoe vaak we
    fetchen. De bewaarde datum is dus de dag dat een prijs voor het eerst op dat
    niveau stond — precies wat je wil weten bij "eerder goedkoper gezien op X"."""
    for item in items:
        key = _history_key(store, item["naam"])
        eerdere = history.get(key, [])
        if eerdere:
            laagste = min(eerdere, key=lambda r: r["actieprijs"])
            item["laagste_ooit_prijs"] = laagste["actieprijs"]
            item["laagste_ooit_datum"] = laagste["datum"]
            item["eerder_gezien"] = len(eerdere)
        nieuw_record = {
            "datum": vandaag,
            "actieprijs": item["actieprijs"],
            "normale_prijs": item.get("normale_prijs"),
        }
        vorige = eerdere[-1] if eerdere else None
        onveranderd = (
            vorige is not None
            and vorige.get("actieprijs") == nieuw_record["actieprijs"]
            and vorige.get("normale_prijs") == nieuw_record["normale_prijs"]
        )
        if not onveranderd:
            history[key] = (eerdere + [nieuw_record])[-HISTORY_MAX_PER_PRODUCT:]
    return items


# ---------------------------------------------------------------------------
# Optioneel: publiceren naar GitHub Pages
# ---------------------------------------------------------------------------

_MAANDEN_NL = ("januari", "februari", "maart", "april", "mei", "juni", "juli",
               "augustus", "september", "oktober", "november", "december")
_DAGEN_NL = ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
             "zaterdag", "zondag")


def _leesbare_datum(iso):
    """"2026-09-03T20:42:11" wordt "woensdag 3 september 2026 om 20:42".

    In de statische lijst stond de ruwe ISO-tijd, en in de voettekst stond
    "nog niets geladen" tot de JavaScript klaar was. Een crawler las dus
    letterlijk dat er niets geladen was op de plek waar de versheid van de
    lijst hoort te staan. Locale-instellingen zijn hier geen optie: de Pi
    draait een kale Alpine-container zonder Nederlandse locale."""
    try:
        stip = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return (f"{_DAGEN_NL[stip.weekday()]} {stip.day} {_MAANDEN_NL[stip.month - 1]} "
            f"{stip.year} om {stip:%H:%M}")


def _jsonld(aanbiedingen, bijgewerkt):
    """De gestructureerde data voor de voorpagina.

    Bewust géén Product/Offer-markup, hoewel dat verleidelijk is: die zegt
    tegen een zoekmachine dat het product hier te koop is, en dat is het niet.
    Wij zijn niet de verkoper, er is niets af te rekenen, en Google's
    richtlijnen voor productdata gaan expliciet over pagina's waar je kunt
    kopen. Wat deze pagina wél is, is een lijst — CollectionPage met een
    ItemList — en de datum waarop die lijst is opgehaald. Dat is machineleesbaar
    en waar."""
    items = []
    for winkel, acties in aanbiedingen.items():
        for actie in acties:
            regel = f"{actie['naam']} — {_euro(actie['actieprijs'])} bij {winkel}"
            items.append({
                "@type": "ListItem",
                "position": len(items) + 1,
                "name": regel,
            })
    blok = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Het Bio Lijstje",
        "description": ("De lopende biologische groente- en fruitaanbiedingen van zes "
                        "Nederlandse supermarkten, elke ochtend opnieuw opgehaald."),
        "url": "https://hetbiolijstje.nl/",
        "inLanguage": "nl-NL",
        "dateModified": bijgewerkt,
        "isPartOf": {
            "@type": "WebSite",
            "name": "Het Bio Lijstje",
            "url": "https://hetbiolijstje.nl/",
        },
        "mainEntity": {
            "@type": "ItemList",
            "name": "Biologische groente- en fruitaanbiedingen",
            "numberOfItems": len(items),
            "itemListOrder": "https://schema.org/ItemListUnordered",
            "itemListElement": items,
        },
    }
    return ('<script type="application/ld+json">'
            + json.dumps(blok, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


def _html_escape(tekst):
    return (
        str(tekst)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def schrijf_index_html(aanbiedingen, bijgewerkt):
    """Zet de producten als platte HTML in index.html, gegenereerd uit
    template.html.

    Waarom dit nodig is: de pagina haalde de producten uitsluitend met
    JavaScript op, en een crawler zonder JavaScript zag daardoor letterlijk
    "Nog niets geladen" — nul productnamen in de broncode. Deze lijst is
    bewust simpel (geen kaarten, geen knoppen): de JavaScript vervangt het blok
    binnen een oogwenk door de interactieve versie. Het doel is alleen dat de
    inhoud in de HTML staat.

    Faalt dit, dan is dat niet fataal: we loggen het en laten de vorige
    index.html staan."""
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError as e:
        log.warning(f"template.html niet leesbaar ({e}); index.html ongewijzigd gelaten")
        return

    if PRODUCTEN_START not in template or PRODUCTEN_EINDE not in template:
        log.warning("Merktekens ontbreken in template.html; index.html ongewijzigd gelaten")
        return

    def vervang_blok(tekst, start, einde, inhoud, wat):
        """Vervangt alles tussen twee merktekens, of laat het met een
        waarschuwing staan als ze ontbreken. Ontbrekende merktekens mogen de
        productlijst niet tegenhouden — dat is de kern van de pagina."""
        if start not in tekst or einde not in tekst:
            log.warning(f"Merktekens voor {wat} ontbreken in template.html; overgeslagen")
            return tekst
        voor = tekst.index(start)
        na = tekst.index(einde) + len(einde)
        return tekst[:voor] + start + inhoud + einde + tekst[na:]

    regels = []
    for winkel, items in aanbiedingen.items():
        regels.append(f"      <section><h2>{_html_escape(winkel)}</h2>")
        if not items:
            regels.append(f"        <p>Geen bio-acties bij {_html_escape(winkel)} deze week.</p>")
        else:
            regels.append("        <ul>")
            for item in items:
                prijs = _euro(item['actieprijs'], entity=True)
                was = item.get("normale_prijs")
                was_txt = f" (was {_euro(was, entity=True)})" if isinstance(was, (int, float)) else ""
                soort = " &middot; voorraad" if item.get("soort") == "voorraad" else ""
                vw = item.get("voorwaarde")
                vw_txt = f" &middot; alleen bij: {_html_escape(vw.lower())}" if vw else ""
                regels.append(
                    f"          <li>{_html_escape(item['naam'])} — {prijs}{was_txt}{soort}{vw_txt}</li>"
                )
            regels.append("        </ul>")
        regels.append("      </section>")

    blok = (
        f"{PRODUCTEN_START}\n"
        f"    <!-- Automatisch gegenereerd; bewerk template.html, niet dit bestand. -->\n"
        f"    <div class=\"statische-lijst\">\n"
        f"      <p>Biologische groente- en fruitaanbiedingen, bijgewerkt op "
        f"{_html_escape(_leesbare_datum(bijgewerkt))}.</p>\n"
        + "\n".join(regels)
        + f"\n    </div>\n    {PRODUCTEN_EINDE}"
    )

    voor = template.index(PRODUCTEN_START)
    na = template.index(PRODUCTEN_EINDE) + len(PRODUCTEN_EINDE)
    nieuw = template[:voor] + blok + template[na:]

    # De voettekst zei "nog niets geladen" tot de JavaScript klaar was, en het
    # datetime-attribuut was leeg. Dat is precies het veld waaraan een crawler
    # of een AI ziet hoe vers deze lijst is.
    nieuw = vervang_blok(
        nieuw, DATUM_START, DATUM_EINDE,
        f'<time id="updated" datetime="{_html_escape(bijgewerkt)}">'
        f'{_html_escape(_leesbare_datum(bijgewerkt))}</time>',
        "de datum")

    nieuw = vervang_blok(nieuw, JSONLD_START, JSONLD_EINDE,
                         _jsonld(aanbiedingen, bijgewerkt), "de gestructureerde data")

    try:
        HTML_OUTPUT_PATH.write_text(nieuw, encoding="utf-8", newline="\n")
        log.info(f"index.html gegenereerd uit template.html ({len(regels)} regels productdata)")
    except OSError as e:
        log.warning(f"index.html schrijven mislukt ({e})")


def publish_to_github():
    """Pusht www/ naar een GitHub-repo via de Contents API, zodat de pagina
    ook publiek bereikbaar is via GitHub Pages (voor delen buiten het
    thuisnetwerk). Volledig optioneel: doet niets als GITHUB_TOKEN of
    GITHUB_REPO niet gezet zijn (via de add-on-opties, zie config.yaml —
    het token staat bewust niet in deze broncode)."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    if not token or not repo:
        return

    import base64
    import requests

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    gepubliceerd = 0
    for rel_path in GITHUB_PUBLISH_FILES:
        local_path = WWW_DIR / rel_path
        if not local_path.exists():
            continue
        content_b64 = base64.b64encode(local_path.read_bytes()).decode("ascii")
        url = f"https://api.github.com/repos/{repo}/contents/{rel_path}"
        try:
            get_resp = requests.get(url, headers=headers, timeout=15)
            sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

            payload = {
                "message": f"Update {rel_path} ({datetime.now().isoformat(timespec='minutes')})",
                "content": content_b64,
                "branch": "main",
            }
            if sha:
                payload["sha"] = sha

            put_resp = requests.put(url, headers=headers, json=payload, timeout=15)
            if put_resp.status_code in (200, 201):
                gepubliceerd += 1
            else:
                log.warning(f"GitHub-publish van {rel_path} mislukt: {put_resp.status_code} {put_resp.text[:200]}")
        except Exception as e:
            log.warning(f"GitHub-publish van {rel_path} mislukt: {e}")
    log.info(f"Gepubliceerd naar github.com/{repo}: {gepubliceerd}/{len(GITHUB_PUBLISH_FILES)} bestanden")


# ---------------------------------------------------------------------------
# Gedeeld
# ---------------------------------------------------------------------------

def _is_agf(title):
    """Is dit groente of fruit, op basis van de productnaam?

    Woordgrens-check (niet kale substring-check): "ui" als kaal substring
    matchte per ongeluk ook "inlegkruisjes" (kr-UI-sjes) — een echte
    false-positive uit live-testen.

    Daarna nog een tegencheck op _NIET_AGF_PATRONEN, voor namen die wél een
    AGF-trefwoord bevatten maar geen groente/fruit zijn (thee, vruchtensap).
    Deze functie wordt door beide bronnen gebruikt, dus de uitsluiting geldt
    ook voor Folderz — waar de naam trouwens de enige informatie is."""
    if not AGF_PATTERN.search(title):
        return False
    return not any(p.search(title) for p in _NIET_AGF_PATRONEN)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def controleer_kandidaten():
    """Kijkt of een van de ketens uit KANDIDAAT_WINKELS inmiddels biologische
    groente of fruit heeft. Verandert niets aan de site; het enige doel is dat
    zo'n verandering vanzelf opvalt in plaats van dat iemand er over een half
    jaar nog eens handmatig achteraan moet.

    Faalt bewust stil: dit is een terzijde, geen reden om de ronde te laten
    klappen."""
    for store_label, retailer_slug in KANDIDAAT_WINKELS.items():
        try:
            treffers, _ = fetch_aanbiedingen_prijsprofeet(store_label, retailer_slug)
        except Exception as e:
            log.info(f"Kandidaat {store_label}: niet te controleren ({e})")
            continue
        if treffers:
            log.warning(
                f"Kandidaat {store_label} heeft nu {len(treffers)} bio AGF-actie(s) — "
                f"overweeg de keten toe te voegen aan AANBIEDINGEN_STORES: "
                + ", ".join(t["naam"] for t in treffers[:5])
            )
        else:
            log.info(f"Kandidaat {store_label}: nog steeds geen bio AGF")


def _lees_argumenten():
    """--dry-run bestaat omdat dit script lange tijd nergens te draaien was
    behalve op de Pi zelf: er stond geen Python op de laptop, en dus kwam een
    verkeerde aanname over de JSON-envelope van de API pas aan het licht toen de
    site al bijna leeg live stond. Droogdraaien schrijft niets en publiceert
    niets — het haalt op, filtert, en laat zien wat er op de pagina zou komen."""
    import argparse

    p = argparse.ArgumentParser(
        description="Haalt biologische groente- en fruitaanbiedingen op en schrijft ze weg.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Niets wegschrijven, niets publiceren. Toont per winkel wat er op de site zou komen.",
    )
    p.add_argument(
        "--winkel", action="append", metavar="NAAM",
        help=("Alleen deze winkel ophalen; meerdere keren te gebruiken. Handig omdat "
              "een volledige ronde ruim drie minuten duurt. Keuze: "
              + ", ".join(AANBIEDINGEN_STORES)),
    )
    args = p.parse_args()
    if args.winkel:
        onbekend = [w for w in args.winkel if w not in AANBIEDINGEN_STORES]
        if onbekend:
            p.error(f"onbekende winkel(s): {', '.join(onbekend)}")
        # Zonder deze grens zou een echte ronde met --winkel de andere winkels
        # uit bio_prices.json gooien: het bestand wordt volledig overschreven.
        if not args.dry_run:
            p.error("--winkel kan alleen samen met --dry-run; anders wist de "
                    "gedeeltelijke ronde de andere winkels uit bio_prices.json")
    return args


def _toon_droogdraai(aanbiedingen):
    """Zelfde volgorde en indeling als de pagina, zodat je in de terminal ziet
    wat de bezoeker zou zien."""
    print()
    print("=" * 72)
    print("DROOGDRAAI — er is niets weggeschreven en niets gepubliceerd")
    print("=" * 72)
    totaal = 0
    for store_label, items in aanbiedingen.items():
        print(f"\n{store_label} — {len(items)} {'actie' if len(items) == 1 else 'acties'}")
        if not items:
            continue
        # Vers eerst, dan voorraad: dezelfde indeling als op de pagina.
        for soort in ("vers", "voorraad"):
            groep = [i for i in items if i.get("soort", "vers") == soort]
            if not groep:
                continue
            if soort == "voorraad":
                print("  -- voorraad (blik, pot, zak of vriezer) --")
            for item in groep:
                totaal += 1
                normaal = item.get("normale_prijs")
                van = f" (van {_euro(normaal)})" if normaal else ""
                korting = ""
                if normaal:
                    korting = f"  -{round((1 - item['actieprijs'] / normaal) * 100)}%"
                mits = f"  vanaf {item['vanaf']} stuks" if item.get("vanaf") else ""
                prijs = _euro(item['actieprijs'])
                print(f"  {prijs:>8}{van}{korting}{mits}  {item['naam']}")
    print(f"\nTotaal: {totaal} acties over {len(aanbiedingen)} winkels.")
    print("=" * 72)


def main():
    args = _lees_argumenten()
    if args.dry_run:
        log.info("Start bio-update (droogdraai: er wordt niets weggeschreven)...")
    else:
        log.info("Start bio-update...")

    vandaag = datetime.now().date().isoformat()
    history = load_history()

    winkels = {k: v for k, v in AANBIEDINGEN_STORES.items()
               if not args.winkel or k in args.winkel}

    aanbiedingen = {}
    winkelstatus = {}
    for store_label, (retailer_slug, folderz_slug) in winkels.items():
        items, status = fetch_aanbiedingen(store_label, retailer_slug, folderz_slug)
        aanbiedingen[store_label] = enrich_and_record_history(store_label, items, history, vandaag)
        winkelstatus[store_label] = status

    # Eén regel die zegt of deze ronde compleet was. Tot nu toe stond het
    # verschil tussen een lege winkel en een onbereikbare winkel verspreid over
    # losse waarschuwingen halverwege het log.
    kapot = {w: s for w, s in winkelstatus.items() if s != "ok"}
    if kapot:
        log.warning("Ronde niet compleet: "
                    + ", ".join(f"{w} {s}" for w, s in sorted(kapot.items())))
    else:
        log.info(f"Ronde compleet: alle {len(winkelstatus)} winkels opgehaald")

    if args.dry_run:
        # enrich_and_record_history heeft history in het geheugen bijgewerkt;
        # door hem niet op te slaan blijft de echte geschiedenis onaangeroerd.
        _toon_droogdraai(aanbiedingen)
        return

    # Na de echte winkels, want dit mag de lijst niet vertragen als het misgaat.
    controleer_kandidaten()

    save_history(history)

    if not any(aanbiedingen.values()):
        log.warning("Niets opgehaald bij geen enkele bron — bestaand JSON-bestand blijft staan")
        return

    resultaat = {
        "laatst_bijgewerkt": datetime.now().isoformat(),
        "aanbiedingen": aanbiedingen,
        # Per winkel "ok", "onvolledig" of "mislukt". De pagina leest dit om
        # niet "vandaag geen bio-acties bij Jumbo" te zeggen als Jumbo
        # onbereikbaar was.
        "winkelstatus": winkelstatus,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(resultaat, indent=2, ensure_ascii=False))
    log.info(f"Klaar. Geschreven naar {OUTPUT_PATH}")

    # Losstaand afgeschermd: de HTML is een extraatje bovenop de data, dus een
    # fout hierin mag het publiceren van bio_prices.json niet tegenhouden.
    try:
        schrijf_index_html(aanbiedingen, resultaat["laatst_bijgewerkt"])
    except Exception as e:
        log.warning(f"index.html genereren mislukt ({e}); vorige versie blijft staan")

    publish_to_github()


if __name__ == "__main__":
    main()
