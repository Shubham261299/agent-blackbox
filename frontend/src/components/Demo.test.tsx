import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { ApiError, ApiUnreachableError, type DataSource } from "../api/client";
import { DataSourceContext } from "../api/context";
import type { DemoManifest } from "../api/types";
import { RunsPage } from "../pages/RunsPage";
import { EvalsPage } from "../pages/EvalsPage";
import { comparison, evalReport } from "../test/factories";
import { fakeSource } from "../test/fakeSource";
import { AboutDemo, REPO_URL, formatDay } from "./AboutDemo";
import { ApiDown } from "./ApiDown";
import { StartHere } from "./StartHere";

const MANIFEST: DemoManifest = {
  format: 1,
  models: ["ollama:qwen2.5:7b"],
  recorded_from: "2026-10-14",
  recorded_to: "2026-10-19",
  counts: { runs: 173, spans: 883, evaluations: 11, comparisons: 20, refused_pairs: 101 },
  evaluations: [],
  tour: { failed_run: "run-e92cfa5d", lab: "eval-lab", fixed: ["eval-lab", "eval-res"], regressed: ["eval-bench", "eval-guided"] },
};

function demoSource(over: Partial<DataSource> = {}): DataSource {
  return fakeSource({
    kind: "demo",
    canStartRuns: false,
    canStartEvals: false,
    traceUrl: () => null,
    demoInfo: vi.fn().mockResolvedValue(MANIFEST),
    compare: vi.fn().mockImplementation(async (a: string) =>
      a === "eval-lab" ? comparison({ matched: 4, fixed: 3, broken: 0 }) : comparison({ matched: 24, fixed: 2, broken: 5 }),
    ),
    ...over,
  });
}

function inProvider(source: DataSource, ui: React.ReactNode) {
  return render(<DataSourceContext.Provider value={source}>{ui}</DataSourceContext.Provider>);
}

beforeEach(() => {
  window.location.hash = "";
});
afterEach(() => vi.useRealTimers());

describe("StartHere", () => {
  it("shows the four stops with links, and numbers read from the stored comparisons", async () => {
    inProvider(demoSource(), <StartHere />);
    const card = await screen.findByRole("region", { name: /Start here/ });
    const links = within(card).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "#/runs/run-e92cfa5d",
      "#/evals/eval-lab",
      "#/compare/eval-lab/eval-res",
      "#/compare/eval-bench/eval-guided",
    ]);
    expect(within(card).getAllByRole("listitem")).toHaveLength(4);
    expect(card).toHaveTextContent("3 now have no effect on the run");
    expect(card).toHaveTextContent("On 24 cases it fixed 2 and broke 5.");
  });

  it("still shows the stops, without numbers, when a comparison cannot be loaded", async () => {
    inProvider(demoSource({ compare: vi.fn().mockRejectedValue(new ApiError("not in this demo", 404)) }), <StartHere />);
    const card = await screen.findByRole("region", { name: /Start here/ });
    expect(within(card).getAllByRole("link")).toHaveLength(4);
    expect(card).not.toHaveTextContent("planted faults,");
  });

  it("is absent from the live app, which has no demo information", async () => {
    const live = fakeSource();
    inProvider(live, <StartHere />);
    await act(async () => {});
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("is absent when the data holds no tour", async () => {
    inProvider(demoSource({ demoInfo: vi.fn().mockResolvedValue({ ...MANIFEST, tour: {} }) }), <StartHere />);
    await act(async () => {});
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});

describe("AboutDemo", () => {
  it("says what was recorded, from which model, when, that nothing is live, and links to the source", async () => {
    inProvider(demoSource(), <AboutDemo />);
    const about = await screen.findByLabelText("About this demo");
    await within(about).findByText(/qwen2\.5:7b/);
    expect(about).toHaveTextContent("recorded from real runs of the local model qwen2.5:7b, between 14 October 2026 and 19 October 2026");
    expect(about).toHaveTextContent("Nothing is live");
    expect(about).toHaveTextContent("173 runs, 11 evaluations and 20 before-and-after comparisons");
    expect(within(about).getByRole("link")).toHaveAttribute("href", REPO_URL);
  });

  it("says 'on' for a single day and keeps the sentence whole without a model or dates", async () => {
    inProvider(demoSource({ demoInfo: vi.fn().mockResolvedValue({ ...MANIFEST, recorded_to: "2026-10-14" }) }), <AboutDemo />);
    expect(await screen.findByText(/on 14 October 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/between/)).not.toBeInTheDocument();
  });

  it("is still shown, and still says nothing is live, if the manifest cannot be read", async () => {
    inProvider(demoSource({ demoInfo: vi.fn().mockRejectedValue(new ApiUnreachableError()) }), <AboutDemo />);
    expect(await screen.findByLabelText("About this demo")).toHaveTextContent("Nothing is live");
  });

  it("formats a day in English whatever the time zone, and passes a bad value through", () => {
    expect(formatDay("2026-10-14")).toBe("14 October 2026");
    expect(formatDay("not a day")).toBe("not a day");
  });
});

describe("the demo in the pages", () => {
  it("puts the tour on the landing page and no start-a-run form", async () => {
    inProvider(demoSource(), <RunsPage />);
    expect(await screen.findByRole("region", { name: /Start here/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Start a run" })).not.toBeInTheDocument();
  });

  it("keeps the tour off the live landing page, which has the start-a-run form", async () => {
    inProvider(fakeSource(), <RunsPage />);
    expect(await screen.findByRole("region", { name: "Start a run" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Start here/ })).not.toBeInTheDocument();
  });

  it("does not keep re-fetching recorded data", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const source = demoSource();
    inProvider(source, <RunsPage />);
    await screen.findByRole("table");
    await act(async () => void vi.advanceTimersByTime(60_000));
    expect(source.listRuns).toHaveBeenCalledTimes(1);
  });

  it("polls the live app for new runs", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const source = fakeSource();
    inProvider(source, <RunsPage />);
    await screen.findByRole("table");
    await act(async () => void vi.advanceTimersByTime(9_000));
    expect((source.listRuns as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1);
  });

  it("does not keep re-fetching the recorded evaluations, and offers no way to run one", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const source = demoSource({ listEvals: vi.fn().mockResolvedValue([evalReport()]) });
    inProvider(source, <EvalsPage />);
    await screen.findByRole("table");
    await act(async () => void vi.advanceTimersByTime(60_000));
    expect(source.listEvals).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Run an evaluation")).not.toBeInTheDocument();
  });
});

describe("ApiDown in the demo", () => {
  it("does not tell a visitor to start a local API that is not there", () => {
    inProvider(demoSource(), <ApiDown onRetry={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The demo data could not be loaded");
    expect(screen.queryByText(/uvicorn/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry now" })).toBeInTheDocument();
  });

  it("still tells a live user how to start it", () => {
    inProvider(fakeSource(), <ApiDown onRetry={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The API is not running");
    expect(screen.getByText(/uvicorn --app-dir backend/)).toBeInTheDocument();
  });
});

describe("the app shell", () => {
  it("says it is recorded and carries the about line in the demo", async () => {
    render(<App source={demoSource()} />);
    expect(await screen.findByLabelText("About this demo")).toBeInTheDocument();
    expect(screen.getByText("Recorded demo data")).toBeInTheDocument();
  });

  it("has no about line in the live app", async () => {
    render(<App source={fakeSource()} />);
    await screen.findByText("Local only");
    expect(screen.queryByLabelText("About this demo")).not.toBeInTheDocument();
  });
});
