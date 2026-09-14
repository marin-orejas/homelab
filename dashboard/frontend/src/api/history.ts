import { ApiError } from "./client";

export interface HistoryPoint {
  ts: number;
  cpu_percent: number | null;
  load1: number | null;
  mem_percent: number | null;
  swap_percent: number | null;
  temp_max: number | null;
  fan_rpm: number | null;
  streams: number | null;
  transcodes: number | null;
  proc_total: number | null;
  net_rx_bps: number | null;
  net_tx_bps: number | null;
  disk_read_bps: number | null;
  disk_write_bps: number | null;
}

export interface DiskSeries {
  label: string;
  points: { ts: number; percent: number | null; used: number | null; total: number | null }[];
}

export interface StorageStats {
  enabled: boolean;
  samples?: number;
  oldest_sample?: number | null;
  retention_days?: number;
  interval_seconds?: number;
  database_bytes?: number;
  schema_version?: number;
  error?: string;
}

export interface History {
  range: HistoryRange;
  from: number;
  to: number;
  bucket_seconds: number;
  point_count: number;
  points: HistoryPoint[];
  disks: DiskSeries[];
  storage: StorageStats;
}

export const HISTORY_RANGES = ["1h", "6h", "24h", "7d", "30d"] as const;
export type HistoryRange = (typeof HISTORY_RANGES)[number];

export const RANGE_LABEL: Record<HistoryRange, string> = {
  "1h": "1 hour",
  "6h": "6 hours",
  "24h": "24 hours",
  "7d": "7 days",
  "30d": "30 days",
};

export async function fetchHistory(
  range: HistoryRange,
  signal?: AbortSignal,
): Promise<History> {
  const response = await fetch(`/api/history?range=${range}`, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (response.status === 503) {
    throw new ApiError("History is disabled on the server.", 503);
  }
  if (!response.ok) {
    throw new ApiError(`History request returned ${response.status}.`, response.status);
  }

  return (await response.json()) as History;
}

export interface DiskProjection {
  observed_days: number;
  sample_days: number;
  bytes_per_day: number;
  free_bytes: number | null;
  days_until_full: number | null;
}

export interface DiskTrendSeries {
  label: string;
  points: { day: string; percent: number | null; used: number | null; total: number | null }[];
  projection: DiskProjection | null;
}

export interface DiskTrend {
  days: number;
  disks: DiskTrendSeries[];
}

export async function fetchDiskTrend(
  days = 90,
  signal?: AbortSignal,
): Promise<DiskTrend> {
  const response = await fetch(`/api/history/disks?days=${days}`, {
    signal,
    headers: { Accept: "application/json" },
  });

  if (response.status === 503) {
    throw new ApiError("History is disabled on the server.", 503);
  }
  if (!response.ok) {
    throw new ApiError(`Disk trend request returned ${response.status}.`, response.status);
  }

  return (await response.json()) as DiskTrend;
}
