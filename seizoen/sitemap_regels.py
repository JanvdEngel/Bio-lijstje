#!/usr/bin/env python3
"""Schrijft sitemap.xml opnieuw uit de seizoensdata.

    python seizoen/sitemap_regels.py

Handmatig bijhouden van dertien URL's naast een generator die ze produceert is
vragen om een sitemap die achterloopt. Dit leest dezelfde bron.
"""

import json
from datetime import date
from pathlib import Path

WORTEL = Path(__file__).parent.parent

# De dag waarop deze pagina's zijn gebouwd. Alleen voor de pagina's die niet
# elke dag veranderen: de seizoenskalender en /over/. De voorpagina en
# /cijfers/ krijgen bewust geen lastmod, want die worden door de Pi
# gepubliceerd en niet door dit script. Een datum van de laatste keer dat ik dit
# draaide zou bij die twee zeggen "er is niets veranderd" terwijl ze elke
# ochtend wel veranderen, en een verkeerd signaal is slechter dan geen signaal.
GEBOUWD = date.today().isoformat()
data = json.loads((WORTEL / "seizoen" / "seizoensdata.json").read_text(encoding="utf-8"))

regels = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    "  <url>",
    "    <loc>https://hetbiolijstje.nl/</loc>",
    "    <changefreq>daily</changefreq>",
    "    <priority>1.0</priority>",
    "  </url>",
    "  <url>",
    "    <loc>https://hetbiolijstje.nl/seizoen/</loc>",
    f"    <lastmod>{GEBOUWD}</lastmod>",
    "    <changefreq>monthly</changefreq>",
    "    <priority>0.8</priority>",
    "  </url>",
]
for m in data["maanden"]:
    regels += [
        "  <url>",
        f'    <loc>https://hetbiolijstje.nl/seizoen/{m["maand"]}/</loc>',
        f"    <lastmod>{GEBOUWD}</lastmod>",
        "    <changefreq>yearly</changefreq>",
        "    <priority>0.6</priority>",
        "  </url>",
    ]
regels += [
    "  <url>",
    "    <loc>https://hetbiolijstje.nl/cijfers/</loc>",
    "    <changefreq>daily</changefreq>",
    "    <priority>0.5</priority>",
    "  </url>",
    "  <url>",
    "    <loc>https://hetbiolijstje.nl/over/</loc>",
    f"    <lastmod>{GEBOUWD}</lastmod>",
    "    <changefreq>yearly</changefreq>",
    "    <priority>0.4</priority>",
    "  </url>",
]
regels.append("</urlset>")

pad = WORTEL / "sitemap.xml"
pad.write_text("\n".join(regels) + "\n", encoding="utf-8", newline="\n")
# Tellen wat er werkelijk in staat, niet met de hand optellen: dat liep twee
# keer achter toen er een pagina bij kwam.
aantal = sum(1 for r in regels if "<loc>" in r)
print(f"sitemap.xml geschreven: {aantal} URL's")
