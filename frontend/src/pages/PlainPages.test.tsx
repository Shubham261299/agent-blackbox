import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type DataSource } from "../api/client";
import { DataSourceContext } from "../api/context";
import { PlainLead, Technical } from "../components/Plain";
import { effectLabel, effectText, verdictText } from "../lib/notes";
import { faultLabNote } from "../test/factories";
import { VariantChip } from "../components/VariantChip";
import { setPlainWords } from "../lib/plain";
import { check, comparison, evalReport, faultLabReport, run, runEvaluation, runFault, span, suspect, withFailures } from "../test/factories";
import { fakeSource } from "../test/fakeSource";
import { ComparePage } from "./ComparePage";
import { EvalReportPage } from "./EvalReportPage";
import { EvalsPage } from "./EvalsPage";
import { RunDetailPage } from "./RunDetailPage";
import { RunsPage } from "./RunsPage";

const page = (source: DataSource, ui: React.ReactNode) => render(<DataSourceContext.Provider value={source}>{ui}</DataSourceContext.Provider>);

const failedSpans = () => [
  span({ span_id: "root", name: "agent.run", span_type: "agent", status: "error" }),
  span({ span_id: "m1", parent_span_id: "root", name: "model.plan", span_type: "llm", duration_ms: 2000 }),
  span({ span_id: "t1", parent_span_id: "root", name: "tool.lookup_order", span_type: "tool", status: "ok", attributes: { "blackbox.tool.args": JSON.stringify({ order_id: 42 }) } }),
  span({ span_id: "t2", parent_span_id: "root", name: "tool.check_refund_policy", span_type: "tool", status: "error", status_message: "ToolTimeoutError: check_refund_policy timed out after 0.3s", duration_ms: 301,
    attributes: { "blackbox.tool.args": JSON.stringify({ order_id: 42 }) } }),
];

const failedRun = () => run({ run_id: "run-x", status: "error", error: "ToolTimeoutError: check_refund_policy timed out after 0.3s", final_answer: null });
const failedEvaluation = () =>
  runEvaluation({ checks: withFailures({ task_completion: { reason: "the run failed" } }), suspects: [suspect({ span_id: "t2", span_name: "tool.check_refund_policy" })] });

function runSource(over: Partial<DataSource> = {}) {
  return fakeSource({
    kind: "demo",
    getRun: vi.fn().mockResolvedValue(failedRun()),
    getSpans: vi.fn().mockResolvedValue(failedSpans()),
    getRunEvaluation: vi.fn().mockResolvedValue(failedEvaluation()),
    getRunFaults: vi.fn().mockResolvedValue([]),
    ...over,
  });
}

beforeEach(() => {
  window.location.hash = "";
});
afterEach(() => setPlainWords(false));

describe("the plain-words components", () => {
  it("show the lead box and the folded details in the demo", () => {
    setPlainWords(true);
    render(
      <>
        <PlainLead>Say it simply.</PlainLead>
        <Technical title="Show the machinery">
          <p>gears</p>
        </Technical>
      </>,
    );
    expect(screen.getByLabelText("In plain words")).toHaveTextContent("Say it simply.");
    const details = screen.getByText("Show the machinery").closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(within(details).getByText("gears")).toBeInTheDocument(); // folded, not removed
  });

  it("show nothing extra in the live app: no lead, the details just appear", () => {
    render(
      <>
        <PlainLead>Say it simply.</PlainLead>
        <Technical title="Show the machinery">
          <p>gears</p>
        </Technical>
      </>,
    );
    expect(screen.queryByLabelText("In plain words")).not.toBeInTheDocument();
    expect(screen.queryByText("Show the machinery")).not.toBeInTheDocument();
    expect(screen.getByText("gears").closest("details")).toBeNull();
  });
});

describe("a run in the demo", () => {
  it("tells what the agent did step by step, what the checks said and where to look", async () => {
    setPlainWords(true);
    page(runSource(), <RunDetailPage runId="run-x" />);
    expect(await screen.findByLabelText("In plain words")).toHaveTextContent("The run stopped with an error after 3 steps. Step 3 is where it failed.");
    const steps = within(screen.getByRole("list", { name: "Steps" })).getAllByRole("listitem");
    expect(steps.map((li) => li.textContent)).toEqual([
      expect.stringContaining("Asked the AI model what to do"),
      expect.stringContaining("Looked up order 42"),
      expect.stringContaining("Checked the refund policy for order 42"),
    ]);
    expect(steps[2]).toHaveTextContent("This step failed. It reported: The refund policy check did not answer within 0.3 seconds.");
    const verdicts = screen.getByRole("list", { name: "What the checks said" });
    expect(verdicts).toHaveTextContent("Finished the job: No");
    expect(verdicts).toHaveTextContent("Followed the rules: Yes");
    const story = screen.getByRole("heading", { name: "What the agent did, step by step" }).closest("section") as HTMLElement;
    expect(within(story).getByText(/Where to look first:/).parentElement).toHaveTextContent("Step 3: Checked the refund policy for order 42");
  });

  it("folds the checks and the full trace away, closed, but keeps them one click away", async () => {
    setPlainWords(true);
    const user = userEvent.setup();
    page(runSource(), <RunDetailPage runId="run-x" />);
    const summary = await screen.findByText("Show technical details: the checks and the full trace");
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(within(details).getByRole("heading", { name: "Trace" })).toBeInTheDocument();
    expect(within(details).getByRole("heading", { name: "Evaluation" })).toBeInTheDocument();
    await user.click(summary);
    expect(details.open).toBe(true);
  });

  it("uses the everyday names of the checks, and leaves the technical trace id out of the facts", async () => {
    setPlainWords(true);
    page(runSource(), <RunDetailPage runId="run-x" />);
    await screen.findByLabelText("In plain words");
    expect(screen.queryByText("Trace", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Finished the job").length).toBeGreaterThan(0);
    expect(screen.queryByText("Task completion")).not.toBeInTheDocument();
  });

  it("explains a planted problem without the word trace and without a button into a folded section", async () => {
    setPlainWords(true);
    page(runSource({ getRunFaults: vi.fn().mockResolvedValue([runFault({ origin_span_id: "t2" })]) }), <RunDetailPage runId="run-x" />);
    expect(await screen.findByText("Failure lab: a problem was planted in this run")).toBeInTheDocument();
    expect(screen.getByText("This is recorded separately, so the analysis is not told about it.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show the planted span" })).not.toBeInTheDocument();
  });

  it("is unchanged in the live app: technical words, the trace in the open, the trace id, no plain story", async () => {
    page(runSource({ kind: "live" }), <RunDetailPage runId="run-x" />);
    expect(await screen.findByRole("heading", { name: "Trace" })).toBeInTheDocument();
    expect(screen.queryByLabelText("In plain words")).not.toBeInTheDocument();
    expect(document.querySelector("details.technical")).toBeNull();
    expect(screen.getByText("Trace", { selector: "dt" })).toBeInTheDocument();
    expect(screen.getAllByText("Task completion").length).toBeGreaterThan(0);
  });

  it("keeps the planted-span button in the live app", async () => {
    page(runSource({ kind: "live", getRunFaults: vi.fn().mockResolvedValue([runFault({ origin_span_id: "t2" })]) }), <RunDetailPage runId="run-x" />);
    expect(await screen.findByRole("button", { name: "Show the planted span" })).toBeInTheDocument();
    expect(screen.getByText("Failure lab: a fault was planted in this run")).toBeInTheDocument();
  });
});

describe("the run list in the demo", () => {
  const runs = [
    run({ run_id: "run-scripted", task: "Scripted one", model: "scripted:reference:N1" }),
    run({ run_id: "run-real", task: "Real one", model: "ollama:qwen2.5:7b" }),
    run({ run_id: "run-bad", task: "Failed one", model: "ollama:qwen2.5:7b", status: "error", error: "boom" }),
  ];

  it("explains itself, lists failed runs first, and calls a scripted run what it is", async () => {
    setPlainWords(true);
    page(fakeSource({ kind: "demo", canStartRuns: false, listRuns: vi.fn().mockResolvedValue(runs) }), <RunsPage />);
    expect(await screen.findByLabelText("In plain words")).toHaveTextContent("one conversation between a customer and the AI agent");
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getByRole("link").textContent)).toEqual(["Failed one", "Real one", "Scripted one"]);
    expect(rows[2]).toHaveTextContent("Scripted example");
    expect(rows[1]).toHaveTextContent("qwen2.5:7b");
    expect(screen.queryByText(/its trace, timing and errors/)).not.toBeInTheDocument();
  });

  it("keeps the order the runs came in, and the technical lede, in the live app", async () => {
    page(fakeSource({ listRuns: vi.fn().mockResolvedValue(runs) }), <RunsPage />);
    await screen.findByRole("table");
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getByRole("link").textContent)).toEqual(["Scripted one", "Real one", "Failed one"]);
    expect(screen.getByText(/its trace, timing and errors/)).toBeInTheDocument();
    expect(screen.queryByLabelText("In plain words")).not.toBeInTheDocument();
  });
});

describe("the results list in the demo", () => {
  const evals = [evalReport({ eval_id: "eval-1", model: "scripted:reference", kind: "reference", n_cases: 24, n_passed: 24 }), evalReport({ eval_id: "eval-2", kind: "benchmark", n_cases: 24 })];

  it("is titled Results, explains itself, and describes each row in everyday words", async () => {
    setPlainWords(true);
    page(fakeSource({ kind: "demo", canStartEvals: false, listEvals: vi.fn().mockResolvedValue(evals) }), <EvalsPage />);
    expect(await screen.findByRole("heading", { level: 1, name: "Results" })).toBeInTheDocument();
    expect(screen.getByLabelText("In plain words")).toHaveTextContent("one version of the agent");
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "What was tested" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Test set" })).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "Sanity check" })).toBeInTheDocument();
    expect(within(table).getByRole("link", { name: "Measured run" })).toBeInTheDocument();
    expect(within(table).getAllByText("24 test cases")).toHaveLength(2);
    expect(within(table).getByText("Scripted (no AI model)")).toBeInTheDocument();
    expect(within(table).queryByText(/golden-v2/)).not.toBeInTheDocument();
  });

  it("keeps the technical table in the live app", async () => {
    page(fakeSource({ listEvals: vi.fn().mockResolvedValue(evals) }), <EvalsPage />);
    expect(await screen.findByRole("heading", { level: 1, name: "Evaluations" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Dataset" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reference run" })).toBeInTheDocument();
  });
});

describe("one set of results in the demo", () => {
  it("opens on what the number means, hides the identifiers, and folds the tables", async () => {
    setPlainWords(true);
    page(fakeSource({ kind: "demo", getEval: vi.fn().mockResolvedValue(evalReport()) }), <EvalReportPage evalId="eval-bench" />);
    expect(await screen.findByLabelText("In plain words")).toHaveTextContent("tried on 3 test cases");
    expect(screen.getByRole("link", { name: "All results" })).toHaveAttribute("href", "#/evals");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("qwen2.5:7b");
    expect(screen.getByRole("heading", { level: 1 })).not.toHaveTextContent("ollama");
    expect(screen.getByText(/test cases passed: the agent finished the job and followed the rules/)).toBeInTheDocument();
    expect(screen.queryByText("Seed", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.queryByText("Dataset", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.getByText(/Identifiers: eval-bench · test set golden-v2 \(abc123def456\) · seed 0/)).toBeInTheDocument();
    const folds = [...document.querySelectorAll("details.technical")] as HTMLDetailsElement[];
    expect(folds).toHaveLength(2);
    expect(folds.every((d) => !d.open)).toBe(true);
    expect(within(folds[0] as HTMLElement).getByRole("heading", { name: "By check" })).toBeInTheDocument();
    expect(within(folds[1] as HTMLElement).getByRole("heading", { name: "Every case, every check" })).toBeInTheDocument();
  });

  it("keeps the technical header and tables open in the live app", async () => {
    page(fakeSource({ getEval: vi.fn().mockResolvedValue(evalReport()) }), <EvalReportPage evalId="eval-bench" />);
    expect(await screen.findByText("Seed", { selector: "dt" })).toBeInTheDocument();
    expect(screen.getByText("Dataset", { selector: "dt" })).toBeInTheDocument();
    expect(document.querySelector("details.technical")).toBeNull();
    expect(screen.queryByLabelText("In plain words")).not.toBeInTheDocument();
  });

  it("explains the failure lab in its own words", async () => {
    setPlainWords(true);
    page(fakeSource({ kind: "demo", getEval: vi.fn().mockResolvedValue(faultLabReport()) }), <EvalReportPage evalId="eval-lab" />);
    expect(await screen.findByLabelText("In plain words")).toHaveTextContent("This is the failure lab");
  });
});

describe("a before and after in the demo", () => {
  const compared = () => comparison({ matched: 24, fixed: 2, broken: 5 });

  it("explains the comparison first, speaks of agents by everyday names, and drops the dataset hash", async () => {
    setPlainWords(true);
    page(fakeSource({ kind: "demo", compare: vi.fn().mockResolvedValue(compared()) }), <ComparePage baselineId="eval-base" candidateId="eval-cand" />);
    expect(await screen.findByLabelText("In plain words")).toHaveTextContent("Fixed means a case used to fail and now passes.");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Original agent → New instructions (v2)");
    expect(screen.getByRole("link", { name: "Back to the results" })).toBeInTheDocument();
    expect(screen.queryByText("Dataset", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.getByText("Measured run", { selector: "dt" })).toBeInTheDocument();
    expect(screen.getByText(/Cases where the agent finished the job and followed the rules, before/)).toBeInTheDocument();
    expect(screen.getByText("Why it fails after")).toBeInTheDocument();
    expect(screen.getByText("Times a tool was used")).toBeInTheDocument();
  });

  it("explains how to read the page in everyday words, and says nothing was edited", async () => {
    setPlainWords(true);
    page(fakeSource({ kind: "demo", compare: vi.fn().mockResolvedValue(compared()) }), <ComparePage baselineId="eval-base" candidateId="eval-cand" />);
    const limits = (await screen.findByRole("heading", { name: "How to read this" })).closest("section") as HTMLElement;
    expect(limits).toHaveTextContent("Only test cases that both sides ran are counted");
    expect(limits).toHaveTextContent("One try per test case on one AI model, 24 compared.");
    expect(limits).toHaveTextContent("I never edited a result.");
    expect(limits).not.toHaveTextContent(/dataset|evaluation|re-judged/);
    expect(limits).toHaveTextContent("New instructions (v2): The agent was given a rewritten set of instructions");
  });

  it("folds the by-check and by-kind tables, but keeps the cases, the cost and the limits in view", async () => {
    setPlainWords(true);
    page(fakeSource({ kind: "demo", compare: vi.fn().mockResolvedValue(compared()) }), <ComparePage baselineId="eval-base" candidateId="eval-cand" />);
    await screen.findByLabelText("In plain words");
    const fold = document.querySelector("details.technical") as HTMLDetailsElement;
    expect(fold.open).toBe(false);
    expect(within(fold).getByRole("heading", { name: "By check" })).toBeInTheDocument();
    expect(within(fold).getByRole("heading", { name: "By kind of task" })).toBeInTheDocument();
    for (const name of ["Case by case", "What it cost", "How to read this"]) {
      expect(screen.getByRole("heading", { name }).closest("details")).toBeNull();
    }
  });

  it("leaves the live page as it was", async () => {
    page(fakeSource({ compare: vi.fn().mockResolvedValue(compared()) }), <ComparePage baselineId="eval-base" candidateId="eval-cand" />);
    expect(await screen.findByText("Dataset", { selector: "dt" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Baseline → Guided (v2)");
    expect(screen.getByRole("link", { name: "Back to the evaluation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How to read this" }).closest("section")).toHaveTextContent("dataset content and kind");
    expect(screen.queryByLabelText("In plain words")).not.toBeInTheDocument();
    expect(document.querySelector("details.technical")).toBeNull();
    expect(check({ metric: "latency" }).metric).toBe("latency");
  });
});

describe("the agent chip", () => {
  it("names the agent in everyday words, says what it does, and calls a re-judged result by that name in the demo", () => {
    setPlainWords(true);
    render(<VariantChip variant="resilient" rescoredFrom="eval-old" />);
    const chip = screen.getByText("Agent that retries").closest(".variant") as HTMLElement;
    expect(chip).toHaveAttribute("title", expect.stringContaining("tries again up to twice"));
    const rescored = screen.getByText("Re-judged");
    expect(rescored).toHaveAttribute("title", "These stored runs (from eval-old) were judged again against corrected rules. No AI model was run for this.");
    expect(screen.queryByText("Rescored")).not.toBeInTheDocument();
  });

  it("keeps the technical names and wording in the live app", () => {
    render(<VariantChip variant="resilient" rescoredFrom="eval-old" />);
    expect(screen.getByText("Resilient").closest(".variant")).toHaveAttribute("title", expect.stringContaining("rejects a tool answer that breaks its contract"));
    expect(screen.getByText("Rescored")).toHaveAttribute("title", expect.stringContaining("newer dataset version"));
  });
});

describe("the failure lab in the demo", () => {
  const lab = () => page(fakeSource({ kind: "demo", getEval: vi.fn().mockResolvedValue(faultLabReport()) }), <EvalReportPage evalId="eval-lab" />);

  it("says planted problem and step where it said fault and span, and keeps the technical span name out", async () => {
    setPlainWords(true);
    lab();
    const timeout = await screen.findByRole("article", { name: "A tool times out" });
    expect(screen.getByText("planted problems pointed at the right step")).toBeInTheDocument();
    expect(within(timeout).getByRole("heading", { name: "Where the analysis says to look" })).toBeInTheDocument();
    expect(within(timeout).getByRole("columnheader", { name: "With the problem" })).toBeInTheDocument();
    expect(within(timeout).getByText("Pass-or-fail rules")).toBeInTheDocument();
    expect(within(timeout).getByText("Times a tool was used")).toBeInTheDocument();
    expect(within(timeout).getAllByText("Checked the refund policy").length).toBeGreaterThan(0);
    expect(within(timeout).queryByText("tool.check_refund_policy")).not.toBeInTheDocument();
    expect(within(timeout).getAllByText(/it reported an error/).length).toBeGreaterThan(0);
    expect(within(timeout).getByText("The planted step was the analysis's number 2 suggestion, not the first.")).toBeInTheDocument();
    expect(within(timeout).getByRole("link", { name: "Open the run with the problem" })).toBeInTheDocument();
    expect(within(timeout).getByText("Run failed", { selector: ".pill" })).toBeInTheDocument();
  });

  it("explains a silent problem as one that went unnoticed", async () => {
    setPlainWords(true);
    lab();
    const silent = await screen.findByRole("article", { name: "A tool sends back garbage" });
    expect(within(silent).getByText("Went unnoticed", { selector: ".pill" })).toBeInTheDocument();
    expect(within(silent).getByText(/looked fine on both pass-or-fail rules/)).toBeInTheDocument();
    expect(within(silent).getByText(/its answer could not be used/)).toBeInTheDocument();
    expect(within(silent).getByText(/a rule was broken/)).toBeInTheDocument();
  });

  it("keeps the technical words in the live app", async () => {
    lab();
    const timeout = await screen.findByRole("article", { name: "Tool timeout" });
    expect(screen.getByText("faults located at the right span")).toBeInTheDocument();
    expect(within(timeout).getByRole("heading", { name: "Where trace analysis says to look" })).toBeInTheDocument();
    expect(within(timeout).getByText("Gating checks")).toBeInTheDocument();
    expect(within(timeout).getAllByText("tool.check_refund_policy").length).toBeGreaterThan(0);
    expect(within(timeout).getByRole("link", { name: "Open the run with the fault" })).toBeInTheDocument();
  });
});

describe("what a problem did, in each mode", () => {
  it("names and explains every effect in everyday words in the demo, and technically in the live app", () => {
    for (const e of ["run_failed", "gating_failed", "silent", "no_effect"] as const) {
      const technical = [effectLabel(e), effectText(e)];
      setPlainWords(true);
      const plain = [effectLabel(e), effectText(e)];
      setPlainWords(false);
      expect(plain[0]).toBeTruthy();
      expect(plain[1]).not.toMatch(/gating|span/);
      if (e === "gating_failed" || e === "silent") expect(plain).not.toEqual(technical);
    }
  });

  it("says in plain words whether the analysis found the planted step", () => {
    setPlainWords(true);
    expect(verdictText(faultLabNote({ rank: 1 }))).toBe("The analysis's first suggestion is the step where the problem was planted.");
    expect(verdictText(faultLabNote({ rank: 3, hit_at_1: false }))).toBe("The planted step was the analysis's number 3 suggestion, not the first.");
    expect(verdictText(faultLabNote({ rank: null, hit_at_1: false }))).toBe("The planted step was not among the analysis's suggestions.");
    expect(verdictText(faultLabNote({ fired: false, rank: null }))).toBe("The problem never happened, so there is nothing to find.");
  });
});

describe("errors and refusals in the demo", () => {
  it("says what went wrong in a failed run in everyday words, and shows the code's message in the live app", async () => {
    setPlainWords(true);
    page(runSource(), <RunDetailPage runId="run-x" />);
    const card = (await screen.findByText("Run failed")).closest("section") as HTMLElement;
    expect(card).toHaveTextContent("The refund policy check did not answer within 0.3 seconds.");
    expect(card).not.toHaveTextContent("ToolTimeoutError");
    cleanup();
    setPlainWords(false);
    page(runSource({ kind: "live" }), <RunDetailPage runId="run-x" />);
    expect((await screen.findByText("Run failed")).closest("section")).toHaveTextContent("ToolTimeoutError: check_refund_policy timed out after 0.3s");
  });

  it("explains the reason a step failed with the same words", async () => {
    setPlainWords(true);
    page(runSource(), <RunDetailPage runId="run-x" />);
    const steps = within(await screen.findByRole("list", { name: "Steps" })).getAllByRole("listitem");
    expect(steps[2]).toHaveTextContent("It reported: The refund policy check did not answer within 0.3 seconds.");
  });

  it("gives a refused pair's reason without hashes, and the demo's own words around it", async () => {
    setPlainWords(true);
    const refused = new ApiError("They ran different cases (golden-v3 82acd02d8a18 against holdout-v1 8c7eb9ea4eb0), so the difference could come from the test.", 422);
    page(fakeSource({ kind: "demo", compare: vi.fn().mockRejectedValue(refused) }), <ComparePage baselineId="eval-a" candidateId="eval-b" />);
    const box = (await screen.findByText("These two cannot be compared fairly")).closest("section") as HTMLElement;
    expect(box).toHaveTextContent("They were tested on different test cases");
    expect(box).toHaveTextContent("both sets of results used the same test cases and the same AI model");
    expect(within(box).getByRole("link", { name: "Open the first result" })).toHaveAttribute("href", "#/evals/eval-a");
    expect(box).not.toHaveTextContent(/82acd02d8a18|golden/);
  });

  it("keeps the API's wording for a refused pair in the live app", async () => {
    const refused = new ApiError("They ran different cases (golden-v3 82acd02d8a18 against holdout-v1 8c7eb9ea4eb0), so the difference could come from the test.", 422);
    page(fakeSource({ compare: vi.fn().mockRejectedValue(refused) }), <ComparePage baselineId="eval-a" candidateId="eval-b" />);
    const box = (await screen.findByText("These two cannot be compared fairly")).closest("section") as HTMLElement;
    expect(box).toHaveTextContent("golden-v3 82acd02d8a18");
    expect(within(box).getByRole("link", { name: "Open the first evaluation" })).toBeInTheDocument();
  });

  it("says a result was not found in the demo's words", async () => {
    setPlainWords(true);
    page(fakeSource({ kind: "demo", compare: vi.fn().mockRejectedValue(new ApiError("evaluation not found: eval-x", 404)) }), <ComparePage baselineId="eval-a" candidateId="eval-x" />);
    expect(await screen.findByRole("heading", { name: "Result not found" })).toBeInTheDocument();
  });

  it("and the compare picker speaks of results, not evaluations, in the demo only", async () => {
    setPlainWords(true);
    page(fakeSource({ kind: "demo", getEval: vi.fn().mockResolvedValue(evalReport()), listEvals: vi.fn().mockResolvedValue([evalReport(), evalReport({ eval_id: "eval-2" })]) }), <EvalReportPage evalId="eval-bench" />);
    expect(await screen.findByLabelText("Compare this result (as the “before”) with")).toBeInTheDocument();
    cleanup();
    setPlainWords(false);
    page(fakeSource({ getEval: vi.fn().mockResolvedValue(evalReport()), listEvals: vi.fn().mockResolvedValue([evalReport(), evalReport({ eval_id: "eval-2" })]) }), <EvalReportPage evalId="eval-bench" />);
    expect(await screen.findByLabelText("Compare this evaluation (as the “before”) with")).toBeInTheDocument();
  });
});

