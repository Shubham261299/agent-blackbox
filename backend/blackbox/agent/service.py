"""Runs one agent task end to end and records it. Shared by the API and the evaluation runner so there is
exactly one code path that creates runs."""
import threading
import time
import uuid
from datetime import UTC, datetime

from blackbox.agent.loop import AgentResult, AgentRunner
from blackbox.agent.tools import OrderDesk
from blackbox.config import Settings
from blackbox.llm.base import ModelClient
from blackbox.models import RunRecord
from blackbox.store.db import Store
from blackbox.telemetry.redaction import scrub_text
from blackbox.telemetry.setup import Telemetry


class RunService:
    def __init__(self, settings: Settings, store: Store, telemetry: Telemetry) -> None:
        self.settings = settings
        self.store = store
        self.telemetry = telemetry
        self._ollama_lock = threading.Lock()  # one local model in memory at a time (16 GB machine)

    def create_run(self, model: ModelClient, task: str) -> RunRecord:
        run = RunRecord(
            run_id=f"run-{uuid.uuid4().hex[:8]}",
            task=scrub_text(task),
            model=f"{model.provider}:{model.name}",
            status="running",
            started_at=datetime.now(UTC).isoformat(),
        )
        self.store.create_run(run)
        return run

    def execute(self, run_id: str, model: ModelClient, task: str, max_steps: int | None = None) -> None:
        started = time.perf_counter()
        lock = self._ollama_lock if model.provider == "ollama" else None
        if lock:
            lock.acquire()
        try:
            runner = AgentRunner(model, OrderDesk().registry(), self.telemetry.tracer(),
                                 max_steps or self.settings.max_agent_steps)
            result = runner.run(run_id, task)
        except Exception as exc:  # defensive: AgentRunner.run already converts agent errors into a result
            result = AgentResult("error", None, f"{type(exc).__name__}: {exc}", None, 0)
        finally:
            if lock:
                lock.release()
        duration_ms = (time.perf_counter() - started) * 1000  # agent time only, not export time
        self.telemetry.flush_store()
        self.store.finish_run(
            run_id,
            status=result.status,
            trace_id=result.trace_id,
            duration_ms=duration_ms,
            final_answer=scrub_text(result.final_answer) if result.final_answer else None,
            error=scrub_text(result.error) if result.error else None,
        )

    def run_sync(self, model: ModelClient, task: str, max_steps: int | None = None) -> RunRecord:
        run = self.create_run(model, task)
        self.execute(run.run_id, model, task, max_steps)
        finished = self.store.get_run(run.run_id)
        assert finished is not None
        return finished
