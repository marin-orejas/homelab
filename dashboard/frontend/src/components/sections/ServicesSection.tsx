import type { ServiceStatus } from "../../api/types";
import { Band, Chip, Note } from "../primitives";

export function ServicesSection({ services }: { services: ServiceStatus[] }) {
  if (services.length === 0) return null;

  const down = services.filter((service) => !service.reachable).length;

  return (
    <Band
      name="Services"
      note={
        down === 0
          ? `${services.length} answering`
          : `${down} of ${services.length} not answering`
      }
      severity={down > 0 ? "critical" : "good"}
    >
      <div className="services">
        {services.map((service) => (
          <article className="service" key={service.name}>
            <div className="service__top">
              <span className="service__name">{service.name}</span>
              <Chip severity={service.reachable ? "good" : "critical"}>
                {service.reachable ? (service.version ?? "up") : "no answer"}
              </Chip>
            </div>
            <p className="service__url">{service.url}</p>
            {service.error ? <p className="service__error">{service.error}</p> : null}
          </article>
        ))}
      </div>

      <Note>
        Adding one is a line of configuration rather than a code change. All
        of them are polled together, off the request path, so a slow service
        never slows this page down.
      </Note>
    </Band>
  );
}
