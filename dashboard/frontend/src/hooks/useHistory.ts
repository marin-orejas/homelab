import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { fetchHistory, type History, type HistoryRange } from "../api/history";

const REFRESH_INTERVAL_MS = 30_000;

export interface HistoryState {
  data: History | null;
  error: string | null;
  loading: boolean;
  range: HistoryRange;
  setRange: (range: HistoryRange) => void;
}

export function useHistory(initial: HistoryRange = "24h"): HistoryState {
  const [range, setRange] = useState<HistoryRange>(initial);
  const [data, setData] = useState<History | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async (target: HistoryRange) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const result = await fetchHistory(target, controller.signal);
      setData(result);
      setError(null);
    } catch (cause) {
      if (controller.signal.aborted) return;
      setError(
        cause instanceof ApiError ? cause.message : "Could not load history from the API.",
      );
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void load(range);

    const timer = window.setInterval(() => {
      if (!cancelled && document.visibilityState === "visible") void load(range);
    }, REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      abortRef.current?.abort();
    };
  }, [range, load]);

  return { data, error, loading, range, setRange };
}
