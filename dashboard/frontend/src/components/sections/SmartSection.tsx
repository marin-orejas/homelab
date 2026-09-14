import type { SmartDisk, SmartState } from "../../api/types";
import { celsius, count, duration } from "../../lib/format";
import type { Severity } from "../../lib/metrics";
import { Band, Chip, Note, Stat } from "../primitives";

const STATE: Record<Severity, string> = {
  good: "Healthy",
  warning: "Watch",
  critical: "Failing",
};

export function SmartSection({ smart }: { smart: SmartState }) {
  const severity = smart.stale ? "critical" : smart.severity;

  return (
    <Band
      name="Disk health"
      note={smart.stale ? "reading is stale" : "read daily at 03:00"}
      severity={severity}
      wide
    >
      <div className="cells cells--head">
        <Stat
          label="Assessment"
          value={<Chip severity={severity}>{smart.stale ? "Stale" : STATE[smart.severity]}</Chip>}
          sub={
            smart.error ??
            `${smart.disks.length} ${smart.disks.length === 1 ? "disk" : "disks"} watched`
          }
        />
        <Stat
          label="Last read"
          value={duration(smart.age_seconds)}
          size="sm"
          sub={smart.age_seconds === null ? "nothing on file" : "ago"}
        />
      </div>

      <div className="drives">
        {smart.disks.map((disk) => (
          <DriveCard key={disk.label} disk={disk} />
        ))}
      </div>

      <Note>
        Read once a day rather than on demand: the USB dock cannot report
        power state honestly, so every query spins a parked disk back up.
        Anything older than {Math.round(smart.stale_after_seconds / 3600)}{" "}
        hours is flagged, because a daily reading that stopped arriving means
        the disks are no longer being watched.
      </Note>
    </Band>
  );
}

function DriveCard({ disk }: { disk: SmartDisk }) {
  return (
    <article className="drive">
      <header className="drive__head">
        <span className="drive__name">{disk.label}</span>
        <Chip severity={disk.severity}>
          {disk.present ? (disk.health ?? "unknown") : "absent"}
        </Chip>
      </header>

      <div className="cells">
        <Stat label="Temperature" value={celsius(disk.temp_c, 0)} size="sm" />
        <Stat
          label="Spin-ups"
          value={count(disk.start_stop)}
          size="sm"
          sub={
            disk.start_stop_delta === null
              ? "no second day recorded yet"
              : `${disk.start_stop_delta} since ${disk.delta_since_day}`
          }
        />
        <Stat
          label="Head parks"
          value={count(disk.load_cycle)}
          size="sm"
          sub={
            disk.load_cycle_delta === null
              ? "no second day recorded yet"
              : `${disk.load_cycle_delta} since ${disk.delta_since_day}`
          }
        />
        <Stat
          label="Bad sectors"
          value={count(disk.realloc)}
          size="sm"
          tone={disk.realloc ? "critical" : undefined}
          sub="remapped"
        />
      </div>
    </article>
  );
}
