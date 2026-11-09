// Vista Routes — cards de rutas con progreso + acciones.
import { CheckCircle2, MapPin, Play, Route as RouteIcon, Sparkles } from 'lucide-react';
import { useApi } from '../hooks/useApi.js';
import { api, asArray, pick } from '../lib/api.js';
import { fmtDate, fmtKm, fmtNum } from '../lib/format.js';
import {
  ActionBtn,
  EmptyBlock,
  ErrorBlock,
  Panel,
  Progress,
  SkeletonRows,
  StatusBadge,
} from '../components/shell.jsx';

export default function Routes() {
  const list = useApi('/api/routes', { interval: 20000 });
  const routes = asArray(list.data);

  const act = async (r, action) => {
    const id = pick(r, 'id', 'route_id', 'routeId');
    if (!id) return;
    try {
      // optimize exige body OptimizeIn (campos opcionales → {}); start/complete no llevan.
      const body = action === 'optimize' ? {} : undefined;
      await api(`/api/routes/${id}/${action}`, { method: 'POST', body });
      if (action === 'optimize') {
        // 202 → corre en background; poll al status hasta done/failed
        // (sin esto el usuario no veía ni progreso ni resultado).
        for (let i = 0; i < 20; i += 1) {
          await new Promise((r) => setTimeout(r, 1200));
          const st = await api(`/api/routes/${id}/optimization-status`).catch(() => null);
          if (st && st.status !== 'running') break;
        }
      }
      list.refetch(true);
    } catch (err) {
      // antes: catch silencioso → los 4xx parecían "no hacer nada".
      // El próximo poll sigue reflejando el estado; esto solo avisa.
      window.alert(err?.message ?? 'acción falló');
    }
  };

  return (
    <Panel title="Rutas" subtitle={`${routes.length} planificadas`}>
      {list.loading ? (
        <SkeletonRows rows={5} />
      ) : list.error ? (
        <ErrorBlock onRetry={list.refetch} />
      ) : routes.length === 0 ? (
        <EmptyBlock icon={RouteIcon} message="Sin rutas creadas todavía." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {routes.map((r, i) => {
            const id = pick(r, 'id', 'route_id') ?? i;
            const status = pick(r, 'status', 'state') ?? 'scheduled';
            const stops = pick(r, 'stops', 'deliveries', 'waypoints');
            const total = Array.isArray(stops)
              ? stops.length
              : Number(pick(r, 'total_stops', 'delivery_count', 'stops_count') ?? 0);
            const done = Number(
              pick(r, 'completed_stops', 'completed_deliveries', 'progress_count') ?? 0,
            );
            const pct = pick(r, 'progress', 'progress_pct') ?? (total ? (done / total) * 100 : 0);
            const dist = pick(r, 'distance_km', 'total_distance', 'distance');
            return (
              <article
                key={id}
                className="rounded-2xl bg-slate-950/50 p-5 ring-1 ring-slate-800 transition hover:ring-slate-700 animate-fade-up"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="grid size-10 place-items-center rounded-xl bg-sky-500/10 text-sky-400 ring-1 ring-sky-500/25">
                      <RouteIcon size={17} />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-slate-100">
                        {pick(r, 'name', 'title', 'code') ?? `Ruta ${id}`}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {pick(r, 'driver_name', 'driver') ?? 'sin chofer'} ·{' '}
                        {fmtDate(pick(r, 'date', 'scheduled_date', 'created_at'))}
                        {dist != null && ` · ${fmtKm(dist)}`}
                      </p>
                    </div>
                  </div>
                  <StatusBadge status={status} />
                </div>

                <div className="mt-4">
                  <div className="mb-1.5 flex items-center justify-between text-[11px]">
                    <span className="flex items-center gap-1 text-slate-500">
                      <MapPin size={11} /> {done}/{total || '—'} paradas
                    </span>
                    <span className="font-semibold text-slate-300">{fmtNum(Math.round(pct))}%</span>
                  </div>
                  <Progress value={pct} tone={status === 'completed' ? 'bg-emerald-500' : 'bg-sky-500'} />
                </div>

                <div className="mt-4 flex gap-2">
                  {['scheduled', 'pending', 'optimized', 'draft'].includes(status) && (
                    <ActionBtn tone="sky" onClick={() => act(r, 'start')}>
                      <span className="inline-flex items-center gap-1"><Play size={10} />Iniciar</span>
                    </ActionBtn>
                  )}
                  {['in_progress', 'started', 'active'].includes(status) && (
                    <ActionBtn onClick={() => act(r, 'complete')}>
                      <span className="inline-flex items-center gap-1"><CheckCircle2 size={10} />Completar</span>
                    </ActionBtn>
                  )}
                  {!['completed', 'optimized'].includes(status) && (
                    <ActionBtn tone="slate" onClick={() => act(r, 'optimize')}>
                      <span className="inline-flex items-center gap-1"><Sparkles size={10} />Optimizar</span>
                    </ActionBtn>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
