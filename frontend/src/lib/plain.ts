/**
 * The recorded demo is read by people who do not know what a "span" or a "gating check" is, so it uses everyday words
 * for the same things (and keeps the technical page one click away). The live app keeps the technical words.
 * Set once at start-up; the vocabulary functions in metrics.ts and compare.ts read it.
 */
let plain = false;

export function setPlainWords(on: boolean): void {
  plain = on;
}

export function plainWords(): boolean {
  return plain;
}
