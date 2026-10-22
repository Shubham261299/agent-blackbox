import { useDataSource } from "../api/context";
import type { Comparison } from "../api/types";
import { useQuery } from "../hooks/useQuery";
import { tourStops } from "../lib/tour";

/** The landing card of the recorded demo: four stops, so a visitor is not dropped into a table of runs. */
export function StartHere() {
  const source = useDataSource();
  const tour = useQuery(async () => {
    if (!source.demoInfo) return null;
    const manifest = await source.demoInfo();
    // A comparison that cannot be loaded only costs its sentence the numbers.
    const pair = (ids?: [string, string]): Promise<Comparison | undefined> =>
      ids ? source.compare(ids[0], ids[1]).catch(() => undefined) : Promise.resolve(undefined);
    const [fixed, regressed] = await Promise.all([pair(manifest.tour.fixed), pair(manifest.tour.regressed)]);
    return tourStops(manifest.tour, fixed, regressed);
  }, [source]);

  if (!tour.data || tour.data.length === 0) return null;
  return (
    <section className="card start-here" aria-labelledby="start-here-title">
      <h2 id="start-here-title" className="card-title">
        Start here: a two-minute tour
      </h2>
      <p className="lede">
        Agent Blackbox records every step an AI agent takes, then checks the recording and says where it went wrong. Four stops show what it does:
      </p>
      <ol className="tour">
        {tour.data.map((stop, i) => (
          <li key={stop.href} className="tour-stop">
            <span className="tour-n" aria-hidden="true">
              {i + 1}
            </span>
            <div>
              <a className="tour-title" href={stop.href}>
                {stop.title}
              </a>
              <p>{stop.text}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
