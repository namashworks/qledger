"""Tests for circuit versioning."""

from qledger.schema.circuit import Instruction, Measurement, UniversalCircuit
from qledger.storage.database import QLedgerStore
from qledger.versioning.tracker import CircuitVersionTracker, compute_diff


class TestComputeDiff:
    def test_no_changes(self) -> None:
        uc = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,))],
        )
        diff = compute_diff(uc, uc)
        assert not diff.has_changes

    def test_gate_added(self) -> None:
        old = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,))],
        )
        new = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,)), Instruction("cx", (0, 1))],
        )
        diff = compute_diff(old, new)
        assert diff.has_changes
        assert len(diff.gates_added) == 1
        assert diff.gates_added[0]["gate"] == "cx"
        assert len(diff.gates_removed) == 0
        assert diff.depth_changed

    def test_gate_removed(self) -> None:
        old = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,)), Instruction("cx", (0, 1))],
        )
        new = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,))],
        )
        diff = compute_diff(old, new)
        assert len(diff.gates_removed) == 1

    def test_qubit_count_change(self) -> None:
        old = UniversalCircuit(num_qubits=2, num_clbits=2, instructions=[])
        new = UniversalCircuit(num_qubits=4, num_clbits=4, instructions=[])
        diff = compute_diff(old, new)
        assert diff.qubit_count_changed

    def test_measurement_change(self) -> None:
        old = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            measurements=[Measurement(0, 0)],
        )
        new = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            measurements=[Measurement(0, 0), Measurement(1, 1)],
        )
        diff = compute_diff(old, new)
        assert diff.measurement_changed

    def test_summary_text(self) -> None:
        old = UniversalCircuit(num_qubits=2, num_clbits=2, instructions=[])
        new = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,))],
        )
        diff = compute_diff(old, new)
        text = diff.summary_text()
        assert "+1 gates" in text


class TestCircuitVersionTracker:
    def test_commit_and_log(self) -> None:
        store = QLedgerStore(":memory:")
        eid = store.create_experiment("v")
        cid = store.save_circuit(eid, "{}", "h", 2, 2, 1, 1, 0, {})

        tracker = CircuitVersionTracker(store)

        uc_v1 = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,))],
            name="v1",
        )
        v1 = tracker.commit(cid, uc_v1, message="initial")
        assert v1 == 1

        uc_v2 = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,)), Instruction("cx", (0, 1))],
            name="v2",
        )
        v2 = tracker.commit(cid, uc_v2, message="added CNOT")
        assert v2 == 2

        log = tracker.log(cid)
        assert len(log) == 2
        store.close()

    def test_checkout(self) -> None:
        store = QLedgerStore(":memory:")
        eid = store.create_experiment("v")
        cid = store.save_circuit(eid, "{}", "h", 2, 2, 1, 1, 0, {})
        tracker = CircuitVersionTracker(store)

        uc = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,))],
        )
        tracker.commit(cid, uc)

        restored = tracker.checkout(cid, 1)
        assert restored is not None
        assert restored.instructions == uc.instructions
        store.close()

    def test_duplicate_commit_returns_same_version(self) -> None:
        store = QLedgerStore(":memory:")
        eid = store.create_experiment("v")
        cid = store.save_circuit(eid, "{}", "h", 2, 2, 1, 1, 0, {})
        tracker = CircuitVersionTracker(store)

        uc = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,))],
        )
        v1 = tracker.commit(cid, uc)
        v2 = tracker.commit(cid, uc)  # same circuit
        assert v1 == v2
        store.close()

    def test_diff_between_versions(self) -> None:
        store = QLedgerStore(":memory:")
        eid = store.create_experiment("v")
        cid = store.save_circuit(eid, "{}", "h", 2, 2, 1, 1, 0, {})
        tracker = CircuitVersionTracker(store)

        uc_v1 = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,))],
        )
        uc_v2 = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,)), Instruction("x", (1,))],
        )
        tracker.commit(cid, uc_v1)
        tracker.commit(cid, uc_v2)

        diff = tracker.diff(cid, 1, 2)
        assert diff is not None
        assert diff.has_changes
        assert len(diff.gates_added) == 1
        store.close()
