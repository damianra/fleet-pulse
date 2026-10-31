// Cliente único del backend FleetPulse (:4000 via proxy Vite).
// Auth por cookie httpOnly `auth` (JWT) — los GET viajan con
// credentials:'include'. Las mutaciones exigen CSRF double-submit:
// la cookie legible `csrf` se reenvía como header `x-csrf-token`.
const USER_KEY = 'fleetpulse.user';

export const getStoredUser = () => {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
  } catch {
    return null;
  }
};
export const storeSession = (_token, user) => {
  // Compat: antes guardaba Bearer — ahora el token vive en la cookie
  // httpOnly; solo persiste el perfil para el shell.
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
};
export const clearSession = () => {
  localStorage.removeItem(USER_KEY);
};

const readCookie = (name) =>
  document.cookie
    .split('; ')
    .find((c) => c.startsWith(`${name}=`))
    ?.split('=')[1] ?? null;

export async function api(path, { method = 'GET', body, headers = {}, ...rest } = {}) {
  const mutating = !['GET', 'HEAD', 'OPTIONS'].includes(method);
  const csrf = mutating ? readCookie('csrf') : null;
  const res = await fetch(path, {
    method,
    credentials: 'include', // cookie `auth` httpOnly — Bearer solo es para externos
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(csrf ? { 'x-csrf-token': csrf } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...rest,
  });
  let data = null;
  const text = await res.text().catch(() => '');
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const err = new Error(
      (data && (data.detail || data.error || data.message)) || `Error ${res.status}`,
    );
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// ---- Normalizadores defensivos (el shape exacto puede variar) ----

/** Extrae un array de una respuesta (array directo o bajo claves comunes). */
export function asArray(payload) {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== 'object') return [];
  for (const k of ['items', 'data', 'results', 'rows', 'records', 'list']) {
    if (Array.isArray(payload[k])) return payload[k];
  }
  const arr = Object.values(payload).find(Array.isArray);
  return Array.isArray(arr) ? arr : [];
}

/** Primer valor definido/no-nulo entre claves alternativas. */
export function pick(obj, ...keys) {
  if (!obj || typeof obj !== 'object') return undefined;
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== null) return obj[k];
  }
  return undefined;
}

/** Compat con vistas que buscaban token en el payload — con cookie auth
 * la respuesta de login ya ES el user; devuelve null y las vistas caen
 * a /api/auth/me. */
export function extractToken() {
  return null;
}

export function extractUser(payload) {
  // El backend devuelve el User directo ({id,email,role,...}).
  if (payload?.id && payload?.email) return payload;
  return pick(payload, 'user', 'me', 'profile') ?? payload?.data?.user ?? null;
}
