"""Guards the 'nothing leaves the machine' rule against DeepEval's built-in analytics."""
import os
import sys


def test_deepeval_pytest_plugin_is_disabled(pytestconfig):
    assert not pytestconfig.pluginmanager.hasplugin("deepeval")


def test_deepeval_telemetry_is_opted_out():
    import blackbox  # noqa: F401  (sets the opt-out on import)

    assert os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] == "YES"
    from deepeval.telemetry.client import telemetry_opt_out

    assert telemetry_opt_out() is True
    assert "deepeval" in sys.modules
