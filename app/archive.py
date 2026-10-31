"""Archivado de tracking_events — corre como tarea asyncio en el
lifespan (cada TRACKING_ARCHIVE_INTERVAL_S, default 1 h, en thread
para no bloquear el loop) y también por POST /api/tracking/archive.

Los eventos con timestamp más viejo que TRACKING_RETENTION_DAYS
(default 30) se mueven a tracking_events_archive (misma shape +
archived_at, sin FKs) y se borran de la tabla caliente — así las
queries de tracking reciente quedan chicas en producción."""
import asyncio
import os
from datetime import timedelta

from .models import TrackingEvent, TrackingEventArchive, utcnow

RETENTION_DAYS = int(os.getenv('TRACKING_RETENTION_DAYS', '30'))
ARCHIVE_INTERVAL_S = int(os.getenv('TRACKING_ARCHIVE_INTERVAL_S', '3600'))
BATCH = 5000


def archive_old_events(db, retention_days=RETENTION_DAYS):
    """Mueve a tracking_events_archive los eventos más viejos que la
    retención. Devuelve (movidos, cutoff). No commitea — el llamador
    decide (mismo contrato que el resto de la app)."""
    cutoff = utcnow() - timedelta(days=retention_days)
    moved = 0
    while True:
        ids = [r[0] for r in db.query(TrackingEvent.id)
               .filter(TrackingEvent.timestamp < cutoff)
               .limit(BATCH).all()]
        if not ids:
            break
        events = db.query(TrackingEvent).filter(
            TrackingEvent.id.in_(ids)).all()
        for e in events:
            db.add(TrackingEventArchive(
                id=e.id, vehicle_id=e.vehicle_id, driver_id=e.driver_id,
                lat=e.lat, lng=e.lng, speed_kmh=e.speed_kmh,
                heading=e.heading, timestamp=e.timestamp,
                accuracy_meters=e.accuracy_meters,
                battery_level=e.battery_level,
                engine_status=e.engine_status, fuel_level=e.fuel_level,
                event_metadata=e.event_metadata))
        db.query(TrackingEvent).filter(
            TrackingEvent.id.in_(ids)).delete(synchronize_session=False)
        db.flush()
        moved += len(ids)
    return moved, cutoff


def run_archive(SessionLocal):
    db = SessionLocal()
    try:
        moved, cutoff = archive_old_events(db)
        db.commit()
        if moved:
            print(f'tracking archive: {moved} eventos anteriores a '
                  f'{cutoff.date()}', flush=True)
    except Exception as exc:
        db.rollback()
        print(f'tracking archive: {exc}', flush=True)
    finally:
        db.close()


async def archive_loop(SessionLocal):
    while True:
        await asyncio.sleep(ARCHIVE_INTERVAL_S)
        await asyncio.to_thread(run_archive, SessionLocal)
