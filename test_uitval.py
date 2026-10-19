#!/usr/bin/env python3
"""Controleert dat uitval niet stilzwijgend op een lege winkel lijkt.

    python test_uitval.py

Drie dagen oude data zag er precies zo uit als verse, en "geen acties bij
Jumbo" was hetzelfde beeld als "Jumbo was onbereikbaar". Het verschil bestond
alleen in het log op de Pi.

Dit bestand toetst beide kanten: de engine geeft per winkel een status af, en
de pagina heeft voor elke status een eigen tekst. Dat laatste door de
gegenereerde HTML te lezen — een status die de engine wél afgeeft maar die de
pagina nergens gebruikt, is net zo stil als geen status.
"""

import importlib.util
import re
import sys
from pathlib import Path

HIER = Path(__file__).parent
spec = importlib.util.spec_from_file_location("bio", HIER / "fetch_bio_prices.py")
bio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bio)

fouten = 0


def keur(wat, ok, toelichting=""):
    global fouten
    if ok:
        print(f"  ok    {wat}")
    else:
        fouten += 1
        print(f"  FOUT  {wat}" + (f" — {toelichting}" if toelichting else ""))


# ---------------------------------------------------------------------------
# De engine: geeft fetch_aanbiedingen een status af?
# ---------------------------------------------------------------------------
class NepAntwoord:
    """Bootst één antwoord van de API na."""

    def __init__(self, status_code=200, producten=None):
        self.status_code = status_code
        self.headers = {}
        self._producten = producten if producten is not None else []

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"products": self._producten}


def draai(antwoorden):
    """Draait de fetch met een vaste reeks antwoorden en geeft (items, status)."""
    import requests

    echte_get, echte_sleep = requests.get, bio.time.sleep
    reeks = list(antwoorden)

    def nep_get(*a, **k):
        if not reeks:
            raise RuntimeError("netwerk weg")
        volgende = reeks.pop(0)
        if isinstance(volgende, Exception):
            raise volgende
        return volgende

    requests.get = nep_get
    bio.time.sleep = lambda *_: None
    try:
        return bio.fetch_aanbiedingen_prijsprofeet("Testwinkel", "test")
    finally:
        requests.get = echte_get
        bio.time.sleep = echte_sleep


print("engine")

items, status = draai([NepAntwoord(producten=[])])
keur('lege eerste pagina geeft status "ok"', status == "ok", f'kreeg "{status}"')
keur("lege eerste pagina geeft geen items", items == [])

items, status = draai([RuntimeError("dns weg")])
keur('fout op pagina 1 geeft status "mislukt"', status == "mislukt", f'kreeg "{status}"')

# Eerst een pagina met een geldig product, dan een fout: halve winkel.
goed = {
    "name": "Bio courgette", "price": 0.79, "original_price": 0.99,
    "dietary_tags": ["bio"], "unified_category": "groente-fruit",
    "promotion_status": "active", "retailer": "test",
}
items, status = draai([NepAntwoord(producten=[goed] * 100), RuntimeError("weg")])
keur('afbreken na pagina 1 geeft status "onvolledig"', status == "onvolledig",
     f'kreeg "{status}"')
keur("wat al gelukt was blijft staan", len(items) >= 1, f"kreeg {len(items)} items")

# Drie keer een 429 op dezelfde pagina: opgeven met wat we hebben.
items, status = draai([NepAntwoord(status_code=429)] * (bio.PRIJSPROFEET_MAX_429 + 1))
keur('drie keer een snelheidsgrens geeft status "onvolledig"', status == "onvolledig",
     f'kreeg "{status}"')

# De paginagrens was een stille afkapping: de lus liep af, de winkel gold als
# compleet, en niemand zag het. AH ging in twee dagen van 28 naar 51 pagina's,
# dus dit is geen theoretisch geval.
class VolleAntwoord(NepAntwoord):
    """Blijft eeuwig volle pagina's geven, zodat de grens wordt geraakt."""

    def json(self):
        return {"products": [{"name": "Iets", "price": 1.0, "dietary_tags": [],
                              "unified_category": "overig", "retailer": "test"}] * 100}


echte_grens = bio.PRIJSPROFEET_MAX_PAGES
bio.PRIJSPROFEET_MAX_PAGES = 3
try:
    items, status = draai([VolleAntwoord()] * 10)
finally:
    bio.PRIJSPROFEET_MAX_PAGES = echte_grens
keur('de paginagrens raken geeft status "onvolledig"', status == "onvolledig",
     f'kreeg "{status}"')

# Publiceren is onderdeel van de ronde. Op 15 oktober 2026 verliep het
# GitHub-token: de rondes bleven draaien, de sensor werd elke ochtend ververst,
# de dertig uur werden nooit gehaald en de site stond vier dagen stil zonder
# dat er een melding afging. Een ronde die nergens aankomt telt niet als klaar.
print("\npubliceren")


class NepAntwoord401:
    status_code = 401
    text = '{"message":"Bad credentials"}'
    headers = {}

    def json(self):
        return {}


import os as _os
import requests as _requests

_echt = (_requests.get, _requests.put)
_bewaard = {k: _os.environ.get(k) for k in ("GITHUB_TOKEN", "GITHUB_REPO")}
try:
    _os.environ.pop("GITHUB_TOKEN", None)
    _os.environ.pop("GITHUB_REPO", None)
    keur("zonder token is er niets te publiceren (0 van 0)",
         bio.publish_to_github() == (0, 0))

    _os.environ["GITHUB_TOKEN"] = "nep"
    _os.environ["GITHUB_REPO"] = "x/y"
    _requests.get = lambda *a, **k: NepAntwoord401()
    _requests.put = lambda *a, **k: NepAntwoord401()
    gelukt, totaal = bio.publish_to_github()
    keur("een verlopen token geeft nul geslaagde bestanden", gelukt == 0)
    keur("maar wel het aantal dat het had moeten zijn", totaal == 3, str(totaal))
    keur("gelukt is niet gelijk aan totaal, dus de sensor blijft staan",
         gelukt != totaal)
finally:
    _requests.get, _requests.put = _echt
    for k, v in _bewaard.items():
        if v is None:
            _os.environ.pop(k, None)
        else:
            _os.environ[k] = v

# GitHub geeft de vervaldatum van een fine-grained token mee in een header.
# Die stond er op 15 oktober ook, alleen keek niemand ernaar.
from datetime import datetime, timedelta, timezone


class NepHeaders:
    def __init__(self, vervalt=None):
        self.headers = {} if vervalt is None else {
            "github-authentication-token-expiration": vervalt}


def _waarschuwingen(vervalt):
    import logging as _l
    opgevangen = []

    class Vang(_l.Handler):
        def emit(self, record):
            opgevangen.append((record.levelname, record.getMessage()))

    h = Vang()
    bio.log.addHandler(h)
    oud_niveau = bio.log.level
    bio.log.setLevel(_l.INFO)
    try:
        bio._waarschuw_bij_verlopend_token(NepHeaders(vervalt))
    finally:
        bio.log.removeHandler(h)
        bio.log.setLevel(oud_niveau)
    return opgevangen


def _over(dagen):
    return (datetime.now(timezone.utc) + timedelta(days=dagen, hours=1)
            ).strftime("%Y-%m-%d %H:%M:%S UTC")


keur("een token van 30 dagen geeft geen waarschuwing",
     all(n != "WARNING" for n, _ in _waarschuwingen(_over(30))))
keur("binnen twee weken wel",
     any(n == "WARNING" for n, _ in _waarschuwingen(_over(9))))
keur("een verlopen token ook",
     any(n == "WARNING" and "verlopen" in m for n, m in _waarschuwingen(_over(-1))))
keur("een dag is enkelvoud",
     any("over 1 dag," in m for _, m in _waarschuwingen(_over(1))))
keur("zonder header gebeurt er niets", _waarschuwingen(None) == [])
keur("een onleesbare header laat de ronde met rust",
     all(n != "WARNING" for n, _ in _waarschuwingen("nergens")))

# Een waarschuwing in het log is geen waarschuwing: daar kijkt niemand uit
# zichzelf, en precies daarom stond de site vier dagen stil. De melding moet in
# het meldingenpaneel van Home Assistant komen.
def _meldingen(dagen_vooruit):
    import os as _o, requests as _r
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    verstuurd = []

    class Ok:
        status_code = 200

    echt_post, oud_token = _r.post, _o.environ.get("SUPERVISOR_TOKEN")
    _o.environ["SUPERVISOR_TOKEN"] = "nep"
    _r.post = lambda url, **k: (verstuurd.append((url, k.get("json") or {})), Ok())[1]
    try:
        kop = (_dt.now(_tz.utc) + _td(days=dagen_vooruit, hours=1)
               ).strftime("%Y-%m-%d %H:%M:%S UTC")
        bio._waarschuw_bij_verlopend_token(NepHeaders(kop))
    finally:
        _r.post = echt_post
        if oud_token is None:
            _o.environ.pop("SUPERVISOR_TOKEN", None)
        else:
            _o.environ["SUPERVISOR_TOKEN"] = oud_token
    return verstuurd


ruim = _meldingen(30)
keur("een ruim geldig token haalt de melding juist weg",
     len(ruim) == 1 and ruim[0][0].endswith("/dismiss"))
bijna = _meldingen(9)
keur("binnen twee weken komt er een melding",
     len(bijna) == 1 and bijna[0][0].endswith("/create"))
keur("met de datum erin", bijna and "28-10-2026" in str(bijna[0][1].get("message", ""))
     or bijna and "-2026" in str(bijna[0][1].get("message", "")))
keur("altijd hetzelfde nummer, dus bijwerken en niet stapelen",
     bijna[0][1].get("notification_id") == bio.TOKEN_MELDING_ID)
verlopen = _meldingen(-1)
keur("een verlopen token zegt dat de site stilstaat",
     "staat stil" in str(verlopen[0][1].get("message", "")))

motor = (HIER / "fetch_bio_prices.py").read_text(encoding="utf-8")
keur("de sensor wordt alleen gezet als alles gepubliceerd is",
     "if gepubliceerd == te_publiceren:" in motor)

# ---------------------------------------------------------------------------
# De pagina: heeft elke status een eigen tekst?
# ---------------------------------------------------------------------------
print("\npagina")
sjabloon = (HIER / "template.html").read_text(encoding="utf-8")

keur("leest data.winkelstatus", "data.winkelstatus" in sjabloon)
keur('valt terug op "ok" bij een oud bestand zonder dat veld',
     "data.winkelstatus || {}" in sjabloon)
keur('"mislukt" heeft een eigen tekst', "Niet opgehaald" in sjabloon)
keur('"onvolledig" heeft een eigen tekst', "niet volledig opgehaald" in sjabloon)
keur('"ok" met nul acties houdt de oude tekst',
     "Vandaag geen bio-acties bij" in sjabloon)
keur("alle winkels mislukt geeft geen 'geen acties'-tekst",
     "De lijst kon niet worden opgehaald" in sjabloon)
keur("een mislukte winkel toont ? in plaats van 0",
     sjabloon.count("=== 'mislukt' ? '?'") == 2,
     f"{sjabloon.count(chr(61) * 3 + chr(32) + chr(39) + 'mislukt' + chr(39) + ' ? ' + chr(39) + '?' + chr(39))} van 2 plekken")

drempel = re.search(r"const VEROUDERD_NA_UREN = (\d+);", sjabloon)
keur("er is een verouderingsdrempel", drempel is not None)
if drempel:
    uren = int(drempel.group(1))
    # De fetch draait dagelijks om 06:00. Onder de 24 uur slaat de melding aan
    # op een normale dag; ver boven de 48 uur mis je een hele dag uitval.
    keur(f"de drempel ({uren} uur) ligt tussen 24 en 48 uur", 24 < uren <= 48)
keur("de balk kondigt zich aan bij een schermlezer",
     'class="verouderd" role="status"' in sjabloon)
# De balk is een HTML-string en geen element, want content.innerHTML wordt op
# drie plekken overschreven en een ingevoegd element is dan weg. test_render.js
# controleert dat hij ook echt op de pagina belandt.
keur("de balk gaat mee in alle takken die innerHTML zetten",
     sjabloon.count("verouderdHtml") == 5,
     f"{sjabloon.count('verouderdHtml')} van 5 verwijzingen")

print()
if fouten:
    sys.exit(f"{fouten} controle(s) niet in orde")
print("uitval en veroudering worden allebei gemeld")
