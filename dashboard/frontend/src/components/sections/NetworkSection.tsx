import type { SystemSnapshot } from "../../api/types";
import { bytes, bytesPerSecond, count, countCompact, split } from "../../lib/format";
import { activeInterfaces, networkRates } from "../../lib/metrics";
import { Band, Note, Stat } from "../primitives";

export function NetworkSection({
  system,
  previous,
}: {
  system: SystemSnapshot;
  previous: SystemSnapshot | undefined;
}) {
  const interfaces = activeInterfaces(system.network);
  const primary = interfaces[0] ?? system.network[0];
  const rate = networkRates(previous, system).find(
    (entry) => entry.interface === primary?.interface,
  );

  if (!primary) {
    return (
      <Band name="Network">
        <div className="empty">No host interface is reporting.</div>
      </Band>
    );
  }

  const dropped = primary.drop_in + primary.drop_out;
  const errors = primary.errors_in + primary.errors_out;

  return (
    <Band name="Network" note={primary.interface}>
      <div className="cells">
        <Stat
          label="Coming in"
          {...(rate?.rx ? split(bytesPerSecond(rate.rx.perSecond)) : { value: "—" })}
          sub={rate?.rx ? `${bytes(primary.bytes_recv)} since boot` : "awaiting a second sample"}
        />
        <Stat
          label="Going out"
          {...(rate?.tx ? split(bytesPerSecond(rate.tx.perSecond)) : { value: "—" })}
          sub={rate?.tx ? `${bytes(primary.bytes_sent)} since boot` : "awaiting a second sample"}
        />
        <Stat
          label="Packets in"
          value={countCompact(primary.packets_recv)}
          sub={`${countCompact(primary.packets_sent)} out`}
        />
        <Stat
          label="Dropped"
          value={count(dropped)}
          tone={errors > 0 ? "warning" : undefined}
          sub={`${count(errors)} errors`}
        />
      </div>

      <Note>
        Link speed, MTU and up-state are missing because they cannot be read
        honestly: sysfs answers from the container’s own network namespace,
        so those fields would describe the wrong interface.
      </Note>
    </Band>
  );
}
