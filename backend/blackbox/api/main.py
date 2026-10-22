"""FastAPI app. Run with:  uvicorn --factory blackbox.api.main:create_app  (from ./backend)"""
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from opentelemetry.sdk.trace.export import SpanExporter

from blackbox.agent.config import AgentConfig, preset
from blackbox.agent.service import RunService
from blackbox.config import Settings, get_settings
from blackbox.evals.cases import load_dataset
from blackbox.evals.compare import ComparisonError, compare
from blackbox.evals.run_evaluation import build_run_evaluation
from blackbox.evals.runner import execute_evaluation, prepare_evaluation
from blackbox.llm.base import ModelClient
from blackbox.llm.ollama_client import OllamaClient
from blackbox.llm.scripted import SCENARIO_INFO, scripted_model
from blackbox.models import (
    Comparison,
    EvalReport,
    EvalRunSummary,
    RunEvaluation,
    RunFault,
    RunRecord,
    RunRequest,
    ScenarioInfo,
    SpanRecord,
    StartEvalRequest,
)
from blackbox.store.db import Store
from blackbox.telemetry.setup import Telemetry

ModelFactory = Callable[[RunRequest, Settings], ModelClient]


def agent_config(variant: str) -> AgentConfig:
    try:
        return preset(variant)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=exc.args[0]) from None


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
    service = RunService(settings, store, telemetry)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        telemetry.shutdown()
        store.close()

    app = FastAPI(title="Agent Blackbox", version="0.2.0", lifespan=lifespan)
    app.state.store = store
    app.state.telemetry = telemetry
    app.state.service = service

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/scenarios", response_model=list[ScenarioInfo])
    def list_scenarios() -> list[ScenarioInfo]:
        return [ScenarioInfo(name=n, description=d, example_task=t) for n, (d, t) in SCENARIO_INFO.items()]

    # ---- runs --------------------------------------------------------------------
    @app.post("/runs", response_model=RunRecord, status_code=202)
    def start_run(request: RunRequest, background: BackgroundTasks) -> RunRecord:
        try:
            model = model_factory(request, settings)
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"unknown scenario {exc.args[0]!r}") from None
        config = agent_config(request.variant)
        run = service.create_run(model, request.task, config)
        background.add_task(service.execute, run.run_id, model, request.task, None, None, config)
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

    @app.get("/runs/{run_id}/evaluation", response_model=RunEvaluation)
    def get_run_evaluation(run_id: str) -> RunEvaluation:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        found = store.find_eval_case_for_run(run_id)
        if run.status == "running" and not found:
            raise HTTPException(status_code=409, detail="run is still running")
        return build_run_evaluation(store, run, found)

    @app.get("/runs/{run_id}/faults", response_model=list[RunFault])
    def get_run_faults(run_id: str) -> list[RunFault]:
        """Ground truth for failure-lab runs (empty for every other run). Kept out of the trace on purpose."""
        if store.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        return store.get_run_faults(run_id)

    # ---- evaluations ---------------------------------------------------------------
    @app.get("/evals", response_model=list[EvalRunSummary])
    def list_evals(limit: int = 50) -> list[EvalRunSummary]:
        return store.list_eval_runs(limit)

    @app.get("/evals/compare", response_model=Comparison)
    def compare_evals(baseline: str, candidate: str) -> Comparison:
        """Before/after of two stored evaluations. 422 (with the reason) when they cannot be fairly compared."""
        reports = [store.get_eval_report(eval_id) for eval_id in (baseline, candidate)]
        missing = [eval_id for eval_id, r in zip((baseline, candidate), reports) if r is None]
        if missing:
            raise HTTPException(status_code=404, detail=f"evaluation not found: {', '.join(missing)}")
        try:
            return compare(store, reports[0], reports[1])  # type: ignore[arg-type]
        except ComparisonError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.get("/evals/{eval_id}", response_model=EvalReport)
    def get_eval(eval_id: str) -> EvalReport:
        report = store.get_eval_report(eval_id)
        if report is None:
            raise HTTPException(status_code=404, detail="evaluation not found")
        return report

    @app.post("/evals", response_model=EvalRunSummary, status_code=202)
    def start_eval(request: StartEvalRequest, background: BackgroundTasks) -> EvalRunSummary:
        """Scripted batches only (instant). Real-model benchmarks take minutes: use the CLI,
        `python -m blackbox.evals run --mode ollama`."""
        dataset = load_dataset()
        config = agent_config(request.variant)
        try:
            summary = prepare_evaluation(service, dataset, request.mode, config)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        background.add_task(execute_evaluation, service, dataset, request.mode, summary.eval_id, None, None, config)
        return summary

    return app
