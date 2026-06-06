"""Abstract base class for all framework adapters.

Every adapter must implement this interface.  The contract is deliberately
narrow so that adding support for a new framework (e.g. Amazon Braket,
Azure Quantum) requires minimal boilerplate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from qledger.schema.circuit import UniversalCircuit
from qledger.schema.noise import NoiseSnapshot
from qledger.schema.result import ExecutionResult


class AdapterError(Exception):
    """Raised when an adapter operation fails."""


class BaseAdapter(ABC):
    """Interface that every framework adapter must implement.

    Subclasses must define
    ----------------------
    * ``framework_name`` — identifier used in gate alias lookups and storage.
    * ``from_native`` — convert a native circuit to ``UniversalCircuit``.
    * ``to_native`` — convert a ``UniversalCircuit`` back to a native circuit.
    * ``execute`` — run a circuit on a backend and return an ``ExecutionResult``.
    * ``get_noise_snapshot`` — extract calibration data from a backend.
    * ``list_backends`` — enumerate available backends.
    """

    @property
    @abstractmethod
    def framework_name(self) -> str:
        """Short lowercase identifier (e.g. ``"qiskit"``, ``"cirq"``)."""
        ...

    @property
    @abstractmethod
    def framework_version(self) -> str:
        """Installed version string of the framework."""
        ...

    # ------------------------------------------------------------------
    # Circuit conversion
    # ------------------------------------------------------------------

    @abstractmethod
    def from_native(self, circuit: Any, name: str = "") -> UniversalCircuit:
        """Convert a native circuit object to ``UniversalCircuit``.

        Parameters
        ----------
        circuit : Any
            Framework-specific circuit object.
        name : str
            Optional label for the circuit.

        Returns
        -------
        UniversalCircuit

        Raises
        ------
        AdapterError
            If the circuit contains gates that cannot be mapped.
        """
        ...

    @abstractmethod
    def to_native(self, circuit: UniversalCircuit) -> Any:
        """Convert a ``UniversalCircuit`` to the framework's native type.

        Parameters
        ----------
        circuit : UniversalCircuit

        Returns
        -------
        Any
            Native circuit object.

        Raises
        ------
        AdapterError
            If a gate in the universal circuit has no mapping in this framework.
        """
        ...

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(
        self,
        circuit: UniversalCircuit,
        backend: Any | None = None,
        *,
        shots: int = 1024,
        seed_simulator: int | None = None,
        optimization_level: int | None = None,
        transpiler_seed: int | None = None,
        save_statevector: bool = False,
        save_memory: bool = False,
        extra_run_options: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute a universal circuit and return a structured result.

        Parameters
        ----------
        circuit : UniversalCircuit
            Circuit in the universal IR.
        backend : Any, optional
            Backend to execute on.  If None, the adapter should provide
            a sensible default (e.g. local simulator).
        shots : int
            Number of measurement shots.
        seed_simulator : int, optional
            Seed for the simulator's random number generator.
        optimization_level : int, optional
            Transpiler optimisation level.
        transpiler_seed : int, optional
            Seed for transpiler stochastic passes.
        save_statevector : bool
            Request statevector output (simulator-only).
        save_memory : bool
            Request per-shot measurement memory.
        extra_run_options : dict, optional
            Additional framework-specific options passed to the runner.

        Returns
        -------
        ExecutionResult
        """
        ...

    # ------------------------------------------------------------------
    # Noise profiling
    # ------------------------------------------------------------------

    @abstractmethod
    def get_noise_snapshot(self, backend: Any) -> NoiseSnapshot:
        """Extract current calibration / noise data from a backend.

        Parameters
        ----------
        backend : Any
            A backend instance (real hardware or simulator with a noise model).

        Returns
        -------
        NoiseSnapshot
        """
        ...

    # ------------------------------------------------------------------
    # Backend discovery
    # ------------------------------------------------------------------

    @abstractmethod
    def list_backends(self, **filters: Any) -> list[dict[str, Any]]:
        """Enumerate available backends.

        Returns
        -------
        list[dict[str, Any]]
            Each dict contains at least ``{"name": str, "num_qubits": int,
            "simulator": bool}``.
        """
        ...
