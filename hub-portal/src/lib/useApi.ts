import { useEffect, useState } from 'react';

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: { message: string; configRequired: boolean } | null;
}

export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ data: null, loading: true, error: null });
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    fn()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((err: any) => {
        if (cancelled) return;
        const msg = err?.detail || err?.message || String(err);
        const configRequired =
          /turnstile|api key|webhook secret|vault|prometheus|ANTHROPIC|requires config/i.test(msg);
        setState({ data: null, loading: false, error: { message: msg, configRequired } });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
