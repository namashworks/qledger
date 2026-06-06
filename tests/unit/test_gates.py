"""Tests for the gate registry and cross-framework mapping."""

from qledger.schema.gates import ParametricType, StandardGates


class TestStandardGates:
    def test_get_by_canonical_name(self) -> None:
        gate = StandardGates.get("h")
        assert gate is not None
        assert gate.label == "Hadamard"
        assert gate.num_qubits == 1
        assert gate.num_params == 0

    def test_resolve_by_qiskit_alias(self) -> None:
        gate = StandardGates.resolve("cx")
        assert gate is not None
        assert gate.canonical_name == "cx"
        assert gate.label == "CNOT"

    def test_resolve_by_cirq_alias(self) -> None:
        gate = StandardGates.resolve("CNOT")
        assert gate is not None
        assert gate.canonical_name == "cx"

    def test_resolve_by_pennylane_alias(self) -> None:
        gate = StandardGates.resolve("Hadamard")
        assert gate is not None
        assert gate.canonical_name == "h"

    def test_resolve_case_insensitive(self) -> None:
        assert StandardGates.resolve("HADAMARD") is not None
        assert StandardGates.resolve("hadamard") is not None

    def test_resolve_unknown_returns_none(self) -> None:
        assert StandardGates.resolve("nonexistent_gate") is None

    def test_canonical_name_for(self) -> None:
        assert StandardGates.canonical_name_for("PauliX") == "x"
        assert StandardGates.canonical_name_for("CZ") == "cz"
        assert StandardGates.canonical_name_for("nope") is None

    def test_alias_for(self) -> None:
        assert StandardGates.alias_for("cx", "pennylane") == "CNOT"
        assert StandardGates.alias_for("h", "cirq") == "H"

    def test_parametric_gates(self) -> None:
        rx = StandardGates.get("rx")
        assert rx is not None
        assert rx.parametric == ParametricType.PARAMETRIC
        assert rx.num_params == 1

    def test_multi_qubit_gates(self) -> None:
        ccx = StandardGates.get("ccx")
        assert ccx is not None
        assert ccx.num_qubits == 3

    def test_all_definitions_nonempty(self) -> None:
        all_gates = StandardGates.all_definitions()
        assert len(all_gates) >= 25  # We registered 25+ gates

    def test_gate_signature(self) -> None:
        gate = StandardGates.get("rx")
        assert gate is not None
        sig = gate.signature
        assert sig.canonical_name == "rx"
        assert sig.num_qubits == 1
        assert sig.num_params == 1
