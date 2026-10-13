import { DataSourceContext } from "./api/context";
import type { DataSource } from "./api/client";
import { Shell } from "./components/Shell";
import { useHashRoute } from "./hooks/useHashRoute";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsPage } from "./pages/RunsPage";

export default function App({ source }: { source: DataSource }) {
  const route = useHashRoute();
  return (
    <DataSourceContext.Provider value={source}>
      <Shell demo={source.kind === "demo"}>
        {route.name === "run" ? <RunDetailPage key={route.runId} runId={route.runId} /> : <RunsPage />}
      </Shell>
    </DataSourceContext.Provider>
  );
}
