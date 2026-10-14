import type { EvalReport, FaultLabNote, LabRunSummary } from "../api/types";
import { runHref } from "../hooks/useHashRoute";
import { EFFECT_LABEL, EFFECT_TEXT, labNote, verdictText } from "../lib/notes";
import { kindNote, metricLabel } from "../lib/metrics";
import { formatDuration } from "../lib/timeScale";
import { Icon } from "./Icon";

const runLabel = (r: LabRunSummary) => (r.run_status === "error" ? "Failed" : "Completed");

function Compare({ note }: { note: FaultLabNote }) {
  const rows: [string, string, string][] = [
    ["Run", runLabel(note.control), runLabel(note.faulted)],
    ["Gating checks", note.control.gating_passed ? "Passed" : "Failed", note.faulted.gating_passed ? "Passed" : "Failed"],
    ["Tool calls", String(note.control.tool_calls), String(note.faulted.tool_calls)],
    [
      "Time",
      note.control.duration_ms == null ? "–" : formatDuration(note.control.duration_ms),
      note.faulted.duration_ms == null ? "–" : formatDuration(note.faulted.duration_ms),
    ],
    [
      "Checks that failed",
      note.control.failed_checks.map(metricLabel).join(", ") || "none",
      note.faulted.failed_checks.map(metricLabel).join(", ") || "none",
    ],
  ];
  return (
    <table className="lab-compare">
      <caption className="sr-only">Control run against the run with the fault</caption>
      <thead>
        <tr>
          <th scope="col" />
          <th scope="col">Control</th>
          <th scope="col">With the fault</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, a, b]) => (
          <tr key={label} data-changed={a !== b}>
            <th scope="row">{label}</th>
            <td>{a}</td>
            <td>{b}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FaultCard({ title, note, runId }: { title: string; note: FaultLabNote; runId: string }) {
  return (
    <article className="card lab-card" aria-label={title}>
      <header className="lab-head">
        <div>
          <h3>{title}</h3>
          <p className="mono muted small">Planted: {note.injected}</p>
        </div>
        <span className="pill" data-status={note.effect === "no_effect" ? "ok" : note.effect === "silent" ? "warn" : "error"}>
          {EFFECT_LABEL[note.effect]}
        </span>
      </header>
      <p className="lab-desc">{note.description}</p>

      <div className="lab-grid">
        <section aria-label={`Effect of ${title}`}>
          <h4>What it did to the run</h4>
          <Compare note={note} />
          <p className="lab-effect">{EFFECT_TEXT[note.effect]}</p>
        </section>

        <section aria-label={`Where analysis points for ${title}`}>
          <h4>Where trace analysis says to look</h4>
          {note.suspects.length === 0 ? (
            <p className="muted">No span stood out.</p>
          ) : (
            <ol className="suspects">
              {note.suspects.map((s) => (
                <li key={s.span_id} data-planted={s.span_id === note.origin_span_id}>
                  <span className="mono">{s.span_name}</span>
                  <span className="muted small"> · {s.source}</span>
                  {s.span_id === note.origin_span_id && <span className="planted-badge">planted here</span>}
                  <span className="suspect-reason">{s.reason}</span>
                </li>
              ))}
            </ol>
          )}
          <p className="lab-verdict" data-hit={note.hit_at_1}>
            <Icon name={note.hit_at_1 ? "check" : "x"} size={14} />
            {verdictText(note)}
          </p>
        </section>
      </div>

      <footer className="lab-links">
        <a className="ext" href={runHref(runId)}>
          Open the run with the fault
        </a>
        <a className="ext" href={runHref(note.control.run_id)}>
          Open the control run
        </a>
      </footer>
    </article>
  );
}

export function FaultLabReport({ report }: { report: EvalReport }) {
  const entries = report.cases.flatMap((c) => {
    const note = labNote(c);
    return note ? [{ c, note }] : [];
  });
  return (
    <>
      <section className="card headline" aria-label="Result">
        <div className="hero">
          <span className="hero-num">
            {report.n_passed}
            <span className="hero-of"> of {report.n_cases}</span>
          </span>
          <span className="hero-label">faults located at the right span</span>
        </div>
        <p className="kind-note">{kindNote(report)}</p>
      </section>
      {entries.map(({ c, note }) => (
        <FaultCard key={c.case_id} title={note.title} note={note} runId={c.run_id} />
      ))}
    </>
  );
}
