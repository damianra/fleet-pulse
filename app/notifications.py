"""Notificaciones por email de alertas nuevas — SMTP por env.

Se engancha en `alerts_engine.broadcast_alerts`, el punto único por
donde pasan TODAS las alertas recién creadas (motor de reglas del
lifespan + chequeos inline de tracking). El envío corre en un thread
daemon: nunca bloquea el request ni el loop, y los errores SMTP se
loguean sin propagarse — una notificación fallida no debe tirar el
flujo de alertas.

Env (ver .env.example):
- SMTP_HOST + ALERT_EMAIL_TO: requeridas — sin ambas es no-op.
- SMTP_PORT (default 587), SMTP_USER/SMTP_PASSWORD (opcional),
  SMTP_FROM, SMTP_TLS (STARTTLS, default true), SMTP_SSL (SSL directo,
  para puerto 465) y ALERT_EMAIL_SEVERITIES (default 'critical').
"""
import logging
import os
import smtplib
import threading
from email.message import EmailMessage

log = logging.getLogger('fleetpulse.notify')


def smtp_config():
    """Config SMTP desde env — None si falta host o destinatarios
    (módulo deshabilitado), o si la config es inválida."""
    host = os.getenv('SMTP_HOST', '').strip()
    to = [a.strip() for a in os.getenv('ALERT_EMAIL_TO', '').split(',')
          if a.strip()]
    if not host or not to:
        return None
    try:
        port = int(os.getenv('SMTP_PORT', '587'))
    except ValueError:
        log.warning('SMTP_PORT inválido — notificaciones deshabilitadas')
        return None
    return {'host': host, 'port': port,
            'user': os.getenv('SMTP_USER', ''),
            'password': os.getenv('SMTP_PASSWORD', ''),
            'tls': os.getenv('SMTP_TLS', 'true').lower() != 'false',
            'ssl': os.getenv('SMTP_SSL', '').lower() == 'true',
            'from': os.getenv('SMTP_FROM', f'fleetpulse@{host}'),
            'to': to}


def notify_severities():
    return {s.strip() for s in
            os.getenv('ALERT_EMAIL_SEVERITIES', 'critical').split(',')
            if s.strip()}


def build_email(alert, cfg):
    msg = EmailMessage()
    msg['From'] = cfg['from']
    msg['To'] = ', '.join(cfg['to'])
    severity = getattr(alert, 'severity', '') or ''
    msg['Subject'] = f"[FleetPulse] {severity.upper()}: {alert.title}"
    lines = [alert.description or '', '',
             f'tipo: {alert.type}',
             f'severidad: {severity}',
             f'disparada: {alert.triggered_at}']
    for field in ('vehicle_id', 'driver_id', 'route_id', 'delivery_id'):
        val = getattr(alert, field, None)
        if val:
            lines.append(f'{field}: {val}')
    meta = getattr(alert, 'alert_metadata', None)
    if meta:
        lines.append(f'metadata: {meta}')
    msg.set_content('\n'.join(lines))
    return msg


def _send_all(msgs, cfg):
    """Una sola conexión SMTP para todos los mensajes del batch."""
    try:
        cls = smtplib.SMTP_SSL if cfg['ssl'] else smtplib.SMTP
        with cls(cfg['host'], cfg['port'], timeout=10) as smtp:
            if cfg['tls'] and not cfg['ssl']:
                smtp.starttls()
            if cfg['user']:
                smtp.login(cfg['user'], cfg['password'])
            for msg in msgs:
                smtp.send_message(msg)
    except Exception as exc:
        log.warning('envío de alertas por email falló: %s', exc)


def notify_new_alerts(alerts):
    """Emails para las alertas nuevas con severidad notificable.

    Construye los EmailMessage en el thread caller — los ORM objects
    pueden quedar detached cuando el thread daemon corra — y delega
    solo el I/O SMTP. Devuelve el thread lanzado (los tests pueden
    joinearlo) o None si no había nada que mandar."""
    try:
        cfg = smtp_config()
        if cfg is None:
            return None
        targets = notify_severities()
        emails = [build_email(a, cfg) for a in (alerts or [])
                  if a is not None
                  and getattr(a, 'severity', None) in targets]
        if not emails:
            return None
        t = threading.Thread(target=_send_all, args=(emails, cfg),
                             daemon=True)
        t.start()
        return t
    except Exception as exc:
        log.warning('notify_new_alerts falló: %s', exc)
        return None
