import type { Summary } from "../api/types";
import { isError } from "../api/types";
import { useTheme, type ThemePreference } from "../hooks/useTheme";
import { celsius, percent } from "../lib/format";
import { networkRates, peakTemperature } from "../lib/metrics";
import { bytesPerSecond } from "../lib/format";
import type { VerdictLevel } from "../lib/verdict";
import type { SystemSnapshot } from "../api/types";

export function TopRail({
  summary,
  previous,
  level,
  lastUpdated,
}: {
  summary: Summary | null;
  previous: SystemSnapshot | undefined;
  level: VerdictLevel;
  lastUpdated: Date | null;
}) {
  const { preference, cycle } = useTheme();

  const system = summary?.system;
  const hottest = system ? peakTemperature(system.sensors.temperatures) : null;
  const fullest = system
    ? [...system.disks].sort((a, b) => (b.percent ?? -1) - (a.percent ?? -1))[0]
    : undefined;

  const rates = system ? networkRates(previous, system) : [];
  const busiest = rates
    .map((rate) => rate.rx?.perSecond)
    .filter((value): value is number => value !== undefined)
    .sort((a, b) => b - a)[0];

  const streams =
    summary?.sessions && !isError(summary.sessions) ? summary.sessions.active_count : null;

  return (
    <div className="rail">
      <div className="rail__inner">
        <span className="rail__host">
          <span className={`rail__mark rail__mark--${level}`} aria-hidden="true" />
          {system?.host.hostname ?? "connecting"}
        </span>

        {system ? (
          <span className="rail__vitals">
            <RailVital label="CPU" value={percent(system.cpu.percent, 0)} />
            <RailVital label="RAM" value={percent(system.memory.ram.percent, 0)} />
            <RailVital
              label={fullest?.label ?? "disk"}
              value={percent(fullest?.percent ?? null, 0)}
            />
            <RailVital
              label="temp"
              value={hottest ? celsius(hottest.current, 0) : "—"}
              optional
            />
            <RailVital
              label="net"
              value={busiest === undefined ? "—" : bytesPerSecond(busiest)}
              optional
            />
            <RailVital
              label="streams"
              value={streams === null ? "—" : String(streams)}
              optional
            />
          </span>
        ) : null}

        <span className="rail__clock">
          {lastUpdated
            ? lastUpdated.toLocaleTimeString(undefined, {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hour12: false,
              })
            : "—"}
        </span>

        <ThemeButton preference={preference} onClick={cycle} />
      </div>

      <span
        className="rail__sweep"
        key={lastUpdated ? lastUpdated.getTime() : "idle"}
        aria-hidden="true"
      />
    </div>
  );
}

function RailVital({
  label,
  value,
  optional = false,
}: {
  label: string;
  value: string;
  optional?: boolean;
}) {
  return (
    <span className={`rail__vital${optional ? " rail__vital--optional" : ""}`}>
      <span className="rail__key">{label}</span>
      <span className="rail__value">{value}</span>
    </span>
  );
}

const THEME_LABEL: Record<ThemePreference, string> = {
  system: "Auto",
  light: "Light",
  dark: "Dark",
};

function ThemeButton({
  preference,
  onClick,
}: {
  preference: ThemePreference;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="rail__theme"
      onClick={onClick}
      aria-label={`Theme: ${THEME_LABEL[preference]}. Activate to change.`}
      title="Follows the system, then light, then dark"
    >
      {THEME_LABEL[preference]}
    </button>
  );
}
