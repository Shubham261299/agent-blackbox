import json
import sqlite3
import threading

from blackbox.config import ensure_parent_dir
from blackbox.models import RunRecord, SpanRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    task         TEXT NOT NULL,
    model        TEXT NOT NULL,
    status       TEXT NOT NULL,
    trace_id     TEXT,
    started_at   TEXT NOT NULL,
    duration_ms  REAL,
    final_answer TEXT,
    error        TEXT
);
CREATE TABLE IF NOT EXISTS spans (
    span_id        TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL,
    trace_id       TEXT NOT NULL,
    parent_span_id TEXT,
    name           TEXT NOT NULL,
    span_type      TEXT NOT NULL,
    start_time_ns  INTEGER NOT NULL,
    end_time_ns    INTEGER NOT NULL,
    duration_ms    REAL NOT NULL,
    status         TEXT NOT NULL,
    status_message TEXT,
    attributes     TEXT NOT NULL,
    events         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spans_run ON spans(run_id, start_time_ns);
"""


class Store:
    """SQLite access for runs and the app's copy of spans. One shared connection guarded by a lock
    (FastAPI runs the agent in a worker thread)."""

    def __init__(self, db_path: str) -> None:
        ensure_parent_dir(db_path)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            if db_path != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ---- runs --------------------------------------------------------------------
    def create_run(self, run: RunRecord) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO runs (run_id, task, model, status, trace_id, started_at, duration_ms, final_answer, error)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (run.run_id, run.task, run.model, run.status, run.trace_id, run.started_at,
                 run.duration_ms, run.final_answer, run.error),
            )
            self._db.commit()

    def finish_run(self, run_id: str, *, status: str, trace_id: str | None, duration_ms: float,
                   final_answer: str | None, error: str | None) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE runs SET status=?, trace_id=?, duration_ms=?, final_answer=?, error=? WHERE run_id=?",
                (status, trace_id, duration_ms, final_answer, error, run_id),
            )
            self._db.commit()

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return RunRecord(**dict(row)) if row else None

    def list_runs(self, limit: int = 100) -> list[RunRecord]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
        return [RunRecord(**dict(r)) for r in rows]

    # ---- spans -------------------------------------------------------------------
    def upsert_spans(self, spans: list[SpanRecord]) -> None:
        rows = [
            (s.span_id, s.run_id, s.trace_id, s.parent_span_id, s.name, s.span_type, s.start_time_ns, s.end_time_ns,
             s.duration_ms, s.status, s.status_message, json.dumps(s.attributes), json.dumps(s.events))
            for s in spans
        ]
        with self._lock:
            self._db.executemany("INSERT OR REPLACE INTO spans VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            self._db.commit()

    def get_spans(self, run_id: str) -> list[SpanRecord]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM spans WHERE run_id=? ORDER BY start_time_ns, parent_span_id IS NOT NULL, rowid", (run_id,)
            ).fetchall()
        origin = min((r["start_time_ns"] for r in rows), default=0)
        return [
            SpanRecord(**{
                **dict(r),
                "attributes": json.loads(r["attributes"]),
                "events": json.loads(r["events"]),
                "start_offset_ms": (r["start_time_ns"] - origin) / 1e6,
            })
            for r in rows
        ]
