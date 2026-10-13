import { Icon } from "./Icon";
import { CopyButton } from "./CopyButton";

const START_CMD = "uvicorn --app-dir backend --factory blackbox.api.main:create_app --port 8000";

export function ApiDown({ onRetry }: { onRetry: () => void }) {
  return (
    <section className="card notice" role="alert" aria-labelledby="down-title">
      <div className="notice-head">
        <Icon name="alert" size={18} />
        <h2 id="down-title" className="card-title">
          The API is not running
        </h2>
      </div>
      <p>The dashboard reads runs and traces from the local API on port 8000. Start it from the project folder:</p>
      <div className="codeline">
        <code className="mono">{START_CMD}</code>
        <CopyButton text={START_CMD} label="Copy command" />
      </div>
      <p className="muted small">This page keeps retrying every few seconds and will fill in as soon as the API answers.</p>
      <button type="button" className="btn" onClick={onRetry}>
        Retry now
      </button>
    </section>
  );
}
