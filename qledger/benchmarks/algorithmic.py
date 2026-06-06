"""Algorithmic benchmarks — measure fidelity of standard quantum algorithms.

Tests how well a backend executes well-understood quantum algorithms by
comparing measured output distributions against known ideal outcomes.

Supported algorithms
--------------------
* **GHZ** — Greenberger-Horne-Zeilinger state.  Ideal: equal superposition
  of |000...0⟩ and |111...1⟩.
* **QFT** — Quantum Fourier Transform applied to a computational basis state.
  Ideal: known uniform-phase output distribution.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from qledger.adapters.base import BaseAdapter
from qledger.schema.circuit import Instruction, Measurement, UniversalCircuit

from .suite import BenchmarkResult

logger = logging.getLogger(__name__)


# ======================================================================
# Circuit generators
# ======================================================================

def _ghz_circuit(n: int) -> UniversalCircuit:
    """Create an n-qubit GHZ state circuit."""
    instructions = [Instruction("h", (0,), ())]
    for i in range(1, n):
        instructions.append(Instruction("cx", (0, i), ()))
    measurements = [Measurement(q, q) for q in range(n)]
    return UniversalCircuit(
        num_qubits=n, num_clbits=n,
        instructions=instructions, measurements=measurements,
        name=f"ghz_{n}",
    )


def _qft_circuit(n: int) -> UniversalCircuit:
    """Create an n-qubit QFT circuit applied to |1⟩ (X on qubit 0)."""
    instructions: list[Instruction] = []

    # Prepare input state |1⟩
    instructions.append(Instruction("x", (0,), ()))

    # QFT
    for i in range(n):
        instructions.append(Instruction("h", (i,), ()))
        for j in range(i + 1, n):
            angle = math.pi / (2 ** (j - i))
            instructions.append(Instruction("cp", (j, i), (angle,)))

    # Swap to get correct output ordering
    for i in range(n // 2):
        instructions.append(Instruction("swap", (i, n - 1 - i), ()))

    measurements = [Measurement(q, q) for q in range(n)]
    return UniversalCircuit(
        num_qubits=n, num_clbits=n,
        instructions=instructions, measurements=measurements,
        name=f"qft_{n}",
    )


# ======================================================================
# Ideal distributions
# ======================================================================

def _ghz_ideal(n: int) -> dict[str, float]:
    """Ideal probability distribution for an n-qubit GHZ state."""
    zeros = "0" * n
    ones = "1" * n
    return {zeros: 0.5, ones: 0.5}


def _qft_ideal(n: int) -> dict[str, float]:
    """Ideal distribution for QFT applied to |1⟩.

    QFT|1⟩ produces a uniform distribution over all 2^n basis states
    (with phases that are not observable in Z-basis measurement).
    """
    num_states = 2 ** n
    prob = 1.0 / num_states
    return {format(i, f"0{n}b"): prob for i in range(num_states)}


_CIRCUIT_GENERATORS: dict[str, Any] = {
    "ghz": (_ghz_circuit, _ghz_ideal),
    "qft": (_qft_circuit, _qft_ideal),
}


# ======================================================================
# Benchmark runner
# ======================================================================

class AlgorithmicBenchmark:
    """Algorithmic benchmark runner.

    Parameters
    ----------
    adapter : BaseAdapter
        Framework adapter for circuit execution.
    """

    def __init__(self, adapter: BaseAdapter) -> None:
        self._adapter = adapter

    def run(
        self,
        algorithm: str = "ghz",
        backend: Any | None = None,
        qubit_range: tuple[int, int] = (2, 8),
        shots: int = 4096,
        seed: int | None = None,
    ) -> BenchmarkResult:
        if algorithm not in _CIRCUIT_GENERATORS:
            raise ValueError(
                f"Unknown algorithm {algorithm!r}. "
                f"Available: {', '.join(_CIRCUIT_GENERATORS)}"
            )

        gen_circuit, gen_ideal = _CIRCUIT_GENERATORS[algorithm]
        backend_name = self._get_backend_name(backend)

        logger.info("Algorithmic benchmark: %s on %s (qubits %d-%d)",
                     algorithm, backend_name, qubit_range[0], qubit_range[1])

        qubit_results: dict[int, dict[str, Any]] = {}
        fidelities: list[float] = []

        for n in range(qubit_range[0], qubit_range[1] + 1):
            circuit = gen_circuit(n)
            ideal = gen_ideal(n)

            result = self._adapter.execute(
                circuit,
                backend=backend,
                shots=shots,
                seed_simulator=seed,
            )

            if not result.success:
                qubit_results[n] = {"success": False, "error": result.error_message}
                continue

            fidelity = result.fidelity_to_ideal(ideal)
            entropy = result.entropy()

            qubit_results[n] = {
                "success": True,
                "fidelity": round(fidelity, 6),
                "entropy": round(entropy, 6),
                "top_counts": dict(
                    sorted(result.counts.items(), key=lambda x: -x[1])[:5]
                ),
            }
            fidelities.append(fidelity)

            logger.info(
                "  %s n=%d: fidelity=%.4f, entropy=%.4f",
                algorithm, n, fidelity, entropy,
            )

        avg_fidelity = sum(fidelities) / len(fidelities) if fidelities else 0.0

        return BenchmarkResult(
            benchmark_type=f"algorithmic_{algorithm}",
            backend_name=backend_name,
            framework=self._adapter.framework_name,
            score=round(avg_fidelity, 6),
            passed=avg_fidelity > 0.8,
            details={
                "algorithm": algorithm,
                "average_fidelity": round(avg_fidelity, 6),
                "qubit_range": list(qubit_range),
                "per_qubit_results": qubit_results,
            },
            parameters={
                "algorithm": algorithm,
                "qubit_range": list(qubit_range),
                "shots": shots,
                "seed": seed,
            },
        )

    @staticmethod
    def _get_backend_name(backend: Any) -> str:
        if backend is None:
            return "default_simulator"
        name = getattr(backend, "name", type(backend).__name__)
        return name() if callable(name) else str(name)
