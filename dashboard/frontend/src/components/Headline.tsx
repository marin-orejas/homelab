import type { Verdict } from "../lib/verdict";

export function Headline({ verdict }: { verdict: Verdict }) {
  return (
    <header className={`lede lede--${verdict.level}`}>
      <p className="lede__line">{verdict.headline}</p>
      <p className="lede__detail">{verdict.detail}</p>
    </header>
  );
}
