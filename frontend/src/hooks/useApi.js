import { useState, useEffect, useCallback } from 'react';

const BASE = process.env.REACT_APP_API_URL || '';

async function apiFetch(path) {
  const res = await fetch(`${BASE}${path}`);
  if (res.status === 401) { window.location.href = '/auth/login'; throw new Error('401'); }
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export function useApi(path, deps = [], refreshInterval = 0) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true); setError(null);
      setData(await apiFetch(path));
    } catch (e) {
      if (e.message !== '401') setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [path]); // eslint-disable-line

  useEffect(() => {
    load();
    if (refreshInterval > 0) { const t = setInterval(load, refreshInterval); return () => clearInterval(t); }
  }, [load, refreshInterval]);

  return { data, loading, error, reload: load };
}

export async function triggerFetch() {
  const res = await fetch(`${BASE}/api/fetch_now`, { method: 'POST' });
  return res.json();
}
