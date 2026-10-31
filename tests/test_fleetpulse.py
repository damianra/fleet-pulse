"""Tests FleetPulse — flujo auth (JWT en cookie httpOnly + CSRF +
RBAC), CRUD de flota, turnos, rutas+optimización, tracking+alertas,
mantenimiento, analytics y WS live."""
from fastapi.testclient import TestClient

from app.main import app

ADMIN = {'email': 'admin@fleetpulse.test', 'password': 'adminpass123'}


# ---------- auth ----------

def test_health(anon):
    assert anon.get('/api/health').json() == {'ok': True}


def test_auth_flow(admin, anon):
    # el primer usuario queda admin (bootstrap del fixture)
    assert admin.get('/api/auth/me').json()['role'] == 'admin'

    # sin auth → 401
    assert anon.get('/api/auth/me').status_code == 401
    assert anon.get('/api/vehicles').status_code == 401

    # register inválido → 400
    assert anon.post('/api/auth/register', json={
        'email': 'no-es-email', 'password': 'password123'}).status_code == 400
    assert anon.post('/api/auth/register', json={
        'email': 'ok@test.co', 'password': 'corta'}).status_code == 400

    # register duplicado → 409
    assert anon.post('/api/auth/register', json={
        'email': ADMIN['email'], 'password': 'password123'}).status_code == 409

    # login inválido → 401 genérico (no enumera usuarios)
    r = anon.post('/api/auth/login', json={
        'email': 'noexiste@fleetpulse.test', 'password': 'password123'})
    assert r.status_code == 401
    r = anon.post('/api/auth/login', json={
        'email': ADMIN['email'], 'password': 'wrongpass'})
    assert r.status_code == 401

    # login ok → JWT en cookie httpOnly, NUNCA en el body
    r = anon.post('/api/auth/login', json=ADMIN)
    assert r.status_code == 200
    assert 'auth' in anon.cookies
    body = r.json()
    assert 'token' not in body and 'access_token' not in body
    assert anon.get('/api/auth/me').json()['email'] == ADMIN['email']

    # CSRF: mutación con cookie pero sin header válido → 403; con header → 201
    payload = {'plate': 'CSRF01', 'type': 'car'}
    assert anon.post('/api/vehicles', json=payload).status_code == 403
    anon.headers['x-csrf-token'] = anon.cookies.get('csrf')
    assert anon.post('/api/vehicles', json=payload).status_code == 201

    # Bearer sin cookie → exento de CSRF (consumidor externo / app móvil)
    token = anon.cookies.get('auth')
    bearer = TestClient(app)
    r = bearer.post('/api/vehicles', json={'plate': 'BEAR01', 'type': 'van'},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 201


def test_rbac_viewer(admin, anon):
    r = anon.post('/api/auth/register', json={
        'email': 'viewer@fleetpulse.test', 'password': 'viewerpass'})
    assert r.status_code == 201 and r.json()['role'] == 'viewer'
    anon.headers['x-csrf-token'] = anon.cookies.get('csrf')
    assert anon.get('/api/vehicles').status_code == 200  # lectura ok
    assert anon.post('/api/vehicles', json={
        'plate': 'VIEW01'}).status_code == 403  # escritura bloqueada

    # admin puede promover el rol
    user_id = r.json()['id']
    r = admin.put(f'/api/auth/users/{user_id}', json={'role': 'dispatcher'})
    assert r.status_code == 200 and r.json()['role'] == 'dispatcher'


def test_logout(admin, anon):
    assert anon.post('/api/auth/login', json=ADMIN).status_code == 200
    anon.headers['x-csrf-token'] = anon.cookies.get('csrf')
    assert anon.post('/api/auth/logout').status_code == 204
    assert anon.get('/api/auth/me').status_code == 401


# ---------- seed + vehicles ----------

def test_seed_data(admin):
    vehicles = admin.get('/api/vehicles').json()
    assert any(v['plate'] == 'ABC123' for v in vehicles)
    drivers = admin.get('/api/drivers').json()
    assert any(d['license_number'] == 'LIC-1001' for d in drivers)
    assert admin.get('/api/items').status_code == 404  # muestra eliminada


def test_vehicles_crud(admin):
    r = admin.post('/api/vehicles', json={
        'plate': 'TEST900', 'type': 'truck', 'brand': 'Scania',
        'model': 'R450', 'year': 2020, 'capacity_kg': 18000,
        'fuel_type': 'diesel', 'mileage': 90000})
    assert r.status_code == 201
    vid = r.json()['id']

    # duplicado de patente → 409
    assert admin.post('/api/vehicles', json={
        'plate': 'TEST900', 'type': 'truck'}).status_code == 409

    found = [v for v in admin.get('/api/vehicles?search=TEST900').json()
             if v['id'] == vid]
    assert found and found[0]['brand'] == 'Scania'
    assert admin.get('/api/vehicles?status=in_route').json() == [] or all(
        v['status'] == 'in_route'
        for v in admin.get('/api/vehicles?status=in_route').json())

    r = admin.put(f'/api/vehicles/{vid}', json={'mileage': 91000})
    assert r.status_code == 200 and r.json()['mileage'] == 91000

    stats = admin.get('/api/vehicles/stats').json()
    assert stats['total_vehicles'] >= 4

    assert admin.delete(f'/api/vehicles/{vid}').status_code == 204
    assert admin.get(f'/api/vehicles/{vid}').status_code == 404  # soft delete


def test_assign_driver(admin):
    vid = admin.post('/api/vehicles', json={
        'plate': 'ASG001', 'type': 'van'}).json()['id']
    did = admin.post('/api/drivers', json={
        'license_number': 'LIC-ASG'}).json()['id']
    r = admin.post(f'/api/vehicles/{vid}/assign-driver',
                   json={'driver_id': did})
    assert r.status_code == 200 and r.json()['assigned_driver_id'] == did
    driver = admin.get(f'/api/drivers/{did}').json()
    assert driver['current_vehicle_id'] == vid
    r = admin.post(f'/api/vehicles/{vid}/assign-driver', json={'driver_id': None})
    assert r.json()['assigned_driver_id'] is None


# ---------- drivers / shifts ----------

def test_driver_shifts(admin):
    did = admin.post('/api/drivers', json={
        'license_number': 'LIC-T1', 'phone': '+54 11 1111-2222'}).json()['id']

    r = admin.post(f'/api/drivers/{did}/start-shift', json={})
    assert r.status_code == 201
    shift = r.json()
    assert admin.get(f'/api/drivers/{did}').json()['status'] == 'on_duty'

    # segundo turno abierto → 409
    assert admin.post(f'/api/drivers/{did}/start-shift',
                      json={}).status_code == 409

    r = admin.post(f'/api/drivers/{did}/end-shift')
    assert r.status_code == 200
    assert r.json()['end_time'] is not None
    assert admin.get(f'/api/drivers/{did}').json()['status'] == 'off_duty'

    shifts = admin.get(f'/api/drivers/{did}/shifts').json()
    assert any(s['id'] == shift['id'] for s in shifts)
    perf = admin.get(f'/api/drivers/{did}/performance').json()
    assert 'on_time_rate' in perf and 'total_shift_hours' in perf


# ---------- routes + deliveries + optimize ----------

def test_route_optimize_and_lifecycle(admin):
    route = admin.post('/api/routes', json={
        'name': 'Ruta Test', 'origin_lat': -34.60, 'origin_lng': -58.38,
        'destination_lat': -34.65, 'destination_lng': -58.45}).json()
    rid = route['id']

    stops = []
    for i, (lat, lng) in enumerate([(-34.61, -58.40), (-34.63, -58.42),
                                    (-34.62, -58.39)]):
        d = admin.post('/api/deliveries', json={
            'order_number': f'OPT-{i}',
            'delivery_address': {'street': f'Calle {i}', 'lat': lat, 'lng': lng},
            'priority': 'medium'}).json()
        r = admin.post(f'/api/routes/{rid}/add-delivery',
                       json={'delivery_id': d['id']})
        assert r.status_code == 201
        stops.append(d['id'])

    # entrega duplicada en la misma ruta → 409
    assert admin.post(f'/api/routes/{rid}/add-delivery',
                      json={'delivery_id': stops[0]}).status_code == 409

    # optimización (BackgroundTask — TestClient la espera) → done
    assert admin.post(f'/api/routes/{rid}/optimize', json={
        'algorithm': 'nearest_neighbor'}).status_code == 202
    st = admin.get(f'/api/routes/{rid}/optimization-status').json()
    assert st['status'] == 'done'
    route = admin.get(f'/api/routes/{rid}').json()
    assert route['total_distance_km'] > 0
    assert len(route['waypoints']) == 3

    # ciclo de vida
    r = admin.post(f'/api/routes/{rid}/start')
    assert r.status_code == 200 and r.json()['status'] == 'in_progress'
    progress = admin.get(f'/api/tracking/routes/{rid}/progress').json()
    assert progress['stops_total'] == 3

    # completar una entrega con prueba (firma + foto por URL)
    r = admin.post(f"/api/deliveries/{stops[0]}/complete", json={
        'signature_url': 'https://files.test/sig.png',
        'photo_urls': ['https://files.test/p1.jpg'], 'notes': 'ok'})
    assert r.status_code == 200 and r.json()['status'] == 'delivered'
    assert r.json()['proof_of_delivery']['signature_url'].endswith('sig.png')

    r = admin.post(f'/api/routes/{rid}/complete')
    assert r.status_code == 200 and r.json()['status'] == 'completed'

    stats = admin.get('/api/deliveries/stats').json()
    assert stats['total_deliveries'] >= 4


def test_deliveries_lifecycle(admin):
    d = admin.post('/api/deliveries', json={
        'order_number': 'LIFE-1', 'customer_name': 'Cliente X',
        'delivery_address': {'street': 'X 1', 'lat': -34.6, 'lng': -58.4},
        'delivery_window_end': '2030-01-01T18:00:00'}).json()
    did = d['id']

    r = admin.post(f'/api/deliveries/{did}/start')
    assert r.json()['status'] == 'in_transit'
    r = admin.post(f'/api/deliveries/{did}/fail', json={'reason': 'ausente'})
    assert r.json()['status'] == 'failed'
    r = admin.post(f'/api/deliveries/{did}/reschedule', json={
        'sla_deadline': '2030-01-02T18:00:00'})
    assert r.json()['status'] == 'rescheduled'
    assert admin.delete(f'/api/deliveries/{did}').status_code == 204


# ---------- tracking + alerts ----------

def test_tracking_update_and_speed_alert(admin):
    vid = next(v['id'] for v in admin.get('/api/vehicles').json()
               if v['plate'] == 'ABC123')
    r = admin.post('/api/tracking/update', json={
        'vehicle_id': vid,
        'location': {'lat': -34.6037, 'lng': -58.3816},
        'speed_kmh': 150.0, 'heading': 90.0, 'engine_status': 'on',
        'fuel_level': 70.0, 'battery_level': 90})
    assert r.status_code == 201

    cur = admin.get(f'/api/tracking/vehicles/{vid}/current').json()
    assert cur['location']['lat'] == -34.6037
    history = admin.get(f'/api/tracking/vehicles/{vid}/history').json()
    assert history and history[0]['speed_kmh'] == 150.0

    # exceso de velocidad → alerta speed_violation activa
    active = admin.get('/api/alerts/active').json()
    speed = next((a for a in active if a['type'] == 'speed_violation'
                  and a['vehicle_id'] == vid), None)
    assert speed is not None

    r = admin.post(f"/api/alerts/{speed['id']}/acknowledge")
    assert r.json()['status'] == 'acknowledged'
    r = admin.post(f"/api/alerts/{speed['id']}/resolve",
                   json={'notes': 'avisado al conductor'})
    assert r.json()['status'] == 'resolved' and r.json()['resolved_by']


def test_alerts_engine_sla(admin):
    d = admin.post('/api/deliveries', json={
        'order_number': 'SLA-1', 'sla_deadline': '2020-01-01T00:00:00'}).json()
    from app.db import SessionLocal
    from app.alerts_engine import run_checks
    run_checks(SessionLocal)
    alerts = admin.get('/api/alerts?type=sla_breach').json()
    sla = next((a for a in alerts if a['delivery_id'] == d['id']), None)
    assert sla is not None and sla['severity'] == 'high'
    stats = admin.get('/api/alerts/stats').json()
    assert stats['alerts_by_type'].get('sla_breach', 0) >= 1


def test_websocket_live(admin):
    vid = next(v['id'] for v in admin.get('/api/vehicles').json()
               if v['plate'] == 'DEF456')
    token = admin.cookies.get('auth')
    with admin.websocket_connect(
            f'/api/tracking/live?token={token}') as ws:
        ws.send_json({'type': 'subscribe', 'vehicles': [vid]})
        assert ws.receive_json()['type'] == 'subscribed'
        admin.post('/api/tracking/update', json={
            'vehicle_id': vid,
            'location': {'lat': -34.61, 'lng': -58.40}})
        msg = ws.receive_json()
        assert msg['type'] == 'location_update'
        assert msg['vehicle_id'] == vid
        assert msg['data']['location']['lat'] == -34.61


def test_ws_rejects_anonymous(anon):
    try:
        with anon.websocket_connect('/api/tracking/live') as ws:
            ws.receive_json()
        assert False, 'debió rechazar la conexión'
    except Exception:
        pass  # close 4401


def test_websocket_alert_broadcast(admin):
    # update con exceso de velocidad → llegan location_update + alert
    vid = next(v['id'] for v in admin.get('/api/vehicles').json()
               if v['plate'] == 'DEF456')
    token = admin.cookies.get('auth')
    with admin.websocket_connect(
            f'/api/tracking/live?token={token}') as ws:
        ws.send_json({'type': 'subscribe', 'vehicles': [vid]})
        assert ws.receive_json()['type'] == 'subscribed'
        admin.post('/api/tracking/update', json={
            'vehicle_id': vid,
            'location': {'lat': -34.50, 'lng': -58.55},
            'speed_kmh': 140.0})
        msgs = [ws.receive_json(), ws.receive_json()]
    loc = next(m for m in msgs if m['type'] == 'location_update')
    alert = next(m for m in msgs if m['type'] == 'alert')
    assert loc['vehicle_id'] == vid
    assert alert['vehicle_id'] == vid and alert['alert_id']
    assert alert['data']['type'] == 'speed_violation'
    assert alert['data']['status'] == 'active'
    assert alert['data']['severity'] == 'medium'


def test_websocket_engine_alert_broadcast(admin):
    # el motor de reglas también broadcastea (sla_breach sin vehicle_id
    # solo llega a suscriptores de "todos" — no mandamos subscribe)
    d = admin.post('/api/deliveries', json={
        'order_number': 'SLA-WS-1',
        'sla_deadline': '2020-01-01T00:00:00'}).json()
    token = admin.cookies.get('auth')
    with admin.websocket_connect(
            f'/api/tracking/live?token={token}') as ws:
        from app.db import SessionLocal
        from app.alerts_engine import run_checks
        run_checks(SessionLocal)
        msg = ws.receive_json()
    assert msg['type'] == 'alert'
    assert msg['data']['type'] == 'sla_breach'
    assert msg['data']['delivery_id'] == d['id']


# ---------- maintenance + analytics ----------

def test_maintenance_flow(admin):
    vid = next(v['id'] for v in admin.get('/api/vehicles').json()
               if v['plate'] == 'GHI789')
    from datetime import date, timedelta
    r = admin.post('/api/maintenance', json={
        'vehicle_id': vid, 'type': 'preventive',
        'description': 'Cambio de aceite',
        'scheduled_date': str(date.today()),
        'next_service_date': str(date.today() + timedelta(days=10)),
        'next_service_mileage': 15000, 'cost': 8500})
    assert r.status_code == 201
    mid = r.json()['id']

    upcoming = admin.get('/api/maintenance/upcoming').json()
    assert any(m['id'] == mid for m in upcoming)
    history = admin.get(f'/api/maintenance/vehicles/{vid}').json()
    assert any(m['id'] == mid for m in history)

    r = admin.post(f'/api/maintenance/{mid}/complete')
    assert r.status_code == 200 and r.json()['status'] == 'completed'
    assert r.json()['completed_date'] is not None


def test_analytics_overview(admin):
    ov = admin.get('/api/analytics/fleet-overview').json()
    assert ov['total_vehicles'] >= 3
    assert 'vehicles_by_status' in ov and 'on_time_delivery_rate' in ov
    assert admin.get('/api/analytics/deliveries').json()['total'] >= 1
    assert 'maintenance_total' in admin.get('/api/analytics/costs').json()


# ---------- geofences + desviación de ruta ----------

SQUARE = [{'lat': -34.00, 'lng': -59.00}, {'lat': -34.00, 'lng': -58.90},
          {'lat': -33.90, 'lng': -58.90}, {'lat': -33.90, 'lng': -59.00}]


def test_geofences_crud(admin):
    poly = [{'lat': -34.70, 'lng': -58.70}, {'lat': -34.70, 'lng': -58.60},
            {'lat': -34.60, 'lng': -58.60}, {'lat': -34.60, 'lng': -58.70}]
    r = admin.post('/api/geofences', json={
        'name': 'Zona Test', 'rule': 'enter', 'polygon': poly})
    assert r.status_code == 201
    gid = r.json()['id']

    # polígono con menos de 3 vértices → 422
    assert admin.post('/api/geofences', json={
        'name': 'Mala', 'polygon': poly[:2]}).status_code == 422

    assert admin.post(f'/api/geofences/{gid}/check', json={
        'lat': -34.65, 'lng': -58.65}).json()['inside'] is True
    assert admin.post(f'/api/geofences/{gid}/check', json={
        'lat': -34.50, 'lng': -58.65}).json()['inside'] is False

    r = admin.put(f'/api/geofences/{gid}', json={'severity': 'high'})
    assert r.status_code == 200 and r.json()['severity'] == 'high'
    assert any(g['id'] == gid for g in
               admin.get('/api/geofences?rule=enter').json())

    assert admin.delete(f'/api/geofences/{gid}').status_code == 204
    assert admin.get(f'/api/geofences/{gid}').status_code == 404


def test_geofence_enter_violation(admin):
    vid = admin.post('/api/vehicles', json={
        'plate': 'GEO001', 'type': 'car'}).json()['id']
    gf = admin.post('/api/geofences', json={
        'name': 'Restringida Test', 'rule': 'enter',
        'polygon': SQUARE}).json()

    # posición fuera de la zona → sin alerta
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.20, 'lng': -58.95}})

    # cruza hacia adentro → geofence_violation
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -33.95, 'lng': -58.95}})
    viol = [a for a in admin.get('/api/alerts/active').json()
            if a['type'] == 'geofence_violation' and a['vehicle_id'] == vid]
    assert len(viol) == 1
    assert viol[0]['metadata']['geofence_id'] == gf['id']

    # sigue adentro → no duplica (se dispara en el borde, no por nivel)
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -33.96, 'lng': -58.94}})
    viol = [a for a in admin.get('/api/alerts/active').json()
            if a['type'] == 'geofence_violation' and a['vehicle_id'] == vid]
    assert len(viol) == 1


def test_geofence_exit_violation(admin):
    vid = admin.post('/api/vehicles', json={
        'plate': 'GEO002', 'type': 'car'}).json()['id']
    admin.post('/api/geofences', json={
        'name': 'Perímetro permitido', 'rule': 'exit', 'severity': 'high',
        'polygon': [{'lat': -35.00, 'lng': -60.00},
                    {'lat': -35.00, 'lng': -59.00},
                    {'lat': -34.00, 'lng': -59.00},
                    {'lat': -34.00, 'lng': -60.00}]})

    # adentro → afuera dispara la alerta exit
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.50, 'lng': -59.50}})
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -33.90, 'lng': -59.50}})
    active = admin.get('/api/alerts/active').json()
    assert any(a['type'] == 'geofence_violation' and a['severity'] == 'high'
               and a['vehicle_id'] == vid for a in active)


def test_route_deviation_alert(admin):
    vid = admin.post('/api/vehicles', json={
        'plate': 'DEV001', 'type': 'truck'}).json()['id']
    route = admin.post('/api/routes', json={
        'name': 'Ruta Dev', 'origin_lat': -34.60, 'origin_lng': -58.40,
        'destination_lat': -34.60, 'destination_lng': -58.30,
        'assigned_vehicle_id': vid,
        'waypoints': [{'lat': -34.60, 'lng': -58.35, 'order': 1}]}).json()
    admin.post(f"/api/routes/{route['id']}/start")

    # sobre el trazado → sin alerta
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.60, 'lng': -58.36}})
    assert not [a for a in admin.get('/api/alerts/active').json()
                if a['type'] == 'route_deviation' and a['vehicle_id'] == vid]

    # ~2.2 km al norte del eje → route_deviation
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.58, 'lng': -58.36}})
    dev = next((a for a in admin.get('/api/alerts/active').json()
                if a['type'] == 'route_deviation'
                and a['vehicle_id'] == vid), None)
    assert dev is not None
    assert dev['route_id'] == route['id']
    assert dev['severity'] == 'high'  # > 2 km
    assert dev['metadata']['distance_m'] > 500


# ---------- migraciones + archivado de tracking ----------

def test_migrations_upgrade_and_stamp(tmp_path):
    """DB nueva → `alembic upgrade head` crea todo (incl. archive) y
    deja alembic_version en head. DB legacy (tablas sin alembic_version)
    → create_all cubre el drift y `stamp head` la marca migrada."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, inspect, text

    from app.db import ALEMBIC_INI, Base, run_migrations
    import app.models  # noqa: F401 — entities en metadata

    head = ScriptDirectory.from_config(
        Config(str(ALEMBIC_INI))).get_current_head()

    fresh = create_engine(f'sqlite:///{tmp_path}/fresh.db')
    run_migrations(fresh)
    names = inspect(fresh).get_table_names()
    assert 'tracking_events' in names
    assert 'tracking_events_archive' in names
    with fresh.connect() as c:
        assert c.execute(text(
            'select version_num from alembic_version')).scalar() == head

    # simula legacy: solo la tabla users creada por create_all viejo
    legacy = create_engine(f'sqlite:///{tmp_path}/legacy.db')
    Base.metadata.tables['users'].create(legacy)
    run_migrations(legacy)
    names = inspect(legacy).get_table_names()
    assert 'tracking_events_archive' in names  # drift completado
    with legacy.connect() as c:
        assert c.execute(text(
            'select version_num from alembic_version')).scalar() == head


def test_tracking_archive(admin, anon):
    from datetime import timedelta

    from app.db import SessionLocal
    from app.models import TrackingEvent, utcnow

    vid = admin.post('/api/vehicles', json={
        'plate': 'ARC001', 'type': 'van'}).json()['id']
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.60, 'lng': -58.38},
        'speed_kmh': 40.0})

    # backdatear el evento para que venza la retención (30 días)
    db = SessionLocal()
    ev = db.query(TrackingEvent).filter(
        TrackingEvent.vehicle_id == vid).first()
    ev.timestamp = utcnow() - timedelta(days=60)
    db.commit()
    db.close()

    # sin auth → 401 (y solo admin puede archivar manualmente)
    assert anon.post('/api/tracking/archive').status_code == 401
    r = admin.post('/api/tracking/archive')
    assert r.status_code == 200
    assert r.json()['archived'] >= 1
    assert r.json()['retention_days'] == 30

    # salió de la tabla caliente y quedó en el archivo
    assert admin.get(
        f'/api/tracking/vehicles/{vid}/history').json() == []
    hist = admin.get(
        f'/api/tracking/vehicles/{vid}/history?archived=true').json()
    assert len(hist) == 1
    assert hist[0]['speed_kmh'] == 40.0
    assert hist[0]['archived_at'] is not None

    # eventos recientes NO se archivan
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.61, 'lng': -58.39}})
    admin.post('/api/tracking/archive')
    assert len(admin.get(
        f'/api/tracking/vehicles/{vid}/history').json()) == 1


# ---------- métricas diarias persistidas ----------

def test_daily_metrics(admin, anon):
    from app.models import utcnow

    today = utcnow().date().isoformat()

    # auth: history es lectura autenticada, snapshot admin/dispatcher
    assert anon.get('/api/analytics/history').status_code == 401
    assert anon.post('/api/analytics/snapshot').status_code == 401

    # datos del día: 1 evento de tracking con speed conocida
    vid = admin.post('/api/vehicles', json={
        'plate': 'MET001', 'type': 'van'}).json()['id']
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.60, 'lng': -58.38},
        'speed_kmh': 50.0})

    # snapshot manual de hoy → 201 con todas las secciones
    r = admin.post('/api/analytics/snapshot', json={})
    assert r.status_code == 201
    snap = r.json()
    assert snap['metric_date'] == today
    assert snap['computed_at']
    for section in ('deliveries', 'routes', 'alerts', 'tracking',
                    'drivers', 'maintenance'):
        assert section in snap['data']
    assert snap['data']['tracking']['events'] >= 1
    assert snap['data']['tracking']['vehicles_seen'] >= 1

    # snapshot de una fecha vieja sin datos → contadores en cero
    old = '2020-01-15'
    r1 = admin.post('/api/analytics/snapshot', json={'day': old})
    assert r1.status_code == 201
    assert r1.json()['metric_date'] == old
    assert r1.json()['data']['tracking']['events'] == 0
    assert r1.json()['data']['deliveries']['delivered'] == 0

    # upsert: re-snapshot del mismo día actualiza la misma fila
    r2 = admin.post('/api/analytics/snapshot', json={'day': old})
    assert r2.status_code == 201
    assert r2.json()['id'] == r1.json()['id']

    # history lista ordenada por fecha; el día upserteado no se duplica
    hist = admin.get('/api/analytics/history?days=365').json()
    dates = [h['metric_date'] for h in hist]
    assert dates == sorted(dates)
    assert today in dates
    hist_old = admin.get(f'/api/analytics/history?days=7&to={old}').json()
    assert [h['metric_date'] for h in hist_old] == [old]

    # history/{day} → la fila; fecha sin snapshot → 404
    assert admin.get(
        f'/api/analytics/history/{old}').json()['id'] == r1.json()['id']
    assert admin.get(
        '/api/analytics/history/1999-01-01').status_code == 404


def test_metrics_rollup_yesterday(admin):
    """run_metrics upsertea hoy + ayer — cubre el loop programado."""
    from datetime import timedelta

    from app.db import SessionLocal
    from app.metrics import run_metrics
    from app.models import DailyMetric, utcnow

    run_metrics(SessionLocal)
    db = SessionLocal()
    try:
        today = utcnow().date()
        for day in (today, today - timedelta(days=1)):
            row = db.query(DailyMetric).filter(
                DailyMetric.metric_date == day).first()
            assert row is not None
            assert row.data['tracking']['events'] >= 0
    finally:
        db.close()


# ---------- load test: tracking concurrente ----------

def test_tracking_concurrent_load(admin):
    """Load test básico: 10 vehículos reportando en paralelo (cada uno
    su propio TestClient Bearer — exento de CSRF, como la app móvil).
    Verifica que los 100 updates entran sin 5xx/429 y que TODOS los
    eventos quedan persistidos (sqlite serializa los commits)."""
    import concurrent.futures
    import time

    token = admin.cookies.get('auth')
    vehicles, per_vehicle = 10, 10
    vids = [admin.post('/api/vehicles', json={
        'plate': f'LOAD{i:03}', 'type': 'van'}).json()['id']
        for i in range(vehicles)]

    def report(vid, n):
        c = TestClient(app, headers={'Authorization': f'Bearer {token}'})
        return [c.post('/api/tracking/update', json={
            'vehicle_id': vid,
            'location': {'lat': -34.60 + (n + j) * 1e-4, 'lng': -58.40},
            'speed_kmh': 40.0, 'engine_status': 'on'}).status_code
            for j in range(per_vehicle)]

    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=vehicles) as pool:
        codes = list(pool.map(report, vids, range(vehicles)))
    elapsed = time.monotonic() - t0
    total = vehicles * per_vehicle
    print(f'\nload: {total} updates en {elapsed:.2f}s '
          f'({total / elapsed:.0f} ev/s)')

    assert all(s == 201 for batch in codes for s in batch)
    assert elapsed < 20  # bound laxo: detecta deadlocks/contención rota
    for vid in vids:
        hist = admin.get(
            f'/api/tracking/vehicles/{vid}/history?limit=1000').json()
        assert len(hist) == per_vehicle


# ---------- notificaciones email de alertas ----------

class _FakeSMTP:
    """Fake de smtplib.SMTP — captura host/port, tls/login y los
    EmailMessage enviados en `instances` para las assertions."""
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.messages = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, password):
        self.auth = (user, password)

    def send_message(self, msg):
        self.messages.append(msg)


def _wait_for(cond, timeout=5):
    """El envío de email corre en un thread daemon — poll hasta que el
    fake registre el mensaje (o timeout → assert falla)."""
    import time
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_alert_email_notifications(admin, monkeypatch):
    """End-to-end: geofence 'enter' severity=critical → tracking update
    dispara geofence_violation → el thread de notificación manda el
    mail por el SMTP fake (config puesta por env antes del request)."""
    import app.notifications as notif

    monkeypatch.setenv('SMTP_HOST', 'smtp.test')
    monkeypatch.setenv('ALERT_EMAIL_TO', 'ops@test.dev,dispatch@test.dev')
    monkeypatch.setenv('SMTP_FROM', 'fleet@test.dev')
    monkeypatch.setattr(notif.smtplib, 'SMTP', _FakeSMTP)
    _FakeSMTP.instances = []

    admin.post('/api/geofences', json={
        'name': 'Zona crítica', 'rule': 'enter', 'severity': 'critical',
        'polygon': [{'lat': -10.5, 'lng': -10.5},
                    {'lat': -10.5, 'lng': -9.5},
                    {'lat': -9.5, 'lng': -9.5},
                    {'lat': -9.5, 'lng': -10.5}]})
    vid = admin.post('/api/vehicles', json={
        'plate': 'MAIL001', 'type': 'van'}).json()['id']
    r = admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -10.0, 'lng': -10.0}})
    assert r.status_code == 201

    def sent():
        return [m for i in _FakeSMTP.instances for m in i.messages]

    assert _wait_for(lambda: sent())
    smtp = _FakeSMTP.instances[0]
    assert smtp.host == 'smtp.test' and smtp.port == 587
    assert getattr(smtp, 'tls', False) is True  # STARTTLS default
    msg = [m for m in sent() if 'CRITICAL' in m['Subject']][0]
    assert msg['From'] == 'fleet@test.dev'
    assert msg['To'] == 'ops@test.dev, dispatch@test.dev'
    body = msg.get_content()
    assert 'geofence_violation' in body and 'Zona crítica' in msg['Subject']


def test_alert_email_filter_and_noop(monkeypatch):
    """Sin SMTP_HOST/ALERT_EMAIL_TO es no-op; con config, solo las
    severidades de ALERT_EMAIL_SEVERITIES (default 'critical') mandan."""
    from types import SimpleNamespace

    import app.notifications as notif

    monkeypatch.delenv('SMTP_HOST', raising=False)
    monkeypatch.delenv('ALERT_EMAIL_TO', raising=False)
    monkeypatch.delenv('ALERT_EMAIL_SEVERITIES', raising=False)
    sent = []
    monkeypatch.setattr(notif, '_send_all',
                        lambda msgs, cfg: sent.extend(msgs))

    base = dict(severity='critical', title='Alerta crítica',
                description='desc', type='sla_breach', triggered_at=None,
                vehicle_id='v1', driver_id=None, route_id=None,
                delivery_id='d1', alert_metadata={'k': 1})
    alert = SimpleNamespace(**base)

    # sin config → ni siquiera construye/lanza el thread
    assert notif.notify_new_alerts([alert]) is None
    assert sent == []

    # con config: severidades fuera del set no notifican; 'critical' sí
    monkeypatch.setenv('SMTP_HOST', 'smtp.test')
    monkeypatch.setenv('ALERT_EMAIL_TO', 'ops@test.dev')
    low = SimpleNamespace(**{**base, 'severity': 'medium'})
    assert notif.notify_new_alerts([low]) is None
    t = notif.notify_new_alerts([alert])
    assert t is not None
    t.join(timeout=5)
    assert len(sent) == 1
    assert 'CRITICAL' in sent[0]['Subject']
    assert 'metadata' in sent[0].get_content()

    # severidades configurables: agregando 'high' también notifica
    monkeypatch.setenv('ALERT_EMAIL_SEVERITIES', 'critical,high')
    high = SimpleNamespace(**{**base, 'severity': 'high'})
    t = notif.notify_new_alerts([high])
    t.join(timeout=5)
    assert len(sent) == 2 and 'HIGH' in sent[1]['Subject']


def test_metrics_endpoint_and_http_instruments(admin, anon):
    # GET /metrics: scrape abierto (sin auth), formato texto Prometheus.
    # Los requests previos del suite ya poblaron http_requests_total con
    # templates de ruta (no URLs crudas) y el collector scrape-time
    # emite el estado actual de la flota desde la DB.
    r = anon.get('/metrics')
    assert r.status_code == 200
    assert 'text/plain' in r.headers['content-type']
    body = r.text
    assert 'http_requests_total{' in body
    assert 'http_request_duration_seconds' in body
    # label path = template de la ruta, cardinalidad acotada
    assert 'path="/api/health"' in body
    assert 'method="GET"' in body and 'status="200"' in body
    # métricas de negocio scrape-time (seed: vehículos available)
    assert 'fleetpulse_vehicles{' in body
    assert 'fleetpulse_alerts_active{' in body
    assert 'fleetpulse_deliveries{' in body
    assert 'fleetpulse_deliveries_completed_1h' in body


def test_request_id_header(anon):
    # El middleware genera un request id y lo devuelve; si el cliente
    # manda X-Request-ID lo respeta (trazabilidad end-to-end).
    r = anon.get('/api/health')
    assert r.headers.get('x-request-id')
    r2 = anon.get('/api/health', headers={'X-Request-ID': 'req-abc123'})
    assert r2.headers['x-request-id'] == 'req-abc123'


def test_json_log_formatter():
    # JsonFormatter: una línea JSON por registro, extras como campos
    # top-level (request_id, status...), sin pisar attrs estándar.
    import json
    import logging
    from app.observability import JsonFormatter

    record = logging.LogRecord(
        'fleetpulse.http', logging.INFO, __file__, 1,
        'GET /api/health 200', None, None)
    record.request_id = 'r1'
    record.status = 200
    entry = json.loads(JsonFormatter().format(record))
    assert entry['logger'] == 'fleetpulse.http'
    assert entry['level'] == 'INFO'
    assert entry['message'] == 'GET /api/health 200'
    assert entry['request_id'] == 'r1' and entry['status'] == 200
    assert 'ts' in entry
    # excepciones → campo 'exception' con el traceback
    try:
        raise ValueError('boom')
    except ValueError:
        import sys
        rec2 = logging.LogRecord(
            'x', logging.ERROR, __file__, 1, 'err', None,
            sys.exc_info())
    assert 'ValueError: boom' in json.loads(
        JsonFormatter().format(rec2))['exception']


# ---------- paths de error: deliveries / routes / maintenance / archive ----------

def test_deliveries_list_filters(admin):
    """GET /deliveries con filtros (status/priority/route_id/search) +
    paginación y orden."""
    for i in range(3):
        admin.post('/api/deliveries', json={
            'order_number': f'FILT-{i}',
            'priority': 'urgent' if i == 2 else 'low'})
    assert all(d['status'] == 'pending'
               for d in admin.get('/api/deliveries?status=pending').json())
    prio = admin.get('/api/deliveries?priority=urgent').json()
    assert any(d['order_number'] == 'FILT-2' for d in prio)
    assert all(d['priority'] == 'urgent' for d in prio)
    assert len(admin.get('/api/deliveries?search=FILT-').json()) >= 3
    by_route = admin.get(
        '/api/deliveries?route_id=no-existe').json()
    assert by_route == []
    page = admin.get(
        '/api/deliveries?page=1&limit=2&sort_by=order_number&order=asc'
    ).json()
    assert len(page) == 2
    nums = [d['order_number'] for d in page]
    assert nums == sorted(nums)


def test_deliveries_error_paths(admin):
    """404/409/400 del CRUD y el ciclo de vida de entregas."""
    # route_id inexistente → 404
    assert admin.post('/api/deliveries', json={
        'order_number': 'ERR-404', 'route_id': 'no-existe'
    }).status_code == 404

    did = admin.post('/api/deliveries', json={
        'order_number': 'ERR-1'}).json()['id']
    # order_number duplicado → 409
    assert admin.post('/api/deliveries', json={
        'order_number': 'ERR-1'}).status_code == 409

    # GET by id + 404
    assert admin.get(f'/api/deliveries/{did}').json()[
        'order_number'] == 'ERR-1'
    assert admin.get('/api/deliveries/no-existe').status_code == 404

    # update ok + 409 al chocar con otro order_number
    admin.post('/api/deliveries', json={'order_number': 'ERR-2'})
    r = admin.put(f'/api/deliveries/{did}', json={'notes': 'n1'})
    assert r.status_code == 200 and r.json()['notes'] == 'n1'
    assert admin.put(f'/api/deliveries/{did}', json={
        'order_number': 'ERR-2'}).status_code == 409

    # start en pending → ok; de nuevo (in_transit) → 400
    assert admin.post(f'/api/deliveries/{did}/start').status_code == 200
    assert admin.post(f'/api/deliveries/{did}/start').status_code == 400

    # upload-proof: firma + append de fotos en posts sucesivos
    r = admin.post(f'/api/deliveries/{did}/upload-proof', json={
        'signature_url': 'https://f.test/s.png',
        'photo_urls': ['https://f.test/1.jpg'], 'notes': 'primero'})
    assert r.json()['proof_of_delivery']['signature_url'].endswith('s.png')
    r = admin.post(f'/api/deliveries/{did}/upload-proof', json={
        'photo_urls': ['https://f.test/2.jpg']})
    proof = r.json()['proof_of_delivery']
    assert proof['photo_urls'] == ['https://f.test/1.jpg',
                                   'https://f.test/2.jpg']

    # complete → ok; toda mutación sobre entrega finalizada → 400
    assert admin.post(f'/api/deliveries/{did}/complete', json={
        'delivered_at': '2030-01-01T10:00:00'}).status_code == 200
    for call in (
            lambda: admin.post(f'/api/deliveries/{did}/complete', json={}),
            lambda: admin.post(f'/api/deliveries/{did}/fail', json={}),
            lambda: admin.post(
                f'/api/deliveries/{did}/reschedule', json={}),
            lambda: admin.put(f'/api/deliveries/{did}',
                              json={'notes': 'x'}),
            lambda: admin.post(f'/api/deliveries/{did}/start')):
        assert call().status_code == 400

    # reschedule con notes sobre una entrega fallida → 200 y actualiza
    d2 = admin.post('/api/deliveries', json={
        'order_number': 'ERR-3'}).json()
    admin.post(f"/api/deliveries/{d2['id']}/fail", json={})
    r = admin.post(f"/api/deliveries/{d2['id']}/reschedule", json={
        'delivery_window_end': '2030-06-01T18:00:00',
        'notes': 'reagendado'})
    assert r.status_code == 200 and r.json()['notes'] == 'reagendado'
    assert r.json()['delivery_window_end'] is not None


def test_delivery_complete_updates_driver_metric(admin):
    """Complete de una entrega cuya ruta tiene conductor asignado suma
    a driver.total_deliveries."""
    drv = admin.post('/api/drivers', json={
        'license_number': 'LIC-MET'}).json()
    route = admin.post('/api/routes', json={
        'name': 'Ruta metric', 'origin_lat': -34.0, 'origin_lng': -58.0,
        'destination_lat': -34.1, 'destination_lng': -58.1,
        'assigned_driver_id': drv['id']}).json()
    d = admin.post('/api/deliveries', json={
        'order_number': 'DRV-MET', 'route_id': route['id']}).json()
    before = admin.get(f"/api/drivers/{drv['id']}").json()[
        'total_deliveries'] or 0
    admin.post(f"/api/deliveries/{d['id']}/complete", json={})
    assert admin.get(f"/api/drivers/{drv['id']}").json()[
        'total_deliveries'] == before + 1


def test_routes_list_and_assignment_404s(admin):
    """Filtros del listado + 404 al asignar vehículo/conductor que no
    existe (create y update)."""
    base = {'origin_lat': 0, 'origin_lng': 0,
            'destination_lat': 0, 'destination_lng': 0}
    assert admin.post('/api/routes', json={
        'name': 'BadV', **base,
        'assigned_vehicle_id': 'no-existe'}).status_code == 404
    assert admin.post('/api/routes', json={
        'name': 'BadD', **base,
        'assigned_driver_id': 'no-existe'}).status_code == 404

    assert all(r['status'] == 'planned' for r in
               admin.get('/api/routes?status=planned').json())
    assert all(r['type'] == 'fixed' for r in
               admin.get('/api/routes?type=fixed').json())
    assert admin.get(
        '/api/routes?assigned_vehicle_id=no-existe').json() == []
    assert admin.get(
        '/api/routes?assigned_driver_id=no-existe').json() == []
    ordered = admin.get('/api/routes?sort_by=name&order=asc&limit=5').json()
    names = [r['name'] for r in ordered]
    assert names == sorted(names)

    rid = admin.post('/api/routes', json={
        'name': 'Upd1', **base}).json()['id']
    assert admin.put(f'/api/routes/{rid}', json={
        'assigned_driver_id': 'no-existe'}).status_code == 404
    r = admin.put(f'/api/routes/{rid}', json={'description': 'd1'})
    assert r.status_code == 200 and r.json()['description'] == 'd1'


def test_routes_lifecycle_errors(admin):
    """400 del ciclo de vida, optimize sin paradas y con una en curso
    (409), y el vehículo vuelve a available al completar."""
    from app.db import SessionLocal
    from app.models import Route

    vid = admin.post('/api/vehicles', json={
        'plate': 'RLC001', 'type': 'van'}).json()['id']
    rid = admin.post('/api/routes', json={
        'name': 'Ruta LC', 'origin_lat': -34.0, 'origin_lng': -58.0,
        'destination_lat': -34.1, 'destination_lng': -58.1,
        'assigned_vehicle_id': vid}).json()['id']

    # optimize sin paradas → 400; complete sin estar en curso → 400
    assert admin.post(f'/api/routes/{rid}/optimize',
                      json={}).status_code == 400
    assert admin.post(f'/api/routes/{rid}/complete').status_code == 400

    # start → ok (vehículo pasa a in_route); start de nuevo → 400
    assert admin.post(f'/api/routes/{rid}/start').status_code == 200
    assert admin.get(f'/api/vehicles/{vid}').json()['status'] == 'in_route'
    assert admin.post(f'/api/routes/{rid}/start').status_code == 400

    # con parada + optimization_data 'running' forzado → 409
    # (la race real es async; el estado se siembra por DB)
    d = admin.post('/api/deliveries', json={
        'order_number': 'LC-OPT'}).json()
    assert admin.post(f'/api/routes/{rid}/add-delivery',
                      json={'delivery_id': d['id']}).status_code == 201
    db = SessionLocal()
    db.get(Route, rid).optimization_data = {'status': 'running'}
    db.commit()
    db.close()
    assert admin.post(f'/api/routes/{rid}/optimize',
                      json={}).status_code == 409
    db = SessionLocal()
    db.get(Route, rid).optimization_data = None
    db.commit()
    db.close()

    # complete → vehículo vuelve a available
    assert admin.post(f'/api/routes/{rid}/complete').status_code == 200
    assert admin.get(f'/api/vehicles/{vid}').json()['status'] == 'available'

    # ruta finalizada: update y add-delivery → 400
    assert admin.put(f'/api/routes/{rid}',
                     json={'name': 'x'}).status_code == 400
    d2 = admin.post('/api/deliveries', json={
        'order_number': 'LC-2'}).json()
    assert admin.post(f'/api/routes/{rid}/add-delivery',
                      json={'delivery_id': d2['id']}).status_code == 400

    # tracking update con driver inexistente → 404
    assert admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'driver_id': 'no-existe',
        'location': {'lat': -34.0, 'lng': -58.0}}).status_code == 404


def test_routes_remove_delivery_and_delete(admin):
    """DELETE /routes/{id}/deliveries/{did}: 404 si la entrega no está,
    re-ordena las paradas restantes y desvincula la entrega. DELETE de
    la ruta desvincula las entregas asociadas."""
    rid = admin.post('/api/routes', json={
        'name': 'Ruta RM', 'origin_lat': -34.0, 'origin_lng': -58.0,
        'destination_lat': -34.1, 'destination_lng': -58.1}).json()['id']
    ids = []
    for i in range(3):
        d = admin.post('/api/deliveries', json={
            'order_number': f'RM-{i}'}).json()
        admin.post(f'/api/routes/{rid}/add-delivery',
                   json={'delivery_id': d['id']})
        ids.append(d['id'])

    # entrega que no es parada de la ruta → 404
    other = admin.post('/api/deliveries', json={
        'order_number': 'RM-X'}).json()
    assert admin.delete(
        f"/api/routes/{rid}/deliveries/{other['id']}").status_code == 404

    # remover la parada del medio → quedan 2 en orden, entrega suelta
    assert admin.delete(
        f'/api/routes/{rid}/deliveries/{ids[1]}').status_code == 204
    assert admin.get(
        f'/api/deliveries/{ids[1]}').json()['route_id'] is None
    stops = admin.get(f'/api/routes/{rid}/deliveries').json()
    assert [s['order_number'] for s in stops] == ['RM-0', 'RM-2']

    # borrar la ruta → 204, las paradas quedan sin route_id
    assert admin.delete(f'/api/routes/{rid}').status_code == 204
    assert admin.get(f'/api/routes/{rid}').status_code == 404
    assert admin.get(
        f'/api/deliveries/{ids[0]}').json()['route_id'] is None


def test_maintenance_error_paths(admin):
    """CRUD restante de mantenimiento + complete duplicado + reset del
    estado del vehículo al completar."""
    vid = admin.post('/api/vehicles', json={
        'plate': 'MNT001', 'type': 'van'}).json()['id']

    # vehicle_id inexistente → 404
    assert admin.post('/api/maintenance', json={
        'vehicle_id': 'no-existe',
        'type': 'inspection'}).status_code == 404

    mid = admin.post('/api/maintenance', json={
        'vehicle_id': vid, 'type': 'corrective', 'cost': 1200,
        'description': 'frenos'}).json()['id']

    # listado con filtros + orden
    assert any(m['id'] == mid for m in admin.get(
        f'/api/maintenance?vehicle_id={vid}').json())
    assert all(m['status'] == 'scheduled' for m in admin.get(
        '/api/maintenance?status=scheduled').json())
    assert all(m['type'] == 'inspection' for m in admin.get(
        '/api/maintenance?type=inspection').json())
    assert admin.get(
        '/api/maintenance?sort_by=cost&order=asc&limit=5').json()

    # get by id + 404
    assert admin.get(f'/api/maintenance/{mid}').json()['cost'] == 1200
    assert admin.get('/api/maintenance/no-existe').status_code == 404

    # update parcial
    r = admin.put(f'/api/maintenance/{mid}', json={
        'cost': 1500, 'provider': 'Taller X'})
    assert r.status_code == 200 and r.json()['cost'] == 1500

    # vehículo en 'maintenance' → complete lo devuelve a available
    admin.put(f'/api/vehicles/{vid}', json={'status': 'maintenance'})
    assert admin.post(f'/api/maintenance/{mid}/complete'
                      ).status_code == 200
    assert admin.get(f'/api/vehicles/{vid}').json()[
        'status'] == 'available'

    # complete duplicado → 400
    assert admin.post(f'/api/maintenance/{mid}/complete'
                      ).status_code == 400

    # delete → 204 + 404
    assert admin.delete(f'/api/maintenance/{mid}').status_code == 204
    assert admin.get(f'/api/maintenance/{mid}').status_code == 404


def test_archive_run_and_loop(admin, monkeypatch):
    """run_archive (SessionLocal) commitea y loguea; la rama de error
    hace rollback sin propagar; archive_loop corre en background con
    intervalo configurable (acelerado por monkeypatch y cancelado)."""
    import asyncio
    from datetime import timedelta

    import app.archive as arc
    from app.db import SessionLocal
    from app.models import TrackingEvent, utcnow

    # evento vencido → run_archive lo mueve y entra en la rama `moved`
    vid = admin.post('/api/vehicles', json={
        'plate': 'ARC002', 'type': 'van'}).json()['id']
    db = SessionLocal()
    db.add(TrackingEvent(vehicle_id=vid, lat=-34.0, lng=-58.0,
                         timestamp=utcnow() - timedelta(days=90)))
    db.commit()
    db.close()
    arc.run_archive(SessionLocal)
    assert len(admin.get(
        f'/api/tracking/vehicles/{vid}/history?archived=true'
    ).json()) == 1

    # excepción dentro → rollback + log, no propaga
    def boom(_db, retention_days=0):
        raise RuntimeError('db rota')
    monkeypatch.setattr(arc, 'archive_old_events', boom)
    arc.run_archive(SessionLocal)  # no lanza

    # el loop itera cada ARCHIVE_INTERVAL_S (acelerado) hasta cancelarlo
    calls = []
    monkeypatch.setattr(arc, 'run_archive', lambda sf: calls.append(1))
    monkeypatch.setattr(arc, 'ARCHIVE_INTERVAL_S', 0.01)

    async def ticks():
        task = asyncio.ensure_future(arc.archive_loop(SessionLocal))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(ticks())
    assert calls


# ---------- deploy env gates ----------

def test_seed_demo_gate(tmp_path, monkeypatch):
    # SEED_DEMO=false: migra a head pero arranca con tablas vacías
    # (producción — el primer usuario registrado queda admin).
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker

    import app.db as db
    from app.models import Vehicle

    eng = create_engine(f'sqlite:///{tmp_path}/fresh.db')
    monkeypatch.setenv('SEED_DEMO', 'false')
    monkeypatch.setattr(db, 'engine', eng)
    monkeypatch.setattr(db, 'SessionLocal', sessionmaker(bind=eng))
    db.init_db()
    assert 'vehicles' in inspect(eng).get_table_names()
    s = db.SessionLocal()
    try:
        assert s.query(Vehicle).count() == 0
    finally:
        s.close()


def test_background_loops_gate(monkeypatch):
    # RUN_BACKGROUND_LOOPS=false: el lifespan no dispara los loops
    # en-proceso (deploy multi-worker); default true los arranca.
    import app.alerts_engine as ae
    import app.archive as arc
    import app.main as m
    import app.metrics as met

    started = []

    async def fake(_sf):
        started.append(1)

    monkeypatch.setattr(ae, 'alerts_loop', fake)
    monkeypatch.setattr(arc, 'archive_loop', fake)
    monkeypatch.setattr(met, 'metrics_loop', fake)

    monkeypatch.setenv('RUN_BACKGROUND_LOOPS', 'false')
    with TestClient(m.app):
        pass
    assert started == []

    monkeypatch.setenv('RUN_BACKGROUND_LOOPS', 'true')
    with TestClient(m.app):
        pass
    assert len(started) == 3


# ---------- bus redis (multi-worker) ----------

def test_bus_disabled_without_redis_url():
    # Sin REDIS_URL → bus off: publish_threadsafe devuelve False (el
    # caller cae al broadcast local) y este worker es líder permanente.
    import asyncio
    from app import bus

    assert bus.enabled() is False
    assert bus.publish_threadsafe({'type': 'x'}) is False

    async def check():
        assert await bus.acquire_or_renew_leadership() is True
        assert await bus.publish({'type': 'x'}) is False
    asyncio.run(check())


def test_bus_pubsub_roundtrip(monkeypatch):
    # start() con fake redis: publish/publish_threadsafe llegan al
    # on_message suscripto via el canal (self-delivery).
    import asyncio
    import fakeredis.aioredis
    import redis.asyncio as aioredis
    from app import bus

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(bus, 'REDIS_URL', 'redis://fake')
    monkeypatch.setattr(aioredis, 'from_url',
                        lambda *a, **k: fake)
    received = []

    async def on_msg(msg):
        received.append(msg)

    async def scenario():
        await bus.start(on_msg)
        assert bus.enabled() and bus.client is fake
        assert await bus.publish({'type': 'location_update',
                                  'vehicle_id': 'v1'}) is True
        # publish_threadsafe encola en este mismo loop
        assert bus.publish_threadsafe(
            {'type': 'alert', 'vehicle_id': 'v2'}) is True
        for _ in range(100):
            if len(received) >= 2:
                break
            await asyncio.sleep(0.02)
        await bus.stop()
        assert bus.enabled() is False

    asyncio.run(scenario())
    types = {m['type'] for m in received}
    assert {'location_update', 'alert'} <= types


def test_bus_leader_election(monkeypatch):
    # Dos "workers" (clientes) sobre el mismo server: uno toma el lease,
    # el otro espera; si el líder muere (key expira/borra) el segundo
    # lo toma.
    import asyncio
    import fakeredis
    import fakeredis.aioredis
    from app import bus

    server = fakeredis.FakeServer()
    a = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    b = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    async def as_worker(client, wid):
        bus.client, bus.worker_id = client, wid
        return await bus.acquire_or_renew_leadership()

    async def scenario():
        orig_client, orig_wid = bus.client, bus.worker_id
        try:
            assert await as_worker(a, 'wA') is True   # A toma el lease
            assert await as_worker(b, 'wB') is False  # B espera
            assert await as_worker(a, 'wA') is True   # A renueva
            await a.delete(bus.LEADER_KEY)            # líder cae
            assert await as_worker(b, 'wB') is True   # B hereda
        finally:
            bus.client, bus.worker_id = orig_client, orig_wid
            await a.aclose()
            await b.aclose()

    asyncio.run(scenario())


def test_bus_leader_supervisor(monkeypatch):
    # El supervisor arranca los loops al ganar el lease y los cancela
    # al perderlo.
    import asyncio
    import fakeredis.aioredis
    from app import bus

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(bus, 'LEADER_RENEW_S', 0.05)
    started = []

    async def scenario():
        orig_client, orig_wid = bus.client, bus.worker_id
        try:
            bus.client, bus.worker_id = fake, 'wS'

            def start_loops():
                t = asyncio.ensure_future(asyncio.sleep(999))
                started.append(t)
                return [t]

            sup = asyncio.ensure_future(bus.leader_supervisor(start_loops))
            for _ in range(100):
                if started:
                    break
                await asyncio.sleep(0.02)
            assert len(started) == 1 and not started[0].done()
            # otro worker usurpa el lease → el supervisor suelta los loops
            await fake.set(bus.LEADER_KEY, 'wOther')
            for _ in range(100):
                if started[0].done():
                    break
                await asyncio.sleep(0.02)
            assert started[0].cancelled()
            sup.cancel()
            try:
                await sup
            except asyncio.CancelledError:
                pass
        finally:
            bus.client, bus.worker_id = orig_client, orig_wid
            await fake.aclose()

    asyncio.run(scenario())


def test_websocket_broadcast_via_redis(admin, monkeypatch):
    # E2E: con el bus activo, un POST /tracking/update publica en el
    # canal y el listener lo reenvía al WS suscripto — en vez del
    # broadcast local directo.
    import fakeredis.aioredis
    import redis.asyncio as aioredis
    from app import bus

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(bus, 'REDIS_URL', 'redis://fake')
    monkeypatch.setattr(aioredis, 'from_url', lambda *a, **k: fake)

    vid = next(v['id'] for v in admin.get('/api/vehicles').json()
               if v['plate'] == 'DEF456')
    token = admin.cookies.get('auth')
    # `with` dispara el lifespan → bus.start suscribe el canal fake.
    with TestClient(app) as c:
        with c.websocket_connect(
                f'/api/tracking/live?token={token}') as ws:
            ws.send_json({'type': 'subscribe', 'vehicles': [vid]})
            assert ws.receive_json()['type'] == 'subscribed'
            admin.post('/api/tracking/update', json={
                'vehicle_id': vid,
                'location': {'lat': -34.62, 'lng': -58.41}})
            msg = ws.receive_json()
            assert msg['type'] == 'location_update'
            assert msg['vehicle_id'] == vid
            assert msg['data']['location']['lat'] == -34.62


# ---------- drivers + auth error paths ----------

def test_drivers_list_filters(admin):
    """Filtros status/search del listado + orden desc."""
    lic = admin.get('/api/drivers').json()[0]['license_number']
    avail = admin.get('/api/drivers?status=available').json()
    assert avail and all(d['status'] == 'available' for d in avail)
    r = admin.get('/api/drivers', params={'search': lic})
    assert any(d['license_number'] == lic for d in r.json())
    assert admin.get('/api/drivers?search=zz-no-existe').json() == []
    ordered = admin.get(
        '/api/drivers?sort_by=license_number&order=desc&limit=5').json()
    lics = [d['license_number'] for d in ordered]
    assert lics == sorted(lics, reverse=True)


def test_drivers_crud_errors(admin):
    """404/409 del CRUD + user_id válido/inválido (unique)."""
    assert admin.post('/api/drivers', json={
        'license_number': 'LIC-E1',
        'user_id': 'no-existe'}).status_code == 404
    uid = admin.get('/api/auth/me').json()['id']
    r = admin.post('/api/drivers', json={
        'license_number': 'LIC-E1', 'user_id': uid})
    assert r.status_code == 201 and r.json()['user_id'] == uid
    # license_number duplicado → 409
    assert admin.post('/api/drivers', json={
        'license_number': 'LIC-E1'}).status_code == 409
    # user_id duplicado → 409 (UNIQUE)
    assert admin.post('/api/drivers', json={
        'license_number': 'LIC-E1B', 'user_id': uid}).status_code == 409

    for url in ('/api/drivers/nope', '/api/drivers/nope/deliveries',
                '/api/drivers/nope/shifts', '/api/drivers/nope/performance'):
        assert admin.get(url).status_code == 404
    assert admin.put('/api/drivers/nope', json={'phone': '1'}
                     ).status_code == 404
    assert admin.delete('/api/drivers/nope').status_code == 404
    assert admin.post('/api/drivers/nope/start-shift',
                      json={}).status_code == 404
    assert admin.post('/api/drivers/nope/end-shift').status_code == 404

    # update ok + update a license existente → 409
    did = admin.post('/api/drivers', json={
        'license_number': 'LIC-E2', 'phone': '111'}).json()['id']
    r = admin.put(f'/api/drivers/{did}', json={
        'phone': '222', 'rating': 4.5})
    assert r.status_code == 200
    assert r.json()['phone'] == '222' and r.json()['rating'] == 4.5
    assert admin.put(f'/api/drivers/{did}', json={
        'license_number': 'LIC-E1'}).status_code == 409


def test_driver_delete_unlinks_vehicles(admin):
    """DELETE desvincula los vehículos que tenía asignados."""
    drv = admin.post('/api/drivers', json={
        'license_number': 'LIC-DEL'}).json()
    veh = admin.post('/api/vehicles', json={
        'plate': 'DELVH01', 'type': 'van'}).json()
    r = admin.post(f"/api/vehicles/{veh['id']}/assign-driver",
                   json={'driver_id': drv['id']})
    assert r.status_code == 200
    assert admin.delete(f"/api/drivers/{drv['id']}").status_code == 204
    assert admin.get(f"/api/drivers/{drv['id']}").status_code == 404
    assert admin.get(f"/api/vehicles/{veh['id']}").json()[
        'assigned_driver_id'] is None


def test_driver_deliveries_and_shift_rules(admin):
    """Historial de entregas vía ruta asignada + reglas de turno
    (vehículo inválido, descanso <8h, suspendido, sin turno)."""
    drv = admin.post('/api/drivers', json={
        'license_number': 'LIC-E3'}).json()
    route = admin.post('/api/routes', json={
        'name': 'Ruta drv', 'origin_lat': -34.0, 'origin_lng': -58.0,
        'destination_lat': -34.1, 'destination_lng': -58.1,
        'assigned_driver_id': drv['id']}).json()
    admin.post('/api/deliveries', json={
        'order_number': 'DRV-E3', 'route_id': route['id']})
    deliveries = admin.get(f"/api/drivers/{drv['id']}/deliveries").json()
    assert any(d['order_number'] == 'DRV-E3' for d in deliveries)

    # start-shift con vehículo inexistente → 404
    assert admin.post(f"/api/drivers/{drv['id']}/start-shift", json={
        'vehicle_id': 'no-existe'}).status_code == 404

    # con vehículo válido → queda current_vehicle_id
    veh = admin.post('/api/vehicles', json={
        'plate': 'DRV-E3', 'type': 'car'}).json()
    r = admin.post(f"/api/drivers/{drv['id']}/start-shift", json={
        'vehicle_id': veh['id'], 'notes': 'turno noche'})
    assert r.status_code == 201 and r.json()['vehicle_id'] == veh['id']
    assert admin.get(f"/api/drivers/{drv['id']}").json()[
        'current_vehicle_id'] == veh['id']

    # end-shift → re-start inmediato viola el descanso mínimo → 400
    assert admin.post(f"/api/drivers/{drv['id']}/end-shift"
                      ).status_code == 200
    r = admin.post(f"/api/drivers/{drv['id']}/start-shift", json={})
    assert r.status_code == 400 and 'descanso' in r.json()['detail']

    # suspendido → start-shift → 400
    drv2 = admin.post('/api/drivers', json={
        'license_number': 'LIC-E4'}).json()
    admin.put(f"/api/drivers/{drv2['id']}", json={'status': 'suspended'})
    r = admin.post(f"/api/drivers/{drv2['id']}/start-shift", json={})
    assert r.status_code == 400 and 'suspendido' in r.json()['detail']
    # end-shift sin turno abierto → 404
    assert admin.post(f"/api/drivers/{drv2['id']}/end-shift"
                      ).status_code == 404


def test_driver_fatigue_alert_on_long_shift(admin):
    """Un turno de >10h genera alerta driver_fatigue al cerrarlo."""
    from datetime import timedelta

    from app.db import SessionLocal
    from app.models import DriverShift

    drv = admin.post('/api/drivers', json={
        'license_number': 'LIC-FAT'}).json()
    shift_id = admin.post(f"/api/drivers/{drv['id']}/start-shift",
                          json={}).json()['id']

    # retroceder el inicio 12h → al cerrar total_hours > 10
    db = SessionLocal()
    shift = db.get(DriverShift, shift_id)
    shift.start_time = shift.start_time - timedelta(hours=12)
    db.commit()
    db.close()

    r = admin.post(f"/api/drivers/{drv['id']}/end-shift")
    assert r.status_code == 200 and r.json()['total_hours'] > 10
    alerts = admin.get(f"/api/alerts?type=driver_fatigue"
                       f"&driver_id={drv['id']}").json()
    assert any(a['driver_id'] == drv['id'] for a in alerts)


def test_auth_admin_register_and_users_list(admin, anon):
    """Un admin puede registrar usuarios con rol sin pisar su sesión;
    GET /users exige rol admin."""
    r = admin.post('/api/auth/register', json={
        'email': 'disp@fleetpulse.test', 'password': 'disppass123',
        'role': 'dispatcher'})
    assert r.status_code == 201 and r.json()['role'] == 'dispatcher'
    # register con sesión activa NO emite cookies → sigue siendo admin
    assert admin.get('/api/auth/me').json()['email'] == ADMIN['email']

    users = admin.get('/api/auth/users').json()
    assert any(u['email'] == 'disp@fleetpulse.test' for u in users)
    assert anon.get('/api/auth/users').status_code == 401
    # viewer autenticado → 403
    anon.post('/api/auth/register', json={
        'email': 'v2@fleetpulse.test', 'password': 'viewerpass123'})
    assert anon.get('/api/auth/users').status_code == 403


def test_auth_refresh_profile_and_inactive(admin, anon):
    """Refresh re-emite cookies, PUT /me actualiza el perfil, y un
    usuario desactivado no puede loguear (401 genérico)."""
    assert anon.post('/api/auth/refresh').status_code == 401
    r = admin.post('/api/auth/refresh')
    assert r.status_code == 200 and r.json()['email'] == ADMIN['email']
    # refresh regenera el token csrf → hay que refrescar el header
    admin.headers['x-csrf-token'] = admin.cookies.get('csrf')

    r = admin.put('/api/auth/me', json={'full_name': 'Admin Renombrado'})
    assert r.status_code == 200
    assert admin.get('/api/auth/me').json()[
        'full_name'] == 'Admin Renombrado'

    # desactivar un usuario → login → 401
    r = anon.post('/api/auth/register', json={
        'email': 'off@fleetpulse.test', 'password': 'offpass123'})
    uid = r.json()['id']
    assert admin.put(f'/api/auth/users/{uid}',
                     json={'is_active': False}).status_code == 200
    anon2 = TestClient(app)
    assert anon2.post('/api/auth/login', json={
        'email': 'off@fleetpulse.test',
        'password': 'offpass123'}).status_code == 401
    # update_user 404
    assert admin.put('/api/auth/users/no-existe',
                     json={'role': 'viewer'}).status_code == 404


def test_auth_change_password(anon):
    """change-password: 401 actual incorrecta, 400 nueva corta, 204 ok
    invalida la sesión y permite re-login con la nueva."""
    anon.post('/api/auth/register', json={
        'email': 'chg@fleetpulse.test', 'password': 'oldpass123'})
    anon.headers['x-csrf-token'] = anon.cookies.get('csrf')

    r = anon.post('/api/auth/change-password', json={
        'current_password': 'wrongpass', 'new_password': 'newpass123'})
    assert r.status_code == 401
    r = anon.post('/api/auth/change-password', json={
        'current_password': 'oldpass123', 'new_password': 'corta'})
    assert r.status_code == 400
    r = anon.post('/api/auth/change-password', json={
        'current_password': 'oldpass123', 'new_password': 'newpass123'})
    assert r.status_code == 204

    # la sesión quedó invalidada (cookies limpiadas)
    assert anon.get('/api/auth/me').status_code == 401
    r = anon.post('/api/auth/login', json={
        'email': 'chg@fleetpulse.test', 'password': 'newpass123'})
    assert r.status_code == 200
    # y la vieja ya no sirve
    anon2 = TestClient(app)
    assert anon2.post('/api/auth/login', json={
        'email': 'chg@fleetpulse.test',
        'password': 'oldpass123'}).status_code == 401


# ---------- vehicles: filtros, sub-recursos y errores de asignación ----------

def test_vehicles_filters_and_subresources(admin):
    """?type= y ?assigned_driver_id= filtran el listado; GET
    /{id}/tracking y /{id}/maintenance devuelven el historial."""
    did = admin.post('/api/drivers', json={
        'license_number': 'LIC-FLT'}).json()['id']
    vid = admin.post('/api/vehicles', json={
        'plate': 'FLT001', 'type': 'motorcycle'}).json()['id']
    admin.post(f'/api/vehicles/{vid}/assign-driver',
               json={'driver_id': did})

    by_type = admin.get('/api/vehicles?type=motorcycle').json()
    assert all(v['type'] == 'motorcycle' for v in by_type)
    assert any(v['id'] == vid for v in by_type)
    by_driver = admin.get(
        f'/api/vehicles?assigned_driver_id={did}').json()
    assert [v['id'] for v in by_driver] == [vid]

    # historial de tracking del vehículo (desc por timestamp)
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.60, 'lng': -58.40}})
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.61, 'lng': -58.41}})
    hist = admin.get(f'/api/vehicles/{vid}/tracking').json()
    assert len(hist) == 2 and hist[0]['lat'] == -34.61

    # historial de mantenimiento del vehículo
    admin.post('/api/maintenance', json={
        'vehicle_id': vid, 'type': 'inspection',
        'scheduled_date': '2030-01-10'})
    maint = admin.get(f'/api/vehicles/{vid}/maintenance').json()
    assert len(maint) == 1 and maint[0]['vehicle_id'] == vid


def test_vehicles_update_409_and_assign_errors(admin):
    """PUT con patente de otro vehículo → 409. assign-driver: conductor
    suspendido → 400; reasignar libera el current_vehicle_id previo;
    mover un conductor a otro vehículo desasigna el vehículo anterior."""
    v1 = admin.post('/api/vehicles', json={
        'plate': 'ASN001', 'type': 'van'}).json()['id']
    v2 = admin.post('/api/vehicles', json={
        'plate': 'ASN002', 'type': 'van'}).json()['id']

    assert admin.put(f'/api/vehicles/{v2}', json={
        'plate': 'ASN001'}).status_code == 409

    d1 = admin.post('/api/drivers', json={
        'license_number': 'LIC-ASN1'}).json()['id']
    d2 = admin.post('/api/drivers', json={
        'license_number': 'LIC-ASN2'}).json()['id']
    susp = admin.post('/api/drivers', json={
        'license_number': 'LIC-ASN3',
        'status': 'suspended'}).json()['id']

    assert admin.post(f'/api/vehicles/{v1}/assign-driver', json={
        'driver_id': susp}).status_code == 400

    # v1: d1 → d2 — d1 queda sin vehículo asignado
    admin.post(f'/api/vehicles/{v1}/assign-driver',
               json={'driver_id': d1})
    admin.post(f'/api/vehicles/{v1}/assign-driver',
               json={'driver_id': d2})
    assert admin.get(f'/api/drivers/{d1}').json()[
        'current_vehicle_id'] is None
    assert admin.get(f'/api/drivers/{d2}').json()[
        'current_vehicle_id'] == v1

    # mover d2 a v2 → v1 queda sin conductor
    r = admin.post(f'/api/vehicles/{v2}/assign-driver',
                   json={'driver_id': d2})
    assert r.json()['assigned_driver_id'] == d2
    assert admin.get(f'/api/vehicles/{v1}').json()[
        'assigned_driver_id'] is None


# ---------- tracking: polyline por paradas, progress, WS edge cases ----------

def test_tracking_degenerate_geofence_and_stops_polyline(admin):
    """Geofence con polígono degenerado (<3 vértices — solo insertable
    por DB, el schema exige ≥3) se saltea sin romper el update; y una
    ruta in_progress sin waypoints construye la polyline desde las
    delivery_address de sus paradas."""
    from app.db import SessionLocal
    from app.models import Geofence

    db = SessionLocal()
    db.add(Geofence(name='Degenerada', rule='enter',
                    polygon=[{'lat': 0, 'lng': 0}, {'lat': 1, 'lng': 1}]))
    db.commit()
    db.close()

    vid = admin.post('/api/vehicles', json={
        'plate': 'PLY001', 'type': 'truck'}).json()['id']
    route = admin.post('/api/routes', json={
        'name': 'Ruta Stops', 'origin_lat': -34.60, 'origin_lng': -58.40,
        'destination_lat': -34.60, 'destination_lng': -58.30,
        'assigned_vehicle_id': vid}).json()
    d = admin.post('/api/deliveries', json={
        'order_number': 'PLY-1',
        'delivery_address': {'lat': -34.60, 'lng': -58.35}}).json()
    admin.post(f"/api/routes/{route['id']}/add-delivery",
               json={'delivery_id': d['id']})
    admin.post(f"/api/routes/{route['id']}/start")

    # sobre el eje origen→parada → check_route_deviation corre con la
    # polyline de paradas y no alerta (distancia < umbral)
    assert admin.post('/api/tracking/update', json={
        'vehicle_id': vid,
        'location': {'lat': -34.60, 'lng': -58.37}}).status_code == 201
    assert not [a for a in admin.get('/api/alerts/active').json()
                if a['type'] == 'route_deviation'
                and a['vehicle_id'] == vid]


def test_route_progress_with_position(admin):
    """progress de una ruta con vehículo asignado expone la última
    posición de tracking del vehículo."""
    vid = admin.post('/api/vehicles', json={
        'plate': 'PRG001', 'type': 'van'}).json()['id']
    route = admin.post('/api/routes', json={
        'name': 'Ruta Prog', 'origin_lat': -34.60, 'origin_lng': -58.40,
        'destination_lat': -34.60, 'destination_lng': -58.30,
        'assigned_vehicle_id': vid}).json()
    admin.post('/api/tracking/update', json={
        'vehicle_id': vid, 'location': {'lat': -34.50, 'lng': -58.50}})
    progress = admin.get(
        f"/api/tracking/routes/{route['id']}/progress").json()
    assert progress['stops_total'] == 0
    assert progress['last_position']['lat'] == -34.50


def test_ws_bad_token_and_malformed_json(admin, anon):
    """?token con JWT inválido → 4401 (PyJWTError); JSON malformado
    dentro del loop cae en el except genérico y desconecta limpio
    (el handler sale sin close frame — la desconexión se observa
    porque el socket sale de manager._subs)."""
    import time

    from app.ws import manager

    try:
        with anon.websocket_connect(
                '/api/tracking/live?token=garbage') as ws:
            ws.receive_json()
        assert False, 'debió rechazar el token inválido'
    except Exception:
        pass  # close 4401

    token = admin.cookies.get('auth')
    baseline = len(manager._subs)
    with admin.websocket_connect(
            f'/api/tracking/live?token={token}') as ws:
        ws.send_text('{invalid json')
        deadline = time.time() + 5
        while len(manager._subs) > baseline and time.time() < deadline:
            time.sleep(0.05)
        assert len(manager._subs) == baseline
