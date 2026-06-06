"""SQLite storage backend for QLedger.

Stores experiments, circuits (as UniversalCircuit JSON), executions with full
metadata, circuit version history, and noise snapshots — all in a single
portable ``.db`` file.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

_SCHEMA_SQL = """\
-- Meta table for schema versioning
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Experiments: top-level containers
CREATE TABLE IF NOT EXISTS experiments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '[]',
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Circuits: stored as UniversalCircuit JSON
CREATE TABLE IF NOT EXISTS circuits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id   INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    name            TEXT    NOT NULL DEFAULT '',
    content_hash    TEXT    NOT NULL,
    circuit_json    TEXT    NOT NULL,
    num_qubits      INTEGER NOT NULL,
    num_clbits      INTEGER NOT NULL,
    depth           INTEGER NOT NULL,
    total_gates     INTEGER NOT NULL,
    two_qubit_gates INTEGER NOT NULL DEFAULT 0,
    gate_counts     TEXT    NOT NULL DEFAULT '{}',
    source_framework TEXT   NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Executions: one per circuit run
CREATE TABLE IF NOT EXISTS executions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    circuit_id         INTEGER NOT NULL REFERENCES circuits(id) ON DELETE CASCADE,
    backend_name       TEXT    NOT NULL,
    backend_version    TEXT    NOT NULL DEFAULT '',
    framework          TEXT    NOT NULL DEFAULT '',
    shots              INTEGER NOT NULL,
    seed_simulator     INTEGER,
    optimization_level INTEGER,
    transpiler_seed    INTEGER,
    counts             TEXT    NOT NULL DEFAULT '{}',
    probabilities      TEXT    NOT NULL DEFAULT '{}',
    most_frequent      TEXT,
    entropy            REAL,
    statevector        TEXT,
    memory             TEXT,
    execution_time_ms  REAL,
    success            INTEGER NOT NULL DEFAULT 1,
    error_message      TEXT,
    simulator_config   TEXT    NOT NULL DEFAULT '{}',
    extra_metadata     TEXT    NOT NULL DEFAULT '{}',
    created_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Circuit versions: git-like version tracking
CREATE TABLE IF NOT EXISTS circuit_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    circuit_id    INTEGER NOT NULL REFERENCES circuits(id) ON DELETE CASCADE,
    version       INTEGER NOT NULL DEFAULT 1,
    content_hash  TEXT    NOT NULL,
    circuit_json  TEXT    NOT NULL,
    parent_hash   TEXT,
    message       TEXT    NOT NULL DEFAULT '',
    diff_summary  TEXT    NOT NULL DEFAULT '{}',
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(circuit_id, version)
);

-- Noise snapshots: point-in-time hardware calibration
CREATE TABLE IF NOT EXISTS noise_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    backend_name    TEXT    NOT NULL,
    framework       TEXT    NOT NULL DEFAULT '',
    num_qubits      INTEGER NOT NULL DEFAULT 0,
    snapshot_json   TEXT    NOT NULL,
    median_t1_us    REAL,
    median_t2_us    REAL,
    avg_cx_error    REAL,
    avg_readout_err REAL,
    captured_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Benchmark results
CREATE TABLE IF NOT EXISTS benchmark_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_type  TEXT    NOT NULL,
    backend_name    TEXT    NOT NULL,
    framework       TEXT    NOT NULL DEFAULT '',
    score           REAL,
    details         TEXT    NOT NULL DEFAULT '{}',
    parameters      TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_circuits_experiment     ON circuits(experiment_id);
CREATE INDEX IF NOT EXISTS idx_circuits_hash           ON circuits(content_hash);
CREATE INDEX IF NOT EXISTS idx_executions_circuit      ON executions(circuit_id);
CREATE INDEX IF NOT EXISTS idx_executions_backend      ON executions(backend_name);
CREATE INDEX IF NOT EXISTS idx_executions_created      ON executions(created_at);
CREATE INDEX IF NOT EXISTS idx_experiments_name        ON experiments(name);
CREATE INDEX IF NOT EXISTS idx_experiments_created     ON experiments(created_at);
CREATE INDEX IF NOT EXISTS idx_noise_backend           ON noise_snapshots(backend_name);
CREATE INDEX IF NOT EXISTS idx_noise_captured          ON noise_snapshots(captured_at);
CREATE INDEX IF NOT EXISTS idx_versions_circuit        ON circuit_versions(circuit_id);
CREATE INDEX IF NOT EXISTS idx_versions_hash           ON circuit_versions(content_hash);
CREATE INDEX IF NOT EXISTS idx_benchmark_type_backend
    ON benchmark_results(benchmark_type, backend_name);
"""


class DatabaseError(Exception):
    """Raised when a database operation fails."""


class QLedgerStore:
    """SQLite storage backend for all QLedger data.

    Parameters
    ----------
    path : str | Path
        File path for the SQLite database.  Use ``":memory:"`` for an
        ephemeral in-memory database (useful for testing).
    """

    def __init__(self, path: str | Path = "qledger.sqlite") -> None:
        self._path = str(path)
        self._conn: sqlite3.Connection | None = None
        self._connect()
        self._initialize_schema()

    def _connect(self) -> None:
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.row_factory = sqlite3.Row

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DatabaseError("Database connection is closed.")
        return self._conn

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Cursor, None, None]:
        conn = self.connection
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _initialize_schema(self) -> None:
        conn = self.connection
        conn.executescript(_SCHEMA_SQL)
        existing = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('version', ?)",
                (str(SCHEMA_VERSION),),
            )
            conn.commit()

    # ==================================================================
    # EXPERIMENTS
    # ==================================================================

    def create_experiment(
        self, name: str, description: str = "", tags: list[str] | None = None
    ) -> int:
        with self._tx() as cur:
            cur.execute(
                "INSERT INTO experiments (name, description, tags) VALUES (?, ?, ?)",
                (name, description, json.dumps(tags or [])),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_experiment(self, experiment_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_experiments(
        self,
        name_like: str | None = None,
        tag: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM experiments WHERE 1=1"
        params: list[Any] = []
        if name_like:
            query += " AND name LIKE ?"
            params.append(f"%{name_like}%")
        if tag:
            query += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(r) for r in self.connection.execute(query, params).fetchall()]

    def delete_experiment(self, experiment_id: int) -> bool:
        with self._tx() as cur:
            cur.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
            return cur.rowcount > 0

    # ==================================================================
    # CIRCUITS
    # ==================================================================

    def save_circuit(
        self,
        experiment_id: int,
        circuit_json: str,
        content_hash: str,
        num_qubits: int,
        num_clbits: int,
        depth: int,
        total_gates: int,
        two_qubit_gates: int,
        gate_counts: dict[str, int],
        name: str = "",
        source_framework: str = "",
    ) -> int:
        with self._tx() as cur:
            cur.execute(
                """INSERT INTO circuits
                   (experiment_id, name, content_hash, circuit_json, num_qubits,
                    num_clbits, depth, total_gates, two_qubit_gates, gate_counts,
                    source_framework)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    experiment_id, name, content_hash, circuit_json,
                    num_qubits, num_clbits, depth, total_gates, two_qubit_gates,
                    json.dumps(gate_counts), source_framework,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_circuit(self, circuit_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM circuits WHERE id = ?", (circuit_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_circuit_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM circuits WHERE content_hash = ? LIMIT 1", (content_hash,)
        ).fetchone()
        return dict(row) if row else None

    def list_circuits(self, experiment_id: int) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.connection.execute(
                "SELECT * FROM circuits WHERE experiment_id = ? ORDER BY id",
                (experiment_id,),
            ).fetchall()
        ]

    # ==================================================================
    # EXECUTIONS
    # ==================================================================

    def save_execution(
        self,
        circuit_id: int,
        result: dict[str, Any],
    ) -> int:
        """Save an execution result.

        Parameters
        ----------
        circuit_id : int
            The circuit that was executed.
        result : dict
            Serialised ExecutionResult fields.
        """
        sv_json = None
        if result.get("statevector"):
            sv = result["statevector"]
            sv_json = json.dumps([{"re": c.real, "im": c.imag} for c in sv])

        with self._tx() as cur:
            cur.execute(
                """INSERT INTO executions
                   (circuit_id, backend_name, backend_version, framework, shots,
                    seed_simulator, optimization_level, transpiler_seed,
                    counts, probabilities, most_frequent, entropy,
                    statevector, memory, execution_time_ms,
                    success, error_message, simulator_config, extra_metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    circuit_id,
                    result.get("backend_name", ""),
                    result.get("backend_version", ""),
                    result.get("framework", ""),
                    result.get("shots", 0),
                    result.get("seed_simulator"),
                    result.get("optimization_level"),
                    result.get("transpiler_seed"),
                    json.dumps(result.get("counts", {})),
                    json.dumps(result.get("probabilities", {})),
                    result.get("most_frequent"),
                    result.get("entropy"),
                    sv_json,
                    json.dumps(result.get("memory")) if result.get("memory") else None,
                    result.get("execution_time_ms"),
                    int(result.get("success", True)),
                    result.get("error_message"),
                    json.dumps(result.get("simulator_config", {})),
                    json.dumps(result.get("extra_metadata", {})),
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_execution(self, execution_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM executions WHERE id = ?", (execution_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_executions(
        self,
        circuit_id: int | None = None,
        backend_name: str | None = None,
        framework: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM executions WHERE 1=1"
        params: list[Any] = []
        if circuit_id is not None:
            query += " AND circuit_id = ?"
            params.append(circuit_id)
        if backend_name:
            query += " AND backend_name = ?"
            params.append(backend_name)
        if framework:
            query += " AND framework = ?"
            params.append(framework)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(r) for r in self.connection.execute(query, params).fetchall()]

    # ==================================================================
    # CIRCUIT VERSIONS
    # ==================================================================

    def save_circuit_version(
        self,
        circuit_id: int,
        version: int,
        content_hash: str,
        circuit_json: str,
        parent_hash: str | None = None,
        message: str = "",
        diff_summary: dict[str, Any] | None = None,
    ) -> int:
        with self._tx() as cur:
            cur.execute(
                """INSERT INTO circuit_versions
                   (circuit_id, version, content_hash, circuit_json,
                    parent_hash, message, diff_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    circuit_id, version, content_hash, circuit_json,
                    parent_hash, message, json.dumps(diff_summary or {}),
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_circuit_versions(self, circuit_id: int) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.connection.execute(
                "SELECT * FROM circuit_versions WHERE circuit_id = ? ORDER BY version",
                (circuit_id,),
            ).fetchall()
        ]

    def get_version_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM circuit_versions WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ).fetchone()
        return dict(row) if row else None

    # ==================================================================
    # NOISE SNAPSHOTS
    # ==================================================================

    def save_noise_snapshot(self, snapshot_json: str, summary: dict[str, Any]) -> int:
        with self._tx() as cur:
            cur.execute(
                """INSERT INTO noise_snapshots
                   (backend_name, framework, num_qubits, snapshot_json,
                    median_t1_us, median_t2_us, avg_cx_error, avg_readout_err)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    summary.get("backend_name", ""),
                    summary.get("framework", ""),
                    summary.get("num_qubits", 0),
                    snapshot_json,
                    summary.get("median_t1_us"),
                    summary.get("median_t2_us"),
                    summary.get("avg_cx_error"),
                    summary.get("avg_readout_err"),
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def list_noise_snapshots(
        self,
        backend_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM noise_snapshots WHERE 1=1"
        params: list[Any] = []
        if backend_name:
            query += " AND backend_name = ?"
            params.append(backend_name)
        query += " ORDER BY captured_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.connection.execute(query, params).fetchall()]

    # ==================================================================
    # BENCHMARKS
    # ==================================================================

    def save_benchmark(
        self,
        benchmark_type: str,
        backend_name: str,
        score: float | None,
        details: dict[str, Any],
        parameters: dict[str, Any] | None = None,
        framework: str = "",
    ) -> int:
        with self._tx() as cur:
            cur.execute(
                """INSERT INTO benchmark_results
                   (benchmark_type, backend_name, framework, score, details, parameters)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    benchmark_type, backend_name, framework, score,
                    json.dumps(details), json.dumps(parameters or {}),
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def list_benchmarks(
        self,
        benchmark_type: str | None = None,
        backend_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM benchmark_results WHERE 1=1"
        params: list[Any] = []
        if benchmark_type:
            query += " AND benchmark_type = ?"
            params.append(benchmark_type)
        if backend_name:
            query += " AND backend_name = ?"
            params.append(backend_name)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.connection.execute(query, params).fetchall()]

    # ==================================================================
    # AGGREGATE QUERIES
    # ==================================================================

    def get_experiment_summary(self, experiment_id: int) -> dict[str, Any] | None:
        exp = self.get_experiment(experiment_id)
        if exp is None:
            return None
        cc = self.connection.execute(
            "SELECT COUNT(*) FROM circuits WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()[0]
        ec = self.connection.execute(
            """SELECT COUNT(*) FROM executions e
               JOIN circuits c ON e.circuit_id = c.id
               WHERE c.experiment_id = ?""",
            (experiment_id,),
        ).fetchone()[0]
        return {**exp, "circuit_count": cc, "execution_count": ec}

    def get_full_history(self, experiment_id: int) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.connection.execute(
                """SELECT e.*, c.name AS circuit_name, c.num_qubits, c.depth,
                          c.content_hash AS circuit_hash
                   FROM executions e
                   JOIN circuits c ON e.circuit_id = c.id
                   WHERE c.experiment_id = ?
                   ORDER BY e.created_at""",
                (experiment_id,),
            ).fetchall()
        ]

    def export_experiment(self, experiment_id: int) -> dict[str, Any]:
        exp = self.get_experiment(experiment_id)
        if exp is None:
            raise DatabaseError(f"Experiment {experiment_id} not found.")
        circuits = self.list_circuits(experiment_id)
        for circ in circuits:
            circ["executions"] = self.list_executions(circuit_id=circ["id"])
            circ["versions"] = self.get_circuit_versions(circ["id"])
        return {**exp, "circuits": circuits}
