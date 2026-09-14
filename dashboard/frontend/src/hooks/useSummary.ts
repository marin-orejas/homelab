import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, fetchSummary } from "../api/client";
import type { Summary, SystemSnapshot } from "../api/types";

const POLL_INTERVAL_MS = 5000;

export interface SummaryState {
  latest: Summary | null;
  previous: SystemSnapshot | undefined;
  error: string | null;
  loading: boolean;
  lastUpdated: Date | null;
  refresh: () => void;
}

export function useSummary(): SummaryState {
  const [latest, setLatest] = useState<Summary | null>(null);
  const [previous, setPrevious] = useState<SystemSnapshot | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const summary = await fetchSummary(controller.signal);
      setLatest((current) => {
        if (current) setPrevious(current.system);
        return summary;
      });
      setError(null);
      setLastUpdated(new Date());
    } catch (cause) {
      if (controller.signal.aborted) return;
      setError(
        cause instanceof ApiError ? cause.message : "Unexpected error while polling the API.",
      );
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const schedule = () => {
      timerRef.current = window.setTimeout(run, POLL_INTERVAL_MS);
    };

    const run = async () => {
      if (cancelled) return;
      if (document.visibilityState === "visible") {
        await load();
      }
      if (!cancelled) schedule();
    };

    void load().finally(() => {
      if (!cancelled) schedule();
    });

    const onVisibility = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, [load]);

  return {
    latest,
    previous,
    error,
    loading,
    lastUpdated,
    refresh: () => void load(),
  };
}
