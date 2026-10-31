import { useEffect, useMemo, useState } from 'react';
import {
  BarChart3,
  BellRing,
  LayoutDashboard,
  Map as MapIcon,
  Package,
  Radio,
  Route as RouteIcon,
  Truck,
  Users,
  Wrench,
} from 'lucide-react';
import { api, asArray, clearSession, getStoredUser, getToken, pick } from './lib/api.js';
import { useApi } from './hooks/useApi.js';
import { Sidebar, Topbar } from './components/shell.jsx';
import Login from './views/Login.jsx';
import Overview from './views/Overview.jsx';
import LiveMap from './views/LiveMap.jsx';
import Vehicles from './views/Vehicles.jsx';
import Deliveries from './views/Deliveries.jsx';
import Drivers from './views/Drivers.jsx';
import Routes from './views/Routes.jsx';
import Alerts from './views/Alerts.jsx';
import Maintenance from './views/Maintenance.jsx';
import Analytics from './views/Analytics.jsx';

const NAV = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, roles: ['admin', 'dispatcher', 'viewer', 'driver'] },
  { id: 'map', label: 'Mapa en vivo', icon: MapIcon, roles: ['admin', 'dispatcher', 'viewer', 'driver'] },
  { id: 'deliveries', label: 'Entregas', icon: Package, roles: ['admin', 'dispatcher', 'viewer', 'driver'] },
  { id: 'routes', label: 'Rutas', icon: RouteIcon, roles: ['admin', 'dispatcher', 'viewer'] },
  { id: 'vehicles', label: 'Vehículos', icon: Truck, roles: ['admin', 'dispatcher', 'viewer'] },
  { id: 'drivers', label: 'Choferes', icon: Users, roles: ['admin', 'dispatcher'] },
  { id: 'alerts', label: 'Alertas', icon: BellRing, roles: ['admin', 'dispatcher', 'viewer', 'driver'] },
  { id: 'maintenance', label: 'Mantenimiento', icon: Wrench, roles: ['admin', 'dispatcher'] },
  { id: 'analytics', label: 'Analytics', icon: BarChart3, roles: ['admin', 'viewer'] },
];

const TITLES = {
  overview: ['Overview', 'pulso general de la operación'],
  map: ['Mapa en vivo', 'tracking GPS en tiempo real'],
  deliveries: ['Entregas', 'ciclo de vida de cada pedido'],
  routes: ['Rutas', 'planificación y progreso'],
  vehicles: ['Vehículos', 'estado de la flota'],
  drivers: ['Choferes', 'turnos y performance'],
  alerts: ['Alertas', 'eventos que requieren atención'],
  maintenance: ['Mantenimiento', 'servicios programados e historial'],
  analytics: ['Analytics', 'métricas y tendencias'],
};

const VIEWS = {
  overview: Overview,
  map: LiveMap,
  deliveries: Deliveries,
  routes: Routes,
  vehicles: Vehicles,
  drivers: Drivers,
  alerts: Alerts,
  maintenance: Maintenance,
  analytics: Analytics,
};

export default function App() {
  const [user, setUser] = useState(getStoredUser());
  const [authChecked, setAuthChecked] = useState(false);
  const [guest, setGuest] = useState(false);
  const [view, setView] = useState('overview');

  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true);
      return;
    }
    api('/api/auth/me')
      .then((u) => setUser(pick(u, 'user', 'data') ?? u))
      .catch(() => {})
      .finally(() => setAuthChecked(true));
  }, []);

  const items = useMemo(() => {
    const role = user?.role;
    return NAV.filter((n) => !role || n.roles.includes(role));
  }, [user]);

  const activeView = items.some((n) => n.id === view) ? view : items[0]?.id ?? 'overview';
  const alerts = useApi('/api/alerts/active', { interval: 30000, enabled: Boolean(user || guest) });
  const alertCount = asArray(alerts.data).length;

  const logout = async () => {
    try {
      await api('/api/auth/logout', { method: 'POST' });
    } catch {
      // sesión local se limpia igual
    }
    clearSession();
    setUser(null);
    setGuest(false);
  };

  if (!authChecked) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-950">
        <Radio size={22} className="animate-pulse text-emerald-400" />
      </main>
    );
  }

  if (!user && !guest) {
    return <Login onLogin={setUser} onGuest={() => setGuest(true)} />;
  }

  const ViewComp = VIEWS[activeView] ?? Overview;
  const [title, subtitle] = TITLES[activeView] ?? ['FleetPulse', ''];

  const mobileNav = (
    <select
      value={activeView}
      onChange={(e) => setView(e.target.value)}
      className="rounded-lg bg-slate-900 px-2 py-1.5 text-xs text-slate-200 ring-1 ring-slate-800 lg:hidden"
    >
      {items.map((n) => (
        <option key={n.id} value={n.id}>{n.label}</option>
      ))}
    </select>
  );

  return (
    <main className="flex h-screen overflow-hidden bg-slate-950 text-slate-100">
      <Sidebar
        items={items}
        active={activeView}
        onSelect={setView}
        user={user ?? { name: 'Invitado', role: 'viewer' }}
        onLogout={user ? logout : () => setGuest(false)}
        alertCount={alertCount}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          title={title}
          subtitle={subtitle}
          onRefresh={() => alerts.refetch()}
          refreshing={alerts.loading}
          mobileNav={mobileNav}
        />
        <div className="min-h-0 flex-1 overflow-y-auto bg-gradient-to-b from-slate-950 via-slate-950 to-slate-900/40 p-5 lg:p-7">
          <div key={activeView} className="mx-auto max-w-7xl animate-fade-up">
            <ViewComp onNavigate={setView} />
          </div>
        </div>
      </div>
    </main>
  );
}
