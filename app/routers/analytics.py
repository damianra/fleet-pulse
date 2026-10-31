"""Analytics — métricas agregadas para el dashboard de flota.
Lectura: cualquier usuario autenticado. Los endpoints "live" agregan
sobre la marcha; `daily_metrics` (app/metrics.py) guarda un snapshot
por día para series históricas (GET /history*)."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..metrics import snapshot_daily_metrics
from ..models import (Alert, DailyMetric, Delivery, Driver,
                      MaintenanceRecord, Route, User, Vehicle, utcnow)
from ..schemas import DailyMetricOut, SnapshotIn
from ..security import get_current_user, require_roles

router = APIRouter()

_ro = Depends(get_current_user)


def _by(rows, attr):
    out = {}
    for r in rows:
        key = getattr(r, attr)
        out[key] = out.get(key, 0) + 1
    return out


@router.get('/fleet-overview')
def fleet_overview(db: Session = Depends(get_db), _u: User = _ro):
    vehicles = db.query(Vehicle).filter(Vehicle.is_active.is_(True)).all()
    deliveries = db.query(Delivery).all()
    today = utcnow().date()
    done = [d for d in deliveries if d.status == 'delivered']
    on_time = [d for d in done if d.actual_delivery_time
               and d.delivery_window_end
               and d.actual_delivery_time <= d.delivery_window_end]
    dist_today = db.query(func.coalesce(func.sum(Route.total_distance_km), 0)).filter(
        func.date(Route.actual_start) == today.isoformat()).scalar() or 0
    return {
        'total_vehicles': len(vehicles),
        'vehicles_by_status': _by(vehicles, 'status'),
        'active_deliveries': sum(1 for d in deliveries
                                 if d.status in ('pending', 'in_transit')),
        'on_time_delivery_rate': round(len(on_time) / len(done), 3) if done else None,
        'total_distance_today_km': round(dist_today, 2),
        'active_alerts': db.query(Alert).filter(Alert.status == 'active').count(),
        'critical_alerts': db.query(Alert).filter(
            Alert.status == 'active', Alert.severity == 'critical').count(),
    }


@router.get('/deliveries')
def deliveries_metrics(db: Session = Depends(get_db), _u: User = _ro):
    rows = db.query(Delivery).all()
    done = [d for d in rows if d.status == 'delivered']
    on_time = [d for d in done if d.actual_delivery_time
               and d.delivery_window_end
               and d.actual_delivery_time <= d.delivery_window_end]
    return {'total': len(rows), 'by_status': _by(rows, 'status'),
            'by_priority': _by(rows, 'priority'),
            'on_time_rate': round(len(on_time) / len(done), 3) if done else None}


@router.get('/drivers')
def drivers_metrics(db: Session = Depends(get_db), _u: User = _ro):
    rows = db.query(Driver).all()
    return {'total': len(rows), 'by_status': _by(rows, 'status'),
            'top_by_deliveries': sorted(
                ({'driver_id': d.id, 'license': d.license_number,
                  'deliveries': d.total_deliveries or 0} for d in rows),
                key=lambda x: x['deliveries'], reverse=True)[:10],
            'avg_rating': round(sum(d.rating or 0 for d in rows) / len(rows), 2) if rows else 0}


@router.get('/vehicles')
def vehicles_metrics(db: Session = Depends(get_db), _u: User = _ro):
    rows = db.query(Vehicle).filter(Vehicle.is_active.is_(True)).all()
    in_use = sum(1 for v in rows if v.status == 'in_route')
    return {'total': len(rows), 'by_status': _by(rows, 'status'),
            'by_type': _by(rows, 'type'),
            'utilization_rate': round(in_use / len(rows), 3) if rows else 0}


@router.get('/routes')
def routes_metrics(db: Session = Depends(get_db), _u: User = _ro):
    rows = db.query(Route).all()
    done = [r for r in rows if r.status == 'completed' and r.actual_start and r.actual_end]
    durations = [(r.actual_end - r.actual_start).total_seconds() / 60 for r in done]
    return {'total': len(rows), 'by_status': _by(rows, 'status'),
            'by_type': _by(rows, 'type'),
            'total_distance_km': round(sum(r.total_distance_km or 0 for r in rows), 2),
            'avg_duration_minutes': round(sum(durations) / len(durations), 1) if durations else None}


@router.get('/alerts')
def alerts_metrics(db: Session = Depends(get_db), _u: User = _ro):
    rows = db.query(Alert).all()
    return {'total': len(rows), 'by_status': _by(rows, 'status'),
            'by_type': _by(rows, 'type'), 'by_severity': _by(rows, 'severity')}


@router.get('/costs')
def costs_metrics(db: Session = Depends(get_db), _u: User = _ro):
    rows = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.status == 'completed').all()
    by_month = {}
    for r in rows:
        if r.completed_date:
            key = r.completed_date.strftime('%Y-%m')
            by_month[key] = round(by_month.get(key, 0) + (r.cost or 0), 2)
    return {'maintenance_total': round(sum(r.cost or 0 for r in rows), 2),
            'maintenance_by_month': by_month,
            'records_completed': len(rows)}


@router.get('/history', response_model=list[DailyMetricOut])
def metrics_history(days: int = Query(30, ge=1, le=365),
                    to: date = Query(None),
                    db: Session = Depends(get_db), _u: User = _ro):
    """Serie histórica: snapshots diarios persistidos por el loop de
    métricas (o por POST /snapshot). `to` = último día (default hoy),
    `days` = cuántos días hacia atrás."""
    to = to or utcnow().date()
    return (db.query(DailyMetric)
            .filter(DailyMetric.metric_date > to - timedelta(days=days),
                    DailyMetric.metric_date <= to)
            .order_by(DailyMetric.metric_date).all())


@router.get('/history/{day}', response_model=DailyMetricOut)
def metrics_history_day(day: date, db: Session = Depends(get_db),
                        _u: User = _ro):
    row = db.query(DailyMetric).filter(
        DailyMetric.metric_date == day).first()
    if row is None:
        raise HTTPException(404, 'sin snapshot para esa fecha')
    return row


@router.post('/snapshot', response_model=DailyMetricOut, status_code=201)
def metrics_snapshot(body: SnapshotIn = None,
                     db: Session = Depends(get_db),
                     _u: User = Depends(require_roles('admin', 'dispatcher'))):
    """Snapshot manual (admin/dispatcher): computa/actualiza las
    métricas de `day` (default hoy) y devuelve la fila."""
    day = (body.day if body and body.day else utcnow().date())
    row = snapshot_daily_metrics(db, day)
    db.commit()
    return row
