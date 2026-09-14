const BINARY_UNITS = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"] as const;

export function bytes(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value === 0) return "0 B";

  const exponent = Math.min(
    Math.floor(Math.log(Math.abs(value)) / Math.log(1024)),
    BINARY_UNITS.length - 1,
  );
  const scaled = value / 1024 ** exponent;
  const precision = exponent === 0 ? 0 : digits;
  return `${scaled.toFixed(precision)} ${BINARY_UNITS[exponent]}`;
}

export function bytesPerSecond(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${bytes(value)}/s`;
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)} %`;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US");
}

export function countCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs < 10_000) return count(value);
  for (const [limit, suffix] of [
    [1e9, "G"],
    [1e6, "M"],
    [1e3, "k"],
  ] as const) {
    if (abs >= limit) return `${(value / limit).toFixed(abs / limit >= 100 ? 0 : 1)} ${suffix}`;
  }
  return count(value);
}

export function celsius(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)} °C`;
}

export function duration(totalSeconds: number | null | undefined): string {
  if (totalSeconds === null || totalSeconds === undefined || Number.isNaN(totalSeconds)) {
    return "—";
  }

  const seconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (days > 0) return `${days} d ${hours} h`;
  if (hours > 0) return `${hours} h ${minutes} min`;
  if (minutes > 0) return `${minutes} min`;
  return `${seconds} s`;
}

export function durationLong(totalSeconds: number | null | undefined): string {
  if (totalSeconds === null || totalSeconds === undefined || Number.isNaN(totalSeconds)) {
    return "—";
  }
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (days) parts.push(`${days} d`);
  if (hours) parts.push(`${hours} h`);
  parts.push(`${minutes} min`);
  return parts.join(" ");
}

export function split(formatted: string): { value: string; unit?: string } {
  const index = formatted.lastIndexOf(" ");
  if (index === -1) return { value: formatted };
  return { value: formatted.slice(0, index), unit: formatted.slice(index + 1) };
}

export function megahertz(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value)} MHz`;
}

export function fillsIn(days: number): string {
  if (days < 1) return "within the day";
  const whole = Math.round(days);
  return `in about ${whole} ${whole === 1 ? "day" : "days"}`;
}
