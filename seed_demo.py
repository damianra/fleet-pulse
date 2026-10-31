"""Seed demo FleetPulse — puebla la DB del .env con datos realistas.

Uso:
    .venv/bin/python seed_demo.py
    .venv/bin/python seed_demo.py --vehicles 40 --drivers 30 --routes 60 --deliveries 150

Aditivo e idempotente en usuarios (emails únicos): los usuarios demo se
saltan si ya existen; el resto appendea cada corrida. Requiere `faker`
(pip install faker — dev-only, no va en requirements).

Usuarios demo (password demo1234, admin viene del bootstrap):
    dispatcher@fleetpulse.dev · driver@fleetpulse.dev · viewer@fleetpulse.dev
"""
import argparse
import random
from datetime import date, datetime, timedelta

import faker
from dotenv import load_dotenv

load_dotenv()

from app.db import SessionLocal
from app.models import (Alert, Delivery, Driver, DriverShift, Geofence,
                        MaintenanceRecord, Route, RouteDelivery,
                        TrackingEvent, User, Vehicle, new_id, utcnow)
from app.security import hash_password

fake = faker.Faker('es_AR')
random.seed(42)

DEMO_USERS = [
    ('dispatcher@fleetpulse.dev', 'dispatcher', 'Demo Dispatcher'),
    ('driver@fleetpulse.dev', 'driver', 'Demo Driver'),
    ('viewer@fleetpulse.dev', 'viewer', 'Demo Viewer'),
]

BASE_LAT, BASE_LNG, SPREAD = -34.6037, -58.3816, 0.5
VEHICLE_TYPES = ['truck', 'van', 'car', 'motorcycle']
V_W = [0.3, 0.5, 0.15, 0.05]
FUEL = ['diesel', 'gasoline', 'electric', 'hybrid']
BRANDS = {'truck': ['Mercedes-Benz', 'Volvo', 'Scania', 'IVECO'],
          'van': ['Ford', 'Fiat', 'Renault', 'Volkswagen'],
          'car': ['Toyota', 'Honda', 'Chevrolet'],
          'motorcycle': ['Honda', 'Yamaha', 'Suzuki']}
DEL_STATUS = ['pending', 'in_transit', 'delivered', 'failed', 'rescheduled']
DEL_W = [0.15, 0.2, 0.5, 0.1, 0.05]
ALERT_TYPES = ['sla_breach', 'route_deviation', 'maintenance_due',
               'driver_fatigue', 'geofence_violation', 'speed_violation']
ALERT_TITLES = {'sla_breach': 'SLA de entrega vencido',
                'route_deviation': 'Desvío de ruta detectado',
                'maintenance_due': 'Mantenimiento preventivo vencido',
                'driver_fatigue': 'Conductor excedió horas de manejo',
                'geofence_violation': 'Violación de geocerca',
                'speed_violation': 'Exceso de velocidad detectado'}
MAINT_DESC = {'preventive': ['Cambio de aceite', 'Revisión de frenos', 'Rotación de neumáticos'],
              'corrective': ['Reparación de motor', 'Cambio de batería', 'Sistema eléctrico'],
              'inspection': ['Verificación técnica', 'Control de emisiones']}


def loc(spread=SPREAD):
    return BASE_LAT + random.uniform(-spread, spread), BASE_LNG + random.uniform(-spread, spread)


def past(days=30):
    return utcnow() - timedelta(days=random.randint(0, days),
                                hours=random.randint(0, 23), minutes=random.randint(0, 59))


def future(days=14):
    return utcnow() + timedelta(days=random.randint(0, days), hours=random.randint(0, 12))


def plate(i):
    return f'DEMO{i:05d}'  # único determinista por corrida


def phone():
    return f'+54 9 {random.randint(11, 99)} {random.randint(1000, 9999)}-{random.randint(1000, 9999)}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vehicles', type=int, default=30)
    ap.add_argument('--drivers', type=int, default=30)
    ap.add_argument('--routes', type=int, default=60)
    ap.add_argument('--deliveries', type=int, default=150)
    ap.add_argument('--tracking', type=int, default=80, help='eventos por vehículo in_route')
    ap.add_argument('--alerts', type=int, default=40)
    ap.add_argument('--maintenance', type=int, default=30)
    args = ap.parse_args()
    db = SessionLocal()
    try:
        # ---- Usuarios demo (1 por rol; admin viene del bootstrap) ----
        admin = db.query(User).filter_by(role='admin').first()
        for email, role, name in DEMO_USERS:
            if not db.query(User).filter_by(email=email).first():
                db.add(User(id=new_id(), email=email,
                            hashed_password=hash_password('demo1234'),
                            full_name=name, role=role,
                            last_login=past(10), created_at=past(180)))
        db.commit()
        n_users = db.query(User).count()
        print(f'users: {n_users} total (demo por rol OK)')

        user_ids = [u.id for u in db.query(User).all()]
        admin_id = admin.id if admin else user_ids[0]

        # ---- Vehículos ----
        vehicles = []
        for i in range(args.vehicles):
            t = random.choices(VEHICLE_TYPES, weights=V_W, k=1)[0]
            in_route = random.random() < 0.4
            lat, lng = loc() if in_route else (None, None)
            cap = {'truck': (5000, 20000, 20, 80), 'van': (800, 3000, 4, 15),
                   'car': (200, 800, 1, 3), 'motorcycle': (20, 100, 0, 0)}[t]
            v = Vehicle(id=new_id(), plate=plate(i), type=t,
                        brand=random.choice(BRANDS[t]), model=fake.word().capitalize(),
                        year=random.randint(2016, 2025),
                        capacity_kg=random.randint(cap[0], cap[1]),
                        capacity_m3=random.randint(cap[2], cap[3]),
                        fuel_type=random.choice(FUEL),
                        status='in_route' if in_route else random.choice(
                            ['available', 'available', 'maintenance', 'out_of_service']),
                        lat=lat, lng=lng,
                        last_location_update=utcnow() - timedelta(minutes=random.randint(0, 60)) if in_route else None,
                        mileage=random.randint(5000, 300000), created_at=past(365))
            vehicles.append(v)
        db.add_all(vehicles)
        db.commit()

        # ---- Drivers (1 user rol driver c/u — user_id es unique) ----
        drivers = []
        for i in range(args.drivers):
            u = User(id=new_id(), email=f'driver{i + 1:03d}@fleetpulse.dev',
                     hashed_password=hash_password('demo1234'),
                     full_name=fake.name(), role='driver', created_at=past(365))
            db.add(u)
            db.flush()
            d = Driver(id=new_id(), user_id=u.id,
                       license_number=f'LIC-{i + 1:06d}',
                       license_type=random.choice(['B', 'C', 'D']),
                       license_expiration=date.today() + timedelta(days=random.randint(30, 1500)),
                       phone=phone(),
                       emergency_contact={'name': fake.name(), 'phone': phone(),
                                          'relationship': random.choice(['Esposo/a', 'Padre/Madre', 'Hijo/a'])},
                       certifications=[{'name': 'Manejo defensivo',
                                        'expiration_date': future(400).isoformat()}],
                       rating=round(random.uniform(3.5, 5.0), 2),
                       total_deliveries=random.randint(50, 4000),
                       status=random.choices(['available', 'on_duty', 'off_duty', 'suspended'],
                                             weights=[0.3, 0.45, 0.2, 0.05], k=1)[0],
                       shift_start=f'{random.randint(6, 10):02d}:00',
                       shift_end=f'{random.randint(16, 22):02d}:00',
                       created_at=past(365))
            drivers.append(d)
        db.add_all(drivers)
        db.commit()

        # Asignación 1:1 driver on_duty/available ↔ vehículo
        active = [d for d in drivers if d.status in ('on_duty', 'available')]
        free_v = [v for v in vehicles if v.status in ('available', 'in_route')]
        for d, v in zip(active, free_v):
            d.current_vehicle_id = v.id
            v.assigned_driver_id = d.id
        db.commit()
        print(f'vehicles: +{len(vehicles)} · drivers: +{len(drivers)} ({min(len(active), len(free_v))} asignados)')

        # ---- Rutas ----
        routes = []
        for i in range(args.routes):
            olat, olng = loc()
            dlat, dlng = loc()
            st = random.choices(['planned', 'in_progress', 'completed', 'cancelled'],
                                weights=[0.2, 0.3, 0.45, 0.05], k=1)[0]
            dist = random.randint(40, 700)
            dur = int(dist * random.uniform(1.2, 2.5))
            ps = past(30) if st != 'planned' else future(7)
            r = Route(id=new_id(), name=f'Ruta {fake.city()} - {fake.city()}',
                      description=fake.sentence(), type=random.choice(['fixed', 'dynamic', 'optimized']),
                      origin_lat=olat, origin_lng=olng,
                      destination_lat=dlat, destination_lng=dlng,
                      waypoints=[{'lat': olat + (dlat - olat) * (k + 1) / 6 + random.uniform(-0.03, 0.03),
                                  'lng': olng + (dlng - olng) * (k + 1) / 6 + random.uniform(-0.03, 0.03),
                                  'order': k + 1, 'address': fake.address()} for k in range(5)],
                      total_distance_km=dist, estimated_duration_minutes=dur, status=st,
                      assigned_vehicle_id=random.choice(free_v).id if st in ('in_progress', 'completed') and free_v else None,
                      assigned_driver_id=random.choice(active).id if st in ('in_progress', 'completed') and active else None,
                      planned_start=ps, planned_end=ps + timedelta(minutes=dur),
                      actual_start=ps + timedelta(minutes=random.randint(-30, 30)) if st in ('in_progress', 'completed') else None,
                      actual_end=(ps + timedelta(minutes=dur + random.randint(-60, 120))) if st == 'completed' else None,
                      optimization_data={'algorithm': random.choice(['genetic', 'nearest_neighbor']),
                                         'result': {'improvement_percentage': random.randint(5, 35)}}
                      if random.random() > 0.3 else None,
                      created_at=past(60))
            routes.append(r)
        db.add_all(routes)
        db.commit()
        route_ids = [r.id for r in routes]
        print(f'routes: +{len(routes)}')

        # ---- Entregas + route_deliveries ----
        deliveries = []
        for i in range(args.deliveries):
            st = random.choices(DEL_STATUS, weights=DEL_W, k=1)[0]
            prio = random.choices(['low', 'medium', 'high', 'urgent'],
                                  weights=[0.3, 0.4, 0.2, 0.1], k=1)[0]
            dws = past(30) if st != 'pending' else future(7)
            sla = dws + timedelta(hours={'low': 48, 'medium': 24, 'high': 12, 'urgent': 4}[prio])
            adt = dws + timedelta(minutes=random.randint(-30, 180)) if st == 'delivered' else None
            d = Delivery(id=new_id(),
                         route_id=random.choice(route_ids) if random.random() > 0.2 else None,
                         order_number=f'ORD-{i + 1:06d}',
                         customer_name=fake.name(), customer_phone=phone(),
                         customer_email=fake.email(),
                         delivery_address={'street': fake.street_address(), 'city': fake.city(),
                                           'state': 'BA', 'zip': fake.postcode(),
                                           'lat': BASE_LAT + random.uniform(-SPREAD, SPREAD),
                                           'lng': BASE_LNG + random.uniform(-SPREAD, SPREAD)},
                         delivery_window_start=dws,
                         delivery_window_end=dws + timedelta(hours=random.randint(2, 8)),
                         priority=prio, status=st,
                         packages=[{'weight': round(random.uniform(0.5, 50), 2),
                                    'description': fake.word().capitalize(),
                                    'barcode': ''.join(random.choices('0123456789', k=13))}
                                   for _ in range(random.randint(1, 4))],
                         special_instructions=fake.sentence() if random.random() > 0.7 else None,
                         required_signature=random.random() > 0.3,
                         proof_of_delivery={'signature_url': f'https://storage.fleetpulse.dev/sig/{new_id()}.png',
                                            'delivered_at': adt.isoformat()} if st == 'delivered' else None,
                         sla_deadline=sla, actual_delivery_time=adt,
                         created_at=past(60))
            deliveries.append(d)
        db.add_all(deliveries)
        db.commit()
        # route_deliveries: paradas ordenadas por ruta
        by_route = {}
        for d in deliveries:
            if d.route_id:
                by_route.setdefault(d.route_id, []).append(d)
        for rid, ds in by_route.items():
            for order, d in enumerate(ds, 1):
                db.add(RouteDelivery(route_id=rid, delivery_id=d.id, stop_order=order,
                                     estimated_arrival=d.delivery_window_start,
                                     actual_arrival=d.actual_delivery_time))
        db.commit()
        print(f'deliveries: +{len(deliveries)} (route_deliveries: {sum(len(v) for v in by_route.values())})')

        # ---- Tracking events (vehículos in_route) ----
        moving = [v for v in vehicles if v.status == 'in_route']
        count = 0
        for v in moving:
            t0 = utcnow() - timedelta(hours=8)
            for i in range(args.tracking):
                lat, lng = loc(0.2)
                db.add(TrackingEvent(id=new_id(), vehicle_id=v.id,
                                     driver_id=v.assigned_driver_id, lat=lat, lng=lng,
                                     speed_kmh=round(random.uniform(0, 110), 1),
                                     heading=round(random.uniform(0, 360), 1),
                                     timestamp=t0 + timedelta(minutes=i * 5),
                                     accuracy_meters=round(random.uniform(2, 20), 1),
                                     battery_level=random.randint(20, 100),
                                     engine_status=random.choice(['on', 'on', 'idle']),
                                     fuel_level=round(random.uniform(15, 100), 1),
                                     event_metadata={'source': random.choice(['mobile_app', 'gps_device'])}))
                count += 1
            db.commit()
        print(f'tracking_events: +{count} ({len(moving)} vehículos)')

        # ---- Alertas (ack/resolved por el admin real — FK users) ----
        alerts = []
        for _ in range(args.alerts):
            t = random.choice(ALERT_TYPES)
            st = random.choices(['active', 'acknowledged', 'resolved'],
                                weights=[0.4, 0.3, 0.3], k=1)[0]
            ta = past(30)
            a = Alert(id=new_id(), type=t, severity=random.choices(
                        ['low', 'medium', 'high', 'critical'], weights=[0.3, 0.4, 0.2, 0.1], k=1)[0],
                      title=ALERT_TITLES[t], description=fake.sentence(), status=st,
                      vehicle_id=random.choice(vehicles).id if random.random() > 0.2 else None,
                      driver_id=random.choice(drivers).id if random.random() > 0.3 else None,
                      route_id=random.choice(route_ids) if random.random() > 0.5 else None,
                      delivery_id=random.choice(deliveries).id if random.random() > 0.6 else None,
                      triggered_at=ta,
                      acknowledged_at=ta + timedelta(minutes=random.randint(5, 120)) if st != 'active' else None,
                      acknowledged_by=admin_id if st != 'active' else None,
                      resolved_at=ta + timedelta(hours=random.randint(1, 48)) if st == 'resolved' else None,
                      resolved_by=admin_id if st == 'resolved' else None,
                      resolution_notes=fake.sentence() if st == 'resolved' else None,
                      alert_metadata={'auto_generated': True})
            alerts.append(a)
        db.add_all(alerts)
        db.commit()
        print(f'alerts: +{len(alerts)}')

        # ---- Mantenimiento ----
        maint = []
        for _ in range(args.maintenance):
            t = random.choice(list(MAINT_DESC))
            st = random.choices(['scheduled', 'in_progress', 'completed', 'cancelled'],
                                weights=[0.2, 0.1, 0.65, 0.05], k=1)[0]
            sd = (past(90).date() if st != 'scheduled' else future(30).date())
            maint.append(MaintenanceRecord(
                id=new_id(), vehicle_id=random.choice(vehicles).id, type=t,
                description=random.choice(MAINT_DESC[t]),
                scheduled_date=sd,
                completed_date=sd + timedelta(days=random.randint(0, 5)) if st == 'completed' else None,
                cost=round(random.uniform(50, 5000), 2) if st == 'completed' else None,
                provider=fake.company(), mileage_at_service=random.randint(10000, 300000),
                next_service_date=(date.today() + timedelta(days=random.randint(60, 300))) if st == 'completed' else None,
                status=st, documents=[], created_at=past(180)))
        db.add_all(maint)
        db.commit()
        print(f'maintenance_records: +{len(maint)}')

        # ---- Geocercas (CABA) ----
        for name, c in [('Microcentro', (-34.605, -58.375)), ('Palermo', (-34.585, -58.42)),
                        ('Zona restringida puerto', (-34.63, -58.36))]:
            lat, lng = c
            pts = [{'lat': lat + dx, 'lng': lng + dy} for dx, dy in
                   [(-0.02, -0.02), (0.02, -0.02), (0.02, 0.02), (-0.02, 0.02)]]
            db.add(Geofence(id=new_id(), name=name, polygon=pts,
                            rule=random.choice(['enter', 'exit']),
                            severity=random.choice(['low', 'medium', 'high'])))
        db.commit()

        # ---- Turnos recientes de drivers activos ----
        for d in drivers[:15]:
            start = utcnow().replace(hour=random.randint(6, 10), minute=0) - timedelta(days=random.randint(0, 3))
            end = start + timedelta(hours=random.uniform(6, 10))
            db.add(DriverShift(id=new_id(), driver_id=d.id,
                               shift_date=start.date(), start_time=start, end_time=end,
                               total_hours=round((end - start).total_seconds() / 3600, 1),
                               vehicle_id=d.current_vehicle_id))
        db.commit()
        print('geofences + driver_shifts: OK')
        print('DONE — DB poblada')
    finally:
        db.close()


if __name__ == '__main__':
    main()
