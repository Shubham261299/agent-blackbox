import type { ReactNode } from "react";
import type { CheckResult, SpanEvent, SpanRecord } from "../api/types";
import { formatDuration, formatOffset } from "../lib/timeScale";
import { metricLabel } from "../lib/metrics";
import { countRedactions, parseMaybeJson, prettyJson } from "../lib/redaction";
import { CodeBlock, RedactedText } from "./RedactedText";
import { CopyButton } from "./CopyButton";
import { Icon } from "./Icon";
import { SpanStatusPill } from "./StatusPill";
import { TYPE_ICON, TYPE_LABEL } from "./Waterfall";

const str = (span: SpanRecord, key: string): string | undefined => {
  const v = span.attributes[key];
  return v === undefined || v === null ? undefined : String(v);
};
const num = (span: SpanRecord, key: string): number | undefined => {
  const v = span.attributes[key];
  return typeof v === "number" ? v : undefined;
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="insp-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

interface ChatMessage {
  role?: string;
  content?: string;
  tool_name?: string;
  tool_calls?: unknown;
}

function Transcript({ raw }: { raw: string }) {
  const parsed = parseMaybeJson(raw);
  if (!Array.isArray(parsed)) return <CodeBlock value={raw} label="Prompt" />;
  return (
    <ol className="transcript">
      {(parsed as ChatMessage[]).map((m, i) => {
        const body = m.content ? prettyJson(m.content) : m.tool_calls ? prettyJson(m.tool_calls) : "";
        const header = (
          <span className="msg-role" data-role={m.role}>
            {m.role}
            {m.tool_name ? ` · ${m.tool_name}` : ""}
            {!m.content && m.tool_calls ? " · requested tools" : ""}
          </span>
        );
        if (m.role === "system") {
          return (
            <li key={i} className="msg">
              <details>
                <summary>{header}</summary>
                <pre className="code">
                  <RedactedText text={body} />
                </pre>
              </details>
            </li>
          );
        }
        return (
          <li key={i} className="msg">
            {header}
            <pre className="code">
              <RedactedText text={body} />
            </pre>
          </li>
        );
      })}
    </ol>
  );
}

function Events({ events }: { events: SpanEvent[] }) {
  return (
    <ul className="events">
      {events.map((e, i) => {
        const type = e.attributes["exception.type"];
        const message = e.attributes["exception.message"];
        const stack = e.attributes["exception.stacktrace"];
        return (
          <li key={i} data-kind={e.name}>
            <div className="event-head">
              <Icon name={e.name === "exception" ? "x" : "check"} size={13} />
              <strong>{e.name}</strong>
              {typeof type === "string" && <span className="mono muted small">{type}</span>}
            </div>
            {typeof message === "string" && (
              <p className="event-msg">
                <RedactedText text={message} />
              </p>
            )}
            {typeof stack === "string" && (
              <details>
                <summary>Stack trace</summary>
                <pre className="code">
                  <RedactedText text={stack} />
                </pre>
              </details>
            )}
            {e.name !== "exception" && Object.keys(e.attributes).length > 0 && <CodeBlock value={e.attributes} label={`${e.name} attributes`} />}
          </li>
        );
      })}
    </ul>
  );
}

export function SpanInspector({
  span,
  spans,
  onSelect,
  findings = [],
}: {
  span: SpanRecord | null;
  spans: SpanRecord[];
  onSelect: (spanId: string) => void;
  /** Failed evaluation checks that point at this span. */
  findings?: CheckResult[];
}) {
  if (!span) {
    return (
      <aside className="card inspector empty" aria-label="Span inspector">
        <p className="muted">Select a span to see its arguments, output, timing and errors.</p>
      </aside>
    );
  }

  const parent = span.parent_span_id ? spans.find((s) => s.span_id === span.parent_span_id) : undefined;
  const redactions = countRedactions([span.attributes, span.events, span.status_message]);
  const tokensIn = num(span, "gen_ai.usage.input_tokens");
  const tokensOut = num(span, "gen_ai.usage.output_tokens");
  const model = str(span, "gen_ai.request.model");
  const provider = str(span, "gen_ai.provider.name");
  const step = str(span, "blackbox.agent.step");
  const args = str(span, "blackbox.tool.args");
  const output = str(span, "blackbox.tool.output");
  const prompt = str(span, "blackbox.model.prompt");
  const completion = str(span, "blackbox.model.completion");
  const toolCalls = str(span, "blackbox.model.tool_calls");
  const agentInput = str(span, "blackbox.agent.input");
  const agentOutput = str(span, "blackbox.agent.output");
  const attrEntries = Object.entries(span.attributes).sort(([a], [b]) => a.localeCompare(b));

  return (
    <aside className="card inspector" aria-label="Span inspector">
      <header className="insp-head">
        <div className="insp-title">
          <span className="wf-glyph" data-type={span.span_type}>
            <Icon name={TYPE_ICON[span.span_type]} size={16} />
          </span>
          <div>
            <h2 className="mono">{span.name}</h2>
            <p className="muted small">{TYPE_LABEL[span.span_type]}</p>
          </div>
        </div>
        <SpanStatusPill status={span.status} />
      </header>

      {span.status === "error" && (
        <div className="callout crit" role="alert">
          <Icon name="x" size={15} />
          <div>
            <strong>This span failed</strong>
            <p>
              <RedactedText text={span.status_message ?? "No message recorded."} />
            </p>
          </div>
        </div>
      )}

      {findings.length > 0 && (
        <section className="callout warn" aria-label="Evaluation findings">
          <Icon name="alert" size={15} />
          <div>
            <strong>Evaluation {findings.length === 1 ? "finding" : "findings"}</strong>
            <ul>
              {findings.map((f) => (
                <li key={f.metric}>
                  <span className="finding-metric">{metricLabel(f.metric)}</span>: {f.reason}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {redactions > 0 && (
        <p className="redaction-note">
          <Icon name="lock" size={13} />
          {redactions} sensitive {redactions === 1 ? "value was" : "values were"} removed before this span was stored.
        </p>
      )}

      <dl className="facts-grid">
        <Fact label="Duration">
          <span className="mono">{formatDuration(span.duration_ms)}</span>
        </Fact>
        <Fact label="Starts at">
          <span className="mono">{formatOffset(span.start_offset_ms)}</span>
        </Fact>
        {model && <Fact label="Model">{provider ? `${model} · ${provider}` : model}</Fact>}
        {step && <Fact label="Agent step">{step}</Fact>}
        {(tokensIn !== undefined || tokensOut !== undefined) && (
          <Fact label="Tokens in / out">
            <span className="mono">
              {tokensIn ?? "–"} / {tokensOut ?? "–"}
            </span>
          </Fact>
        )}
        <Fact label="Span id">
          <span className="mono small">{span.span_id}</span> <CopyButton text={span.span_id} label="Copy span id" />
        </Fact>
        <Fact label="Parent">
          {parent ? (
            <button type="button" className="link-btn mono" onClick={() => onSelect(parent.span_id)}>
              {parent.name}
            </button>
          ) : (
            <span className="muted">none (root)</span>
          )}
        </Fact>
      </dl>

      {span.span_type === "agent" && (
        <>
          {agentInput && (
            <Section title="Task">
              <p className="prose">
                <RedactedText text={agentInput} />
              </p>
            </Section>
          )}
          {agentOutput && (
            <Section title="Final answer">
              <p className="prose">
                <RedactedText text={agentOutput} />
              </p>
            </Section>
          )}
        </>
      )}

      {span.span_type === "tool" && (
        <>
          {args && (
            <Section title="Arguments">
              <CodeBlock value={args} label="Tool arguments" />
            </Section>
          )}
          {output && (
            <Section title="Output">
              <CodeBlock value={output} label="Tool output" />
            </Section>
          )}
        </>
      )}

      {span.span_type === "llm" && (
        <>
          {toolCalls && (
            <Section title="Requested tool calls">
              <CodeBlock value={toolCalls} label="Requested tool calls" />
            </Section>
          )}
          {completion && (
            <Section title="Reply">
              <p className="prose">
                <RedactedText text={completion} />
              </p>
            </Section>
          )}
          {prompt && (
            <Section title="Prompt sent to the model">
              <Transcript raw={prompt} />
            </Section>
          )}
        </>
      )}

      {span.events.length > 0 && (
        <Section title="Events">
          <Events events={span.events} />
        </Section>
      )}

      <Section title="All attributes">
        <details>
          <summary>{attrEntries.length} attributes</summary>
          <table className="attrs">
            <tbody>
              {attrEntries.map(([key, value]) => (
                <tr key={key}>
                  <th scope="row" className="mono">
                    {key}
                  </th>
                  <td className="mono">
                    <RedactedText text={typeof value === "string" ? value : JSON.stringify(value)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </Section>
    </aside>
  );
}
