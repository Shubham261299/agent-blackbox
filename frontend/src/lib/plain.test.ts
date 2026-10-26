import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { comparison } from "../test/factories";
import { PLAIN_VARIANT_INFO, VARIANT_INFO, costRows, variantInfo, variantLabel } from "./compare";
import { JUDGED_METRICS, KIND_LABEL, METRICS, PLAIN_KIND_LABEL, PLAIN_METRICS, kindLabel, kindNote, metricLabel, metricWhat } from "./metrics";
import { plainWords, setPlainWords } from "./plain";

afterEach(() => setPlainWords(false));

describe("the plain-words switch", () => {
  it("is off until something turns it on, so the live app keeps the technical words", () => {
    expect(plainWords()).toBe(false);
    expect(metricLabel("task_completion")).toBe("Task completion");
    expect(kindLabel("faultlab")).toBe("Failure lab");
    expect(variantLabel("baseline")).toBe("Baseline");
  });

  it("switches every vocabulary at once, and back", () => {
    setPlainWords(true);
    expect(metricLabel("task_completion")).toBe("Finished the job");
    expect(kindLabel("benchmark")).toBe("Measured run");
    expect(variantLabel("resilient")).toBe("Agent that retries");
    setPlainWords(false);
    expect(metricLabel("task_completion")).toBe("Task completion");
    expect(kindLabel("benchmark")).toBe("Benchmark");
    expect(variantLabel("resilient")).toBe("Resilient");
  });
});

describe("plain vocabularies cover everything the technical ones do", () => {
  it("has an everyday name and a sentence for every check", () => {
    expect(Object.keys(PLAIN_METRICS).sort()).toEqual(Object.keys(METRICS).sort());
    for (const m of [...JUDGED_METRICS, "latency"]) {
      expect(PLAIN_METRICS[m]?.label).toBeTruthy();
      expect(PLAIN_METRICS[m]?.what.length).toBeGreaterThan(20);
    }
  });

  it("has an everyday name for every kind of evaluation and every agent", () => {
    expect(Object.keys(PLAIN_KIND_LABEL).sort()).toEqual(Object.keys(KIND_LABEL).sort());
    expect(Object.keys(PLAIN_VARIANT_INFO).sort()).toEqual(Object.keys(VARIANT_INFO).sort());
  });

  it("never gives two things the same name, in either mode", () => {
    for (const table of [PLAIN_METRICS, METRICS]) expect(new Set(Object.values(table).map((m) => m.label)).size).toBe(Object.keys(table).length);
    for (const table of [PLAIN_VARIANT_INFO, VARIANT_INFO]) expect(new Set(Object.values(table).map((v) => v.label)).size).toBe(Object.keys(table).length);
  });

  it("describes what each check and each agent does in the words of the mode", () => {
    expect(metricWhat("policy_compliance")).toBe(METRICS.policy_compliance?.what);
    setPlainWords(true);
    expect(metricWhat("policy_compliance")).toBe(PLAIN_METRICS.policy_compliance?.what);
    expect(variantInfo("guided")?.what).toContain("rewritten set of instructions");
    expect(variantInfo("not-a-variant")).toBeUndefined();
    expect(variantLabel("not-a-variant")).toBe("not-a-variant"); // an unknown name is shown as it is
  });

  it("keeps the retries-and-instructions names distinguishable from the two things alone", () => {
    setPlainWords(true);
    expect(variantLabel("full")).toBe("Retries + new instructions (v2)");
    expect(variantLabel("full-v3")).toBe("Retries + new instructions (v3)");
    expect(variantLabel("guided")).not.toBe(variantLabel("full"));
  });
});

describe("what the demo says about each kind of evaluation", () => {
  const report = { model: "ollama:qwen2.5:7b", n_cases: 24, seed: 0 };

  it("explains a measured run with the model's name and the number of cases, and says one try is noisy", () => {
    setPlainWords(true);
    const note = kindNote({ ...report, kind: "benchmark" });
    expect(note).toContain("24 test cases");
    expect(note).toContain("qwen2.5:7b");
    expect(note).toContain("just noise");
    expect(note).not.toMatch(/seed|ollama:/);
  });

  it("says a scripted run proves the pipeline and nothing about a model", () => {
    setPlainWords(true);
    expect(kindNote({ ...report, kind: "reference" })).toContain("says nothing about any AI model");
  });

  it("states that four problems on one task is a demonstration", () => {
    setPlainWords(true);
    expect(kindNote({ ...report, kind: "faultlab" })).toContain("a demonstration, not a benchmark");
  });

  it("describes the checker test as catching the right problems and nothing else", () => {
    setPlainWords(true);
    expect(kindNote({ ...report, kind: "validation" })).toContain("flagged nothing else");
  });

  it("keeps the technical wording for the live app", () => {
    expect(kindNote({ ...report, kind: "benchmark" })).toContain("seed 0");
  });
});

describe("cost labels", () => {
  const rows = () => costRows(comparison().baseline_cost, comparison().candidate_cost).map((r) => r.label);

  it("name what was counted in everyday words in the demo", () => {
    setPlainWords(true);
    expect(rows()).toEqual(expect.arrayContaining(["Times a tool was used", "Times the AI model was asked", "Retries", "Text sent to the AI model (tokens)", "Text the AI model wrote (tokens)"]));
  });

  it("keep the technical names in the live app", () => {
    expect(rows()).toEqual(expect.arrayContaining(["Tool calls", "Model calls", "Prompt tokens", "Reply tokens"]));
  });
});

describe("start-up", () => {
  it("turns the plain words on for the recorded demo and only for it", () => {
    const main = readFileSync(join(process.cwd(), "src", "main.tsx"), "utf-8");
    expect(main).toContain('setPlainWords(import.meta.env.MODE === "demo");');
    expect(main.indexOf("setPlainWords")).toBeLessThan(main.indexOf("createRoot("));
  });
});
