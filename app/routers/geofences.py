"""Geofences — zonas geográficas definidas como polígonos con regla
`enter` (alerta al ingresar, ej. zona restringida) o `exit` (alerta al
salir, ej. perímetro permitido). La violación se evalúa inline en
POST /api/tracking/update por detección de borde (posición previa vs.
nueva). `vehicle_id` null aplica a toda la flota.
Lectura y check: autenticado. Escritura: admin|dispatcher."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..geo import point_in_polygon
from ..models import Geofence, User, Vehicle
from ..schemas import (GeofenceIn, GeofenceOut, GeofenceUpdateIn, Location)
from ..security import get_current_user, require_roles
from ._common import get_or_404, paginate, sortable

router = APIRouter()

_rw = Depends(require_roles('admin', 'dispatcher'))
_ro = Depends(get_current_user)
SORTABLE = {'name', 'rule', 'severity', 'created_at'}


@router.get('', response_model=list[GeofenceOut])
def list_geofences(rule: str = Query(None), is_active: bool = Query(None),
                   vehicle_id: str = Query(None), search: str = Query(None),
                   page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                   sort_by: str = Query(None), order: str = Query('asc'),
                   db: Session = Depends(get_db), _u: User = _ro):
    q = db.query(Geofence)
    if rule:
        q = q.filter(Geofence.rule == rule)
    if is_active is not None:
        q = q.filter(Geofence.is_active.is_(is_active))
    if vehicle_id:
        # zonas que aplican al vehículo: las suyas + las globales
        q = q.filter(Geofence.vehicle_id.is_(None) |
                     (Geofence.vehicle_id == vehicle_id))
    if search:
        q = q.filter(Geofence.name.ilike(f'%{search}%'))
    col = sortable(Geofence, sort_by, SORTABLE, Geofence.name)
    return paginate(q, page, limit, col, order)


@router.post('', response_model=GeofenceOut, status_code=201)
def create_geofence(payload: GeofenceIn, db: Session = Depends(get_db),
                    _u: User = _rw):
    if payload.vehicle_id:
        get_or_404(db, Vehicle, payload.vehicle_id, 'vehicle')
    gf = Geofence(**payload.model_dump())
    db.add(gf)
    db.commit()
    db.refresh(gf)
    return gf


@router.get('/{gf_id}', response_model=GeofenceOut)
def get_geofence(gf_id: str, db: Session = Depends(get_db), _u: User = _ro):
    return get_or_404(db, Geofence, gf_id, 'geofence')


@router.put('/{gf_id}', response_model=GeofenceOut)
def update_geofence(gf_id: str, payload: GeofenceUpdateIn,
                    db: Session = Depends(get_db), _u: User = _rw):
    gf = get_or_404(db, Geofence, gf_id, 'geofence')
    if payload.vehicle_id:
        get_or_404(db, Vehicle, payload.vehicle_id, 'vehicle')
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(gf, key, value)
    db.commit()
    db.refresh(gf)
    return gf


@router.delete('/{gf_id}', status_code=204)
def delete_geofence(gf_id: str, db: Session = Depends(get_db), _u: User = _rw):
    db.delete(get_or_404(db, Geofence, gf_id, 'geofence'))
    db.commit()


@router.post('/{gf_id}/check')
def check_point(gf_id: str, payload: Location, db: Session = Depends(get_db),
                _u: User = _ro):
    gf = get_or_404(db, Geofence, gf_id, 'geofence')
    return {'geofence_id': gf_id, 'rule': gf.rule,
            'inside': point_in_polygon(payload.lat, payload.lng,
                                       gf.polygon or [])}
