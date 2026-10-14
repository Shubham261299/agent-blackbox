import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { DataSource } from "../api/client";
import { DataSourceContext } from "../api/context";
import { fakeSource } from "../test/fakeSource";
import { happyPathSpans, run, runEvaluation, span, withFailures } from "../test/factories";
import { RunDetailPage, defaultSelection } from "./RunDetailPage";

function renderPage(source: DataSource, runId = "run-aaaa1111") {
  return render(
    <DataSourceContext.Provider value={source}>
      <RunDetailPage runId={runId} />
    </DataSourceContext.Provider>,
  );
}

const inspector = () => screen.getByRole("complementary", { name: "Span inspector" });

describe("defaultSelection", () => {
  it("prefers the innermost failed span, then any failed span, then the root", () => {
    const spans = [
      span({ span_id: "root", name: "agent.run", status: "error" }),
      span({ span_id: "m", parent_span_id: "root", name: "model.call", status: "error", start_offset_ms: 1 }),
    ];
    expect(defaultSelection(spans)).toBe("m");
    expect(defaultSelection([span({ span_id: "root", name: "agent.run", status: "error" })])).toBe("root");
    expect(defaultSelection(happyPathSpans())).toBe("root");
    expect(defaultSelection([])).toBeNull();
  });

  it("prefers the span a failed gating check points at, then a failed reported check, over a plain failed span", () => {
    const spans = [
      span({ span_id: "root", name: "agent.run" }),
      span({ span_id: "t1", parent_span_id: "root", name: "tool.a", start_offset_ms: 1, status: "error" }),
      span({ span_id: "t2", parent_span_id: "root", name: "tool.b", start_offset_ms: 2 }),
      span({ span_id: "t3", parent_span_id: "root", name: "tool.c", start_offset_ms: 3 }),
    ];
    const soft = runEvaluation({ checks: withFailures({ tool_correctness: { span_ids: ["t3"] } }) });
    expect(defaultSelection(spans, soft)).toBe("t3");
    const both = runEvaluation({ checks: withFailures({ tool_correctness: { span_ids: ["t3"] }, policy_compliance: { gating: true, span_ids: ["t2"] } }) });
    expect(defaultSelection(spans, both)).toBe("t2");
    const unknownSpan = runEvaluation({ checks: withFailures({ policy_compliance: { gating: true, span_ids: ["gone"] } }) });
    expect(defaultSelection(spans, unknownSpan)).toBe("t1"); // a span id that is not in the trace is ignored
    expect(defaultSelection(spans, runEvaluation())).toBe("t1"); // nothing failed in the evaluation: the failed span wins
  });
});

describe("RunDetailPage", () => {
  it("shows the outcome, facts and one waterfall row per span", async () => {
    renderPage(fakeSource());
    expect(await screen.findByRole("heading", { level: 1, name: /arrived damaged/ })).toBeInTheDocument();
    // the banner label is a <strong>; the inspector has its own "Final answer" heading once the trace loads
    expect(screen.getByText("Final answer", { selector: "strong" })).toBeInTheDocument();
    const wf = await screen.findByRole("group", { name: "Trace waterfall" }); // spans load after the run
    for (const name of ["agent.run", "model.plan", "tool.lookup_order", "model.finalize"]) {
      expect(within(wf).getByText(name)).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: /Jaeger/ })).toHaveAttribute("href", expect.stringContaining("/trace/ab073c70"));
  });

  it("shows a tool's arguments and output, with redacted values as chips and a count", async () => {
    const user = userEvent.setup();
    renderPage(fakeSource());
    const wf = await screen.findByRole("group", { name: "Trace waterfall" });
    await user.click(within(wf).getByText("tool.lookup_order"));

    const panel = inspector();
    expect(within(panel).getByRole("heading", { level: 2, name: "tool.lookup_order" })).toBeInTheDocument();
    expect(within(panel).getByLabelText("Tool arguments")).toHaveTextContent('"order_id": 42');
    const chips = within(panel).getAllByText("[REDACTED]", { selector: "mark" });
    expect(chips.length).toBeGreaterThanOrEqual(2);
    expect(panel).toHaveTextContent(/sensitive values were removed/);
    expect(within(panel).getByText("Arguments")).toBeInTheDocument();
    expect(within(panel).getByText("Output")).toBeInTheDocument();
  });

  it("moves the selection with the arrow keys", async () => {
    const user = userEvent.setup();
    renderPage(fakeSource());
    const wf = await screen.findByRole("group", { name: "Trace waterfall" });
    const rows = within(wf).getAllByRole("button");
    expect(rows[0]).toHaveAttribute("aria-pressed", "true"); // healthy run opens on the root

    rows[0]?.focus();
    await user.keyboard("{ArrowDown}");
    expect(rows[1]).toHaveAttribute("aria-pressed", "true");
    expect(within(inspector()).getByRole("heading", { level: 2, name: "model.plan" })).toBeInTheDocument();
    await user.keyboard("{End}");
    expect(rows.at(-1)).toHaveAttribute("aria-pressed", "true");
    await user.keyboard("{Home}");
    expect(rows[0]).toHaveAttribute("aria-pressed", "true");
  });

  it("opens on the failed span and explains the failure", async () => {
    const spans = [
      span({ span_id: "root", name: "agent.run", span_type: "agent", duration_ms: 10, status: "error", status_message: "boom" }),
      span({
        span_id: "t", parent_span_id: "root", name: "tool.issue_refund", span_type: "tool", start_offset_ms: 1, duration_ms: 2,
        status: "error", status_message: "cannot refund order 45: status is shipped",
        events: [{ name: "exception", timestamp_ns: 0, attributes: { "exception.type": "ToolError", "exception.message": "cannot refund order 45" } }],
      }),
    ];
    renderPage(fakeSource({ getRun: vi.fn().mockResolvedValue(run({ status: "error", error: "ToolError: boom" })), getSpans: vi.fn().mockResolvedValue(spans) }));

    expect(await screen.findByText("Run failed")).toBeInTheDocument();
    const panel = await screen.findByRole("complementary", { name: "Span inspector" });
    expect(within(panel).getByRole("heading", { level: 2, name: "tool.issue_refund" })).toBeInTheDocument();
    expect(within(panel).getByText("This span failed")).toBeInTheDocument();
    expect(within(panel).getByText("ToolError")).toBeInTheDocument();
  });

  it("offers the same spans as a table", async () => {
    const user = userEvent.setup();
    renderPage(fakeSource());
    await screen.findByRole("group", { name: "Trace waterfall" });
    await user.click(screen.getByRole("radio", { name: "Table" }));
    const table = screen.getByRole("table", { name: /Spans of this run/ });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 4);
    expect(within(table).getByText("Share of run")).toBeInTheDocument();
  });

  it("says the trace is still being recorded while the run is running", async () => {
    const getSpans = vi.fn().mockResolvedValue([]);
    renderPage(fakeSource({ getRun: vi.fn().mockResolvedValue(run({ status: "running", duration_ms: null, final_answer: null })), getSpans }));
    expect(await screen.findByText("Recording this run…")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Trace waterfall" })).not.toBeInTheDocument();
    expect(getSpans).not.toHaveBeenCalled();
  });

  it("shows a loading state, never 'No spans recorded', while the trace is still loading", async () => {
    let resolveSpans!: (spans: ReturnType<typeof happyPathSpans>) => void;
    const pending = new Promise<ReturnType<typeof happyPathSpans>>((resolve) => (resolveSpans = resolve));
    renderPage(fakeSource({ getSpans: vi.fn().mockReturnValue(pending) }));

    expect(await screen.findByText("Loading trace…")).toBeInTheDocument();
    expect(screen.queryByText("No spans recorded")).not.toBeInTheDocument();

    resolveSpans(happyPathSpans());
    expect(await screen.findByRole("group", { name: "Trace waterfall" })).toBeInTheDocument();
    expect(screen.queryByText("No spans recorded")).not.toBeInTheDocument();
  });

  it("says so when a finished run really has no spans", async () => {
    renderPage(fakeSource({ getSpans: vi.fn().mockResolvedValue([]) }));
    expect(await screen.findByText("No spans recorded")).toBeInTheDocument();
  });

  it("shows the run's evaluation above the trace, failures first, and a path to the failing span", async () => {
    const user = userEvent.setup();
    const evaluation = runEvaluation({
      checks: withFailures({
        policy_compliance: { gating: true, reason: "refund on order 42 was not approved by a prior policy check", span_ids: ["t1"] },
      }),
    });
    renderPage(fakeSource({ getRunEvaluation: vi.fn().mockResolvedValue(evaluation) }));

    const card = await screen.findByRole("region", { name: "Evaluation" });
    expect(card).toHaveTextContent("Case N1 in eval-bench");
    expect(card).toHaveTextContent("1 failed, 1 of them gating");
    const rows = within(card).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Policy compliance"); // the failure is listed first
    expect(rows[0]).toHaveTextContent("gates the run");

    // the page opens on the span the failed gating check points at, with the finding already shown
    const panel = await screen.findByRole("complementary", { name: "Span inspector" });
    expect(within(panel).getByRole("heading", { level: 2, name: "tool.lookup_order" })).toBeInTheDocument();
    expect(within(panel).getByRole("region", { name: "Evaluation findings" })).toHaveTextContent("not approved by a prior policy check");

    // move elsewhere: the finding belongs to that one span only
    const wf = screen.getByRole("group", { name: "Trace waterfall" });
    await user.click(within(wf).getByText("agent.run"));
    expect(within(panel).queryByRole("region", { name: "Evaluation findings" })).not.toBeInTheDocument();

    // and "Show span" takes you back to the evidence
    await user.click(within(card).getByRole("button", { name: "Show span" }));
    expect(within(panel).getByRole("heading", { level: 2, name: "tool.lookup_order" })).toBeInTheDocument();
    expect(within(panel).getByRole("region", { name: "Evaluation findings" })).toBeInTheDocument();
  });

  it("does not show findings on spans the failed checks do not point at", async () => {
    const user = userEvent.setup();
    const evaluation = runEvaluation({ checks: withFailures({ policy_compliance: { gating: true, reason: "x", span_ids: ["t1"] } }) });
    renderPage(fakeSource({ getRunEvaluation: vi.fn().mockResolvedValue(evaluation) }));
    const panel = await screen.findByRole("complementary", { name: "Span inspector" });
    const wf = screen.getByRole("group", { name: "Trace waterfall" });
    await user.click(within(wf).getByText("model.finalize")); // a span no failed check points at
    expect(within(panel).getByRole("heading", { level: 2, name: "model.finalize" })).toBeInTheDocument();
    expect(within(panel).queryByRole("region", { name: "Evaluation findings" })).not.toBeInTheDocument();
  });

  it("says when a run is not part of an evaluation", async () => {
    renderPage(fakeSource({ getRunEvaluation: vi.fn().mockResolvedValue(runEvaluation({ stored: false, eval_id: null, case_id: null })) }));
    const card = await screen.findByRole("region", { name: "Evaluation" });
    expect(card).toHaveTextContent("not part of an evaluation");
    expect(card).toHaveTextContent("Nothing failed.");
  });

  it("still shows the trace when the evaluation cannot be loaded", async () => {
    renderPage(fakeSource({ getRunEvaluation: vi.fn().mockRejectedValue(new ApiError("boom", 500)) }));
    expect(await screen.findByRole("group", { name: "Trace waterfall" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Evaluation" })).not.toBeInTheDocument();
  });

  it("handles an unknown run id", async () => {
    renderPage(fakeSource({ getRun: vi.fn().mockRejectedValue(new ApiError("run not found", 404)) }), "nope");
    expect(await screen.findByText("Run not found")).toBeInTheDocument();
  });
});
