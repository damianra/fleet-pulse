"""Bus de coordinación multi-worker via Redis pub/sub — activo solo si
REDIS_URL está configurado; sin URL el proceso corre en modo
single-process (broadcast local directo, líder permanente).

Con REDIS_URL:

- **Broadcast WS**: `publish` manda el mensaje al canal REDIS_CHANNEL;
  cada worker corre un listener que lo reenvía a sus sockets locales
  → un POST /api/tracking/update que cae en el worker A llega a los WS
  suscritos en el worker B (self-delivery por la propia suscripción, el
  emisor no hace broadcast local por separado).
- **Liderazgo de loops**: lease `REDIS_LEADER_KEY` (SET worker_id NX EX
  + renovación). Solo el líder corre los loops en-proceso (alertas,
  archivado, métricas); si el proceso líder muere, el TTL vence y otro
  worker toma el liderazgo. Permite escalar la API en N réplicas todas
  con RUN_BACKGROUND_LOOPS=true sin duplicar trabajos (ante un overlap
  breve, el dedup `_exists_active` del motor cubre dobles disparos).

Degradación: si REDIS_URL está set pero Redis no responde al boot, el
bus queda deshabilitado con un warning — la app sigue en modo local.
"""
import asyncio
import json
import logging
import os
import uuid

log = logging.getLogger('fleetpulse.bus')

REDIS_URL = os.getenv('REDIS_URL', '')
CHANNEL = os.getenv('REDIS_CHANNEL', 'fleetpulse:ws')
LEADER_KEY = os.getenv('REDIS_LEADER_KEY', 'fleetpulse:leader')
LEADER_TTL_S = int(os.getenv('REDIS_LEADER_TTL_S', '30'))
LEADER_RENEW_S = max(1, LEADER_TTL_S // 3)

client = None          # redis.asyncio client — None = bus deshabilitado
worker_id = uuid.uuid4().hex
_pubsub = None
_listener = None       # task asyncio del subscriber
_loop = None           # loop de la app, capturado en start()
_on_message = None     # callable async (dict) → entrega local (ws.manager.broadcast)


def enabled() -> bool:
    return client is not None


async def start(on_message):
    """Conecta a Redis, suscribe el canal y levanta el listener.
    `on_message` recibe cada mensaje publicado (propio o de otros
    workers) y lo entrega a los sockets locales. Llamar desde el
    lifespan — captura el loop de la app para publish_threadsafe."""
    global client, _pubsub, _listener, _loop, _on_message
    _on_message = on_message
    _loop = asyncio.get_running_loop()
    if not REDIS_URL:
        return
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await client.ping()
        _pubsub = client.pubsub()
        await _pubsub.subscribe(CHANNEL)
        _listener = asyncio.create_task(_listen())
        log.info('bus redis activo — canal %s (worker %s)',
                 CHANNEL, worker_id[:8])
    except Exception as exc:
        log.warning('REDIS_URL set pero Redis no responde (%s) '
                    '— modo single-process', exc)
        client = None


async def stop():
    global client, _pubsub, _listener
    if _listener is not None:
        _listener.cancel()
        try:
            await _listener
        except asyncio.CancelledError:
            pass
        _listener = None
    if _pubsub is not None:
        try:
            await _pubsub.unsubscribe(CHANNEL)
            await _pubsub.aclose()
        except Exception:
            pass
        _pubsub = None
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            pass
        client = None


async def _listen():
    """Loop del subscriber: reenvía cada mensaje del canal a los
    sockets locales. Si la conexión se cae, re-suscribe y sigue."""
    while True:
        try:
            async for raw in _pubsub.listen():
                if raw.get('type') != 'message':
                    continue
                try:
                    await _on_message(json.loads(raw['data']))
                except Exception as exc:
                    log.warning('mensaje de bus inválido: %s', exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning('listener caído (%s) — re-suscribiendo', exc)
            try:
                await _pubsub.subscribe(CHANNEL)
            except Exception:
                pass
            await asyncio.sleep(1)


async def publish(message) -> bool:
    """Publica al canal. False si el bus está deshabilitado."""
    if client is None:
        return False
    await client.publish(CHANNEL, json.dumps(message))
    return True


async def _publish_or_local(message):
    try:
        await publish(message)
    except Exception as exc:
        log.warning('publish falló (%s) — broadcast local', exc)
        if _on_message is not None:
            await _on_message(message)


def publish_threadsafe(message) -> bool:
    """Encola un publish al canal en el loop de la app — llamable desde
    endpoints sync (threadpool) y threads de los loops. True si quedó
    encolado; False si el bus está off o el loop murió → el caller hace
    el broadcast local directo."""
    if client is None or _loop is None or _loop.is_closed():
        return False
    coro = _publish_or_local(message)
    try:
        asyncio.run_coroutine_threadsafe(coro, _loop)
        return True
    except RuntimeError:
        coro.close()
        return False


async def acquire_or_renew_leadership() -> bool:
    """True si este worker tiene el lease de líder. Sin Redis → siempre
    líder (single-process). El lease expira solo si el líder muere —
    otro worker lo toma al vencer el TTL."""
    if client is None:
        return True
    try:
        if await client.set(LEADER_KEY, worker_id, nx=True,
                            ex=LEADER_TTL_S):
            return True
        if await client.get(LEADER_KEY) == worker_id:
            await client.expire(LEADER_KEY, LEADER_TTL_S)
            return True
        return False
    except Exception as exc:
        log.warning('leader check falló (%s) — asumo no-líder', exc)
        return False


async def leader_supervisor(start_loops):
    """Supervisa el lease: mantiene los loops corriendo solo mientras
    este worker sea líder; si lo pierde los cancela, si lo gana los
    arranca. `start_loops` → list[asyncio.Task]."""
    tasks = []
    try:
        while True:
            leader = await acquire_or_renew_leadership()
            if leader and not tasks:
                tasks = start_loops()
                log.info('worker %s líder — loops activos', worker_id[:8])
            elif not leader and tasks:
                for t in tasks:
                    t.cancel()
                tasks = []
                log.info('worker %s cedió liderazgo — loops pausados',
                         worker_id[:8])
            await asyncio.sleep(LEADER_RENEW_S)
    finally:
        for t in tasks:
            t.cancel()
