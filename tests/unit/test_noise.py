"""Tests for noise profile models."""


from qledger.schema.noise import (
    GateFidelity,
    NoiseSnapshot,
    QubitProperties,
    ReadoutError,
)


class TestQubitProperties:
    def test_roundtrip(self) -> None:
        qp = QubitProperties(index=0, t1_us=100.0, t2_us=50.0, readout_error=0.01)
        d = qp.to_dict()
        restored = QubitProperties.from_dict(d)
        assert restored.index == 0
        assert restored.t1_us == 100.0

    def test_none_fields_excluded(self) -> None:
        qp = QubitProperties(index=0)
        d = qp.to_dict()
        assert "t1_us" not in d


class TestGateFidelity:
    def test_roundtrip(self) -> None:
        gf = GateFidelity(gate="cx", qubits=(0, 1), fidelity=0.99, error_rate=0.01)
        d = gf.to_dict()
        restored = GateFidelity.from_dict(d)
        assert restored.gate == "cx"
        assert restored.fidelity == 0.99


class TestReadoutError:
    def test_average_error(self) -> None:
        re = ReadoutError(qubit=0, prob_meas1_prep0=0.02, prob_meas0_prep1=0.04)
        assert abs(re.average_error - 0.03) < 1e-9

    def test_roundtrip(self) -> None:
        re = ReadoutError(qubit=0, prob_meas1_prep0=0.02, prob_meas0_prep1=0.04)
        d = re.to_dict()
        restored = ReadoutError.from_dict(d)
        assert restored.qubit == 0


class TestNoiseSnapshot:
    def _sample_snapshot(self) -> NoiseSnapshot:
        return NoiseSnapshot(
            backend_name="test_backend",
            num_qubits=3,
            qubit_properties=[
                QubitProperties(0, t1_us=100.0, t2_us=50.0),
                QubitProperties(1, t1_us=120.0, t2_us=60.0),
                QubitProperties(2, t1_us=80.0, t2_us=40.0),
            ],
            gate_fidelities=[
                GateFidelity("cx", (0, 1), 0.99, 0.01),
                GateFidelity("cx", (1, 2), 0.98, 0.02),
            ],
            readout_errors=[
                ReadoutError(0, 0.02, 0.03),
                ReadoutError(1, 0.01, 0.02),
            ],
            coupling_map=[(0, 1), (1, 2)],
            basis_gates=["cx", "rz", "sx", "x"],
        )

    def test_median_t1(self) -> None:
        snap = self._sample_snapshot()
        assert snap.median_t1_us == 100.0  # sorted: 80, 100, 120 → median 100

    def test_median_t2(self) -> None:
        snap = self._sample_snapshot()
        assert snap.median_t2_us == 50.0

    def test_average_cx_error(self) -> None:
        snap = self._sample_snapshot()
        assert snap.average_cx_error is not None
        assert abs(snap.average_cx_error - 0.015) < 1e-9

    def test_average_readout_error(self) -> None:
        snap = self._sample_snapshot()
        assert snap.average_readout_error is not None
        assert abs(snap.average_readout_error - 0.02) < 1e-9

    def test_json_roundtrip(self) -> None:
        snap = self._sample_snapshot()
        json_str = snap.to_json()
        restored = NoiseSnapshot.from_dict(__import__("json").loads(json_str))
        assert restored.backend_name == "test_backend"
        assert restored.num_qubits == 3
        assert len(restored.qubit_properties) == 3
        assert len(restored.gate_fidelities) == 2

    def test_dict_includes_aggregates(self) -> None:
        snap = self._sample_snapshot()
        d = snap.to_dict()
        assert "aggregate" in d
        assert d["aggregate"]["median_t1_us"] == 100.0
