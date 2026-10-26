import { describe, expect, it } from "vitest";
import { parseHash } from "../hooks/useHashRoute";
import { span } from "../test/factories";
import { JUDGED_METRICS, METRICS, kindNote, metricLabel, ratePercent } from "./metrics";
import { median, splitModel, timeAgo } from "./format";
import { countRedactions, parseMaybeJson, prettyJson, splitRedactions } from "./redaction";
import { buildRows, traceDurationMs } from "./spanTree";
import { barGeometry, formatDuration, formatOffset, formatTick, niceStep, niceTicks, unitFor } from "./timeScale";

describe("buildRows", () => {
  it("orders parents before children and siblings by start time, with depth", () => {
    const rows = buildRows([
      span({ span_id: "c2", parent_span_id: "root", name: "second", start_offset_ms: 5 }),
      span({ span_id: "root", name: "root" }),
      span({ span_id: "c1", parent_span_id: "root", name: "first", start_offset_ms: 1 }),
      span({ span_id: "g1", parent_span_id: "c1", name: "grandchild", start_offset_ms: 2 }),
    ]);
    expect(rows.map((r) => [r.span.name, r.depth, r.childCount])).toEqual([
      ["root", 0, 2],
      ["first", 1, 1],
      ["grandchild", 2, 0],
      ["second", 1, 0],
    ]);
  });

  it("shows a span whose parent is missing as a root instead of dropping it", () => {
    const rows = buildRows([span({ span_id: "a", name: "a" }), span({ span_id: "b", parent_span_id: "gone", name: "orphan", start_offset_ms: 1 })]);
    expect(rows.map((r) => [r.span.name, r.depth])).toEqual([["a", 0], ["orphan", 0]]);
  });

  it("handles an empty list", () => {
    expect(buildRows([])).toEqual([]);
    expect(traceDurationMs([])).toBe(0);
  });

  it("measures the trace as the furthest span end", () => {
    expect(traceDurationMs([span({ span_id: "a", name: "a", duration_ms: 10 }), span({ span_id: "b", name: "b", start_offset_ms: 8, duration_ms: 5 })])).toBe(13);
  });
});

describe("formatDuration", () => {
  it.each([
    [0.0004, "<1 µs"],
    [0.054, "54 µs"],
    [0.5, "500 µs"],
    [1.234, "1.23 ms"],
    [12.34, "12.3 ms"],
    [123.4, "123 ms"],
    [1500, "1.5 s"],
    [22212, "22.2 s"],
    [72_000, "1m 12s"],
  ])("%s ms -> %s", (ms, expected) => expect(formatDuration(ms)).toBe(expected));

  it("does not print NaN", () => expect(formatDuration(NaN)).toBe("–"));

  it("describes a span's offset, with the root at run start", () => {
    expect(formatOffset(0)).toBe("run start");
    expect(formatOffset(12.3)).toBe("+12.3 ms");
    expect(formatOffset(0.054)).toBe("+54 µs");
  });
});

describe("time axis", () => {
  it("picks one unit per axis from its maximum", () => {
    expect([unitFor(0.57), unitFor(42), unitFor(22212)]).toEqual(["us", "ms", "s"]);
  });

  it("uses 1-2-5 steps", () => {
    expect(niceStep(22212)).toBe(5000);
    expect(niceStep(0.57)).toBeCloseTo(0.2); // raw 0.114 rounds up to the next 1-2-5 step
    expect(niceTicks(0.57)).toEqual([0, 0.2, 0.4]);
    expect(niceStep(0)).toBe(1);
  });

  it("makes ticks from 0 that never pass the maximum", () => {
    const ticks = niceTicks(22212);
    expect(ticks).toEqual([0, 5000, 10000, 15000, 20000]);
    expect(niceTicks(0.57).at(-1)).toBeLessThanOrEqual(0.57);
    expect(niceTicks(0)).toEqual([0]);
  });

  it("labels ticks in the axis unit", () => {
    expect(formatTick(5000, "s")).toBe("5 s");
    expect(formatTick(0.1, "us")).toBe("100 µs");
    expect(formatTick(2.5, "ms")).toBe("2.5 ms");
  });

  it("positions bars as percentages and clamps them to the axis", () => {
    expect(barGeometry(0, 100, 100)).toEqual({ leftPct: 0, widthPct: 100 });
    expect(barGeometry(25, 50, 100)).toEqual({ leftPct: 25, widthPct: 50 });
    expect(barGeometry(90, 50, 100).widthPct).toBeCloseTo(10);
    expect(barGeometry(5, 5, 0)).toEqual({ leftPct: 0, widthPct: 100 });
  });
});

describe("redaction helpers", () => {
  it("splits text around redaction markers", () => {
    expect(splitRedactions('{"email":"[REDACTED]","note":"a [REDACTED_EMAIL] b"}')).toEqual([
      { text: '{"email":"', redacted: false },
      { text: "[REDACTED]", redacted: true },
      { text: '","note":"a ', redacted: false },
      { text: "[REDACTED_EMAIL]", redacted: true },
      { text: ' b"}', redacted: false },
    ]);
    expect(splitRedactions("nothing here")).toEqual([{ text: "nothing here", redacted: false }]);
  });

  it("counts markers through nested values", () => {
    expect(countRedactions({ a: "[REDACTED]", b: ["x [REDACTED_CARD]", { c: "[REDACTED]" }], d: 5 })).toBe(3);
    expect(countRedactions(null)).toBe(0);
  });

  it("parses JSON stored in strings but leaves plain text alone", () => {
    expect(parseMaybeJson('{"a":1}')).toEqual({ a: 1 });
    expect(parseMaybeJson("{broken")).toBe("{broken");
    expect(parseMaybeJson("hello")).toBe("hello");
    expect(prettyJson('{"a":1}')).toBe('{\n  "a": 1\n}');
  });
});

describe("format helpers", () => {
  it("describes elapsed time", () => {
    const now = Date.parse("2026-10-13T12:00:00Z");
    expect(timeAgo("2026-10-13T11:59:58Z", now)).toBe("just now");
    expect(timeAgo("2026-10-13T11:59:30Z", now)).toBe("30s ago");
    expect(timeAgo("2026-10-13T11:50:00Z", now)).toBe("10m ago");
    expect(timeAgo("2026-10-13T09:00:00Z", now)).toBe("3h ago");
  });

  it("computes medians", () => {
    expect(median([])).toBeNull();
    expect(median([3, 1, 2])).toBe(2);
    expect(median([1, 2, 3, 10])).toBe(2.5);
  });

  it("splits provider from model name, keeping colons in the name", () => {
    expect(splitModel("ollama:qwen2.5:7b")).toEqual({ provider: "ollama", name: "qwen2.5:7b" });
    expect(splitModel("plain")).toEqual({ provider: "", name: "plain" });
  });
});

describe("routes", () => {
  it("parses run, evaluation and default routes", () => {
    expect(parseHash("")).toEqual({ name: "home" });
    expect(parseHash("#/")).toEqual({ name: "home" });
    expect(parseHash("#/runs")).toEqual({ name: "runs" });
    expect(parseHash("#/runs/")).toEqual({ name: "runs" });
    expect(parseHash("#/nonsense")).toEqual({ name: "home" });
    expect(parseHash("#/runs/run-1")).toEqual({ name: "run", runId: "run-1" });
    expect(parseHash("#/evals")).toEqual({ name: "evals" });
    expect(parseHash("#/evals/")).toEqual({ name: "evals" });
    expect(parseHash("#/evals/eval-9")).toEqual({ name: "eval", evalId: "eval-9" });
  });
});

describe("metric helpers", () => {
  it("every judged metric has a label and a plain-language description", () => {
    for (const m of JUDGED_METRICS) expect(METRICS[m]?.label && METRICS[m]?.what).toBeTruthy();
    expect(metricLabel("policy_compliance")).toBe("Policy compliance");
    expect(metricLabel("something_new")).toBe("something new");
  });

  it("computes rates without dividing by zero", () => {
    expect(ratePercent(3, 4)).toBe(75);
    expect(ratePercent(0, 0)).toBe(0);
  });

  it("states what each kind of evaluation does and does not show", () => {
    const base = { model: "ollama:qwen2.5:7b", n_cases: 24, seed: 0 };
    expect(kindNote({ ...base, kind: "benchmark" })).toContain("one run per case (n=24)");
    expect(kindNote({ ...base, kind: "reference" })).toContain("says nothing about any model");
    expect(kindNote({ ...base, kind: "validation" })).toContain("reacted exactly as expected");
  });
});
