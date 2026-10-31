"""Alertas — listado con filtros, detalle, acknowledge/resolve y stats.
La generación es automática (alerts_engine + triggers inline); acá solo
se gestionan. Lectura: autenticado. Ack/resolve: admin|dispatcher."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Alert, User, utcnow
from ..schemas import AlertOut, ResolveAlertIn
from ..security import get_current_user, require_roles
from ._common import get_or_404, paginate, sortable

router = APIRouter()

_rw = Depends(require_roles('admin', 'dispatcher'))
_ro = Depends(get_current_user)
SORTABLE = {'triggered_at', 'severity', 'status', 'type'}


@router.get('/stats')
def alert_stats(db: Session = Depends(get_db), _u: User = _ro):
    rows = db.query(Alert).all()
    by_status, by_type, by_severity = {}, {}, {}
    for a in rows:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        by_type[a.type] = by_type.get(a.type, 0) + 1
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
    return {'total_alerts': len(rows), 'alerts_by_status': by_status,
            'alerts_by_type': by_type, 'alerts_by_severity': by_severity}


@router.get('/active', response_model=list[AlertOut])
def active_alerts(db: Session = Depends(get_db), _u: User = _ro):
    return (db.query(Alert).filter(Alert.status == 'active')
            .order_by(Alert.triggered_at.desc()).all())


@router.get('', response_model=list[AlertOut])
def list_alerts(status: str = Query(None), type: str = Query(None),
                severity: str = Query(None), vehicle_id: str = Query(None),
                driver_id: str = Query(None), delivery_id: str = Query(None),
                page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                sort_by: str = Query('triggered_at'), order: str = Query('desc'),
                db: Session = Depends(get_db), _u: User = _ro):
    q = db.query(Alert)
    for col, val in ((Alert.status, status), (Alert.type, type),
                     (Alert.severity, severity), (Alert.vehicle_id, vehicle_id),
                     (Alert.driver_id, driver_id), (Alert.delivery_id, delivery_id)):
        if val:
            q = q.filter(col == val)
    col = sortable(Alert, sort_by, SORTABLE, Alert.triggered_at)
    return paginate(q, page, limit, col, order)


@router.get('/{alert_id}', response_model=AlertOut)
def get_alert(alert_id: str, db: Session = Depends(get_db), _u: User = _ro):
    return get_or_404(db, Alert, alert_id, 'alert')


@router.post('/{alert_id}/acknowledge', response_model=AlertOut)
def acknowledge_alert(alert_id: str, db: Session = Depends(get_db),
                      user: User = _rw):
    alert = get_or_404(db, Alert, alert_id, 'alert')
    if alert.status == 'active':
        alert.status = 'acknowledged'
        alert.acknowledged_at = utcnow()
        alert.acknowledged_by = user.id
        db.commit()
        db.refresh(alert)
    return alert


@router.post('/{alert_id}/resolve', response_model=AlertOut)
def resolve_alert(alert_id: str, payload: ResolveAlertIn,
                  db: Session = Depends(get_db), user: User = _rw):
    alert = get_or_404(db, Alert, alert_id, 'alert')
    if alert.status != 'resolved':
        if alert.status == 'active':
            alert.acknowledged_at = utcnow()
            alert.acknowledged_by = user.id
        alert.status = 'resolved'
        alert.resolved_at = utcnow()
        alert.resolved_by = user.id
        alert.resolution_notes = payload.notes
        db.commit()
        db.refresh(alert)
    return alert
