import { describe, expect, it } from "vitest";
import type { RunRecord } from "../api/types";
import { setPlainWords } from "../lib/plain";
import { afterEach, beforeEach } from "vitest";
import { check, comparison, evalReport, happyPathSpans, run, runEvaluation, span, suspect, withFailures } from "../test/factories";
import { EVALS_LEAD, RUNS_LEAD, compareLead, evalLead, plainDataset, plainFault, plainModel, plainReason, plainRefusal, plainSource, plainStepName, runOrder, runStory, stepText } from "./plain";

beforeEach(() => setPlainWords(true));
afterEach(() => setPlainWords(false));

describe("leads", () => {
  it("say what each list is and how to use it", () => {
    expect(RUNS_LEAD).toContain("one conversation between a customer and the AI agent");
    expect(RUNS_LEAD).toContain("Failed runs are listed first");
    expect(EVALS_LEAD).toContain("tried on the same test cases and judged by the same rules");
  });

  it("explain what a set of results is, by kind", () => {
    expect(evalLead({ kind: "benchmark", n_cases: 24, n_passed: 19 })).toContain("tried on 24 test cases");
    expect(evalLead({ kind: "benchmark", n_cases: 24, n_passed: 19 })).toContain("finished the job and followed the rules");
    expect(evalLead({ kind: "reference", n_cases: 24, n_passed: 24 })).toContain("says nothing about any AI model");
    expect(evalLead({ kind: "validation", n_cases: 11, n_passed: 11 })).toContain("tests the checker itself");
    expect(evalLead({ kind: "faultlab", n_cases: 4, n_passed: 4 })).toContain("without being told what I planted");
  });

  it("explain a comparison: who against whom, on how many, and what fixed and broken mean", () => {
    const text = compareLead(comparison({ matched: 24, baseline: { ...comparison().baseline, variant: "baseline" }, candidate: { ...comparison().candidate, variant: "guided" } }));
    expect(text).toContain("I compared “New instructions (v2)” with “Original agent” on the same 24 test cases.");
    expect(text).toContain("Fixed means a case used to fail and now passes.");
    expect(text).toContain("Broken means a case used to pass and now fails.");
    expect(text).toContain("Passing means the agent finished the job and followed the rules.");
    expect(text).toContain("A fix that breaks working cases is not free.");
  });

  it("speak of planted problems for the failure lab, and not of passing", () => {
    const text = compareLead(comparison({ kind: "faultlab", matched: 4 }));
    expect(text).toContain("on the same 4 planted problems");
    expect(text).toContain("a planted problem used to hurt the run and now does not");
    expect(text).not.toContain("Passing means");
  });

  it("warn that two runs of the same agent differ only by noise", () => {
    const same = comparison({ baseline: { ...comparison().baseline, variant: "baseline" }, candidate: { ...comparison().candidate, variant: "baseline" } });
    expect(compareLead(same)).toContain("same agent (Original agent), so any difference below is just run-to-run noise");
  });

  it("use the singular for one", () => {
    expect(compareLead(comparison({ matched: 1 }))).toContain("on the same 1 test case.");
  });
});

describe("stepText", () => {
  const tool = (name: string, args?: unknown) => span({ span_id: "s", name, attributes: args === undefined ? {} : { "blackbox.tool.args": JSON.stringify(args) } });

  it("says what each model call was for", () => {
    expect(stepText(span({ span_id: "a", name: "model.plan" }))).toBe("Asked the AI model what to do");
    expect(stepText(span({ span_id: "a", name: "model.call" }))).toBe("Asked the AI model what to do next");
    expect(stepText(span({ span_id: "a", name: "model.finalize" }))).toBe("Asked the AI model to write the reply");
  });

  it("says what each tool did, with the order number when it is known", () => {
    expect(stepText(tool("tool.lookup_order", { order_id: 42 }))).toBe("Looked up order 42");
    expect(stepText(tool("tool.check_refund_policy", { order_id: "43", amount: 10 }))).toBe("Checked the refund policy for order 43");
    expect(stepText(tool("tool.issue_refund", { order_id: 42 }))).toBe("Issued a refund on order 42");
    expect(stepText(tool("tool.update_shipping_address", { order_id: 45 }))).toBe("Changed the shipping address on order 45");
  });

  it("falls back to a plain sentence when the details were removed or are not readable", () => {
    expect(stepText(tool("tool.lookup_order"))).toBe("Looked up the order");
    expect(stepText(tool("tool.lookup_order", { order_id: "[REDACTED]" }))).toBe("Looked up order [REDACTED]");
    expect(stepText(span({ span_id: "s", name: "tool.lookup_order", attributes: { "blackbox.tool.args": "not json" } }))).toBe("Looked up the order");
    expect(stepText(tool("tool.lookup_order", { other: 1 }))).toBe("Looked up the order");
  });

  it("names a tool it does not know instead of hiding it", () => {
    expect(stepText(tool("tool.refund_customer"))).toBe("Used the “refund customer” tool");
  });
});

describe("runStory", () => {
  const spans = () => [
    ...happyPathSpans(),
  ];
  const failedSpans = () => [
    span({ span_id: "root", name: "agent.run", span_type: "agent", status: "error" }),
    span({ span_id: "m1", parent_span_id: "root", name: "model.plan", duration_ms: 2000 }),
    span({ span_id: "t1", parent_span_id: "root", name: "tool.lookup_order", status: "ok", attributes: { "blackbox.tool.args": JSON.stringify({ order_id: 42 }) } }),
    span({ span_id: "t2", parent_span_id: "root", name: "tool.check_refund_policy", status: "error", status_message: "ToolTimeoutError: timed out after 0.3s",
      attributes: { "blackbox.agent.retry_count": 2 } }),
  ];
  const finished = (extra: Partial<RunRecord> = {}) => ({ ...run(), ...extra });

  it("lists the steps in order without the run itself, numbered from 1", () => {
    const story = runStory(finished(), spans());
    expect(story.steps.map((s) => [s.n, s.text])).toEqual([
      [1, "Asked the AI model what to do"],
      [2, "Looked up order 42"],
      [3, "Asked the AI model to write the reply"],
    ]);
  });

  it("says the agent finished when the checks say so", () => {
    const story = runStory(finished(), spans(), runEvaluation());
    expect(story.sentence).toBe("The agent took 3 steps and finished the job.");
    expect([story.finished, story.rules]).toEqual([true, true]);
  });

  it("says when the agent answered but did not finish the job, and when it broke a rule", () => {
    const notDone = runEvaluation({ checks: withFailures({ task_completion: {} }) });
    expect(runStory(finished(), spans(), notDone).sentence).toBe("The agent took 3 steps and gave an answer, but it did not finish the job.");
    const broke = runEvaluation({ checks: withFailures({ policy_compliance: {} }) });
    expect(runStory(finished(), spans(), broke).sentence).toBe("The agent took 3 steps and finished, but it broke a rule on the way.");
  });

  it("says only that it answered when there are no checks to say more", () => {
    expect(runStory(finished(), spans()).sentence).toBe("The agent took 3 steps and gave an answer.");
    expect(runStory(finished(), spans(), runEvaluation({ checks: [check({ metric: "latency", passed: null })] })).finished).toBeNull();
  });

  it("names the step that failed when the run stopped with an error", () => {
    const story = runStory(finished({ status: "error" }), failedSpans());
    expect(story.sentence).toBe("The run stopped with an error after 3 steps. Step 3 is where it failed.");
    expect(story.steps[2]).toMatchObject({ failed: true, retries: 2, detail: "ToolTimeoutError: timed out after 0.3s" });
    expect(story.steps[1]).toMatchObject({ failed: false, retries: 0, detail: undefined });
  });

  it("points at the step the analysis names, and at the run as a whole when it names the run", () => {
    const at = (spanId: string) => runEvaluation({ suspects: [suspect({ span_id: spanId })] });
    expect(runStory(finished({ status: "error" }), failedSpans(), at("t2")).where).toBe("Step 3: Checked the refund policy");
    expect(runStory(finished({ status: "error" }), failedSpans(), at("root")).where).toBe("The run as a whole");
    expect(runStory(finished(), spans(), runEvaluation()).where).toBeUndefined();
  });

  it("uses the singular for a run with one step", () => {
    const one = [span({ span_id: "root", name: "agent.run" }), span({ span_id: "m", parent_span_id: "root", name: "model.plan" })];
    expect(runStory(finished(), one).sentence).toBe("The agent took 1 step and gave an answer.");
  });
});

describe("the run list order", () => {
  const r = (id: string, over: Partial<RunRecord>) => run({ run_id: id, ...over });
  const list = [
    r("scripted-new", { model: "scripted:reference:N1" }),
    r("real-ok", { model: "ollama:qwen2.5:7b" }),
    r("scripted-failed", { model: "scripted:unknown_order", status: "error" }),
    r("real-failed", { model: "ollama:qwen2.5:7b", status: "error" }),
    r("real-ok-2", { model: "ollama:qwen2.5:7b" }),
    r("scripted-old", { model: "scripted:refund_happy_path" }),
  ];

  it("puts failed runs first, then the real model's, then the scripted examples, each group in its original order", () => {
    expect(runOrder(list).map((x) => x.run_id)).toEqual(["scripted-failed", "real-failed", "real-ok", "real-ok-2", "scripted-new", "scripted-old"]);
  });

  it("does not change the list it is given, and keeps every run", () => {
    const copy = [...list];
    expect(runOrder(list)).toHaveLength(list.length);
    expect(list).toEqual(copy);
    expect(runOrder([])).toEqual([]);
  });
});

describe("names in the evaluations table", () => {
  it("shows an AI model by name and a scripted run as not being one", () => {
    expect(plainModel("ollama:qwen2.5:7b")).toBe("qwen2.5:7b");
    expect(plainModel("scripted:reference")).toBe("Scripted (no AI model)");
    expect(plainModel("plain-name")).toBe("plain-name".slice("plain-name".indexOf(":") + 1));
  });

  it("describes the test set by how many cases it has, not by a hash", () => {
    expect(plainDataset(evalReport({ n_cases: 24 }))).toBe("24 test cases");
  });
});

describe("the analysis's suggestions in everyday words", () => {
  it("names a suggested step by what it was", () => {
    expect(plainStepName("tool.check_refund_policy")).toBe("Checked the refund policy");
    expect(plainStepName("tool.lookup_order")).toBe("Looked up the order");
    expect(plainStepName("tool.refund_customer")).toBe("Used the “refund customer” tool");
    expect(plainStepName("model.plan")).toBe("Asked the AI model");
    expect(plainStepName("model.finalize")).toBe("Asked the AI model");
    expect(plainStepName("agent.run")).toBe("The run as a whole");
    expect(plainStepName("something.else")).toBe("something.else");
  });

  it("says why it was suggested, and shows an unknown reason as it is", () => {
    expect(plainSource("error status")).toBe("it reported an error");
    expect(plainSource("tool output contract")).toBe("its answer could not be used");
    expect(plainSource("policy compliance")).toBe("a rule was broken");
    expect(plainSource("task completion")).toBe("the job was not finished");
    expect(plainSource("retried")).toBe("it needed retries");
    expect(plainSource("something new")).toBe("something new");
  });
});

describe("plainReason: what an error or a suggestion says", () => {
  it("says a tool sent back something unusable, naming the tool", () => {
    expect(plainReason("lookup_order returned data that breaks its contract: expected an object, got str: '<html>'")).toBe("The order lookup sent back something the agent could not use.");
    expect(plainReason("issue_refund returned data that breaks its contract: x")).toBe("The refund tool sent back something the agent could not use.");
    expect(plainReason("mystery_tool returned data that breaks its contract: x")).toBe("The “mystery tool” tool sent back something the agent could not use.");
  });

  it("says how long a tool took before it gave up", () => {
    expect(plainReason("ToolTimeoutError: check_refund_policy timed out after 0.3s")).toBe("The refund policy check did not answer within 0.3 seconds.");
    expect(plainReason("ToolTimeoutError: lookup_order timed out after 12s")).toBe("The order lookup did not answer within 12 seconds.");
  });

  it("says the AI model could not be reached, without the machinery", () => {
    expect(plainReason("ModelUnavailableError: model backend unavailable: connection refused")).toBe("The AI model could not be reached.");
  });

  it("says a rule was broken: acting on an order that was never looked up", () => {
    expect(plainReason("update_shipping_address on order 45 without a successful lookup first")).toBe("Changed the shipping address on order 45 without looking the order up first.");
    expect(plainReason("issue_refund on order 42 without a successful lookup first")).toBe("Issued a refund on order 42 without looking the order up first.");
    expect(plainReason("weird_tool on order 7 without a successful lookup first")).toBe("Used the “weird tool” tool on order 7 without looking the order up first.");
  });

  it("shows a message it does not know exactly as it is, and never guesses", () => {
    expect(plainReason("refund not approved")).toBe("refund not approved");
    expect(plainReason("")).toBe("");
    expect(plainReason("TypeError: something unexpected")).toBe("TypeError: something unexpected");
  });
});

describe("plainRefusal: why two results cannot be compared", () => {
  it("rewords each refusal the API gives", () => {
    expect(plainRefusal("An evaluation cannot be compared with itself.")).toBe("A result cannot be compared with itself.");
    expect(plainRefusal("They ran different cases (golden-v3 82acd02d8a18 against holdout-v1 8c7eb9ea4eb0), so the difference could come from the test.")).toBe(
      "They were tested on different test cases, so any difference could come from the test and not from the agent.");
    expect(plainRefusal("They used different models (ollama:a and ollama:b).")).toContain("different AI models");
    expect(plainRefusal("They used different seeds (0 and 1).")).toContain("different settings");
    expect(plainRefusal("These are different kinds of evaluation (benchmark and faultlab).")).toBe("These are two different kinds of result, so there is nothing fair to compare.");
    expect(plainRefusal("eval-a5479ac6 is a validation evaluation: it checks the checks, not an agent, so there is nothing to compare.")).toBe(
      "That one tests the checker itself, not an agent, so there is nothing to compare.");
    expect(plainRefusal("eval-x has not finished.")).toBe("One of them has not finished yet.");
  });

  it("leaves out the hashes and ids the API's wording includes", () => {
    expect(plainRefusal("They ran different cases (golden-v3 82acd02d8a18 against holdout-v1 8c7eb9ea4eb0), so the difference could come from the test.")).not.toMatch(/\d{4}|golden/);
  });

  it("shows a refusal it does not know as it is", () => {
    expect(plainRefusal("Something new went wrong.")).toBe("Something new went wrong.");
  });
});

describe("plainFault: the four planted problems", () => {
  const own = { title: "Own title", description: "Own description" };

  it("names and describes each one in everyday words", () => {
    expect(plainFault("tool_timeout", own).title).toBe("A tool times out");
    expect(plainFault("malformed_output", own).title).toBe("A tool sends back garbage");
    expect(plainFault("wrong_tool", own).title).toBe("The wrong tool is chosen");
    expect(plainFault("model_error", own).title).toBe("The AI model stops answering");
    for (const f of ["tool_timeout", "malformed_output", "wrong_tool", "model_error"]) expect(plainFault(f, own).description.length).toBeGreaterThan(50);
  });

  it("keeps an unknown problem's own title and description", () => {
    expect(plainFault("something_new", own)).toEqual(own);
  });
});
