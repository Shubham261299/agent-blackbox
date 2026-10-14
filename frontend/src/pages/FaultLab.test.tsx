import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DataSource } from "../api/client";
import { DataSourceContext } from "../api/context";
import { EFFECT_LABEL, EFFECT_TEXT, labNote, validationNote, verdictText } from "../lib/notes";
import { JUDGED_METRICS, KIND_LABEL, kindNote } from "../lib/metrics";
import { caseResult, faultLabCase, faultLabNote, faultLabReport } from "../test/factories";
import { fakeSource } from "../test/fakeSource";
import { EvalReportPage } from "./EvalReportPage";
import { EvalsPage } from "./EvalsPage";

function renderWith(source: DataSource, node: React.ReactNode) {
  return render(<DataSourceContext.Provider value={source}>{node}</DataSourceContext.Provider>);
}

const labSource = () => fakeSource({ getEval: vi.fn().mockResolvedValue(faultLabReport()) });

describe("failure lab report", () => {
  it("leads with how many faults were located, and says what that does and does not show", async () => {
    renderWith(labSource(), <EvalReportPage evalId="eval-lab" />);
    const result = await screen.findByRole("region", { name: "Result" });
    expect(result).toHaveTextContent("1 of 2");
    expect(result).toHaveTextContent("faults located at the right span");
    expect(result).toHaveTextContent("without being told what was planted");
    expect(result).toHaveTextContent("a demonstration, not a benchmark");
    expect(screen.getByText("Failure lab")).toBeInTheDocument(); // the kind pill
  });

  it("shows one card per fault with what was planted, the effect, and control against faulted", async () => {
    renderWith(labSource(), <EvalReportPage evalId="eval-lab" />);
    const silent = await screen.findByRole("article", { name: "Malformed tool output" });
    expect(within(silent).getByText("Planted: malformed_output on lookup_order call 1")).toBeInTheDocument();
    expect(within(silent).getByText("Silent")).toBeInTheDocument();
    expect(within(silent).getByText(EFFECT_TEXT.silent)).toBeInTheDocument();
    const compare = within(silent).getByRole("table", { name: "Control run against the run with the fault" });
    const failedRow = within(compare).getByText("Checks that failed").closest("tr") as HTMLElement;
    expect(failedRow).toHaveTextContent("none");
    expect(failedRow).toHaveTextContent("Tool output contract");

    const loud = screen.getByRole("article", { name: "Tool timeout" });
    expect(within(loud).getByText("Run failed")).toBeInTheDocument();
    const runRow = within(loud).getByText("Run").closest("tr") as HTMLElement;
    expect(runRow).toHaveTextContent("Completed");
    expect(runRow).toHaveTextContent("Failed");
  });

  it("lists the ranked suspects, marks the planted span, and states the verdict", async () => {
    renderWith(labSource(), <EvalReportPage evalId="eval-lab" />);
    const hit = await screen.findByRole("article", { name: "Malformed tool output" });
    const items = within(hit).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("tool.lookup_order");
    expect(items[0]).toHaveTextContent("tool output contract");
    expect(items[0]).toHaveTextContent("planted here");
    expect(items[1]).not.toHaveTextContent("planted here");
    expect(within(hit).getByText("The top suspect is the span the fault was planted in.")).toBeInTheDocument();

    const miss = screen.getByRole("article", { name: "Tool timeout" });
    expect(within(miss).getByText("The planted span ranked number 2, not first.")).toBeInTheDocument();
    expect(within(miss).getAllByRole("listitem")[1]).toHaveTextContent("planted here"); // the planted span is second
  });

  it("links to the run with the fault and to the control run", async () => {
    renderWith(labSource(), <EvalReportPage evalId="eval-lab" />);
    const card = await screen.findByRole("article", { name: "Malformed tool output" });
    expect(within(card).getByRole("link", { name: "Open the run with the fault" })).toHaveAttribute("href", "#/runs/run-faulted");
    expect(within(card).getByRole("link", { name: "Open the control run" })).toHaveAttribute("href", "#/runs/run-control");
  });

  it("does not show the pass-rate tables meant for benchmarks", async () => {
    renderWith(labSource(), <EvalReportPage evalId="eval-lab" />);
    await screen.findByRole("region", { name: "Result" });
    expect(screen.queryByRole("heading", { name: "By check" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Results per case and check" })).not.toBeInTheDocument();
  });

  it("can be started from the evaluations page", async () => {
    const user = userEvent.setup();
    const source = fakeSource();
    renderWith(source, <EvalsPage />);
    await user.click(await screen.findByRole("button", { name: /Run failure lab/ }));
    expect(source.startEval).toHaveBeenCalledWith("faultlab");
  });
});

describe("note helpers", () => {
  it("narrows a case's note to the kind it holds", () => {
    const lab = faultLabCase();
    expect(labNote(lab)?.fault).toBe("malformed_output");
    expect(validationNote(lab)).toBeNull();
    const validation = caseResult({ note: { fault: "x", expected_fail: ["a"], matched: true } });
    expect(validationNote(validation)?.matched).toBe(true);
    expect(labNote(validation)).toBeNull();
    expect(labNote(caseResult({ note: null }))).toBeNull();
  });

  it("describes every effect and every verdict in words", () => {
    expect(Object.keys(EFFECT_LABEL)).toEqual(Object.keys(EFFECT_TEXT));
    expect(verdictText(faultLabNote())).toContain("top suspect is the span");
    expect(verdictText(faultLabNote({ rank: 3, hit_at_1: false }))).toBe("The planted span ranked number 3, not first.");
    expect(verdictText(faultLabNote({ rank: null, hit_at_1: false }))).toBe("The planted span was not among the suspects.");
    expect(verdictText(faultLabNote({ fired: false, rank: null }))).toContain("never fired");
  });

  it("knows about the new check and the new kind", () => {
    expect(JUDGED_METRICS).toContain("tool_output_contract");
    expect(KIND_LABEL.faultlab).toBe("Failure lab");
    expect(kindNote({ kind: "faultlab", model: "m", n_cases: 4, seed: null })).toContain("not a benchmark");
  });
});
