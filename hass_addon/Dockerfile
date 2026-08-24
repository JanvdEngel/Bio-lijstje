FROM python:3.12-alpine

RUN pip install --no-cache-dir requests beautifulsoup4

WORKDIR /app
COPY fetch_bio_prices.py /app/fetch_bio_prices.py
COPY www /app/www

# Dagelijks 06:00. Was zondag 08:00, maar de actieweken van de ketens lopen
# niet gelijk: AH gaat maandag-zondag, Jumbo/Dirk/Plus woensdag-dinsdag, Lidl
# heeft twee batches per week en Aldi rommelt (do/vr/zo). Eén vaste dag per week
# liep daardoor structureel achter — op zondag ophalen betekende zelfs dat AH's
# week diezelfde dag afliep. 06:00 omdat PrijsProfeet zelf om 23:00 ververst en
# promotion_status live wordt berekend: na middernacht is de nieuwe week actief.
RUN echo '0 6 * * * . /etc/bio_bord_env.sh 2>/dev/null; cd /app && python3 fetch_bio_prices.py >> /proc/1/fd/1 2>&1' > /etc/crontabs/root

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
