"""Integration tests — full Qiskit pipeline through QLedger."""


import pytest
from qiskit import QuantumCircuit

from qledger import QLedger
from qledger.adapters.registry import AdapterRegistry


@pytest.fixture()
def db() -> QLedger:
    return QLedger(":memory:", default_framework="qiskit")


class TestQiskitConversion:
    def test_from_native_bell(self, db: QLedger) -> None:
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        adapter = AdapterRegistry.get("qiskit")
        uc = adapter.from_native(qc)

        assert uc.num_qubits == 2
        assert uc.num_clbits == 2
        assert uc.total_gates == 2
        assert uc.two_qubit_gate_count == 1
        assert len(uc.measurements) == 2
        assert uc.gate_counts == {"h": 1, "cx": 1}

    def test_roundtrip_qiskit(self) -> None:
        qc = QuantumCircuit(3, 3)
        qc.h(0)
        qc.cx(0, 1)
        qc.cx(1, 2)
        qc.measure([0, 1, 2], [0, 1, 2])

        adapter = AdapterRegistry.get("qiskit")
        uc = adapter.from_native(qc)
        restored = adapter.to_native(uc)

        assert restored.num_qubits == 3
        assert restored.num_clbits == 3

    def test_parametric_circuit(self) -> None:
        qc = QuantumCircuit(1, 1)
        qc.rx(1.5708, 0)
        qc.ry(0.7854, 0)
        qc.measure(0, 0)

        adapter = AdapterRegistry.get("qiskit")
        uc = adapter.from_native(qc)

        assert uc.total_gates == 2
        assert uc.instructions[0].gate == "rx"
        assert abs(uc.instructions[0].params[0] - 1.5708) < 1e-4


class TestFullPipeline:
    def test_run_single_circuit(self, db: QLedger) -> None:
        exp_id = db.create_experiment("integration", tags=["test"])

        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        result = db.run(
            qc,
            experiment_id=exp_id,
            name="bell",
            shots=2048,
            seed_simulator=42,
        )

        assert result.success
        assert result.total_counts == 2048
        assert "00" in result.counts or "11" in result.counts
        assert result.execution_time_ms is not None
        assert result.execution_time_ms > 0

        # Verify storage
        summary = db.get_experiment_summary(exp_id)
        assert summary is not None
        assert summary["circuit_count"] == 1
        assert summary["execution_count"] == 1

    def test_run_batch(self, db: QLedger) -> None:
        circuits = []
        for n in range(2, 5):
            qc = QuantumCircuit(n, n)
            qc.h(0)
            for i in range(1, n):
                qc.cx(0, i)
            qc.measure(range(n), range(n))
            circuits.append(qc)

        results = db.run_batch(
            circuits,
            experiment_name="batch-test",
            names=["2q", "3q", "4q"],
            shots=1024,
        )

        assert len(results) == 3
        assert all(r.success for r in results)

    def test_circuit_versioning(self, db: QLedger) -> None:
        exp_id = db.create_experiment("version-test")

        # V1
        qc1 = QuantumCircuit(2, 2)
        qc1.h(0)
        qc1.measure([0, 1], [0, 1])
        db.run(qc1, experiment_id=exp_id, name="v1")

        # The circuit should have been auto-versioned
        circuits = db.list_circuits(exp_id)
        assert len(circuits) == 1
        versions = db.circuit_log(circuits[0]["id"])
        assert len(versions) >= 1

    def test_export_experiment(self, db: QLedger) -> None:
        exp_id = db.create_experiment("export-test")
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])
        db.run(qc, experiment_id=exp_id, shots=100)

        export = db.export_experiment(exp_id)
        assert export["name"] == "export-test"
        assert len(export["circuits"]) == 1
        assert len(export["circuits"][0]["executions"]) == 1

    def test_execution_history(self, db: QLedger) -> None:
        exp_id = db.create_experiment("history-test")
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        # Run multiple times
        for i in range(3):
            db.run(qc, experiment_id=exp_id, name=f"run-{i}", shots=100)

        history = db.get_history(exp_id)
        assert len(history) == 3

    def test_reproducibility_with_seeds(self, db: QLedger) -> None:
        exp_id = db.create_experiment("repro")
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        r1 = db.run(qc, experiment_id=exp_id, shots=1000,
                     seed_simulator=777, transpiler_seed=777)
        r2 = db.run(qc, experiment_id=exp_id, shots=1000,
                     seed_simulator=777, transpiler_seed=777)
        assert r1.counts == r2.counts


class TestCrossFrameworkConversion:
    def test_qiskit_to_universal_and_back(self) -> None:
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        adapter = AdapterRegistry.get("qiskit")
        uc = adapter.from_native(qc, name="test")
        restored = adapter.to_native(uc)

        # Re-convert to verify structural equivalence
        uc2 = adapter.from_native(restored)
        assert uc.content_hash() == uc2.content_hash()
