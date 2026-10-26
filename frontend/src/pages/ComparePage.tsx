import { useMemo, useState } from "react";
import { ApiError, ApiUnreachableError } from "../api/client";
import { useDataSource } from "../api/context";
import type { CaseChange, Comparison, LabEffect } from "../api/types";
import { ApiDown } from "../components/ApiDown";
import { PlainLead, Technical } from "../components/Plain";
import { compareLead, plainModel } from "../content/plain";
import { Icon } from "../components/Icon";
import { RateBar } from "../components/RateBar";
import { VariantChip } from "../components/VariantChip";
import { compareHref, evalHref, runHref } from "../hooks/useHashRoute";
import { useQuery } from "../hooks/useQuery";
import { CHANGE_LABEL, costRows, delta, passCounts, sameAgent, variantInfo, variantLabel, verdict } from "../lib/compare";
import { kindLabel, metricLabel } from "../lib/metrics";
import { plainWords } from "../lib/plain";
import { effectLabel } from "../lib/notes";

const ORDER: Record<CaseChange["change"], number> = { broken: 0, fixed: 1, only_baseline: 2, only_candidate: 3, still_failing: 4, still_passing: 5 };
const MOVED: CaseChange["change"][] = ["broken", "fixed", "only_baseline", "only_candidate"];

function Head({ baselineId, data }: { baselineId: string; data?: Comparison }) {
  return (
    <>
      <a className="back" href={evalHref(baselineId)}>
        <Icon name="back" size={15} /> {plainWords() ? "Back to the results" : "Back to the evaluation"}
      </a>
      <header className="run-head">
        <div className="run-title">
          <span className="pill" data-status="neutral">
            Before and after
          </span>
          <h1>{data ? `${variantLabel(data.baseline.variant)} → ${variantLabel(data.candidate.variant)}` : (plainWords() ? "Comparing two sets of results" : "Comparing two evaluations")}</h1>
        </div>
        {data && (
          <dl className="facts-row">
            <div>
              <dt>{kindLabel(data.kind)}</dt>
              <dd>
                {data.matched} {data.kind === "faultlab" ? (plainWords() ? "planted problems" : "faults") : plainWords() ? "test cases" : "cases"} compared
              </dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{plainWords() ? plainModel(data.baseline.model) : data.baseline.model}</dd>
            </div>
            {!plainWords() && (
              <div>
                <dt>Dataset</dt>
                <dd className="mono">
                  {data.baseline.dataset_version} · {data.baseline.dataset_hash}
                </dd>
              </div>
            )}
            <div>
              <dt>Before</dt>
              <dd>
                <a className="ext" href={evalHref(data.baseline.eval_id)}>
                  <span className="mono">{data.baseline.eval_id}</span>
                </a>{" "}
                <VariantChip variant={data.baseline.variant} rescoredFrom={data.baseline.rescored_from} />
              </dd>
            </div>
            <div>
              <dt>After</dt>
              <dd>
                <a className="ext" href={evalHref(data.candidate.eval_id)}>
                  <span className="mono">{data.candidate.eval_id}</span>
                </a>{" "}
                <VariantChip variant={data.candidate.variant} rescoredFrom={data.candidate.rescored_from} />
              </dd>
            </div>
          </dl>
        )}
      </header>
    </>
  );
}

function Headline({ data }: { data: Comparison }) {
  const v = verdict(data);
  const { before, after, total } = passCounts(data);
  const lab = data.kind === "faultlab";
  const what = lab
    ? plainWords() ? "Planted problems with no effect on the run" : "Faults with no effect on the run"
    : plainWords() ? "Cases where the agent finished the job and followed the rules" : "Cases that passed both gating checks";
  return (
    <section className="card verdict" data-tone={v.tone} aria-labelledby="verdict-title">
      <div className="verdict-main">
        <p className="eyebrow">What changed</p>
        <h2 id="verdict-title">{v.headline}</h2>
        <p>{v.detail}</p>
      </div>
      <dl className="verdict-bars">
        <div>
          <dt>{what}, before</dt>
          <dd>
            <RateBar passed={before} total={total} label={`${what}, before`} />
          </dd>
        </div>
        <div>
          <dt>{what}, after</dt>
          <dd>
            <RateBar passed={after} total={total} label={`${what}, after`} />
            <span className="delta">{delta(before, after)}</span>
          </dd>
        </div>
      </dl>
      <ul className="verdict-counts" aria-label="Counts">
        <li data-kind="fixed">
          <strong>{data.fixed}</strong> fixed
        </li>
        <li data-kind="broken">
          <strong>{data.broken}</strong> broken
        </li>
        <li>
          <strong>{data.still_passing}</strong> still {lab ? "harmless" : "passing"}
        </li>
        <li>
          <strong>{data.still_failing}</strong> still {lab ? "harmful" : "failing"}
        </li>
      </ul>
    </section>
  );
}

const effectStatus = (effect: LabEffect | null) => (effect === "no_effect" ? "ok" : effect === "silent" ? "warn" : "error");

function Outcome({ passed, effect }: { passed: boolean | null; effect: LabEffect | null }) {
  if (effect) {
    return (
      <span className="pill" data-status={effectStatus(effect)}>
        {effectLabel(effect)}
      </span>
    );
  }
  if (passed === null) return <span className="muted">–</span>;
  return (
    <span className="outcome-mark" data-pass={passed}>
      <Icon name={passed ? "check" : "x"} size={14} />
      {passed ? "Passed" : "Failed"}
    </span>
  );
}

function ChangePill({ change }: { change: CaseChange["change"] }) {
  const status = change === "fixed" ? "ok" : change === "broken" ? "error" : "neutral";
  const icon = change === "fixed" ? "check" : change === "broken" ? "x" : null;
  return (
    <span className="pill" data-status={status}>
      {icon && <Icon name={icon} size={13} />}
      {CHANGE_LABEL[change]}
    </span>
  );
}

function Cases({ data }: { data: Comparison }) {
  const lab = data.kind === "faultlab";
  const moved = data.cases.filter((c) => MOVED.includes(c.change));
  const [show, setShow] = useState<"changed" | "all">("changed");
  const rows = useMemo(
    () => [...(show === "all" ? data.cases : moved)].sort((a, b) => ORDER[a.change] - ORDER[b.change]),
    [data.cases, moved, show],
  );
  const noun = lab ? "fault" : "case";

  return (
    <section className="card table-card" aria-labelledby="cases-title">
      <div className="table-head">
        <div>
          <h2 id="cases-title" className="card-title">
            {lab ? "Every fault, before and after" : "Case by case"}
          </h2>
          <p className="muted small">Broken ones come first: a fix that breaks something that worked is not free.</p>
        </div>
        <div className="seg seg-text" role="radiogroup" aria-label={`Which ${noun}s to show`}>
          <button type="button" role="radio" aria-checked={show === "changed"} className="seg-btn" onClick={() => setShow("changed")}>
            Changed<span className="count">{moved.length}</span>
          </button>
          <button type="button" role="radio" aria-checked={show === "all"} className="seg-btn" onClick={() => setShow("all")}>
            All<span className="count">{data.cases.length}</span>
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="empty-inline">No {noun} changed its verdict. Show all to see them anyway.</p>
      ) : (
        <div className="table-scroll">
          <table className="plain compare-cases">
            <caption className="sr-only">Each {noun} before and after</caption>
            <thead>
              <tr>
                <th scope="col">{lab ? "Fault" : "Case"}</th>
                <th scope="col">Before</th>
                <th scope="col">After</th>
                <th scope="col">Change</th>
                <th scope="col">Why it fails after</th>
                <th scope="col" className="num">
                  Runs
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.case_id} data-change={c.change}>
                  <td className="case-cell">
                    <span className="case-id">
                      <span className="mono">{c.case_id}</span>
                      <span className="muted small">{c.category.replace("_", " ")}</span>
                    </span>
                    <span className="case-task">{c.task}</span>
                  </td>
                  <td>
                    <Outcome passed={c.baseline_passed} effect={c.baseline_effect} />
                  </td>
                  <td>
                    <Outcome passed={c.candidate_passed} effect={c.candidate_effect} />
                  </td>
                  <td>
                    <ChangePill change={c.change} />
                  </td>
                  <td className="small">
                    {c.candidate_passed === false && c.candidate_failed_checks.length > 0 ? c.candidate_failed_checks.map(metricLabel).join(", ") : <span className="muted">–</span>}
                  </td>
                  <td className="num run-links">
                    {c.baseline_run_id ? (
                      <a className="ext" href={runHref(c.baseline_run_id)} aria-label={`Open the baseline run of ${c.case_id}`}>
                        Before
                      </a>
                    ) : null}
                    {c.candidate_run_id ? (
                      <a className="ext" href={runHref(c.candidate_run_id)} aria-label={`Open the candidate run of ${c.case_id}`}>
                        After
                      </a>
                    ) : null}
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

function Checks({ data }: { data: Comparison }) {
  return (
    <section className="card table-card" aria-labelledby="checks-title">
      <div className="table-head">
        <div>
          <h2 id="checks-title" className="card-title">
            By check
          </h2>
          <p className="muted small">How many {data.kind === "faultlab" ? "faults" : "cases"} each check passed, before and after. The two gating checks decide whether a run passes.</p>
        </div>
      </div>
<div className="table-scroll">
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">Check</th>
            <th scope="col">Before</th>
            <th scope="col">After</th>
            <th scope="col" className="num">
              Change
            </th>
          </tr>
        </thead>
        <tbody>
          {data.metrics.map((m) => (
            <tr key={m.metric}>
              <td>
                {metricLabel(m.metric)}
                {m.gating && <span className="gate">gates</span>}
              </td>
              <td>
                <RateBar passed={m.baseline_passed} total={m.baseline_total} label={`${metricLabel(m.metric)} before`} />
              </td>
              <td>
                <RateBar passed={m.candidate_passed} total={m.candidate_total} label={`${metricLabel(m.metric)} after`} />
              </td>
              <td className="num" data-sign={Math.sign(m.candidate_passed - m.baseline_passed)}>
                {delta(m.baseline_passed, m.candidate_passed)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </section>
  );
}

function Cost({ data }: { data: Comparison }) {
  const rows = costRows(data.baseline_cost, data.candidate_cost);
  return (
    <section className="card table-card" aria-labelledby="cost-title">
      <div className="table-head">
        <div>
          <h2 id="cost-title" className="card-title">
            What it cost
          </h2>
          <p className="muted small">Over the {data.baseline_cost.cases} {data.kind === "faultlab" ? "faults" : "cases"} both ran. Tokens appear only when every model call reported them.</p>
        </div>
      </div>
<div className="table-scroll">
      <table className="plain">
        <thead>
          <tr>
            <th scope="col" />
            <th scope="col" className="num">
              Before
            </th>
            <th scope="col" className="num">
              After
            </th>
            <th scope="col" className="num">
              Change
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">
                {r.label}
                {r.note && <span className="muted small row-note">{r.note}</span>}
              </th>
              <td className="num">{r.before}</td>
              <td className="num">{r.after}</td>
              <td className="num">{r.change}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </section>
  );
}

function Categories({ data }: { data: Comparison }) {
  if (data.categories.length === 0) return null;
  return (
    <section className="card table-card" aria-labelledby="comp-cat-title">
      <div className="table-head">
        <h2 id="comp-cat-title" className="card-title">
          By kind of task
        </h2>
      </div>
<div className="table-scroll">
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">Category</th>
            <th scope="col">Before</th>
            <th scope="col">After</th>
            <th scope="col" className="num">
              Change
            </th>
          </tr>
        </thead>
        <tbody>
          {data.categories.map((c) => (
            <tr key={c.category}>
              <td>{c.category.replace("_", " ")}</td>
              <td>
                <RateBar passed={c.baseline_passed} total={c.total} label={`${c.category} before`} />
              </td>
              <td>
                <RateBar passed={c.candidate_passed} total={c.total} label={`${c.category} after`} />
              </td>
              <td className="num">{delta(c.baseline_passed, c.candidate_passed)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </section>
  );
}

function Limits({ data }: { data: Comparison }) {
  const lab = data.kind === "faultlab";
  const plain = plainWords();
  return (
    <section className="card limits" aria-label="How to read this">
      <h2 className="card-title">How to read this</h2>
      <ul>
        <li>
          {plain ? (
            <>
              Only {lab ? "planted problems" : "test cases"} that both sides ran are counted. This page only exists when both were run on the same AI model and the same {lab ? "problems" : "test cases"},
              so a difference cannot come from a different test.
            </>
          ) : (
            <>
              Only {lab ? "faults" : "cases"} both evaluations ran are counted, and the page only exists for two evaluations of the same model, dataset content and kind, so a
              difference cannot come from a different test.
            </>
          )}
        </li>
        <li>
          {plain ? "One try per" : "One run per"} {lab ? (plain ? "planted problem" : "fault") : plain ? "test case" : "case"} on one {plain ? "AI " : ""}model, {data.matched} compared. These are counts, not percentages with error bars.
        </li>
        <li>
          {plain
            ? "Fixed and broken are decided by the checks. A check can be wrong. When one was, I fixed it under a new version of the test cases and judged the old results again. I never edited a result."
            : "Fixed and broken are measured against the checks. A check can be wrong; when one was, it was fixed under a new dataset version and the old results were re-judged, never edited."}
        </li>
        {data.candidate.variant !== "baseline" && variantInfo(data.candidate.variant) && (
          <li>
            <strong>{variantLabel(data.candidate.variant)}</strong>: {variantInfo(data.candidate.variant)?.what}
          </li>
        )}
      </ul>
    </section>
  );
}

export function ComparePage({ baselineId, candidateId }: { baselineId: string; candidateId: string }) {
  const source = useDataSource();
  const result = useQuery(() => source.compare(baselineId, candidateId), [source, baselineId, candidateId]);
  const data = result.data;
  const refused = result.error instanceof ApiError && result.error.status === 422;
  const notFound = result.error instanceof ApiError && result.error.status === 404;

  return (
    <>
      <Head baselineId={baselineId} data={data} />

      {result.error instanceof ApiUnreachableError && !data ? (
        <ApiDown onRetry={result.refetch} />
      ) : refused ? (
        <section className="card empty" role="alert">
          <h2 className="card-title">These two cannot be compared fairly</h2>
          <p>{result.error?.message}</p>
          <p className="muted small">
            A comparison only makes sense when both evaluations ran the same cases on the same model, so the difference can only come from the agent.{" "}
            <a href={evalHref(baselineId)}>Open the first evaluation</a> to pick another one to compare it with.
          </p>
        </section>
      ) : notFound ? (
        <section className="card empty" role="alert">
          <h2 className="card-title">Evaluation not found</h2>
          <p>{result.error?.message}</p>
        </section>
      ) : !data ? (
        <p className="muted" role="status">
          {result.error ? `Could not load the comparison: ${result.error.message}` : "Comparing…"}
        </p>
      ) : (
        <>
          {sameAgent(data) && (
            <section className="callout warn" role="note">
              <Icon name="alert" size={15} />
              <div>
                <strong>Both evaluations used the same agent</strong>
                <p>Any difference below is run-to-run noise, not a change. That is what this page is for when you want to know how much to trust a difference.</p>
              </div>
            </section>
          )}
          <PlainLead>{compareLead(data)}</PlainLead>
          <Headline data={data} />
          <Cases data={data} />
          <Cost data={data} />
          <Technical title="Show technical details: results by check and by kind of task">
            <Checks data={data} />
            <Categories data={data} />
          </Technical>
          <Limits data={data} />
          <p className="foot muted small">
            <a href={compareHref(candidateId, baselineId)}>Swap before and after</a>
          </p>
        </>
      )}
    </>
  );
}
