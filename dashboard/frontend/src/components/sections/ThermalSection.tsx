import type { Fan, Temperature } from "../../api/types";
import { celsius } from "../../lib/format";
import {
  peakTemperature,
  sanitiseTemperatures,
  temperatureSeverity,
  type Severity,
} from "../../lib/metrics";
import { Band, Chip, Meter, Note, Stat, Subhead } from "../primitives";

const ASSUMED_CEILING = 100;

const STATE: Record<Severity, string> = {
  good: "Nominal",
  warning: "Warm",
  critical: "Hot",
};

export function ThermalSection({
  temperatures,
  fans,
}: {
  temperatures: Temperature[];
  fans: Fan[];
}) {
  const readings = sanitiseTemperatures(temperatures);
  const hottest = peakTemperature(readings);
  const overall: Severity = hottest ? temperatureSeverity(hottest) : "good";

  const cpu = readings.find((entry) => entry.label.toLowerCase().includes("package"));
  const nvme = readings.find((entry) => entry.chip === "nvme" && entry.label === "Composite");
  const fan = fans[0];

  const hadSentinel = temperatures.some(
    (entry) => (entry.high ?? 0) > 150 || (entry.critical ?? 0) > 150,
  );

  return (
    <Band name="Thermal" note="hwmon" severity={overall}>
      <div className="cells">
        <Stat
          label="CPU package"
          value={cpu ? cpu.current.toFixed(0) : "—"}
          unit={cpu ? "°C" : undefined}
          tone={cpu ? temperatureSeverity(cpu) : undefined}
          sub={cpu?.high ? `limit ${celsius(cpu.high, 0)}` : "no limit published"}
        />
        <Stat
          label="NVMe"
          value={nvme ? nvme.current.toFixed(1) : "—"}
          unit={nvme ? "°C" : undefined}
          sub={
            nvme?.high && nvme?.critical
              ? `warns at ${nvme.high.toFixed(0)}, limit ${nvme.critical.toFixed(0)}`
              : undefined
          }
        />
        <Stat
          label="Fan"
          value={fan ? String(fan.rpm) : "—"}
          unit={fan ? "rpm" : undefined}
          sub={fan ? `reported by the “${fan.chip}” chip` : "no fan sensor"}
        />
        <Stat
          label="State"
          value={<Chip severity={overall}>{STATE[overall]}</Chip>}
          sub={hottest ? `hottest sensor ${celsius(hottest.current, 0)}` : undefined}
        />
      </div>

      <Subhead>Every sensor</Subhead>
      <div className="meters">
        {[...readings]
          .sort((a, b) => b.current - a.current)
          .map((entry) => {
            const ceiling = entry.critical ?? entry.high ?? ASSUMED_CEILING;
            return (
              <Meter
                key={`${entry.chip}-${entry.label}`}
                name={entry.label}
                percent={(entry.current / ceiling) * 100}
                severity={temperatureSeverity(entry)}
                value={celsius(entry.current)}
              />
            );
          })}
      </div>

      {hadSentinel ? (
        <Note>
          Some NVMe sensors publish <code>65261.85 °C</code> as their limit.
          That is the <code>0xFFFF</code> sentinel for “undefined”, not a
          temperature, so those limits are dropped. The readings themselves
          are real.
        </Note>
      ) : null}
    </Band>
  );
}
