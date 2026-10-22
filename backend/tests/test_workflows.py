"""The GitHub Actions files cannot be run here, so what can go wrong silently is checked as text: that they use the
versions and paths the project really has, ask for no more permission than they need, and use no secret."""
import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8") if (WORKFLOWS / "ci.yml").exists() else ""
PAGES = (WORKFLOWS / "pages.yml").read_text(encoding="utf-8") if (WORKFLOWS / "pages.yml").exists() else ""
pytestmark = pytest.mark.skipif(not CI, reason="no workflows in this checkout")


def files():
    return {p.name: p.read_text(encoding="utf-8") for p in WORKFLOWS.glob("*.yml")}


def test_python_is_the_version_the_project_requires():
    requires = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["requires-python"]
    assert requires == ">=3.12,<3.13"
    assert 'python-version: "3.12"' in CI


def test_node_satisfies_what_vite_and_vitest_need():
    for text in (CI, PAGES):
        assert re.search(r"node-version: 22\b", text)


def test_the_demo_that_is_published_is_the_folder_the_build_writes():
    config = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    out = re.search(r'outDir: mode === "demo" \? "([^"]+)"', config)
    assert out and f"path: frontend/{out[1]}" in PAGES
    scripts = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert "build:demo" in scripts and "npm run build:demo" in PAGES and "npm run build:demo" in CI
    assert "npm test" in CI and "npx tsc --noEmit" in CI


def test_the_jaeger_test_is_left_out_of_ci_and_the_marker_exists():
    assert '-m "not integration"' in CI
    assert "integration:" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_the_lockfile_the_cache_and_the_install_use_exists():
    assert (ROOT / "frontend" / "package-lock.json").is_file()
    for text in (CI, PAGES):
        assert "cache-dependency-path: frontend/package-lock.json" in text and "npm ci" in text


def test_every_action_is_pinned_to_a_major_version():
    for name, text in files().items():
        uses = re.findall(r"uses:\s*(\S+)", text)
        assert uses, name
        assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@v\d+", u) for u in uses), (name, uses)


def test_permissions_are_the_least_that_work_and_no_secret_is_used():
    assert re.search(r"^permissions:\n  contents: read\n(?!  \w)", CI, re.M)
    assert "pages: write" in PAGES and "id-token: write" in PAGES
    assert "contents: write" not in PAGES + CI
    for name, text in files().items():
        assert "secrets." not in text, name
        assert "pull_request_target" not in text, name


def test_the_pages_job_deploys_from_main_only_and_can_be_started_by_hand():
    assert "branches: [main]" in PAGES and "workflow_dispatch:" in PAGES
    assert "environment:\n      name: github-pages" in PAGES


def test_the_readme_badge_shows_the_workflow_that_exists_in_this_repository():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "github.com/Shubham261299/agent-blackbox/actions/workflows/ci.yml/badge.svg" in readme
    assert (WORKFLOWS / "ci.yml").is_file() and CI.startswith("name: CI\n")
