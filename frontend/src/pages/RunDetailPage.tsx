import { useEffect, useMemo, useState } from "react";
import { ApiError, ApiUnreachableError } from "../api/client";
import { useDataSource } from "../api/context";
import type { RunEvaluation, RunFault, RunRecord, SpanRecord } from "../api/types";
import { ApiDown } from "../components/ApiDown";
import { CopyButton } from "../components/CopyButton";
import { VariantChip } from "../components/VariantChip";
import { EvaluationCard } from "../components/EvaluationCard";
import { PlainRun } from "../components/PlainRun";
import { plainReason } from "../content/plain";
import { Technical } from "../components/Plain";
import { Icon } from "../components/Icon";
import { RedactedText } from "../components/RedactedText";
import { SpanInspector } from "../components/SpanInspector";
import { RunStatusPill } from "../components/StatusPill";
import { Legend, SpanTable, Waterfall } from "../components/Waterfall";
import { useQuery } from "../hooks/useQuery";
import { clockTime, splitModel } from "../lib/format";
import { plainWords } from "../lib/plain";
import { buildRows } from "../lib/spanTree";
import { formatDuration } from "../lib/timeScale";

/**
 * Open on the span you most likely came to see: the span a failed gating check points at, else a failed
 * check's span, else the innermost failed span, else the whole run.
 */
export function defaultSelection(spans: SpanRecord[], evaluation?: RunEvaluation): string | null {
  const ids = new Set(spans.map((s) => s.span_id));
  const failedChecks = (evaluation?.checks ?? []).filter((c) => c.passed === false);
  const pointed = [...failedChecks.filter((c) => c.gating), ...failedChecks.filter((c) => !c.gating)]
    .flatMap((c) => c.span_ids)
    .find((id) => ids.has(id));
  if (pointed) return pointed;

  const rows = buildRows(spans);
  const failedLeaf = rows.find((r) => r.span.status === "error" && r.childCount === 0);
  return (failedLeaf ?? rows.find((r) => r.span.status === "error") ?? rows[0])?.span.span_id ?? null;
}

function Elapsed({ since }: { since: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, []);
  return <>{formatDuration(Math.max(0, now - new Date(since).getTime()))}</>;
}

function Outcome({ run }: { run: RunRecord }) {
  if (run.status === "running")
    return (
      <section className="card outcome" data-status="running" role="status">
        <Icon name="spinner" size={16} className="spin" />
        <div>
          <strong>Recording this run…</strong>
          <p>
            <Elapsed since={run.started_at} /> so far. The trace appears here when the run finishes.
          </p>
        </div>
      </section>
    );
  if (run.status === "error")
    return (
      <section className="card outcome" data-status="error" role="alert">
        <Icon name="x" size={16} />
        <div>
          <strong>Run failed</strong>
          <p>
            <RedactedText text={run.error ? (plainWords() ? plainReason(run.error) : run.error) : "No error message was recorded."} />
          </p>
        </div>
      </section>
    );
  return (
    <section className="card outcome" data-status="ok">
      <Icon name="check" size={16} />
      <div>
        <strong>Final answer</strong>
        <p>
          <RedactedText text={run.final_answer ?? "The agent finished without a text answer."} />
        </p>
      </div>
    </section>
  );
}

function Trace({ run, spans, evaluation, faults = [] }: { run: RunRecord; spans: SpanRecord[]; evaluation?: RunEvaluation; faults?: RunFault[] }) {
  const plain = plainWords();
  const [selectedId, setSelectedId] = useState<string | null>(() => defaultSelection(spans, evaluation));
  const [view, setView] = useState<"waterfall" | "table">("waterfall");
  const selected = useMemo(() => spans.find((s) => s.span_id === selectedId) ?? null, [spans, selectedId]);
  const failed = spans.filter((s) => s.status === "error").length;
  const planted = faults.filter((f) => f.origin_span_id);
  const plantedIds = useMemo(() => new Set(planted.map((f) => f.origin_span_id as string)), [planted]);
  const findings = useMemo(
    () => (evaluation?.checks ?? []).filter((c) => c.passed === false && selectedId !== null && c.span_ids.includes(selectedId)),
    [evaluation, selectedId],
  );

  return (
    <>
      {faults.length > 0 && (
        <section className="card planted" aria-label="Planted fault">
          <Icon name="alert" size={16} />
          <div>
            <strong>{plain ? "Failure lab: a problem was planted in this run" : "Failure lab: a fault was planted in this run"}</strong>
            <ul>
              {faults.map((f) => (
                <li key={f.description}>
                  <span className="mono">{f.description}</span>
                  {f.origin_span_id ? (
                    !plain && (
                      <button type="button" className="chip" onClick={() => setSelectedId(f.origin_span_id)}>
                        Show the planted span
                      </button>
                    )
                  ) : (
                    <span className="muted small"> (it never fired)</span>
                  )}
                </li>
              ))}
            </ul>
            <p className="muted small">
              {plain ? "This is recorded separately, so the analysis is not told about it." : "This is recorded outside the trace, so trace analysis is not told about it."}
            </p>
          </div>
        </section>
      )}
      {plain && <PlainRun run={run} spans={spans} evaluation={evaluation} />}
      <Technical title="Show technical details: the checks and the full trace">
      {evaluation && <EvaluationCard evaluation={evaluation} onShowSpan={setSelectedId} />}
      <div className="trace-layout">
      <section className="card trace" aria-labelledby="trace-title">
        <div className="trace-head">
          <div>
            <h2 id="trace-title" className="card-title">
              Trace
            </h2>
            <p className="muted small">
              {spans.length} spans{failed > 0 ? `, ${failed} failed` : ""}. Select a span to inspect it.
            </p>
          </div>
          <div className="seg seg-text" role="radiogroup" aria-label="Trace view">
            <button type="button" role="radio" aria-checked={view === "waterfall"} className="seg-btn" onClick={() => setView("waterfall")}>
              Waterfall
            </button>
            <button type="button" role="radio" aria-checked={view === "table"} className="seg-btn" onClick={() => setView("table")}>
              Table
            </button>
          </div>
        </div>
        {view === "waterfall" ? (
          <>
            <Legend />
            <Waterfall spans={spans} selectedId={selectedId} onSelect={setSelectedId} plantedIds={plantedIds} />
          </>
        ) : (
          <SpanTable spans={spans} selectedId={selectedId} onSelect={setSelectedId} />
        )}
      </section>
      <SpanInspector span={selected} spans={spans} onSelect={setSelectedId} findings={findings} />
      </div>
      </Technical>
    </>
  );
}

/** Mounts only once a run has finished, so it can never show data left over from "not loaded yet". */
function TraceSection({ run, runId }: { run: RunRecord; runId: string }) {
  const source = useDataSource();
  const spans = useQuery(() => source.getSpans(runId), [source, runId]);
  // The evaluation is a bonus: if it cannot be loaded the trace is still shown without it.
  const evaluation = useQuery(() => source.getRunEvaluation(runId), [source, runId]);
  const faults = useQuery(() => source.getRunFaults(runId), [source, runId]);

  if ((spans.loading && !spans.data) || (evaluation.loading && !evaluation.data && !evaluation.error))
    return (
      <p className="muted" role="status">
        Loading trace…
      </p>
    );
  if (spans.error && !spans.data)
    return (
      <p className="form-error" role="alert">
        Could not load the trace: {spans.error.message}
      </p>
    );
  if (!spans.data || spans.data.length === 0)
    return (
      <section className="card empty">
        <h2 className="card-title">No spans recorded</h2>
        <p>This run has no trace data, so there is nothing to inspect.</p>
      </section>
    );
  return <Trace run={run} spans={spans.data} evaluation={evaluation.data} faults={faults.data} />;
}

export function RunDetailPage({ runId }: { runId: string }) {
  const source = useDataSource();
  const run = useQuery(() => source.getRun(runId), [source, runId], {
    refetchMs: (r) => (r?.status === "running" ? 1500 : false),
  });
  const notFound = run.error instanceof ApiError && run.error.status === 404;
  const unreachable = run.error instanceof ApiUnreachableError && !run.data;
  const model = run.data ? splitModel(run.data.model) : null;
  const traceUrl = run.data?.trace_id ? source.traceUrl(run.data.trace_id) : null;

  return (
    <>
      <a className="back" href="#/runs">
        <Icon name="back" size={15} /> All runs
      </a>

      {unreachable ? (
        <ApiDown onRetry={run.refetch} />
      ) : notFound ? (
        <section className="card empty">
          <h2 className="card-title">Run not found</h2>
          <p>
            There is no run called <span className="mono">{runId}</span>. It may have been deleted, or the link is wrong.
          </p>
        </section>
      ) : !run.data ? (
        <p className="muted" role="status">
          {run.error ? `Could not load this run: ${run.error.message}` : "Loading run…"}
        </p>
      ) : (
        <>
          <header className="run-head">
            <div className="run-title">
              <RunStatusPill status={run.data.status} />
              <h1>{run.data.task}</h1>
            </div>
            <dl className="facts-row">
              <div>
                <dt>Run</dt>
                <dd>
                  <span className="mono">{run.data.run_id}</span> <CopyButton text={run.data.run_id} label="Copy run id" />
                </dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>
                  {model?.name}
                  {model?.provider && <span className="muted"> · {model.provider}</span>}
                </dd>
              </div>
              {run.data.variant !== "baseline" && (
                <div>
                  <dt>Agent</dt>
                  <dd>
                    <VariantChip variant={run.data.variant} />
                  </dd>
                </div>
              )}
              <div>
                <dt>Duration</dt>
                <dd className="mono">{run.data.duration_ms == null ? "–" : formatDuration(run.data.duration_ms)}</dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd title={new Date(run.data.started_at).toLocaleString()}>{clockTime(run.data.started_at)}</dd>
              </div>
              {run.data.trace_id && !plainWords() && (
                <div>
                  <dt>Trace</dt>
                  <dd>
                    <span className="mono">{run.data.trace_id.slice(0, 12)}…</span> <CopyButton text={run.data.trace_id} label="Copy trace id" />
                    {traceUrl && (
                      <a className="ext" href={traceUrl} target="_blank" rel="noreferrer">
                        Jaeger <Icon name="external" size={12} />
                      </a>
                    )}
                  </dd>
                </div>
              )}
            </dl>
          </header>

          <Outcome run={run.data} />

          {run.data.status !== "running" && <TraceSection key={run.data.status} run={run.data} runId={runId} />}
        </>
      )}
    </>
  );
}
