"""Writes the app's own copy of every span to SQLite so the UI never depends on Jaeger's query API."""
from collections.abc import Sequence
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode

from blackbox.models import SpanRecord
from blackbox.store.db import Store
from blackbox.telemetry import attributes as attr

_STATUS = {StatusCode.UNSET: "unset", StatusCode.OK: "ok", StatusCode.ERROR: "error"}
_SPAN_TYPES = {"agent", "llm", "tool"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def to_record(span: ReadableSpan) -> SpanRecord | None:
    attrs = {k: _jsonable(v) for k, v in (span.attributes or {}).items()}
    run_id = attrs.get(attr.RUN_ID)
    if run_id is None:  # not one of ours; cannot be attached to a run
        return None
    span_type = attrs.get(attr.SPAN_TYPE)
    return SpanRecord(
        span_id=format(span.context.span_id, "016x"),
        run_id=run_id,
        trace_id=format(span.context.trace_id, "032x"),
        parent_span_id=format(span.parent.span_id, "016x") if span.parent else None,
        name=span.name,
        span_type=span_type if span_type in _SPAN_TYPES else "other",
        start_time_ns=span.start_time,
        end_time_ns=span.end_time,
        duration_ms=(span.end_time - span.start_time) / 1e6,
        status=_STATUS[span.status.status_code],
        status_message=span.status.description,
        attributes=attrs,
        events=[
            {"name": e.name, "timestamp_ns": e.timestamp, "attributes": {k: _jsonable(v) for k, v in (e.attributes or {}).items()}}
            for e in span.events
        ],
    )


class SQLiteSpanExporter(SpanExporter):
    def __init__(self, store: Store) -> None:
        self._store = store

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        records = [r for r in (to_record(s) for s in spans) if r is not None]
        if records:
            self._store.upsert_spans(records)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
