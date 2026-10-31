"""Helpers de geolocalización — distancia haversine en km, punto en
polígono (ray casting) y distancia punto→polyline (proyección
equirectangular local, válida a escala urbana)."""
import math


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def point_in_polygon(lat, lng, polygon) -> bool:
    """Ray casting en el plano (lng, lat). polygon = [{lat,lng},...];
    válido para zonas urbanas (no polos ni cruce del antimeridiano)."""
    pts = [(p['lng'], p['lat']) for p in polygon]
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > lat) != (yj > lat) and \
                lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _to_xy_km(lat, lng, lat0):
    return (math.radians(lng) * 6371.0 * math.cos(math.radians(lat0)),
            math.radians(lat) * 6371.0)


def point_to_segment_km(lat, lng, a, b) -> float:
    """Distancia del punto al segmento a→b en km (plano tangente local)."""
    px, py = _to_xy_km(lat, lng, lat)
    ax, ay = _to_xy_km(a[0], a[1], lat)
    bx, by = _to_xy_km(b[0], b[1], lat)
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy)
                     / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_to_polyline_km(lat, lng, points) -> float:
    """Mínima distancia del punto a la polyline [(lat,lng),...] en km."""
    if len(points) < 2:
        return haversine_km(lat, lng, points[0][0], points[0][1])
    return min(point_to_segment_km(lat, lng, points[i], points[i + 1])
               for i in range(len(points) - 1))
