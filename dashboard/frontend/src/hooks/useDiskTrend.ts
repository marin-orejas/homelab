import { useEffect, useRef, useState } from "react";

import { fetchDiskTrend, type DiskTrend } from "../api/history";

const REFRESH_INTERVAL_MS = 60 * 60 * 1000;

export function useDiskTrend(days = 90): DiskTrend | null {
  const [trend, setTrend] = useState<DiskTrend | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const result = await fetchDiskTrend(days, controller.signal);
        if (!cancelled) setTrend(result);
      } catch {
      }
    };

    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      abortRef.current?.abort();
    };
  }, [days]);

  return trend;
}
