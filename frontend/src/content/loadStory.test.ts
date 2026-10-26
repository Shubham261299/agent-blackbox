import { describe, expect, it, vi } from "vitest";
import { ApiUnreachableError } from "../api/client";
import { demoSource } from "../test/demoSource";
import { fakeSource } from "../test/fakeSource";
import { loadDemoStory } from "./loadStory";

describe("loadDemoStory", () => {
  it("has nothing to say for the live app, and asks it for nothing", async () => {
    const live = fakeSource();
    await expect(loadDemoStory(live)).resolves.toBeNull();
    expect(live.listEvals).not.toHaveBeenCalled();
    expect(live.compare).not.toHaveBeenCalled();
  });

  it("returns the story and the tour stops from the recorded data", async () => {
    const result = await loadDemoStory(demoSource());
    expect(result?.story.found).toHaveLength(3);
    expect(result?.stops.map((s) => s.title)).toEqual(["A run that failed", "The failure lab", "A fix that worked", "A fix that did not"]);
  });

  it("asks for each comparison once", async () => {
    const source = demoSource();
    await loadDemoStory(source);
    expect(vi.mocked(source.compare).mock.calls.map((c) => c.join(">"))).toEqual(["eval-lab>eval-res", "eval-bench>eval-guided", "eval-bench>eval-guided3"]);
  });

  it("still returns the stops, without numbers, when a comparison cannot be loaded", async () => {
    const result = await loadDemoStory(demoSource({ compare: vi.fn().mockRejectedValue(new ApiUnreachableError()) }));
    expect(result?.story.found).toHaveLength(1);
    expect(result?.stops).toHaveLength(4);
  });

  it("fails when the recorded data itself cannot be read, so the page can say so", async () => {
    await expect(loadDemoStory(demoSource({ demoInfo: vi.fn().mockRejectedValue(new ApiUnreachableError()) }))).rejects.toBeInstanceOf(ApiUnreachableError);
  });
});
