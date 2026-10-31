"""Tracking — POST /update recibe posiciones de la app móvil (conductor
o vehículo), guarda el evento, actualiza la posición del vehículo,
broadcast por WS /live y dispara inline: speed_violation,
geofence_violation (bordes enter/exit de los polígonos activos) y
route_deviation (distancia a la polyline de la ruta en curso). Las
alertas nuevas se broadcastean como {"type":"alert"} después del
location_update y, si su severidad está en ALERT_EMAIL_SEVERITIES con
SMTP configurado, también se notifican por email (el motor de reglas
de alerts_engine hace lo mismo con las que genera en su tick).

WS /api/tracking/live — autenticación por cookie `auth` o ?token=<jwt>
(las apps móviles no manejan cookies fácilmente)."""
import os

import jwt
from fastapi import (APIRouter, Depends, HTTPException, Query, WebSocket,
                     WebSocketDisconnect)
from sqlalchemy.orm import Session

from ..alerts_engine import broadcast_alerts, create_alert
from ..archive import RETENTION_DAYS, archive_old_events
from ..db import get_db
from ..geo import point_in_polygon, point_to_polyline_km
from ..models import (Alert, Delivery, Driver, Geofence, Route,
                      RouteDelivery, TrackingEvent, TrackingEventArchive,
                      User, Vehicle, utcnow)
from ..schemas import (TrackingEventArchiveOut, TrackingEventOut,
                       TrackingUpdateIn)
from ..security import decode_token, get_current_user, require_roles
from ..ws import manager
from ._common import get_or_404

router = APIRouter()

_ro = Depends(get_current_user)
SPEED_LIMIT_KMH = float(os.getenv('SPEED_LIMIT_KMH', '120'))
ROUTE_DEVIATION_M = float(os.getenv('ROUTE_DEVIATION_M', '500'))


def _geofence_alerted(db, vehicle_id, geofence_id) -> bool:
    rows = db.query(Alert.alert_metadata).filter(
        Alert.type == 'geofence_violation',
        Alert.vehicle_id == vehicle_id,
        Alert.status.in_(['active', 'acknowledged'])).all()
    return any((m or {}).get('geofence_id') == geofence_id for (m,) in rows)


def check_geofences(db, vehicle, driver_id, prev, lat, lng):
    """Detección de borde: 'enter' dispara al cruzar de afuera→adentro,
    'exit' de adentro→afuera. Sin posición previa solo puede disparar
    'enter' (aparecer adentro ya es violación); 'exit' no puede saberse.
    Devuelve las alertas creadas (para broadcast post-commit)."""
    created = []
    fences = db.query(Geofence).filter(
        Geofence.is_active.is_(True),
        Geofence.vehicle_id.is_(None) |
        (Geofence.vehicle_id == vehicle.id)).all()
    prev_known = prev[0] is not None and prev[1] is not None
    for gf in fences:
        poly = gf.polygon or []
        if len(poly) < 3:
            continue
        now_in = point_in_polygon(lat, lng, poly)
        was_in = point_in_polygon(prev[0], prev[1], poly) if prev_known else False
        triggered = (not was_in and now_in) if gf.rule == 'enter' \
            else (was_in and not now_in)
        if not triggered or _geofence_alerted(db, vehicle.id, gf.id):
            continue
        direction = 'ingresó a' if gf.rule == 'enter' else 'salió de'
        created.append(Alert(type='geofence_violation',
                             severity=gf.severity or 'medium',
                             title=f'{vehicle.plate} {direction} {gf.name}',
                             description=f'Zona {gf.rule} violada en '
                                         f'({lat}, {lng})',
                             vehicle_id=vehicle.id, driver_id=driver_id,
                             alert_metadata={'geofence_id': gf.id,
                                             'geofence_name': gf.name,
                                             'rule': gf.rule,
                                             'lat': lat, 'lng': lng}))
    db.add_all(created)
    return created


def _route_polyline(db, route):
    """Polyline planificada: origen → waypoints (o paradas con coords,
    si la ruta nunca se optimizó) → destino."""
    pts = [(route.origin_lat, route.origin_lng)]
    wps = route.waypoints or []
    if wps:
        for w in sorted(wps, key=lambda w: w.get('order', 0)):
            if w.get('lat') is not None and w.get('lng') is not None:
                pts.append((float(w['lat']), float(w['lng'])))
    else:
        for rd in sorted(route.stops, key=lambda s: s.stop_order):
            d = db.get(Delivery, rd.delivery_id)
            addr = (d.delivery_address or {}) if d else {}
            if addr.get('lat') is not None and addr.get('lng') is not None:
                pts.append((float(addr['lat']), float(addr['lng'])))
    pts.append((route.destination_lat, route.destination_lng))
    return pts


def check_route_deviation(db, vehicle, driver_id, lat, lng):
    route = db.query(Route).filter(
        Route.assigned_vehicle_id == vehicle.id,
        Route.status == 'in_progress').first()
    if route is None:
        return None
    dist_m = point_to_polyline_km(lat, lng, _route_polyline(db, route)) * 1000
    if dist_m <= ROUTE_DEVIATION_M:
        return None
    alert = create_alert(
        db, 'route_deviation', 'high' if dist_m > 2000 else 'medium',
        f'{vehicle.plate} desviado de la ruta {route.name}',
        f'A {round(dist_m)} m del trazado planificado '
        f'(umbral {ROUTE_DEVIATION_M:g} m)',
        vehicle_id=vehicle.id, driver_id=driver_id, route_id=route.id)
    if alert is not None:
        alert.alert_metadata = {'distance_m': round(dist_m),
                                'lat': lat, 'lng': lng}
    return alert


@router.post('/update', response_model=TrackingEventOut, status_code=201)
def tracking_update(payload: TrackingUpdateIn, db: Session = Depends(get_db),
                    _u: User = _ro):
    vehicle = get_or_404(db, Vehicle, payload.vehicle_id, 'vehicle')
    if payload.driver_id:
        get_or_404(db, Driver, payload.driver_id, 'driver')
    ts = payload.timestamp or utcnow()
    event = TrackingEvent(
        vehicle_id=payload.vehicle_id, driver_id=payload.driver_id,
        lat=payload.location.lat, lng=payload.location.lng,
        speed_kmh=payload.speed_kmh, heading=payload.heading, timestamp=ts,
        accuracy_meters=payload.accuracy_meters,
        battery_level=payload.battery_level,
        engine_status=payload.engine_status, fuel_level=payload.fuel_level,
        event_metadata=payload.metadata)
    db.add(event)
    prev = (vehicle.lat, vehicle.lng)
    vehicle.lat = payload.location.lat
    vehicle.lng = payload.location.lng
    vehicle.last_location_update = ts
    new_alerts = []
    if (payload.speed_kmh or 0) > SPEED_LIMIT_KMH:
        new_alerts.append(create_alert(
            db, 'speed_violation', 'medium',
            f'Exceso de velocidad en {vehicle.plate}',
            f'{payload.speed_kmh} km/h (límite {SPEED_LIMIT_KMH})',
            vehicle_id=vehicle.id, driver_id=payload.driver_id))
    new_alerts += check_geofences(db, vehicle, payload.driver_id, prev,
                                  event.lat, event.lng)
    new_alerts.append(check_route_deviation(db, vehicle, payload.driver_id,
                                            event.lat, event.lng))
    db.commit()
    db.refresh(event)
    # Broadcast a los WS suscritos (thread → loop de la app): primero la
    # posición, después las alertas que disparó este update.
    manager.broadcast_threadsafe({
        'type': 'location_update', 'vehicle_id': vehicle.id,
        'data': {'location': {'lat': event.lat, 'lng': event.lng},
                 'speed_kmh': event.speed_kmh,
                 'timestamp': event.timestamp.isoformat() if event.timestamp else None}})
    broadcast_alerts(new_alerts)
    return event


@router.get('/vehicles/{vehicle_id}/current')
def current_position(vehicle_id: str, db: Session = Depends(get_db),
                     _u: User = _ro):
    vehicle = get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    return {'vehicle_id': vehicle_id, 'plate': vehicle.plate,
            'location': {'lat': vehicle.lat, 'lng': vehicle.lng}
            if vehicle.lat is not None else None,
            'last_location_update': vehicle.last_location_update,
            'status': vehicle.status}


@router.get('/vehicles/{vehicle_id}/history',
            response_model=list[TrackingEventArchiveOut])
def tracking_history(vehicle_id: str,
                     limit: int = Query(200, ge=1, le=1000),
                     archived: bool = Query(False),
                     db: Session = Depends(get_db), _u: User = _ro):
    """Historial del vehículo — `?archived=true` lee de
    tracking_events_archive (eventos vencidos por retención)."""
    get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    model = TrackingEventArchive if archived else TrackingEvent
    return (db.query(model)
            .filter(model.vehicle_id == vehicle_id)
            .order_by(model.timestamp.desc()).limit(limit).all())


@router.post('/archive')
def archive_tracking(db: Session = Depends(get_db),
                     _u: User = Depends(require_roles('admin'))):
    """Archivado manual (admin): mueve a tracking_events_archive los
    eventos más viejos que TRACKING_RETENTION_DAYS. El loop de lifespan
    corre lo mismo cada TRACKING_ARCHIVE_INTERVAL_S."""
    moved, cutoff = archive_old_events(db)
    db.commit()
    return {'archived': moved, 'cutoff': cutoff,
            'retention_days': RETENTION_DAYS}


@router.get('/routes/{route_id}/progress')
def route_progress(route_id: str, db: Session = Depends(get_db), _u: User = _ro):
    route = get_or_404(db, Route, route_id, 'route')
    stops = db.query(RouteDelivery).filter(
        RouteDelivery.route_id == route_id).all()
    delivery_ids = [s.delivery_id for s in stops]
    done = db.query(Delivery).filter(
        Delivery.id.in_(delivery_ids or ['']),
        Delivery.status == 'delivered').count() if delivery_ids else 0
    last = None
    if route.assigned_vehicle_id:
        last = (db.query(TrackingEvent)
                .filter(TrackingEvent.vehicle_id == route.assigned_vehicle_id)
                .order_by(TrackingEvent.timestamp.desc()).first())
    return {'route_id': route_id, 'status': route.status,
            'stops_total': len(stops), 'stops_completed': done,
            'progress_pct': round(done / len(stops) * 100, 1) if stops else 0,
            'last_position': {'lat': last.lat, 'lng': last.lng,
                              'timestamp': last.timestamp} if last else None}


def _ws_user_id(ws: WebSocket):
    token = ws.cookies.get('auth') or ws.query_params.get('token')
    if not token:
        return None
    try:
        return decode_token(token).get('sub')
    except jwt.PyJWTError:
        return None


@router.websocket('/live')
async def tracking_live(ws: WebSocket):
    if _ws_user_id(ws) is None:
        await ws.close(code=4401)
        return
    await manager.connect(ws)
    try:
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get('type') == 'subscribe':
                manager.subscribe(ws, msg.get('vehicles'))
                await ws.send_json({'type': 'subscribed',
                                    'vehicles': msg.get('vehicles') or 'all'})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(ws)
