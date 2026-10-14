import pytest

from blackbox.agent.loop import AgentRunner
from blackbox.agent.tools import OrderDesk
from blackbox.config import Settings
from blackbox.store.db import Store
from blackbox.telemetry.setup import Telemetry


@pytest.fixture
def settings():
    return Settings(db_path=":memory:", otlp_endpoint=None)


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def telemetry(settings, store):
    t = Telemetry(settings, store)
    yield t
    t.shutdown()


@pytest.fixture
def service(settings, store, telemetry):
    from blackbox.agent.service import RunService

    return RunService(settings, store, telemetry)


@pytest.fixture
def run_agent(telemetry):
    def _run(model, task="Refund order 42, it arrived damaged.", run_id="run-test", max_steps=8):
        runner = AgentRunner(model, OrderDesk().registry(), telemetry.tracer(), max_steps)
        result = runner.run(run_id, task)
        telemetry.flush()  # spans are exported in the background; make them visible to assertions
        return result

    return _run
