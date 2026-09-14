import {
  HISTORY_RANGES,
  RANGE_LABEL,
  type History,
  type HistoryRange,
} from "../../api/history";
import { bytes, bytesPerSecond, celsius, percent } from "../../lib/format";
import { MirroredChart, TimeSeriesChart } from "../charts";
import { Band, Note, Subhead } from "../primitives";

export function HistorySection({
  history,
  error,
  loading,
  range,
  onRangeChange,
}: {
  history: History | null;
  error: string | null;
  loading: boolean;
  range: HistoryRange;
  onRangeChange: (range: HistoryRange) => void;
}) {
  const points = history?.points ?? [];
  const stored = history?.storage;

  return (
    <Band
      name="History"
      note={
        stored?.samples !== undefined
          ? `${stored.samples.toLocaleString("en-US")} readings in ${bytes(stored.database_bytes)}`
          : undefined
      }
      wide
    >
      <div className="ranges" role="group" aria-label="History window">
        {HISTORY_RANGES.map((option) => (
          <button
            key={option}
            type="button"
            className={`ranges__button${option === range ? " ranges__button--on" : ""}`}
            aria-pressed={option === range}
            onClick={() => onRangeChange(option)}
          >
            {RANGE_LABEL[option]}
          </button>
        ))}
      </div>

      {error ? (
        <div className="alert" role="alert">
          <strong>{error}</strong> The live figures above do not go through
          the database and are unaffected.
        </div>
      ) : null}

      {!error && points.length === 0 ? (
        <div className="empty">
          {loading
            ? "Loading history…"
            : `Nothing was recorded in the last ${RANGE_LABEL[range]}. A reading is written every ${stored?.interval_seconds ?? 30} seconds, so a window this wide fills in gradually after a fresh start.`}
        </div>
      ) : null}

      {points.length > 0 ? (
        <div className="charts">
          <TimeSeriesChart
            points={points.map((p) => ({ ts: p.ts, value: p.cpu_percent }))}
            label="Processor"
            format={(v) => percent(v)}
            domainMax={100}
          />
          <TimeSeriesChart
            points={points.map((p) => ({ ts: p.ts, value: p.mem_percent }))}
            label="Memory"
            format={(v) => percent(v)}
            domainMax={100}
          />
          <TimeSeriesChart
            points={points.map((p) => ({ ts: p.ts, value: p.temp_max }))}
            label="Hottest sensor"
            format={(v) => celsius(v, 0)}
            domainFloor={60}
          />
          <MirroredChart
            points={points.map((p) => ({ ts: p.ts, up: p.net_rx_bps, down: p.net_tx_bps }))}
            upLabel="Network in"
            downLabel="out"
            format={bytesPerSecond}
            domainFloor={1024}
          />
          <MirroredChart
            points={points.map((p) => ({
              ts: p.ts,
              up: p.disk_read_bps,
              down: p.disk_write_bps,
            }))}
            upLabel="Disk read"
            downLabel="written"
            format={bytesPerSecond}
            domainFloor={1024}
          />
          <TimeSeriesChart
            points={points.map((p) => ({ ts: p.ts, value: p.streams }))}
            label="Streams"
            format={(v) => `${Math.round(v)}`}
            domainFloor={2}
          />
        </div>
      ) : null}

      {history?.disks.length ? (
        <>
          <Subhead>Disks over the same window</Subhead>
          <div className="charts">
            {history.disks
              .slice()
              .sort((a, b) => a.label.localeCompare(b.label))
              .map((disk) => (
                <TimeSeriesChart
                  key={disk.label}
                  points={disk.points.map((p) => ({ ts: p.ts, value: p.percent }))}
                  label={disk.label}
                  format={(v) => percent(v)}
                  domainMax={100}
                />
              ))}
          </div>
        </>
      ) : null}

      {stored?.samples !== undefined ? (
        <Note>
          Written every {stored.interval_seconds} seconds and kept for{" "}
          {stored.retention_days} days. Daily disk levels outlive that window
          and are kept for good, because a fill rate needs months before it
          means anything.
        </Note>
      ) : null}
    </Band>
  );
}
