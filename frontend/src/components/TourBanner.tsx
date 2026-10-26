import { useDataSource } from "../api/context";
import { loadDemoStory } from "../content/loadStory";
import { HOME_HREF } from "../hooks/useHashRoute";
import { useQuery } from "../hooks/useQuery";
import { parseTour, tourLink, withoutTour } from "../lib/tour";

/**
 * On a page that is a stop of the guided tour, says which stop it is, what to look at, and where Back and Next go.
 * Shown only to a visitor who came in through the tour (the address carries the stop number) and only on the page
 * that stop belongs to; anywhere else it stays out of the way.
 */
export function TourBanner({ hash }: { hash: string }) {
  const source = useDataSource();
  const data = useQuery(() => loadDemoStory(source), [source]);
  const n = parseTour(hash);
  const stops = data.data?.stops;
  if (!stops || n === null) return null;
  const stop = stops[n - 1]; // a number outside the tour (0, 9) finds no stop
  if (!stop || withoutTour(hash) !== stop.href) return null; // the number belongs to another page

  const previous = stops[n - 2];
  const next = stops[n];
  return (
    <aside className="tour-banner" aria-label="Guided tour">
      <div className="tour-banner-text">
        <p className="tour-banner-step">
          Guided tour · Stop {n} of {stops.length}: {stop.title}
        </p>
        <p className="tour-banner-notice">{stop.notice}</p>
      </div>
      <div className="tour-banner-buttons">
        <a className="btn" href={previous ? tourLink(previous, n - 2) : HOME_HREF}>
          {previous ? "Back" : "Back to the start"}
        </a>
        <a className="btn primary" href={next ? tourLink(next, n) : HOME_HREF}>
          {next ? "Next stop" : "Finish the tour"}
        </a>
        <a className="tour-banner-leave" href={stop.href}>
          Leave the tour
        </a>
      </div>
    </aside>
  );
}
