import { useState } from 'react';
import { Eye, EyeOff, Radio, ShieldCheck } from 'lucide-react';
import { api, extractToken, extractUser, storeSession } from '../lib/api.js';

export default function Login({ onLogin, onGuest }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const valid = email.trim().length > 3 && password.length > 0;

  const submit = async (e) => {
    e.preventDefault();
    if (!valid || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api('/api/auth/login', {
        method: 'POST',
        body: { email: email.trim(), password },
      });
      const token = extractToken(res);
      let user = extractUser(res);
      if (token) storeSession(token, user);
      if (!user) {
        try {
          user = await api('/api/auth/me');
        } catch {
          user = { email: email.trim() };
        }
        if (user) storeSession(token, user);
      }
      onLogin(user ?? { email: email.trim() });
    } catch (err) {
      setError(
        err.status === 401 || err.status === 403
          ? 'Credenciales inválidas. Revisá email y contraseña.'
          : 'No se pudo conectar con el backend (:4000).',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative grid min-h-screen place-items-center overflow-hidden bg-slate-950 px-6">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 left-1/2 h-96 w-[42rem] -translate-x-1/2 rounded-full bg-emerald-500/10 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-72 w-72 rounded-full bg-sky-500/5 blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm animate-fade-up">
        <div className="mb-8 text-center">
          <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-emerald-500/15 ring-1 ring-emerald-500/30">
            <Radio size={22} className="text-emerald-400" />
          </span>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-50">FleetPulse</h1>
          <p className="mt-1 text-sm text-slate-500">Centro de control de flota en tiempo real</p>
        </div>

        <form
          onSubmit={submit}
          className="space-y-4 rounded-2xl bg-slate-900/80 p-6 ring-1 ring-slate-800 shadow-xl backdrop-blur"
        >
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-400">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="operador@fleetpulse.io"
              className="w-full rounded-xl bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 ring-1 ring-slate-800 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 transition"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-400">Contraseña</label>
            <div className="relative">
              <input
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-xl bg-slate-950 px-3.5 py-2.5 pr-10 text-sm text-slate-100 ring-1 ring-slate-800 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 transition"
              />
              <button
                type="button"
                onClick={() => setShowPw((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {error && (
            <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300 ring-1 ring-red-500/25">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={!valid || loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 transition disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? 'Ingresando…' : 'Ingresar al centro de control'}
          </button>

          {onGuest && (
            <button
              type="button"
              onClick={onGuest}
              className="flex w-full items-center justify-center gap-1.5 rounded-xl py-1 text-xs text-slate-500 hover:text-slate-300 transition"
            >
              <ShieldCheck size={13} /> Explorar en modo lectura
            </button>
          )}
        </form>

        <p className="mt-6 text-center text-[11px] text-slate-600">
          Acceso por roles: admin · dispatcher · viewer
        </p>
      </div>
    </main>
  );
}
