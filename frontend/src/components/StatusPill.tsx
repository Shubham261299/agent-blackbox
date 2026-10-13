import type { RunStatus, SpanStatus } from "../api/types";
import { Icon } from "./Icon";

const RUN: Record<RunStatus, { label: string; icon: "check" | "x" | "spinner" }> = {
  ok: { label: "Completed", icon: "check" },
  error: { label: "Failed", icon: "x" },
  running: { label: "Running", icon: "spinner" },
};

/** Status is always icon + label + tint, never colour alone. */
export function RunStatusPill({ status }: { status: RunStatus }) {
  const { label, icon } = RUN[status];
  return (
    <span className="pill" data-status={status}>
      <Icon name={icon} size={13} className={status === "running" ? "spin" : undefined} />
      {label}
    </span>
  );
}

const SPAN: Record<SpanStatus, { label: string; icon: "check" | "x" | null }> = {
  ok: { label: "OK", icon: "check" },
  error: { label: "Error", icon: "x" },
  unset: { label: "No error", icon: null },
};

export function SpanStatusPill({ status }: { status: SpanStatus }) {
  const { label, icon } = SPAN[status];
  return (
    <span className="pill" data-status={status === "unset" ? "neutral" : status}>
      {icon && <Icon name={icon} size={13} />}
      {label}
    </span>
  );
}
