// Formatters compartidos — tolerantes a campos faltantes.

export const fmtNum = (n, digits = 0) =>
  n === null || n === undefined || Number.isNaN(Number(n))
    ? '—'
    : Number(n).toLocaleString('es-AR', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });

export const fmtPct = (n, digits = 0) =>
  n === null || n === undefined || Number.isNaN(Number(n))
    ? '—'
    : `${fmtNum(n, digits)}%`;

export const fmtKm = (n) =>
  n === null || n === undefined ? '—' : `${fmtNum(n)} km`;

export const fmtMoney = (n) =>
  n === null || n === undefined
    ? '—'
    : `$${fmtNum(n, 0)}`;

export function fmtDate(d, withTime = false) {
  if (!d) return '—';
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return '—';
  return dt.toLocaleDateString('es-AR', {
    day: '2-digit',
    month: 'short',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  });
}

/** "hace 5 min", "hace 2 h", "ayer"… */
export function timeAgo(d) {
  if (!d) return '—';
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return '—';
  const s = Math.max(0, (Date.now() - dt.getTime()) / 1000);
  if (s < 60) return 'ahora';
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  const days = Math.floor(s / 86400);
  return days === 1 ? 'ayer' : `hace ${days} días`;
}

export const STATUS_LABELS = {
  active: 'Activo',
  available: 'Disponible',
  in_transit: 'En tránsito',
  'in-transit': 'En tránsito',
  en_route: 'En ruta',
  idle: 'En espera',
  offline: 'Offline',
  maintenance: 'Mantenimiento',
  pending: 'Pendiente',
  scheduled: 'Programado',
  assigned: 'Asignado',
  started: 'Iniciado',
  in_progress: 'En curso',
  completed: 'Completado',
  delivered: 'Entregado',
  failed: 'Fallido',
  cancelled: 'Cancelado',
  resolved: 'Resuelto',
  acknowledged: 'Reconocido',
  critical: 'Crítico',
  warning: 'Advertencia',
  info: 'Info',
  high: 'Alta',
  medium: 'Media',
  low: 'Baja',
  overdue: 'Vencido',
  optimizing: 'Optimizando',
  optimized: 'Optimizado',
  on_shift: 'En turno',
  off_shift: 'Fuera de turno',
};

export const statusLabel = (s) => STATUS_LABELS[s] ?? (s ? s.replace(/_/g, ' ') : '—');
