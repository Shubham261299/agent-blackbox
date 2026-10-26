import { describe, expect, it } from "vitest";
import { BANNED_WORDS, jargonIn, longestSentence, readingGrade, sentences, syllables, words } from "./readability";

describe("syllables", () => {
  it.each([
    ["cat", 1], ["the", 1], ["agent", 2], ["recorder", 3], ["recorded", 3], ["finished", 2], ["follow", 2], ["followed", 2], ["checks", 1], ["problem", 2],
    ["refund", 2], ["policy", 3], ["planted", 2], ["noticing", 3], ["airplane", 2], ["table", 2], ["are", 1], ["", 0], ["59", 0],
  ])("%s has %i", (word, n) => expect(syllables(word)).toBe(n));
});

describe("words and sentences", () => {
  it("finds words, keeping apostrophes and hyphens", () => {
    expect(words("I didn't re-run it, 3 times.")).toEqual(["I", "didn't", "re-run", "it", "times"]);
  });

  it("splits sentences at full stops, and not inside a number or an abbreviation-like gap", () => {
    expect(sentences("A refund of $59.90 was issued. It worked! Did it? Yes.")).toEqual(["A refund of $59.90 was issued.", "It worked!", "Did it?", "Yes."]);
    expect(sentences("")).toEqual([]);
    expect(sentences("12 34.")).toEqual([]);
  });
});

describe("readingGrade", () => {
  it("scores short plain words low and long technical ones high", () => {
    expect(readingGrade("The cat sat on the mat. The dog ran to the man.")).toBeLessThan(2);
    expect(readingGrade("Instrumentation of nondeterministic orchestration necessitates comprehensive observability infrastructure.")).toBeGreaterThan(16);
  });

  it("is the Flesch-Kincaid formula: one 6-word sentence of 6 one-syllable words is grade -1.45", () => {
    expect(readingGrade("The cat sat on the mat.")).toBeCloseTo(0.39 * 6 + 11.8 * 1 - 15.59, 5);
    expect(readingGrade("The cat sat on the mat.")).toBeCloseTo(-1.45, 2);
  });

  it("goes up when sentences get longer, with the same words", () => {
    const short = "The agent looked up the order. It checked the policy. It issued the refund.";
    const long = "The agent looked up the order and it checked the policy and it issued the refund.";
    expect(readingGrade(long)).toBeGreaterThan(readingGrade(short));
  });

  it("is zero for no text", () => {
    expect(readingGrade("")).toBe(0);
    expect(readingGrade("123 456")).toBe(0);
  });
});

describe("longestSentence", () => {
  it("returns the longest sentence and its length", () => {
    expect(longestSentence("Short one. This one is a good deal longer than the first. Mid size here.")).toEqual({
      words: 10,
      sentence: "This one is a good deal longer than the first.",
    });
    expect(longestSentence("")).toEqual({ words: 0, sentence: "" });
  });
});

describe("jargonIn", () => {
  it("finds banned words as whole words, in any case, once each", () => {
    expect(jargonIn("Open the Trace. Each span is in the trace; a spanner is not a span.", BANNED_WORDS)).toEqual(["trace", "span"]);
  });

  it("does not flag a word that only contains a banned one", () => {
    expect(jargonIn("A contractor hashed it out over an apiary seedling.", BANNED_WORDS)).toEqual([]);
  });

  it("finds nothing in plain text", () => {
    expect(jargonIn("The agent looked up order 42 and checked the refund rules.", BANNED_WORDS)).toEqual([]);
  });

  it("covers the words that appeared on the old pages", () => {
    for (const w of ["span", "trace", "gating", "contract", "localizer", "seed", "hash", "benchmark", "dataset", "evaluation", "baseline", "prompt"]) {
      expect(BANNED_WORDS).toContain(w);
    }
  });
});
