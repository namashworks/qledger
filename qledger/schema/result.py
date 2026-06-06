"""Execution result model — framework-agnostic representation of circuit outcomes."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """Holds the outcome of a single circuit execution.

    Every adapter produces an ``ExecutionResult`` regardless of which
    framework ran the circuit.  This makes it possible to compare results
    across Qiskit, Cirq, and PennyLane in a uniform way.

    Parameters
    ----------
    counts : dict[str, int]
        Measurement outcome counts keyed by bitstring (e.g. ``{"00": 512, "11": 512}``).
    shots : int
        Number of shots requested.
    backend_name : str
        Name of the backend / simulator that executed the circuit.
    backend_version : str
        Version string of the backend, if available.
    success : bool
        Whether execution completed without error.
    error_message : str | None
        Error description if ``success`` is False.
    statevector : list[complex] | None
        Final statevector, if requested and available.
    memory : list[str] | None
        Per-shot measurement outcomes, if requested.
    execution_time_ms : float | None
        Wall-clock execution time in milliseconds.
    seed_simulator : int | None
        Simulator seed used for this execution.
    optimization_level : int | None
        Transpiler optimization level (0-3).
    transpiler_seed : int | None
        Seed for the transpiler's stochastic passes.
    simulator_config : dict
        Full backend / simulator configuration snapshot.
    extra_metadata : dict
        Arbitrary user-supplied metadata.
    """

    counts: dict[str, int]
    shots: int
    backend_name: str = ""
    backend_version: str = ""
    success: bool = True
    error_message: str | None = None
    statevector: list[complex] | None = None
    memory: list[str] | None = None
    execution_time_ms: float | None = None
    seed_simulator: int | None = None
    optimization_level: int | None = None
    transpiler_seed: int | None = None
    simulator_config: dict[str, Any] = field(default_factory=dict)
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def total_counts(self) -> int:
        """Sum of all measurement counts."""
        return sum(self.counts.values())

    @property
    def probabilities(self) -> dict[str, float]:
        """Normalised probability distribution."""
        total = self.total_counts
        if total == 0:
            return {}
        return {k: v / total for k, v in self.counts.items()}

    def most_frequent(self) -> str | None:
        """Bitstring with the highest count (None if empty)."""
        if not self.counts:
            return None
        return max(self.counts, key=self.counts.get)  # type: ignore[arg-type]

    def entropy(self) -> float:
        """Shannon entropy of the measurement distribution (in bits)."""
        total = self.total_counts
        if total == 0:
            return 0.0
        h = 0.0
        for count in self.counts.values():
            if count > 0:
                p = count / total
                h -= p * math.log2(p)
        return h

    def fidelity_to_ideal(self, ideal_probs: dict[str, float]) -> float:
        """Classical fidelity between measured probabilities and ideal distribution.

        Uses the Bhattacharyya coefficient:
        F = (Σ √(p_i · q_i))²

        Parameters
        ----------
        ideal_probs : dict[str, float]
            Ideal probability distribution to compare against.

        Returns
        -------
        float
            Fidelity in [0, 1].
        """
        measured = self.probabilities
        all_keys = set(measured) | set(ideal_probs)
        bc = sum(
            math.sqrt(measured.get(k, 0.0) * ideal_probs.get(k, 0.0))
            for k in all_keys
        )
        return bc * bc

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "counts": self.counts,
            "shots": self.shots,
            "backend_name": self.backend_name,
            "success": self.success,
            "total_counts": self.total_counts,
            "probabilities": self.probabilities,
            "most_frequent": self.most_frequent(),
            "entropy": round(self.entropy(), 6),
        }
        if self.backend_version:
            d["backend_version"] = self.backend_version
        if self.error_message:
            d["error_message"] = self.error_message
        if self.statevector is not None:
            d["statevector_length"] = len(self.statevector)
        if self.memory is not None:
            d["memory_samples"] = len(self.memory)
        if self.execution_time_ms is not None:
            d["execution_time_ms"] = round(self.execution_time_ms, 3)
        if self.seed_simulator is not None:
            d["seed_simulator"] = self.seed_simulator
        if self.optimization_level is not None:
            d["optimization_level"] = self.optimization_level
        if self.transpiler_seed is not None:
            d["transpiler_seed"] = self.transpiler_seed
        if self.simulator_config:
            d["simulator_config"] = self.simulator_config
        if self.extra_metadata:
            d["extra_metadata"] = self.extra_metadata
        return d
