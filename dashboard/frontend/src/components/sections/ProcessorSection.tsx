import type { CpuInfo } from "../../api/types";
import { megahertz, percent } from "../../lib/format";
import { CoreBars } from "../charts";
import { Band, Note, Stat, Subhead } from "../primitives";

export function ProcessorSection({ cpu }: { cpu: CpuInfo }) {
  const load1 = cpu.load_average["1m"];

  return (
    <Band
      name="Processor"
      note={`${cpu.cores_physical ?? "?"} cores · ${cpu.cores_logical} threads`}
    >
      <div className="cells">
        <Stat
          label="In use"
          value={cpu.percent === null ? "—" : cpu.percent.toFixed(1)}
          unit={cpu.percent === null ? undefined : "%"}
          sub={cpu.times_percent ? `${cpu.times_percent.idle.toFixed(0)} % idle` : undefined}
        />
        <Stat
          label="Load, 1 min"
          value={load1 === null ? "—" : load1.toFixed(2)}
          sub={
            cpu.load_average_percent === null
              ? undefined
              : `${cpu.load_average_percent} % of ${cpu.cores_logical} threads`
          }
        />
        <Stat
          label="Clock"
          value={cpu.frequency_mhz ? String(Math.round(cpu.frequency_mhz.current)) : "—"}
          unit={cpu.frequency_mhz ? "MHz" : undefined}
          sub={
            cpu.frequency_mhz
              ? `${megahertz(cpu.frequency_mhz.min)} to ${megahertz(cpu.frequency_mhz.max)}`
              : undefined
          }
        />
        <Stat
          label="Waiting on disk"
          value={cpu.times_percent?.iowait?.toFixed(1) ?? "—"}
          unit={cpu.times_percent?.iowait == null ? undefined : "%"}
          sub={
            cpu.times_percent?.steal == null
              ? undefined
              : `${percent(cpu.times_percent.steal)} stolen`
          }
        />
      </div>

      <Subhead>Per thread</Subhead>
      <CoreBars values={cpu.percent_per_core} />
      <Note>
        A true 0 to 100 scale. Rescaling to the highest reading would make an
        idle machine look busy.
      </Note>
    </Band>
  );
}
