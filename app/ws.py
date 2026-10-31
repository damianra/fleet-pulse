"""ConnectionManager para WS /api/tracking/live — tracking en tiempo
real. Con REDIS_URL configurado los POSTs de tracking y el motor de
alertas publican en el canal Redis (app/bus.py) y TODOS los workers
reenvían a sus sockets locales — el update puede caer en un worker
distinto del que tiene el WS. Sin REDIS_URL → broadcast local directo
(modo single-process).

Protocolo del cliente:
- Conectar a ws://host/api/tracking/live (auth via cookie `auth` o
  ?token=<jwt> para apps móviles).
- Suscribirse: {"type":"subscribe","vehicles":["<id>",...]} —
  sin "vehicles" (o vacío) recibe TODAS las actualizaciones.
- Mensajes salientes:
  {"type":"location_update","vehicle_id":...,"data":{...}} y
  {"type":"alert","vehicle_id":...,"alert_id":...,"data":{...}} —
  data de alert = mismo shape que GET /api/alerts; el filtro de
  suscripción aplica igual (alertas sin vehicle_id solo llegan a
  suscriptores de "todos").
"""
import asyncio

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._subs = {}  # websocket -> set(vehicle_id) | None(todos)
        self.loop = None  # loop del app, capturado al conectar el 1er WS

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._subs[ws] = None
        self.loop = asyncio.get_running_loop()

    def disconnect(self, ws: WebSocket):
        self._subs.pop(ws, None)

    def subscribe(self, ws: WebSocket, vehicle_ids):
        self._subs[ws] = set(vehicle_ids) if vehicle_ids else None

    async def broadcast(self, message: dict):
        dead = []
        for ws, vehicles in self._subs.items():
            vid = message.get('vehicle_id')
            if vehicles is not None and vid not in vehicles:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_threadsafe(self, message: dict):
        """Llamable desde endpoints sync (threadpool): si el bus Redis
        está activo publica en el canal (llega a los sockets de TODOS
        los workers); si no, agenda el broadcast local en el loop de la
        app. Si el loop capturado ya cerró, descarta el mensaje."""
        from . import bus
        if bus.publish_threadsafe(message):
            return
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        coro = self.broadcast(message)
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            coro.close()
            self.loop = None


manager = ConnectionManager()
