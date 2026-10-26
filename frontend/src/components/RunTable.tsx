import { useMemo, useState } from "react";
import type { RunRecord, RunStatus } from "../api/types";
import { formatDuration } from "../lib/timeScale";
import { median, splitModel, timeAgo } from "../lib/format";
import { plainWords } from "../lib/plain";
import { runHref } from "../hooks/useHashRoute";
import { RunStatusPill } from "./StatusPill";
import { Icon } from "./Icon";

type Filter = "all" | RunStatus;

export function StatStrip({ runs }: { runs: RunRecord[] }) {
  const ok = runs.filter((r) => r.status === "ok").length;
  const failed = runs.filter((r) => r.status === "error").length;
  const running = runs.filter((r) => r.status === "running").length;
  const med = median(runs.filter((r) => r.duration_ms != null).map((r) => r.duration_ms as number));
  return (
    <dl className="stats" aria-label="Run summary">
      <div className="stat">
        <dt>Runs</dt>
        <dd>{runs.length}</dd>
      </div>
      <div className="stat">
        <dt>Completed</dt>
        <dd>{ok}</dd>
      </div>
      <div className="stat" data-alert={failed > 0}>
        <dt>Failed</dt>
        <dd>
          {failed > 0 && <Icon name="x" size={16} />}
          {failed}
        </dd>
      </div>
      {running > 0 && (
        <div className="stat">
          <dt>Running</dt>
          <dd>{running}</dd>
        </div>
      )}
      <div className="stat">
        <dt>Median duration</dt>
        <dd>{med == null ? "–" : formatDuration(med)}</dd>
      </div>
    </dl>
  );
}

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "ok", label: "Completed" },
  { value: "error", label: "Failed" },
  { value: "running", label: "Running" },
];

export function RunTable({ runs }: { runs: RunRecord[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const shown = useMemo(() => (filter === "all" ? runs : runs.filter((r) => r.status === filter)), [runs, filter]);
  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: runs.length, ok: 0, error: 0, running: 0 };
    for (const r of runs) c[r.status] += 1;
    return c;
  }, [runs]);

  return (
    <section className="card table-card" aria-labelledby="runs-title">
      <div className="table-head">
        <h2 id="runs-title" className="card-title">
          All runs
        </h2>
        <div className="seg seg-text" role="radiogroup" aria-label="Filter runs by status">
          {FILTERS.map((f) => (
            <button key={f.value} type="button" role="radio" aria-checked={filter === f.value} className="seg-btn" onClick={() => setFilter(f.value)}>
              {f.label}
              <span className="count">{counts[f.value]}</span>
            </button>
          ))}
        </div>
      </div>

      {shown.length === 0 ? (
        <p className="empty-inline">No {filter === "all" ? "" : FILTERS.find((f) => f.value === filter)?.label.toLowerCase() + " "}runs.</p>
      ) : (
        <div className="table-scroll">
          <table className="runs">
            <thead>
              <tr>
                <th scope="col">Status</th>
                <th scope="col">Task</th>
                <th scope="col">Model</th>
                <th scope="col" className="num">
                  Duration
                </th>
                <th scope="col" className="num">
                  Started
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((run) => {
                const model = splitModel(run.model);
                return (
                  <tr key={run.run_id} data-status={run.status}>
                    <td>
                      <RunStatusPill status={run.status} />
                    </td>
                    <td className="task-cell">
                      <a className="row-link" href={runHref(run.run_id)}>
                        {run.task}
                      </a>
                      <span className="mono muted small">{run.run_id}</span>
                    </td>
                    <td>
                      {plainWords() && model.provider === "scripted" ? (
                        <span className="model-name">Scripted example</span>
                      ) : (
                        <>
                          <span className="model-name">{model.name}</span>
                          {model.provider && <span className="muted small"> {model.provider}</span>}
                        </>
                      )}
                    </td>
                    <td className="num mono">{run.duration_ms == null ? "–" : formatDuration(run.duration_ms)}</td>
                    <td className="num muted" title={new Date(run.started_at).toLocaleString()}>
                      {timeAgo(run.started_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
