import type { EvalCaseResult, FaultLabNote, LabEffect, ValidationNote } from "../api/types";

/** A case's note, narrowed: validation batches and the failure lab store different things there. */
export function validationNote(c: EvalCaseResult): ValidationNote | null {
  return c.note && c.note.kind !== "faultlab" ? c.note : null;
}

export function labNote(c: EvalCaseResult): FaultLabNote | null {
  return c.note?.kind === "faultlab" ? c.note : null;
}

export const EFFECT_LABEL: Record<LabEffect, string> = {
  run_failed: "Run failed",
  gating_failed: "Failed a check",
  silent: "Silent",
  no_effect: "No effect",
};

/** What the fault did to the run, as one sentence. */
export const EFFECT_TEXT: Record<LabEffect, string> = {
  run_failed: "The run failed.",
  gating_failed: "The run finished, but it failed a gating check.",
  silent: "The run passed both gating checks. Only a reported check noticed.",
  no_effect: "No check noticed anything.",
};

export function verdictText(note: FaultLabNote): string {
  if (!note.fired) return "The fault never fired, so there is nothing to locate.";
  if (note.rank === 1) return "The top suspect is the span the fault was planted in.";
  if (note.rank) return `The planted span ranked number ${note.rank}, not first.`;
  return "The planted span was not among the suspects.";
}
