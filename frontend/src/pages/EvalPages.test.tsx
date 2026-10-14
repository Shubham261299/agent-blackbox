import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, ApiUnreachableError } from "../api/client";
import type { DataSource } from "../api/client";
import { DataSourceContext } from "../api/context";
import { caseResult, evalReport, withFailures } from "../test/factories";
import { fakeSource } from "../test/fakeSource";
import { EvalReportPage, detectionRows } from "./EvalReportPage";
import { EvalsPage } from "./EvalsPage";

function renderWith(source: DataSource, node: React.ReactNode) {
  return render(<DataSourceContext.Provider value={source}>{node}</DataSourceContext.Provider>);
}

beforeEach(() => {
  window.location.hash = "";
});

describe("EvalsPage", () => {
  it("lists evaluations with kind, model, dataset and pass rate, linking to the report", async () => {
    renderWith(fakeSource(), <EvalsPage />);
    const link = await screen.findByRole("link", { name: "Benchmark" });
    expect(link).toHaveAttribute("href", "#/evals/eval-bench");
    const row = link.closest("tr") as HTMLElement;
    expect(within(row).getByText("ollama:qwen2.5:7b")).toBeInTheDocument();
    expect(within(row).getByText(/golden-v2 · abc123d/)).toBeInTheDocument();
    expect(within(row).getByRole("img", { name: "Cases passed: 2 of 3" })).toBeInTheDocument();
  });

  it("starts a scripted evaluation and opens its report", async () => {
    const user = userEvent.setup();
    const source = fakeSource();
    renderWith(source, <EvalsPage />);
    await user.click(await screen.findByRole("button", { name: /Run reference/ }));
    expect(source.startEval).toHaveBeenCalledWith("reference");
    expect(window.location.hash).toBe("#/evals/eval-new");
    // the page stays busy while it navigates away, so a second click cannot start a second batch
    expect(screen.getByRole("button", { name: /Run validation/ })).toBeDisabled();
  });

  it("starts a check validation batch", async () => {
    const user = userEvent.setup();
    const source = fakeSource();
    renderWith(source, <EvalsPage />);
    await user.click(await screen.findByRole("button", { name: /Run validation/ }));
    expect(source.startEval).toHaveBeenCalledWith("faults");
  });

  it("tells you how to benchmark a real model, because that runs from the command line", async () => {
    renderWith(fakeSource(), <EvalsPage />);
    expect(await screen.findByText("python -m blackbox.evals run --mode ollama")).toBeInTheDocument();
  });

  it("shows why a start failed", async () => {
    const user = userEvent.setup();
    renderWith(fakeSource({ startEval: vi.fn().mockRejectedValue(new Error("boom")) }), <EvalsPage />);
    await user.click(await screen.findByRole("button", { name: /Run reference/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });

  it("covers the empty, running and API-down states", async () => {
    const { unmount } = renderWith(fakeSource({ listEvals: vi.fn().mockResolvedValue([]) }), <EvalsPage />);
    expect(await screen.findByText("No evaluations yet")).toBeInTheDocument();
    unmount();

    const running = evalReport({ status: "running", n_cases: 0, n_passed: 0 });
    const second = renderWith(fakeSource({ listEvals: vi.fn().mockResolvedValue([running]) }), <EvalsPage />);
    expect(await screen.findByText("Running")).toBeInTheDocument();
    second.unmount();

    renderWith(fakeSource({ listEvals: vi.fn().mockRejectedValue(new ApiUnreachableError()) }), <EvalsPage />);
    expect(await screen.findByText("The API is not running")).toBeInTheDocument();
  });

  it("hides the start panel for read-only sources", async () => {
    renderWith(fakeSource({ canStartEvals: false, kind: "demo" }), <EvalsPage />);
    await screen.findByRole("table");
    expect(screen.queryByText("Run an evaluation")).not.toBeInTheDocument();
  });
});

describe("EvalReportPage", () => {
  it("leads with the result and says what it does and does not mean", async () => {
    renderWith(fakeSource(), <EvalReportPage evalId="eval-bench" />);
    const result = await screen.findByRole("region", { name: "Result" });
    expect(result).toHaveTextContent("2 of 3");
    expect(result).toHaveTextContent("runs passed both gating checks");
    expect(result).toHaveTextContent("Measured on ollama:qwen2.5:7b with seed 0, one run per case (n=3)");
    expect(screen.getByText("golden-v2 · abc123def456")).toBeInTheDocument();
  });

  it("shows pass rates per check, marks the two that gate, and leaves latency out of the pass rates", async () => {
    renderWith(fakeSource(), <EvalReportPage evalId="eval-bench" />);
    const byCheck = (await screen.findByRole("heading", { name: "By check" })).closest("section") as HTMLElement;
    expect(within(byCheck).getByRole("img", { name: "Policy compliance: 2 of 3" })).toBeInTheDocument();
    expect(within(byCheck).getAllByText("gates the run")).toHaveLength(2);
    expect(within(byCheck).queryByText("Latency")).not.toBeInTheDocument();
    expect(within(byCheck).getByText(/Run time: median/)).toBeInTheDocument();

    const byKind = screen.getByRole("heading", { name: "By kind of task" }).closest("section") as HTMLElement;
    expect(within(byKind).getByRole("img", { name: "normal: 1 of 2" })).toBeInTheDocument();
  });

  it("lists failing cases first, with an icon and a reason for every failed check", async () => {
    renderWith(fakeSource(), <EvalReportPage evalId="eval-bench" />);
    const matrix = await screen.findByRole("table", { name: "Results per case and check" });
    const ids = within(matrix).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0]?.textContent ?? "");
    expect(ids[0]).toMatch(/^N6/);
    expect(ids.some((t) => t.startsWith("N1"))).toBe(true);
    expect(ids).toHaveLength(3);

    const failedRow = within(matrix).getAllByRole("row")[1] as HTMLElement;
    expect(within(failedRow).getByText(/failed: update_shipping_address on order 45 without a successful lookup first/)).toBeInTheDocument();
    expect(within(failedRow).getByRole("link", { name: "Open" })).toHaveAttribute("href", "#/runs/run-n6");
  });

  it("orders cases: failed a gating check, then failed only a reported check, then clean", async () => {
    const report = evalReport({
      cases: [
        caseResult({ case_id: "CLEAN" }),
        caseResult({ case_id: "SOFT", checks: withFailures({ tool_correctness: { reason: "x" } }) }),
        caseResult({ case_id: "HARD", passed: false, checks: withFailures({ task_completion: { gating: true, reason: "y" } }) }),
      ],
    });
    renderWith(fakeSource({ getEval: vi.fn().mockResolvedValue(report) }), <EvalReportPage evalId="e" />);
    const matrix = await screen.findByRole("table", { name: "Results per case and check" });
    const firstCells = within(matrix).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0]?.textContent ?? "");
    const order = firstCells.map((text) => ["HARD", "SOFT", "CLEAN"].find((id) => text.startsWith(id)));
    expect(order).toEqual(["HARD", "SOFT", "CLEAN"]);
  });

  it("can show only the failing cases", async () => {
    const user = userEvent.setup();
    renderWith(fakeSource(), <EvalReportPage evalId="eval-bench" />);
    const matrix = await screen.findByRole("table", { name: "Results per case and check" });
    await user.click(screen.getByRole("radio", { name: /Failing/ }));
    expect(within(matrix).getAllByRole("row")).toHaveLength(2); // header + N6
    expect(within(matrix).queryByText("I want a refund.")).not.toBeInTheDocument();
  });

  it("explains a validation batch in terms of faults and expectations", async () => {
    const validation = evalReport({
      kind: "validation", model: "scripted:faults", n_cases: 1, n_passed: 1, seed: null,
      cases: [caseResult({
        case_id: "skips_policy_check", category: "validation", passed: true, task: "base task",
        note: { fault: "skips_policy_check", description: "Refunds without checking the policy first.", expected_fail: ["policy_compliance", "tool_correctness"],
          actual_fail: ["policy_compliance", "tool_correctness"], matched: true },
        checks: withFailures({ policy_compliance: { gating: true }, tool_correctness: {} }),
      })],
      categories: [],
    });
    renderWith(fakeSource({ getEval: vi.fn().mockResolvedValue(validation) }), <EvalReportPage evalId="eval-val" />);
    expect(await screen.findByText("faults caught exactly as expected")).toBeInTheDocument();
    expect(screen.getByText(/Known faults planted into runs/)).toBeInTheDocument();
    expect(screen.getByText("Refunds without checking the policy first.")).toBeInTheDocument();
    expect(screen.getByText(/Expected to trip: Policy compliance, Tool correctness/)).toBeInTheDocument();
    expect(screen.getByText(/Detected exactly that/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "By kind of task" })).not.toBeInTheDocument();

    // a validation batch shows detection, not pass rates
    const detection = screen.getByRole("heading", { name: "By check: did it catch its faults?" }).closest("section") as HTMLElement;
    expect(within(detection).getByRole("img", { name: "Policy compliance caught: 1 of 1" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "By check" })).not.toBeInTheDocument();
  });

  it("counts caught faults and false alarms per check", () => {
    const note = (expected: string[], actual: string[]) => ({ expected_fail: expected, actual_fail: actual, matched: false });
    const rows = detectionRows([
      caseResult({ case_id: "a", note: note(["task_completion", "tool_correctness"], ["task_completion", "tool_correctness"]) }),
      caseResult({ case_id: "b", note: note(["tool_correctness"], ["tool_correctness", "step_efficiency"]) }), // step_efficiency: false alarm
      caseResult({ case_id: "c", note: note(["task_completion"], []) }), // task_completion: missed
    ]);
    const by = Object.fromEntries(rows.map((r) => [r.metric, r]));
    expect(by.task_completion).toMatchObject({ expected: 2, caught: 1, falseAlarms: 0 });
    expect(by.tool_correctness).toMatchObject({ expected: 2, caught: 2, falseAlarms: 0 });
    expect(by.step_efficiency).toMatchObject({ expected: 0, caught: 0, falseAlarms: 1 });
    expect(by.policy_compliance).toMatchObject({ expected: 0, caught: 0, falseAlarms: 0 });
  });

  it("describes a reference run as proof of the pipeline, not of a model", async () => {
    renderWith(fakeSource({ getEval: vi.fn().mockResolvedValue(evalReport({ kind: "reference", model: "scripted:reference", seed: null })) }),
      <EvalReportPage evalId="eval-ref" />);
    expect(await screen.findByText(/says nothing about any model/)).toBeInTheDocument();
  });

  it("shows progress while running, and handles not-found", async () => {
    const { unmount } = renderWith(
      fakeSource({ getEval: vi.fn().mockResolvedValue(evalReport({ status: "running", n_cases: 0, n_passed: 0, cases: [], metrics: [], categories: [] })) }),
      <EvalReportPage evalId="eval-x" />,
    );
    expect(await screen.findByText("Evaluation in progress…")).toBeInTheDocument();
    unmount();

    renderWith(fakeSource({ getEval: vi.fn().mockRejectedValue(new ApiError("evaluation not found", 404)) }), <EvalReportPage evalId="nope" />);
    expect(await screen.findByText("Evaluation not found")).toBeInTheDocument();
  });
});
