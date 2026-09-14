import type { ProcessEntry, ProcessesInfo } from "../../api/types";
import { Band, Note } from "../primitives";

export function ProcessesSection({ processes }: { processes: ProcessesInfo }) {
  const awaitingSecondSample = processes.top_cpu.every((row) => row.cpu_percent === null);

  const statuses = Object.entries(processes.by_status)
    .sort((a, b) => b[1] - a[1])
    .map(([status, n]) => `${n} ${status}`)
    .join(", ");

  return (
    <Band name="Processes" note={`${processes.total} running · ${statuses}`} wide>
      <div className="pair">
        <div>
          <h3 className="subhead">Heaviest on CPU</h3>
          {awaitingSecondSample ? (
            <div className="empty">
              A CPU ranking needs two readings. It appears on the next poll.
            </div>
          ) : (
            <ProcessTable rows={processes.top_cpu} primary="cpu" />
          )}
        </div>
        <div>
          <h3 className="subhead">Heaviest on memory</h3>
          <ProcessTable rows={processes.top_memory} primary="memory" />
        </div>
      </div>

      <Note>
        Rows are named by what the process actually is, read from its command
        line on the host. A user name would be wrong here: user ids resolve
        against the container’s own password file, so everything owned by uid
        1000 used to read as <code>appuser</code>.
      </Note>
    </Band>
  );
}

function ProcessTable({
  rows,
  primary,
}: {
  rows: ProcessEntry[];
  primary: "cpu" | "memory";
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Process</th>
            <th className="num">{primary === "cpu" ? "CPU" : "Memory"}</th>
            <th className="num">{primary === "cpu" ? "Memory" : "CPU"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const cpu = row.cpu_percent === null ? "—" : `${row.cpu_percent.toFixed(1)} %`;
            const mem = `${row.memory_percent.toFixed(2)} %`;
            return (
              <tr key={`${row.pid}-${row.name}`}>
                <td className="name">
                  {row.service ?? row.name}
                  {row.service && row.service !== row.name ? (
                    <span className="table__aside">{row.name}</span>
                  ) : null}
                </td>
                <td className="num">{primary === "cpu" ? cpu : mem}</td>
                <td className="num">{primary === "cpu" ? mem : cpu}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
