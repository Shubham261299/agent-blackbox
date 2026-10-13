import { useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import type { SpanRecord, SpanType } from "../api/types";
import { buildRows, traceDurationMs } from "../lib/spanTree";
import { barGeometry, formatDuration, formatOffset, formatTick, niceStep, niceTicks, unitFor } from "../lib/timeScale";
import { Icon, type IconName } from "./Icon";

export const TYPE_LABEL: Record<SpanType, string> = {
  agent: "Agent run",
  llm: "Model call",
  tool: "Tool call",
  other: "Span",
};
export const TYPE_ICON: Record<SpanType, IconName> = { agent: "agent", llm: "chat", tool: "tool", other: "agent" };

export function Legend() {
  return (
    <ul className="legend" aria-label="Legend">
      {(["agent", "llm", "tool"] as const).map((t) => (
        <li key={t}>
          <span className="swatch" data-type={t} aria-hidden="true" />
          {TYPE_LABEL[t]}
        </li>
      ))}
      <li>
        <span className="swatch" data-failed="true" aria-hidden="true" />
        Failed
      </li>
    </ul>
  );
}

interface Hover {
  id: string;
  x: number;
  y: number;
}

export function Waterfall({
  spans,
  selectedId,
  onSelect,
}: {
  spans: SpanRecord[];
  selectedId: string | null;
  onSelect: (spanId: string) => void;
}) {
  const rows = useMemo(() => buildRows(spans), [spans]);
  const total = useMemo(() => traceDurationMs(spans), [spans]);
  const unit = unitFor(total);
  const ticks = useMemo(() => niceTicks(total), [total]);
  const step = niceStep(total);
  const [hover, setHover] = useState<Hover | null>(null);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  const hovered = hover ? rows.find((r) => r.span.span_id === hover.id)?.span : undefined;
  const style = { "--grid-step": `${total > 0 ? (step / total) * 100 : 100}%` } as CSSProperties;

  function move(index: number) {
    const target = rows[Math.max(0, Math.min(rows.length - 1, index))];
    if (!target) return;
    onSelect(target.span.span_id);
    buttons.current[rows.indexOf(target)]?.focus();
  }

  function onKeyDown(event: KeyboardEvent, index: number) {
    const next =
      event.key === "ArrowDown" ? index + 1 : event.key === "ArrowUp" ? index - 1 : event.key === "Home" ? 0 : event.key === "End" ? rows.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    move(next);
  }

  function showAtBar(event: { currentTarget: HTMLElement }, id: string) {
    const track = event.currentTarget.querySelector(".wf-bar") as HTMLElement | null;
    const box = (track ?? event.currentTarget).getBoundingClientRect();
    setHover({ id, x: box.left + box.width / 2, y: box.top });
  }

  return (
    <div className="wf-scroll">
      <div className="wf" style={style} role="group" aria-label="Trace waterfall">
        <div className="wf-head" aria-hidden="true">
          <span>Span</span>
          <span className="wf-dur">Duration</span>
          <span className="wf-axis">
            {ticks.map((t, i) => (
              <span key={t} className="wf-tick" style={{ left: `${(t / total) * 100}%` }} data-first={i === 0}>
                {formatTick(t, unit)}
              </span>
            ))}
          </span>
        </div>

        {rows.map(({ span, depth }, i) => {
          const { leftPct, widthPct } = barGeometry(span.start_offset_ms, span.duration_ms, total);
          const failed = span.status === "error";
          return (
            <button
              key={span.span_id}
              ref={(el) => {
                buttons.current[i] = el;
              }}
              type="button"
              className="wf-row"
              data-selected={span.span_id === selectedId}
              data-failed={failed}
              aria-pressed={span.span_id === selectedId}
              tabIndex={span.span_id === selectedId || (selectedId === null && i === 0) ? 0 : -1}
              onClick={() => onSelect(span.span_id)}
              onKeyDown={(e) => onKeyDown(e, i)}
              onMouseMove={(e) => setHover({ id: span.span_id, x: e.clientX, y: e.currentTarget.getBoundingClientRect().top })}
              onMouseLeave={() => setHover(null)}
              onFocus={(e) => showAtBar(e, span.span_id)}
              onBlur={() => setHover(null)}
            >
              <span className="wf-label" style={{ paddingInlineStart: `${depth * 18}px` }}>
                <span className="wf-glyph" data-type={span.span_type}>
                  <Icon name={TYPE_ICON[span.span_type]} size={14} />
                </span>
                <span className="wf-name">{span.name}</span>
                {failed && (
                  <span className="wf-flag">
                    <Icon name="x" size={13} />
                    <span className="sr-only">failed</span>
                  </span>
                )}
              </span>
              <span className="wf-dur mono">{formatDuration(span.duration_ms)}</span>
              <span className="wf-track">
                <span
                  className="wf-bar"
                  data-type={span.span_type}
                  data-failed={failed}
                  style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                />
              </span>
            </button>
          );
        })}
      </div>

      {hovered && hover && (
        <div
          className="tip"
          role="tooltip"
          style={{ left: Math.min(hover.x + 14, window.innerWidth - 250), top: Math.max(hover.y - 8, 8) }}
        >
          <div className="tip-name">{hovered.name}</div>
          <div className="tip-row">
            <span>{TYPE_LABEL[hovered.span_type]}</span>
            <span>{hovered.status === "error" ? "Failed" : "No error"}</span>
          </div>
          <div className="tip-row mono">
            <span>{formatOffset(hovered.start_offset_ms)}</span>
            <span>{formatDuration(hovered.duration_ms)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function SpanTable({
  spans,
  selectedId,
  onSelect,
}: {
  spans: SpanRecord[];
  selectedId: string | null;
  onSelect: (spanId: string) => void;
}) {
  const rows = useMemo(() => buildRows(spans), [spans]);
  const total = traceDurationMs(spans);
  return (
    <div className="table-scroll">
      <table className="spans">
        <caption className="sr-only">Spans of this run, in trace order</caption>
        <thead>
          <tr>
            <th scope="col">Span</th>
            <th scope="col">Type</th>
            <th scope="col">Status</th>
            <th scope="col" className="num">
              Starts at
            </th>
            <th scope="col" className="num">
              Duration
            </th>
            <th scope="col" className="num">
              Share of run
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ span, depth }) => (
            <tr key={span.span_id} data-selected={span.span_id === selectedId} data-failed={span.status === "error"}>
              <td style={{ paddingInlineStart: `${12 + depth * 18}px` }}>
                <button type="button" className="link-btn" onClick={() => onSelect(span.span_id)} aria-pressed={span.span_id === selectedId}>
                  {span.name}
                </button>
              </td>
              <td>{TYPE_LABEL[span.span_type]}</td>
              <td>{span.status === "error" ? "Failed" : "No error"}</td>
              <td className="num mono">{formatOffset(span.start_offset_ms)}</td>
              <td className="num mono">{formatDuration(span.duration_ms)}</td>
              <td className="num mono">{total > 0 ? `${Math.min(100, (span.duration_ms / total) * 100).toFixed(span.duration_ms / total < 0.1 ? 1 : 0)}%` : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
