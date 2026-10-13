"""FastAPI app. Run with:  uvicorn --factory blackbox.api.main:create_app  (from ./backend)"""
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import BackgroundTasks, FastAPI, HTTPException
from opentelemetry.sdk.trace.export import SpanExporter

from blackbox.agent.loop import AgentResult, AgentRunner
from blackbox.agent.tools import OrderDesk
from blackbox.config import Settings, get_settings
from blackbox.llm.base import ModelClient
from blackbox.llm.ollama_client import OllamaClient
from blackbox.llm.scripted import SCENARIO_INFO, scripted_model
from blackbox.models import RunRecord, RunRequest, ScenarioInfo, SpanRecord
from blackbox.store.db import Store
from blackbox.telemetry.redaction import scrub_text
from blackbox.telemetry.setup import Telemetry

ModelFactory = Callable[[RunRequest, Settings], ModelClient]


def build_model(request: RunRequest, settings: Settings) -> ModelClient:
    if request.model == "ollama":
        return OllamaClient(settings.ollama_host, settings.ollama_model, settings.ollama_timeout_s)
    return scripted_model(request.scenario)  # KeyError for an unknown scenario


def create_app(
    settings: Settings | None = None,
    model_factory: ModelFactory = build_model,
    extra_exporters: tuple[SpanExporter, ...] = (),
) -> FastAPI:
    settings = settings or get_settings()
    store = Store(settings.db_path)
    telemetry = Telemetry(settings, store, extra_exporters)
    ollama_lock = threading.Lock()  # one local model in memory at a time (16 GB machine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        telemetry.shutdown()
        store.close()

    app = FastAPI(title="Agent Blackbox", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.telemetry = telemetry

    def execute_run(run_id: str, model: ModelClient, task: str) -> None:
        started = time.perf_counter()
        lock = ollama_lock if model.provider == "ollama" else None
        if lock:
            lock.acquire()
        try:
            runner = AgentRunner(model, OrderDesk().registry(), telemetry.tracer(), settings.max_agent_steps)
            result = runner.run(run_id, task)
        except Exception as exc:  # defensive: AgentRunner.run already converts agent errors into a result
            result = AgentResult("error", None, f"{type(exc).__name__}: {exc}", None, 0)
        finally:
            if lock:
                lock.release()
        duration_ms = (time.perf_counter() - started) * 1000  # agent time only, not export time
        telemetry.flush_store()
        store.finish_run(
            run_id,
            status=result.status,
            trace_id=result.trace_id,
            duration_ms=duration_ms,
            final_answer=scrub_text(result.final_answer) if result.final_answer else None,
            error=scrub_text(result.error) if result.error else None,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/scenarios", response_model=list[ScenarioInfo])
    def list_scenarios() -> list[ScenarioInfo]:
        return [ScenarioInfo(name=n, description=d, example_task=t) for n, (d, t) in SCENARIO_INFO.items()]

    @app.post("/runs", response_model=RunRecord, status_code=202)
    def start_run(request: RunRequest, background: BackgroundTasks) -> RunRecord:
        try:
            model = model_factory(request, settings)
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"unknown scenario {exc.args[0]!r}") from None
        run = RunRecord(
            run_id=f"run-{uuid.uuid4().hex[:8]}",
            task=scrub_text(request.task),
            model=f"{model.provider}:{model.name}",
            status="running",
            started_at=datetime.now(UTC).isoformat(),
        )
        store.create_run(run)
        background.add_task(execute_run, run.run_id, model, request.task)
        return run

    @app.get("/runs", response_model=list[RunRecord])
    def list_runs(limit: int = 100) -> list[RunRecord]:
        return store.list_runs(limit)

    @app.get("/runs/{run_id}", response_model=RunRecord)
    def get_run(run_id: str) -> RunRecord:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.get("/runs/{run_id}/spans", response_model=list[SpanRecord])
    def get_spans(run_id: str) -> list[SpanRecord]:
        if store.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        return store.get_spans(run_id)

    return app
