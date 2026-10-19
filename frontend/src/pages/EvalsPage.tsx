import { useState } from "react";
import { ApiUnreachableError } from "../api/client";
import { useDataSource } from "../api/context";
import { ApiDown } from "../components/ApiDown";
import { CopyButton } from "../components/CopyButton";
import { Icon } from "../components/Icon";
import { RateBar } from "../components/RateBar";
import { VariantChip } from "../components/VariantChip";
import { evalHref } from "../hooks/useHashRoute";
import { useQuery } from "../hooks/useQuery";
import { timeAgo } from "../lib/format";
import { KIND_LABEL } from "../lib/metrics";

const BENCHMARK_CMD = "python -m blackbox.evals run --mode ollama";

export function EvalsPage() {
  const source = useDataSource();
  const evals = useQuery(() => source.listEvals(), [source], {
    refetchMs: (data) => (data?.some((e) => e.status === "running") ? 2000 : 8000),
  });
  const [busy, setBusy] = useState<"reference" | "faults" | "faultlab" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start(mode: "reference" | "faults" | "faultlab") {
    setBusy(mode);
    setError(null);
    try {
      const started = await source.startEval(mode);
      window.location.hash = evalHref(started.eval_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the evaluation.");
      setBusy(null);
    }
  }

  if (evals.error instanceof ApiUnreachableError && !evals.data) {
    return (
      <>
        <PageHead />
        <ApiDown onRetry={evals.refetch} />
      </>
    );
  }

  return (
    <>
      <PageHead />

      {source.canStartEvals && (
        <section className="card start" aria-labelledby="eval-start-title">
          <h2 id="eval-start-title" className="card-title">
            Run an evaluation
          </h2>
          <div className="eval-options">
            <div className="eval-option">
              <h3>Reference run</h3>
              <p>Replays a correct scripted run of all 24 cases. Instant. Shows the pipeline works; says nothing about a model.</p>
              <button type="button" className="btn" disabled={busy !== null} onClick={() => start("reference")}>
                <Icon name={busy === "reference" ? "spinner" : "play"} size={14} className={busy === "reference" ? "spin" : undefined} />
                Run reference
              </button>
            </div>
            <div className="eval-option">
              <h3>Check validation</h3>
              <p>Plants known faults in scripted behaviour and confirms each check catches exactly the ones it should. This is how the checks themselves are tested.</p>
              <button type="button" className="btn" disabled={busy !== null} onClick={() => start("faults")}>
                <Icon name={busy === "faults" ? "spinner" : "play"} size={14} className={busy === "faults" ? "spin" : undefined} />
                Run validation
              </button>
            </div>
            <div className="eval-option">
              <h3>Failure lab</h3>
              <p>Plants a timeout, malformed output, a wrong tool choice and a model failure, then asks trace analysis which span to look at first.</p>
              <button type="button" className="btn" disabled={busy !== null} onClick={() => start("faultlab")}>
                <Icon name={busy === "faultlab" ? "spinner" : "play"} size={14} className={busy === "faultlab" ? "spin" : undefined} />
                Run failure lab
              </button>
            </div>
            <div className="eval-option">
              <h3>Benchmark a model</h3>
              <p>Runs all 24 cases through the local model. It takes a few minutes, so it runs from the command line (with the project's virtual environment active):</p>
              <div className="codeline">
                <code className="mono">{BENCHMARK_CMD}</code>
                <CopyButton text={BENCHMARK_CMD} label="Copy command" />
              </div>
            </div>
          </div>
          {error && (
            <p className="form-error" role="alert">
              <Icon name="alert" size={14} /> {error}
            </p>
          )}
        </section>
      )}

      {evals.loading && !evals.data ? (
        <p className="muted" role="status">
          Loading evaluations…
        </p>
      ) : evals.data && evals.data.length === 0 ? (
        <section className="card empty">
          <h2 className="card-title">No evaluations yet</h2>
          <p>Run a reference evaluation above, or benchmark the local model from the command line.</p>
        </section>
      ) : (
        evals.data && (
          <section className="card table-card" aria-labelledby="evals-title">
            <div className="table-head">
              <h2 id="evals-title" className="card-title">
                All evaluations
              </h2>
            </div>
            <div className="table-scroll">
              <table className="runs">
                <thead>
                  <tr>
                    <th scope="col">Kind</th>
                    <th scope="col">Model</th>
                    <th scope="col">Agent</th>
                    <th scope="col">Dataset</th>
                    <th scope="col">Cases passed</th>
                    <th scope="col" className="num">
                      Started
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {evals.data.map((e) => (
                    <tr key={e.eval_id}>
                      <td className="task-cell">
                        <a className="row-link" href={evalHref(e.eval_id)}>
                          {KIND_LABEL[e.kind]}
                        </a>
                        <span className="mono muted small">{e.eval_id}</span>
                      </td>
                      <td>
                        <span className="model-name">{e.model}</span>
                      </td>
                      <td>
                        <VariantChip variant={e.variant} rescoredFrom={e.rescored_from} />
                      </td>
                      <td>
                        <span className="mono small">
                          {e.dataset_version} · {e.dataset_hash.slice(0, 7)}
                        </span>
                      </td>
                      <td>
                        {e.status === "running" ? (
                          <span className="pill" data-status="running">
                            <Icon name="spinner" size={13} className="spin" />
                            Running
                          </span>
                        ) : e.status === "error" ? (
                          <span className="pill" data-status="error">
                            <Icon name="x" size={13} />
                            Failed
                          </span>
                        ) : (
                          <RateBar passed={e.n_passed} total={e.n_cases} label="Cases passed" />
                        )}
                      </td>
                      <td className="num muted" title={new Date(e.started_at).toLocaleString()}>
                        {timeAgo(e.started_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )
      )}
    </>
  );
}

function PageHead() {
  return (
    <div className="page-head">
      <div>
        <h1>Evaluations</h1>
        <p className="lede">
          Each run is scored against what a correct run looks like. Open an evaluation to see which checks passed for which case, then follow a failure
          to the exact span.
        </p>
      </div>
    </div>
  );
}
