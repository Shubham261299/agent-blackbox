import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, ApiUnreachableError } from "./client";
import { createDemoSource } from "./demo";
import { comparison, evalReport, run, runEvaluation, runFault, span } from "../test/factories";

const FILES: Record<string, unknown> = {
  "runs.json": [run({ run_id: "run-a" }), run({ run_id: "run-lab" })],
  "scenarios.json": [{ name: "refund_happy_path", description: "d", example_task: "t" }],
  "evals.json": [evalReport({ eval_id: "eval-1" }), evalReport({ eval_id: "eval-2" }), evalReport({ eval_id: "eval-3" })],
  "evals/eval-1.json": evalReport({ eval_id: "eval-1" }),
  "spans/run-a.json": [span({ span_id: "s1", name: "agent.run" })],
  "run-evaluations/run-a.json": runEvaluation({ run_id: "run-a" }),
  "faults.json": { "run-lab": [runFault()] },
  "comparisons/index.json": { ok: { "eval-1|eval-2": "eval-1__eval-2.json" }, refused: { "eval-1|eval-3": "They ran different cases.", "eval-1|eval-1": "An evaluation cannot be compared with itself." } },
  "comparisons/eval-1__eval-2.json": comparison({ matched: 7 }),
  "manifest.json": { format: 1, models: ["ollama:m"], recorded_from: "2026-10-14", recorded_to: "2026-10-19", counts: {}, evaluations: [], tour: {} },
};

let requested: string[];

function serve(files: Record<string, unknown> = FILES) {
  requested = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      requested.push(url);
      const path = url.replace(/^demo-data\//, "");
      return path in files ? new Response(JSON.stringify(files[path]), { status: 200 }) : new Response("nope", { status: 404 });
    }),
  );
}

beforeEach(() => serve());
afterEach(() => vi.unstubAllGlobals());

describe("createDemoSource", () => {
  it("is a recorded demo that cannot start anything and has no Jaeger", () => {
    const source = createDemoSource();
    expect(source.kind).toBe("demo");
    expect(source.canStartRuns).toBe(false);
    expect(source.canStartEvals).toBe(false);
    expect(source.traceUrl("abc")).toBeNull();
  });

  it("refuses to start a run or an evaluation, saying why", async () => {
    const source = createDemoSource();
    await expect(source.startRun({ task: "x", model: "scripted" })).rejects.toMatchObject({ status: 405, message: expect.stringContaining("cannot start anything") });
    await expect(source.startEval("reference")).rejects.toBeInstanceOf(ApiError);
    expect(requested).toEqual([]);
  });

  it("reads files from the folder it is given, and fetches each file once", async () => {
    const source = createDemoSource("demo-data");
    await source.listRuns();
    await source.listRuns();
    await source.getRun("run-a");
    expect(requested).toEqual(["demo-data/runs.json"]);
  });

  it("looks up one run, and says not found for one that is not in the demo", async () => {
    const source = createDemoSource();
    expect((await source.getRun("run-a")).run_id).toBe("run-a");
    await expect(source.getRun("run-zzz")).rejects.toMatchObject({ status: 404, message: "run not found" });
  });

  it("does not even ask the server for the spans of a run it does not hold", async () => {
    const source = createDemoSource();
    await expect(source.getSpans("run-zzz")).rejects.toMatchObject({ status: 404 });
    await expect(source.getRunEvaluation("run-zzz")).rejects.toMatchObject({ status: 404 });
    expect(requested).toEqual(["demo-data/runs.json"]);
    expect((await source.getSpans("run-a"))[0]?.span_id).toBe("s1");
    expect((await source.getRunEvaluation("run-a")).run_id).toBe("run-a");
  });

  it("returns the planted faults of a lab run and nothing for any other run", async () => {
    const source = createDemoSource();
    expect(await source.getRunFaults("run-lab")).toHaveLength(1);
    expect(await source.getRunFaults("run-a")).toEqual([]);
    await expect(source.getRunFaults("run-zzz")).rejects.toMatchObject({ status: 404 });
  });

  it("lists scenarios and evaluations and opens one evaluation", async () => {
    const source = createDemoSource();
    expect(await source.listScenarios()).toHaveLength(1);
    expect((await source.listEvals()).map((e) => e.eval_id)).toEqual(["eval-1", "eval-2", "eval-3"]);
    expect((await source.getEval("eval-1")).eval_id).toBe("eval-1");
    await expect(source.getEval("eval-nope")).rejects.toMatchObject({ status: 404, message: "evaluation not found" });
  });

  it("serves a baked comparison", async () => {
    expect((await createDemoSource().compare("eval-1", "eval-2")).matched).toBe(7);
  });

  it("gives the API's own reason for a pair it refused, with the 422 the page looks for", async () => {
    const source = createDemoSource();
    await expect(source.compare("eval-1", "eval-3")).rejects.toMatchObject({ status: 422, message: "They ran different cases." });
    await expect(source.compare("eval-1", "eval-1")).rejects.toMatchObject({ status: 422, message: "An evaluation cannot be compared with itself." });
  });

  it("says which evaluation is not in the demo, as the API does", async () => {
    const source = createDemoSource();
    await expect(source.compare("eval-1", "eval-x")).rejects.toMatchObject({ status: 404, message: "evaluation not found: eval-x" });
    await expect(source.compare("eval-y", "eval-x")).rejects.toMatchObject({ status: 404, message: "evaluation not found: eval-y, eval-x" });
  });

  it("explains a pair that is neither baked nor refused instead of failing blankly", async () => {
    const source = createDemoSource();
    await expect(source.compare("eval-2", "eval-1")).rejects.toMatchObject({ status: 422, message: expect.stringContaining("not compared in this demo") });
  });

  it("reads the manifest for the about line and the tour", async () => {
    expect((await createDemoSource().demoInfo?.())?.recorded_from).toBe("2026-10-14");
  });

  it("reports an unreachable demo when the network is down, and retries instead of remembering the failure", async () => {
    const source = createDemoSource();
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(source.listRuns()).rejects.toBeInstanceOf(ApiUnreachableError);
    serve();
    expect(await source.listRuns()).toHaveLength(2);
  });

  it("says a file is not in the demo when the server has no such file, which is not the same as being offline", async () => {
    const files = { ...FILES };
    delete files["evals/eval-1.json"];
    serve(files);
    await expect(createDemoSource().getEval("eval-1")).rejects.toMatchObject({ status: 404, message: "not in this demo" });
  });

  it("treats a server error as unreachable too", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("x", { status: 503 })));
    await expect(createDemoSource().listRuns()).rejects.toBeInstanceOf(ApiUnreachableError);
  });
});
