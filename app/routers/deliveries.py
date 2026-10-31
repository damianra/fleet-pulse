"""Entregas — CRUD + ciclo de vida (start/complete/fail/reschedule) +
prueba de entrega (URLs de firma/fotos, sin upload de archivos) + stats.
Lectura: autenticado. Escritura: admin|dispatcher."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Delivery, Driver, Route, User, utcnow
from ..schemas import (CompleteDeliveryIn, DeliveryIn, DeliveryOut,
                       DeliveryUpdateIn, FailDeliveryIn, ProofIn,
                       RescheduleDeliveryIn)
from ..security import get_current_user, require_roles
from ._common import get_or_404, paginate, sortable

router = APIRouter()

_rw = Depends(require_roles('admin', 'dispatcher'))
_ro = Depends(get_current_user)
SORTABLE = {'order_number', 'status', 'priority', 'sla_deadline', 'created_at'}


@router.get('/stats')
def delivery_stats(db: Session = Depends(get_db), _u: User = _ro):
    rows = db.query(Delivery).all()
    by_status = {}
    for d in rows:
        by_status[d.status] = by_status.get(d.status, 0) + 1
    done = [d for d in rows if d.status == 'delivered']
    on_time = [d for d in done if d.actual_delivery_time and d.delivery_window_end
               and d.actual_delivery_time <= d.delivery_window_end]
    times = [(d.actual_delivery_time - d.created_at).total_seconds() / 60
             for d in done if d.actual_delivery_time and d.created_at]
    return {'total_deliveries': len(rows),
            'deliveries_by_status': by_status,
            'on_time_rate': round(len(on_time) / len(done), 3) if done else None,
            'avg_delivery_time_minutes': round(sum(times) / len(times), 1) if times else None}


@router.get('', response_model=list[DeliveryOut])
def list_deliveries(status: str = Query(None), priority: str = Query(None),
                    route_id: str = Query(None), search: str = Query(None),
                    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                    sort_by: str = Query(None), order: str = Query('desc'),
                    db: Session = Depends(get_db), _u: User = _ro):
    q = db.query(Delivery)
    if status:
        q = q.filter(Delivery.status == status)
    if priority:
        q = q.filter(Delivery.priority == priority)
    if route_id:
        q = q.filter(Delivery.route_id == route_id)
    if search:
        like = f'%{search}%'
        q = q.filter(Delivery.order_number.ilike(like))
    col = sortable(Delivery, sort_by, SORTABLE, Delivery.created_at)
    return paginate(q, page, limit, col, order)


@router.post('', response_model=DeliveryOut, status_code=201)
def create_delivery(payload: DeliveryIn, db: Session = Depends(get_db),
                    _u: User = _rw):
    if payload.route_id:
        get_or_404(db, Route, payload.route_id, 'route')
    delivery = Delivery(**payload.model_dump())
    db.add(delivery)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'order_number ya registrado')
    db.refresh(delivery)
    return delivery


@router.get('/{delivery_id}', response_model=DeliveryOut)
def get_delivery(delivery_id: str, db: Session = Depends(get_db), _u: User = _ro):
    return get_or_404(db, Delivery, delivery_id, 'delivery')


@router.put('/{delivery_id}', response_model=DeliveryOut)
def update_delivery(delivery_id: str, payload: DeliveryUpdateIn,
                    db: Session = Depends(get_db), _u: User = _rw):
    delivery = get_or_404(db, Delivery, delivery_id, 'delivery')
    if delivery.status in ('delivered', 'failed'):
        raise HTTPException(400, 'no se puede modificar una entrega finalizada')
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(delivery, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'order_number ya registrado')
    db.refresh(delivery)
    return delivery


@router.delete('/{delivery_id}', status_code=204)
def delete_delivery(delivery_id: str, db: Session = Depends(get_db),
                    _u: User = _rw):
    delivery = get_or_404(db, Delivery, delivery_id, 'delivery')
    db.delete(delivery)
    db.commit()


@router.post('/{delivery_id}/start', response_model=DeliveryOut)
def start_delivery(delivery_id: str, db: Session = Depends(get_db),
                   _u: User = _rw):
    delivery = get_or_404(db, Delivery, delivery_id, 'delivery')
    if delivery.status not in ('pending', 'rescheduled'):
        raise HTTPException(400, f'no se puede iniciar una entrega {delivery.status}')
    delivery.status = 'in_transit'
    db.commit()
    db.refresh(delivery)
    return delivery


@router.post('/{delivery_id}/complete', response_model=DeliveryOut)
def complete_delivery(delivery_id: str, payload: CompleteDeliveryIn,
                      db: Session = Depends(get_db), _u: User = _rw):
    delivery = get_or_404(db, Delivery, delivery_id, 'delivery')
    if delivery.status in ('delivered',):
        raise HTTPException(400, 'la entrega ya está completada')
    when = payload.delivered_at or utcnow()
    delivery.status = 'delivered'
    delivery.actual_delivery_time = when
    delivery.proof_of_delivery = {
        'signature_url': payload.signature_url,
        'photo_urls': payload.photo_urls,
        'delivered_at': when.isoformat(),
        'notes': payload.notes}
    if payload.notes:
        delivery.notes = payload.notes
    # Métrica del conductor asignado a la ruta.
    if delivery.route_id:
        route = db.get(Route, delivery.route_id)
        if route and route.assigned_driver_id:
            driver = db.get(Driver, route.assigned_driver_id)
            if driver:
                driver.total_deliveries = (driver.total_deliveries or 0) + 1
    db.commit()
    db.refresh(delivery)
    return delivery


@router.post('/{delivery_id}/fail', response_model=DeliveryOut)
def fail_delivery(delivery_id: str, payload: FailDeliveryIn,
                  db: Session = Depends(get_db), _u: User = _rw):
    delivery = get_or_404(db, Delivery, delivery_id, 'delivery')
    if delivery.status == 'delivered':
        raise HTTPException(400, 'la entrega ya está completada')
    delivery.status = 'failed'
    if payload.reason:
        delivery.notes = payload.reason
    db.commit()
    db.refresh(delivery)
    return delivery


@router.post('/{delivery_id}/reschedule', response_model=DeliveryOut)
def reschedule_delivery(delivery_id: str, payload: RescheduleDeliveryIn,
                        db: Session = Depends(get_db), _u: User = _rw):
    delivery = get_or_404(db, Delivery, delivery_id, 'delivery')
    if delivery.status == 'delivered':
        raise HTTPException(400, 'la entrega ya está completada')
    for key in ('delivery_window_start', 'delivery_window_end', 'sla_deadline'):
        value = getattr(payload, key)
        if value is not None:
            setattr(delivery, key, value)
    delivery.status = 'rescheduled'
    if payload.notes:
        delivery.notes = payload.notes
    db.commit()
    db.refresh(delivery)
    return delivery


@router.post('/{delivery_id}/upload-proof', response_model=DeliveryOut)
def upload_proof(delivery_id: str, payload: ProofIn,
                 db: Session = Depends(get_db), _u: User = _rw):
    delivery = get_or_404(db, Delivery, delivery_id, 'delivery')
    proof = dict(delivery.proof_of_delivery or {})
    if payload.signature_url:
        proof['signature_url'] = payload.signature_url
    if payload.photo_urls:
        proof['photo_urls'] = list(proof.get('photo_urls') or []) + payload.photo_urls
    if payload.notes:
        proof['notes'] = payload.notes
    delivery.proof_of_delivery = proof
    db.commit()
    db.refresh(delivery)
    return delivery
