"""The Docker files cannot be built by the test suite (and the Jaeger container on a developer's machine must never be
disturbed), so what can silently go wrong is checked as text: the settings names the containers use are the ones the
app reads, the dependency groups keep the API image small, and nothing is published or run that should not be."""
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
API = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
WEB = (ROOT / "Dockerfile.web").read_text(encoding="utf-8")
NGINX = (ROOT / "nginx.conf").read_text(encoding="utf-8")
CONFIG = (ROOT / "backend" / "blackbox" / "config.py").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def service(name):
    """The text of one top-level service block."""
    match = re.search(rf"^  {name}:\n((?:    .*\n|\n)+)", COMPOSE, re.M)
    assert match, name
    return match[1]


def test_the_settings_the_api_container_gets_are_ones_the_app_reads():
    env = set(re.findall(r"^      (BLACKBOX_\w+):", service("api"), re.M))
    assert env == {"BLACKBOX_DB_PATH", "BLACKBOX_OTLP_ENDPOINT", "BLACKBOX_OLLAMA_HOST"}
    for name in env:
        assert f'"{name}"' in CONFIG, name


def test_the_api_exports_traces_to_the_jaeger_service_and_reaches_the_model_on_the_host():
    api = service("api")
    assert "BLACKBOX_OTLP_ENDPOINT: http://jaeger:4318/v1/traces" in api
    assert "http://host.docker.internal:11434" in api and "host.docker.internal:host-gateway" in api
    assert "services:\n  jaeger:" in COMPOSE  # the service name the URL above relies on


def test_results_survive_a_restart_and_nothing_but_the_dashboard_and_jaeger_is_published():
    assert "blackbox-data:/data" in service("api") and re.search(r"^volumes:\n  blackbox-data:", COMPOSE, re.M)
    assert "ports:" not in service("api")  # the dashboard forwards /api; the API is not exposed to the network
    assert '"${BLACKBOX_PORT:-8080}:80"' in service("web")


def test_every_published_port_can_be_moved_by_the_environment():
    ports = re.findall(r'^      - "([^"]+)"\s', service("jaeger") + service("web"), re.M)
    published = [p for p in ports if re.search(r":\d+(/\w+)?$", p)]
    assert published and all(p.startswith("${") for p in published), published


def test_services_come_back_after_a_docker_restart_and_jaeger_is_pinned():
    for name in ("jaeger", "api", "web"):
        assert "restart: unless-stopped" in service(name), name
    assert re.search(r"image: jaegertracing/jaeger:\d+\.\d+\.\d+\n", COMPOSE)  # never :latest
    assert "container_name: ${BLACKBOX_JAEGER_NAME:-jaeger}" in COMPOSE  # the documented name, movable for a second copy


def test_the_dashboard_waits_for_a_healthy_api():
    assert "condition: service_healthy" in service("web")
    assert re.search(r"^HEALTHCHECK ", API, re.M) and "/health" in API


def test_the_api_image_runs_as_a_normal_user_and_installs_only_the_runtime():
    assert re.search(r"^USER blackbox$", API, re.M) and "useradd" in API
    assert re.search(r"pip install --no-cache-dir -e \.( |$)", API) and "[dev" not in API and "[judge" not in API
    assert "BLACKBOX_DB_PATH=/data/blackbox.db" in API
    assert "--factory" in API and "blackbox.api.main:create_app" in API


def test_the_runtime_dependencies_do_not_include_tests_the_gif_tool_or_the_judge():
    runtime = " ".join(PYPROJECT["project"]["dependencies"]).lower()
    for heavy in ("pytest", "pillow", "deepeval"):
        assert heavy not in runtime, heavy
    extras = PYPROJECT["project"]["optional-dependencies"]
    assert any(d.startswith("pytest") for d in extras["dev"]) and any(d.startswith("pillow") for d in extras["dev"])
    assert any(d.startswith("deepeval") for d in extras["judge"])
    assert "httpx" in runtime  # imported directly by the agent


def test_everything_the_runtime_imports_directly_is_declared():
    declared = {re.split(r"[=<>\[]", d)[0].strip().lower().replace("_", "-") for d in PYPROJECT["project"]["dependencies"]}
    imported = set()
    for path in (ROOT / "backend" / "blackbox").rglob("*.py"):
        imported.update(re.findall(r"^(?:import|from) (\w+)", path.read_text(encoding="utf-8"), re.M))
    third_party = {"httpx": "httpx", "fastapi": "fastapi", "uvicorn": "uvicorn", "ollama": "ollama", "opentelemetry": "opentelemetry-sdk"}
    for module, package in third_party.items():
        if module in imported:
            assert package in declared, f"{module} is imported but {package} is not a dependency"
    assert not imported & {"deepeval", "pytest", "PIL"}


def test_nginx_forwards_api_without_its_prefix_and_serves_the_app_for_every_other_path():
    assert re.search(r"location /api/ \{[^}]*proxy_pass http://api:8000/;", NGINX, re.S)  # the trailing slash strips /api
    assert "try_files $uri /index.html;" in NGINX


def test_the_dashboard_image_builds_the_live_app_from_the_lockfile_and_serves_it_with_nginx():
    assert "npm ci" in WEB and "npm run build\n" in WEB and "build:demo" not in WEB
    assert "COPY nginx.conf /etc/nginx/conf.d/default.conf" in WEB and "/app/dist" in WEB
    assert re.search(r"^FROM nginx:\d+\.\d+-alpine$", WEB, re.M) and re.search(r"^FROM node:22", WEB, re.M)


def test_the_build_context_leaves_out_local_state():
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for must in (".git", ".venv", "data", "frontend/node_modules", "**/*.db"):
        assert must in ignore, must


@pytest.mark.parametrize("path", ["Dockerfile.api", "Dockerfile.web", "nginx.conf", "docker-compose.yml", ".dockerignore"])
def test_the_files_use_unix_line_endings(path):
    assert b"\r" not in (ROOT / path).read_bytes()


# ---- licence ------------------------------------------------------------------------------------------
def test_the_licence_is_the_standard_mit_text_in_the_owners_name():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License\n\nCopyright (c) 2026 Shubham Jamdar\n")
    for clause in ("Permission is hereby granted, free of charge", "THE SOFTWARE IS PROVIDED \"AS IS\"", "The above copyright notice and this permission notice shall be included"):
        assert clause in text


def test_the_notices_name_every_runtime_dependency_and_the_readme_points_at_both_files():
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").lower()
    for dep in PYPROJECT["project"]["dependencies"]:
        name = re.split(r"[=<>\[]", dep)[0].strip().lower()
        short = name.removesuffix("-sdk").removesuffix("-exporter-otlp") if name.startswith("opentelemetry") else name
        assert short in notices, name
    assert "react" in notices and "jaeger" in notices
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "[LICENSE](LICENSE)" in readme and "[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)" in readme


def test_the_notices_make_no_claim_the_licence_file_contradicts():
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "MIT licensed (see [LICENSE](LICENSE))" in notices
    assert not re.search(r"\bGPL\b|AGPL|LGPL", notices)
