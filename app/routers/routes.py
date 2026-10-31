"""Rutas — CRUD, optimización de paradas (BackgroundTask, progreso en
routes.optimization_data), ciclo de vida start/complete y gestión de
entregas/paradas.
Lectura: autenticado. Escritura: admin|dispatcher."""
from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException,
                     Query)
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models import Delivery, Driver, Route, RouteDelivery, User, Vehicle, utcnow
from ..optimizer import run_optimization
from ..schemas import (AddDeliveryIn, DeliveryOut, OptimizeIn, RouteIn,
                       RouteOut, RouteUpdateIn)
from ..security import get_current_user, require_roles
from ._common import get_or_404, paginate, sortable

router = APIRouter()

_rw = Depends(require_roles('admin', 'dispatcher'))
_ro = Depends(get_current_user)
SORTABLE = {'name', 'status', 'type', 'planned_start', 'created_at'}


def _check_assignments(db, vehicle_id, driver_id):
    if vehicle_id:
        get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    if driver_id:
        get_or_404(db, Driver, driver_id, 'driver')


@router.get('', response_model=list[RouteOut])
def list_routes(status: str = Query(None), type: str = Query(None),
                assigned_vehicle_id: str = Query(None),
                assigned_driver_id: str = Query(None),
                page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                sort_by: str = Query(None), order: str = Query('desc'),
                db: Session = Depends(get_db), _u: User = _ro):
    q = db.query(Route)
    if status:
        q = q.filter(Route.status == status)
    if type:
        q = q.filter(Route.type == type)
    if assigned_vehicle_id:
        q = q.filter(Route.assigned_vehicle_id == assigned_vehicle_id)
    if assigned_driver_id:
        q = q.filter(Route.assigned_driver_id == assigned_driver_id)
    col = sortable(Route, sort_by, SORTABLE, Route.created_at)
    return paginate(q, page, limit, col, order)


@router.post('', response_model=RouteOut, status_code=201)
def create_route(payload: RouteIn, db: Session = Depends(get_db), _u: User = _rw):
    _check_assignments(db, payload.assigned_vehicle_id, payload.assigned_driver_id)
    route = Route(**payload.model_dump())
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


@router.get('/{route_id}', response_model=RouteOut)
def get_route(route_id: str, db: Session = Depends(get_db), _u: User = _ro):
    return get_or_404(db, Route, route_id, 'route')


@router.put('/{route_id}', response_model=RouteOut)
def update_route(route_id: str, payload: RouteUpdateIn,
                 db: Session = Depends(get_db), _u: User = _rw):
    route = get_or_404(db, Route, route_id, 'route')
    if route.status in ('completed', 'cancelled'):
        raise HTTPException(400, 'no se puede modificar una ruta finalizada')
    _check_assignments(db, payload.assigned_vehicle_id, payload.assigned_driver_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(route, key, value)
    db.commit()
    db.refresh(route)
    return route


@router.delete('/{route_id}', status_code=204)
def delete_route(route_id: str, db: Session = Depends(get_db), _u: User = _rw):
    route = get_or_404(db, Route, route_id, 'route')
    db.query(Delivery).filter(Delivery.route_id == route_id).update(
        {'route_id': None})
    db.delete(route)  # stops se borran en cascada
    db.commit()


@router.post('/{route_id}/optimize', status_code=202)
def optimize_route(route_id: str, payload: OptimizeIn, bg: BackgroundTasks,
                   db: Session = Depends(get_db), _u: User = _rw):
    route = get_or_404(db, Route, route_id, 'route')
    if not route.stops:
        raise HTTPException(400, 'la ruta no tiene paradas para optimizar')
    if (route.optimization_data or {}).get('status') == 'running':
        raise HTTPException(409, 'ya hay una optimización en curso')
    route.optimization_data = {'status': 'running',
                               'algorithm': payload.algorithm,
                               'params': {'constraints': payload.constraints,
                                          'priorities': payload.priorities},
                               'started_at': utcnow().isoformat()}
    db.commit()
    bg.add_task(run_optimization, SessionLocal, route_id)
    return {'route_id': route_id, 'status': 'running'}


@router.get('/{route_id}/optimization-status')
def optimization_status(route_id: str, db: Session = Depends(get_db),
                        _u: User = _ro):
    route = get_or_404(db, Route, route_id, 'route')
    data = route.optimization_data or {}
    return {'route_id': route_id, 'status': data.get('status', 'idle'),
            'optimization': data}


@router.post('/{route_id}/start', response_model=RouteOut)
def start_route(route_id: str, db: Session = Depends(get_db), _u: User = _rw):
    route = get_or_404(db, Route, route_id, 'route')
    if route.status != 'planned':
        raise HTTPException(400, f'no se puede iniciar una ruta {route.status}')
    route.status = 'in_progress'
    route.actual_start = utcnow()
    if route.assigned_vehicle_id:
        vehicle = db.get(Vehicle, route.assigned_vehicle_id)
        if vehicle:
            vehicle.status = 'in_route'
    db.query(Delivery).filter(
        Delivery.route_id == route_id,
        Delivery.status == 'pending').update({'status': 'in_transit'})
    db.commit()
    db.refresh(route)
    return route


@router.post('/{route_id}/complete', response_model=RouteOut)
def complete_route(route_id: str, db: Session = Depends(get_db), _u: User = _rw):
    route = get_or_404(db, Route, route_id, 'route')
    if route.status != 'in_progress':
        raise HTTPException(400, 'solo se completa una ruta en curso')
    route.status = 'completed'
    route.actual_end = utcnow()
    if route.assigned_vehicle_id:
        vehicle = db.get(Vehicle, route.assigned_vehicle_id)
        if vehicle and vehicle.status == 'in_route':
            vehicle.status = 'available'
    db.commit()
    db.refresh(route)
    return route


@router.get('/{route_id}/deliveries', response_model=list[DeliveryOut])
def route_deliveries(route_id: str, db: Session = Depends(get_db), _u: User = _ro):
    route = get_or_404(db, Route, route_id, 'route')
    return [rd.delivery for rd in route.stops]


@router.post('/{route_id}/add-delivery', status_code=201)
def add_delivery(route_id: str, payload: AddDeliveryIn,
                 db: Session = Depends(get_db), _u: User = _rw):
    route = get_or_404(db, Route, route_id, 'route')
    delivery = get_or_404(db, Delivery, payload.delivery_id, 'delivery')
    if route.status in ('completed', 'cancelled'):
        raise HTTPException(400, 'no se puede modificar una ruta finalizada')
    if any(rd.delivery_id == delivery.id for rd in route.stops):
        raise HTTPException(409, 'la entrega ya está en la ruta')
    next_order = max((rd.stop_order for rd in route.stops), default=0) + 1
    db.add(RouteDelivery(route_id=route.id, delivery_id=delivery.id,
                         stop_order=next_order))
    delivery.route_id = route.id
    db.commit()
    return {'route_id': route_id, 'delivery_id': delivery.id,
            'stop_order': next_order}


@router.delete('/{route_id}/deliveries/{delivery_id}', status_code=204)
def remove_delivery(route_id: str, delivery_id: str,
                    db: Session = Depends(get_db), _u: User = _rw):
    route = get_or_404(db, Route, route_id, 'route')
    rd = next((s for s in route.stops if s.delivery_id == delivery_id), None)
    if rd is None:
        raise HTTPException(404, 'la entrega no está en la ruta')
    delivery = db.get(Delivery, delivery_id)
    if delivery:
        delivery.route_id = None
    db.delete(rd)
    db.flush()
    for i, s in enumerate(sorted(route.stops, key=lambda x: x.stop_order)):
        s.stop_order = i + 1
    db.commit()
