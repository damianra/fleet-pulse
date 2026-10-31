"""Métricas diarias persistidas — corre como tarea asyncio en el
lifespan (cada METRICS_INTERVAL_S, default 1 h, en thread para no
bloquear el loop) y también por POST /api/analytics/snapshot.

Cada corrida upsertea una fila en daily_metrics por día: la de HOY
(parcial — se refresca en cada pasada, así el dashboard muestra el
día en curso) y la de AYER (re-cómputo final, captura eventos que
llegaron tarde). Los días anteriores quedan congelados.

`data` agrupa por sección (mismas claves que los endpoints de
analytics): deliveries, routes, alerts, tracking, drivers y
maintenance — suficiente para series históricas sin recomputar la
tabla caliente."""
import asyncio
import os
from datetime import datetime, timedelta

from sqlalchemy import func

from .models import (Alert, DailyMetric, Delivery, DriverShift,
                     MaintenanceRecord, Route, TrackingEvent, utcnow)

INTERVAL_S = int(os.getenv('METRICS_INTERVAL_S', '3600'))


def _bounds(day):
    """Rango [start, end) naive-UTC del día — portable sqlite/postgres."""
    start = datetime(day.year, day.month, day.day)
    return start, start + timedelta(days=1)


def _by(rows, attr):
    out = {}
    for r in rows:
        key = getattr(r, attr)
        out[key] = out.get(key, 0) + 1
    return out


def compute_daily_metrics(db, day):
    """Agrega las métricas del día `day` (date). Devuelve el dict que
    se persiste en daily_metrics.data."""
    start, end = _bounds(day)

    deliveries = db.query(Delivery).all()
    created = [d for d in deliveries
               if d.created_at and start <= d.created_at < end]
    delivered = [d for d in deliveries
                 if d.actual_delivery_time
                 and start <= d.actual_delivery_time < end]
    on_time = [d for d in delivered
               if d.delivery_window_end
               and d.actual_delivery_time <= d.delivery_window_end]
    durations = [(d.actual_delivery_time - d.created_at).total_seconds() / 60
                 for d in delivered if d.created_at]

    routes = db.query(Route).all()
    started = [r for r in routes
               if r.actual_start and start <= r.actual_start < end]
    completed = [r for r in routes
                 if r.actual_end and start <= r.actual_end < end]
    durations_r = [(r.actual_end - r.actual_start).total_seconds() / 60
                   for r in completed if r.actual_start]

    alerts = [a for a in db.query(Alert).all()
              if a.triggered_at and start <= a.triggered_at < end]

    events = db.query(TrackingEvent).filter(
        TrackingEvent.timestamp >= start,
        TrackingEvent.timestamp < end).all()
    speeds = [e.speed_kmh for e in events if e.speed_kmh is not None]

    shifts = [s for s in db.query(DriverShift).all()
              if s.start_time and start <= s.start_time < end]
    hours = [s.total_hours for s in shifts if s.total_hours is not None]

    maint = [m for m in db.query(MaintenanceRecord).all()
             if m.completed_date == day]

    return {
        'deliveries': {
            'created': len(created), 'delivered': len(delivered),
            'on_time': len(on_time),
            'on_time_rate': round(len(on_time) / len(delivered), 3)
            if delivered else None,
            'avg_delivery_time_minutes':
                round(sum(durations) / len(durations), 1)
                if durations else None},
        'routes': {
            'started': len(started), 'completed': len(completed),
            'distance_km': round(
                sum(r.total_distance_km or 0 for r in completed), 2),
            'avg_duration_minutes':
                round(sum(durations_r) / len(durations_r), 1)
                if durations_r else None},
        'alerts': {
            'triggered': len(alerts), 'by_type': _by(alerts, 'type'),
            'by_severity': _by(alerts, 'severity')},
        'tracking': {
            'events': len(events),
            'vehicles_seen': len({e.vehicle_id for e in events}),
            'avg_speed_kmh': round(sum(speeds) / len(speeds), 1)
            if speeds else None},
        'drivers': {
            'shifts': len(shifts),
            'hours_worked': round(sum(hours), 2) if hours else 0},
        'maintenance': {
            'completed': len(maint),
            'cost': round(sum(m.cost or 0 for m in maint), 2)},
    }


def snapshot_daily_metrics(db, day):
    """Upsert de la fila daily_metrics para `day`. Devuelve la entity.
    No commitea — el llamador decide (contrato del resto de la app)."""
    row = db.query(DailyMetric).filter(
        DailyMetric.metric_date == day).first()
    if row is None:
        row = DailyMetric(metric_date=day, data={})
        db.add(row)
    row.data = compute_daily_metrics(db, day)
    row.computed_at = utcnow()
    return row


def run_metrics(SessionLocal):
    """Corrida programada: refresca el snapshot de hoy (parcial) y el
    de ayer (final)."""
    today = utcnow().date()
    db = SessionLocal()
    try:
        snapshot_daily_metrics(db, today)
        snapshot_daily_metrics(db, today - timedelta(days=1))
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f'metrics: {exc}', flush=True)
    finally:
        db.close()


async def metrics_loop(SessionLocal):
    while True:
        await asyncio.sleep(INTERVAL_S)
        await asyncio.to_thread(run_metrics, SessionLocal)
