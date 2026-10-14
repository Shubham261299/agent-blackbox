from pathlib import Path

from blackbox.config import DEFAULT_DB_PATH, REPO_ROOT, Settings, get_settings


def test_default_database_path_does_not_depend_on_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("BLACKBOX_DB_PATH", raising=False)
    here = get_settings().db_path
    monkeypatch.chdir(tmp_path)
    assert get_settings().db_path == here == DEFAULT_DB_PATH
    assert Path(here).is_absolute() and Path(here) == REPO_ROOT / "data" / "blackbox.db"
    assert (REPO_ROOT / "pyproject.toml").exists()  # REPO_ROOT really is the project root


def test_environment_overrides_the_database_path(monkeypatch):
    monkeypatch.setenv("BLACKBOX_DB_PATH", "elsewhere.db")
    assert get_settings().db_path == "elsewhere.db"
    assert Settings().db_path == DEFAULT_DB_PATH
