"""App FastAPI base — espejo de `server/app.js` del api-skeleton
Express. Convención de auto-mount: cada `app/routers/<name>.py` que
exporte `router` (APIRouter) se monta en `/api/<name>` — agregar un
endpoint es agregar un archivo, no hay nada que registrar."""
import asyncio
import importlib
import logging
import os
import pkgutil
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from .observability import (full_path_template, metrics_response,
                            observe_request, setup_logging)

load_dotenv()
setup_logging()
http_log = logging.getLogger('fleetpulse.http')

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Rate limit in-memory por IP solo en métodos de escritura (espejo de
# server/security.js — 20 req/min; los 429 también quedan logueados).
RATE_WINDOW_S = 60
RATE_MAX = int(os.getenv('RATE_LIMIT_MAX', '20'))
_rate = {}


@asynccontextmanager
async def lifespan(_app):
    from . import bus
    from .alerts_engine import alerts_loop
    from .archive import archive_loop
    from .db import init_db, SessionLocal
    from .metrics import metrics_loop
    from .ws import manager

    init_db()
    # Bus Redis (app/bus.py): con REDIS_URL, los broadcasts WS viajan
    # por pub/sub — el listener de este worker reenvía a sus sockets
    # los mensajes de todos los workers. Sin REDIS_URL es no-op y el
    # broadcast queda local (single-process).
    await bus.start(manager.broadcast)

    # Motor de reglas de alertas (SLA, mantenimiento, fatiga) — corre en
    # el loop de la app, cada ALERTS_INTERVAL_S (default 60). El loop de
    # archivado mueve tracking_events viejos a su tabla archive cada
    # TRACKING_ARCHIVE_INTERVAL_S (default 1 h), y el de métricas
    # upsertea el snapshot diario (hoy + ayer) cada METRICS_INTERVAL_S
    # (default 1 h) en daily_metrics. leader_supervisor los corre solo
    # en el worker que tiene el lease Redis (con REDIS_URL, todas las
    # réplicas pueden llevar RUN_BACKGROUND_LOOPS=true — el lease elige
    # una); sin Redis este worker es líder permanente.
    # RUN_BACKGROUND_LOOPS=false apaga los 3 loops del proceso.
    def start_loops():
        return [asyncio.create_task(alerts_loop(SessionLocal)),
                asyncio.create_task(archive_loop(SessionLocal)),
                asyncio.create_task(metrics_loop(SessionLocal))]
    tasks = []
    if os.getenv('RUN_BACKGROUND_LOOPS', 'true').lower() != 'false':
        tasks = [asyncio.create_task(bus.leader_supervisor(start_loops))]
    yield
    for task in tasks:
        task.cancel()
    await bus.stop()


app = FastAPI(title=os.getenv('APP_NAME', 'app'), lifespan=lifespan)

# Cookies httpOnly (auth) exigen origins explícitos + credentials —
# allow_origins=['*'] es incompatible con credentials en browsers.
FRONTEND_ORIGINS = [o.strip() for o in os.getenv(
    'FRONTEND_ORIGINS',
    'http://localhost:5173,http://localhost:4173,http://localhost:3000').split(',')]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.middleware('http')
async def log_rate_secure(request, call_next):
    ip = request.client.host if request.client else '?'
    # Correlación: respeta X-Request-ID entrante o genera uno — queda en
    # el log estructurado y vuelve al cliente como response header.
    request_id = request.headers.get('x-request-id') or secrets.token_hex(8)
    t0 = time.monotonic()
    res = None
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.url.path.startswith('/api'):
        # CSRF double-submit: requests autenticados por cookie `auth`
        # deben reenviar la cookie `csrf` en el header x-csrf-token.
        # Los clientes Bearer (app móvil) quedan exentos.
        if 'auth' in request.cookies:
            if request.headers.get('x-csrf-token') != request.cookies.get('csrf'):
                res = JSONResponse({'error': 'csrf token inválido'}, status_code=403)
        if res is None:
            now = time.monotonic()
            hits = [t for t in _rate.get(ip, []) if now - t < RATE_WINDOW_S]
            if len(hits) >= RATE_MAX:
                res = JSONResponse({'error': 'rate limited'}, status_code=429)
            else:
                hits.append(now)
                _rate[ip] = hits
    if res is None:
        res = await call_next(request)
    res.headers.setdefault('X-Content-Type-Options', 'nosniff')
    res.headers.setdefault('X-Frame-Options', 'DENY')
    res.headers.setdefault('Referrer-Policy', 'no-referrer')
    res.headers.setdefault('X-Request-ID', request_id)
    duration = time.monotonic() - t0
    # Prometheus: el label path usa el template de la ruta — scope.route
    # da el path relativo del router incluído, se reconstruye el completo
    # (/api/vehicles/{id}) — cardinalidad acotada; sin match → 'other'.
    route = request.scope.get('route')
    path_template = full_path_template(
        request.url.path, route.path) if route else 'other'
    observe_request(request.method, path_template, res.status_code, duration)
    http_log.info(
        '%s %s %s', request.method, request.url.path, res.status_code,
        extra={'method': request.method, 'url': request.url.path,
               'path': path_template, 'status': res.status_code,
               'ms': round(duration * 1000), 'ip': ip,
               'request_id': request_id})
    return res


@app.get('/api/health')
def health():
    return {'ok': True}


@app.get('/metrics', include_in_schema=False)
def prometheus_metrics():
    # Scrape de Prometheus — sin auth (convención: se protege a nivel
    # de red en el deploy, como el puerto de métricas de cualquier
    # servicio). Registrado antes del catch-all SPA para que gane.
    body, content_type = metrics_response()
    return Response(body, media_type=content_type)


# Auto-mount de routers: app/routers/<name>.py con `router` → /api/<name>
ROUTERS_DIR = HERE / 'routers'
for mod in pkgutil.iter_modules([str(ROUTERS_DIR)]):
    if mod.name.startswith('_'):
        continue
    module = importlib.import_module(f'app.routers.{mod.name}')
    router = getattr(module, 'router', None)
    if router is not None:
        app.include_router(router, prefix=f'/api/{mod.name}')


@app.api_route('/api/{_path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], include_in_schema=False)
def api_not_found(_path: str):
    raise HTTPException(404, 'not found')


# Frontend build estático (fullstack): dist/ (Vite) u out/ (Next
# export) en la raíz del proyecto — el primero que exista, con SPA
# fallback para GETs que no son /api (mismo contrato que Express).
STATIC_DIR = next(
    (ROOT / name for name in ('dist', 'out') if (ROOT / name / 'index.html').exists()),
    None,
)


@app.get('/{_path:path}', include_in_schema=False)
def spa(_path: str):
    if STATIC_DIR and _path:
        candidate = (STATIC_DIR / _path).resolve()
        if candidate.is_file() and candidate.is_relative_to(STATIC_DIR.resolve()):
            return FileResponse(candidate)
    if STATIC_DIR and (STATIC_DIR / 'index.html').exists():
        return FileResponse(STATIC_DIR / 'index.html')
    raise HTTPException(404, 'not found')
