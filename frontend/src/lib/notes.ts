import type { EvalCaseResult, FaultLabNote, LabEffect, ValidationNote } from "../api/types";
import { plainWords } from "./plain";

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

const PLAIN_EFFECT_LABEL: Record<LabEffect, string> = {
  run_failed: "Run failed",
  gating_failed: "Failed the job",
  silent: "Went unnoticed",
  no_effect: "No effect",
};

const PLAIN_EFFECT_TEXT: Record<LabEffect, string> = {
  run_failed: "The run failed.",
  gating_failed: "The run finished, but the agent did not finish the job or it broke a rule.",
  silent: "The run looked fine on both pass-or-fail rules. Only one of the other checks noticed.",
  no_effect: "No check noticed anything.",
};

/** The effect's name and its sentence, in the words of the current mode. */
export const effectLabel = (effect: LabEffect): string => (plainWords() ? PLAIN_EFFECT_LABEL : EFFECT_LABEL)[effect];
export const effectText = (effect: LabEffect): string => (plainWords() ? PLAIN_EFFECT_TEXT : EFFECT_TEXT)[effect];

export function verdictText(note: FaultLabNote): string {
  if (plainWords()) {
    if (!note.fired) return "The problem never happened, so there is nothing to find.";
    if (note.rank === 1) return "The analysis's first suggestion is the step where the problem was planted.";
    if (note.rank) return `The planted step was the analysis's number ${note.rank} suggestion, not the first.`;
    return "The planted step was not among the analysis's suggestions.";
  }
  if (!note.fired) return "The fault never fired, so there is nothing to locate.";
  if (note.rank === 1) return "The top suspect is the span the fault was planted in.";
  if (note.rank) return `The planted span ranked number ${note.rank}, not first.`;
  return "The planted span was not among the suspects.";
}
