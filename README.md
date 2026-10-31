# FleetPulse

API de gestión de flota — Python + FastAPI + SQLAlchemy, DB via
`DATABASE_URL` (sqlite local por default), migraciones Alembic.

## Usuarios demo

| Email | Password | Rol |
| --- | --- | --- |
| `admin@fleetpulse.dev` | `admin1234` | admin |
| `dispatcher@fleetpulse.dev` | `demo1234` | dispatcher |
| `driver@fleetpulse.dev` | `demo1234` | driver |
| `viewer@fleetpulse.dev` | `demo1234` | viewer |

Los drivers 1-30 del seed (`driver001@fleetpulse.dev`…`driver030@`) usan `demo1234`.

El primer usuario registrado queda `admin` (bootstrap); los registros
posteriores son `viewer` salvo que los cree un admin autenticado.

## Comandos

```bash
.venv/bin/uvicorn app.main:app --port 4000   # API en :4000
.venv/bin/python seed_demo.py              # puebla la DB con datos demo (aditivo, requiere faker en .venv)
.venv/bin/python -m pytest                   # tests
.venv/bin/alembic upgrade head               # migraciones pendientes
```
