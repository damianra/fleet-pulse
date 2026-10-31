"""Observabilidad FleetPulse — logging JSON estructurado + Prometheus.

Logging:
- `setup_logging()` configura el root logger. LOG_FORMAT=json emite una
  línea JSON por registro ({ts, level, logger, message, request_id, ...
  extras del LogRecord}); cualquier otro valor = formato texto clásico.
  LOG_LEVEL (default INFO) fija el nivel. Se llama al importar main.py,
  antes de que uvicorn cree sus propios handlers — así los logs de app
  Y los de acceso/error de uvicorn salen en el mismo formato.
- El middleware de main.py emite `fleetpulse.http` por request con
  method/path_template/status/ms/ip/request_id como campos, y el header
  `X-Request-ID` (generado o reenviado) para correlacionar.

Métricas (endpoint GET /metrics en main.py, formato Prometheus):
- http_requests_total{method,path,status} — counter por request. El
  label `path` usa el template de la ruta (`/api/vehicles/{id}`), no la
  URL cruda — cardinalidad acotada; requests sin match → 'other'.
- http_request_duration_seconds{method,path} — histograma.
- FleetPulseCollector (scrape-time, consulta la DB en cada collect):
  - fleetpulse_vehicles{status} — gauge
  - fleetpulse_alerts_active{severity} — gauge
  - fleetpulse_deliveries{status} — gauge
  Nota: los counters http_* son por proceso — en deploys multi-worker
  cada worker expone los suyos (convención estándar de prometheus_client).
"""
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_client.core import GaugeMetricFamily

log = logging.getLogger('fleetpulse.obs')


# ---------- Logging estructurado ----------

class JsonFormatter(logging.Formatter):
    """Una línea JSON por LogRecord. Los `extra` del call site se vuelcan
    como campos top-level (salvo los attrs estándar del record)."""

    _STANDARD = frozenset(
        vars(logging.makeLogRecord({})).keys()) | {'taskName'}

    def format(self, record):
        entry = {
            'ts': datetime.fromtimestamp(
                record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._STANDARD and not key.startswith('_'):
                entry[key] = value
        if record.exc_info:
            entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def setup_logging():
    """Configura el root logger una sola vez (guard contra re-import en
    tests). LOG_FORMAT=json → JSON lines; LOG_LEVEL → nivel. Los loggers
    propios de uvicorn (access/error) comparten el handler — uvicorn los
    configura antes de cargar la app, así que acá solo se les reemplaza
    el handler para que salgan en el mismo formato."""
    root = logging.getLogger()
    if getattr(root, '_fleetpulse_configured', False):
        return
    root._fleetpulse_configured = True
    handler = logging.StreamHandler(sys.stdout)
    if os.getenv('LOG_FORMAT', 'text').lower() == 'json':
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s %(message)s'))
    root.handlers[:] = [handler]
    root.setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers[:] = [handler]
        uv_logger.propagate = False


# ---------- Métricas Prometheus ----------

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    'http_requests_total', 'Requests HTTP procesados',
    ['method', 'path', 'status'], registry=REGISTRY)
HTTP_DURATION = Histogram(
    'http_request_duration_seconds', 'Latencia de requests HTTP',
    ['method', 'path'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=REGISTRY)


def observe_request(method, path_template, status, duration_s):
    """Registra un request en los instrumentos HTTP — lo llama el
    middleware de main.py una vez por request."""
    HTTP_REQUESTS.labels(method, path_template, str(status)).inc()
    HTTP_DURATION.labels(method, path_template).observe(duration_s)


def full_path_template(url_path, route_path):
    """Template completo del endpoint — `route.path` de una APIRoute
    incluída via include_router es RELATIVO al prefijo (p.ej.
    `/{vehicle_id}` montado en /api/vehicles). Se reconstruye matcheando
    los segmentos del template contra la URL real de atrás hacia
    adelante: cada segmento consume 1 de la URL, salvo el conversor
    `{x:path}` que consume todo lo que queda. Si no calza, devuelve el
    template tal cual (cardinalidad igual acotada)."""
    url_segs = [s for s in url_path.strip('/').split('/') if s]
    tpl_segs = [s for s in route_path.strip('/').split('/') if s]
    i, j = len(url_segs), len(tpl_segs)
    while j > 0:
        seg = tpl_segs[j - 1]
        j -= 1
        if seg.startswith('{') and seg.endswith(':path}'):
            i = j  # `{x:path}` consume hasta dejar i == j restantes
            continue
        i -= 1
        if i < j:
            return route_path
    prefix = '/'.join(url_segs[:i])
    return ('/' + prefix if prefix else '') + route_path


class FleetPulseCollector:
    """Collector scrape-time: en cada scrape consulta la DB y emite el
    estado actual de la flota — sin tasks ni sampling aparte."""

    def collect(self):
        from .db import SessionLocal
        from .models import Alert, Delivery, Vehicle, utcnow
        from sqlalchemy import func

        try:
            db = SessionLocal()
            try:
                vehicles = GaugeMetricFamily(
                    'fleetpulse_vehicles',
                    'Vehículos por estado actual', labels=['status'])
                for status, n in db.query(
                        Vehicle.status, func.count()).group_by(
                        Vehicle.status):
                    vehicles.add_metric([status], n)
                yield vehicles

                alerts = GaugeMetricFamily(
                    'fleetpulse_alerts_active',
                    'Alertas activas por severidad', labels=['severity'])
                for severity, n in db.query(
                        Alert.severity, func.count()).filter(
                        Alert.status == 'active').group_by(Alert.severity):
                    alerts.add_metric([severity], n)
                yield alerts

                deliveries = GaugeMetricFamily(
                    'fleetpulse_deliveries',
                    'Entregas por estado', labels=['status'])
                for status, n in db.query(
                        Delivery.status, func.count()).group_by(
                        Delivery.status):
                    deliveries.add_metric([status], n)
                yield deliveries

                hour_ago = utcnow() - timedelta(hours=1)
                completed_1h = db.query(func.count()).select_from(
                    Delivery).filter(
                    Delivery.status == 'delivered',
                    Delivery.actual_delivery_time >= hour_ago).scalar()
                metric = GaugeMetricFamily(
                    'fleetpulse_deliveries_completed_1h',
                    'Entregas completadas en la última hora')
                metric.add_metric([], completed_1h or 0)
                yield metric
            finally:
                db.close()
        except Exception as exc:  # DB caída → no romper el scrape
            log.warning('collector de métricas falló: %s', exc)


REGISTRY.register(FleetPulseCollector())


def metrics_response():
    """(body, content_type) del scrape — lo sirve GET /metrics."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
