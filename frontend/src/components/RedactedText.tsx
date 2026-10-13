import { prettyJson, splitRedactions } from "../lib/redaction";

/** Text where redaction markers are shown as chips, so it is obvious a value was removed on purpose. */
export function RedactedText({ text }: { text: string }) {
  return (
    <>
      {splitRedactions(text).map((part, i) =>
        part.redacted ? (
          <mark key={i} className="redacted" title="Removed before this was stored">
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  );
}

export function CodeBlock({ value, label }: { value: unknown; label: string }) {
  return (
    <pre className="code" tabIndex={0} aria-label={label}>
      <RedactedText text={prettyJson(value)} />
    </pre>
  );
}
