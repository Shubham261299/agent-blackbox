import { useCallback, useEffect, useRef, useState } from "react";

export interface QueryState<T> {
  data: T | undefined;
  error: Error | undefined;
  /** True only until the first answer; refetches keep the previous data on screen. */
  loading: boolean;
  refetch: () => void;
}

interface Options<T> {
  /** Milliseconds until the next refetch, or false to stop. Receives the latest data. */
  refetchMs?: (data: T | undefined) => number | false;
}

const RETRY_AFTER_ERROR_MS = 3000;

export function useQuery<T>(load: () => Promise<T>, deps: readonly unknown[], options: Options<T> = {}): QueryState<T> {
  const [state, setState] = useState<{ data: T | undefined; error: Error | undefined; loading: boolean }>({
    data: undefined,
    error: undefined,
    loading: true,
  });
  const loadRef = useRef(load);
  loadRef.current = load;
  const refetchMsRef = useRef(options.refetchMs);
  refetchMsRef.current = options.refetchMs;
  const trigger = useRef<(() => void) | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setState({ data: undefined, error: undefined, loading: true });

    const run = async () => {
      clearTimeout(timer);
      let next: number | false = false;
      try {
        const data = await loadRef.current();
        if (cancelled) return;
        setState({ data, error: undefined, loading: false });
        next = refetchMsRef.current?.(data) ?? false;
      } catch (err) {
        if (cancelled) return;
        // keep whatever was on screen; show the error beside it and keep trying
        setState((prev) => ({ data: prev.data, error: err as Error, loading: false }));
        next = RETRY_AFTER_ERROR_MS;
      }
      if (next !== false && !cancelled) timer = setTimeout(run, next);
    };

    trigger.current = () => void run();
    void run();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const refetch = useCallback(() => trigger.current?.(), []);
  return { ...state, refetch };
}
