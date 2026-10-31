// Vista Maintenance — próximos servicios + historial.
import { CalendarClock, CheckCircle2, Wrench } from 'lucide-react';
import { useApi } from '../hooks/useApi.js';
import { api, asArray, pick } from '../lib/api.js';
import { fmtDate, fmtKm, fmtMoney } from '../lib/format.js';
import {
  ActionBtn,
  EmptyBlock,
  ErrorBlock,
  Panel,
  SkeletonRows,
  StatusBadge,
} from '../components/shell.jsx';

export default function Maintenance() {
  const upcoming = useApi('/api/maintenance/upcoming', { interval: 60000 });
  const all = useApi('/api/maintenance', { interval: 60000 });

  const next = asArray(upcoming.data);
  const records = asArray(all.data);

  const complete = async (r) => {
    const id = pick(r, 'id', 'record_id', 'maintenance_id');
    if (!id) return;
    try {
      await api(`/api/maintenance/${id}/complete`, { method: 'POST' });
      upcoming.refetch(true);
      all.refetch(true);
    } catch {
      // poll
    }
  };

  const isOverdue = (r) => {
    const due = pick(r, 'due_date', 'scheduled_date', 'date');
    return due && new Date(due) < new Date() && pick(r, 'status') !== 'completed';
  };

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title="Próximos servicios" subtitle="mantenimiento programado" className="animate-fade-up">
        {upcoming.loading ? (
          <SkeletonRows rows={4} />
        ) : upcoming.error ? (
          <ErrorBlock onRetry={upcoming.refetch} />
        ) : next.length === 0 ? (
          <EmptyBlock icon={CheckCircle2} title="Flota al día" message="No hay servicios pendientes." />
        ) : (
          <ul className="space-y-2">
            {next.map((r, i) => {
              const overdue = isOverdue(r);
              return (
                <li
                  key={pick(r, 'id', 'record_id') ?? i}
                  className={`flex items-center gap-3 rounded-xl p-4 ring-1 transition animate-fade-up ${
                    overdue ? 'bg-red-500/5 ring-red-500/25' : 'bg-slate-950/50 ring-slate-800'
                  }`}
                >
                  <span className={`grid size-9 shrink-0 place-items-center rounded-lg ring-1 ${overdue ? 'bg-red-500/10 text-red-400 ring-red-500/25' : 'bg-violet-500/10 text-violet-400 ring-violet-500/25'}`}>
                    <CalendarClock size={16} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-100">
                      {pick(r, 'type', 'service_type', 'title', 'description') ?? 'Service'}
                    </p>
                    <p className="text-[11px] text-slate-500">
                      {pick(r, 'vehicle_plate', 'vehicle', 'vehicle_id') ?? '—'} ·{' '}
                      {fmtDate(pick(r, 'due_date', 'scheduled_date', 'date'))}
                      {pick(r, 'due_odometer', 'odometer_due') != null && ` · ${fmtKm(pick(r, 'due_odometer', 'odometer_due'))}`}
                    </p>
                  </div>
                  {overdue && <StatusBadge status="overdue" />}
                  <ActionBtn onClick={() => complete(r)}>Completar</ActionBtn>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Panel title="Historial" subtitle="registros de mantenimiento" className="animate-fade-up">
        {all.loading ? (
          <SkeletonRows rows={4} />
        ) : all.error ? (
          <ErrorBlock onRetry={all.refetch} />
        ) : records.length === 0 ? (
          <EmptyBlock icon={Wrench} message="Sin registros de mantenimiento." />
        ) : (
          <ul className="space-y-2">
            {records.slice(0, 12).map((r, i) => (
              <li
                key={pick(r, 'id', 'record_id') ?? i}
                className="flex items-center gap-3 rounded-xl bg-slate-950/50 p-4 ring-1 ring-slate-800"
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-slate-800 text-slate-400 ring-1 ring-slate-700">
                  <Wrench size={15} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-slate-200">
                    {pick(r, 'type', 'service_type', 'title', 'description') ?? 'Service'}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {pick(r, 'vehicle_plate', 'vehicle', 'vehicle_id') ?? '—'} ·{' '}
                    {fmtDate(pick(r, 'completed_at', 'date', 'performed_at'))}
                    {pick(r, 'cost', 'total_cost') != null && ` · ${fmtMoney(pick(r, 'cost', 'total_cost'))}`}
                  </p>
                </div>
                <StatusBadge status={pick(r, 'status') ?? 'completed'} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
