import type { RunEvaluation, RunRecord, SpanRecord } from "../api/types";
import { plainReason, runStory, stepTime } from "../content/plain";
import { metricLabel } from "../lib/metrics";
import { Icon } from "./Icon";
import { PlainLead } from "./Plain";

const answer = (v: boolean | null) => (v === null ? null : v ? "Yes" : "No");

/** A run as a short story: what the agent did in order, whether it finished the job and kept to the rules, and where to look. */
export function PlainRun({ run, spans, evaluation }: { run: Pick<RunRecord, "status">; spans: SpanRecord[]; evaluation?: RunEvaluation }) {
  const story = runStory(run, spans, evaluation);
  const verdicts: [string, boolean | null][] = [
    [metricLabel("task_completion"), story.finished],
    [metricLabel("policy_compliance"), story.rules],
  ];
  return (
    <>
      <PlainLead>{story.sentence}</PlainLead>
      <section className="card plain-run" aria-labelledby="plain-run-title">
        <h2 id="plain-run-title" className="card-title">
          What the agent did, step by step
        </h2>
        <ol className="steps" aria-label="Steps">
          {story.steps.map((s) => (
            <li key={s.spanId} className="step" data-failed={s.failed}>
              <span className="step-n" aria-hidden="true">
                {s.failed ? <Icon name="x" size={13} /> : s.n}
              </span>
              <div>
                <p className="step-text">
                  {s.text}
                  <span className="step-time">{stepTime(s.ms)}</span>
                  {s.retries > 0 && <span className="step-note">tried again {s.retries === 1 ? "once" : `${s.retries} times`}</span>}
                </p>
                {s.failed && (
                  <p className="step-failed">
                    <strong>This step failed.</strong> {s.detail && <span className="muted">It reported: {plainReason(s.detail)}</span>}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
        {verdicts.some(([, v]) => v !== null) && (
          <ul className="verdicts" aria-label="What the checks said">
            {verdicts.map(([label, v]) =>
              v === null ? null : (
                <li key={label} data-pass={v}>
                  <Icon name={v ? "check" : "x"} size={14} />
                  {label}: <strong>{answer(v)}</strong>
                </li>
              ),
            )}
          </ul>
        )}
        {story.where && (
          <p className="look-first">
            <strong>Where to look first:</strong> {story.where}
          </p>
        )}
      </section>
    </>
  );
}
