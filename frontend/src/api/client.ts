import type { RunRecord, RunRequest, ScenarioInfo, SpanRecord } from "./types";

/**
 * Everything the UI reads goes through this interface, so a prebaked-JSON source (static demo)
 * can replace the live API without touching a component.
 */
export interface DataSource {
  readonly kind: "live" | "demo";
  readonly canStartRuns: boolean;
  listRuns(): Promise<RunRecord[]>;
  getRun(runId: string): Promise<RunRecord>;
  getSpans(runId: string): Promise<SpanRecord[]>;
  listScenarios(): Promise<ScenarioInfo[]>;
  startRun(request: RunRequest): Promise<RunRecord>;
  /** Link to the same trace in Jaeger, when that backend exists. */
  traceUrl(traceId: string): string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The API did not answer at all (not started, wrong port, network down). */
export class ApiUnreachableError extends Error {
  constructor() {
    super("Cannot reach the Agent Blackbox API");
    this.name = "ApiUnreachableError";
  }
}

const JAEGER_UI = "http://localhost:16686";

export function createApiSource(base = "/api"): DataSource {
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${base}${path}`, init);
    } catch {
      throw new ApiUnreachableError();
    }
    // A dev proxy answers 502/504 when the backend behind it is down.
    if (response.status === 502 || response.status === 503 || response.status === 504) throw new ApiUnreachableError();
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        /* keep statusText */
      }
      throw new ApiError(detail, response.status);
    }
    return (await response.json()) as T;
  }

  return {
    kind: "live",
    canStartRuns: true,
    listRuns: () => request<RunRecord[]>("/runs"),
    getRun: (id) => request<RunRecord>(`/runs/${encodeURIComponent(id)}`),
    getSpans: (id) => request<SpanRecord[]>(`/runs/${encodeURIComponent(id)}/spans`),
    listScenarios: () => request<ScenarioInfo[]>("/scenarios"),
    startRun: (body) =>
      request<RunRecord>("/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    traceUrl: (traceId) => `${JAEGER_UI}/trace/${traceId}`,
  };
}
