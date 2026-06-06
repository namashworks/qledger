"""Benchmark suite runner — orchestrates benchmarks and stores results."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from qledger.adapters.base import BaseAdapter
from qledger.storage.database import QLedgerStore

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Outcome of a single benchmark run.

    Parameters
    ----------
    benchmark_type : str
        Identifier (e.g. ``"quantum_volume"``, ``"clops"``, ``"vqe"``).
    backend_name : str
        Backend used for the benchmark.
    framework : str
        Framework adapter name.
    score : float | None
        Primary scalar score (meaning depends on benchmark type).
    passed : bool
        Whether the benchmark threshold was met.
    details : dict
        Full breakdown of the benchmark result.
    parameters : dict
        Configuration used for the benchmark.
    """

    benchmark_type: str
    backend_name: str
    framework: str = ""
    score: float | None = None
    passed: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        score_str = f"{self.score:.4f}" if self.score is not None else "N/A"
        return (
            f"[{status}] {self.benchmark_type} on {self.backend_name}: "
            f"score={score_str}"
        )


class BenchmarkSuite:
    """Orchestrates benchmark execution and result persistence.

    Parameters
    ----------
    store : QLedgerStore
        Database for persisting results.
    adapter : BaseAdapter
        Framework adapter used for circuit execution.
    """

    def __init__(self, store: QLedgerStore, adapter: BaseAdapter) -> None:
        self._store = store
        self._adapter = adapter

    def run_quantum_volume(
        self,
        backend: Any | None = None,
        max_depth: int = 10,
        num_trials: int = 100,
        shots: int = 1024,
        seed: int | None = None,
    ) -> BenchmarkResult:
        """Run the Quantum Volume benchmark.

        Parameters
        ----------
        backend : Any, optional
            Backend to benchmark.
        max_depth : int
            Maximum circuit depth to test (tests 2..max_depth qubits).
        num_trials : int
            Number of random circuits per depth.
        shots : int
            Shots per circuit.
        seed : int, optional
            Random seed for reproducibility.
        """
        from .quantum_volume import QuantumVolumeBenchmark

        bench = QuantumVolumeBenchmark(self._adapter)
        result = bench.run(
            backend=backend,
            max_depth=max_depth,
            num_trials=num_trials,
            shots=shots,
            seed=seed,
        )
        self._persist(result)
        return result

    def run_clops(
        self,
        backend: Any | None = None,
        num_qubits: int = 2,
        num_circuits: int = 100,
        shots: int = 1024,
    ) -> BenchmarkResult:
        """Run the CLOPS (Circuit Layer Operations Per Second) benchmark."""
        from .clops import CLOPSBenchmark

        bench = CLOPSBenchmark(self._adapter)
        result = bench.run(
            backend=backend,
            num_qubits=num_qubits,
            num_circuits=num_circuits,
            shots=shots,
        )
        self._persist(result)
        return result

    def run_algorithmic(
        self,
        algorithm: str = "ghz",
        backend: Any | None = None,
        qubit_range: tuple[int, int] = (2, 8),
        shots: int = 4096,
        seed: int | None = None,
    ) -> BenchmarkResult:
        """Run an algorithmic benchmark (GHZ, QFT, etc.)."""
        from .algorithmic import AlgorithmicBenchmark

        bench = AlgorithmicBenchmark(self._adapter)
        result = bench.run(
            algorithm=algorithm,
            backend=backend,
            qubit_range=qubit_range,
            shots=shots,
            seed=seed,
        )
        self._persist(result)
        return result

    def run_all(
        self,
        backend: Any | None = None,
        shots: int = 1024,
        seed: int | None = None,
    ) -> list[BenchmarkResult]:
        """Run the full benchmark suite with sensible per-benchmark defaults.

        Only ``shots`` and ``seed`` are shared across benchmarks. For finer
        control, call each benchmark individually.
        """
        results = [
            self.run_quantum_volume(backend=backend, shots=shots, seed=seed),
            self.run_clops(backend=backend, shots=shots),
        ]
        for algo in ("ghz", "qft"):
            results.append(
                self.run_algorithmic(
                    algorithm=algo, backend=backend, shots=shots, seed=seed
                )
            )
        return results

    def _persist(self, result: BenchmarkResult) -> None:
        self._store.save_benchmark(
            benchmark_type=result.benchmark_type,
            backend_name=result.backend_name,
            score=result.score,
            details=result.details,
            parameters=result.parameters,
            framework=result.framework,
        )
        logger.info(result.summary())

    def get_results(
        self,
        benchmark_type: str | None = None,
        backend_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query stored benchmark results."""
        return self._store.list_benchmarks(
            benchmark_type=benchmark_type,
            backend_name=backend_name,
            limit=limit,
        )

    def compare_backends(
        self,
        benchmark_type: str,
        backend_names: list[str],
    ) -> dict[str, Any]:
        """Compare benchmark scores across multiple backends."""
        comparison: dict[str, Any] = {"benchmark_type": benchmark_type, "backends": {}}
        for name in backend_names:
            results = self._store.list_benchmarks(
                benchmark_type=benchmark_type,
                backend_name=name,
                limit=1,
            )
            if results:
                import json
                details = results[0].get("details", "{}")
                if isinstance(details, str):
                    details = json.loads(details)
                comparison["backends"][name] = {
                    "score": results[0].get("score"),
                    "details": details,
                    "timestamp": results[0].get("created_at"),
                }
        return comparison
