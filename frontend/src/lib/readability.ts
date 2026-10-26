/** Measures how easy a text is to read, so "plain words" is a number a test can hold and not a feeling. */

/** Counts syllables with the usual rule of thumb: groups of vowels, minus a silent final "e". Good enough for a grade. */
export function syllables(word: string): number {
  const w = word.toLowerCase().replace(/[^a-z]/g, "");
  if (w.length === 0) return 0;
  if (w.length <= 3) return 1;
  const groups = w.replace(/(?:[^laeiouy]es|[^tdaeiouy]ed|[^laeiouy]e)$/, "").replace(/^y/, "").match(/[aeiouy]{1,2}/g);
  return Math.max(1, groups?.length ?? 1);
}

export function words(text: string): string[] {
  return text.match(/[A-Za-z][A-Za-z'’-]*/g) ?? [];
}

/** Sentences, split at . ! ? followed by a space or the end. A number like 59.90 does not end one. */
export function sentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+(?=[A-Z“"(])/)
    .map((s) => s.trim())
    .filter((s) => words(s).length > 0);
}

/** The Flesch-Kincaid grade level: roughly the school year a reader needs to follow the text. Lower is easier. */
export function readingGrade(text: string): number {
  const w = words(text);
  const s = sentences(text);
  if (w.length === 0 || s.length === 0) return 0;
  const syl = w.reduce((n, x) => n + syllables(x), 0);
  return 0.39 * (w.length / s.length) + 11.8 * (syl / w.length) - 15.59;
}

/** The longest sentence, in words. */
export function longestSentence(text: string): { words: number; sentence: string } {
  return sentences(text)
    .map((sentence) => ({ words: words(sentence).length, sentence }))
    .reduce((a, b) => (b.words > a.words ? b : a), { words: 0, sentence: "" });
}

/** Words from `banned` that appear in `text` as whole words, ignoring case. */
export function jargonIn(text: string, banned: readonly string[]): string[] {
  const found = new Set<string>();
  for (const w of words(text)) {
    const lower = w.toLowerCase();
    if (banned.includes(lower)) found.add(lower);
  }
  return [...found];
}

/**
 * Words a newcomer should not meet in the plain part of the demo. Each is either a term of the field or one of this
 * project's own names for something. The technical details behind a fold may use them.
 */
export const BANNED_WORDS = [
  "span", "spans", "trace", "traces", "tracing", "gating", "gate", "gates", "contract", "localizer", "localiser", "suspect", "suspects",
  "seed", "hash", "opentelemetry", "otel", "benchmark", "benchmarks", "dataset", "datasets", "evaluation", "evaluations", "variant",
  "regression", "latency", "tokenizer", "llm", "api", "json", "prompt", "prompts", "baseline", "orchestrator", "telemetry", "payload",
  "heuristic", "deterministic", "infrastructure", "endpoint", "backend", "metric", "metrics",
] as const;
