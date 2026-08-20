#!/usr/bin/env python3
"""
Bio Groente & Fruit — AH / Jumbo / Lidl
=========================================================
Standalone script (GEEN Home Assistant nodig). Draait via cron, 1x per week,
en schrijft een JSON-bestand dat de telefoon-app (www/index.html) uitleest.

Eén feature (zie README voor de achtergrond van deze opzet): "aanbiedingen"
— lopende bio AGF-acties per winkel (AH/Jumbo/Lidl), via twee gecombineerde
bronnen: de publieke PrijsProfeet-API (schoon, snel, maar met merkbaar
dunnere Lidl-dekking) en Folderz.nl (scraping, trager, maar met een
volledige doorzoeking van alle lopende acties per winkel). Resultaten
worden samengevoegd en op naam gedupliceerd. Geen cross-store matching —
acties zijn te schaars om een zinnig prijsverschil-overzicht op te bouwen
(soms enkele bio-items per winkel per week).

Gebruik:
    python3 fetch_bio_prices.py

Installatie & cron: zie README.md.
"""

import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bio_prices")

# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------

AGF_KEYWORDS = [
    "appel", "banaan", "tomaat", "tomaten", "komkommer", "paprika", "ui", "uien",
    "aardappel", "wortel", "sla", "spinazie", "avocado", "citroen", "courgette",
    "champignon", "oesterzwam", "shiitake", "portobello", "kastanjechampignon",
    "druif", "druiven", "sinaasappel", "peer", "peren", "broccoli",
    "bloemkool", "prei", "aardbei", "framboos", "blauwe bes", "bosbes", "kiwi",
    "mandarijn", "radijs", "witlof", "boon", "bonen", "knoflook", "venkel",
    "asperge", "mango", "meloen", "sperzieboon", "rucola", "andijvie",
    "koolraap", "pompoen", "biet", "selderij", "gember", "limoen", "kool",
    "mais", "maïs",  # ontbraken; kwamen live langs als "BIO+ Mais zoet" en "Maïskolven"
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
    "koffie-thee",
    "drogisterij",
    "bier-wijn-sterke-drank",
    # Vlees, vis en kaas/vleeswaren horen per definitie niet in een
    # groente&fruit-lijst; hier kwamen bij het testen o.a. biologische
    # hamburgers, olijven en tomatentapenade uit.
    "vlees",
    "vis",
    "kaas",
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
_AGF_WHOLE_WORD_ONLY = {"ui", "uien", "kool", "sla"}
_agf_prefix = [k for k in AGF_KEYWORDS if k not in _AGF_WHOLE_WORD_ONLY]
_agf_whole = [k for k in AGF_KEYWORDS if k in _AGF_WHOLE_WORD_ONLY]
AGF_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _agf_prefix) + r")"
    r"|\b(" + "|".join(re.escape(k) for k in _agf_whole) + r")\b",
    re.IGNORECASE,
)

# Feature 1: bio-aanbiedingen per winkel, via twee gecombineerde bronnen (zie README)
# store_label -> (prijsprofeet_retailer_slug, folderz_winkel_slug of None,
#                  PrijsProfeet-zoektermen)
# Folderz staat alleen nog aan voor Lidl: bij AH/Jumbo leverde de volledige
# paginering (~99 resp. ~36 pagina's) vrijwel nooit iets op dat PrijsProfeet
# niet al had — enkel tijd kosten (2-4 min) zonder toegevoegde waarde. Bij
# Lidl vult Folderz een structurele blinde vlek van PrijsProfeet (zie README).
# Hertest augustus 2026 bevestigt dit nog steeds: 2040 AH-producten over 60
# pagina's leverden 7 bio-treffers op, allemaal wijn/thee/crackers.
#
# "biologisch" staat als aparte zoekterm naast "bio", want de fuzzy search van
# PrijsProfeet geeft op "bio" de "Biologisch"-huismerken níet terug — daardoor
# bleef bv. een halve-prijs-actie op AH Biologisch Blauwe bessen onzichtbaar.
#
# Ekoplaza is eruit gehaald: hun items bleken geen echte acties (actieprijs
# gelijk aan normale prijs, met een valid_from uit 2024) — die hoorden dus niet
# in een aanbiedingenlijst thuis.
AANBIEDINGEN_STORES = {
    "AH": ("albert_heijn", None, ["bio", "biologisch"]),
    "Jumbo": ("jumbo", None, ["bio", "biologisch"]),
    "Lidl": ("lidl", "lidl", ["bio", "biologisch"]),
    "Aldi": ("aldi", None, ["bio", "biologisch"]),
    "Dirk": ("dirk", None, ["bio", "biologisch"]),
    "Plus": ("plus", None, ["bio", "biologisch"]),
}
PRIJSPROFEET_SEARCH_URL = "https://www.prijsprofeet.nl/api/v1/search"
FOLDERZ_MAX_PAGES = 120  # veiligheidsgrens; Lidl had er ~34-36 tijdens het bouwen
MAX_ITEMS_PER_STORE = 15  # cap na dedup, grootste korting eerst — houdt winkels in verhouding

OUTPUT_PATH = Path(__file__).parent / "www" / "data" / "bio_prices.json"
HISTORY_PATH = Path(__file__).parent / "www" / "data" / "geschiedenis.json"
HISTORY_MAX_PER_PRODUCT = 30  # ~7 maanden bij 1x per week
WWW_DIR = Path(__file__).parent / "www"
GITHUB_PUBLISH_FILES = ["index.html", "manifest.json", "icon.png", "sw.js", "data/bio_prices.json"]


# ---------------------------------------------------------------------------
# Feature 1: bio-aanbiedingen per winkel (PrijsProfeet-API + Folderz.nl)
# ---------------------------------------------------------------------------

def fetch_aanbiedingen(store_label, retailer_slug, folderz_slug, search_terms):
    """Combineert twee bronnen voor de bio-aanbiedingen van één winkel:
    - PrijsProfeet-API: schoon, snel, gratis, sleutelloos JSON.
    - Folderz.nl: trager (scraping, pagineert door alle lopende acties),
      maar vult structurele gaten van PrijsProfeet op. Alleen ingeschakeld
      voor winkels waar dat nodig bleek (folderz_slug niet None) — zie
      AANBIEDINGEN_STORES hierboven.
    Resultaten van beide worden samengevoegd en op (genormaliseerde) naam
    gededupliceerd, zodat een product dat in beide bronnen voorkomt maar
    één keer getoond wordt."""
    resultaten = fetch_aanbiedingen_prijsprofeet(store_label, retailer_slug, search_terms)
    if folderz_slug:
        resultaten += fetch_aanbiedingen_folderz(store_label, folderz_slug)

    gezien = set()
    gededupliceerd = []
    for item in resultaten:
        sleutel = re.sub(r"\s+", " ", item["naam"].strip().lower())
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        gededupliceerd.append(item)

    # Cap per winkel, grootste korting eerst — anders kan een winkel met veel
    # treffers (Plus gaf er 19 op "bio") de pagina domineren t.o.v. de andere
    # winkels.
    def _korting(item):
        if item.get("normale_prijs"):
            return item["normale_prijs"] - item["actieprijs"]
        return 0
    gededupliceerd.sort(key=_korting, reverse=True)
    gededupliceerd = gededupliceerd[:MAX_ITEMS_PER_STORE]

    log.info(f"{store_label} aanbiedingen totaal: {len(gededupliceerd)} bio AGF-acties (na dedupliceren)")
    return gededupliceerd


def fetch_aanbiedingen_prijsprofeet(store_label, retailer_slug, search_terms):
    """Haalt lopende bio AGF-aanbiedingen van één winkel op via de publieke
    PrijsProfeet-API (prijsprofeet.nl/api) — een gratis, sleutelloos JSON-
    endpoint dat 10 NL-supermarkten uniform ontsluit, met producten al
    getagd op dietary_tags (o.a. "bio"). Let op: PrijsProfeet is zelf ook
    een acties-database (elk resultaat bleek live "is_promotional": true)
    — er is geen doorlopende (niet-actie) prijscatalogus voor Jumbo/Lidl
    beschikbaar, zie README. Bronvermelding conform de gebruiksvoorwaarden
    van de gratis publieke endpoints staat in index.html.

    search_terms: meerdere zoektermen worden na elkaar bevraagd en
    samengevoegd (dedup gebeurt later in fetch_aanbiedingen) — nodig omdat de
    fuzzy search op "bio" de "Biologisch"-huismerken niet meeneemt.

    Een item moet vier checks halen:
    1. AGF-trefwoord in de naam;
    2. categorie niet in EXCLUDED_CATEGORIES (weert koffie/wijn/babyvoeding
       die toevallig een AGF-woord in de naam hebben);
    3. bio volgens het dietary_tags-label van PrijsProfeet, óf anders volgens
       de naam — het label is betrouwbaarder dan de naam, maar niet elk
       bio-product blijkt getagd, dus de naam blijft een terugvaloptie;
    4. promotion_status niet 'upcoming' of 'historical' — de API levert
       namelijk ook nog-niet-geldige en verlopen acties (Aldi's bio-items
       stonden bij het testen allebei op 'upcoming'). Ontbreekt het veld
       helemaal, dan laten we het item door: dat is het oude gedrag, en
       liever dat dan een lege site als de API van vorm verandert."""
    import requests

    headers = {"User-Agent": "BioBordPi/1.0 (Home Assistant add-on, persoonlijk gebruik)"}
    resultaten = []
    for term in search_terms:
        try:
            resp = requests.get(
                PRIJSPROFEET_SEARCH_URL,
                headers=headers,
                timeout=15,
                params={"q": term, "retailer": retailer_slug, "page_size": 100},
            )
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("results", []):
                title = item.get("name") or ""
                if not title or not _is_agf(title):
                    continue
                if item.get("unified_category") in EXCLUDED_CATEGORIES:
                    continue
                tags = item.get("dietary_tags") or []
                if "bio" not in tags and not BIO_PATTERN.search(title):
                    continue
                status = item.get("promotion_status")
                if status is not None and status != "active":
                    continue
                actieprijs = item.get("price")
                if not isinstance(actieprijs, (int, float)):
                    continue
                resultaten.append({
                    "naam": title,
                    "actieprijs": float(actieprijs),
                    "normale_prijs": item.get("original_price"),
                })
        except Exception as e:
            log.warning(f"Aanbiedingen ophalen mislukt voor {store_label} (PrijsProfeet, q={term}): {e}")
    log.info(f"{store_label} aanbiedingen: {len(resultaten)} bio AGF-acties (PrijsProfeet)")
    return resultaten


def fetch_aanbiedingen_folderz(store_label, folderz_slug):
    """Vult PrijsProfeet aan met een volledige doorzoeking van Folderz.nl,
    een reclamefolder-aggregator. Live geverifieerd: gewone requests werken
    hier prima op de daadwerkelijke aanbiedingen-pagina's (geen headless
    browser nodig) — een AWS-botcheck bleek alleen op /robots.txt te zitten,
    niet op de content zelf. We pagineren tot een lege of 404-pagina."""
    import time
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
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

def _history_key(store, naam):
    kern = re.sub(r"\s+", " ", naam.strip().lower())
    return f"{store}:{kern}"


def load_history():
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"Geschiedenis-bestand onleesbaar ({e}), begin opnieuw")
    return {}


def save_history(history):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def enrich_and_record_history(store, items, history, vandaag):
    """Zet per product de laagste ooit geziene prijs erbij (voordat we
    vandaag's prijs meetellen, anders vergelijk je met jezelf), en schrijft
    daarna vandaag's prijs bij in de geschiedenis. Zo kun je zien of een
    'aanbieding' eigenlijk duurder is dan wat je hem al eerder zag — de
    normale_prijs die de winkel toont is een claim, dit is de check."""
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
        history[key] = (eerdere + [nieuw_record])[-HISTORY_MAX_PER_PRODUCT:]
    return items


# ---------------------------------------------------------------------------
# Optioneel: publiceren naar GitHub Pages
# ---------------------------------------------------------------------------

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
    """Woordgrens-check (niet kale substring-check): "ui" als kaal substring
    matchte per ongeluk ook "inlegkruisjes" (kr-UI-sjes) — een echte
    false-positive uit live-testen."""
    return bool(AGF_PATTERN.search(title))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("Start wekelijkse bio-update...")

    vandaag = datetime.now().date().isoformat()
    history = load_history()

    aanbiedingen = {}
    for store_label, (retailer_slug, folderz_slug, search_terms) in AANBIEDINGEN_STORES.items():
        items = fetch_aanbiedingen(store_label, retailer_slug, folderz_slug, search_terms)
        aanbiedingen[store_label] = enrich_and_record_history(store_label, items, history, vandaag)

    save_history(history)

    if not any(aanbiedingen.values()):
        log.warning("Niets opgehaald bij geen enkele bron — bestaand JSON-bestand blijft staan")
        return

    resultaat = {
        "laatst_bijgewerkt": datetime.now().isoformat(),
        "aanbiedingen": aanbiedingen,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(resultaat, indent=2, ensure_ascii=False))
    log.info(f"Klaar. Geschreven naar {OUTPUT_PATH}")

    publish_to_github()


if __name__ == "__main__":
    main()
