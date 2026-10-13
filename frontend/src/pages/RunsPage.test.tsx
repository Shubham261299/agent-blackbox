import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiUnreachableError } from "../api/client";
import { DataSourceContext } from "../api/context";
import type { DataSource } from "../api/client";
import { fakeSource } from "../test/fakeSource";
import { run } from "../test/factories";
import { RunsPage } from "./RunsPage";

function renderPage(source: DataSource) {
  return render(
    <DataSourceContext.Provider value={source}>
      <RunsPage />
    </DataSourceContext.Provider>,
  );
}

beforeEach(() => {
  window.location.hash = "";
});

describe("RunsPage", () => {
  it("lists runs with status, link, model and a summary", async () => {
    const source = fakeSource({
      listRuns: vi.fn().mockResolvedValue([
        run({ run_id: "run-ok", task: "Refund order 42" }),
        run({ run_id: "run-bad", task: "Refund order 43", status: "error", error: "boom", duration_ms: 5000, model: "ollama:qwen2.5:7b" }),
      ]),
    });
    renderPage(source);

    const link = await screen.findByRole("link", { name: "Refund order 42" });
    expect(link).toHaveAttribute("href", "#/runs/run-ok");
    const table = screen.getByRole("table");
    expect(within(table).getByText("Completed")).toBeInTheDocument();
    expect(within(table).getByText("Failed")).toBeInTheDocument();
    expect(within(table).getByText("qwen2.5:7b")).toBeInTheDocument();

    expect(screen.getByLabelText("Run summary")).toHaveTextContent(/Runs\s*2/);
    expect(screen.getByLabelText("Run summary")).toHaveTextContent(/Failed\s*1/);
  });

  it("filters by status", async () => {
    const user = userEvent.setup();
    renderPage(
      fakeSource({
        listRuns: vi.fn().mockResolvedValue([run({ run_id: "a", task: "Good one" }), run({ run_id: "b", task: "Bad one", status: "error" })]),
      }),
    );
    await screen.findByText("Good one");
    await user.click(screen.getByRole("radio", { name: /Failed/ }));
    expect(screen.queryByText("Good one")).not.toBeInTheDocument();
    expect(screen.getByText("Bad one")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Running/ }));
    expect(screen.getByText(/No running runs/)).toBeInTheDocument();
  });

  it("shows how to start the API when it cannot be reached", async () => {
    renderPage(fakeSource({ listRuns: vi.fn().mockRejectedValue(new ApiUnreachableError()) }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The API is not running");
    expect(screen.getByText(/uvicorn --app-dir backend/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry now" })).toBeInTheDocument();
  });

  it("explains an empty database", async () => {
    renderPage(fakeSource({ listRuns: vi.fn().mockResolvedValue([]) }));
    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
  });

  it("starts the chosen scripted scenario with its matching task, then opens the run", async () => {
    const user = userEvent.setup();
    const source = fakeSource();
    renderPage(source);
    await screen.findByRole("option", { name: "unknown order" });

    await user.selectOptions(screen.getByLabelText("Scenario"), "unknown_order");
    expect(screen.getByText(/Where is order 999\?/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run agent" }));

    expect(source.startRun).toHaveBeenCalledWith({ task: "Where is order 999?", model: "scripted", scenario: "unknown_order" });
    expect(window.location.hash).toBe("#/runs/run-new");
  });

  it("sends a free-text request to the local model", async () => {
    const user = userEvent.setup();
    const source = fakeSource();
    renderPage(source);
    await screen.findByRole("option", { name: "unknown order" });

    await user.click(screen.getByRole("radio", { name: "Local model (Ollama)" }));
    const input = screen.getByLabelText("Customer request");
    await user.clear(input);
    await user.type(input, "Refund order 44");
    await user.click(screen.getByRole("button", { name: "Run agent" }));

    expect(source.startRun).toHaveBeenCalledWith({ task: "Refund order 44", model: "ollama" });
  });

  it("shows the reason when a run cannot be started", async () => {
    const user = userEvent.setup();
    renderPage(fakeSource({ startRun: vi.fn().mockRejectedValue(new Error("unknown scenario 'x'")) }));
    await screen.findByRole("option", { name: "unknown order" });
    await user.click(screen.getByRole("button", { name: "Run agent" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("unknown scenario 'x'");
  });

  it("hides the start panel for read-only (demo) sources", async () => {
    renderPage(fakeSource({ canStartRuns: false, kind: "demo" }));
    await screen.findByRole("table");
    expect(screen.queryByText("Start a run")).not.toBeInTheDocument();
  });
});
