import { useMemo, useState } from "react";
import { ApiError, ApiUnreachableError } from "../api/client";
import { useDataSource } from "../api/context";
import type { EvalCaseResult, EvalReport } from "../api/types";
import { ApiDown } from "../components/ApiDown";
import { FaultLabReport } from "../components/FaultLabReport";
import { Icon } from "../components/Icon";
import { RateBar } from "../components/RateBar";
import { VariantChip } from "../components/VariantChip";
import { compareHref, runHref } from "../hooks/useHashRoute";
import { comparableWith, variantLabel } from "../lib/compare";
import { useQuery } from "../hooks/useQuery";
import { median } from "../lib/format";
import { validationNote } from "../lib/notes";
import { PlainLead, Technical } from "../components/Plain";
import { evalLead, plainModel } from "../content/plain";
import { JUDGED_METRICS, kindLabel, kindNote, metricLabel, metricWhat } from "../lib/metrics";
import { plainWords } from "../lib/plain";
import { formatDuration } from "../lib/timeScale";

function Cell({ metric, c }: { metric: string; c: EvalCaseResult }) {
  const check = c.checks.find((x) => x.metric === metric);
  if (!check || check.passed === null) return <td className="cell">–</td>;
  return (
    <td className="cell" data-pass={check.passed} title={check.reason}>
      <Icon name={check.passed ? "check" : "x"} size={15} />
      <span className="sr-only">{check.passed ? "passed" : `failed: ${check.reason}`}</span>
    </td>
  );
}

function Matrix({ report }: { report: EvalReport }) {
  const [only, setOnly] = useState<"all" | "failing">("all");
  const validation = report.kind === "validation";
  const rows = useMemo(() => {
    // failed a gating check, then failed only a reported check, then clean (stable within each group)
    const rank = (c: EvalCaseResult) => (!c.passed ? 0 : c.checks.some((x) => x.passed === false) ? 1 : 2);
    const ordered = [...report.cases].sort((a, b) => rank(a) - rank(b));
    return only === "failing" ? ordered.filter((c) => !c.passed) : ordered;
  }, [report.cases, only]);
  const failing = report.cases.filter((c) => !c.passed).length;

  return (
    <section className="card table-card" aria-labelledby="matrix-title">
      <div className="table-head">
        <div>
          <h2 id="matrix-title" className="card-title">
            {validation ? "Faults and the checks that caught them" : "Every case, every check"}
          </h2>
          <p className="muted small">{validation ? "A cross means that check flagged the fault." : "A cross means that check failed for that case. Cases that failed a gating check come first, then cases with a failed reported check."}</p>
        </div>
        <div className="seg seg-text" role="radiogroup" aria-label="Which cases to show">
          <button type="button" role="radio" aria-checked={only === "all"} className="seg-btn" onClick={() => setOnly("all")}>
            All<span className="count">{report.cases.length}</span>
          </button>
          <button type="button" role="radio" aria-checked={only === "failing"} className="seg-btn" onClick={() => setOnly("failing")}>
            {validation ? "Not as expected" : "Failing"}
            <span className="count">{failing}</span>
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="empty-inline">Nothing to show here.</p>
      ) : (
        <div className="table-scroll">
          <table className="matrix">
            <caption className="sr-only">Results per case and check</caption>
            <thead>
              <tr>
                <th scope="col">{validation ? "Fault" : "Case"}</th>
                {JUDGED_METRICS.map((m) => (
                  <th key={m} scope="col" className="cell" title={metricWhat(m)}>
                    {metricLabel(m).replace(" ", " ")}
                    {m === "task_completion" || m === "policy_compliance" ? <span className="gate">gates</span> : null}
                  </th>
                ))}
                <th scope="col" className="num">
                  Run
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.case_id} data-passed={c.passed}>
                  <td className="case-cell">
                    <span className="case-id">
                      <span className="mono">{c.case_id}</span>
                      <span className="muted small">{c.category.replace("_", " ")}</span>
                    </span>
                    <span className="case-task">{validation ? (validationNote(c)?.description ?? c.task) : c.task}</span>
                    {validation && validationNote(c) && (
                      <span className="small muted">
                        Expected to trip:{" "}
                        {validationNote(c)?.expected_fail?.length ? validationNote(c)?.expected_fail?.map(metricLabel).join(", ") : "nothing"}.{" "}
                        {validationNote(c)?.matched
                          ? "Detected exactly that."
                          : `Detected: ${validationNote(c)?.actual_fail?.map(metricLabel).join(", ") || "nothing"}.`}
                      </span>
                    )}
                  </td>
                  {JUDGED_METRICS.map((m) => (
                    <Cell key={m} metric={m} c={c} />
                  ))}
                  <td className="num">
                    <a className="ext" href={runHref(c.run_id)}>
                      Open
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** For a validation batch: per check, how many of the faults it was meant to catch did it catch, and did it raise any false alarm? */
export function detectionRows(cases: EvalCaseResult[]) {
  return JUDGED_METRICS.map((metric) => {
    const expected = cases.filter((c) => validationNote(c)?.expected_fail?.includes(metric));
    const caught = expected.filter((c) => validationNote(c)?.actual_fail?.includes(metric));
    const falseAlarms = cases.filter((c) => validationNote(c)?.actual_fail?.includes(metric) && !validationNote(c)?.expected_fail?.includes(metric));
    return { metric, expected: expected.length, caught: caught.length, falseAlarms: falseAlarms.length };
  });
}

function DetectionTable({ report }: { report: EvalReport }) {
  const rows = detectionRows(report.cases);
  return (
    <section className="card table-card" aria-labelledby="detect-title">
      <div className="table-head">
        <div>
          <h2 id="detect-title" className="card-title">
            By check: did it catch its faults?
          </h2>
          <p className="muted small">Caught = faults this check was meant to flag. A false alarm is a flag on a fault it was not meant to flag.</p>
        </div>
      </div>
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">Check</th>
            <th scope="col">Caught</th>
            <th scope="col" className="num">
              False alarms
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.metric}>
              <td>
                <span className="metric-name" title={metricWhat(r.metric)}>
                  {metricLabel(r.metric)}
                </span>
              </td>
              <td>
                <RateBar passed={r.caught} total={r.expected} label={`${metricLabel(r.metric)} caught`} />
              </td>
              <td className="num" data-alarm={r.falseAlarms > 0}>
                {r.falseAlarms}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Summary({ report }: { report: EvalReport }) {
  const validation = report.kind === "validation";
  const durations = report.cases.map((c) => c.duration_ms).filter((d): d is number => d != null);
  const med = median(durations);
  const slowest = durations.length ? Math.max(...durations) : null;
  return (
    <>
      <section className="card headline" aria-label="Result">
        <div className="hero">
          <span className="hero-num">
            {report.n_passed}
            <span className="hero-of"> of {report.n_cases}</span>
          </span>
          <span className="hero-label">
            {validation
              ? plainWords() ? "problems caught exactly as expected" : "faults caught exactly as expected"
              : plainWords() ? "test cases passed: the agent finished the job and followed the rules" : "runs passed both gating checks"}
          </span>
        </div>
        <p className="kind-note">{kindNote(report)}</p>
      </section>

      <Technical title="Show technical details: results by check and by kind of task">
      <div className="two-up">
        {validation ? (
          <DetectionTable report={report} />
        ) : (
        <section className="card table-card" aria-labelledby="metrics-title">
          <div className="table-head">
            <h2 id="metrics-title" className="card-title">
              By check
            </h2>
          </div>
          <table className="plain">
            <thead>
              <tr>
                <th scope="col">Check</th>
                <th scope="col">Passed</th>
              </tr>
            </thead>
            <tbody>
              {report.metrics
                .filter((m) => m.metric !== "latency")
                .map((m) => (
                  <tr key={m.metric}>
                    <td>
                      <span className="metric-name" title={metricWhat(m.metric)}>
                        {metricLabel(m.metric)}
                      </span>
                      {m.gating && <span className="gate">gates the run</span>}
                    </td>
                    <td>
                      <RateBar passed={m.passed} total={m.total} label={metricLabel(m.metric)} />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          {med != null && slowest != null && (
            <p className="foot muted small">
              Run time: median {formatDuration(med)}, slowest {formatDuration(slowest)}.
            </p>
          )}
        </section>
        )}

        {!validation && (
          <section className="card table-card" aria-labelledby="cat-title">
            <div className="table-head">
              <h2 id="cat-title" className="card-title">
                By kind of task
              </h2>
            </div>
            <table className="plain">
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col">Passed</th>
                </tr>
              </thead>
              <tbody>
                {report.categories.map((c) => (
                  <tr key={c.category}>
                    <td>{c.category.replace("_", " ")}</td>
                    <td>
                      <RateBar passed={c.passed} total={c.total} label={c.category} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </div>
      </Technical>
    </>
  );
}

/** Offers only evaluations the API would accept (same model, dataset content and kind), newest first. */
function ComparePicker({ report }: { report: EvalReport }) {
  const source = useDataSource();
  const all = useQuery(() => source.listEvals(), [source]);
  const options = comparableWith(report, all.data ?? []);
  const [chosen, setChosen] = useState("");
  const pick = options.some((o) => o.eval_id === chosen) ? chosen : (options[0]?.eval_id ?? "");
  if (report.status !== "done" || report.kind === "validation" || !all.data) return null;
  if (options.length === 0) {
    return (
      <p className="muted small compare-none">
        Nothing to compare this with yet: a comparison needs another finished evaluation of the same kind, on the same model and dataset content.
      </p>
    );
  }
  return (
    <form
      className="compare-picker"
      onSubmit={(e) => {
        e.preventDefault();
        window.location.hash = compareHref(report.eval_id, pick);
      }}
    >
      <label htmlFor="compare-with">Compare this evaluation (as the “before”) with</label>
      <select id="compare-with" value={pick} onChange={(e) => setChosen(e.target.value)}>
        {options.map((o) => (
          <option key={o.eval_id} value={o.eval_id}>
            {variantLabel(o.variant)} · {o.n_passed}/{o.n_cases} · {o.eval_id}
          </option>
        ))}
      </select>
      <button type="submit" className="btn">
        Compare
      </button>
    </form>
  );
}

export function EvalReportPage({ evalId }: { evalId: string }) {
  const source = useDataSource();
  const report = useQuery(() => source.getEval(evalId), [source, evalId], {
    refetchMs: (r) => (r?.status === "running" ? 1500 : false),
  });

  const notFound = report.error instanceof ApiError && report.error.status === 404;
  const data = report.data;

  return (
    <>
      <a className="back" href="#/evals">
        <Icon name="back" size={15} /> {plainWords() ? "All results" : "All evaluations"}
      </a>

      {report.error instanceof ApiUnreachableError && !data ? (
        <ApiDown onRetry={report.refetch} />
      ) : notFound ? (
        <section className="card empty">
          <h2 className="card-title">Evaluation not found</h2>
          <p>
            There is no evaluation called <span className="mono">{evalId}</span>.
          </p>
        </section>
      ) : !data ? (
        <p className="muted" role="status">
          {report.error ? `Could not load this evaluation: ${report.error.message}` : "Loading evaluation…"}
        </p>
      ) : (
        <>
          <header className="run-head">
            <div className="run-title">
              <span className="pill" data-status={data.status === "running" ? "running" : data.status === "error" ? "error" : "neutral"}>
                {data.status === "running" && <Icon name="spinner" size={13} className="spin" />}
                {kindLabel(data.kind)}
                {data.status === "running" ? " · running" : data.status === "error" ? " · failed" : ""}
              </span>
              <h1>{plainWords() ? plainModel(data.model) : data.model}</h1>
              <VariantChip variant={data.variant} rescoredFrom={data.rescored_from} />
            </div>
            <dl className="facts-row">
              {!plainWords() && (
                <div>
                  <dt>Dataset</dt>
                  <dd>
                    <span className="mono">
                      {data.dataset_version} · {data.dataset_hash}
                    </span>
                  </dd>
                </div>
              )}
              <div>
                <dt>{plainWords() ? "Test cases" : "Cases"}</dt>
                <dd>{data.n_cases}</dd>
              </div>
              {data.seed != null && !plainWords() && (
                <div>
                  <dt>Seed</dt>
                  <dd>{data.seed}</dd>
                </div>
              )}
              <div>
                <dt>Started</dt>
                <dd title={new Date(data.started_at).toLocaleString()}>{new Date(data.started_at).toLocaleTimeString()}</dd>
              </div>
              {!plainWords() && (
                <div>
                  <dt>Evaluation</dt>
                  <dd className="mono">{data.eval_id}</dd>
                </div>
              )}
            </dl>
            <ComparePicker report={data} />
          </header>
          {data.status !== "running" && <PlainLead>{evalLead(data)}</PlainLead>}

          {data.status === "running" && data.n_cases === 0 ? (
            <section className="card outcome" data-status="running" role="status">
              <Icon name="spinner" size={16} className="spin" />
              <div>
                <strong>Evaluation in progress…</strong>
                <p>Results appear as cases finish.</p>
              </div>
            </section>
          ) : (
            data.kind === "faultlab" ? (
              <FaultLabReport report={data} />
            ) : (
              <>
                <Summary report={data} />
                <Technical title="Show technical details: every check for every case">
                  <Matrix report={data} />
                </Technical>
              </>
            )
          )}
          {plainWords() && (
            <p className="foot muted small">
              Identifiers: {data.eval_id} · test set {data.dataset_version} ({data.dataset_hash}){data.seed != null ? ` · seed ${data.seed}` : ""}
            </p>
          )}
        </>
      )}
    </>
  );
}
