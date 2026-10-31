#!/bin/sh
# Entrypoint de producción: levanta uvicorn con host/puerto/workers por
# env. Las migraciones a head las corre init_db() en el lifespan de la
# app — no hace falta paso previo. Detrás de un reverse proxy se
# confía en X-Forwarded-* solo desde FORWARDED_ALLOW_IPS (el rate-limit
# por IP y los logs lo usan).
set -eu

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-4000}" \
    --workers "${UVICORN_WORKERS:-1}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
