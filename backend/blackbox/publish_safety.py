"""Makes recorded data safe to publish, and checks that it is.

The demo bakes stored runs into a public website. Redaction at record time already scrubs the home directory
(`<user-home>`), but what follows it in a stack trace still names the folders the project lived in. `publishable`
rewrites those paths to repository-relative ones; `audit` is the independent check that fails when anything
machine-specific or secret-looking is left, whatever the export did.
"""
import getpass
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from blackbox.config import REPO_ROOT

HOME_PLACEHOLDER = "<user-home>"
PROJECT_FOLDER = "agent-blackbox"  # what the repository folder was called when the stored runs were recorded
# `<user-home>\<folders>\agent-blackbox\backend\x.py`: everything up to and including the repository folder.
_REPO_PREFIX = re.compile(re.escape(HOME_PLACEHOLDER) + r"[\\/].*?[\\/]" + re.escape(PROJECT_FOLDER) + r"[\\/]")
_VENV_PREFIX = re.compile(r"\.venv[\\/]Lib[\\/]site-packages[\\/]|\.venv[\\/]lib[\\/]python[\d.]+[\\/]site-packages[\\/]")
_FILE_LINE = re.compile(r'File "([^"]+)"')

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_HOME_PATH = re.compile(r"(?:^|[\s\"'(=])(?:/home/|/Users/|/root/)|[\\/]Users[\\/][^\\/\s]+[\\/]", re.IGNORECASE)
_SECRETS = {
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"),
    "API key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "AWS key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "bearer token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# Folder names that say nothing about whose machine it is (on a CI runner the repository sits under .../work/...).
_GENERIC_FOLDERS = {"work", "home", "user", "users", "code", "repos", "repo", "src", "dev", "docs", "source", "projects"}
ALLOWED_EMAIL_DOMAIN = "example.com"


def _clean_path(match: re.Match[str]) -> str:
    path = _VENV_PREFIX.sub("site-packages/", _REPO_PREFIX.sub("", match.group(1)))
    return f'File "{path.replace(chr(92), "/")}"'


def publishable_text(text: str) -> str:
    """Rewrite machine-specific file paths (in stack traces) to repository-relative ones. Other text is untouched."""
    if HOME_PLACEHOLDER not in text:
        return text
    return _FILE_LINE.sub(_clean_path, text)


def publishable(value: Any) -> Any:
    """`publishable_text` applied to every string in a JSON-like structure (returns a copy)."""
    if isinstance(value, str):
        return publishable_text(value)
    if isinstance(value, list):
        return [publishable(v) for v in value]
    if isinstance(value, dict):
        return {k: publishable(v) for k, v in value.items()}
    return value


def machine_identifiers(home: Path | None = None, repo_root: Path = REPO_ROOT, user: str | None = None) -> list[str]:
    """Names that identify this machine or its owner: the account name, the home folder, and the folders between the
    home folder and the repository. The repository's own folder is public (it is the project name) and is not one."""
    home = home or Path.home()
    names = [user if user is not None else _safe_user(), home.name]
    try:
        names += list(repo_root.relative_to(home).parts[:-1])
    except ValueError:
        pass
    seen: list[str] = []
    for name in names:
        if len(name) >= 4 and name.lower() not in _GENERIC_FOLDERS and name.lower() != repo_root.name.lower() and name not in seen:
            seen.append(name)
    return seen


def _safe_user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - no account name available (some containers): nothing to look for
        return ""


def _strings(value: Any, where: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield where, value
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{where}[{i}]")
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(k, f"{where}.<key>")
            yield from _strings(v, f"{where}.{k}")


def audit(value: Any, identifiers: Iterable[str] | None = None) -> list[str]:
    """Everything in `value` that should not be published, as `<where>: <what>` lines (empty when clean).
    `identifiers` defaults to this machine's, see `machine_identifiers`."""
    names = list(machine_identifiers() if identifiers is None else identifiers)
    name_patterns = [(n, re.compile(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])", re.IGNORECASE)) for n in names if n]
    problems: list[str] = []
    for where, text in _strings(value):
        if HOME_PLACEHOLDER in text:
            problems.append(f"{where}: home-directory placeholder left in a path")
        if _DRIVE_PATH.search(text) or _HOME_PATH.search(text):
            problems.append(f"{where}: absolute file path")
        for email in _EMAIL.findall(text):
            if not email.lower().endswith("@" + ALLOWED_EMAIL_DOMAIN):
                problems.append(f"{where}: email address {email!r}")
        for label, pattern in _SECRETS.items():
            if pattern.search(text):
                problems.append(f"{where}: looks like a {label}")
        for name, pattern in name_patterns:
            if pattern.search(text):
                problems.append(f"{where}: this machine's name {name!r}")
    return problems
