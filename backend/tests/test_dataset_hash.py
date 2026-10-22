"""A dataset's hash identifies its content, not the line endings a machine happened to check it out with, and
evaluations stored under the old (Windows-only) hash are migrated to it without touching anything else."""
import sqlite3

import pytest

from blackbox.evals.cases import (
    DATASETS_DIR,
    content_hash,
    dataset_hash_migrations,
    legacy_content_hash,
    load_dataset,
)
from blackbox.store.db import Store

NAMES = ["golden-v2", "golden-v3", "holdout-v1"]
# Pinned: if one of these changes, a dataset's content changed (or the hash rule did) and every stored result that
# names the old value no longer says which cases it ran.
HASH = {"golden-v2": "c703c519168a", "golden-v3": "82acd02d8a18", "holdout-v1": "8c7eb9ea4eb0"}
# What Days 3-5 stored on Windows, where the files were checked out with CRLF.
LEGACY = {"golden-v2": "e6a742cd5224", "golden-v3": "7bb5852c6198"}


def write_variant(tmp_path, name, ending):
    raw = (DATASETS_DIR / f"{name}.json").read_bytes().replace(b"\r\n", b"\n")
    folder = tmp_path / ("crlf" if b"\r" in ending else "lf")
    folder.mkdir(exist_ok=True)
    (folder / f"{name}.json").write_bytes(raw.replace(b"\n", ending))
    return folder


@pytest.mark.parametrize("name", NAMES)
def test_the_hash_is_the_same_whatever_the_line_endings(tmp_path, name):
    lf = load_dataset(name, write_variant(tmp_path, name, b"\n"))
    crlf = load_dataset(name, write_variant(tmp_path, name, b"\r\n"))
    assert lf.content_hash == crlf.content_hash == load_dataset(name).content_hash == HASH[name]


def test_a_real_change_to_the_content_still_changes_the_hash(tmp_path):
    folder = write_variant(tmp_path, "golden-v3", b"\n")
    path = folder / "golden-v3.json"
    original = load_dataset("golden-v3", folder).content_hash
    path.write_bytes(path.read_bytes().replace(b"Order 42 arrived damaged", b"Order 42 arrived broken"))
    assert load_dataset("golden-v3", folder).content_hash != original


def test_a_mixed_file_hashes_like_a_clean_one():
    raw = b'{"a": 1,\r\n "b": 2,\n "c": 3}\r\n'
    assert content_hash(raw) == content_hash(raw.replace(b"\r\n", b"\n")) == content_hash(raw.replace(b"\n", b"\r\n").replace(b"\r\r\n", b"\r\n"))


@pytest.mark.parametrize("name", ["golden-v2", "golden-v3"])
def test_the_old_windows_hash_is_still_computable_so_it_can_be_migrated(name):
    raw = (DATASETS_DIR / f"{name}.json").read_bytes()
    assert legacy_content_hash(raw) == LEGACY[name]
    assert content_hash(raw) == HASH[name] != LEGACY[name]


def test_the_migration_table_lists_every_dataset_with_its_old_and_new_hash():
    table = {version: (old, new) for version, old, new in dataset_hash_migrations()}
    assert set(table) >= set(NAMES)
    assert table["golden-v3"] == (LEGACY["golden-v3"], HASH["golden-v3"])
    assert table["golden-v2"] == (LEGACY["golden-v2"], HASH["golden-v2"])


# ---- migrating stored evaluations ---------------------------------------------------------------------
def make_db(path, rows):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE eval_runs (eval_id TEXT PRIMARY KEY, kind TEXT NOT NULL, model TEXT NOT NULL,
                                dataset_version TEXT NOT NULL, dataset_hash TEXT NOT NULL, seed INTEGER,
                                started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL);""")
    db.executemany("INSERT INTO eval_runs VALUES (?, 'benchmark', 'ollama:x', ?, ?, 0, '2026-10-01T00:00:00+00:00', NULL, 'done')", rows)
    db.commit()
    db.close()


def hashes(path):
    db = sqlite3.connect(path)
    try:
        return dict(db.execute("SELECT eval_id, dataset_hash FROM eval_runs"))
    finally:
        db.close()


def test_stored_evaluations_get_the_new_hash_and_nothing_else_changes(tmp_path):
    path = str(tmp_path / "old.db")
    make_db(path, [
        ("old-v3", "golden-v3", LEGACY["golden-v3"]),      # made on Windows before the change: migrated
        ("old-v2", "golden-v2", LEGACY["golden-v2"]),      # likewise
        ("new-v3", "golden-v3", HASH["golden-v3"]),        # made on Linux, or after the change: already right
        ("holdout", "holdout-v1", HASH["holdout-v1"]),     # was always the same (LF file)
        ("odd", "golden-v3", "0123456789ab"),              # a hash this scheme never produced: left alone
        ("other", "some-other-set", LEGACY["golden-v3"]),  # the same string under another dataset: left alone
    ])
    Store(path).close()
    assert hashes(path) == {
        "old-v3": HASH["golden-v3"], "old-v2": HASH["golden-v2"], "new-v3": HASH["golden-v3"],
        "holdout": HASH["holdout-v1"], "odd": "0123456789ab", "other": LEGACY["golden-v3"]}


def test_the_migration_is_safe_to_run_on_every_start(tmp_path):
    path = str(tmp_path / "old.db")
    make_db(path, [("old-v3", "golden-v3", LEGACY["golden-v3"])])
    for _ in range(3):
        Store(path).close()
        assert hashes(path) == {"old-v3": HASH["golden-v3"]}


def test_old_and_new_evaluations_become_comparable_after_migration(tmp_path):
    from blackbox.evals.compare import ComparisonError, compare
    from blackbox.models import EvalReport

    path = str(tmp_path / "old.db")
    make_db(path, [("before", "golden-v3", LEGACY["golden-v3"]), ("after", "golden-v3", HASH["golden-v3"])])
    store = Store(path)
    reports = {i: store.get_eval_report(i) for i in ("before", "after")}
    assert isinstance(reports["before"], EvalReport) and reports["before"].dataset_hash == reports["after"].dataset_hash
    try:
        compare(store, reports["before"], reports["after"])
    except ComparisonError as exc:  # the empty evaluations may be refused for other reasons, but never for different cases
        assert "different cases" not in str(exc)
    store.close()
