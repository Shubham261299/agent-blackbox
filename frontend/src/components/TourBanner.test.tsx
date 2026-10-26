import { act, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataSourceContext } from "../api/context";
import type { DataSource } from "../api/client";
import { demoSource } from "../test/demoSource";
import { fakeSource } from "../test/fakeSource";
import { TourBanner } from "./TourBanner";

const STOPS = [
  "#/runs/run-e92cfa5d",
  "#/evals/eval-lab",
  "#/compare/eval-lab/eval-res",
  "#/compare/eval-bench/eval-guided",
];

function renderBanner(hash: string, source: DataSource = demoSource()) {
  return render(
    <DataSourceContext.Provider value={source}>
      <TourBanner hash={hash} />
    </DataSourceContext.Provider>,
  );
}

/** Wait until the banner has had everything it needs (so that "nothing is shown" means it decided so, not that it is still loading). */
async function settled(source: DataSource) {
  if (source.kind === "demo") await waitFor(() => expect(source.compare).toHaveBeenCalled());
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

const hrefs = (banner: HTMLElement) => within(banner).getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")]);

describe("TourBanner", () => {
  it("says which stop this is and what to look at", async () => {
    renderBanner(`${STOPS[0]}?tour=1`);
    const banner = await screen.findByRole("complementary", { name: "Guided tour" });
    expect(banner).toHaveTextContent("Guided tour · Stop 1 of 4: A run that failed");
    expect(banner).toHaveTextContent("The list shows what the agent did, step by step");
  });

  it("goes back to the start from the first stop and on to the second", async () => {
    renderBanner(`${STOPS[0]}?tour=1`);
    const banner = await screen.findByRole("complementary");
    expect(hrefs(banner)).toEqual([
      ["Back to the start", "#/"],
      ["Next stop", `${STOPS[1]}?tour=2`],
      ["Leave the tour", STOPS[0]],
    ]);
  });

  it("goes back and forward between the middle stops", async () => {
    renderBanner(`${STOPS[2]}?tour=3`);
    const banner = await screen.findByRole("complementary");
    expect(banner).toHaveTextContent("Stop 3 of 4: A fix that worked");
    expect(hrefs(banner)).toEqual([
      ["Back", `${STOPS[1]}?tour=2`],
      ["Next stop", `${STOPS[3]}?tour=4`],
      ["Leave the tour", STOPS[2]],
    ]);
  });

  it("ends on the last stop with a way back to the front page", async () => {
    renderBanner(`${STOPS[3]}?tour=4`);
    const banner = await screen.findByRole("complementary");
    expect(hrefs(banner)).toEqual([
      ["Back", `${STOPS[2]}?tour=3`],
      ["Finish the tour", "#/"],
      ["Leave the tour", STOPS[3]],
    ]);
  });

  it("leaving the tour keeps the page and drops the banner", async () => {
    const { rerender } = renderBanner(`${STOPS[1]}?tour=2`);
    const leave = within(await screen.findByRole("complementary")).getByRole("link", { name: "Leave the tour" });
    expect(leave).toHaveAttribute("href", STOPS[1]);
    rerender(
      <DataSourceContext.Provider value={demoSource()}>
        <TourBanner hash={STOPS[1] as string} />
      </DataSourceContext.Provider>,
    );
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("stays out of the way for a visitor who did not come through the tour", async () => {
    const source = demoSource();
    renderBanner(STOPS[0] as string, source);
    await settled(source);
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("is not shown on a page the stop number does not belong to", async () => {
    const source = demoSource();
    renderBanner("#/runs/some-other-run?tour=1", source);
    await settled(source);
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("ignores a stop number that does not exist", async () => {
    const source = demoSource();
    renderBanner(`${STOPS[0]}?tour=0`, source);
    renderBanner(`${STOPS[0]}?tour=9`, source);
    await settled(source);
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("does nothing in the live app, which has no tour", async () => {
    const source = fakeSource();
    renderBanner(`${STOPS[0]}?tour=1`, source);
    await settled(source);
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
});
