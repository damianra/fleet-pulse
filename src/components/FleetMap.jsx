// Mapa estilizado — grilla urbana SVG + geofences + vehículos en vivo.
// Posiciones reales normalizadas al viewBox por bounds de lat/lng.
import { useMemo, useState } from 'react';
import { Navigation } from 'lucide-react';
import { pick } from '../lib/api.js';
import { statusLabel } from '../lib/format.js';

const W = 800;
const H = 520;
const PAD = 40;

const STATUS_COLOR = {
  active: '#10b981',
  available: '#10b981',
  in_transit: '#38bdf8',
  'in-transit': '#38bdf8',
  en_route: '#38bdf8',
  idle: '#94a3b8',
  maintenance: '#a78bfa',
  offline: '#475569',
};

export function vehicleXY(v) {
  const lat = pick(v, 'latitude', 'lat', 'last_lat') ?? pick(v?.position ?? v?.current_position ?? {}, 'latitude', 'lat');
  const lng = pick(v, 'longitude', 'lng', 'lon', 'last_lng') ?? pick(v?.position ?? v?.current_position ?? {}, 'longitude', 'lng', 'lon');
  if (lat === undefined || lng === undefined) return null;
  return { lat: Number(lat), lng: Number(lng) };
}

export default function FleetMap({ vehicles = [], geofences = [], selected, onSelect }) {
  const [hover, setHover] = useState(null);

  const pts = useMemo(
    () => vehicles.map((v) => ({ v, p: vehicleXY(v) })).filter((x) => x.p),
    [vehicles],
  );

  const bounds = useMemo(() => {
    if (!pts.length) {
      // Buenos Aires por defecto — el mapa igualmente se dibuja.
      return { minLat: -34.75, maxLat: -34.5, minLng: -58.6, maxLng: -58.3 };
    }
    const lats = pts.map((x) => x.p.lat);
    const lngs = pts.map((x) => x.p.lng);
    const dLat = Math.max(0.01, Math.max(...lats) - Math.min(...lats));
    const dLng = Math.max(0.01, Math.max(...lngs) - Math.min(...lngs));
    return {
      minLat: Math.min(...lats) - dLat * 0.15,
      maxLat: Math.max(...lats) + dLat * 0.15,
      minLng: Math.min(...lngs) - dLng * 0.15,
      maxLng: Math.max(...lngs) + dLng * 0.15,
    };
  }, [pts]);

  const toXY = (lat, lng) => ({
    x: PAD + ((lng - bounds.minLng) / (bounds.maxLng - bounds.minLng)) * (W - PAD * 2),
    y: H - PAD - ((lat - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * (H - PAD * 2),
  });

  // Geofences con centro+radio normalizados.
  const fences = useMemo(
    () =>
      geofences
        .map((g) => {
          const lat = pick(g, 'latitude', 'lat', 'center_lat') ?? pick(g?.center ?? {}, 'latitude', 'lat');
          const lng = pick(g, 'longitude', 'lng', 'lon', 'center_lng') ?? pick(g?.center ?? {}, 'longitude', 'lng', 'lon');
          const radius = pick(g, 'radius_m', 'radius', 'radius_meters') ?? 400;
          if (lat === undefined || lng === undefined) return null;
          const { x, y } = toXY(lat, lng);
          const rPx = (Number(radius) / 111320) * ((W - PAD * 2) / (bounds.maxLng - bounds.minLng));
          return { g, x, y, r: Math.max(14, Math.min(90, rPx)) };
        })
        .filter(Boolean),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [geofences, bounds],
  );

  return (
    <div className="relative overflow-hidden rounded-2xl bg-slate-950 ring-1 ring-slate-800">
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full">
        <defs>
          <radialGradient id="map-glow" cx="50%" cy="40%" r="80%">
            <stop offset="0%" stopColor="#0f172a" />
            <stop offset="100%" stopColor="#020617" />
          </radialGradient>
        </defs>
        <rect width={W} height={H} fill="url(#map-glow)" />

        {/* grilla urbana */}
        {Array.from({ length: 15 }).map((_, i) => (
          <line key={`v${i}`} x1={(i * W) / 14} y1="0" x2={(i * W) / 14} y2={H} stroke="#0f172a" strokeWidth="1" />
        ))}
        {Array.from({ length: 10 }).map((_, i) => (
          <line key={`h${i}`} x1="0" y1={(i * H) / 9} x2={W} y2={(i * H) / 9} stroke="#0f172a" strokeWidth="1" />
        ))}
        {/* avenidas */}
        <path d={`M0,${H * 0.3} C${W * 0.3},${H * 0.25} ${W * 0.6},${H * 0.45} ${W},${H * 0.35}`} fill="none" stroke="#1e293b" strokeWidth="7" strokeLinecap="round" />
        <path d={`M${W * 0.25},0 C${W * 0.3},${H * 0.35} ${W * 0.2},${H * 0.7} ${W * 0.35},${H}`} fill="none" stroke="#1e293b" strokeWidth="6" strokeLinecap="round" />
        <path d={`M${W * 0.65},0 L${W * 0.7},${H}`} fill="none" stroke="#1e293b" strokeWidth="5" />
        <path d={`M0,${H * 0.75} C${W * 0.4},${H * 0.65} ${W * 0.7},${H * 0.85} ${W},${H * 0.7}`} fill="none" stroke="#1e293b" strokeWidth="6" />
        <path d={`M0,${H * 0.3} C${W * 0.3},${H * 0.25} ${W * 0.6},${H * 0.45} ${W},${H * 0.35}`} fill="none" stroke="#334155" strokeWidth="1" strokeDasharray="8 8" />

        {/* geofences */}
        {fences.map((f, i) => (
          <g key={i}>
            <circle cx={f.x} cy={f.y} r={f.r} fill="#10b981" opacity="0.05" />
            <circle cx={f.x} cy={f.y} r={f.r} fill="none" stroke="#10b981" strokeOpacity="0.35" strokeWidth="1.2" strokeDasharray="5 5" />
            <text x={f.x} y={f.y - f.r - 5} fontSize="9" fill="#34d399" textAnchor="middle" opacity="0.8">
              {pick(f.g, 'name', 'label', 'title') ?? 'Geofence'}
            </text>
          </g>
        ))}

        {/* vehículos */}
        {pts.map(({ v, p }, i) => {
          const { x, y } = toXY(p.lat, p.lng);
          const status = pick(v, 'status', 'state') ?? 'active';
          const color = STATUS_COLOR[status] ?? '#10b981';
          const id = pick(v, 'id', 'vehicle_id', 'vehicleId') ?? i;
          const name = pick(v, 'plate', 'license_plate', 'name', 'label') ?? `#${id}`;
          const isSel = selected === id;
          const isHover = hover === id;
          return (
            <g
              key={id}
              transform={`translate(${x},${y})`}
              className="cursor-pointer"
              onClick={() => onSelect?.(v)}
              onMouseEnter={() => setHover(id)}
              onMouseLeave={() => setHover(null)}
            >
              <circle r={isSel || isHover ? 18 : 12} fill={color} opacity="0.15">
                <animate attributeName="r" values="12;20;12" dur="2.4s" repeatCount="indefinite" begin={`${i * 0.3}s`} />
                <animate attributeName="opacity" values="0.25;0;0.25" dur="2.4s" repeatCount="indefinite" begin={`${i * 0.3}s`} />
              </circle>
              <circle r="5.5" fill={color} stroke="#020617" strokeWidth="2" />
              {(isSel || isHover) && (
                <g>
                  <rect x="-52" y="-34" width="104" height="20" rx="6" fill="#0f172a" stroke={color} strokeOpacity="0.5" />
                  <text y="-20" fontSize="10" fill="#e2e8f0" textAnchor="middle" fontWeight="600">
                    {name}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>

      {/* leyenda */}
      <div className="absolute bottom-3 left-3 flex flex-wrap gap-2 rounded-xl bg-slate-950/85 px-3 py-2 ring-1 ring-slate-800 backdrop-blur">
        {[
          ['En movimiento', '#38bdf8'],
          ['Activo', '#10b981'],
          ['En espera', '#94a3b8'],
          ['Mantenimiento', '#a78bfa'],
        ].map(([l, c]) => (
          <span key={l} className="flex items-center gap-1.5 text-[10px] text-slate-400">
            <span className="size-2 rounded-full" style={{ background: c }} /> {l}
          </span>
        ))}
      </div>

      {!pts.length && (
        <div className="absolute inset-0 grid place-items-center bg-slate-950/60">
          <div className="text-center">
            <Navigation size={22} className="mx-auto text-slate-600" />
            <p className="mt-2 text-sm font-semibold text-slate-300">Sin posiciones activas</p>
            <p className="mt-1 max-w-xs text-xs text-slate-500">
              Cuando el backend reporte coordenadas de tracking, los vehículos aparecen acá en tiempo real.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export { STATUS_COLOR, statusLabel };
