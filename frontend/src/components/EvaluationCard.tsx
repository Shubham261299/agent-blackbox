import type { CheckResult, RunEvaluation } from "../api/types";
import { evalHref } from "../hooks/useHashRoute";
import { metricLabel } from "../lib/metrics";
import { Icon } from "./Icon";

function Row({ check, onShowSpan }: { check: CheckResult; onShowSpan: (spanId: string) => void }) {
  const state = check.passed === null ? "info" : check.passed ? "pass" : "fail";
  return (
    <li className="eval-row" data-state={state}>
      <span className="eval-mark" aria-hidden="true">
        {state === "pass" && <Icon name="check" size={15} />}
        {state === "fail" && <Icon name="x" size={15} />}
        {state === "info" && <span className="dot" />}
      </span>
      <div className="eval-body">
        <div className="eval-line">
          <strong>{metricLabel(check.metric)}</strong>
          <span className="sr-only">{state === "pass" ? " passed" : state === "fail" ? " failed" : " informational"}</span>
          {check.gating && <span className="gate">gates the run</span>}
          {check.score !== null && check.passed === false && <span className="muted small">score {check.score.toFixed(2)}</span>}
        </div>
        <p className="eval-reason">{check.reason}</p>
        {check.passed === false && check.span_ids.length > 0 && (
          <div className="eval-spans">
            {check.span_ids.slice(0, 4).map((id, i) => (
              <button key={id} type="button" className="chip" onClick={() => onShowSpan(id)}>
                Show span{check.span_ids.length > 1 ? ` ${i + 1}` : ""}
              </button>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

/** The checks for one run, next to the trace they were computed from. */
export function EvaluationCard({
  evaluation,
  onShowSpan,
}: {
  evaluation: RunEvaluation;
  onShowSpan: (spanId: string) => void;
}) {
  const failed = evaluation.checks.filter((c) => c.passed === false);
  const gatingFailed = failed.filter((c) => c.gating).length;
  const top = evaluation.suspects[0];
  return (
    <section className="card evaluation" aria-labelledby="evaluation-title">
      <div className="trace-head">
        <div>
          <h2 id="evaluation-title" className="card-title">
            Evaluation
          </h2>
          <p className="muted small">
            {evaluation.stored && evaluation.eval_id ? (
              <>
                Case <span className="mono">{evaluation.case_id}</span> in <a href={evalHref(evaluation.eval_id)}>{evaluation.eval_id}</a>.{" "}
              </>
            ) : (
              "This run is not part of an evaluation, so only the checks that need no expectations are shown. "
            )}
            {failed.length === 0 ? "Nothing failed." : `${failed.length} failed${gatingFailed ? `, ${gatingFailed} of them gating` : ""}.`}
          </p>
        </div>
      </div>
      {top && (
        <p className="look-first">
          <strong>Where to look first:</strong>{" "}
          <button type="button" className="chip" onClick={() => onShowSpan(top.span_id)}>
            {top.span_name}
          </button>
          <span className="muted small">
            {" "}
            {top.source}: {top.reason}
            {evaluation.suspects.length > 1 ? ` (and ${evaluation.suspects.length - 1} more)` : ""}
          </span>
        </p>
      )}
      <ul className="eval-list">
        {[...evaluation.checks]
          .sort((a, b) => Number(a.passed !== false) - Number(b.passed !== false))
          .map((c) => (
            <Row key={c.metric} check={c} onShowSpan={onShowSpan} />
          ))}
      </ul>
    </section>
  );
}
