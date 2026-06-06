"""Standardised benchmark suite for quantum hardware comparison.

Provides implementations of:
* **Quantum Volume** — the industry-standard measure of quantum computational
  capability (as defined by IBM).
* **CLOPS** — Circuit Layer Operations Per Second, measuring throughput.
* **Algorithmic benchmarks** — VQE, QAOA, and Grover circuits at varying
  problem sizes, measuring fidelity against known ideal results.
"""

from .algorithmic import AlgorithmicBenchmark
from .clops import CLOPSBenchmark
from .quantum_volume import QuantumVolumeBenchmark
from .suite import BenchmarkResult, BenchmarkSuite

__all__ = [
    "AlgorithmicBenchmark",
    "BenchmarkResult",
    "BenchmarkSuite",
    "CLOPSBenchmark",
    "QuantumVolumeBenchmark",
]
