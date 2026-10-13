import json

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from blackbox.telemetry.redaction import REDACTED, RedactingExporter, redact_str, scrub_text


def test_scrub_text_patterns():
    assert scrub_text("mail ava@example.com now") == "mail [REDACTED_EMAIL] now"
    assert "[REDACTED_CARD]" in scrub_text("card 4111 1111 1111 1111 on file")
    assert "jdoe" not in scrub_text(r'File "C:\Users\jdoe\proj\x.py", line 3')
    assert scrub_text("order 42 refund 59.90") == "order 42 refund 59.90"  # ordinary numbers survive


def test_redact_json_by_key():
    raw = json.dumps({"order_id": 42, "customer_email": "ava@example.com", "shipping_address": "12 Birch Lane"})
    out = json.loads(redact_str(raw))
    assert out == {"order_id": 42, "customer_email": REDACTED, "shipping_address": REDACTED}


def test_redact_json_nested_inside_json_string():
    # a serialized prompt contains tool results as *strings of JSON*
    inner = json.dumps({"customer_email": "ava@example.com", "shipping_address": "12 Birch Lane", "total": 59.9})
    outer = json.dumps([{"role": "tool", "content": inner}])
    out = redact_str(outer)
    assert "Birch" not in out and "example.com" not in out and "59.9" in out


def test_non_json_text_falls_back_to_pattern_scrub():
    assert redact_str("{not json ava@example.com") == "{not json [REDACTED_EMAIL]"


@pytest.fixture
def captured():
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(RedactingExporter(memory)))
    yield provider.get_tracer("t"), memory
    provider.shutdown()


def test_exporter_redacts_attributes_events_and_status(captured):
    tracer, memory = captured
    with tracer.start_as_current_span("tool.x", attributes={
        "blackbox.tool.output": json.dumps({"customer_email": "ava@example.com", "total": 1}),
        "user.email": "ava@example.com",
        "note": "contact bob@example.com",
        "blackbox.run_id": "run-1",
    }) as span:
        span.add_event("tool.result", {"summary": "sent to carl@example.com"})
        span.set_status(Status(StatusCode.ERROR, "failed for dana@example.com"))
    (exported,) = memory.get_finished_spans()
    dump = json.dumps({"a": dict(exported.attributes), "e": [dict(e.attributes) for e in exported.events],
                       "s": exported.status.description})
    assert "example.com" not in dump
    assert exported.attributes["user.email"] == REDACTED
    assert exported.attributes["blackbox.run_id"] == "run-1"  # non-sensitive values untouched
    assert exported.events[0].name == "tool.result"
    assert exported.status.status_code == StatusCode.ERROR
    assert exported.name == "tool.x" and exported.context.span_id and exported.end_time >= exported.start_time
