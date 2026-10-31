"""Motor de reglas de alertas — corre como tarea asyncio en el lifespan
de la app (cada ALERTS_INTERVAL_S segundos, en thread para no bloquear
el loop). Implementa las reglas que no requieren infra extra:

- sla_breach: entrega pending/in_transit con sla_deadline vencido.
- maintenance_due: mileage >= next_service_mileage o next_service_date
  vencida (del último registro de mantenimiento del vehículo).
- driver_fatigue: turno abierto (driver_shifts sin end_time) > 10 h.
- speed_violation, geofence_violation y route_deviation se disparan
  inline en routers/tracking.py (dependen de cada posición nueva).

Dedup: no crea una alerta si ya existe una `active` del mismo tipo para
la misma entidad (delivery/vehicle/driver)."""
import asyncio
import os
from datetime import date

from .models import (Alert, Delivery, DriverShift, MaintenanceRecord,
                     Vehicle, utcnow)
from .notifications import notify_new_alerts
from .schemas import AlertOut
from .ws import manager

INTERVAL_S = int(os.getenv('ALERTS_INTERVAL_S', '60'))
MAX_SHIFT_HOURS = 10


def alert_ws_message(alert):
    """Mensaje WS de alerta nueva — `vehicle_id` top-level para el
    filtro de suscripciones del manager; `data` tiene el mismo shape
    que GET /api/alerts."""
    return {'type': 'alert', 'vehicle_id': alert.vehicle_id,
            'alert_id': alert.id,
            'data': AlertOut.model_validate(alert).model_dump(mode='json')}


def broadcast_alerts(alerts):
    """Despacha las alertas nuevas a todos los canales: WS suscritos +
    email si la severidad está en ALERT_EMAIL_SEVERITIES y hay SMTP
    configurado. Llamar DESPUÉS del commit (los objetos necesitan
    id/triggered_at persistidos)."""
    for alert in alerts:
        if alert is not None:
            manager.broadcast_threadsafe(alert_ws_message(alert))
    notify_new_alerts(alerts)


def _exists_active(db, type_, **entity):
    q = db.query(Alert).filter(Alert.type == type_, Alert.status.in_(['active', 'acknowledged']))
    for key, val in entity.items():
        if val is not None:
            q = q.filter(getattr(Alert, key) == val)
    return db.query(q.exists()).scalar()


def create_alert(db, type_, severity, title, description='', **entity):
    if _exists_active(db, type_, **entity):
        return None
    alert = Alert(type=type_, severity=severity, title=title,
                  description=description, **entity)
    db.add(alert)
    return alert


def check_sla_breaches(db):
    now = utcnow()
    created = []
    overdue = db.query(Delivery).filter(
        Delivery.status.in_(['pending', 'in_transit']),
        Delivery.sla_deadline.isnot(None),
        Delivery.sla_deadline < now).all()
    for d in overdue:
        created.append(create_alert(
            db, 'sla_breach', 'high',
            f'SLA vencido para entrega {d.order_number}',
            f'Deadline {d.sla_deadline} superado con estado {d.status}',
            delivery_id=d.id, route_id=d.route_id))
    return created


def check_maintenance_due(db):
    today = date.today()
    created = []
    vehicles = db.query(Vehicle).filter(Vehicle.is_active.is_(True)).all()
    for v in vehicles:
        last = (db.query(MaintenanceRecord)
                .filter(MaintenanceRecord.vehicle_id == v.id,
                        MaintenanceRecord.next_service_date.isnot(None) |
                        MaintenanceRecord.next_service_mileage.isnot(None))
                .order_by(MaintenanceRecord.created_at.desc()).first())
        if last is None:
            continue
        due_mileage = (last.next_service_mileage is not None
                       and (v.mileage or 0) >= last.next_service_mileage)
        due_date = (last.next_service_date is not None
                    and last.next_service_date <= today)
        if due_mileage or due_date:
            why = f'kilometraje {v.mileage}' if due_mileage else f'fecha {last.next_service_date}'
            created.append(create_alert(
                db, 'maintenance_due', 'medium',
                f'Mantenimiento pendiente para {v.plate}',
                f'Vencido por {why}',
                vehicle_id=v.id))
    return created


def check_driver_fatigue(db):
    now = utcnow()
    created = []
    open_shifts = db.query(DriverShift).filter(DriverShift.end_time.is_(None)).all()
    for s in open_shifts:
        hours = (now - s.start_time).total_seconds() / 3600
        if hours > MAX_SHIFT_HOURS:
            created.append(create_alert(
                db, 'driver_fatigue', 'high',
                f'Conductor excede {MAX_SHIFT_HOURS}h de turno',
                f'Turno iniciado {s.start_time} ({hours:.1f}h en curso)',
                driver_id=s.driver_id, vehicle_id=s.vehicle_id))
    return created


def run_checks(SessionLocal):
    db = SessionLocal()
    try:
        new = (check_sla_breaches(db) + check_maintenance_due(db)
               + check_driver_fatigue(db))
        db.commit()
        broadcast_alerts(new)
    except Exception as exc:
        db.rollback()
        print(f'alerts_engine: {exc}', flush=True)
    finally:
        db.close()


async def alerts_loop(SessionLocal):
    while True:
        await asyncio.sleep(INTERVAL_S)
        await asyncio.to_thread(run_checks, SessionLocal)
