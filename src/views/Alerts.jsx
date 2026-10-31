// Vista Alerts — feed con severidad + acknowledge/resolve.
import { useMemo, useState } from 'react';
import { BellRing, CheckCheck, ShieldAlert } from 'lucide-react';
import { useApi } from '../hooks/useApi.js';
import { api, asArray, pick } from '../lib/api.js';
import { fmtNum, timeAgo } from '../lib/format.js';
import {
  ActionBtn,
  EmptyBlock,
  ErrorBlock,
  Kpi,
  Panel,
  SkeletonRows,
  StatusBadge,
} from '../components/shell.jsx';

const num = (o, ...k) => Number(pick(o ?? {}, ...k) ?? 0) || 0;

const FILTERS = [
  ['all', 'Todas'],
  ['active', 'Activas'],
  ['acknowledged', 'Reconocidas'],
  ['resolved', 'Resueltas'],
];

const SEV_ICON = {
  critical: ShieldAlert,
  high: ShieldAlert,
  warning: BellRing,
  medium: BellRing,
};

export default function Alerts() {
  const [filter, setFilter] = useState('all');
  const list = useApi('/api/alerts', { interval: 15000 });
  const stats = useApi('/api/alerts/stats', { interval: 30000 });

  const alerts = asArray(list.data);
  const st = stats.data ?? {};

  const filtered = useMemo(
    () =>
      filter === 'all'
        ? alerts
        : alerts.filter((a) =>
            filter === 'active'
              ? !['resolved', 'acknowledged'].includes(pick(a, 'status', 'state'))
              : (pick(a, 'status', 'state') ?? 'active') === filter,
          ),
    [alerts, filter],
  );

  const act = async (a, action) => {
    const id = pick(a, 'id', 'alert_id', 'alertId');
    if (!id) return;
    try {
      await api(`/api/alerts/${id}/${action}`, { method: 'POST' });
      list.refetch(true);
      stats.refetch(true);
    } catch {
      // poll refleja el cambio
    }
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Kpi icon={BellRing} label="Activas" tone="amber" value={fmtNum(num(st, 'active', 'total_active') || alerts.filter((a) => !['resolved', 'acknowledged'].includes(pick(a, 'status'))).length)} loading={list.loading} />
        <Kpi icon={ShieldAlert} label="Críticas" tone="red" value={fmtNum(num(st, 'critical', 'critical_count'))} loading={stats.loading} />
        <Kpi icon={CheckCheck} label="Reconocidas" value={fmtNum(num(st, 'acknowledged'))} loading={stats.loading} />
        <Kpi icon={CheckCheck} label="Resueltas hoy" tone="emerald" value={fmtNum(num(st, 'resolved', 'resolved_today'))} loading={stats.loading} />
      </div>

      <Panel title="Feed de alertas" subtitle={`${filtered.length} de ${alerts.length}`}>
        <div className="mb-4 flex flex-wrap gap-1.5">
          {FILTERS.map(([id, label]) => (
            <button
              key={id}
              onClick={() => setFilter(id)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition ${
                filter === id
                  ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
                  : 'bg-slate-900 text-slate-400 ring-slate-800 hover:text-slate-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {list.loading ? (
          <SkeletonRows rows={6} />
        ) : list.error ? (
          <ErrorBlock onRetry={list.refetch} />
        ) : filtered.length === 0 ? (
          <EmptyBlock icon={CheckCheck} title="Bandeja limpia" message="No hay alertas en esta categoría." />
        ) : (
          <ul className="space-y-2">
            {filtered.map((a, i) => {
              const id = pick(a, 'id', 'alert_id') ?? i;
              const severity = pick(a, 'severity', 'priority') ?? 'info';
              const status = pick(a, 'status', 'state') ?? 'active';
              const Icon = SEV_ICON[severity] ?? BellRing;
              const resolved = status === 'resolved';
              return (
                <li
                  key={id}
                  className={`flex items-start gap-3 rounded-xl p-4 ring-1 transition animate-fade-up ${
                    severity === 'critical' || severity === 'high'
                      ? 'bg-red-500/5 ring-red-500/20'
                      : 'bg-slate-950/50 ring-slate-800'
                  } ${resolved ? 'opacity-50' : ''}`}
                >
                  <span
                    className={`mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg ring-1 ${
                      severity === 'critical' || severity === 'high'
                        ? 'bg-red-500/10 text-red-400 ring-red-500/25'
                        : severity === 'warning' || severity === 'medium'
                          ? 'bg-amber-500/10 text-amber-400 ring-amber-500/25'
                          : 'bg-sky-500/10 text-sky-400 ring-sky-500/25'
                    }`}
                  >
                    <Icon size={15} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-slate-100">
                        {pick(a, 'title', 'type', 'alert_type') ?? 'Alerta'}
                      </p>
                      <StatusBadge status={severity} />
                      <StatusBadge status={status} />
                    </div>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {pick(a, 'message', 'description', 'detail') ?? ''}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-500">
                      {[pick(a, 'vehicle_plate', 'vehicle', 'vehicle_id'), pick(a, 'driver_name', 'driver')]
                        .filter(Boolean)
                        .join(' · ')}
                      {' · '}
                      {timeAgo(pick(a, 'created_at', 'timestamp', 'time'))}
                    </p>
                  </div>
                  {!resolved && (
                    <div className="flex shrink-0 gap-1.5">
                      {status !== 'acknowledged' && (
                        <ActionBtn tone="slate" onClick={() => act(a, 'acknowledge')}>Reconocer</ActionBtn>
                      )}
                      <ActionBtn onClick={() => act(a, 'resolve')}>Resolver</ActionBtn>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
