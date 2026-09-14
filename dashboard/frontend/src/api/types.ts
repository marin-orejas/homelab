export interface HostInfo {
  hostname: string;
  kernel: string;
  architecture: string;
  boot_time: number;
  uptime_seconds: number;
  python_version: string;
  procfs_path: string;
  reading_host_procfs: boolean;
}

export interface CpuInfo {
  percent: number | null;
  percent_per_core: (number | null)[];
  cores_physical: number | null;
  cores_logical: number;
  interval_seconds: number | null;
  frequency_mhz: { current: number; min: number; max: number } | null;
  load_average: { "1m": number | null; "5m": number | null; "15m": number | null };
  load_average_percent: number | null;
  times_percent: {
    user: number;
    system: number;
    idle: number;
    iowait: number | null;
    steal: number | null;
  } | null;
}

export interface MemoryInfo {
  ram: {
    total: number;
    available: number;
    used: number;
    free: number;
    percent: number;
    cached: number | null;
    buffers: number | null;
  };
  swap: { total: number; used: number; free: number; percent: number };
}

export interface DiskUsage {
  label: string;
  path: string;
  total: number | null;
  used: number | null;
  free: number | null;
  percent: number | null;
  error: string | null;
}

export interface DiskIo {
  device: string;
  read_bytes: number;
  write_bytes: number;
  read_count: number;
  write_count: number;
  read_time_ms: number;
  write_time_ms: number;
  busy_time_ms: number | null;
}

export interface NetworkInterface {
  interface: string;
  bytes_sent: number;
  bytes_recv: number;
  packets_sent: number;
  packets_recv: number;
  errors_in: number;
  errors_out: number;
  drop_in: number;
  drop_out: number;
}

export interface Temperature {
  chip: string;
  label: string;
  current: number;
  high: number | null;
  critical: number | null;
}

export interface Fan {
  chip: string;
  label: string;
  rpm: number;
}

export interface ProcessEntry {
  pid: number;
  name: string;
  service: string | null;
  cpu_percent: number | null;
  memory_percent: number;
  status: string;
}

export interface ProcessesInfo {
  total: number;
  by_status: Record<string, number>;
  cores_logical: number;
  top_cpu: ProcessEntry[];
  top_memory: ProcessEntry[];
}

export interface SystemSnapshot {
  timestamp: number;
  snapshot_age_seconds: number;
  host: HostInfo;
  cpu: CpuInfo;
  memory: MemoryInfo;
  disks: DiskUsage[];
  disk_io: DiskIo[];
  network: NetworkInterface[];
  sensors: { temperatures: Temperature[]; fans: Fan[] };
  processes: ProcessesInfo;
}

export interface StreamSession {
  session_id: string;
  user: string | null;
  client: string | null;
  device: string | null;
  remote_endpoint: string | null;
  item: {
    title: string | null;
    type: string | null;
    year: number | null;
    runtime_ticks: number | null;
  } | null;
  play_state: {
    is_paused: boolean | null;
    position_ticks: number | null;
    progress_percent: number | null;
    play_method: string | null;
    audio_stream_index: number | null;
    subtitle_stream_index: number | null;
  };
  transcoding: {
    reasons: string[];
    is_video_direct: boolean | null;
    is_audio_direct: boolean | null;
    video_codec: string | null;
    audio_codec: string | null;
    container: string | null;
    bitrate: number | null;
    framerate: number | null;
    completion_percentage: number | null;
    hardware_acceleration: string | null;
  } | null;
}

export interface SessionsInfo {
  active_count: number;
  transcoding_count: number;
  direct_play_count: number;
  idle_client_count: number;
  sessions: StreamSession[];
}

export interface LibraryInfo {
  counts: {
    movies: number | null;
    series: number | null;
    episodes: number | null;
  };
  server: {
    name: string | null;
    version: string | null;
    has_pending_restart: boolean | null;
    has_update_available: boolean | null;
  };
}

export interface ServiceStatus {
  name: string;
  kind: string;
  url: string;
  reachable: boolean;
  version: string | null;
  error: string | null;
}

export interface SmartDisk {
  label: string;
  present: boolean;
  health: string | null;
  start_stop: number | null;
  load_cycle: number | null;
  realloc: number | null;
  temp_c: number | null;
  severity: "good" | "warning" | "critical";
  start_stop_delta: number | null;
  load_cycle_delta: number | null;
  delta_since_day: string | null;
}

export interface SmartState {
  path: string;
  generated_at: string | null;
  age_seconds: number | null;
  stale: boolean;
  stale_after_seconds: number;
  severity: "good" | "warning" | "critical";
  disks: SmartDisk[];
  error?: string;
}

export interface CollectorError {
  error: string;
}

export type Maybe<T> = T | CollectorError;

export interface Summary {
  system: SystemSnapshot;
  smart: SmartState;
  services: ServiceStatus[];
  sessions?: Maybe<SessionsInfo>;
  library?: Maybe<LibraryInfo>;
}

export function isError<T>(value: Maybe<T>): value is CollectorError {
  return value !== null && typeof value === "object" && "error" in value;
}
