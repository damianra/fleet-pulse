"""Mantenimiento — CRUD de registros, próximos servicios, historial por
vehículo y marcado de completado.
Lectura: autenticado. Escritura: admin|dispatcher."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import MaintenanceRecord, User, Vehicle
from ..schemas import (MaintenanceIn, MaintenanceOut, MaintenanceUpdateIn)
from ..security import get_current_user, require_roles
from ._common import get_or_404, paginate, sortable

router = APIRouter()

_rw = Depends(require_roles('admin', 'dispatcher'))
_ro = Depends(get_current_user)
SORTABLE = {'scheduled_date', 'next_service_date', 'cost', 'created_at'}
UPCOMING_DAYS = 30


@router.get('/upcoming', response_model=list[MaintenanceOut])
def upcoming(db: Session = Depends(get_db), _u: User = _ro):
    limit_date = date.today() + timedelta(days=UPCOMING_DAYS)
    return (db.query(MaintenanceRecord)
            .filter(MaintenanceRecord.status.in_(['scheduled', 'in_progress']),
                    MaintenanceRecord.next_service_date.isnot(None),
                    MaintenanceRecord.next_service_date <= limit_date)
            .order_by(MaintenanceRecord.next_service_date).all())


@router.get('/vehicles/{vehicle_id}', response_model=list[MaintenanceOut])
def by_vehicle(vehicle_id: str, db: Session = Depends(get_db), _u: User = _ro):
    get_or_404(db, Vehicle, vehicle_id, 'vehicle')
    return (db.query(MaintenanceRecord)
            .filter(MaintenanceRecord.vehicle_id == vehicle_id)
            .order_by(MaintenanceRecord.scheduled_date.desc()).all())


@router.get('', response_model=list[MaintenanceOut])
def list_maintenance(status: str = Query(None), type: str = Query(None),
                     vehicle_id: str = Query(None),
                     page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                     sort_by: str = Query(None), order: str = Query('desc'),
                     db: Session = Depends(get_db), _u: User = _ro):
    q = db.query(MaintenanceRecord)
    if status:
        q = q.filter(MaintenanceRecord.status == status)
    if type:
        q = q.filter(MaintenanceRecord.type == type)
    if vehicle_id:
        q = q.filter(MaintenanceRecord.vehicle_id == vehicle_id)
    col = sortable(MaintenanceRecord, sort_by, SORTABLE,
                   MaintenanceRecord.created_at)
    return paginate(q, page, limit, col, order)


@router.post('', response_model=MaintenanceOut, status_code=201)
def create_maintenance(payload: MaintenanceIn, db: Session = Depends(get_db),
                       _u: User = _rw):
    get_or_404(db, Vehicle, payload.vehicle_id, 'vehicle')
    record = MaintenanceRecord(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get('/{record_id}', response_model=MaintenanceOut)
def get_maintenance(record_id: str, db: Session = Depends(get_db),
                    _u: User = _ro):
    return get_or_404(db, MaintenanceRecord, record_id, 'maintenance record')


@router.put('/{record_id}', response_model=MaintenanceOut)
def update_maintenance(record_id: str, payload: MaintenanceUpdateIn,
                       db: Session = Depends(get_db), _u: User = _rw):
    record = get_or_404(db, MaintenanceRecord, record_id, 'maintenance record')
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


@router.delete('/{record_id}', status_code=204)
def delete_maintenance(record_id: str, db: Session = Depends(get_db),
                       _u: User = _rw):
    record = get_or_404(db, MaintenanceRecord, record_id, 'maintenance record')
    db.delete(record)
    db.commit()


@router.post('/{record_id}/complete', response_model=MaintenanceOut)
def complete_maintenance(record_id: str, db: Session = Depends(get_db),
                         _u: User = _rw):
    record = get_or_404(db, MaintenanceRecord, record_id, 'maintenance record')
    if record.status == 'completed':
        raise HTTPException(400, 'el registro ya está completado')
    record.status = 'completed'
    record.completed_date = date.today()
    vehicle = db.get(Vehicle, record.vehicle_id)
    if vehicle and vehicle.status == 'maintenance':
        vehicle.status = 'available'
    db.commit()
    db.refresh(record)
    return record
