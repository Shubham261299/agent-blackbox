/** Markers the backend writes in place of sensitive values: [REDACTED], [REDACTED_EMAIL], [REDACTED_CARD]. */
const MARKER = /\[REDACTED(?:_[A-Z]+)?\]/g;

export interface TextPart {
  text: string;
  redacted: boolean;
}

/** Split text so redaction markers can be rendered as chips. */
export function splitRedactions(text: string): TextPart[] {
  const parts: TextPart[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    const at = match.index ?? 0;
    if (at > last) parts.push({ text: text.slice(last, at), redacted: false });
    parts.push({ text: match[0], redacted: true });
    last = at + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), redacted: false });
  return parts;
}

export function countRedactions(value: unknown): number {
  if (typeof value === "string") return (value.match(MARKER) ?? []).length;
  if (Array.isArray(value)) return value.reduce<number>((n, v) => n + countRedactions(v), 0);
  if (value && typeof value === "object")
    return Object.values(value).reduce<number>((n, v) => n + countRedactions(v), 0);
  return 0;
}

/** Attribute values are often JSON stored as strings; show them structured when they parse. */
export function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  if (trimmed[0] !== "{" && trimmed[0] !== "[") return value;
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

export function prettyJson(value: unknown): string {
  const parsed = parseMaybeJson(value);
  return typeof parsed === "string" ? parsed : JSON.stringify(parsed, null, 2);
}
