import json
import sqlite3
import threading
from collections.abc import Collection

from blackbox.config import ensure_parent_dir
from blackbox.models import (
    CategorySummary,
    CheckResult,
    EvalCaseResult,
    EvalReport,
    EvalRunSummary,
    MetricSummary,
    RunFault,
    RunRecord,
    SpanRecord,
)

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
    error        TEXT,
    variant      TEXT NOT NULL DEFAULT 'baseline'
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
CREATE TABLE IF NOT EXISTS eval_runs (
    eval_id         TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    model           TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    dataset_hash    TEXT NOT NULL,
    seed            INTEGER,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,
    variant         TEXT NOT NULL DEFAULT 'baseline',
    rescored_from   TEXT
);
CREATE TABLE IF NOT EXISTS eval_cases (
    eval_id     TEXT NOT NULL,
    case_id     TEXT NOT NULL,
    category    TEXT NOT NULL,
    task        TEXT NOT NULL,
    run_id      TEXT NOT NULL,
    run_status  TEXT NOT NULL,
    passed      INTEGER NOT NULL,
    duration_ms REAL,
    note        TEXT,
    PRIMARY KEY (eval_id, case_id)
);
CREATE INDEX IF NOT EXISTS idx_eval_cases_run ON eval_cases(run_id);
CREATE TABLE IF NOT EXISTS run_faults (
    run_id         TEXT NOT NULL,
    idx            INTEGER NOT NULL,
    kind           TEXT NOT NULL,
    tool           TEXT,
    occurrence     INTEGER NOT NULL,
    description    TEXT NOT NULL,
    origin_span_id TEXT,
    fired          INTEGER NOT NULL,
    PRIMARY KEY (run_id, idx)
);
CREATE TABLE IF NOT EXISTS eval_results (
    eval_id  TEXT NOT NULL,
    case_id  TEXT NOT NULL,
    metric   TEXT NOT NULL,
    passed   INTEGER,
    score    REAL,
    gating   INTEGER NOT NULL,
    reason   TEXT NOT NULL,
    span_ids TEXT NOT NULL,
    details  TEXT NOT NULL,
    PRIMARY KEY (eval_id, case_id, metric)
);
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
            self._add_missing_columns()
            self._migrate_dataset_hashes()

    def _add_missing_columns(self) -> None:
        """Databases made before a column existed keep working: CREATE TABLE IF NOT EXISTS does not add columns, so
        add them here. Every row written before variants existed came from the baseline agent, hence the default."""
        for table, column, definition in (
            ("runs", "variant", "TEXT NOT NULL DEFAULT 'baseline'"),
            ("eval_runs", "variant", "TEXT NOT NULL DEFAULT 'baseline'"),
            ("eval_runs", "rescored_from", "TEXT"),
        ):
            have = {row[1] for row in self._db.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        self._db.commit()

    def _migrate_dataset_hashes(self) -> None:
        """Evaluations made before the hash ignored line endings stored the Windows (CRLF) hash. Rewrite exactly those
        rows to the hash the same content has everywhere now, so old and new evaluations stay comparable. A row is only
        touched when its version and its stored hash both match the old scheme, so it is safe to run on every start."""
        from blackbox.evals.cases import dataset_hash_migrations

        for version, old, new in dataset_hash_migrations():
            if old != new:
                self._db.execute("UPDATE eval_runs SET dataset_hash=? WHERE dataset_version=? AND dataset_hash=?", (new, version, old))
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ---- runs --------------------------------------------------------------------
    def create_run(self, run: RunRecord) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO runs (run_id, task, model, status, trace_id, started_at, duration_ms, final_answer, error,"
                " variant) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run.run_id, run.task, run.model, run.status, run.trace_id, run.started_at,
                 run.duration_ms, run.final_answer, run.error, run.variant),
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

    # ---- faults planted by the failure lab (ground truth, kept out of the trace) -----
    def save_run_faults(self, run_id: str, faults: list[RunFault]) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO run_faults (run_id, idx, kind, tool, occurrence, description, origin_span_id, fired)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [(run_id, i, f.kind, f.tool, f.occurrence, f.description, f.origin_span_id, int(f.fired))
                 for i, f in enumerate(faults)],
            )
            self._db.commit()

    def get_run_faults(self, run_id: str) -> list[RunFault]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM run_faults WHERE run_id=? ORDER BY idx", (run_id,)).fetchall()
        return [RunFault(kind=r["kind"], tool=r["tool"], occurrence=r["occurrence"], description=r["description"],
                         origin_span_id=r["origin_span_id"], fired=bool(r["fired"])) for r in rows]

    # ---- test harness only ---------------------------------------------------------
    def delete_span(self, span_id: str) -> None:
        """Used by the validation batch to plant a 'missing span' fault. Not used in normal operation."""
        with self._lock:
            self._db.execute("DELETE FROM spans WHERE span_id=?", (span_id,))
            self._db.commit()

    # ---- evaluations ---------------------------------------------------------------
    def create_eval_run(self, summary: EvalRunSummary) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO eval_runs (eval_id, kind, model, dataset_version, dataset_hash, seed, started_at,"
                " finished_at, status, variant, rescored_from) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (summary.eval_id, summary.kind, summary.model, summary.dataset_version, summary.dataset_hash,
                 summary.seed, summary.started_at, summary.finished_at, summary.status, summary.variant,
                 summary.rescored_from),
            )
            self._db.commit()

    def finish_eval_run(self, eval_id: str, status: str, finished_at: str) -> None:
        with self._lock:
            self._db.execute("UPDATE eval_runs SET status=?, finished_at=? WHERE eval_id=?", (status, finished_at, eval_id))
            self._db.commit()

    def save_eval_case(self, eval_id: str, result: EvalCaseResult) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO eval_cases (eval_id, case_id, category, task, run_id, run_status, passed,"
                " duration_ms, note) VALUES (?,?,?,?,?,?,?,?,?)",
                (eval_id, result.case_id, result.category, result.task, result.run_id, result.run_status,
                 int(result.passed), result.duration_ms, json.dumps(result.note) if result.note else None),
            )
            self._db.executemany(
                "INSERT OR REPLACE INTO eval_results (eval_id, case_id, metric, passed, score, gating, reason,"
                " span_ids, details) VALUES (?,?,?,?,?,?,?,?,?)",
                [(eval_id, result.case_id, c.metric, None if c.passed is None else int(c.passed), c.score,
                  int(c.gating), c.reason, json.dumps(c.span_ids), json.dumps(c.details)) for c in result.checks],
            )
            self._db.commit()

    @staticmethod
    def _summary_from_row(row: sqlite3.Row) -> EvalRunSummary:
        return EvalRunSummary(
            eval_id=row["eval_id"], kind=row["kind"], model=row["model"], dataset_version=row["dataset_version"],
            dataset_hash=row["dataset_hash"], seed=row["seed"], variant=row["variant"], rescored_from=row["rescored_from"], started_at=row["started_at"],
            finished_at=row["finished_at"], status=row["status"],
            n_cases=row["n_cases"] or 0, n_passed=row["n_passed"] or 0,
        )

    _EVAL_SELECT = (
        "SELECT r.*, (SELECT COUNT(*) FROM eval_cases c WHERE c.eval_id = r.eval_id) AS n_cases,"
        " (SELECT COALESCE(SUM(c.passed), 0) FROM eval_cases c WHERE c.eval_id = r.eval_id) AS n_passed"
        " FROM eval_runs r"
    )

    def list_eval_runs(self, limit: int = 50) -> list[EvalRunSummary]:
        with self._lock:
            rows = self._db.execute(
                f"{self._EVAL_SELECT} ORDER BY r.started_at DESC, r.rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._summary_from_row(r) for r in rows]

    @staticmethod
    def _check_from_row(r: sqlite3.Row) -> CheckResult:
        return CheckResult(
            metric=r["metric"], passed=None if r["passed"] is None else bool(r["passed"]), score=r["score"],
            reason=r["reason"], span_ids=json.loads(r["span_ids"]), details=json.loads(r["details"]),
            gating=bool(r["gating"]),
        )

    def get_eval_report(self, eval_id: str) -> EvalReport | None:
        with self._lock:
            head = self._db.execute(f"{self._EVAL_SELECT} WHERE r.eval_id=?", (eval_id,)).fetchone()
            if head is None:
                return None
            cases = self._db.execute("SELECT * FROM eval_cases WHERE eval_id=? ORDER BY rowid", (eval_id,)).fetchall()
            results = self._db.execute("SELECT * FROM eval_results WHERE eval_id=? ORDER BY rowid", (eval_id,)).fetchall()

        by_case: dict[str, list[CheckResult]] = {}
        for r in results:
            by_case.setdefault(r["case_id"], []).append(self._check_from_row(r))
        case_results = [
            EvalCaseResult(
                case_id=c["case_id"], category=c["category"], task=c["task"], run_id=c["run_id"],
                run_status=c["run_status"], passed=bool(c["passed"]), duration_ms=c["duration_ms"],
                note=json.loads(c["note"]) if c["note"] else None, checks=by_case.get(c["case_id"], []),
            )
            for c in cases
        ]

        order = ["task_completion", "policy_compliance", "tool_correctness", "argument_correctness",
                 "step_efficiency", "trace_completeness", "tool_output_contract", "latency"]
        grouped: dict[str, list[CheckResult]] = {}
        for case in case_results:
            for check in case.checks:
                grouped.setdefault(check.metric, []).append(check)
        metrics = []
        for name in sorted(grouped, key=lambda m: order.index(m) if m in order else len(order)):
            checks = grouped[name]
            decided = [x for x in checks if x.passed is not None]
            scores = [x.score for x in checks if x.score is not None]
            metrics.append(MetricSummary(
                metric=name, gating=checks[0].gating, passed=sum(1 for x in decided if x.passed), total=len(decided),
                mean_score=(sum(scores) / len(scores)) if scores else None,
            ))
        categories: dict[str, list[bool]] = {}
        for case in case_results:
            categories.setdefault(case.category, []).append(case.passed)
        return EvalReport(
            **self._summary_from_row(head).model_dump(),
            cases=case_results, metrics=metrics,
            categories=[CategorySummary(category=k, passed=sum(v), total=len(v)) for k, v in categories.items()],
        )

    def find_eval_case_for_run(self, run_id: str, among: Collection[str] | None = None) -> tuple[str, str] | None:
        """The latest evaluation case that ran this run (a rescored evaluation reuses the runs of the one it was
        rescored from). `among` limits the search to some evaluations, for an export that only holds a few."""
        with self._lock:
            rows = self._db.execute(
                "SELECT eval_id, case_id FROM eval_cases WHERE run_id=? ORDER BY rowid DESC", (run_id,)
            ).fetchall()
        for row in rows:
            if among is None or row["eval_id"] in among:
                return row["eval_id"], row["case_id"]
        return None

    def get_case_checks(self, eval_id: str, case_id: str) -> list[CheckResult]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM eval_results WHERE eval_id=? AND case_id=? ORDER BY rowid", (eval_id, case_id)
            ).fetchall()
        return [self._check_from_row(r) for r in rows]
