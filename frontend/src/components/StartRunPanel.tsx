import { useState, type FormEvent } from "react";
import type { ScenarioInfo } from "../api/types";
import { useDataSource } from "../api/context";
import { runHref } from "../hooks/useHashRoute";
import { Icon } from "./Icon";

type Mode = "scripted" | "ollama";

const OLLAMA_PRESETS = [
  "Order 42 arrived damaged, please refund it.",
  "Order 43 is damaged, I want my $180 back.",
  "Where is order 999?",
];

export function StartRunPanel({ scenarios }: { scenarios: ScenarioInfo[] }) {
  const source = useDataSource();
  const [mode, setMode] = useState<Mode>("scripted");
  const [scenario, setScenario] = useState<string>("");
  const [task, setTask] = useState(OLLAMA_PRESETS[0] as string);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Derived, not synced by an effect: until the user picks one, the first scenario is the choice.
  const chosen = scenarios.find((s) => s.name === scenario) ?? scenarios[0];

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const started =
        mode === "scripted"
          ? await source.startRun({ task: chosen?.example_task ?? "Run", model: "scripted", scenario: chosen?.name })
          : await source.startRun({ task: task.trim(), model: "ollama" });
      window.location.hash = runHref(started.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the run.");
      setBusy(false);
    }
  }

  return (
    <section className="card start" aria-labelledby="start-title">
      <div className="start-head">
        <h2 id="start-title" className="card-title">
          Start a run
        </h2>
        <div className="seg seg-text" role="radiogroup" aria-label="Model">
          <button type="button" role="radio" aria-checked={mode === "scripted"} className="seg-btn" onClick={() => setMode("scripted")}>
            Scripted scenario
          </button>
          <button type="button" role="radio" aria-checked={mode === "ollama"} className="seg-btn" onClick={() => setMode("ollama")}>
            Local model (Ollama)
          </button>
        </div>
      </div>

      <form onSubmit={submit}>
        <div className="start-form">
          {mode === "scripted" ? (
            <div className="field grow">
              <label htmlFor="scenario">Scenario</label>
              <select id="scenario" value={chosen?.name ?? ""} onChange={(e) => setScenario(e.target.value)} disabled={scenarios.length === 0}>
                {scenarios.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="field grow">
              <label htmlFor="task">Customer request</label>
              <input id="task" type="text" value={task} onChange={(e) => setTask(e.target.value)} maxLength={2000} required />
            </div>
          )}
          <button type="submit" className="btn primary" disabled={busy || (mode === "ollama" && !task.trim())}>
            <Icon name={busy ? "spinner" : "play"} size={14} className={busy ? "spin" : undefined} />
            {busy ? "Starting…" : "Run agent"}
          </button>
        </div>

        {mode === "scripted" ? (
          <p className="hint">
            {chosen ? `${chosen.description} Task sent: “${chosen.example_task}”` : "Loading scenarios…"} Scripted runs replay a
            recorded conversation, so they are instant and repeatable.
          </p>
        ) : (
          <>
            <div className="chips" aria-label="Example requests">
              {OLLAMA_PRESETS.map((p) => (
                <button key={p} type="button" className="chip" onClick={() => setTask(p)}>
                  {p}
                </button>
              ))}
            </div>
            <p className="hint">Runs on your CPU. The first model call loads the model and can take 10–30 seconds.</p>
          </>
        )}
      </form>
      {error && (
        <p className="form-error" role="alert">
          <Icon name="alert" size={14} /> {error}
        </p>
      )}
    </section>
  );
}
