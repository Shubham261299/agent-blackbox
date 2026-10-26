import { useRef } from "react";
import { useDataSource } from "../api/context";
import { loadDemoStory } from "../content/loadStory";
import { REPO_URL } from "../content/story";
import { useQuery } from "../hooks/useQuery";
import { tourLink } from "../lib/tour";
import { RUNS_HREF } from "../hooks/useHashRoute";

const GIF = `${import.meta.env.BASE_URL}tour.gif`;

/** The front page of the recorded demo: plain words first, the evidence one click away. */
export function HomePage() {
  const source = useDataSource();
  const found = useRef<HTMLElement>(null);
  const data = useQuery(() => loadDemoStory(source), [source]);

  if (!data.data) {
    return (
      <p className="muted" role="status">
        {data.error ? "The recorded results could not be loaded. Check your connection and reload the page." : "Loading…"}
      </p>
    );
  }
  const { story, stops } = data.data;
  const firstStop = stops[0];

  return (
    <div className="home">
      <section className="hero" aria-labelledby="home-title">
        <h1 id="home-title">{story.title}</h1>
        <p className="hero-intro">{story.intro}</p>
        <div className="ways" role="group" aria-label="Choose how much to read">
          <button type="button" className="btn primary big" onClick={() => found.current?.scrollIntoView({ behavior: "smooth", block: "start" })}>
            30 seconds
            <span>the three results</span>
          </button>
          <a className="btn big" href={firstStop ? tourLink(firstStop, 0) : RUNS_HREF}>
            3 minutes
            <span>a guided tour</span>
          </a>
          <a className="btn big" href="#/evals">
            I&rsquo;m an engineer
            <span>all the evidence</span>
          </a>
        </div>
        <ul className="hero-stats" aria-label="What is in this demo">
          {story.stats.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </section>

      <section className="home-section" aria-labelledby="problem-title">
        <h2 id="problem-title">{story.problemTitle}</h2>
        {story.problem.map((p) => (
          <p key={p} className="prose">
            {p}
          </p>
        ))}
      </section>

      <section className="home-section" aria-labelledby="built-title">
        <h2 id="built-title">{story.builtTitle}</h2>
        <ol className="built">
          {story.built.map((b, i) => (
            <li key={b.title} className="card">
              <span className="built-n" aria-hidden="true">
                {i + 1}
              </span>
              <h3>{b.title}</h3>
              <p>{b.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="home-section" aria-labelledby="found-title" ref={found}>
        <h2 id="found-title">{story.foundTitle}</h2>
        <div className="found">
          {story.found.map((f) => (
            <article key={f.href} className="card found-card">
              <p className="kicker">{f.kicker}</p>
              <p className="big-number">{f.big}</p>
              <p>{f.text}</p>
              <a className="btn" href={f.href}>
                {f.linkText}
              </a>
            </article>
          ))}
        </div>
      </section>

      <section className="home-section" aria-labelledby="gif-title">
        <h2 id="gif-title">The 25-second version</h2>
        <figure className="gif">
          <img src={GIF} alt="A captioned walk through the demo: a failed run, a fix that worked, a fix that did not." width={960} height={540} loading="lazy" />
        </figure>
      </section>

      <section className="home-section" aria-labelledby="honest-title">
        <h2 id="honest-title">{story.honestTitle}</h2>
        <ul className="honest">
          {story.honest.map((h) => (
            <li key={h.text}>
              <span>{h.text}</span>
              {h.href && (
                <>
                  {" "}
                  <a href={h.href} {...(h.href.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}>
                    {h.linkText}
                  </a>
                </>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="home-section" aria-labelledby="limits-title">
        <div className="callout warn limits-box">
          <div>
            <h2 id="limits-title">{story.limitsTitle}</h2>
            <p>{story.limits}</p>
          </div>
        </div>
      </section>

      <section className="home-section" aria-labelledby="inside-title">
        <h2 id="inside-title">{story.insideTitle}</h2>
        <ol className="inside">
          {stops.map((stop, i) => (
            <li key={stop.href}>
              <a href={tourLink(stop, i)}>{stop.title}</a>
              <span>{stop.text}</span>
            </li>
          ))}
        </ol>
        <p className="inside-links">
          <a href={RUNS_HREF}>All runs</a> · <a href="#/evals">All results</a> ·{" "}
          <a href={REPO_URL} target="_blank" rel="noreferrer">
            Source code
          </a>{" "}
          ·{" "}
          <a href={`${REPO_URL}#run-it-yourself`} target="_blank" rel="noreferrer">
            How to run it yourself
          </a>
        </p>
      </section>
    </div>
  );
}
