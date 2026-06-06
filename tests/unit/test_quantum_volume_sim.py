"""Tests for the pure-Python ideal simulator used by the QV benchmark."""

import math

from qledger.benchmarks.quantum_volume import (
    _generate_qv_circuit,
    _heavy_outputs,
    _ideal_probabilities,
)
from qledger.schema.circuit import Instruction, UniversalCircuit


class TestIdealProbabilities:
    def test_empty_circuit_is_all_zeros(self) -> None:
        uc = UniversalCircuit(num_qubits=2, num_clbits=2)
        probs = _ideal_probabilities(uc)
        assert probs == {"00": 1.0}

    def test_rx_pi_flips_qubit(self) -> None:
        uc = UniversalCircuit(
            num_qubits=1, num_clbits=1,
            instructions=[Instruction("rx", (0,), (math.pi,))],
        )
        probs = _ideal_probabilities(uc)
        # RX(pi)|0> = -i|1>, so all probability on "1"
        assert probs.get("1", 0) == 1.0
        assert probs.get("0", 0) == 0.0

    def test_ry_pi_over_2_creates_superposition(self) -> None:
        uc = UniversalCircuit(
            num_qubits=1, num_clbits=1,
            instructions=[Instruction("ry", (0,), (math.pi / 2,))],
        )
        probs = _ideal_probabilities(uc)
        assert math.isclose(probs.get("0", 0), 0.5, abs_tol=1e-9)
        assert math.isclose(probs.get("1", 0), 0.5, abs_tol=1e-9)

    def test_rz_doesnt_change_z_basis_probabilities(self) -> None:
        uc = UniversalCircuit(
            num_qubits=1, num_clbits=1,
            instructions=[Instruction("rz", (0,), (1.234,))],
        )
        probs = _ideal_probabilities(uc)
        assert math.isclose(probs.get("0", 0), 1.0, abs_tol=1e-9)

    def test_bell_state_via_ry_and_cx(self) -> None:
        # RY(pi/2) then CX gives an entangled state equiv. to a Bell state
        uc = UniversalCircuit(
            num_qubits=2, num_clbits=2,
            instructions=[
                Instruction("ry", (0,), (math.pi / 2,)),
                Instruction("cx", (0, 1), ()),
            ],
        )
        probs = _ideal_probabilities(uc)
        # |00> and |11> each with probability 0.5
        assert math.isclose(probs.get("00", 0), 0.5, abs_tol=1e-9)
        assert math.isclose(probs.get("11", 0), 0.5, abs_tol=1e-9)
        assert probs.get("01", 0) == 0.0
        assert probs.get("10", 0) == 0.0

    def test_probabilities_sum_to_one(self) -> None:
        import random
        rng = random.Random(42)
        uc = _generate_qv_circuit(4, rng)
        probs = _ideal_probabilities(uc)
        assert math.isclose(sum(probs.values()), 1.0, abs_tol=1e-9)


class TestHeavyOutputs:
    def test_heavy_set_is_upper_half(self) -> None:
        # 2 qubits, 4 outcomes — deliberately skewed distribution
        ideal = {"00": 0.5, "01": 0.3, "10": 0.15, "11": 0.05}
        heavy = _heavy_outputs(ideal, num_qubits=2)
        # Median of [0.05, 0.15, 0.3, 0.5] at index 2 = 0.3; outputs strictly > 0.3
        assert heavy == {"00"}

    def test_uniform_distribution_no_heavy(self) -> None:
        ideal = {"00": 0.25, "01": 0.25, "10": 0.25, "11": 0.25}
        heavy = _heavy_outputs(ideal, num_qubits=2)
        # All equal — nothing strictly above median
        assert heavy == set()
