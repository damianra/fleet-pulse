# Convenciones del proyecto

Este proyecto fue generado por MetaBuilder. Stack esperado:

- **Frontend**: React + Vite + Tailwind CSS (si aplica)
- **Backend**: Python + FastAPI (si aplica)
- **Base de datos**: SQLAlchemy via DATABASE_URL en .env (sqlite local default; postgres/mysql por URL + driver pip) (si aplica)
- **Testing**: Vitest + pytest (unit/integración), Playwright + Chromium (E2E, si hay frontend)

## Reglas de UI obligatorias (React + Tailwind)

1. No agregar propiedades a componentes no utilizados; confiar solo en los datos disponibles del backend.
2. Los componentes no soportados no deben renderizar y no deben romper el flujo de la aplicación (fallback silencioso o controlado).
3. Si una URL está vacía, no se debe mostrar ningún icono ni intentar abrirse ninguna ventana.
4. Los botones de acción (ej. "Guardar", "Enviar") deben estar deshabilitados (`disabled`) por defecto y solo habilitarse cuando se detecten cambios reales en los campos del formulario.
5. Si una consulta a la API no devuelve resultados, la UI debe mostrar un estado de fallback informativo (nunca una pantalla en blanco o un error crudo).

## Guía de diseño (obligatoria — el resultado debe verse moderno y limpio)

- **Íconos**: usar `lucide-react` (ya instalado). NUNCA cuadrados/círculos de color como placeholder de ícono — si un dato no tiene ícono propio, usar uno genérico (`Sparkles`) o nada. La data puede llevar un campo `icon` con nombre en kebab-case mapeado a componentes.
- **Paleta**: neutra (slate/stone/zinc) + 1 color de acento — máximo 2 colores de marca en toda la página.
- **Tipografía**: system-ui/Inter; headings `font-bold tracking-tight` (`text-3xl`–`text-5xl`), body `text-sm/base`, contraste alto.
- **Layout**: contenedores `max-w-6xl mx-auto px-6`; secciones `py-16` o `py-24`; grids `gap-6`/`gap-8`.
- **Cards**: `rounded-2xl bg-white ring-1 ring-<neutro>-200 shadow-sm hover:shadow-md transition`.
- **Botones**: `rounded-full` o `rounded-lg`, `px-6 py-3 font-semibold`; primario sólido + `hover:` visible; secundario outline.
- **Hero**: gradiente sutil (`bg-gradient-to-b`) o fondo sólido oscuro + badge/logo con ícono Lucide real; nunca un div vacío de color.
- **Navbar** simple con nombre/logo + links de ancla a las secciones.
- Contenido no provisto por el usuario → lorem ipsum breve; bloque con ícono Lucide si no hay imagen.
- **Imágenes (licencias)**: la app puede venderse — SOLO imágenes con licencia que permita **uso comercial + redistribución**: `images.unsplash.com` (Unsplash License), `images.pexels.com` (Pexels License), `cdn.pixabay.com` (Pixabay Content License). **Prohibido** hotlink (la request expone la IP del visitante y la URL puede rotar): la imagen se **descarga a `public/images/`** y se referencia local; registrar fuente+licencia en `public/images/LICENSES.txt`. Nunca Google images ni fuentes arbitrarias (licencia no verificable); si ninguna fuente libre aplica (o el usuario exige una imagen que no puede verificarse), usar el `public/images/placeholder.svg` del skeleton (bloque dashed "Seleccionar imagen" — el usuario reemplaza el archivo; es asset propio, sin licencia) — nunca imagen remota ni `<img>` vacío.


## Kit de componentes (`src/components/ui.jsx`)

El skeleton trae bloques pre-styled — **componerlos/parametrizarlos,
no reescribirlos**: `Section`, `Navbar`, `Hero`, `Card`, `StatCard`,
`EmptyState`, `ErrorState`, `FormShell` (submit gateado por `disabled`),
`CTA`. Acento configurable: `accent="indigo|emerald|amber"` (mapa de
clases literales — Tailwind no genera clases dinámicas). Si un bloque
necesita variante, extenderlo con `className` antes que duplicar markup.

## Reglas de privacidad y seguridad (obligatorias)

- Todo formulario que capture datos personales exige un checkbox **no pre-tildado** "Acepto la política de privacidad" (link a `/privacidad`) — el botón de enviar solo se habilita marcado.
- Debe existir una página/sección `/privacidad` con aviso de datos (qué se recolecta, finalidad, retención, derechos ARCO, contacto del responsable) y link visible en el footer.
- Prohibido scripts de terceros con cookies/trackers (analytics, pixels, embebidos con tracking) sin banner de consentimiento previo.
- Nunca `dangerouslySetInnerHTML` con datos de usuario o de la API.
- SQL siempre con prepared statements — nunca interpolar valores en queries.
- Secretos solo en `.env` (gitignored); declarar en `.env.example`. Nunca en logs ni en el bundle del frontend.


## Comandos que deben existir

- `npm run build` — build de producción
- `npm run dev` — dev server en puerto 5173
- `npx vitest run` — suite Vitest
- `npm run test:e2e` — suite e2e
- `.venv/bin/uvicorn app.main:app --port 4000` — API en puerto 4000
- `.venv/bin/python -m pytest` — suite pytest

## Notas para el agente que escribe código

- Mantener los pasos atómicos y autocontenidos: cada tarea debe dejar el proyecto en un estado compilable.
- **Estado (front)**: `lib/api.js` como cliente único del backend (fetch + error handling centralizado); `useState` local por componente, `useReducer` para flujos multi-paso (formularios/wizard/cart). Sin librería de estado (Redux/Zustand/MobX) — fuera del scope: rápido, funcional, fácil de conectar front↔back.
- Si la app tiene login/usuarios del seed, documentarlos en el README (sección 'Usuarios demo' con email+password dev y el rol de cada uno).
- Al final del README, una sección 'Prompt' con el prompt original del usuario (si el plan tiene sección BACKEND, incluirla entera).
- No commitear `node_modules/`, `.env`, `*.sqlite`, `server/uploads/*`, `dist/`, `out/` ni `build/`.
- Al escribir tests E2E con Playwright, cubrir explícitamente las reglas de UI de arriba.
- **Backend**: cada `app/routers/<name>.py` con `APIRouter` se auto-monta en `/api/<name>` — no tocar `app/main.py` ni `app/db.py`. Models SQLAlchemy en `app/models.py`, schemas pydantic en `app/schemas.py`.
- **Capa de datos**: `app/db.py` con `DATABASE_URL` (sqlite por default — postgres/mysql via env); `init_db()` aplica las migraciones Alembic a head al arrancar; seed idempotente.
- **Migraciones (Alembic)**: el skeleton trae `alembic.ini` + `alembic/` configurados (env.py toma `DATABASE_URL` o el engine de `init_db`). Tras definir `app/models.py` generar la baseline con `.venv/bin/alembic revision --autogenerate -m "initial schema"` **contra una DB limpia** (borrar app.db o apuntar DATABASE_URL a un sqlite temporario — con tablas ya creadas el diff sale vacío) y verificar `.venv/bin/alembic upgrade head`. Todo cambio de schema posterior = nueva revisión autogenerada; prohibido `create_all`/DDL manual ni tocar `alembic_version`.
- **Sin uploads en el skeleton** — agregar como endpoint propio si hacen falta.
- **Secretos/config**: `.env` (gitignored) — `python-dotenv` ya cargado en `app/main.py`. Declarar toda variable en `.env.example`.
- **Docker**: los provee el orquestador — el contenedor corre `uvicorn app.main:app` (el backend sirve `dist/` si existe).

## Arquitectura backend

Toda la lógica del endpoint vive en `app/routers/<name>.py` (queries via `app/db.py`). Al agregar endpoints, mantener el mismo estilo — no crear services/repositories ni capas extra.
