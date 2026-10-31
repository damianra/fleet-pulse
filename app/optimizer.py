"""Optimización de rutas — nearest-neighbor + mejora 2-opt sobre las
paradas de la ruta (route_deliveries → deliveries.delivery_address).

Corre en una BackgroundTask de FastAPI (single-process, sin Celery); el
progreso/resultado se persiste en routes.optimization_data, así
GET /optimization-status lo lee de la DB y sobrevive reinicios.

Los algoritmos 'genetic' y 'simulated_annealing' del plan se resuelven
con NN + 2-opt como aproximación y se registra `algorithm_used`."""
from datetime import timedelta

from .geo import haversine_km
from .models import Delivery, Route, utcnow

AVG_SPEED_KMH = 40.0
STOP_SERVICE_MIN = 10


def _nn_order(origin, stops):
    remaining = list(stops)
    ordered = []
    cur = origin
    while remaining:
        nxt = min(remaining, key=lambda s: haversine_km(
            cur[0], cur[1], s['lat'], s['lng']))
        ordered.append(nxt)
        cur = (nxt['lat'], nxt['lng'])
        remaining.remove(nxt)
    return ordered


def _leg(a, b):
    return haversine_km(a[0], a[1], b[0], b[1])


def _total(order, origin, destination):
    pts = [(s['lat'], s['lng']) for s in order]
    total = _leg(origin, pts[0]) if pts else _leg(origin, destination)
    total += sum(_leg(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if pts:
        total += _leg(pts[-1], destination)
    return total


def _two_opt(order, origin, destination, max_passes=20):
    improved = True
    passes = 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if _total(cand, origin, destination) < _total(order, origin, destination) - 1e-9:
                    order = cand
                    improved = True
    return order


def run_optimization(SessionLocal, route_id: str):
    """BackgroundTask — recalcula el orden de paradas y persiste todo en
    la ruta (waypoints, distancia, duración estimada, ETAs)."""
    db = SessionLocal()
    try:
        route = db.get(Route, route_id)
        if route is None:
            return
        data = dict(route.optimization_data or {})
        try:
            origin = (route.origin_lat, route.origin_lng)
            destination = (route.destination_lat, route.destination_lng)
            stops = []
            for rd in route.stops:
                d = db.get(Delivery, rd.delivery_id)
                addr = (d.delivery_address or {}) if d else {}
                if addr.get('lat') is None or addr.get('lng') is None:
                    continue  # paradas sin coordenadas conservan su orden
                stops.append({'rd': rd, 'delivery_id': d.id,
                              'lat': float(addr['lat']), 'lng': float(addr['lng']),
                              'address': addr.get('street', '')})
            ordered = _two_opt(_nn_order(origin, stops), origin, destination)
            distance = _total(ordered, origin, destination)

            eta = (route.actual_start or route.planned_start or utcnow())
            waypoints = []
            for i, s in enumerate(ordered):
                if i:
                    prev = ordered[i - 1]
                    leg_km = _leg((prev['lat'], prev['lng']), (s['lat'], s['lng']))
                    eta += timedelta(minutes=leg_km / AVG_SPEED_KMH * 60 + STOP_SERVICE_MIN)
                s['rd'].stop_order = i + 1
                s['rd'].estimated_arrival = eta
                waypoints.append({'order': i + 1, 'delivery_id': s['delivery_id'],
                                  'lat': s['lat'], 'lng': s['lng'],
                                  'address': s['address'],
                                  'estimated_arrival': eta.isoformat()})

            route.waypoints = waypoints
            route.total_distance_km = round(distance, 2)
            route.estimated_duration_minutes = round(
                distance / AVG_SPEED_KMH * 60 + STOP_SERVICE_MIN * len(ordered))
            data.update({'status': 'done',
                         'algorithm_used': 'nearest_neighbor+2opt',
                         'result': {'ordered_delivery_ids': [s['delivery_id'] for s in ordered],
                                    'total_distance_km': route.total_distance_km,
                                    'estimated_duration_minutes': route.estimated_duration_minutes},
                         'finished_at': utcnow().isoformat()})
        except Exception as exc:  # la tarea nunca debe morir en silencio
            data.update({'status': 'failed', 'error': str(exc),
                         'finished_at': utcnow().isoformat()})
        route.optimization_data = data
        db.commit()
    finally:
        db.close()
