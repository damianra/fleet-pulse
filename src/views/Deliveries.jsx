// Vista Deliveries — stats + tabla con filtros y acciones de ciclo de vida.
import { useMemo, useState } from 'react';
import { CheckCircle2, CircleX, Package, Play, RotateCcw } from 'lucide-react';
import { useApi } from '../hooks/useApi.js';
import { api, asArray, pick } from '../lib/api.js';
import { fmtDate, fmtNum } from '../lib/format.js';
import {
  ActionBtn,
  DataTable,
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
  ['pending', 'Pendientes'],
  ['in_transit', 'En tránsito'],
  ['delivered', 'Entregadas'],
  ['failed', 'Fallidas'],
];

export default function Deliveries() {
  const [filter, setFilter] = useState('all');
  const [busy, setBusy] = useState(null);
  const list = useApi('/api/deliveries', { interval: 15000 });
  const stats = useApi('/api/deliveries/stats', { interval: 30000 });

  const deliveries = asArray(list.data);
  const st = stats.data ?? {};

  const filtered = useMemo(
    () =>
      filter === 'all'
        ? deliveries
        : deliveries.filter((d) => (pick(d, 'status', 'state') ?? '') === filter),
    [deliveries, filter],
  );

  const act = async (d, action) => {
    const id = pick(d, 'id', 'delivery_id', 'deliveryId');
    if (!id) return;
    setBusy(`${id}:${action}`);
    try {
      // complete/fail/reschedule exigen body pydantic (campos
      // opcionales → {}); start no lleva body.
      const body = action === 'start' ? undefined : {};
      await api(`/api/deliveries/${id}/${action}`, { method: 'POST', body });
      list.refetch(true);
      stats.refetch(true);
    } catch (err) {
      // el estado lo refleja el próximo poll; el error se muestra
      // (antes era catch silencioso — los 4xx parecían "no hacer nada")
      setError?.(err?.message ?? 'acción falló');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Kpi icon={Package} label="Total" value={fmtNum(num(st, 'total', 'total_deliveries', 'count') || deliveries.length)} loading={list.loading} />
        <Kpi icon={Play} label="En tránsito" tone="sky" value={fmtNum(num(st, 'in_transit', 'active'))} loading={stats.loading} />
        <Kpi icon={CheckCircle2} label="Entregadas" value={fmtNum(num(st, 'delivered', 'completed', 'completed_today'))} loading={stats.loading} />
        <Kpi icon={CircleX} label="Fallidas" tone="red" value={fmtNum(num(st, 'failed', 'failed_today'))} loading={stats.loading} />
      </div>

      <Panel title="Entregas" subtitle={`${filtered.length} de ${deliveries.length}`}>
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
          <EmptyBlock icon={Package} message="No hay entregas con ese filtro." />
        ) : (
          <DataTable head={['#', 'Destino', 'Cliente', 'Estado', 'Chofer / Vehículo', 'Programada', 'Acciones']}>
            {filtered.map((d, i) => {
              const id = pick(d, 'id', 'delivery_id', 'deliveryId') ?? i;
              const status = pick(d, 'status', 'state') ?? 'pending';
              return (
                <tr key={id} className="text-slate-300 hover:bg-slate-900/60 transition">
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {pick(d, 'tracking_code', 'code') ?? `#${id}`}
                  </td>
                  <td className="px-4 py-3">
                    <p className="max-w-[16rem] truncate text-sm text-slate-200">
                      {pick(d, 'address', 'destination', 'dropoff_address') ?? '—'}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-xs">{pick(d, 'customer_name', 'customer', 'recipient') ?? '—'}</td>
                  <td className="px-4 py-3"><StatusBadge status={status} /></td>
                  <td className="px-4 py-3 text-xs">
                    {pick(d, 'driver_name', 'driver') ?? '—'}
                    <span className="text-slate-500"> · {pick(d, 'vehicle_plate', 'vehicle') ?? '—'}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {fmtDate(pick(d, 'scheduled_at', 'scheduled_date', 'delivery_date'), true)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1.5">
                      {['pending', 'assigned', 'scheduled'].includes(status) && (
                        <ActionBtn tone="sky" disabled={busy} onClick={() => act(d, 'start')}>Iniciar</ActionBtn>
                      )}
                      {['in_transit', 'in_progress', 'started'].includes(status) && (
                        <>
                          <ActionBtn disabled={busy} onClick={() => act(d, 'complete')}>Completar</ActionBtn>
                          <ActionBtn tone="red" disabled={busy} onClick={() => act(d, 'fail')}>Falló</ActionBtn>
                        </>
                      )}
                      {['failed', 'cancelled'].includes(status) && (
                        <ActionBtn tone="slate" disabled={busy} onClick={() => act(d, 'reschedule')}>
                          <span className="inline-flex items-center gap-1"><RotateCcw size={10} />Reagendar</span>
                        </ActionBtn>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </DataTable>
        )}
      </Panel>
    </div>
  );
}
