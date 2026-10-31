"""Datos iniciales FleetPulse — demo mínima de flota (se inserta solo si
cada tabla está vacía, idempotente). Coordenadas: Ciudad de Buenos Aires."""
from .models import (Delivery, Driver, Geofence, Route, RouteDelivery,
                     Vehicle)

VEHICLES = [
    {'plate': 'ABC123', 'type': 'truck', 'brand': 'Iveco', 'model': 'Daily',
     'year': 2021, 'capacity_kg': 3500, 'capacity_m3': 18,
     'fuel_type': 'diesel', 'status': 'available', 'mileage': 48200},
    {'plate': 'DEF456', 'type': 'van', 'brand': 'Renault', 'model': 'Kangoo',
     'year': 2022, 'capacity_kg': 800, 'capacity_m3': 4,
     'fuel_type': 'gasoline', 'status': 'available', 'mileage': 31000},
    {'plate': 'GHI789', 'type': 'motorcycle', 'brand': 'Honda', 'model': 'XR150',
     'year': 2023, 'capacity_kg': 40, 'capacity_m3': 0.2,
     'fuel_type': 'gasoline', 'status': 'available', 'mileage': 12000},
]

DRIVERS = [
    {'license_number': 'LIC-1001', 'license_type': 'C',
     'phone': '+54 11 5555-1001', 'status': 'available', 'rating': 4.8},
    {'license_number': 'LIC-1002', 'license_type': 'B',
     'phone': '+54 11 5555-1002', 'status': 'available', 'rating': 4.5},
    {'license_number': 'LIC-1003', 'license_type': 'A',
     'phone': '+54 11 5555-1003', 'status': 'available', 'rating': 4.9},
]


GEOFENCES = [
    {'name': 'Puerto — zona restringida',
     'description': 'Diques de Puerto Madero — ingreso prohibido a la flota',
     'rule': 'enter', 'severity': 'high',
     'polygon': [{'lat': -34.608, 'lng': -58.362},
                 {'lat': -34.628, 'lng': -58.352},
                 {'lat': -34.640, 'lng': -58.362},
                 {'lat': -34.622, 'lng': -58.372}]},
]


def seed_if_empty(db):
    if db.query(Vehicle).count() == 0:
        db.add_all([Vehicle(**row) for row in VEHICLES])
    if db.query(Driver).count() == 0:
        db.add_all([Driver(**row) for row in DRIVERS])
    if db.query(Geofence).count() == 0:
        db.add_all([Geofence(**row) for row in GEOFENCES])
    db.flush()

    if db.query(Delivery).count() == 0 and db.query(Route).count() == 0:
        route = Route(name='Reparto Centro AM', type='fixed',
                      origin_lat=-34.6037, origin_lng=-58.3816,
                      destination_lat=-34.6037, destination_lng=-58.3816,
                      status='planned')
        db.add(route)
        db.flush()
        deliveries = [
            Delivery(order_number='ORD-0001', customer_name='Kiosco 25',
                     customer_phone='+54 11 4444-0001', priority='high',
                     delivery_address={'street': 'Av. Corrientes 1200',
                                       'city': 'CABA', 'lat': -34.6040,
                                       'lng': -58.3830},
                     route_id=route.id),
            Delivery(order_number='ORD-0002', customer_name='Farmacia Sur',
                     customer_phone='+54 11 4444-0002', priority='medium',
                     delivery_address={'street': 'Av. de Mayo 900',
                                       'city': 'CABA', 'lat': -34.6089,
                                       'lng': -58.3800},
                     route_id=route.id),
        ]
        db.add_all(deliveries)
        db.flush()
        for i, d in enumerate(deliveries):
            db.add(RouteDelivery(route_id=route.id, delivery_id=d.id,
                                 stop_order=i + 1))
    db.commit()
