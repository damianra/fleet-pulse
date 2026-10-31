"""Helpers compartidos entre routers (los `_*.py` no se auto-montan)."""
from fastapi import HTTPException


def get_or_404(db, model, id_, label):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f'{label} not found')
    return obj


def paginate(query, page: int, limit: int, sort_col=None, order: str = 'asc'):
    if sort_col is not None:
        query = query.order_by(sort_col.desc() if order == 'desc' else sort_col.asc())
    return query.offset((page - 1) * limit).limit(limit).all()


def sortable(model, sort_by: str, allowed: set, default_col):
    if sort_by and sort_by in allowed:
        return getattr(model, sort_by)
    return default_col
