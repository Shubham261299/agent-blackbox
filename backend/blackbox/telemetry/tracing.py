"""Span helper with a high-resolution clock.

Why: on Windows, `time.time_ns()` only advances about once per millisecond, so fast spans (scripted
tools run in microseconds) would get identical timestamps, zero durations and ambiguous ordering.
Here wall-clock time is anchored once and advanced with `perf_counter_ns()`.
"""
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer

_WALL_ANCHOR_NS = time.time_ns()
_PERF_ANCHOR_NS = time.perf_counter_ns()


def now_ns() -> int:
    return _WALL_ANCHOR_NS + (time.perf_counter_ns() - _PERF_ANCHOR_NS)


@contextmanager
def start_span(tracer: Tracer, name: str, attributes: Mapping[str, Any]) -> Iterator[Span]:
    """Start a span, make it current, and end it with a high-res timestamp.
    An exception escaping the block is recorded on the span (status ERROR) and re-raised."""
    span = tracer.start_span(name, attributes=attributes, start_time=now_ns())
    end_ns: int | None = None
    try:
        with trace.use_span(span, end_on_exit=False, record_exception=False, set_status_on_exception=False):
            yield span
    except Exception as exc:
        # Take the end time first: formatting the stack trace can cost tens of milliseconds and that
        # is our own overhead, not time the work took.
        end_ns = now_ns()
        span.record_exception(exc, timestamp=end_ns)
        span.set_status(Status(StatusCode.ERROR, f"{type(exc).__name__}: {exc}"))
        raise
    finally:
        span.end(end_time=end_ns if end_ns is not None else now_ns())
