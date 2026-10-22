import { ApiUnreachableError } from "../api/client";
import { useDataSource } from "../api/context";
import { ApiDown } from "../components/ApiDown";
import { RunTable, StatStrip } from "../components/RunTable";
import { StartHere } from "../components/StartHere";
import { StartRunPanel } from "../components/StartRunPanel";
import { useQuery } from "../hooks/useQuery";

export function RunsPage() {
  const source = useDataSource();
  // A recorded demo never changes, so there is nothing to poll for.
  const runs = useQuery(() => source.listRuns(), [source], { refetchMs: () => (source.kind === "demo" ? false : 4000) });
  const scenarios = useQuery(() => source.listScenarios(), [source]);

  const unreachable = runs.error instanceof ApiUnreachableError && !runs.data;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p className="lede">Every agent execution, recorded. Open a run to see its trace, timing and errors.</p>
        </div>
      </div>

      {unreachable ? (
        <ApiDown onRetry={runs.refetch} />
      ) : (
        <>
          {source.kind === "demo" && <StartHere />}
          {source.canStartRuns && <StartRunPanel scenarios={scenarios.data ?? []} />}
          {runs.loading && !runs.data ? (
            <p className="muted" role="status">
              Loading runs…
            </p>
          ) : runs.error && !runs.data ? (
            <p className="form-error" role="alert">
              Could not load runs: {runs.error.message}
            </p>
          ) : runs.data && runs.data.length === 0 ? (
            <section className="card empty">
              <h2 className="card-title">No runs yet</h2>
              <p>Start your first run above. It takes a moment, then you can open it to see every model call and tool call as a trace.</p>
            </section>
          ) : (
            runs.data && (
              <>
                <StatStrip runs={runs.data} />
                <RunTable runs={runs.data} />
              </>
            )
          )}
          {runs.error && runs.data && (
            <p className="muted small" role="status">
              Connection lost. Showing the last data and retrying…
            </p>
          )}
        </>
      )}
    </>
  );
}
