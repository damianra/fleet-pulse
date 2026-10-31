// Vista Overview — KPIs + tendencia + estado de flota + alertas.
import {
  AlertTriangle,
  CheckCircle2,
  Package,
  Route as RouteIcon,
  Truck,
  Users,
} from 'lucide-react';
import { useApi } from '../hooks/useApi.js';
import { asArray, pick } from '../lib/api.js';
import { fmtNum, fmtPct, timeAgo, statusLabel } from '../lib/format.js';
import { AreaChart, Donut } from '../components/charts.jsx';
import {
  EmptyBlock,
  ErrorBlock,
  Kpi,
  Panel,
  SkeletonRows,
  StatusBadge,
} from '../components/shell.jsx';

const num = (obj, ...keys) => Number(pick(obj ?? {}, ...keys) ?? 0) || 0;

export default function Overview({ onNavigate }) {
  const fleet = useApi('/api/analytics/fleet-overview', { interval: 20000 });
  const vStats = useApi('/api/vehicles/stats', { interval: 20000 });
  const dStats = useApi('/api/deliveries/stats', { interval: 20000 });
  const aStats = useApi('/api/alerts/stats', { interval: 20000 });
  const alerts = useApi('/api/alerts/active', { interval: 15000 });
  const deliveries = useApi('/api/analytics/deliveries', { interval: 30000 });

  const loading = fleet.loading && vStats.loading && dStats.loading;
  const fo = fleet.data ?? {};
  const vs = vStats.data ?? {};
  const ds = dStats.data ?? {};
  const as = aStats.data ?? {};

  const totalVehicles = num(vs, 'total', 'total_vehicles', 'count') || num(fo, 'total_vehicles', 'vehicles_total');
  const activeVehicles = num(vs, 'active', 'active_vehicles', 'in_transit') || num(fo, 'active_vehicles');
  const deliveriesToday = num(ds, 'today', 'deliveries_today', 'total_today') || num(fo, 'deliveries_today');
  const onTime = pick(ds, 'on_time_rate', 'on_time_pct', 'success_rate') ?? pick(fo, 'on_time_rate');
  const activeAlerts = num(as, 'active', 'active_alerts', 'total_active') || num(fo, 'active_alerts');
  const driversActive = num(fo, 'drivers_active', 'active_drivers', 'drivers_on_shift');

  // Donut de estado de flota: usa breakdown si viene, si no total/active/idle.
  const statusBreakdown =
    asArray(pick(vs, 'by_status', 'status_breakdown', 'breakdown')).map((s) => ({
      label: statusLabel(pick(s, 'status', 'name', 'label')),
      value: num(s, 'count', 'value', 'total'),
    })).filter((s) => s.value > 0) || [];
  const donutData = statusBreakdown.length
    ? statusBreakdown
    : [
        { label: 'En tránsito', value: activeVehicles, color: '#38bdf8' },
        { label: 'Disponibles', value: Math.max(0, totalVehicles - activeVehicles), color: '#10b981' },
      ].filter((d) => d.value > 0);

  // Serie temporal para el area chart.
  const series = asArray(pick(deliveries.data, 'by_day', 'daily', 'series', 'trend')).map((d) => ({
    label: String(pick(d, 'day', 'date', 'label') ?? '').slice(5),
    value: num(d, 'count', 'deliveries', 'value', 'total'),
  }));
  const history = useApi(series.length ? null : '/api/analytics/history', { interval: 60000 });
  const histSeries = asArray(history.data).slice(-14).map((d) => ({
    label: String(pick(d, 'date', 'day', 'label') ?? '').slice(5, 10),
    value: num(d, 'deliveries', 'completed_deliveries', 'count', 'value'),
  }));
  const chartData = series.length ? series.slice(-14) : histSeries;

  const activeAlertsList = asArray(alerts.data).slice(0, 6);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Kpi
          icon={Truck}
          label="Vehículos activos"
          loading={loading}
          value={`${fmtNum(activeVehicles)} / ${fmtNum(totalVehicles)}`}
          hint="en movimiento / flota total"
        />
        <Kpi
          icon={Package}
          label="Entregas hoy"
          loading={loading}
          value={fmtNum(deliveriesToday)}
          tone="sky"
          hint={onTime !== undefined ? `puntualidad ${fmtPct(onTime)}` : 'completadas hoy'}
        />
        <Kpi
          icon={AlertTriangle}
          label="Alertas activas"
          loading={loading}
          value={fmtNum(activeAlerts)}
          tone={activeAlerts > 0 ? 'amber' : 'emerald'}
          hint="requieren atención"
        />
        <Kpi
          icon={Users}
          label="Choferes en turno"
          loading={loading}
          value={driversActive ? fmtNum(driversActive) : '—'}
          tone="violet"
          hint="activos ahora"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel
          title="Entregas — últimos días"
          subtitle="volumen diario completado"
          className="xl:col-span-2 animate-fade-up"
        >
          {deliveries.loading || history.loading ? (
            <SkeletonRows rows={3} />
          ) : deliveries.error && history.error ? (
            <ErrorBlock onRetry={() => { deliveries.refetch(); history.refetch(); }} />
          ) : (
            <AreaChart data={chartData} height={190} />
          )}
        </Panel>

        <Panel title="Estado de flota" subtitle="distribución actual" className="animate-fade-up">
          {vStats.loading ? (
            <SkeletonRows rows={3} />
          ) : vStats.error ? (
            <ErrorBlock onRetry={vStats.refetch} />
          ) : donutData.length ? (
            <Donut data={donutData} centerLabel="vehículos" centerValue={fmtNum(totalVehicles)} />
          ) : (
            <EmptyBlock icon={Truck} message="El backend no reportó estados de flota todavía." />
          )}
        </Panel>
      </div>

      <Panel
        title="Alertas activas"
        subtitle="eventos que piden atención del despachador"
        action={
          <button
            onClick={() => onNavigate?.('alerts')}
            className="text-xs font-semibold text-emerald-400 hover:text-emerald-300"
          >
            Ver todas →
          </button>
        }
      >
        {alerts.loading ? (
          <SkeletonRows rows={4} />
        ) : alerts.error ? (
          <ErrorBlock onRetry={alerts.refetch} />
        ) : activeAlertsList.length === 0 ? (
          <EmptyBlock
            icon={CheckCircle2}
            title="Todo en orden"
            message="No hay alertas activas en este momento."
          />
        ) : (
          <ul className="divide-y divide-slate-800/70">
            {activeAlertsList.map((al, i) => (
              <li key={pick(al, 'id', 'alert_id') ?? i} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                <span
                  className={`size-2 shrink-0 rounded-full ${
                    pick(al, 'severity', 'priority') === 'critical' || pick(al, 'severity') === 'high'
                      ? 'bg-red-400 animate-pulse'
                      : 'bg-amber-400'
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-slate-200">
                    {pick(al, 'message', 'title', 'description', 'type') ?? 'Alerta'}
                  </p>
                  <p className="text-xs text-slate-500">
                    {pick(al, 'vehicle_plate', 'vehicle', 'vehicle_id') ?? ''}{' '}
                    {timeAgo(pick(al, 'created_at', 'timestamp', 'time'))}
                  </p>
                </div>
                <StatusBadge status={pick(al, 'severity', 'priority', 'status') ?? 'warning'} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
