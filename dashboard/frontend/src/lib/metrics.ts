import type { DiskProjection } from "../api/history";
import type { DiskIo, NetworkInterface, SystemSnapshot, Temperature } from "../api/types";

const SENTINEL_TEMPERATURE = 150;

export function sanitiseThreshold(value: number | null): number | null {
  if (value === null || Number.isNaN(value)) return null;
  return value > SENTINEL_TEMPERATURE ? null : value;
}

export function sanitiseTemperatures(temperatures: Temperature[]): Temperature[] {
  return temperatures.map((entry) => ({
    ...entry,
    high: sanitiseThreshold(entry.high),
    critical: sanitiseThreshold(entry.critical),
  }));
}

export function wholeDevices(entries: DiskIo[]): DiskIo[] {
  const names = entries.map((entry) => entry.device);
  return entries.filter(
    (entry) =>
      !names.some((other) => other !== entry.device && entry.device.startsWith(other)),
  );
}

export function activeInterfaces(interfaces: NetworkInterface[]): NetworkInterface[] {
  return interfaces.filter((nic) => nic.bytes_recv > 0 || nic.bytes_sent > 0);
}

export interface Rate {
  perSecond: number;
  reliable: boolean;
}

function rateBetween(previous: number, current: number, seconds: number): Rate | null {
  if (seconds <= 0) return null;
  const delta = current - previous;
  if (delta < 0) return { perSecond: 0, reliable: false };
  return { perSecond: delta / seconds, reliable: true };
}

export interface NetworkRates {
  interface: string;
  rx: Rate | null;
  tx: Rate | null;
}

export function networkRates(
  previous: SystemSnapshot | undefined,
  current: SystemSnapshot,
): NetworkRates[] {
  if (!previous) {
    return current.network.map((nic) => ({ interface: nic.interface, rx: null, tx: null }));
  }

  const seconds = current.timestamp - previous.timestamp;
  const before = new Map(previous.network.map((nic) => [nic.interface, nic]));

  return current.network.map((nic) => {
    const old = before.get(nic.interface);
    if (!old) return { interface: nic.interface, rx: null, tx: null };
    return {
      interface: nic.interface,
      rx: rateBetween(old.bytes_recv, nic.bytes_recv, seconds),
      tx: rateBetween(old.bytes_sent, nic.bytes_sent, seconds),
    };
  });
}

export interface DiskRates {
  device: string;
  read: Rate | null;
  write: Rate | null;
}

export function diskRates(
  previous: SystemSnapshot | undefined,
  current: SystemSnapshot,
): DiskRates[] {
  const devices = wholeDevices(current.disk_io);
  if (!previous) {
    return devices.map((device) => ({ device: device.device, read: null, write: null }));
  }

  const seconds = current.timestamp - previous.timestamp;
  const before = new Map(previous.disk_io.map((entry) => [entry.device, entry]));

  return devices.map((entry) => {
    const old = before.get(entry.device);
    if (!old) return { device: entry.device, read: null, write: null };
    return {
      device: entry.device,
      read: rateBetween(old.read_bytes, entry.read_bytes, seconds),
      write: rateBetween(old.write_bytes, entry.write_bytes, seconds),
    };
  });
}

export function peakTemperature(temperatures: Temperature[]): Temperature | null {
  const usable = temperatures.filter((entry) => Number.isFinite(entry.current));
  if (usable.length === 0) return null;
  return usable.reduce((hottest, entry) =>
    entry.current > hottest.current ? entry : hottest,
  );
}

export type Severity = "good" | "warning" | "critical";

export function temperatureSeverity(entry: Temperature): Severity {
  const critical = sanitiseThreshold(entry.critical);
  const high = sanitiseThreshold(entry.high);

  if (critical !== null && entry.current >= critical) return "critical";
  if (high !== null && entry.current >= high) return "warning";
  if (critical === null && high === null) {
    if (entry.current >= 90) return "critical";
    if (entry.current >= 75) return "warning";
  }
  return "good";
}

export function usageSeverity(percentUsed: number | null): Severity {
  if (percentUsed === null) return "good";
  if (percentUsed >= 90) return "critical";
  if (percentUsed >= 75) return "warning";
  return "good";
}

export interface FillOutlook {
  bytesPerDay: number;
  daysLeft: number;
}

export function fillOutlook(
  free: number | null,
  projection: DiskProjection | null | undefined,
): FillOutlook | null {
  if (!projection || projection.bytes_per_day <= 0) return null;
  if (projection.days_until_full === null) return null;
  const daysLeft =
    free === null ? projection.days_until_full : Math.max(0, free) / projection.bytes_per_day;
  return { bytesPerDay: projection.bytes_per_day, daysLeft };
}
