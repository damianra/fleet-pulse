// Vista Analytics — grilla de charts desde los endpoints /api/analytics/*.
import { useApi } from '../hooks/useApi.js';
import { asArray, pick } from '../lib/api.js';
import { fmtMoney, statusLabel } from '../lib/format.js';
import { AreaChart, Bars, Donut } from '../components/charts.jsx';
import { ErrorBlock, Panel, SkeletonRows } from '../components/shell.jsx';

const num = (o, ...k) => Number(pick(o ?? {}, ...k) ?? 0) || 0;

const toSeries = (payload, labelKeys, valueKeys, limit = 14) =>
  asArray(payload)
    .slice(-limit)
    .map((d) => ({
      label: String(pick(d, ...labelKeys) ?? '').slice(0, 10),
      value: num(d, ...valueKeys),
    }))
    .filter((d) => d.value > 0 || d.label);

const toCats = (payload, labelKeys, valueKeys) =>
  asArray(payload)
    .map((d) => ({
      label: statusLabel(pick(d, ...labelKeys)),
      value: num(d, ...valueKeys),
    }))
    .filter((d) => d.value > 0);

function ChartPanel({ title, subtitle, query, className = '', children }) {
  return (
    <Panel title={title} subtitle={subtitle} className={`animate-fade-up ${className}`}>
      {query.loading ? (
        <SkeletonRows rows={3} />
      ) : query.error ? (
        <ErrorBlock onRetry={query.refetch} />
      ) : (
        children
      )}
    </Panel>
  );
}

export default function Analytics() {
  const deliveries = useApi('/api/analytics/deliveries', { interval: 60000 });
  const drivers = useApi('/api/analytics/drivers', { interval: 60000 });
  const vehicles = useApi('/api/analytics/vehicles', { interval: 60000 });
  const alerts = useApi('/api/analytics/alerts', { interval: 60000 });
  const costs = useApi('/api/analytics/costs', { interval: 60000 });
  const history = useApi('/api/analytics/history', { interval: 60000 });

  // Shapes reales de /api/analytics/*: dicts {k: count} (by_status,
  // by_type, maintenance_by_month), arrays (top_by_deliveries) y
  // history con métricas anidadas en row.data — se aplanan acá.
  const fromMap = (m) =>
    Object.entries(m ?? {}).map(([k, v]) => ({ label: statusLabel(k), value: Number(v) || 0 }));

  // Serie temporal: daily_metrics.metric_date + data.deliveries.{created,delivered}
  const histSeries = asArray(history.data).map((d) => ({
    label: String(pick(d, 'metric_date', 'date', 'day') ?? '').slice(5, 10),
    value: num(d.data?.deliveries ?? {}, 'delivered', 'created', 'count'),
  }));

  const delSeries = toSeries(
    pick(deliveries.data ?? {}, 'by_day', 'daily', 'series'),
    ['day', 'date', 'label'],
    ['count', 'deliveries', 'completed', 'value', 'total'],
  );

  const driverBars = toCats(
    pick(drivers.data ?? {}, 'top_by_deliveries') ?? drivers.data,
    ['name', 'driver_name', 'driver', 'license', 'driver_id'],
    ['deliveries_completed', 'completed', 'deliveries', 'count'],
  )
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);

  const vehicleBars = fromMap(pick(vehicles.data ?? {}, 'by_type', 'by_status'));

  const alertCats = fromMap(pick(alerts.data ?? {}, 'by_type', 'by_severity'));

  const costCats = fromMap(costs.data?.maintenance_by_month);
  const costTotal = pick(costs.data ?? {}, 'maintenance_total', 'total', 'total_cost', 'amount');

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <ChartPanel title="Entregas por día" subtitle="volumen del período" query={deliveries}>
        <AreaChart data={delSeries.length ? delSeries : histSeries} height={190} color="#10b981" />
      </ChartPanel>

      <ChartPanel title="Costos operativos" subtitle={costTotal != null ? `total ${fmtMoney(costTotal)}` : 'por categoría'} query={costs}>
        <Donut
          data={costCats}
          centerLabel="total"
          centerValue={costTotal != null ? fmtMoney(costTotal) : undefined}
        />
      </ChartPanel>

      <ChartPanel title="Choferes — entregas" subtitle="top por volumen completado" query={drivers}>
        <Bars data={driverBars.map((d, i) => ({ ...d, color: i === 0 ? '#10b981' : '#334155' }))} height={200} />
      </ChartPanel>

      <ChartPanel title="Vehículos — utilización" subtitle="actividad por unidad" query={vehicles}>
        <Bars data={vehicleBars.map((d, i) => ({ ...d, color: i === 0 ? '#38bdf8' : '#334155' }))} height={200} />
      </ChartPanel>

      <ChartPanel title="Alertas por tipo" subtitle="distribución del período" query={alerts} className="xl:col-span-2">
        {alertCats.length ? (
          <Donut data={alertCats} centerLabel="alertas" />
        ) : (
          <Bars data={toSeries(alerts.data, ['day', 'date'], ['count', 'total', 'value'])} height={180} color="#fbbf24" />
        )}
      </ChartPanel>
    </div>
  );
}
