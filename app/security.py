"""Autenticación FleetPulse — JWT dentro de cookie httpOnly (perfil
compliance `auth`): el token nunca viaja en body ni localStorage.

- `auth` cookie: JWT firmado con JWT_SECRET (HS256), payload {sub,email}.
- `csrf` cookie: token aleatorio NO-httpOnly — todo request que muta con
  cookie auth debe mandarlo en el header `x-csrf-token` (double-submit;
  el middleware de main.py lo valida). Los clientes Bearer (app móvil de
  conductores) están exentos porque CSRF solo aplica a cookies.
- Passwords: bcrypt (costo 12) — nunca texto plano ni en responses.
- JWT_SECRET: leído de env; si falta se genera uno efímero por proceso
  (dev/tests — en deploy va en .env, nunca commiteado).
"""
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

JWT_SECRET = os.getenv('JWT_SECRET') or secrets.token_hex(32)
JWT_ALG = 'HS256'
JWT_EXPIRES_S = int(os.getenv('JWT_EXPIRES_IN', '3600'))
AUTH_COOKIE = 'auth'
CSRF_COOKIE = 'csrf'
CSRF_HEADER = 'x-csrf-token'
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

if not os.getenv('JWT_SECRET'):
    print('WARN: JWT_SECRET no definido — usando secreto efímero (solo dev)')


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {'sub': user.id, 'email': user.email,
               'iat': now, 'exp': now + timedelta(seconds=JWT_EXPIRES_S)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


def issue_auth_cookies(response: Response, user: User) -> str:
    """Setea cookie `auth` (JWT httpOnly) + `csrf` (legible por el front
    para reenviarla como header). Devuelve el csrf token."""
    secure = os.getenv('NODE_ENV', os.getenv('ENV', '')) == 'production'
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(AUTH_COOKIE, create_token(user), httponly=True,
                        samesite='strict', secure=secure, max_age=JWT_EXPIRES_S)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False,
                        samesite='strict', secure=secure, max_age=JWT_EXPIRES_S)
    return csrf


def clear_auth_cookies(response: Response):
    response.delete_cookie(AUTH_COOKIE)
    response.delete_cookie(CSRF_COOKIE)


def _token_from_request(request: Request):
    token = request.cookies.get(AUTH_COOKIE)
    if token:
        return token
    # Bearer solo para consumidores externos (app móvil de tracking).
    auth = request.headers.get('authorization', '')
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(401, 'no autenticado')
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(401, 'token inválido o expirado')
    user = db.get(User, payload.get('sub', ''))
    if user is None or not user.is_active:
        raise HTTPException(401, 'usuario inválido o inactivo')
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)):
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


def require_roles(*roles: str):
    """Guard RBAC — `Depends(require_roles('admin','dispatcher'))` en
    endpoints de escritura."""
    def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, 'permisos insuficientes')
        return user
    return guard


def validate_credentials(email: str, password: str):
    """Validación manual → 400 (no 422) según el perfil auth."""
    if not EMAIL_RE.match(email or ''):
        raise HTTPException(400, 'email inválido')
    if not password or len(password) < 8:
        raise HTTPException(400, 'password debe tener al menos 8 caracteres')
    if len(password.encode()) > 128:
        raise HTTPException(400, 'password demasiado largo')
