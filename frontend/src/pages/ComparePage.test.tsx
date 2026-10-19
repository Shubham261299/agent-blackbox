import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, ApiUnreachableError } from "../api/client";
import type { DataSource } from "../api/client";
import { DataSourceContext } from "../api/context";
import type { EvalRunSummary } from "../api/types";
import { caseChange, comparison, evalReport, happyPathSpans, run, runEvaluation, span } from "../test/factories";
import { fakeSource } from "../test/fakeSource";
import { ComparePage } from "./ComparePage";
import { EvalReportPage } from "./EvalReportPage";
import { EvalsPage } from "./EvalsPage";
import { RunDetailPage } from "./RunDetailPage";

function renderWith(source: DataSource, node: React.ReactNode) {
  return render(<DataSourceContext.Provider value={source}>{node}</DataSourceContext.Provider>);
}
const page = (source: DataSource) => renderWith(source, <ComparePage baselineId="eval-base" candidateId="eval-cand" />);

beforeEach(() => {
  window.location.hash = "";
});

describe("ComparePage", () => {
  it("leads with what changed, in counts, with the pass counts before and after", async () => {
    const source = fakeSource();
    page(source);
    const verdict = await screen.findByRole("region", { name: "1 case fixed, 1 case broken" });
    expect(source.compare).toHaveBeenCalledWith("eval-base", "eval-cand");
    expect(within(verdict).getByText(/net zero/)).toBeInTheDocument();
    expect(within(verdict).getByRole("img", { name: "Cases that passed both gating checks, before: 2 of 4" })).toBeInTheDocument();
    expect(within(verdict).getByRole("img", { name: "Cases that passed both gating checks, after: 2 of 4" })).toBeInTheDocument();
    const counts = within(verdict).getByRole("list", { name: "Counts" });
    expect(counts).toHaveTextContent("1 fixed");
    expect(counts).toHaveTextContent("1 broken");
    expect(counts).toHaveTextContent("1 still passing");
    expect(counts).toHaveTextContent("1 still failing");
  });

  it("names the two agents and links both evaluations", async () => {
    page(fakeSource());
    expect(await screen.findByRole("heading", { level: 1, name: "Baseline → Guided (v2)" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "eval-base" })).toHaveAttribute("href", "#/evals/eval-base");
    expect(screen.getByRole("link", { name: "eval-cand" })).toHaveAttribute("href", "#/evals/eval-cand");
    expect(screen.getByText(/golden-v2 · abc123def456/)).toBeInTheDocument();
  });

  it("shows the changed cases first, broken before fixed, and hides the ones that did not move until asked", async () => {
    const user = userEvent.setup();
    page(fakeSource());
    const table = await screen.findByRole("table", { name: /each case before and after/i });
    const ids = () => within(table).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0]?.textContent);
    expect(ids()).toEqual([expect.stringContaining("N1"), expect.stringContaining("N8")]); // broken, then fixed
    expect(screen.getByRole("radio", { name: /Changed\s*2/ })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: /All\s*4/ }));
    expect(ids()).toEqual([expect.stringContaining("N1"), expect.stringContaining("N8"), expect.stringContaining("A2"), expect.stringContaining("N2")]);
  });

  it("says in words and icons what happened to each changed case, and why a broken one fails now", async () => {
    page(fakeSource());
    const table = await screen.findByRole("table", { name: /each case before and after/i });
    const broken = within(table).getByText("N1").closest("tr") as HTMLElement;
    expect(within(broken).getByText("Broken")).toBeInTheDocument();
    expect(within(broken).getByText("Passed")).toBeInTheDocument();
    expect(within(broken).getByText("Failed")).toBeInTheDocument();
    expect(within(broken).getByText("Task completion, Tool correctness")).toBeInTheDocument();
    const fixed = within(table).getByText("N8").closest("tr") as HTMLElement;
    expect(within(fixed).getByText("Fixed")).toBeInTheDocument();
  });

  it("links every row to the run behind each side", async () => {
    page(fakeSource());
    const table = await screen.findByRole("table", { name: /each case before and after/i });
    const row = within(table).getByText("N8").closest("tr") as HTMLElement;
    expect(within(row).getByRole("link", { name: "Open the baseline run of N8" })).toHaveAttribute("href", "#/runs/run-b-n8");
    expect(within(row).getByRole("link", { name: "Open the candidate run of N8" })).toHaveAttribute("href", "#/runs/run-c-n8");
  });

  it("compares each check with a signed change, and the cost with its caveats", async () => {
    page(fakeSource());
    const checks = await screen.findByRole("region", { name: "By check" });
    const policy = within(checks).getByText("Policy compliance").closest("tr") as HTMLElement;
    expect(within(policy).getByText("+1")).toBeInTheDocument();
    const task = within(checks).getByText("Task completion").closest("tr") as HTMLElement;
    expect(within(task).getByText("−1")).toBeInTheDocument();
    expect(within(task).getByText("gates")).toBeInTheDocument();

    const cost = screen.getByRole("region", { name: "What it cost" });
    const tools = within(cost).getByText("Tool calls").closest("tr") as HTMLElement;
    expect(tools).toHaveTextContent("10");
    expect(tools).toHaveTextContent("7");
    expect(tools).toHaveTextContent("−3");
    expect(within(cost).getByText(/one slow case cannot move it/)).toBeInTheDocument();
    expect(within(cost).getByText(/one stuck model call can dominate it/)).toBeInTheDocument();
  });

  it("explains how to read the numbers and what the candidate agent is", async () => {
    page(fakeSource());
    const limits = await screen.findByRole("region", { name: "How to read this" });
    expect(within(limits).getByText(/same model, dataset content and kind/)).toBeInTheDocument();
    expect(within(limits).getByText(/Guided \(v2\)/)).toBeInTheDocument();
    expect(within(limits).getByText(/not percentages with error bars/)).toBeInTheDocument();
  });

  it("warns that two runs of the same agent show noise, not change", async () => {
    const c = comparison();
    page(fakeSource({ compare: vi.fn().mockResolvedValue({ ...c, candidate: { ...c.candidate, variant: "baseline" } }) }));
    expect(await screen.findByRole("note")).toHaveTextContent(/same agent.*run-to-run noise/is);
  });

  it("shows a case present on one side only without counting it", async () => {
    const c = comparison({
      cases: [caseChange({ case_id: "Z9", change: "only_candidate", baseline_passed: null, baseline_run_id: null })],
      fixed: 0, broken: 0, still_passing: 0, still_failing: 0, matched: 0,
    });
    page(fakeSource({ compare: vi.fn().mockResolvedValue(c) }));
    const table = await screen.findByRole("table", { name: /each case before and after/i });
    expect(within(table).getByText("Only in candidate")).toBeInTheDocument();
    expect(within(table).queryByRole("link", { name: /baseline run/ })).toBeNull();
  });

  it("says nothing changed when nothing did, and offers to show everything", async () => {
    const c = comparison({ fixed: 0, broken: 0, cases: [caseChange({ case_id: "N1" })], still_passing: 1, still_failing: 0, matched: 1 });
    page(fakeSource({ compare: vi.fn().mockResolvedValue(c) }));
    expect(await screen.findByRole("region", { name: "Nothing changed" })).toBeInTheDocument();
    expect(screen.getByText(/No case changed its verdict/)).toBeInTheDocument();
  });

  it("compares a failure lab by what each fault did to the run", async () => {
    const lab = comparison({
      kind: "faultlab", fixed: 1, broken: 0, still_passing: 0, still_failing: 1, matched: 2,
      cases: [
        caseChange({ case_id: "tool_timeout", category: "faultlab", task: "Order 42 arrived damaged.", change: "fixed", baseline_passed: false, candidate_passed: true,
          baseline_effect: "run_failed", candidate_effect: "no_effect" }),
        caseChange({ case_id: "wrong_tool", category: "faultlab", change: "still_failing", baseline_passed: false, candidate_passed: false,
          baseline_effect: "gating_failed", candidate_effect: "gating_failed" }),
      ],
    });
    page(fakeSource({ compare: vi.fn().mockResolvedValue(lab) }));
    expect(await screen.findByRole("region", { name: "1 fault fixed, none broken" })).toBeInTheDocument();
    const row = screen.getByText("tool_timeout").closest("tr") as HTMLElement;
    expect(within(row).getByText("Run failed")).toBeInTheDocument();
    expect(within(row).getByText("No effect")).toBeInTheDocument();
    expect(screen.getByText(/Faults with no effect on the run, before/)).toBeInTheDocument();
  });

  it("shows the reason in words when the API refuses an unfair comparison", async () => {
    const reason = "They ran different cases (golden-v2 e6a742cd5224 against holdout-v1 8c7eb9ea4eb0), so the difference could come from the test.";
    page(fakeSource({ compare: vi.fn().mockRejectedValue(new ApiError(reason, 422)) }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("cannot be compared fairly");
    expect(alert).toHaveTextContent(reason);
    expect(within(alert).getByRole("link", { name: "Open the first evaluation" })).toHaveAttribute("href", "#/evals/eval-base");
  });

  it("handles a missing evaluation", async () => {
    page(fakeSource({ compare: vi.fn().mockRejectedValue(new ApiError("evaluation not found: eval-cand", 404)) }));
    expect(await screen.findByRole("alert")).toHaveTextContent("evaluation not found: eval-cand");
  });

  it("shows the start-the-API help when the API is down", async () => {
    page(fakeSource({ compare: vi.fn().mockRejectedValue(new ApiUnreachableError()) }));
    expect(await screen.findByText("The API is not running")).toBeInTheDocument();
  });

  it("offers to swap before and after", async () => {
    page(fakeSource());
    expect(await screen.findByRole("link", { name: "Swap before and after" })).toHaveAttribute("href", "#/compare/eval-cand/eval-base");
  });
});

describe("the compare picker on an evaluation report", () => {
  const summary = (over: Partial<EvalRunSummary>): EvalRunSummary => {
    const { cases: _c, metrics: _m, categories: _k, ...rest } = evalReport();
    return { ...rest, ...over };
  };
  const others = [
    summary({ eval_id: "eval-res", variant: "resilient", n_passed: 19, n_cases: 24, started_at: "2026-10-19T10:00:00Z" }),
    summary({ eval_id: "eval-other-data", dataset_hash: "different", started_at: "2026-10-19T11:00:00Z" }),
    summary({ eval_id: "eval-guided", variant: "guided", n_passed: 16, n_cases: 24, started_at: "2026-10-19T12:00:00Z" }),
  ];
  const source = (over: Partial<DataSource> = {}) =>
    fakeSource({ getEval: vi.fn().mockResolvedValue(evalReport({ eval_id: "eval-bench" })), listEvals: vi.fn().mockResolvedValue(others), ...over });

  it("offers only evaluations the API would accept, newest first, and opens the comparison", async () => {
    const user = userEvent.setup();
    renderWith(source(), <EvalReportPage evalId="eval-bench" />);
    const select = await screen.findByRole("combobox", { name: /Compare this evaluation/ });
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Guided (v2) · 16/24 · eval-guided", "Resilient · 19/24 · eval-res"]); // the other dataset is not offered
    await user.selectOptions(select, "eval-res");
    await user.click(screen.getByRole("button", { name: "Compare" }));
    expect(window.location.hash).toBe("#/compare/eval-bench/eval-res");
  });

  it("says why there is nothing to compare with instead of showing an empty choice", async () => {
    renderWith(source({ listEvals: vi.fn().mockResolvedValue([others[1]]) }), <EvalReportPage evalId="eval-bench" />);
    expect(await screen.findByText(/Nothing to compare this with yet/)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("is not offered for an evaluation that is still running or only checks the checks", async () => {
    const { unmount } = renderWith(source({ getEval: vi.fn().mockResolvedValue(evalReport({ status: "running", n_cases: 0, n_passed: 0, cases: [] })) }), <EvalReportPage evalId="eval-bench" />);
    await screen.findByText("Evaluation in progress…");
    expect(screen.queryByRole("combobox")).toBeNull();
    unmount();
    renderWith(source({ getEval: vi.fn().mockResolvedValue(evalReport({ kind: "validation" })) }), <EvalReportPage evalId="eval-bench" />);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("shows which agent made the evaluation, and that it was rescored", async () => {
    renderWith(source({ getEval: vi.fn().mockResolvedValue(evalReport({ variant: "full-v3", rescored_from: "eval-old" })) }), <EvalReportPage evalId="eval-bench" />);
    expect(await screen.findByText("Full (v3)")).toBeInTheDocument();
    expect(screen.getByText("Rescored")).toHaveAttribute("title", expect.stringContaining("eval-old"));
  });
});

describe("variants elsewhere in the app", () => {
  it("shows the agent column in the evaluation list", async () => {
    const { cases: _c, metrics: _m, categories: _k, ...rest } = evalReport();
    renderWith(fakeSource({ listEvals: vi.fn().mockResolvedValue([{ ...rest, variant: "resilient" }, { ...rest, eval_id: "eval-2", variant: "baseline" }]) }), <EvalsPage />);
    expect(await screen.findByRole("columnheader", { name: "Agent" })).toBeInTheDocument();
    expect(screen.getByText("Resilient")).toBeInTheDocument();
    expect(screen.getByText("Baseline")).toBeInTheDocument();
  });

  it("names the agent on a run only when it is not the baseline", async () => {
    const { unmount } = renderWith(fakeSource({ getRun: vi.fn().mockResolvedValue(run({ variant: "full" })) }), <RunDetailPage runId="run-aaaa1111" />);
    expect(await screen.findByText("Full (v2)")).toBeInTheDocument();
    unmount();
    renderWith(fakeSource(), <RunDetailPage runId="run-aaaa1111" />);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByText("Baseline")).toBeNull();
  });
});

describe("a call that needed retries", () => {
  const retried = () => [
    ...happyPathSpans(),
    span({
      span_id: "t2", parent_span_id: "root", name: "tool.check_refund_policy", span_type: "tool", start_offset_ms: 12001.5, duration_ms: 310, status: "ok",
      attributes: { "blackbox.agent.retry_count": 2, "blackbox.tool.args": JSON.stringify({ order_id: 42, amount: 59.9 }) },
      events: [
        { name: "retry", timestamp_ns: 1, attributes: { "retry.attempt": 1, "exception.type": "blackbox.agent.errors.ToolTimeoutError", "exception.message": "check_refund_policy timed out after 0.3s" } },
        { name: "retry", timestamp_ns: 2, attributes: { "retry.attempt": 2, "exception.type": "blackbox.agent.errors.ToolTimeoutError", "exception.message": "check_refund_policy timed out after 0.3s" } },
      ],
    }),
  ];

  it("marks the span in the waterfall and explains it in the inspector", async () => {
    const user = userEvent.setup();
    renderWith(fakeSource({ getSpans: vi.fn().mockResolvedValue(retried()), getRunEvaluation: vi.fn().mockResolvedValue(runEvaluation()) }), <RunDetailPage runId="run-aaaa1111" />);
    const row = await screen.findByRole("button", { name: /tool\.check_refund_policy/ });
    expect(within(row).getByText("retried ×2")).toBeInTheDocument();
    await user.click(row);
    const inspector = screen.getByRole("complementary", { name: "Span inspector" });
    expect(within(inspector).getByText("This call needed 2 retries before it went through")).toBeInTheDocument();
    expect(within(inspector).getAllByText(/after attempt/)).toHaveLength(2);
    expect(within(inspector).getAllByText("check_refund_policy timed out after 0.3s")).toHaveLength(2);
    expect(within(inspector).getByText("Retries").nextElementSibling).toHaveTextContent("2");
  });

  it("shows nothing about retries on a call that did not need any", async () => {
    renderWith(fakeSource(), <RunDetailPage runId="run-aaaa1111" />);
    await screen.findByRole("button", { name: /tool\.lookup_order/ });
    expect(screen.queryByText(/retried/)).toBeNull();
  });
});
