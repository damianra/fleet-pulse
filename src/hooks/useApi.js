import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api.js';

/**
 * Hook de datos con polling opcional.
 * useApi('/api/vehicles', { interval: 15000 })
 * → { data, loading, error, refetch }
 * `path === null` suspende el fetch.
 */
export function useApi(path, { interval, transform, enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState(null);
  const timer = useRef(null);
  const mounted = useRef(true);

  const refetch = useCallback(
    async (silent = false) => {
      if (!path) return;
      if (!silent) setLoading(true);
      try {
        const raw = await api(path);
        if (!mounted.current) return;
        setData(transform ? transform(raw) : raw);
        setError(null);
      } catch (e) {
        if (!mounted.current) return;
        setError(e);
      } finally {
        if (mounted.current) setLoading(false);
      }
    },
    [path, transform],
  );

  useEffect(() => {
    mounted.current = true;
    if (!path || !enabled) return undefined;
    refetch();
    if (interval) timer.current = setInterval(() => refetch(true), interval);
    return () => {
      mounted.current = false;
      if (timer.current) clearInterval(timer.current);
    };
  }, [path, interval, enabled, refetch]);

  return { data, loading, error, refetch };
}
