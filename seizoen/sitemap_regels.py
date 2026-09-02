#!/usr/bin/env python3
"""Schrijft sitemap.xml opnieuw uit de seizoensdata.

    python seizoen/sitemap_regels.py

Handmatig bijhouden van dertien URL's naast een generator die ze produceert is
vragen om een sitemap die achterloopt. Dit leest dezelfde bron.
"""

import json
from pathlib import Path

WORTEL = Path(__file__).parent.parent
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
    "    <changefreq>monthly</changefreq>",
    "    <priority>0.8</priority>",
    "  </url>",
]
for m in data["maanden"]:
    regels += [
        "  <url>",
        f'    <loc>https://hetbiolijstje.nl/seizoen/{m["maand"]}/</loc>',
        "    <changefreq>yearly</changefreq>",
        "    <priority>0.6</priority>",
        "  </url>",
    ]
regels += [
    "  <url>",
    "    <loc>https://hetbiolijstje.nl/over/</loc>",
    "    <changefreq>yearly</changefreq>",
    "    <priority>0.4</priority>",
    "  </url>",
]
regels.append("</urlset>")

pad = WORTEL / "sitemap.xml"
pad.write_text("\n".join(regels) + "\n", encoding="utf-8", newline="\n")
print(f"sitemap.xml geschreven: {len(data['maanden']) + 3} URL's")
