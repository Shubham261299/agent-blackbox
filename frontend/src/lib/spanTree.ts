import type { SpanRecord } from "../api/types";

export interface TreeRow {
  span: SpanRecord;
  depth: number;
  childCount: number;
}

/**
 * Flatten spans into depth-first display order (parents before children, siblings by start time).
 * A span whose parent is missing from the list is shown as a root instead of being dropped, so a
 * partial trace is still inspectable.
 */
export function buildRows(spans: SpanRecord[]): TreeRow[] {
  const ids = new Set(spans.map((s) => s.span_id));
  const children = new Map<string | null, SpanRecord[]>();
  for (const span of spans) {
    const parent = span.parent_span_id && ids.has(span.parent_span_id) ? span.parent_span_id : null;
    const siblings = children.get(parent) ?? [];
    siblings.push(span);
    children.set(parent, siblings);
  }
  const byStart = (a: SpanRecord, b: SpanRecord) =>
    a.start_offset_ms - b.start_offset_ms || a.duration_ms - b.duration_ms;

  const rows: TreeRow[] = [];
  const visit = (span: SpanRecord, depth: number) => {
    const kids = (children.get(span.span_id) ?? []).slice().sort(byStart);
    rows.push({ span, depth, childCount: kids.length });
    for (const kid of kids) visit(kid, depth + 1);
  };
  for (const root of (children.get(null) ?? []).slice().sort(byStart)) visit(root, 0);
  return rows;
}

/** Total time covered by the trace: the furthest end of any span. */
export function traceDurationMs(spans: SpanRecord[]): number {
  return spans.reduce((max, s) => Math.max(max, s.start_offset_ms + s.duration_ms), 0);
}
