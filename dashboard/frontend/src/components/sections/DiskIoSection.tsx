import type { SystemSnapshot } from "../../api/types";
import { bytes, bytesPerSecond, duration } from "../../lib/format";
import { diskRates, wholeDevices } from "../../lib/metrics";
import { Band, Note } from "../primitives";

export function DiskIoSection({
  system,
  previous,
}: {
  system: SystemSnapshot;
  previous: SystemSnapshot | undefined;
}) {
  const devices = wholeDevices(system.disk_io);
  const rates = diskRates(previous, system);

  return (
    <Band name="Disk traffic" note="since boot">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Device</th>
              <th className="num">Read</th>
              <th className="num">Written</th>
              <th className="num">Right now</th>
              <th className="num">Busy</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => {
              const rate = rates.find((entry) => entry.device === device.device);
              const read = rate?.read?.perSecond ?? 0;
              const write = rate?.write?.perSecond ?? 0;
              const busy = device.busy_time_ms === null ? null : device.busy_time_ms / 1000;

              const now =
                !rate?.read && !rate?.write
                  ? "—"
                  : read === 0 && write === 0
                    ? "idle"
                    : [
                        read > 0 ? `${bytesPerSecond(read)} read` : null,
                        write > 0 ? `${bytesPerSecond(write)} written` : null,
                      ]
                        .filter(Boolean)
                        .join(", ");

              return (
                <tr key={device.device}>
                  <td className="name">{device.device}</td>
                  <td className="num">{bytes(device.read_bytes)}</td>
                  <td className="num">{bytes(device.write_bytes)}</td>
                  <td className={`num${read || write ? " num--live" : ""}`}>{now}</td>
                  <td className="num">{duration(busy)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Note>
        Partitions are folded into their parent device. Counting{" "}
        <code>nvme0n1p2</code> next to <code>nvme0n1</code> would count the
        same traffic twice.
      </Note>
    </Band>
  );
}
