"""CLOPS (Circuit Layer Operations Per Second) benchmark.

CLOPS measures the throughput of a quantum system — how many circuit
layers it can process per second, including transpilation, execution,
and result retrieval.  It captures the end-to-end speed of the quantum
execution pipeline.

Definition
----------
CLOPS = (num_circuits x layers_per_circuit x shots) / total_time_seconds

This is a practical metric: a backend with high quantum volume but low
CLOPS is bottlenecked by its software stack or queue management.

References
----------
* Wack et al., "Quality, Speed, and Scale: three key attributes to measure
  the performance of near-term quantum computers" (2021).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from qledger.adapters.base import BaseAdapter
from qledger.schema.circuit import Instruction, Measurement, UniversalCircuit

from .suite import BenchmarkResult

logger = logging.getLogger(__name__)


def _generate_clops_circuit(num_qubits: int, depth: int = 1) -> UniversalCircuit:
    """Generate a simple parameterised circuit for CLOPS measurement.

    The circuit has `depth` layers, each consisting of single-qubit gates
    on every qubit followed by a layer of CNOT gates on adjacent pairs.
    """
    instructions: list[Instruction] = []

    for _ in range(depth):
        # Layer of Hadamards
        for q in range(num_qubits):
            instructions.append(Instruction("h", (q,), ()))
        # Layer of CNOTs
        for q in range(0, num_qubits - 1, 2):
            instructions.append(Instruction("cx", (q, q + 1), ()))

    measurements = [Measurement(q, q) for q in range(num_qubits)]

    return UniversalCircuit(
        num_qubits=num_qubits,
        num_clbits=num_qubits,
        instructions=instructions,
        measurements=measurements,
        name=f"clops_{num_qubits}q_{depth}d",
    )


class CLOPSBenchmark:
    """CLOPS benchmark runner.

    Parameters
    ----------
    adapter : BaseAdapter
        Framework adapter for circuit execution.
    """

    def __init__(self, adapter: BaseAdapter) -> None:
        self._adapter = adapter

    def run(
        self,
        backend: Any | None = None,
        num_qubits: int = 2,
        num_circuits: int = 100,
        shots: int = 1024,
    ) -> BenchmarkResult:
        backend_name = self._get_backend_name(backend)
        circuit = _generate_clops_circuit(num_qubits, depth=1)

        logger.info("CLOPS: Running %d circuits x %d shots on %s...",
                     num_circuits, shots, backend_name)

        execution_times: list[float] = []
        successes = 0

        total_start = time.perf_counter()

        for _ in range(num_circuits):
            result = self._adapter.execute(
                circuit,
                backend=backend,
                shots=shots,
            )
            if result.success and result.execution_time_ms is not None:
                execution_times.append(result.execution_time_ms)
                successes += 1

        total_elapsed_s = time.perf_counter() - total_start

        # CLOPS = (M x D x S) / T
        # M = num_circuits, D = depth (1 layer), S = shots, T = total time
        layers_per_circuit = 1
        clops = (
            (num_circuits * layers_per_circuit * shots) / total_elapsed_s
            if total_elapsed_s > 0 else 0
        )

        avg_time = sum(execution_times) / len(execution_times) if execution_times else 0
        min_time = min(execution_times) if execution_times else 0
        max_time = max(execution_times) if execution_times else 0

        return BenchmarkResult(
            benchmark_type="clops",
            backend_name=backend_name,
            framework=self._adapter.framework_name,
            score=round(clops, 2),
            passed=successes == num_circuits,
            details={
                "clops": round(clops, 2),
                "total_time_s": round(total_elapsed_s, 3),
                "circuits_executed": successes,
                "circuits_failed": num_circuits - successes,
                "avg_execution_ms": round(avg_time, 3),
                "min_execution_ms": round(min_time, 3),
                "max_execution_ms": round(max_time, 3),
            },
            parameters={
                "num_qubits": num_qubits,
                "num_circuits": num_circuits,
                "shots": shots,
            },
        )

    @staticmethod
    def _get_backend_name(backend: Any) -> str:
        if backend is None:
            return "default_simulator"
        name = getattr(backend, "name", type(backend).__name__)
        return name() if callable(name) else str(name)
