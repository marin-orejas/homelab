import { useEffect, useRef, useState, type ReactNode } from "react";

import type { Severity } from "../lib/metrics";

export function Band({
  name,
  note,
  severity = "good",
  wide = false,
  children,
}: {
  name: string;
  note?: ReactNode;
  severity?: Severity;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      className={`band${wide ? " band--wide" : ""}${
        severity === "good" ? "" : ` band--${severity}`
      }`}
    >
      <header className="band__head">
        <h2 className="band__name">{name}</h2>
        {note ? <span className="band__note">{note}</span> : null}
      </header>
      {children}
    </section>
  );
}

export function Subhead({ children }: { children: ReactNode }) {
  return <h3 className="subhead">{children}</h3>;
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="note">{children}</p>;
}

function useJustChanged(value: string): boolean {
  const seen = useRef<string | null>(null);
  const [changed, setChanged] = useState(false);

  useEffect(() => {
    if (seen.current === null) {
      seen.current = value;
      return;
    }
    if (seen.current === value) return;
    seen.current = value;
    setChanged(true);
    const timer = window.setTimeout(() => setChanged(false), 620);
    return () => window.clearTimeout(timer);
  }, [value]);

  return changed;
}

export type FigureSize = "sm" | "md" | "lg";

export function Figure({
  value,
  unit,
  size = "md",
  tone,
}: {
  value: string;
  unit?: string;
  size?: FigureSize;
  tone?: Severity;
}) {
  const changed = useJustChanged(unit ? `${value} ${unit}` : value);

  return (
    <span
      className={`fig fig--${size}${changed ? " fig--moved" : ""}${
        tone && tone !== "good" ? ` fig--${tone}` : ""
      }`}
    >
      {value}
      {unit ? <span className="fig__unit">{unit}</span> : null}
    </span>
  );
}

export function Stat({
  label,
  value,
  unit,
  sub,
  size = "md",
  tone,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  size?: FigureSize;
  tone?: Severity;
}) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <span className="stat__value">
        {typeof value === "string" || typeof value === "number" ? (
          <Figure value={String(value)} unit={unit} size={size} tone={tone} />
        ) : (
          value
        )}
      </span>
      {sub ? <span className="stat__sub">{sub}</span> : null}
    </div>
  );
}

export function Chip({
  severity,
  children,
}: {
  severity: Severity | "idle";
  children: ReactNode;
}) {
  return (
    <span className={`chip chip--${severity}`}>
      <span className="chip__mark" />
      {children}
    </span>
  );
}

export function Bar({
  percent,
  severity = "good",
  projected,
  projectedLabel,
  height = "md",
}: {
  percent: number | null;
  severity?: Severity;
  projected?: number | null;
  projectedLabel?: string;
  height?: "sm" | "md" | "lg";
}) {
  const filled = percent === null ? 0 : clamp(percent);
  const ahead =
    projected === null || projected === undefined ? 0 : Math.max(0, clamp(projected) - filled);

  return (
    <span className={`bar bar--${height}`}>
      <span className="bar__track">
        <span
          className={`bar__fill${severity === "good" ? "" : ` bar__fill--${severity}`}`}
          style={{ width: `${filled}%` }}
        />
        {ahead > 0 ? (
          <span
            className="bar__ahead"
            style={{ left: `${filled}%`, width: `${ahead}%` }}
            title={projectedLabel}
          />
        ) : null}
      </span>
    </span>
  );
}

export function Meter({
  name,
  percent,
  value,
  severity = "good",
}: {
  name: ReactNode;
  percent: number | null;
  value: ReactNode;
  severity?: Severity;
}) {
  return (
    <div className="meter">
      <span className="meter__name">{name}</span>
      <Bar percent={percent} severity={severity} height="sm" />
      <span className="meter__value">{value}</span>
    </div>
  );
}

export function Facts({ children }: { children: ReactNode }) {
  return <dl className="facts">{children}</dl>;
}

export function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function clamp(value: number): number {
  return Math.max(0, Math.min(100, value));
}
