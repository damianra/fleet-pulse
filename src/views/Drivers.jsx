// Vista Drivers — cards con performance + turnos.
import { BadgeCheck, Clock, Phone, Star, UserRound } from 'lucide-react';
import { useApi } from '../hooks/useApi.js';
import { api, asArray, pick } from '../lib/api.js';
import { fmtNum, fmtPct } from '../lib/format.js';
import {
  ActionBtn,
  EmptyBlock,
  ErrorBlock,
  Panel,
  SkeletonRows,
  StatusBadge,
} from '../components/shell.jsx';

export default function Drivers() {
  const list = useApi('/api/drivers', { interval: 25000 });
  const analytics = useApi('/api/analytics/drivers', { interval: 60000 });

  const drivers = asArray(list.data);
  const perf = asArray(analytics.data);
  const perfById = Object.fromEntries(
    perf.map((p) => [pick(p, 'driver_id', 'id') ?? pick(p, 'name'), p]),
  );

  const toggleShift = async (d, onShift) => {
    const id = pick(d, 'id', 'driver_id', 'driverId');
    if (!id) return;
    try {
      await api(`/api/drivers/${id}/${onShift ? 'end-shift' : 'start-shift'}`, { method: 'POST' });
      list.refetch(true);
    } catch {
      // lo refleja el próximo poll
    }
  };

  return (
    <Panel title="Choferes" subtitle={`${drivers.length} registrados`}>
      {list.loading ? (
        <SkeletonRows rows={5} />
      ) : list.error ? (
        <ErrorBlock onRetry={list.refetch} />
      ) : drivers.length === 0 ? (
        <EmptyBlock icon={UserRound} message="Sin choferes registrados todavía." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {drivers.map((d, i) => {
            const id = pick(d, 'id', 'driver_id') ?? i;
            const p = perfById[id] ?? perfById[pick(d, 'name')] ?? {};
            const onShift = ['on_shift', 'active', 'driving'].includes(pick(d, 'shift_status', 'status') ?? '');
            const rating = pick(p, 'rating', 'score') ?? pick(d, 'rating');
            const done = pick(p, 'deliveries_completed', 'completed', 'deliveries') ?? pick(d, 'deliveries_completed');
            const onTime = pick(p, 'on_time_rate', 'on_time_pct') ?? pick(d, 'on_time_rate');
            return (
              <article
                key={id}
                className="rounded-2xl bg-slate-950/50 p-4 ring-1 ring-slate-800 transition hover:ring-slate-700 animate-fade-up"
              >
                <div className="flex items-center gap-3">
                  <span className="grid size-10 shrink-0 place-items-center rounded-full bg-emerald-500/15 text-sm font-bold text-emerald-300 ring-1 ring-emerald-500/30">
                    {(pick(d, 'name', 'full_name') ?? '?').slice(0, 2).toUpperCase()}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-100">
                      {pick(d, 'name', 'full_name') ?? `Chofer ${id}`}
                    </p>
                    <p className="flex items-center gap-1 truncate text-[11px] text-slate-500">
                      <Phone size={10} /> {pick(d, 'phone', 'phone_number') ?? pick(d, 'license', 'license_number') ?? '—'}
                    </p>
                  </div>
                  <StatusBadge status={pick(d, 'shift_status', 'status') ?? 'off_shift'} />
                </div>

                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                  {[
                    ['Entregas', done != null ? fmtNum(done) : '—'],
                    ['A tiempo', onTime != null ? fmtPct(onTime) : '—'],
                    ['Rating', rating != null ? `★ ${fmtNum(rating, 1)}` : '—'],
                  ].map(([label, val]) => (
                    <div key={label} className="rounded-lg bg-slate-900 py-2 ring-1 ring-slate-800">
                      <p className="text-sm font-bold text-slate-100">{val}</p>
                      <p className="text-[10px] text-slate-500">{label}</p>
                    </div>
                  ))}
                </div>

                <div className="mt-3 flex items-center justify-between">
                  <span className="flex items-center gap-1 text-[11px] text-slate-500">
                    {onShift ? <Clock size={11} className="text-emerald-400" /> : <BadgeCheck size={11} />}
                    {onShift ? 'en turno' : 'fuera de turno'}
                  </span>
                  <ActionBtn
                    tone={onShift ? 'slate' : 'emerald'}
                    onClick={() => toggleShift(d, onShift)}
                  >
                    {onShift ? 'Terminar turno' : 'Iniciar turno'}
                  </ActionBtn>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
