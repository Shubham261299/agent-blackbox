"""The tracer must not charge its own bookkeeping to the work it measures."""
import time

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from blackbox.llm.scripted import scripted_model
from blackbox.telemetry.tracing import start_span


class SlowToDescribe(Exception):
    """Recording an exception calls str() on it; make that deliberately slow."""

    def __str__(self) -> str:
        time.sleep(0.08)
        return "slow"


@pytest.fixture
def traced():
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    yield provider.get_tracer("t"), memory
    provider.shutdown()


def test_exception_recording_time_is_not_counted_in_the_span(traced):
    tracer, memory = traced
    with pytest.raises(SlowToDescribe):
        with start_span(tracer, "work", {}):
            pass  # the work itself takes microseconds
            raise SlowToDescribe()
    (span,) = memory.get_finished_spans()
    assert span.status.status_code.name == "ERROR"
    assert [e.name for e in span.events] == ["exception"]
    assert (span.end_time - span.start_time) / 1e6 < 20  # ms; the 80+ ms of str() happened after the end time


def test_expected_tool_failure_is_cheap_and_has_no_stack_trace(run_agent, store):
    run_agent(scripted_model("unknown_order"))
    failed = next(s for s in store.get_spans("run-test") if s.name == "tool.lookup_order")
    (event,) = failed.events
    assert event["attributes"]["exception.type"].endswith("ToolError")
    assert event["attributes"]["exception.message"] == "order 999 not found"
    assert "exception.stacktrace" not in event["attributes"]
    assert failed.duration_ms < 10  # was ~31 ms when a stack trace was formatted inside the span
