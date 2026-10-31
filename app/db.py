"""Capa de datos: SQLAlchemy 2 sobre `DATABASE_URL` (env, default
sqlite local). Espejo de `server/db.js` del api-skeleton Express:
engine único, `get_db` como dependencia FastAPI e `init_db()`
idempotente (migraciones Alembic a head + seed solo si está vacío).

Migraciones: `run_migrations()` aplica `alembic upgrade head` con el
mismo engine (alembic/env.py lo toma de config.attributes). Las DBs
creadas por create_all antes de Alembic (sin tabla alembic_version)
se completan con create_all (solo agrega lo que falte) y se marcan
con `stamp head` — así conviven upgrades reales y legacy."""
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./app.db')
ALEMBIC_INI = Path(__file__).resolve().parent.parent / 'alembic.ini'

# sqlite necesita check_same_thread=False con el thread pool de
# FastAPI; los engines TCP (postgres/mysql) no aceptan ese arg.
connect_args = {'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations(eng=None):
    from alembic import command
    from alembic.config import Config

    eng = eng or engine
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes['engine'] = eng
    insp = inspect(eng)
    if not insp.has_table('alembic_version') and insp.get_table_names():
        # Schema legacy pre-Alembic: completar drift (create_all solo
        # agrega tablas faltantes) y marcar como migrada a head.
        Base.metadata.create_all(eng)
        command.stamp(cfg, 'head')
    else:
        command.upgrade(cfg, 'head')


def init_db():
    # Importar models/seed acá registra las entities en Base.metadata
    # antes de migrar (evita el import circular arriba). SEED_DEMO=false
    # saltea los datos demo de flota (producción arranca con tablas
    # vacías — el primer usuario registrado queda admin).
    from . import models, seed

    run_migrations()
    if os.getenv('SEED_DEMO', 'true').lower() == 'false':
        return
    db = SessionLocal()
    try:
        seed.seed_if_empty(db)
    finally:
        db.close()
