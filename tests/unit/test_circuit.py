"""Tests for the UniversalCircuit IR."""


from qledger.schema.circuit import Instruction, Measurement, UniversalCircuit


class TestInstruction:
    def test_roundtrip_dict(self) -> None:
        inst = Instruction("rx", (0,), (1.5708,))
        d = inst.to_dict()
        assert d["gate"] == "rx"
        assert d["qubits"] == [0]
        assert d["params"] == [1.5708]
        restored = Instruction.from_dict(d)
        assert restored == inst

    def test_fixed_gate_no_params(self) -> None:
        inst = Instruction("h", (0,))
        d = inst.to_dict()
        assert "params" not in d


class TestMeasurement:
    def test_roundtrip(self) -> None:
        m = Measurement(qubit=2, clbit=1)
        d = m.to_dict()
        assert d == {"qubit": 2, "clbit": 1}
        assert Measurement.from_dict(d) == m


class TestUniversalCircuit:
    def _bell_circuit(self) -> UniversalCircuit:
        return UniversalCircuit(
            num_qubits=2,
            num_clbits=2,
            instructions=[
                Instruction("h", (0,)),
                Instruction("cx", (0, 1)),
            ],
            measurements=[Measurement(0, 0), Measurement(1, 1)],
            name="bell",
        )

    def test_depth(self) -> None:
        uc = self._bell_circuit()
        assert uc.depth == 2

    def test_gate_counts(self) -> None:
        uc = self._bell_circuit()
        assert uc.gate_counts == {"h": 1, "cx": 1}

    def test_total_gates(self) -> None:
        uc = self._bell_circuit()
        assert uc.total_gates == 2

    def test_two_qubit_gate_count(self) -> None:
        uc = self._bell_circuit()
        assert uc.two_qubit_gate_count == 1

    def test_used_qubits(self) -> None:
        uc = self._bell_circuit()
        assert uc.used_qubits == {0, 1}

    def test_content_hash_deterministic(self) -> None:
        a = self._bell_circuit()
        b = self._bell_circuit()
        assert a.content_hash() == b.content_hash()

    def test_content_hash_changes_with_gate(self) -> None:
        a = self._bell_circuit()
        b = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (0,)), Instruction("cz", (0, 1))],
            measurements=[Measurement(0, 0), Measurement(1, 1)],
        )
        assert a.content_hash() != b.content_hash()

    def test_content_hash_ignores_name_and_metadata(self) -> None:
        a = self._bell_circuit()
        b = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=a.instructions.copy(),
            measurements=a.measurements.copy(),
            name="different_name",
            metadata={"key": "value"},
        )
        assert a.content_hash() == b.content_hash()

    def test_json_roundtrip(self) -> None:
        uc = self._bell_circuit()
        json_str = uc.to_json()
        restored = UniversalCircuit.from_json(json_str)
        assert restored.num_qubits == uc.num_qubits
        assert restored.instructions == uc.instructions
        assert restored.measurements == uc.measurements
        assert restored.content_hash() == uc.content_hash()

    def test_dict_roundtrip(self) -> None:
        uc = self._bell_circuit()
        d = uc.to_dict()
        restored = UniversalCircuit.from_dict(d)
        assert restored.depth == uc.depth
        assert restored.gate_counts == uc.gate_counts

    def test_validate_valid_circuit(self) -> None:
        uc = self._bell_circuit()
        assert uc.validate() == []

    def test_validate_qubit_out_of_range(self) -> None:
        uc = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("h", (5,))],
        )
        warnings = uc.validate()
        assert len(warnings) == 1
        assert "out of range" in warnings[0]

    def test_validate_wrong_param_count(self) -> None:
        uc = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[Instruction("rx", (0,), ())],  # missing param
        )
        warnings = uc.validate()
        assert len(warnings) == 1
        assert "params" in warnings[0]

    def test_empty_circuit(self) -> None:
        uc = UniversalCircuit(num_qubits=0, num_clbits=0)
        assert uc.depth == 0
        assert uc.total_gates == 0
        assert uc.gate_counts == {}

    def test_summary(self) -> None:
        uc = self._bell_circuit()
        s = uc.summary()
        assert "bell" in s
        assert "qubits=2" in s

    def test_depth_parallel_gates(self) -> None:
        """Gates on different qubits can execute in parallel → depth = 1."""
        uc = UniversalCircuit(
            num_qubits=4, num_clbits=0,
            instructions=[
                Instruction("h", (0,)),
                Instruction("h", (1,)),
                Instruction("h", (2,)),
                Instruction("h", (3,)),
            ],
        )
        assert uc.depth == 1
