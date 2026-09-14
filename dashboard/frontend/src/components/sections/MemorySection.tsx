import type { MemoryInfo } from "../../api/types";
import { bytes, percent, split } from "../../lib/format";
import { usageSeverity } from "../../lib/metrics";
import { Band, Note, Stat } from "../primitives";

export function MemorySection({ memory }: { memory: MemoryInfo }) {
  const { ram, swap } = memory;
  const cached = ram.cached ?? 0;
  const buffers = ram.buffers ?? 0;
  const share = (value: number) => (ram.total > 0 ? (value / ram.total) * 100 : 0);

  return (
    <Band
      name="Memory"
      note={`${bytes(ram.total)} fitted`}
      severity={usageSeverity(ram.percent)}
    >
      <div
        className="stack"
        role="img"
        aria-label={`Memory: ${bytes(ram.used)} used, ${bytes(cached)} cached, ${bytes(
          buffers,
        )} buffers, ${bytes(ram.free)} free`}
      >
        <span className="stack__part stack__part--used" style={{ width: `${share(ram.used)}%` }} />
        <span
          className="stack__part stack__part--cached"
          style={{ width: `${share(cached)}%` }}
        />
        <span
          className="stack__part stack__part--buffers"
          style={{ width: `${share(buffers)}%` }}
        />
      </div>

      <div className="keys">
        <Key kind="used" label="Used" value={bytes(ram.used)} />
        <Key kind="cached" label="Cached" value={bytes(cached)} />
        <Key kind="buffers" label="Buffers" value={bytes(buffers)} />
        <Key kind="free" label="Free" value={bytes(ram.free)} />
      </div>

      <div className="cells">
        <Stat
          label="In use"
          value={ram.percent.toFixed(1)}
          unit="%"
          sub={`${bytes(ram.available)} available`}
        />
        <Stat
          label="Swap"
          value={swap.percent.toFixed(1)}
          unit="%"
          sub={`${bytes(swap.used)} of ${bytes(swap.total)}`}
        />
        <Stat
          label="Reclaimable"
          {...split(bytes(cached + buffers, 2))}
          sub="cache the kernel hands back on demand"
        />
      </div>

      <Note>
        Cache and buffers sit outside “in use” because the kernel releases
        them the moment something needs the memory. {percent(ram.percent)} is
        the figure that matters.
      </Note>
    </Band>
  );
}

function Key({
  kind,
  label,
  value,
}: {
  kind: "used" | "cached" | "buffers" | "free";
  label: string;
  value: string;
}) {
  return (
    <span className="key">
      <span className={`key__swatch key__swatch--${kind}`} />
      {label} {value}
    </span>
  );
}
