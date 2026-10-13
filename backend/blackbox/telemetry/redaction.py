"""Redaction applied to spans *before* any exporter (SQLite, Jaeger) sees them.

OTel span processors only receive finished, read-only spans, so redaction is done by wrapping each
exporter: `RedactingExporter` rebuilds every span with scrubbed attributes/events/status.

Scope and limits (be honest about them): redaction is key-based (known sensitive field names inside JSON)
plus pattern-based (emails, card-like digit runs, local user-home paths in free text). Free-text PII that
matches neither -- e.g. a street address written in prose -- is NOT caught.
"""
import json
import re
from collections.abc import Sequence
from typing import Any

from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Status, StatusCode

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset({
    "customer_email", "email", "shipping_address", "new_address", "address", "phone",
    "card", "card_number", "password", "token", "api_key", "authorization", "secret",
})

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
# C:\Users\<name>\ , /Users/<name>/ , /home/<name>/ (stack traces leak local account names)
_HOME_PATH = re.compile(r"(?i)(?:[a-z]:)?[\\/](?:users|home)[\\/][^\\/\s\"']+")


def scrub_text(text: str) -> str:
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    text = _CARD.sub("[REDACTED_CARD]", text)
    return _HOME_PATH.sub("<user-home>", text)


def redact_obj(obj: Any, key: str | None = None) -> Any:
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(obj, dict):
        return {k: redact_obj(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, str):
        return redact_str(obj)
    return obj


def redact_str(value: str) -> str:
    """Strings that are themselves JSON (tool args/outputs, serialized messages) are redacted structurally."""
    stripped = value.lstrip()
    if stripped[:1] in ("{", "["):
        try:
            return json.dumps(redact_obj(json.loads(value)))
        except ValueError:
            pass
    return scrub_text(value)


def redact_attribute(key: str, value: Any) -> Any:
    if key.rsplit(".", 1)[-1].lower() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, str):
        return redact_str(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact_attribute(key, v) for v in value]
    return value


def redact_span(span: ReadableSpan) -> ReadableSpan:
    status = span.status
    description = scrub_text(status.description) if status.description else None
    new_status = Status(status.status_code, description if status.status_code == StatusCode.ERROR else None)
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes={k: redact_attribute(k, v) for k, v in (span.attributes or {}).items()},
        events=[
            Event(e.name, {k: redact_attribute(k, v) for k, v in (e.attributes or {}).items()}, e.timestamp)
            for e in span.events
        ],
        links=span.links,
        kind=span.kind,
        status=new_status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class RedactingExporter(SpanExporter):
    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([redact_span(s) for s in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)
