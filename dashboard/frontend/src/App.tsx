import { useEffect } from "react";

import { Headline } from "./components/Headline";
import { StorageBand } from "./components/StorageBand";
import { TopRail } from "./components/TopRail";
import { DiskIoSection } from "./components/sections/DiskIoSection";
import { HistorySection } from "./components/sections/HistorySection";
import { JellyfinSection } from "./components/sections/JellyfinSection";
import { MemorySection } from "./components/sections/MemorySection";
import { NetworkSection } from "./components/sections/NetworkSection";
import { ProcessesSection } from "./components/sections/ProcessesSection";
import { ProcessorSection } from "./components/sections/ProcessorSection";
import { ServicesSection } from "./components/sections/ServicesSection";
import { SmartSection } from "./components/sections/SmartSection";
import { ThermalSection } from "./components/sections/ThermalSection";
import { useDiskTrend } from "./hooks/useDiskTrend";
import { useHistory } from "./hooks/useHistory";
import { useSummary } from "./hooks/useSummary";
import { paintFavicon } from "./lib/favicon";
import { durationLong } from "./lib/format";
import { verdictFor } from "./lib/verdict";

export default function App() {
  const { latest, previous, error, loading, lastUpdated } = useSummary();
  const history = useHistory("24h");
  const trend = useDiskTrend();

  const verdict = verdictFor(latest, trend, error !== null, lastUpdated);
  const system = latest?.system;

  useEffect(() => {
    paintFavicon(verdict.level);
  }, [verdict.level]);

  return (
    <div className="page">
      <TopRail
        summary={latest}
        previous={previous}
        level={verdict.level}
        lastUpdated={lastUpdated}
      />

      <main className="shell">
        <Headline verdict={verdict} />

        {error ? (
          <div className="alert" role="alert">
            <strong>{error}</strong>
          </div>
        ) : null}

        {loading && !latest ? (
          <div className="empty empty--tall">Asking the server…</div>
        ) : null}

        {latest && system ? (
          <>
            <div className="plate">
              <StorageBand disks={system.disks} trend={trend} />
              <SmartSection smart={latest.smart} />

              <ProcessorSection cpu={system.cpu} />
              <MemorySection memory={system.memory} />

              <ThermalSection
                temperatures={system.sensors.temperatures}
                fans={system.sensors.fans}
              />
              <NetworkSection system={system} previous={previous} />

              {latest.sessions && latest.library ? (
                <JellyfinSection sessions={latest.sessions} library={latest.library} />
              ) : null}

              <DiskIoSection system={system} previous={previous} />
              <ServicesSection services={latest.services} />

              <ProcessesSection processes={system.processes} />

              <HistorySection
                history={history.data}
                error={history.error}
                loading={history.loading}
                range={history.range}
                onRangeChange={history.setRange}
              />
            </div>

            <footer className="colophon">
              <span>
                {system.host.hostname} · {system.host.kernel} · {system.host.architecture}
              </span>
              <span>
                {system.cpu.cores_physical ?? "?"} cores, {system.cpu.cores_logical} threads
                · up {durationLong(system.host.uptime_seconds)}
              </span>
              <span>
                Live figures every 5 s, recorded every 30 s
                {system.host.reading_host_procfs
                  ? ""
                  : " · reading the container, not the host"}
              </span>
            </footer>
          </>
        ) : null}
      </main>
    </div>
  );
}
