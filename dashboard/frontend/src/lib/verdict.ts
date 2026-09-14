import type { DiskTrend } from "../api/history";
import type { Summary } from "../api/types";
import { isError } from "../api/types";
import { bytes, duration, fillsIn } from "./format";
import {
  fillOutlook,
  peakTemperature,
  temperatureSeverity,
  usageSeverity,
  type Severity,
} from "./metrics";

export type VerdictLevel = Severity | "stale";

export interface Verdict {
  level: VerdictLevel;
  headline: string;
  detail: string;
  focus: string | null;
}

const RANK: Record<VerdictLevel, number> = { good: 0, warning: 1, critical: 2, stale: 3 };

interface Finding {
  level: VerdictLevel;
  headline: string;
  focus?: string;
}

export function verdictFor(
  summary: Summary | null,
  trend: DiskTrend | null,
  stale: boolean,
  lastUpdated: Date | null,
): Verdict {
  if (!summary) {
    return {
      level: "stale",
      headline: "Waiting for the first reading.",
      detail: "The page asks the server every 5 seconds.",
      focus: null,
    };
  }

  if (stale) {
    const at = lastUpdated
      ? lastUpdated.toLocaleTimeString(undefined, {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        })
      : null;
    return {
      level: "stale",
      headline: "The server stopped answering.",
      detail: at
        ? `Everything below is the reading from ${at}, not live.`
        : "Everything below is the last reading received, not live.",
      focus: null,
    };
  }

  const { system, smart } = summary;
  const findings: Finding[] = [];

  const byDisk = new Map<string, Finding>();

  for (const disk of system.disks) {
    if (disk.error) {
      byDisk.set(disk.label, {
        level: "critical",
        headline: `${disk.label} is not reporting.`,
        focus: disk.label,
      });
      continue;
    }
    const level = usageSeverity(disk.percent);
    if (level !== "good") {
      byDisk.set(disk.label, {
        level,
        headline: `${disk.label} is ${disk.percent?.toFixed(0)} % full, with ${bytes(disk.free)} left.`,
        focus: disk.label,
      });
    }
  }

  const filling = (trend?.disks ?? [])
    .filter((disk) => disk.projection?.days_until_full != null)
    .sort((a, b) => a.projection!.days_until_full! - b.projection!.days_until_full!)[0];

  if (filling) {
    const disk = system.disks.find((entry) => entry.label === filling.label);
    const outlook = fillOutlook(disk?.free ?? null, filling.projection);

    if (outlook && outlook.daysLeft <= 30) {
      const level: VerdictLevel = outlook.daysLeft <= 7 ? "critical" : "warning";
      const already = byDisk.get(filling.label);

      byDisk.set(filling.label, {
        level: RANK[level] > RANK[already?.level ?? "good"] ? level : already!.level,
        headline: already
          ? `${filling.label} is ${disk?.percent?.toFixed(0)} % full and fills ${fillsIn(outlook.daysLeft)}.`
          : `${filling.label} fills ${fillsIn(outlook.daysLeft)} at the current rate.`,
        focus: filling.label,
      });
    }
  }

  findings.push(...byDisk.values());

  if (smart.stale) {
    findings.push({
      level: "critical",
      headline: "Nothing has checked the disks since the last daily reading.",
    });
  } else if (smart.severity !== "good") {
    const bad = smart.disks.find((disk) => disk.severity !== "good");
    findings.push({
      level: smart.severity,
      headline: bad
        ? `SMART reports ${bad.label} as ${bad.health ?? "unhealthy"}.`
        : "SMART reports a problem.",
      focus: bad?.label,
    });
  }

  const hottest = peakTemperature(system.sensors.temperatures);
  if (hottest) {
    const level = temperatureSeverity(hottest);
    if (level !== "good") {
      findings.push({
        level,
        headline: `${hottest.label} is running at ${hottest.current.toFixed(0)} °C.`,
      });
    }
  }

  const ram = system.memory.ram.percent;
  if (ram >= 90) {
    findings.push({
      level: ram >= 95 ? "critical" : "warning",
      headline: `Memory is ${ram.toFixed(0)} % used, with ${bytes(system.memory.ram.available)} available.`,
    });
  }

  const worst = findings.sort((a, b) => RANK[b.level] - RANK[a.level])[0];

  const streams =
    summary.sessions && !isError(summary.sessions) ? summary.sessions.active_count : null;

  const playing =
    streams && streams > 0
      ? `${streams} ${streams === 1 ? "stream" : "streams"} playing`
      : "nothing playing";

  const up = `up ${duration(system.host.uptime_seconds)}`;

  if (!worst) {
    return {
      level: "good",
      headline: `${system.host.hostname} is healthy.`,
      detail: `${capitalise(up)}, ${playing}, every disk inside its limits.`,
      focus: null,
    };
  }

  const others = findings.filter((finding) => finding !== worst);
  const alsoText =
    others.length === 0
      ? "Everything else reads normal."
      : others.length === 1
        ? others[0].headline
        : `${others[0].headline} ${others.length - 1} more reading${
            others.length === 2 ? "" : "s"
          } need attention.`;

  return {
    level: worst.level,
    headline: worst.headline,
    detail: `${alsoText} ${capitalise(up)}, ${playing}.`,
    focus: worst.focus ?? null,
  };
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
