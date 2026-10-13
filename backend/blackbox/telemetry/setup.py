from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Tracer

from blackbox.config import Settings
from blackbox.store.db import Store
from blackbox.telemetry.redaction import RedactingExporter
from blackbox.telemetry.sqlite_exporter import SQLiteSpanExporter


class Telemetry:
    """Owns a TracerProvider (deliberately not the global one, so tests and apps can each have their own)."""

    def __init__(self, settings: Settings, store: Store, extra_exporters: tuple[SpanExporter, ...] = ()) -> None:
        self.provider = TracerProvider(resource=Resource.create({"service.name": settings.service_name}))
        # SQLite: exported on a background thread so our own DB writes never inflate the duration of the
        # span being measured. Callers must flush() when a run ends (the API does, before marking it done).
        self._store_processor = BatchSpanProcessor(RedactingExporter(SQLiteSpanExporter(store)))
        self.provider.add_span_processor(self._store_processor)
        # Jaeger: best-effort batched OTLP/HTTP. An unreachable Jaeger must never break or delay a run.
        if settings.otlp_endpoint:
            otlp = OTLPSpanExporter(endpoint=settings.otlp_endpoint, timeout=5)
            self.provider.add_span_processor(
                BatchSpanProcessor(RedactingExporter(otlp), schedule_delay_millis=1000)
            )
        for exporter in extra_exporters:
            self.provider.add_span_processor(SimpleSpanProcessor(RedactingExporter(exporter)))

    def tracer(self) -> Tracer:
        return self.provider.get_tracer("blackbox.agent")

    def flush_store(self) -> None:
        """Wait for the SQLite copy only. A run is finished when the app's own data is complete;
        Jaeger export is best-effort and must not hold it up."""
        self._store_processor.force_flush()

    def flush(self) -> None:
        """Wait for every exporter, Jaeger included (can block up to the OTLP timeout if Jaeger is down)."""
        self.provider.force_flush()

    def shutdown(self) -> None:
        self.provider.shutdown()
