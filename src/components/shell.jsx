// Componentes del shell "control tower" — tema oscuro slate + acento emerald.
import { AlertCircle, Inbox, LogOut, Radio, RefreshCw } from 'lucide-react';
import { statusLabel } from '../lib/format.js';

export const EMERALD = '#10b981';

/** Panel — card oscura estándar. */
export function Panel({ title, subtitle, action, children, className = '', pad = true }) {
  return (
    <section
      className={`rounded-2xl bg-slate-900/70 ring-1 ring-slate-800 shadow-sm backdrop-blur ${className}`}
    >
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 px-5 pt-4 pb-1">
          <div>
            {title && <h3 className="text-sm font-semibold text-slate-100">{title}</h3>}
            {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={pad ? 'p-5 pt-3' : ''}>{children}</div>
    </section>
  );
}

/** KPI — métrica grande con icono y delta opcional. */
export function Kpi({ icon: Icon, label, value, hint, tone = 'emerald', loading }) {
  const tones = {
    emerald: 'text-emerald-400 bg-emerald-400/10 ring-emerald-400/20',
    amber: 'text-amber-400 bg-amber-400/10 ring-amber-400/20',
    red: 'text-red-400 bg-red-400/10 ring-red-400/20',
    sky: 'text-sky-400 bg-sky-400/10 ring-sky-400/20',
    violet: 'text-violet-400 bg-violet-400/10 ring-violet-400/20',
  };
  return (
    <div className="rounded-2xl bg-slate-900/70 p-5 ring-1 ring-slate-800 shadow-sm hover:ring-slate-700 transition animate-fade-up">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {label}
        </span>
        {Icon && (
          <span className={`grid size-8 place-items-center rounded-lg ring-1 ${tones[tone]}`}>
            <Icon size={15} />
          </span>
        )}
      </div>
      {loading ? (
        <div className="mt-2 h-8 w-24 rounded bg-slate-800 animate-pulse" />
      ) : (
        <p className="mt-1 text-3xl font-bold tracking-tight text-slate-50">{value ?? '—'}</p>
      )}
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

/** Badge de estado con mapa de colores. */
export function StatusBadge({ status }) {
  const map = {
    active: 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/30',
    available: 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/30',
    in_transit: 'bg-sky-400/10 text-sky-300 ring-sky-400/30',
    'in-transit': 'bg-sky-400/10 text-sky-300 ring-sky-400/30',
    en_route: 'bg-sky-400/10 text-sky-300 ring-sky-400/30',
    in_progress: 'bg-sky-400/10 text-sky-300 ring-sky-400/30',
    started: 'bg-sky-400/10 text-sky-300 ring-sky-400/30',
    optimizing: 'bg-sky-400/10 text-sky-300 ring-sky-400/30',
    optimized: 'bg-sky-400/10 text-sky-300 ring-sky-400/30',
    pending: 'bg-amber-400/10 text-amber-300 ring-amber-400/30',
    scheduled: 'bg-amber-400/10 text-amber-300 ring-amber-400/30',
    assigned: 'bg-amber-400/10 text-amber-300 ring-amber-400/30',
    warning: 'bg-amber-400/10 text-amber-300 ring-amber-400/30',
    medium: 'bg-amber-400/10 text-amber-300 ring-amber-400/30',
    acknowledged: 'bg-amber-400/10 text-amber-300 ring-amber-400/30',
    idle: 'bg-slate-400/10 text-slate-300 ring-slate-400/30',
    completed: 'bg-slate-400/10 text-slate-300 ring-slate-400/30',
    delivered: 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/30',
    resolved: 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/30',
    low: 'bg-slate-400/10 text-slate-300 ring-slate-400/30',
    info: 'bg-slate-400/10 text-slate-300 ring-slate-400/30',
    failed: 'bg-red-400/10 text-red-300 ring-red-400/30',
    critical: 'bg-red-400/10 text-red-300 ring-red-400/30',
    high: 'bg-red-400/10 text-red-300 ring-red-400/30',
    overdue: 'bg-red-400/10 text-red-300 ring-red-400/30',
    cancelled: 'bg-red-400/10 text-red-300 ring-red-400/30',
    maintenance: 'bg-violet-400/10 text-violet-300 ring-violet-400/30',
    offline: 'bg-slate-500/10 text-slate-400 ring-slate-500/30',
    off_shift: 'bg-slate-500/10 text-slate-400 ring-slate-500/30',
    on_shift: 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/30',
  };
  const cls = map[status] ?? 'bg-slate-400/10 text-slate-300 ring-slate-400/30';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${cls}`}
    >
      {statusLabel(status)}
    </span>
  );
}

/** Sidebar del shell — navegación por vistas + usuario al pie. */
export function Sidebar({ brand = 'FleetPulse', items, active, onSelect, user, onLogout, alertCount = 0 }) {
  return (
    <aside className="flex w-64 shrink-0 flex-col bg-slate-950 ring-1 ring-slate-800/80 max-lg:hidden">
      <div className="flex h-16 items-center gap-2.5 px-5 ring-1 ring-slate-800/80">
        <span className="relative grid size-9 place-items-center rounded-xl bg-emerald-500/15 ring-1 ring-emerald-500/30">
          <Radio size={17} className="text-emerald-400" />
          <span className="absolute -right-0.5 -top-0.5 size-2 rounded-full bg-emerald-400 animate-pulse" />
        </span>
        <div>
          <p className="text-sm font-bold tracking-tight text-slate-50">{brand}</p>
          <p className="text-[11px] text-slate-500">Control de flota en vivo</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {items.map((it) => {
          const Icon = it.icon;
          const isActive = active === it.id;
          return (
            <button
              key={it.id}
              onClick={() => onSelect(it.id)}
              className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                isActive
                  ? 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/25'
                  : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
              }`}
            >
              <Icon size={16} className={isActive ? 'text-emerald-400' : 'text-slate-500 group-hover:text-slate-300'} />
              <span className="flex-1 text-left">{it.label}</span>
              {it.id === 'alerts' && alertCount > 0 && (
                <span className="rounded-full bg-red-500/15 px-1.5 py-0.5 text-[10px] font-bold text-red-300 ring-1 ring-red-500/30">
                  {alertCount > 99 ? '99+' : alertCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {user && (
        <div className="m-3 flex items-center gap-3 rounded-xl bg-slate-900 p-3 ring-1 ring-slate-800">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-emerald-500/15 text-xs font-bold text-emerald-300 ring-1 ring-emerald-500/30">
            {(user.name || user.email || '?').slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-slate-200">
              {user.name || user.email || 'Usuario'}
            </p>
            <p className="truncate text-[11px] capitalize text-slate-500">{user.role || 'operador'}</p>
          </div>
          {onLogout && (
            <button
              onClick={onLogout}
              title="Cerrar sesión"
              className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-800 hover:text-slate-200 transition"
            >
              <LogOut size={14} />
            </button>
          )}
        </div>
      )}
    </aside>
  );
}

/** Topbar — título de vista + reloj en vivo + acciones. */
export function Topbar({ title, subtitle, onRefresh, refreshing, live = true, mobileNav }) {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-slate-800/80 bg-slate-950/80 px-6 backdrop-blur">
      {mobileNav}
      <div className="min-w-0">
        <h1 className="truncate text-lg font-bold tracking-tight text-slate-50">{title}</h1>
        {subtitle && <p className="truncate text-xs text-slate-500">{subtitle}</p>}
      </div>
      <div className="ml-auto flex items-center gap-3">
        {live && (
          <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-300 ring-1 ring-emerald-500/25">
            <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse" />
            EN VIVO
          </span>
        )}
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="grid size-8 place-items-center rounded-lg bg-slate-900 text-slate-400 ring-1 ring-slate-800 hover:text-slate-200 transition"
            title="Actualizar"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          </button>
        )}
      </div>
    </header>
  );
}

/** Empty state oscuro. */
export function EmptyBlock({ icon: Icon = Inbox, title = 'Sin datos', message, action }) {
  return (
    <div className="grid place-items-center rounded-xl bg-slate-900/50 px-6 py-12 text-center ring-1 ring-dashed ring-slate-800">
      <Icon size={26} className="text-slate-600" />
      <h3 className="mt-3 text-sm font-semibold text-slate-300">{title}</h3>
      {message && <p className="mt-1 max-w-sm text-xs text-slate-500">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** Error state oscuro con retry. */
export function ErrorBlock({ title = 'No se pudo cargar', message, onRetry }) {
  return (
    <div className="flex items-start gap-3 rounded-xl bg-red-500/5 p-5 ring-1 ring-red-500/20">
      <AlertCircle size={18} className="mt-0.5 shrink-0 text-red-400" />
      <div>
        <h3 className="text-sm font-semibold text-red-300">{title}</h3>
        <p className="mt-1 text-xs text-red-400/80">
          {message || 'El backend no respondió. Verificá que esté corriendo en :4000.'}
        </p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 rounded-lg bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-red-300 ring-1 ring-red-500/25 hover:bg-red-500/20 transition"
          >
            Reintentar
          </button>
        )}
      </div>
    </div>
  );
}

/** Skeleton de tabla/lista. */
export function SkeletonRows({ rows = 5 }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-12 rounded-lg bg-slate-800/50 animate-pulse" style={{ animationDelay: `${i * 80}ms` }} />
      ))}
    </div>
  );
}

/** Tabla oscura base. */
export function DataTable({ head, children, className = '' }) {
  return (
    <div className={`overflow-x-auto rounded-xl ring-1 ring-slate-800 ${className}`}>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="bg-slate-900 text-[11px] uppercase tracking-wider text-slate-500">
            {head.map((h) => (
              <th key={h} className="px-4 py-3 font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/70">{children}</tbody>
      </table>
    </div>
  );
}

/** Botón pequeño de acción. */
export function ActionBtn({ children, onClick, tone = 'emerald', disabled, title }) {
  const tones = {
    emerald: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/25 hover:bg-emerald-500/20',
    slate: 'bg-slate-800 text-slate-300 ring-slate-700 hover:bg-slate-700',
    red: 'bg-red-500/10 text-red-300 ring-red-500/25 hover:bg-red-500/20',
    sky: 'bg-sky-500/10 text-sky-300 ring-sky-500/25 hover:bg-sky-500/20',
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold ring-1 transition disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]}`}
    >
      {children}
    </button>
  );
}

/** Barra de progreso. */
export function Progress({ value = 0, tone = 'bg-emerald-500', className = '' }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-slate-800 ${className}`}>
      <div
        className={`h-full rounded-full ${tone} transition-all duration-700`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
