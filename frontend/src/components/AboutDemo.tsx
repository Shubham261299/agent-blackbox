import { useDataSource } from "../api/context";
import { useQuery } from "../hooks/useQuery";
import { REPO_URL } from "../content/story";
import { splitModel } from "../lib/format";

export { REPO_URL };

/** "2026-10-14" -> "14 October 2026", whatever the viewer's time zone. */
export function formatDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? day : date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

function period(from: string | null, to: string | null): string | null {
  if (!from) return null;
  return !to || to === from ? `on ${formatDay(from)}` : `between ${formatDay(from)} and ${formatDay(to)}`;
}

/** Says what the demo data is and what it is not. Rendered only for a recorded demo. */
export function AboutDemo() {
  const source = useDataSource();
  const info = useQuery(() => (source.demoInfo ? source.demoInfo() : Promise.reject(new Error("not a demo"))), [source]);
  const manifest = info.data;
  const model = manifest?.models[0] ? splitModel(manifest.models[0]).name : null;
  const when = manifest ? period(manifest.recorded_from, manifest.recorded_to) : null;

  return (
    <footer className="about-demo" aria-label="About this demo">
      <p>
        <strong>About this demo.</strong> Everything here was recorded from real runs
        {model ? ` of the local model ${model}` : ""}
        {when ? `, ${when}` : ""}. Nothing is live: no agent runs and no model is called while you browse.
        {manifest && ` It holds ${manifest.counts.runs} runs, ${manifest.counts.evaluations} sets of results and ${manifest.counts.comparisons} before-and-after comparisons.`}{" "}
        <a href={REPO_URL} target="_blank" rel="noreferrer">
          Source code and how to run it yourself
        </a>
        .
      </p>
    </footer>
  );
}
