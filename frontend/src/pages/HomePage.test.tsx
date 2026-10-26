import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { ApiUnreachableError } from "../api/client";
import { DataSourceContext } from "../api/context";
import { demoSource, MANIFEST } from "../test/demoSource";
import { fakeSource } from "../test/fakeSource";
import { HomePage } from "./HomePage";

function renderHome(source = demoSource()) {
  return render(
    <DataSourceContext.Provider value={source}>
      <HomePage />
    </DataSourceContext.Provider>,
  );
}

beforeEach(() => {
  window.location.hash = "";
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
});

describe("HomePage", () => {
  it("opens with one sentence that says what this is and what it is for", async () => {
    renderHome();
    const h1 = await screen.findByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent("AI agents can fail without anyone noticing. I built a flight recorder that shows where, and tests whether a fix really works.");
    expect(screen.getByText(/Nothing here is live/)).toBeInTheDocument();
  });

  it("offers three ways in, and each does what it says", async () => {
    const user = userEvent.setup();
    renderHome();
    const ways = await screen.findByRole("group", { name: "Choose how much to read" });
    await user.click(within(ways).getByRole("button", { name: /30 seconds/ }));
    expect(window.HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
    expect(within(ways).getByRole("link", { name: /3 minutes/ })).toHaveAttribute("href", "#/runs/run-e92cfa5d");
    expect(within(ways).getByRole("link", { name: /I.m an engineer/ })).toHaveAttribute("href", "#/evals");
  });

  it("shows what is in the demo, from the data", async () => {
    renderHome();
    const stats = await screen.findByLabelText("What is in this demo");
    expect(stats).toHaveTextContent("173 recorded runs");
    expect(stats).toHaveTextContent("11 sets of results");
  });

  it("explains the problem, what was built, and what was found, in that order", async () => {
    renderHome();
    await screen.findByRole("heading", { level: 1 });
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "The problem, in one minute",
      "What I built",
      "What I found",
      "The 25-second version",
      "How I made sure the numbers are honest",
      "What this cannot tell you",
      "Look inside",
    ]);
    expect(screen.getAllByRole("listitem").some((li) => li.textContent?.startsWith("1The agent"))).toBe(true);
  });

  it("shows the three results with big numbers from the stored comparisons and a link to each", async () => {
    renderHome();
    const section = (await screen.findByRole("heading", { name: "What I found" })).closest("section") as HTMLElement;
    const cards = within(section).getAllByRole("article");
    expect(cards).toHaveLength(3);
    expect(cards[1]).toHaveTextContent("3 of 4");
    expect(cards[2]).toHaveTextContent("Fixed 2, broke 5");
    expect(within(cards[0] as HTMLElement).getByRole("link", { name: "See the failed run" })).toHaveAttribute("href", "#/runs/run-e92cfa5d");
    expect(within(cards[1] as HTMLElement).getByRole("link")).toHaveAttribute("href", "#/compare/eval-lab/eval-res");
    expect(within(cards[2] as HTMLElement).getByRole("link")).toHaveAttribute("href", "#/compare/eval-bench/eval-guided");
  });

  it("shows the short tour with a description that says what it shows", async () => {
    renderHome();
    const img = await screen.findByRole("img", { name: /captioned walk through the demo/ });
    expect(img).toHaveAttribute("src", expect.stringMatching(/tour\.gif$/));
  });

  it("states the limits in plain sight, not in a footnote", async () => {
    renderHome();
    const box = (await screen.findByRole("heading", { name: "What this cannot tell you" })).closest(".callout") as HTMLElement;
    expect(box).toHaveTextContent("One small model, one laptop");
  });

  it("links the evidence: predictions, the hidden test, and the source", async () => {
    renderHome();
    const honest = (await screen.findByRole("heading", { name: /numbers are honest/ })).closest("section") as HTMLElement;
    expect(within(honest).getByRole("link", { name: "See that test" })).toHaveAttribute("href", "#/evals/eval-hold");
    expect(within(honest).getByRole("link", { name: "See the written predictions" })).toHaveAttribute("target", "_blank");
    expect(within(honest).getByText(/8 extra test cases hidden/)).toBeInTheDocument();
  });

  it("ends with a way into the guided tour and every page of the evidence", async () => {
    renderHome();
    const inside = (await screen.findByRole("heading", { name: "Look inside" })).closest("section") as HTMLElement;
    expect(within(inside).getAllByRole("listitem")).toHaveLength(4);
    expect(within(inside).getByRole("link", { name: "All runs" })).toHaveAttribute("href", "#/runs");
    expect(within(inside).getByRole("link", { name: "All results" })).toHaveAttribute("href", "#/evals");
    expect(within(inside).getByRole("link", { name: "Source code" })).toHaveAttribute("href", expect.stringContaining("github.com/Shubham261299/agent-blackbox"));
    expect(within(inside).getByRole("link", { name: "Source code" })).toHaveAttribute("target", "_blank"); // leaving the demo opens a new tab
  });

  it("still tells the story, without numbers, if a comparison cannot be loaded", async () => {
    renderHome(demoSource({ compare: vi.fn().mockRejectedValue(new ApiUnreachableError()) }));
    const section = (await screen.findByRole("heading", { name: "What I found" })).closest("section") as HTMLElement;
    expect(within(section).getAllByRole("article")).toHaveLength(1); // the failed run needs no comparison
  });

  it("says so, and offers no broken page, if the recorded data cannot be loaded", async () => {
    renderHome(demoSource({ demoInfo: vi.fn().mockRejectedValue(new ApiUnreachableError()) }));
    expect(await screen.findByRole("status")).toHaveTextContent("could not be loaded");
  });
});

describe("the front page in the app", () => {
  it("is where the demo opens, and the run list is one click away", async () => {
    render(<App source={demoSource()} />);
    expect(await screen.findByRole("heading", { level: 1, name: /flight recorder/ })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getAllByRole("link").map((l) => [l.textContent, l.getAttribute("href")])).toEqual([
      ["Overview", "#/"],
      ["Runs", "#/runs"],
      ["Evaluations", "#/evals"],
    ]);
    expect(within(nav).getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  });

  it("shows the run list at #/runs, with Runs marked as the current page", async () => {
    window.location.hash = "#/runs";
    render(<App source={demoSource()} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Runs" })).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");
  });

  it("leaves the live app as it was: it opens on the run list, with no Overview", async () => {
    render(<App source={fakeSource()} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Runs" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).queryByRole("link", { name: "Overview" })).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Runs" })).toHaveAttribute("href", "#/");
    expect(MANIFEST.counts.runs).toBeGreaterThan(0);
  });
});
