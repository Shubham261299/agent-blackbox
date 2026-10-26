import { variantInfo, variantLabel } from "../lib/compare";
import { plainWords } from "../lib/plain";
import { Icon } from "./Icon";

/**
 * Which agent configuration made a run or an evaluation. The baseline is the default and says nothing extra;
 * anything else is named, with what it changes in the tooltip. `rescoredFrom` marks an evaluation that re-judged
 * another one's stored runs against a newer dataset version (no model was run for it).
 */
export function VariantChip({ variant, rescoredFrom }: { variant: string; rescoredFrom?: string | null }) {
  const what = variantInfo(variant)?.what;
  return (
    <span className="variant-chips">
      <span className="variant" data-variant={variant === "baseline" ? "baseline" : "changed"} title={what}>
        <Icon name="agent" size={12} />
        {variantLabel(variant)}
      </span>
      {rescoredFrom && (
        <span className="variant" data-variant="rescored" title={
            plainWords()
              ? `These stored runs (from ${rescoredFrom}) were judged again against corrected rules. No AI model was run for this.`
              : `Re-judged from the stored runs of ${rescoredFrom} against a newer dataset version. No model was run.`
          }
        >
          {plainWords() ? "Re-judged" : "Rescored"}
        </span>
      )}
    </span>
  );
}
