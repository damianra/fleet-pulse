// Vista Vehicles — stats + tabla con búsqueda y filtro por estado.
import { useMemo, useState } from 'react';
import { Search, Truck, Wrench } from 'lucide-react';
import { useApi } from '../hooks/useApi.js';
import { asArray, pick } from '../lib/api.js';
import { fmtKm, fmtNum, timeAgo } from '../lib/format.js';
import {
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
  ['all', 'Todos'],
  ['in_transit', 'En tránsito'],
  ['active', 'Activos'],
  ['idle', 'En espera'],
  ['maintenance', 'Mantenimiento'],
  ['offline', 'Offline'],
];

export default function Vehicles() {
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const list = useApi('/api/vehicles', { interval: 20000 });
  const stats = useApi('/api/vehicles/stats', { interval: 30000 });

  const vehicles = asArray(list.data);
  const st = stats.data ?? {};

  const filtered = useMemo(
    () =>
      vehicles.filter((v) => {
        const status = pick(v, 'status', 'state') ?? '';
        const hay = `${pick(v, 'plate', 'license_plate', 'name') ?? ''} ${pick(v, 'driver_name', 'driver') ?? ''} ${pick(v, 'type', 'vehicle_type', 'model') ?? ''}`.toLowerCase();
        const okQ = !q || hay.includes(q.toLowerCase());
        const okF = filter === 'all' || status === filter;
        return okQ && okF;
      }),
    [vehicles, q, filter],
  );

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Kpi icon={Truck} label="Total" value={fmtNum(num(st, 'total', 'total_vehicles', 'count') || vehicles.length)} loading={list.loading} />
        <Kpi icon={Truck} label="En tránsito" tone="sky" value={fmtNum(num(st, 'in_transit', 'active', 'active_vehicles'))} loading={stats.loading} />
        <Kpi icon={Wrench} label="Mantenimiento" tone="violet" value={fmtNum(num(st, 'maintenance', 'in_maintenance'))} loading={stats.loading} />
        <Kpi icon={Truck} label="Offline" tone="amber" value={fmtNum(num(st, 'offline', 'inactive'))} loading={stats.loading} />
      </div>

      <Panel title="Vehículos" subtitle={`${filtered.length} de ${vehicles.length}`}>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar patente, chofer, tipo…"
              className="w-64 rounded-lg bg-slate-950 py-2 pl-9 pr-3 text-sm text-slate-200 ring-1 ring-slate-800 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
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
        </div>

        {list.loading ? (
          <SkeletonRows rows={6} />
        ) : list.error ? (
          <ErrorBlock onRetry={list.refetch} />
        ) : filtered.length === 0 ? (
          <EmptyBlock
            icon={Truck}
            title={vehicles.length ? 'Sin resultados' : 'Sin vehículos'}
            message={vehicles.length ? 'Probá con otro filtro o búsqueda.' : 'La flota aparece acá cuando el backend reporte vehículos.'}
          />
        ) : (
          <DataTable head={['Vehículo', 'Tipo', 'Estado', 'Chofer', 'Combustible', 'Odómetro', 'Última señal']}>
            {filtered.map((v, i) => {
              const fuel = pick(v, 'fuel_level', 'fuel', 'fuel_pct');
              return (
                <tr key={pick(v, 'id', 'vehicle_id') ?? i} className="text-slate-300 hover:bg-slate-900/60 transition">
                  <td className="px-4 py-3">
                    <p className="font-semibold text-slate-100">{pick(v, 'plate', 'license_plate', 'name') ?? `#${pick(v, 'id') ?? i}`}</p>
                    <p className="text-[11px] text-slate-500">{pick(v, 'model', 'brand') ?? ''}</p>
                  </td>
                  <td className="px-4 py-3 text-xs capitalize">{pick(v, 'type', 'vehicle_type') ?? '—'}</td>
                  <td className="px-4 py-3"><StatusBadge status={pick(v, 'status', 'state')} /></td>
                  <td className="px-4 py-3 text-xs">{pick(v, 'driver_name', 'driver') ?? 'sin asignar'}</td>
                  <td className="px-4 py-3">
                    {fuel != null ? (
                      <span className={`text-xs font-semibold ${fuel < 25 ? 'text-red-400' : 'text-slate-300'}`}>
                        {fmtNum(fuel)}%
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 text-xs">{fmtKm(pick(v, 'odometer', 'odometer_km', 'mileage'))}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{timeAgo(pick(v, 'last_seen', 'updated_at', 'last_update'))}</td>
                </tr>
              );
            })}
          </DataTable>
        )}
      </Panel>
    </div>
  );
}
