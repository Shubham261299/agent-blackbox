import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { DataSource } from "../api/client";
import { DataSourceContext } from "../api/context";
import { fakeSource } from "../test/fakeSource";
import { happyPathSpans, run, span } from "../test/factories";
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

  it("handles an unknown run id", async () => {
    renderPage(fakeSource({ getRun: vi.fn().mockRejectedValue(new ApiError("run not found", 404)) }), "nope");
    expect(await screen.findByText("Run not found")).toBeInTheDocument();
  });
});
