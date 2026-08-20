FROM python:3.12-alpine

RUN pip install --no-cache-dir requests beautifulsoup4

WORKDIR /app
COPY fetch_bio_prices.py /app/fetch_bio_prices.py
COPY www /app/www

RUN echo '0 8 * * 0 . /etc/bio_bord_env.sh 2>/dev/null; cd /app && python3 fetch_bio_prices.py >> /proc/1/fd/1 2>&1' > /etc/crontabs/root

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
