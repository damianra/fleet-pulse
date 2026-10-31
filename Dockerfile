# FleetPulse API — imagen de producción (FastAPI + uvicorn + postgres).
# Build:  docker build -t fleetpulse-api .
# Run:    docker run -p 4000:4000 --env-file .env \
#           -e DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/fleetpulse \
#           fleetpulse-api
# Al boot: init_db() migra a head (alembic) y siembra demo si SEED_DEMO!=false.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=4000 \
    UVICORN_WORKERS=1

WORKDIR /srv/app

# Deps primero para aprovechar la cache de capas. psycopg2-binary ya
# viene activo en requirements para DATABASE_URL=postgresql+psycopg2://.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Usuario no-root.
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && useradd --system --uid 10001 --home-dir /srv/app appuser \
    && chown -R appuser:appuser /srv/app
USER appuser

EXPOSE 4000

# Healthcheck sin curl/wget (la imagen slim no los trae).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','4000')+'/api/health',timeout=4)"

ENTRYPOINT ["docker-entrypoint.sh"]
