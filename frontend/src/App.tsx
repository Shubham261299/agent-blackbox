import { DataSourceContext } from "./api/context";
import type { DataSource } from "./api/client";
import { Shell } from "./components/Shell";
import { useHashRoute } from "./hooks/useHashRoute";
import { ComparePage } from "./pages/ComparePage";
import { EvalReportPage } from "./pages/EvalReportPage";
import { EvalsPage } from "./pages/EvalsPage";
import { HomePage } from "./pages/HomePage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsPage } from "./pages/RunsPage";

export default function App({ source }: { source: DataSource }) {
  const route = useHashRoute();
  return (
    <DataSourceContext.Provider value={source}>
      <Shell demo={source.kind === "demo"} route={route}>
        {route.name === "run" ? (
          <RunDetailPage key={route.runId} runId={route.runId} />
        ) : route.name === "evals" ? (
          <EvalsPage />
        ) : route.name === "compare" ? (
          <ComparePage key={`${route.baseline}/${route.candidate}`} baselineId={route.baseline} candidateId={route.candidate} />
        ) : route.name === "eval" ? (
          <EvalReportPage key={route.evalId} evalId={route.evalId} />
        ) : route.name === "home" && source.kind === "demo" ? (
          <HomePage />
        ) : (
          <RunsPage />
        )}
      </Shell>
    </DataSourceContext.Provider>
  );
}
