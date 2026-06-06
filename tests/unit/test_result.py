"""Tests for ExecutionResult."""


from qledger.schema.result import ExecutionResult


class TestExecutionResult:
    def test_probabilities(self) -> None:
        r = ExecutionResult(counts={"00": 250, "11": 750}, shots=1000)
        assert abs(r.probabilities["00"] - 0.25) < 1e-9
        assert abs(r.probabilities["11"] - 0.75) < 1e-9

    def test_total_counts(self) -> None:
        r = ExecutionResult(counts={"0": 600, "1": 400}, shots=1000)
        assert r.total_counts == 1000

    def test_most_frequent(self) -> None:
        r = ExecutionResult(counts={"00": 100, "11": 900}, shots=1000)
        assert r.most_frequent() == "11"

    def test_empty_counts(self) -> None:
        r = ExecutionResult(counts={}, shots=0)
        assert r.total_counts == 0
        assert r.probabilities == {}
        assert r.most_frequent() is None
        assert r.entropy() == 0.0

    def test_entropy_uniform(self) -> None:
        r = ExecutionResult(counts={"00": 500, "01": 500, "10": 500, "11": 500}, shots=2000)
        assert abs(r.entropy() - 2.0) < 1e-9  # log2(4) = 2

    def test_entropy_deterministic(self) -> None:
        r = ExecutionResult(counts={"00": 1000}, shots=1000)
        assert r.entropy() == 0.0

    def test_fidelity_perfect(self) -> None:
        r = ExecutionResult(counts={"00": 500, "11": 500}, shots=1000)
        ideal = {"00": 0.5, "11": 0.5}
        assert abs(r.fidelity_to_ideal(ideal) - 1.0) < 1e-6

    def test_fidelity_orthogonal(self) -> None:
        r = ExecutionResult(counts={"00": 1000}, shots=1000)
        ideal = {"11": 1.0}
        assert r.fidelity_to_ideal(ideal) == 0.0

    def test_to_dict_includes_key_fields(self) -> None:
        r = ExecutionResult(
            counts={"0": 1},
            shots=1,
            execution_time_ms=5.0,
            backend_name="sim",
        )
        d = r.to_dict()
        assert d["counts"] == {"0": 1}
        assert d["execution_time_ms"] == 5.0
        assert d["backend_name"] == "sim"
