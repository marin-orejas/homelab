import type { DiskTrend } from "../api/history";
import type { DiskUsage } from "../api/types";
import { bytes, fillsIn } from "../lib/format";
import { fillOutlook, usageSeverity, type Severity } from "../lib/metrics";
import { Bar, Band, Figure, Note } from "./primitives";

const RANK: Record<Severity, number> = { good: 0, warning: 1, critical: 2 };

const HORIZON_DAYS = 7;

const ROLE: Record<string, string> = {
  root: "system and configs",
  wd1tb: "series",
  toshiba2tb: "films",
};

export function StorageBand({
  disks,
  trend,
}: {
  disks: DiskUsage[];
  trend: DiskTrend | null;
}) {
  const projections = new Map(
    (trend?.disks ?? []).map((disk) => [disk.label, disk.projection]),
  );

  const worst = disks
    .map((disk) => usageSeverity(disk.percent))
    .reduce<Severity>((a, b) => (RANK[b] > RANK[a] ? b : a), "good");

  const ordered = [...disks].sort((a, b) => (b.percent ?? -1) - (a.percent ?? -1));

  return (
    <Band name="Storage" note="never joined" severity={worst} wide>
      <div className="disks">
        {ordered.map((disk) => (
          <DiskRow
            key={disk.label}
            disk={disk}
            projection={projections.get(disk.label) ?? null}
          />
        ))}
      </div>

      <Note>
        The two media disks stay separate on purpose. Films live on
        toshiba2tb and series on wd1tb, so they fill independently and a
        failure costs half the library rather than all of it.
      </Note>
    </Band>
  );
}

function DiskRow({
  disk,
  projection,
}: {
  disk: DiskUsage;
  projection: DiskTrend["disks"][number]["projection"] | null;
}) {
  const severity = usageSeverity(disk.percent);
  const outlook = fillOutlook(disk.free, projection);

  const projectedPercent =
    outlook && disk.total && disk.used !== null
      ? ((disk.used + outlook.bytesPerDay * HORIZON_DAYS) / disk.total) * 100
      : null;

  return (
    <article className={`disk${severity === "good" ? "" : ` disk--${severity}`}`}>
      <div className="disk__id">
        <span className="disk__name">{disk.label}</span>
        <span className="disk__role">{ROLE[disk.label] ?? disk.path}</span>
      </div>

      <div className="disk__gauge">
        <Bar
          percent={disk.percent}
          severity={severity}
          projected={projectedPercent}
          projectedLabel={`Projected level in ${HORIZON_DAYS} days`}
          height="lg"
        />
        <p className="disk__line">
          {disk.error ? (
            <span className="disk__fault">{disk.error}</span>
          ) : (
            <>
              <span>
                {bytes(disk.used)} of {bytes(disk.total)}
              </span>
              {outlook ? (
                <span className="disk__rate">
                  gaining {bytes(outlook.bytesPerDay)} a day · full{" "}
                  {fillsIn(outlook.daysLeft)}
                </span>
              ) : projection ? (
                <span className="disk__rate">not filling</span>
              ) : null}
            </>
          )}
        </p>
      </div>

      <div className="disk__reading">
        <Figure
          value={disk.percent === null ? "—" : disk.percent.toFixed(1)}
          unit={disk.percent === null ? undefined : "%"}
          size="lg"
          tone={severity}
        />
        <span className="disk__free">{bytes(disk.free)} free</span>
      </div>
    </article>
  );
}
