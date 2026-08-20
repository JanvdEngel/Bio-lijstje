#!/bin/sh
set -e

mkdir -p /share/bio_bord/data
rm -rf /app/www/data
ln -sfn /share/bio_bord/data /app/www/data

python3 -c "
import json, shlex
opts = {}
try:
    with open('/data/options.json') as f:
        opts = json.load(f)
except FileNotFoundError:
    pass
with open('/etc/bio_bord_env.sh', 'w') as out:
    out.write('export GITHUB_TOKEN=' + shlex.quote(opts.get('github_token') or '') + '\n')
    out.write('export GITHUB_REPO=' + shlex.quote(opts.get('github_repo') or '') + '\n')
"
. /etc/bio_bord_env.sh

echo "[bio_bord] Start crond (wekelijkse fetch: zondag 08:00)..."
crond -b -l 2

echo "[bio_bord] Webserver starten op poort 8099 (met laatst bekende data)..."
cd /app
python3 -m http.server 8099 --directory /app/www &
HTTP_PID=$!

echo "[bio_bord] Fetch starten op de achtergrond zodat de pagina meteen bereikbaar is..."
python3 fetch_bio_prices.py || echo "[bio_bord] Fetch mislukt, bestaande data blijft staan"

wait "$HTTP_PID"
