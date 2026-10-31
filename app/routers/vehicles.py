"""Vehículos — CRUD con filtros/paginación, soft delete, asignación de
conductor, historial de tracking y mantenimiento, stats de flota.
Lectura: cualquier usuario autenticado. Escritura: admin|dispatcher."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Driver, MaintenanceRecord, TrackingEvent, User, Vehicle
from ..schemas import (AssignDriverIn, MaintenanceOut, TrackingEventOut,
                       VehicleIn, VehicleOut, VehicleUpdateIn)
from ..security import get_current_user, require_roles
from ._common import get_or_404, paginate, sortable

router = APIRouter()

_rw = Depends(require_roles('admin', 'dispatcher'))
_ro = Depends(get_current_user)
SORTABLE = {'plate', 'brand', 'status', 'type', 'mileage', 'created_at'}


@router.get('/stats')
def vehicle_stats(db: Session = Depends(get_db), _u: User = _ro):
    rows = db.query(Vehicle).filter(Vehicle.is_active.is_(True)).all()
    by_status, by_type = {}, {}
    for v in rows:
        by_status[v.status] = by_status.get(v.status, 0) + 1
        by_type[v.type] = by_type.get(v.type, 0) + 1
    mileages = [v.mileage or 0 for v in rows]
    return {'total_vehicles': len(rows),
            'vehicles_by_status': by_status,
            'vehicles_by_type': by_type,
            'avg_mileage': round(sum(mileages) / len(mileages), 1) if mileages else 0}


@router.get('', response_model=list[VehicleOut])
def list_vehicles(status: str = Query(None), type: str = Query(None),
                  assigned_driver_id: str = Query(None),
                  search: str = Query(None),
                  page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                  sort_by: str = Query(None), order: str = Query('asc'),
                  db: Session = Depends(get_db), _u: User = _ro):
    q = db.query(Vehicle).filter(Vehicle.is_active.is_(True))
    if status:
        q = q.filter(Vehicle.status == status)
    if type:
        q = q.filter(Vehicle.type == type)
    if assigned_driver_id:
        q = q.filter(Vehicle.assigned_driver_id == assigned_driver_id)
    if search:
        like = f'%{search}%'
        q = q.filter(or_(Vehicle.plate.ilike(like), Vehicle.brand.ilike(like),
                         Vehicle.model.ilike(like)))
    col = sortable(Vehicle, sort_by, SORTABLE, Vehicle.plate)
    return paginate(q, page, limit, col, order)


@router.post('', response_model=VehicleOut, status_code=201)
def create_vehicle(payload: VehicleIn, db: Session = Depends(get_db),
                   _u: User = _rw):
    vehicle = Vehicle(**payload.model_dump())
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'plate ya registrada')
    db.refresh(vehicle)
    return vehicle


@router.get('/{vehicle_id}', response_model=VehicleOut)
def get_vehicle(vehicle_id: str, db: Session = Depends(get_db), _u: User = _ro):
    v = get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    if not v.is_active:
        raise HTTPException(404, 'vehicle not found')
    return v


@router.put('/{vehicle_id}', response_model=VehicleOut)
def update_vehicle(vehicle_id: str, payload: VehicleUpdateIn,
                   db: Session = Depends(get_db), _u: User = _rw):
    vehicle = get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(vehicle, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'plate ya registrada')
    db.refresh(vehicle)
    return vehicle


@router.delete('/{vehicle_id}', status_code=204)
def delete_vehicle(vehicle_id: str, db: Session = Depends(get_db),
                   _u: User = _rw):
    vehicle = get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    vehicle.is_active = False  # soft delete
    db.commit()


@router.get('/{vehicle_id}/tracking', response_model=list[TrackingEventOut])
def vehicle_tracking(vehicle_id: str, limit: int = Query(100, ge=1, le=1000),
                     db: Session = Depends(get_db), _u: User = _ro):
    get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    return (db.query(TrackingEvent)
            .filter(TrackingEvent.vehicle_id == vehicle_id)
            .order_by(TrackingEvent.timestamp.desc())
            .limit(limit).all())


@router.get('/{vehicle_id}/maintenance', response_model=list[MaintenanceOut])
def vehicle_maintenance(vehicle_id: str, db: Session = Depends(get_db),
                        _u: User = _ro):
    get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    return (db.query(MaintenanceRecord)
            .filter(MaintenanceRecord.vehicle_id == vehicle_id)
            .order_by(MaintenanceRecord.scheduled_date.desc()).all())


@router.post('/{vehicle_id}/assign-driver', response_model=VehicleOut)
def assign_driver(vehicle_id: str, payload: AssignDriverIn,
                  db: Session = Depends(get_db), _u: User = _rw):
    vehicle = get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    if payload.driver_id is None:
        if vehicle.assigned_driver_id:
            prev = db.get(Driver, vehicle.assigned_driver_id)
            if prev and prev.current_vehicle_id == vehicle.id:
                prev.current_vehicle_id = None
        vehicle.assigned_driver_id = None
    else:
        driver = get_or_404(db, Driver, payload.driver_id, 'driver')
        if driver.status == 'suspended':
            raise HTTPException(400, 'driver suspendido')
        prev = db.get(Driver, vehicle.assigned_driver_id) if vehicle.assigned_driver_id else None
        if prev and prev.current_vehicle_id == vehicle.id:
            prev.current_vehicle_id = None
        if driver.current_vehicle_id and driver.current_vehicle_id != vehicle.id:
            other = db.get(Vehicle, driver.current_vehicle_id)
            if other:
                other.assigned_driver_id = None
        vehicle.assigned_driver_id = driver.id
        driver.current_vehicle_id = vehicle.id
    db.commit()
    db.refresh(vehicle)
    return vehicle
