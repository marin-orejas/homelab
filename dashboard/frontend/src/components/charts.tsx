import { useMemo } from "react";

const WIDTH = 720;
const HEIGHT = 150;

export interface SeriesPoint {
  ts: number;
  value: number | null;
}

export function CoreBars({ values }: { values: (number | null)[] }) {
  return (
    <div
      className="cores"
      role="img"
      aria-label={`Per-thread utilisation: ${values
        .map((v) => (v === null ? "not measured yet" : `${v.toFixed(1)} percent`))
        .join(", ")}`}
    >
      {values.map((value, index) => (
        <div className="cores__item" key={index}>
          <div className="cores__track">
            <div
              className="cores__fill"
              style={{ height: `${value === null ? 0 : Math.max(0, Math.min(100, value))}%` }}
            />
          </div>
          <div className="cores__value">{value === null ? "—" : value.toFixed(1)}</div>
        </div>
      ))}
    </div>
  );
}

export function TimeSeriesChart({
  points,
  label,
  format,
  domainMax,
  domainFloor = 0,
}: {
  points: SeriesPoint[];
  label: string;
  format: (value: number) => string;
  domainMax?: number;
  domainFloor?: number;
}) {
  const stats = useMemo(() => summarise(points), [points]);

  if (stats.filled < 2) {
    return <div className="empty">Not enough samples in this window yet.</div>;
  }

  const scale = domainMax ?? Math.max(stats.max, domainFloor);
  const y = (value: number) => HEIGHT - 4 - (value / (scale || 1)) * (HEIGHT - 12);
  const x = (index: number) => (index / (points.length - 1)) * WIDTH;

  const { line, areas } = buildPaths(points, x, y, HEIGHT - 2);
  const half = domainMax === undefined ? null : y(domainMax / 2);

  return (
    <figure className="chart">
      <div className="chart__scale">
        <span className="chart__axis">{label}</span>
        <span className="chart__peak">
          now {stats.last === null ? "—" : format(stats.last)} · peak {format(stats.max)}
        </span>
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${label}. Latest ${
          stats.last === null ? "unknown" : format(stats.last)
        }, peak ${format(stats.max)} over ${points.length} buckets.`}
      >
        {half === null ? null : (
          <line
            x1="0"
            y1={half}
            x2={WIDTH}
            y2={half}
            stroke="var(--line-firm)"
            strokeWidth="1"
            strokeDasharray="3 5"
            vectorEffect="non-scaling-stroke"
          />
        )}
        {areas.map((d, i) => (
          <path key={i} d={d} fill="var(--accent)" opacity="0.18" />
        ))}
        {line.map((d, i) => (
          <path
            key={i}
            d={d}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <line
          x1="0"
          y1={HEIGHT - 2}
          x2={WIDTH}
          y2={HEIGHT - 2}
          stroke="var(--line-firm)"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <TimeAxis points={points} />
    </figure>
  );
}

export function MirroredChart({
  points,
  upLabel,
  downLabel,
  format,
  domainFloor = 0,
}: {
  points: { ts: number; up: number | null; down: number | null }[];
  upLabel: string;
  downLabel: string;
  format: (value: number) => string;
  domainFloor?: number;
}) {
  const upSeries = useMemo(() => points.map((p) => ({ ts: p.ts, value: p.up })), [points]);
  const downSeries = useMemo(
    () => points.map((p) => ({ ts: p.ts, value: p.down })),
    [points],
  );

  const upStats = summarise(upSeries);
  const downStats = summarise(downSeries);

  if (upStats.filled < 2 && downStats.filled < 2) {
    return (
      <div className="empty">
        Not enough samples in this window yet. A rate is the difference between two
        buckets, and a window this wide has not filled two of them — try a shorter range.
      </div>
    );
  }

  const middle = HEIGHT / 2;
  const amplitude = middle - 6;
  const scale = Math.max(upStats.max, downStats.max, domainFloor);

  const x = (index: number) => (index / (points.length - 1)) * WIDTH;
  const yUp = (value: number) => middle - (value / (scale || 1)) * amplitude;
  const yDown = (value: number) => middle + (value / (scale || 1)) * amplitude;

  const up = buildPaths(upSeries, x, yUp, middle);
  const down = buildPaths(downSeries, x, yDown, middle);

  return (
    <figure className="chart">
      <div className="chart__scale">
        <span className="chart__axis">▲ {upLabel}</span>
        <span className="chart__peak">peak {format(scale)}</span>
        <span className="chart__axis">▼ {downLabel}</span>
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${upLabel} above the zero line, ${downLabel} below. Latest ${
          upStats.last === null ? "unknown" : format(upStats.last)
        } and ${downStats.last === null ? "unknown" : format(downStats.last)}.`}
      >
        {up.areas.map((d, i) => (
          <path key={`ua${i}`} d={d} fill="var(--accent)" opacity="0.20" />
        ))}
        {up.line.map((d, i) => (
          <path
            key={`ul${i}`}
            d={d}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {down.areas.map((d, i) => (
          <path key={`da${i}`} d={d} fill="var(--accent)" opacity="0.10" />
        ))}
        {down.line.map((d, i) => (
          <path
            key={`dl${i}`}
            d={d}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            strokeDasharray="5 3"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        <line
          x1="0"
          y1={middle}
          x2={WIDTH}
          y2={middle}
          stroke="var(--line-firm)"
          strokeWidth="1"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <TimeAxis
        points={points.map((p) => ({ ts: p.ts, value: p.up }))}
        centre={`${format(upStats.last ?? 0)} ▲ · ▼ ${format(downStats.last ?? 0)}`}
      />
    </figure>
  );
}

function TimeAxis({ points, centre }: { points: SeriesPoint[]; centre?: string }) {
  if (points.length === 0) return null;
  const first = new Date(points[0].ts * 1000);
  const last = new Date(points[points.length - 1].ts * 1000);
  const hours = (last.getTime() - first.getTime()) / 3_600_000;

  const stamp = (date: Date) => {
    if (hours > 72) {
      return date.toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" });
    }
    const clock = date.toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    if (hours <= 12) return clock;
    return `${date.toLocaleDateString(undefined, {
      day: "2-digit",
      month: "2-digit",
    })} ${clock}`;
  };

  return (
    <figcaption className="chart__caption">
      <span>{stamp(first)}</span>
      {centre ? <span className="chart__now">{centre}</span> : null}
      <span>{stamp(last)}</span>
    </figcaption>
  );
}

function summarise(points: SeriesPoint[]) {
  let max = 0;
  let filled = 0;
  let last: number | null = null;

  for (const point of points) {
    if (point.value === null || Number.isNaN(point.value)) continue;
    filled += 1;
    if (point.value > max) max = point.value;
    last = point.value;
  }

  return { max, filled, last };
}

function buildPaths(
  points: SeriesPoint[],
  x: (index: number) => number,
  y: (value: number) => number,
  baseline: number,
) {
  const line: string[] = [];
  const areas: string[] = [];

  let segment: { index: number; value: number }[] = [];

  const flush = () => {
    if (segment.length >= 2) {
      const d = segment
        .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.index)},${y(p.value)}`)
        .join(" ");
      line.push(d);
      areas.push(
        `${d} L${x(segment[segment.length - 1].index)},${baseline} L${x(segment[0].index)},${baseline} Z`,
      );
    }
    segment = [];
  };

  points.forEach((point, index) => {
    if (point.value === null || Number.isNaN(point.value)) flush();
    else segment.push({ index, value: point.value });
  });
  flush();

  return { line, areas };
}
