"""Auth FleetPulse — JWT en cookie httpOnly (perfil compliance auth).
El token nunca se devuelve en el body ni se guarda en localStorage:
login/register setean cookies `auth` + `csrf`; el front solo hace
fetch con credentials:'include' y reenvía el csrf como header.

Bootstrap: el PRIMER usuario registrado queda `admin`; después, register
público crea `viewer` (un admin autenticado puede crear otros roles)."""
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, utcnow
from ..schemas import (ChangePasswordIn, LoginIn, ProfileUpdateIn,
                       RegisterIn, UserAdminUpdateIn, UserOut)
from ..security import (clear_auth_cookies, get_current_user,
                        get_optional_user, hash_password,
                        issue_auth_cookies, require_roles,
                        validate_credentials, verify_password)
from ._common import get_or_404

router = APIRouter()


@router.post('/register', response_model=UserOut, status_code=201)
def register(payload: RegisterIn, response: Response,
             db: Session = Depends(get_db),
             current=Depends(get_optional_user)):
    validate_credentials(payload.email, payload.password)
    email = payload.email.lower().strip()
    first_user = db.query(User).count() == 0
    # Rol: admin solo si es el primer usuario o lo pide un admin.
    if first_user:
        role = 'admin'
    elif current is not None and current.role == 'admin':
        role = payload.role or 'viewer'
    else:
        role = 'viewer'
    user = User(email=email, hashed_password=hash_password(payload.password),
                full_name=payload.full_name, role=role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'email ya registrado')
    db.refresh(user)
    # Login implícito solo en el registro público (viewer o primer admin).
    if current is None:
        issue_auth_cookies(response, user)
    return user


@router.post('/login', response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    email = (payload.email or '').lower().strip()
    user = db.query(User).filter(User.email == email).first()
    # 401 genérico — no distinguir "no existe" de "password mal".
    if user is None or not verify_password(payload.password or '', user.hashed_password):
        raise HTTPException(401, 'credenciales inválidas')
    if not user.is_active:
        raise HTTPException(401, 'credenciales inválidas')
    user.last_login = utcnow()
    db.commit()
    issue_auth_cookies(response, user)
    return user


@router.post('/logout', status_code=204)
def logout(response: Response):
    clear_auth_cookies(response)


@router.post('/refresh', response_model=UserOut)
def refresh(response: Response, user: User = Depends(get_current_user)):
    issue_auth_cookies(response, user)
    return user


@router.get('/me', response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.put('/me', response_model=UserOut)
def update_me(payload: ProfileUpdateIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    if payload.full_name is not None:
        user.full_name = payload.full_name
    db.commit()
    db.refresh(user)
    return user


@router.post('/change-password', status_code=204)
def change_password(payload: ChangePasswordIn, response: Response,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not verify_password(payload.current_password or '', user.hashed_password):
        raise HTTPException(401, 'credenciales inválidas')
    if not payload.new_password or len(payload.new_password) < 8:
        raise HTTPException(400, 'password debe tener al menos 8 caracteres')
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    clear_auth_cookies(response)  # re-login requerido


@router.get('/users', response_model=list[UserOut])
def list_users(db: Session = Depends(get_db),
               _admin: User = Depends(require_roles('admin'))):
    return db.query(User).order_by(User.created_at).all()


@router.put('/users/{user_id}', response_model=UserOut)
def update_user(user_id: str, payload: UserAdminUpdateIn,
                db: Session = Depends(get_db),
                _admin: User = Depends(require_roles('admin'))):
    user = get_or_404(db, User, user_id, 'user')
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user
