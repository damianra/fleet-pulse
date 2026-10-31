"""Conductores — CRUD, turnos (start/end con reglas de fatiga),
historial de entregas y métricas de performance.
Lectura: autenticado. Escritura: admin|dispatcher.
Reglas de turno: máx 10 h continuas y ≥8 h de descanso entre turnos."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..alerts_engine import create_alert
from ..db import get_db
from ..models import (Delivery, Driver, DriverShift, Route, User, Vehicle,
                      utcnow)
from ..schemas import (DriverIn, DriverOut, DriverUpdateIn, DeliveryOut,
                       ShiftOut, StartShiftIn)
from ..security import get_current_user, require_roles
from ._common import get_or_404, paginate, sortable

router = APIRouter()

_rw = Depends(require_roles('admin', 'dispatcher'))
_ro = Depends(get_current_user)
SORTABLE = {'license_number', 'status', 'rating', 'total_deliveries', 'created_at'}
MAX_SHIFT_HOURS = 10
MIN_REST_HOURS = 8


@router.get('', response_model=list[DriverOut])
def list_drivers(status: str = Query(None), search: str = Query(None),
                 page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                 sort_by: str = Query(None), order: str = Query('asc'),
                 db: Session = Depends(get_db), _u: User = _ro):
    q = db.query(Driver)
    if status:
        q = q.filter(Driver.status == status)
    if search:
        like = f'%{search}%'
        q = q.filter(or_(Driver.license_number.ilike(like),
                         Driver.phone.ilike(like)))
    col = sortable(Driver, sort_by, SORTABLE, Driver.license_number)
    return paginate(q, page, limit, col, order)


@router.post('', response_model=DriverOut, status_code=201)
def create_driver(payload: DriverIn, db: Session = Depends(get_db),
                  _u: User = _rw):
    if payload.user_id:
        get_or_404(db, User, payload.user_id, 'user')
    driver = Driver(**payload.model_dump())
    db.add(driver)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'license_number o user_id ya registrado')
    db.refresh(driver)
    return driver


@router.get('/{driver_id}', response_model=DriverOut)
def get_driver(driver_id: str, db: Session = Depends(get_db), _u: User = _ro):
    return get_or_404(db, Driver, driver_id, 'driver')


@router.put('/{driver_id}', response_model=DriverOut)
def update_driver(driver_id: str, payload: DriverUpdateIn,
                  db: Session = Depends(get_db), _u: User = _rw):
    driver = get_or_404(db, Driver, driver_id, 'driver')
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(driver, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'license_number o user_id ya registrado')
    db.refresh(driver)
    return driver


@router.delete('/{driver_id}', status_code=204)
def delete_driver(driver_id: str, db: Session = Depends(get_db),
                  _u: User = _rw):
    driver = get_or_404(db, Driver, driver_id, 'driver')
    db.query(Vehicle).filter(Vehicle.assigned_driver_id == driver_id).update(
        {'assigned_driver_id': None})
    db.delete(driver)
    db.commit()


@router.get('/{driver_id}/deliveries', response_model=list[DeliveryOut])
def driver_deliveries(driver_id: str, limit: int = Query(100, ge=1, le=500),
                      db: Session = Depends(get_db), _u: User = _ro):
    get_or_404(db, Driver, driver_id, 'driver')
    return (db.query(Delivery).join(Route, Delivery.route_id == Route.id)
            .filter(Route.assigned_driver_id == driver_id)
            .order_by(Delivery.created_at.desc()).limit(limit).all())


@router.get('/{driver_id}/shifts', response_model=list[ShiftOut])
def driver_shifts(driver_id: str, limit: int = Query(100, ge=1, le=500),
                  db: Session = Depends(get_db), _u: User = _ro):
    get_or_404(db, Driver, driver_id, 'driver')
    return (db.query(DriverShift).filter(DriverShift.driver_id == driver_id)
            .order_by(DriverShift.start_time.desc()).limit(limit).all())


@router.post('/{driver_id}/start-shift', response_model=ShiftOut, status_code=201)
def start_shift(driver_id: str, payload: StartShiftIn,
                db: Session = Depends(get_db), _u: User = _rw):
    driver = get_or_404(db, Driver, driver_id, 'driver')
    if driver.status == 'suspended':
        raise HTTPException(400, 'driver suspendido')
    open_shift = (db.query(DriverShift)
                  .filter(DriverShift.driver_id == driver_id,
                          DriverShift.end_time.is_(None)).first())
    if open_shift:
        raise HTTPException(409, 'ya tiene un turno abierto')
    last = (db.query(DriverShift).filter(DriverShift.driver_id == driver_id,
                                         DriverShift.end_time.isnot(None))
            .order_by(DriverShift.end_time.desc()).first())
    if last and utcnow() - last.end_time < timedelta(hours=MIN_REST_HOURS):
        raise HTTPException(400, f'descanso mínimo de {MIN_REST_HOURS}h entre turnos')
    if payload.vehicle_id:
        get_or_404(db, Vehicle, payload.vehicle_id, 'vehicle')
    now = utcnow()
    shift = DriverShift(driver_id=driver_id, shift_date=date.today(),
                        start_time=now, vehicle_id=payload.vehicle_id,
                        notes=payload.notes)
    driver.status = 'on_duty'
    if payload.vehicle_id:
        driver.current_vehicle_id = payload.vehicle_id
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.post('/{driver_id}/end-shift', response_model=ShiftOut)
def end_shift(driver_id: str, db: Session = Depends(get_db), _u: User = _rw):
    driver = get_or_404(db, Driver, driver_id, 'driver')
    shift = (db.query(DriverShift)
             .filter(DriverShift.driver_id == driver_id,
                     DriverShift.end_time.is_(None)).first())
    if shift is None:
        raise HTTPException(404, 'no hay turno abierto')
    shift.end_time = utcnow()
    shift.total_hours = round(
        (shift.end_time - shift.start_time).total_seconds() / 3600, 2)
    driver.status = 'off_duty'
    if shift.total_hours > MAX_SHIFT_HOURS:
        create_alert(db, 'driver_fatigue', 'high',
                     f'Conductor excedió {MAX_SHIFT_HOURS}h de turno',
                     f'Turno de {shift.total_hours}h finalizado',
                     driver_id=driver.id, vehicle_id=shift.vehicle_id)
    db.commit()
    db.refresh(shift)
    return shift


@router.get('/{driver_id}/performance')
def driver_performance(driver_id: str, db: Session = Depends(get_db),
                       _u: User = _ro):
    driver = get_or_404(db, Driver, driver_id, 'driver')
    deliveries = (db.query(Delivery).join(Route, Delivery.route_id == Route.id)
                  .filter(Route.assigned_driver_id == driver_id).all())
    done = [d for d in deliveries if d.status == 'delivered']
    on_time = [d for d in done
               if d.actual_delivery_time and d.delivery_window_end
               and d.actual_delivery_time <= d.delivery_window_end]
    shifts = (db.query(DriverShift).filter(DriverShift.driver_id == driver_id,
                                           DriverShift.total_hours.isnot(None)).all())
    return {'driver_id': driver_id,
            'total_deliveries': driver.total_deliveries,
            'deliveries_in_scope': len(deliveries),
            'completed': len(done),
            'on_time_rate': round(len(on_time) / len(done), 3) if done else None,
            'rating': driver.rating,
            'total_shift_hours': round(sum(s.total_hours or 0 for s in shifts), 2),
            'shifts_count': len(shifts)}
