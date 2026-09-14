import type { VerdictLevel } from "./verdict";

const PLATE: Record<VerdictLevel, string> = {
  good: "#A03C87",
  warning: "#9C6100",
  critical: "#C0322F",
  stale: "#806274",
};

function draw(plate: string): string {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">` +
    `<rect width="32" height="32" rx="7.5" fill="${plate}"/>` +
    `<path d="M7.8 23.2V9.8l8.2 8.6L24.2 9.8V23.2" fill="none" stroke="#FFF9FC"` +
    ` stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

let painted: VerdictLevel | null = null;

export function paintFavicon(level: VerdictLevel): void {
  if (level === painted) return;
  const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) return;
  link.href = draw(PLATE[level]);
  painted = level;
}
