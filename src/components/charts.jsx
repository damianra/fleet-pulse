// Charts SVG puros (sin deps) — tema oscuro.
import { useId } from 'react';

const PALETTE = ['#10b981', '#38bdf8', '#a78bfa', '#fbbf24', '#f87171', '#94a3b8'];

/** Área/line chart suave. data: [{label, value}] */
export function AreaChart({ data = [], height = 160, color = '#10b981' }) {
  const gid = useId();
  if (!data.length) return <ChartEmpty height={height} />;
  const w = 600;
  const h = height;
  const pad = 8;
  const max = Math.max(...data.map((d) => d.value), 1);
  const stepX = data.length > 1 ? (w - pad * 2) / (data.length - 1) : 0;
  const pts = data.map((d, i) => [pad + i * stepX, h - pad - (d.value / max) * (h - pad * 2)]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const area = `${line} L${pts[pts.length - 1][0].toFixed(1)},${h - pad} L${pts[0][0].toFixed(1)},${h - pad} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1={pad} x2={w - pad} y1={h * f} y2={h * f} stroke="#1e293b" strokeDasharray="3 4" />
      ))}
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="3.5" fill={color}>
        <animate attributeName="r" values="3.5;5;3.5" dur="2s" repeatCount="indefinite" />
      </circle>
      {data.map((d, i) =>
        data.length <= 14 || i % Math.ceil(data.length / 10) === 0 ? (
          <text key={i} x={pts[i][0]} y={h - 0} fontSize="9" fill="#64748b" textAnchor="middle">
            {d.label}
          </text>
        ) : null,
      )}
    </svg>
  );
}

/** Barras verticales. data: [{label, value, color?}] */
export function Bars({ data = [], height = 180, color = '#10b981' }) {
  if (!data.length) return <ChartEmpty height={height} />;
  const w = 600;
  const h = height;
  const pad = 20;
  const max = Math.max(...data.map((d) => d.value), 1);
  const bw = Math.min(40, (w - pad * 2) / data.length - 8);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height }}>
      {data.map((d, i) => {
        const x = pad + (i * (w - pad * 2)) / data.length + ((w - pad * 2) / data.length - bw) / 2;
        const bh = (d.value / max) * (h - pad - 24);
        return (
          <g key={i}>
            <rect
              x={x}
              y={h - pad - bh}
              width={bw}
              height={bh}
              rx="4"
              fill={d.color || color}
              opacity="0.85"
            >
              <animate attributeName="height" from="0" to={bh} dur="0.6s" fill="freeze" />
              <animate attributeName="y" from={h - pad} to={h - pad - bh} dur="0.6s" fill="freeze" />
            </rect>
            <text x={x + bw / 2} y={h - 6} fontSize="9" fill="#64748b" textAnchor="middle">
              {String(d.label).slice(0, 8)}
            </text>
            {d.value > 0 && (
              <text x={x + bw / 2} y={h - pad - bh - 5} fontSize="9" fill="#94a3b8" textAnchor="middle">
                {d.value}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/** Donut. data: [{label, value, color?}] */
export function Donut({ data = [], size = 160, thickness = 18, centerLabel, centerValue }) {
  const total = data.reduce((s, d) => s + (Number(d.value) || 0), 0);
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  let acc = 0;
  return (
    <div className="flex items-center gap-5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0 -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e293b" strokeWidth={thickness} />
        {total > 0 &&
          data.map((d, i) => {
            const frac = d.value / total;
            const dash = `${frac * c} ${c}`;
            const offset = -acc * c;
            acc += frac;
            return (
              <circle
                key={i}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={d.color || PALETTE[i % PALETTE.length]}
                strokeWidth={thickness}
                strokeDasharray={dash}
                strokeDashoffset={offset}
                strokeLinecap="butt"
                className="transition-all duration-700"
              />
            );
          })}
        <g className="rotate-90" style={{ transformOrigin: 'center' }}>
          <text x="50%" y="47%" textAnchor="middle" fontSize="20" fontWeight="700" fill="#f1f5f9">
            {centerValue ?? total}
          </text>
          {centerLabel && (
            <text x="50%" y="60%" textAnchor="middle" fontSize="9" fill="#64748b">
              {centerLabel}
            </text>
          )}
        </g>
      </svg>
      <ul className="space-y-1.5 text-xs">
        {data.map((d, i) => (
          <li key={i} className="flex items-center gap-2 text-slate-400">
            <span
              className="size-2 rounded-full"
              style={{ background: d.color || PALETTE[i % PALETTE.length] }}
            />
            <span className="flex-1">{d.label}</span>
            <span className="font-semibold text-slate-200">{d.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ChartEmpty({ height = 140 }) {
  return (
    <div
      className="grid place-items-center rounded-lg bg-slate-900/50 text-xs text-slate-600 ring-1 ring-dashed ring-slate-800"
      style={{ height }}
    >
      Sin datos para graficar
    </div>
  );
}
