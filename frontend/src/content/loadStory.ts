import type { DataSource } from "../api/client";
import type { Comparison } from "../api/types";
import { tourStops } from "../lib/tour";
import { buildStory } from "./story";

/** Everything the front page and the tour banner need from the recorded data. Each file is fetched once by the source. */
export async function loadDemoStory(source: DataSource) {
  if (!source.demoInfo) return null;
  const manifest = await source.demoInfo();
  const evals = await source.listEvals();
  // A comparison that cannot be loaded only costs its card the numbers.
  const pair = (ids?: [string, string]): Promise<Comparison | undefined> =>
    ids ? source.compare(ids[0], ids[1]).catch(() => undefined) : Promise.resolve(undefined);
  const [lab, bench, second] = await Promise.all([pair(manifest.tour.fixed), pair(manifest.tour.regressed), pair(manifest.tour.second_attempt)]);
  return { story: buildStory({ manifest, evals, lab, bench, second }), stops: tourStops(manifest.tour, lab, bench) };
}
