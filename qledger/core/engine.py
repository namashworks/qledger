"""QLedger — the unified quantum experiment lifecycle engine.

This is the main entry point for the entire platform.  It provides a single
coherent interface for:

* Creating and managing experiments
* Executing circuits across any supported framework
* Versioning circuits as they evolve
* Capturing and tracking noise profiles
* Running standardised benchmarks
* Exporting and querying all stored data

Usage
-----
>>> from qledger import QLedger
>>> db = QLedger("my_research.db")
>>> exp = db.create_experiment("Bell States", tags=["entanglement"])
>>> result = db.run(qiskit_circuit, experiment_id=exp, framework="qiskit", shots=4096)
>>> print(result.probabilities)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from qledger.adapters.base import BaseAdapter
from qledger.adapters.registry import AdapterRegistry
from qledger.benchmarks.suite import BenchmarkResult, BenchmarkSuite
from qledger.noise.profiler import NoiseProfiler
from qledger.schema.circuit import UniversalCircuit
from qledger.schema.noise import NoiseSnapshot
from qledger.schema.result import ExecutionResult
from qledger.storage.database import QLedgerStore
from qledger.versioning.tracker import CircuitDiff, CircuitVersionTracker

logger = logging.getLogger(__name__)


class QLedger:
    """The unified quantum experiment lifecycle engine.

    Parameters
    ----------
    db_path : str | Path
        Path to the SQLite database file.  Created on first use.
        Use ``":memory:"`` for ephemeral storage.
    default_framework : str
        Default framework adapter to use (``"qiskit"``, ``"cirq"``,
        ``"pennylane"``).  Can be overridden per-call.
    default_shots : int
        Default number of measurement shots.
    """

    def __init__(
        self,
        db_path: str | Path = "qledger.sqlite",
        default_framework: str = "qiskit",
        default_shots: int = 1024,
    ) -> None:
        self._store = QLedgerStore(db_path)
        self._default_framework = default_framework
        self._default_shots = default_shots
        self._version_tracker = CircuitVersionTracker(self._store)
        self._noise_profiler = NoiseProfiler(self._store)

    # ------------------------------------------------------------------
    # Adapter resolution
    # ------------------------------------------------------------------

    def _get_adapter(self, framework: str | None = None) -> BaseAdapter:
        fw = framework or self._default_framework
        return AdapterRegistry.get(fw)

    # ==================================================================
    # EXPERIMENTS
    # ==================================================================

    def create_experiment(
        self,
        name: str,
        description: str = "",
        tags: list[str] | None = None,
    ) -> int:
        """Create a named experiment container. Returns the experiment id."""
        exp_id = self._store.create_experiment(name, description, tags)
        logger.info("Created experiment %d: %s", exp_id, name)
        return exp_id

    def get_experiment(self, experiment_id: int) -> dict[str, Any] | None:
        return self._store.get_experiment(experiment_id)

    def list_experiments(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._store.list_experiments(**kwargs)

    def delete_experiment(self, experiment_id: int) -> bool:
        return self._store.delete_experiment(experiment_id)

    def get_experiment_summary(self, experiment_id: int) -> dict[str, Any] | None:
        return self._store.get_experiment_summary(experiment_id)

    # ==================================================================
    # CIRCUIT EXECUTION
    # ==================================================================

    def run(
        self,
        circuit: Any,
        *,
        experiment_id: int | None = None,
        experiment_name: str | None = None,
        name: str = "",
        framework: str | None = None,
        backend: Any | None = None,
        shots: int | None = None,
        seed_simulator: int | None = None,
        optimization_level: int | None = None,
        transpiler_seed: int | None = None,
        save_statevector: bool = False,
        save_memory: bool = False,
        auto_version: bool = True,
        extra_metadata: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute a circuit, persist everything, and return the result.

        Accepts **any** native circuit type (Qiskit QuantumCircuit, Cirq
        Circuit, PennyLane tape) — the appropriate adapter is selected
        automatically or via the ``framework`` parameter.

        Parameters
        ----------
        circuit : Any
            A native circuit object or a ``UniversalCircuit``.
        experiment_id : int, optional
            Existing experiment to attach this run to.
        experiment_name : str, optional
            Auto-create an experiment with this name if ``experiment_id``
            is not given.
        name : str
            Label for this circuit.
        framework : str, optional
            Override the default framework adapter.
        backend : Any, optional
            Backend to execute on (framework-specific).
        shots : int, optional
            Number of shots (defaults to ``default_shots``).
        seed_simulator : int, optional
            Simulator seed for reproducibility.
        optimization_level : int, optional
            Transpiler optimisation level.
        transpiler_seed : int, optional
            Transpiler seed.
        save_statevector : bool
            Request statevector output.
        save_memory : bool
            Request per-shot measurement memory.
        auto_version : bool
            Automatically version the circuit on each run.
        extra_metadata : dict, optional
            Arbitrary key-value pairs stored with the execution.

        Returns
        -------
        ExecutionResult
        """
        adapter = self._get_adapter(framework)

        # Resolve experiment
        if experiment_id is None:
            exp_name = experiment_name or "default"
            experiment_id = self._store.create_experiment(exp_name)

        # Convert to UniversalCircuit if native
        if isinstance(circuit, UniversalCircuit):
            uc = circuit
        else:
            uc = adapter.from_native(circuit, name=name)

        # Save circuit to database
        circuit_id = self._store.save_circuit(
            experiment_id=experiment_id,
            circuit_json=uc.to_json(),
            content_hash=uc.content_hash(),
            num_qubits=uc.num_qubits,
            num_clbits=uc.num_clbits,
            depth=uc.depth,
            total_gates=uc.total_gates,
            two_qubit_gates=uc.two_qubit_gate_count,
            gate_counts=uc.gate_counts,
            name=uc.name or name,
            source_framework=adapter.framework_name,
        )

        # Auto-version
        if auto_version:
            self._version_tracker.commit(circuit_id, uc, message=f"Run: {name}")

        # Execute
        resolved_shots = shots or self._default_shots
        result = adapter.execute(
            uc,
            backend=backend,
            shots=resolved_shots,
            seed_simulator=seed_simulator,
            optimization_level=optimization_level,
            transpiler_seed=transpiler_seed,
            save_statevector=save_statevector,
            save_memory=save_memory,
        )

        # Persist execution
        exec_data = {
            "backend_name": result.backend_name,
            "backend_version": result.backend_version,
            "framework": adapter.framework_name,
            "shots": resolved_shots,
            "seed_simulator": seed_simulator,
            "optimization_level": optimization_level,
            "transpiler_seed": transpiler_seed,
            "counts": result.counts,
            "probabilities": result.probabilities,
            "most_frequent": result.most_frequent(),
            "entropy": result.entropy(),
            "statevector": result.statevector,
            "memory": result.memory,
            "execution_time_ms": result.execution_time_ms,
            "success": result.success,
            "error_message": result.error_message,
            "simulator_config": result.simulator_config,
            "extra_metadata": extra_metadata or {},
        }
        self._store.save_execution(circuit_id, exec_data)

        logger.info(
            "Executed on %s (%d shots, %.1f ms) → %s",
            result.backend_name,
            resolved_shots,
            result.execution_time_ms or 0,
            result.most_frequent() or "N/A",
        )

        return result

    def run_batch(
        self,
        circuits: list[Any],
        *,
        experiment_id: int | None = None,
        experiment_name: str | None = None,
        names: list[str] | None = None,
        **kwargs: Any,
    ) -> list[ExecutionResult]:
        """Execute multiple circuits under a single experiment.

        Parameters
        ----------
        circuits : list
            Native or universal circuits.
        names : list[str], optional
            Per-circuit labels.
        **kwargs
            Forwarded to ``run()`` for each circuit.

        Returns
        -------
        list[ExecutionResult]
        """
        if names and len(names) != len(circuits):
            raise ValueError("Length of names must match length of circuits.")

        if experiment_id is None:
            exp_name = experiment_name or "batch"
            experiment_id = self._store.create_experiment(exp_name)

        results = []
        for i, circ in enumerate(circuits):
            lbl = names[i] if names else ""
            res = self.run(circ, experiment_id=experiment_id, name=lbl, **kwargs)
            results.append(res)
        return results

    # ==================================================================
    # CIRCUIT VERSIONING
    # ==================================================================

    def version_circuit(
        self, circuit_id: int, circuit: UniversalCircuit, message: str = ""
    ) -> int:
        """Manually commit a new version of a circuit."""
        return self._version_tracker.commit(circuit_id, circuit, message)

    def circuit_log(self, circuit_id: int) -> list[dict[str, Any]]:
        """Get version history for a circuit."""
        return self._version_tracker.log(circuit_id)

    def checkout_circuit(self, circuit_id: int, version: int) -> UniversalCircuit | None:
        """Restore a specific version of a circuit."""
        return self._version_tracker.checkout(circuit_id, version)

    def diff_circuit(
        self, circuit_id: int, version_a: int, version_b: int
    ) -> CircuitDiff | None:
        """Compute diff between two circuit versions."""
        return self._version_tracker.diff(circuit_id, version_a, version_b)

    # ==================================================================
    # NOISE PROFILING
    # ==================================================================

    def capture_noise(
        self,
        backend: Any,
        framework: str | None = None,
    ) -> NoiseSnapshot:
        """Capture a noise snapshot from a backend."""
        adapter = self._get_adapter(framework)
        return self._noise_profiler.capture(adapter, backend)

    def get_noise_history(self, backend_name: str, limit: int = 50) -> list[NoiseSnapshot]:
        """Get historical noise snapshots for a backend."""
        return self._noise_profiler.get_history(backend_name, limit)

    def compare_noise(
        self, snapshot_a: NoiseSnapshot, snapshot_b: NoiseSnapshot
    ) -> dict[str, Any]:
        """Compare two noise snapshots."""
        return self._noise_profiler.compare(snapshot_a, snapshot_b)

    def best_qubits(
        self, backend_name: str, count: int = 5, metric: str = "t1"
    ) -> list[dict[str, Any]]:
        """Find the best qubits on a backend by a given metric."""
        return self._noise_profiler.best_qubits(backend_name, count, metric)

    # ==================================================================
    # BENCHMARKS
    # ==================================================================

    def benchmark(self, framework: str | None = None) -> BenchmarkSuite:
        """Get a benchmark suite instance.

        Usage
        -----
        >>> suite = db.benchmark()
        >>> result = suite.run_quantum_volume(backend=my_backend)
        >>> result = suite.run_clops()
        >>> result = suite.run_algorithmic(algorithm="ghz")
        """
        adapter = self._get_adapter(framework)
        return BenchmarkSuite(self._store, adapter)

    def run_benchmark(
        self,
        benchmark_type: str,
        backend: Any | None = None,
        framework: str | None = None,
        **kwargs: Any,
    ) -> BenchmarkResult:
        """Run a specific benchmark.

        Parameters
        ----------
        benchmark_type : str
            One of ``"quantum_volume"``, ``"clops"``, ``"ghz"``, ``"qft"``.
        """
        suite = self.benchmark(framework)
        if benchmark_type == "quantum_volume":
            return suite.run_quantum_volume(backend=backend, **kwargs)
        elif benchmark_type == "clops":
            return suite.run_clops(backend=backend, **kwargs)
        elif benchmark_type in ("ghz", "qft"):
            return suite.run_algorithmic(algorithm=benchmark_type, backend=backend, **kwargs)
        else:
            raise ValueError(f"Unknown benchmark type: {benchmark_type!r}")

    def get_benchmark_results(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Query stored benchmark results."""
        return self._store.list_benchmarks(**kwargs)

    # ==================================================================
    # DATA ACCESS
    # ==================================================================

    def get_history(self, experiment_id: int) -> list[dict[str, Any]]:
        """Full execution history for an experiment."""
        return self._store.get_full_history(experiment_id)

    def export_experiment(self, experiment_id: int) -> dict[str, Any]:
        """Export a complete experiment as a JSON-serializable dict."""
        return self._store.export_experiment(experiment_id)

    def list_circuits(self, experiment_id: int) -> list[dict[str, Any]]:
        return self._store.list_circuits(experiment_id)

    def list_executions(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._store.list_executions(**kwargs)

    # ==================================================================
    # CROSS-FRAMEWORK CONVERSION
    # ==================================================================

    def convert(
        self,
        circuit: Any,
        *,
        from_framework: str,
        to_framework: str,
    ) -> Any:
        """Convert a circuit between frameworks.

        Parameters
        ----------
        circuit : Any
            Native circuit in the source framework.
        from_framework : str
            Source framework (``"qiskit"``, ``"cirq"``, ``"pennylane"``).
        to_framework : str
            Target framework.

        Returns
        -------
        Any
            Native circuit in the target framework.

        Examples
        --------
        >>> cirq_circuit = db.convert(qiskit_circuit, from_framework="qiskit", to_framework="cirq")
        """
        source = self._get_adapter(from_framework)
        target = self._get_adapter(to_framework)
        uc = source.from_native(circuit)
        return target.to_native(uc)

    # ==================================================================
    # LIFECYCLE
    # ==================================================================

    @property
    def store(self) -> QLedgerStore:
        """Direct access to the underlying database store (advanced)."""
        return self._store

    def close(self) -> None:
        """Close the database connection."""
        self._store.close()

    def __enter__(self) -> QLedger:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"QLedger(db={self._store._path!r}, framework={self._default_framework!r})"
