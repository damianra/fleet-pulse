// Vista Live Map — mapa en vivo + lista de vehículos + geofences.
import { useState } from 'react';
import { CircleDot, Fuel, Gauge, MapPin, Truck } from 'lucide-react';
import { useApi } from '../hooks/useApi.js';
import { asArray, pick } from '../lib/api.js';
import { fmtNum, timeAgo } from '../lib/format.js';
import FleetMap from '../components/FleetMap.jsx';
import {
  EmptyBlock,
  ErrorBlock,
  Panel,
  SkeletonRows,
  StatusBadge,
} from '../components/shell.jsx';

export default function LiveMap() {
  const [selected, setSelected] = useState(null);
  const vehicles = useApi('/api/vehicles', { interval: 10000 });
  const geofences = useApi('/api/geofences', { interval: 60000 });

  const list = asArray(vehicles.data);
  const fences = asArray(geofences.data);
  const selId = selected && (pick(selected, 'id', 'vehicle_id', 'vehicleId') ?? null);

  const moving = list.filter((v) =>
    ['in_transit', 'in-transit', 'en_route', 'active'].includes(pick(v, 'status', 'state')),
  ).length;

  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <div className="space-y-4 xl:col-span-2">
        <Panel pad={false} className="animate-fade-up">
          <FleetMap
            vehicles={list}
            geofences={fences}
            selected={selId}
            onSelect={setSelected}
          />
        </Panel>

        {selected && (
          <Panel
            title={pick(selected, 'plate', 'license_plate', 'name') ?? 'Vehículo'}
            subtitle="detalle en vivo"
            action={<StatusBadge status={pick(selected, 'status', 'state')} />}
          >
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              {[
                [Gauge, 'Velocidad', pick(selected, 'speed', 'speed_kmh') != null ? `${fmtNum(pick(selected, 'speed', 'speed_kmh'))} km/h` : '—'],
                [Fuel, 'Combustible', pick(selected, 'fuel_level', 'fuel', 'fuel_pct') != null ? `${fmtNum(pick(selected, 'fuel_level', 'fuel', 'fuel_pct'))}%` : '—'],
                [MapPin, 'Última señal', timeAgo(pick(selected, 'last_seen', 'updated_at', 'last_update'))],
                [Truck, 'Chofer', pick(selected, 'driver_name', 'driver') ?? 'sin asignar'],
              ].map(([Icon, label, val]) => (
                <div key={label} className="rounded-xl bg-slate-950/60 p-3 ring-1 ring-slate-800">
                  <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    <Icon size={12} /> {label}
                  </p>
                  <p className="mt-1 text-sm font-semibold text-slate-100">{val}</p>
                </div>
              ))}
            </div>
          </Panel>
        )}
      </div>

      <Panel
        title="Flota en vivo"
        subtitle={`${moving} en movimiento · ${list.length} total`}
        className="animate-fade-up"
      >
        {vehicles.loading ? (
          <SkeletonRows rows={6} />
        ) : vehicles.error ? (
          <ErrorBlock onRetry={vehicles.refetch} />
        ) : list.length === 0 ? (
          <EmptyBlock icon={Truck} message="Sin vehículos registrados todavía." />
        ) : (
          <ul className="max-h-[30rem] space-y-1.5 overflow-y-auto pr-1">
            {list.map((v, i) => {
              const id = pick(v, 'id', 'vehicle_id', 'vehicleId') ?? i;
              const name = pick(v, 'plate', 'license_plate', 'name') ?? `Vehículo ${id}`;
              const status = pick(v, 'status', 'state') ?? 'active';
              const isSel = selId === id;
              return (
                <li key={id}>
                  <button
                    onClick={() => setSelected(v)}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                      isSel
                        ? 'bg-emerald-500/10 ring-1 ring-emerald-500/30'
                        : 'bg-slate-950/50 ring-1 ring-slate-800 hover:ring-slate-700'
                    }`}
                  >
                    <CircleDot
                      size={14}
                      className={
                        ['in_transit', 'en_route'].includes(status)
                          ? 'text-sky-400'
                          : status === 'active' || status === 'available'
                            ? 'text-emerald-400'
                            : 'text-slate-500'
                      }
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-slate-200">{name}</p>
                      <p className="truncate text-[11px] text-slate-500">
                        {pick(v, 'driver_name', 'driver') ?? pick(v, 'type', 'vehicle_type') ?? '—'} ·{' '}
                        {timeAgo(pick(v, 'last_seen', 'updated_at'))}
                      </p>
                    </div>
                    <StatusBadge status={status} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
