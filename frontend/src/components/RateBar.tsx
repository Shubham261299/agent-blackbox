import { ratePercent } from "../lib/metrics";

/** A thin meter: one colour, the unfilled track is the same hue lightened. The numbers are always shown beside it. */
export function RateBar({ passed, total, label }: { passed: number; total: number; label: string }) {
  return (
    <span className="rate" role="img" aria-label={`${label}: ${passed} of ${total}`}>
      <span className="rate-track">
        <span className="rate-fill" style={{ width: `${ratePercent(passed, total)}%` }} />
      </span>
      <span className="rate-text">
        {passed}/{total}
      </span>
    </span>
  );
}
