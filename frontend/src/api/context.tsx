import { createContext, useContext } from "react";
import type { DataSource } from "./client";

export const DataSourceContext = createContext<DataSource | null>(null);

export function useDataSource(): DataSource {
  const source = useContext(DataSourceContext);
  if (!source) throw new Error("useDataSource must be used inside <DataSourceContext.Provider>");
  return source;
}
