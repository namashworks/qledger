"""Tests for the SQLite storage layer."""

import json

import pytest

from qledger.storage.database import DatabaseError, QLedgerStore


@pytest.fixture()
def store() -> QLedgerStore:
    return QLedgerStore(":memory:")


class TestExperiments:
    def test_create_and_get(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("test", "desc", ["tag1"])
        exp = store.get_experiment(eid)
        assert exp is not None
        assert exp["name"] == "test"
        assert json.loads(exp["tags"]) == ["tag1"]

    def test_list_with_filter(self, store: QLedgerStore) -> None:
        store.create_experiment("alpha")
        store.create_experiment("beta")
        store.create_experiment("alpha-2")
        assert len(store.list_experiments(name_like="alpha")) == 2

    def test_delete(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("del")
        assert store.delete_experiment(eid)
        assert store.get_experiment(eid) is None

    def test_get_nonexistent(self, store: QLedgerStore) -> None:
        assert store.get_experiment(999) is None


class TestCircuits:
    def test_save_and_get(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("c")
        cid = store.save_circuit(
            eid, '{"test": true}', "abc123", 2, 2, 3, 5, 1,
            {"h": 1, "cx": 1}, name="bell", source_framework="qiskit",
        )
        circ = store.get_circuit(cid)
        assert circ is not None
        assert circ["num_qubits"] == 2
        assert circ["content_hash"] == "abc123"

    def test_find_by_hash(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("h")
        store.save_circuit(eid, "{}", "hash1", 1, 1, 1, 1, 0, {})
        assert store.find_circuit_by_hash("hash1") is not None
        assert store.find_circuit_by_hash("nope") is None

    def test_list_circuits(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("multi")
        store.save_circuit(eid, "{}", "h1", 1, 1, 1, 1, 0, {})
        store.save_circuit(eid, "{}", "h2", 2, 2, 2, 2, 0, {})
        assert len(store.list_circuits(eid)) == 2


class TestExecutions:
    def test_save_and_get(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("e")
        cid = store.save_circuit(eid, "{}", "h", 2, 2, 1, 1, 0, {})
        xid = store.save_execution(cid, {
            "backend_name": "aer_simulator",
            "shots": 1024,
            "counts": {"00": 500, "11": 524},
            "success": True,
        })
        exe = store.get_execution(xid)
        assert exe is not None
        assert exe["backend_name"] == "aer_simulator"
        assert json.loads(exe["counts"]) == {"00": 500, "11": 524}

    def test_list_by_backend(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("f")
        cid = store.save_circuit(eid, "{}", "h", 1, 1, 1, 1, 0, {})
        store.save_execution(cid, {"backend_name": "aer", "shots": 100, "counts": {}})
        store.save_execution(cid, {"backend_name": "sv", "shots": 100, "counts": {}})
        assert len(store.list_executions(backend_name="aer")) == 1


class TestVersions:
    def test_save_and_get(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("v")
        cid = store.save_circuit(eid, "{}", "h", 1, 1, 1, 1, 0, {})
        store.save_circuit_version(cid, 1, "h1", "{}", message="initial")
        store.save_circuit_version(cid, 2, "h2", "{}", parent_hash="h1", message="update")
        versions = store.get_circuit_versions(cid)
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["parent_hash"] == "h1"


class TestNoise:
    def test_save_and_list(self, store: QLedgerStore) -> None:
        store.save_noise_snapshot('{"backend_name": "sim"}', {
            "backend_name": "sim",
            "num_qubits": 5,
            "median_t1_us": 100.0,
        })
        results = store.list_noise_snapshots(backend_name="sim")
        assert len(results) == 1
        assert results[0]["num_qubits"] == 5


class TestBenchmarks:
    def test_save_and_list(self, store: QLedgerStore) -> None:
        store.save_benchmark("quantum_volume", "sim", 32.0, {"qv": 32})
        results = store.list_benchmarks(benchmark_type="quantum_volume")
        assert len(results) == 1
        assert results[0]["score"] == 32.0


class TestCascadeDelete:
    def test_delete_experiment_cascades(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("cascade")
        cid = store.save_circuit(eid, "{}", "h", 1, 1, 1, 1, 0, {})
        xid = store.save_execution(cid, {"backend_name": "s", "shots": 1, "counts": {}})
        store.save_circuit_version(cid, 1, "h", "{}")
        store.delete_experiment(eid)
        assert store.get_circuit(cid) is None
        assert store.get_execution(xid) is None
        assert store.get_circuit_versions(cid) == []


class TestAggregates:
    def test_experiment_summary(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("agg")
        c1 = store.save_circuit(eid, "{}", "h1", 1, 1, 1, 1, 0, {})
        c2 = store.save_circuit(eid, "{}", "h2", 2, 2, 2, 2, 0, {})
        store.save_execution(c1, {"backend_name": "s", "shots": 1, "counts": {}})
        store.save_execution(c2, {"backend_name": "s", "shots": 1, "counts": {}})
        store.save_execution(c2, {"backend_name": "s", "shots": 1, "counts": {}})
        summary = store.get_experiment_summary(eid)
        assert summary is not None
        assert summary["circuit_count"] == 2
        assert summary["execution_count"] == 3

    def test_export(self, store: QLedgerStore) -> None:
        eid = store.create_experiment("exp")
        cid = store.save_circuit(eid, "{}", "h", 1, 1, 1, 1, 0, {})
        store.save_execution(cid, {"backend_name": "s", "shots": 1, "counts": {"0": 1}})
        data = store.export_experiment(eid)
        assert data["name"] == "exp"
        assert len(data["circuits"]) == 1
        assert len(data["circuits"][0]["executions"]) == 1

    def test_export_nonexistent_raises(self, store: QLedgerStore) -> None:
        with pytest.raises(DatabaseError):
            store.export_experiment(999)
