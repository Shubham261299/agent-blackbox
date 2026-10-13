export type TimeUnit = "us" | "ms" | "s";

const UNIT_FACTOR: Record<TimeUnit, number> = { us: 0.001, ms: 1, s: 1000 };
const UNIT_LABEL: Record<TimeUnit, string> = { us: "µs", ms: "ms", s: "s" };

export function unitFor(maxMs: number): TimeUnit {
  if (maxMs < 1) return "us";
  if (maxMs < 1000) return "ms";
  return "s";
}

function trimmed(value: number, digits: number): string {
  return value.toFixed(digits).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
}

/** Human duration with 3 significant figures: 54 µs, 12.3 ms, 22.2 s, 1m 12s. */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms)) return "–";
  if (ms >= 60_000) {
    const total = Math.round(ms / 1000);
    return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
  }
  if (ms >= 1000) return `${trimmed(ms / 1000, ms >= 10_000 ? 1 : 2)} s`;
  if (ms >= 1) return `${trimmed(ms, ms >= 100 ? 0 : ms >= 10 ? 1 : 2)} ms`;
  const us = ms * 1000;
  if (us >= 1) return `${trimmed(us, us >= 100 ? 0 : us >= 10 ? 1 : 2)} µs`;
  return "<1 µs";
}

/** Offset from the start of the run: "start" for the root, otherwise "+12.3 ms". */
export function formatOffset(ms: number): string {
  return ms < 0.0005 ? "run start" : `+${formatDuration(ms)}`;
}

/** A clean tick label in a fixed unit, so every tick on an axis reads in the same unit. */
export function formatTick(ms: number, unit: TimeUnit): string {
  const value = ms / UNIT_FACTOR[unit];
  return `${trimmed(value, value < 10 && value % 1 !== 0 ? 2 : 1)} ${UNIT_LABEL[unit]}`;
}

/** Step of 1, 2 or 5 times a power of ten, giving roughly `target` intervals over `max`. */
export function niceStep(max: number, target = 5): number {
  if (!(max > 0)) return 1;
  const raw = max / target;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / magnitude;
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return nice * magnitude;
}

/** Tick positions from 0 up to (and not beyond) `max`. */
export function niceTicks(max: number, target = 5): number[] {
  if (!(max > 0)) return [0];
  const step = niceStep(max, target);
  const ticks: number[] = [];
  for (let i = 0; i * step <= max * (1 + 1e-9); i++) ticks.push(Number((i * step).toPrecision(12)));
  return ticks;
}

export interface BarGeometry {
  leftPct: number;
  widthPct: number;
}

/** Position of a span on a 0..totalMs axis, as percentages. Width is clamped to the axis. */
export function barGeometry(offsetMs: number, durationMs: number, totalMs: number): BarGeometry {
  if (!(totalMs > 0)) return { leftPct: 0, widthPct: 100 };
  const left = Math.min(Math.max(offsetMs / totalMs, 0), 1);
  const width = Math.min(Math.max(durationMs / totalMs, 0), 1 - left);
  return { leftPct: left * 100, widthPct: width * 100 };
}
