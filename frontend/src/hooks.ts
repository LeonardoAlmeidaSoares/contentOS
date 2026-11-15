import { useEffect, useState } from "react";

/** Polling simples; `enabled` permite parar quando não há mais o que acompanhar. */
export function usePoll<T>(fn: () => Promise<T>, deps: unknown[], intervalMs = 1500, enabled: (d: T) => boolean = () => true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const d = await fn();
        if (stop) return;
        setData(d); setError(null);
        if (!enabled(d)) return;
      } catch (e) {
        if (!stop) setError(String(e));
      }
      timer = setTimeout(tick, intervalMs);
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}
