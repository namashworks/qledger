"""PennyLane adapter — converts between PennyLane tapes/QNodes and UniversalCircuit.

Supports PennyLane >= 0.35.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from qledger.schema.circuit import Instruction, Measurement, UniversalCircuit
from qledger.schema.gates import StandardGates
from qledger.schema.noise import NoiseSnapshot
from qledger.schema.result import ExecutionResult

from .base import AdapterError, BaseAdapter
from .registry import AdapterRegistry

logger = logging.getLogger(__name__)

# PennyLane op name → canonical name
_PL_TO_CANONICAL: dict[str, str] = {
    "Identity": "id",
    "Hadamard": "h",
    "PauliX": "x",
    "PauliY": "y",
    "PauliZ": "z",
    "S": "s",
    "T": "t",
    "SX": "sx",
    "RX": "rx",
    "RY": "ry",
    "RZ": "rz",
    "PhaseShift": "p",
    "Rot": "u",
    "CNOT": "cx",
    "CY": "cy",
    "CZ": "cz",
    "SWAP": "swap",
    "ISWAP": "iswap",
    "ECR": "ecr",
    "IsingXX": "rxx",
    "IsingYY": "ryy",
    "IsingZZ": "rzz",
    "ControlledPhaseShift": "cp",
    "CRX": "crx",
    "CRY": "cry",
    "CRZ": "crz",
    "Toffoli": "ccx",
    "CSWAP": "cswap",
}

# Canonical → PennyLane op name (reverse)
_CANONICAL_TO_PL: dict[str, str] = {v: k for k, v in _PL_TO_CANONICAL.items()}


@AdapterRegistry.register
class PennylaneAdapter(BaseAdapter):
    """Adapter for Xanadu PennyLane."""

    _FRAMEWORK_NAME = "pennylane"

    def __init__(self) -> None:
        import pennylane

        self._pennylane = pennylane

    @property
    def framework_name(self) -> str:
        return "pennylane"

    @property
    def framework_version(self) -> str:
        return str(self._pennylane.__version__)

    # ------------------------------------------------------------------
    # PennyLane tape → UniversalCircuit
    # ------------------------------------------------------------------

    def from_native(self, circuit: Any, name: str = "") -> UniversalCircuit:
        """Convert a PennyLane QuantumTape (or QuantumScript) to UniversalCircuit.

        Parameters
        ----------
        circuit : pennylane.tape.QuantumTape | pennylane.tape.QuantumScript
            A PennyLane tape object.
        """
        pl = self._pennylane

        # Accept both QuantumTape and QuantumScript
        tape_types = []
        if hasattr(pl, "tape"):
            if hasattr(pl.tape, "QuantumTape"):
                tape_types.append(pl.tape.QuantumTape)
            if hasattr(pl.tape, "QuantumScript"):
                tape_types.append(pl.tape.QuantumScript)

        if tape_types and not isinstance(circuit, tuple(tape_types)):
            raise AdapterError(
                f"Expected PennyLane QuantumTape or QuantumScript, got {type(circuit).__name__}. "
                f"Use qml.tape.QuantumScript.from_queue() or capture a QNode tape."
            )

        # Determine qubit count
        all_wires: set[int] = set()
        for op in circuit.operations:
            all_wires.update(int(w) for w in op.wires)
        for mp in circuit.measurements:
            if mp.wires:
                all_wires.update(int(w) for w in mp.wires)

        num_qubits = max(all_wires) + 1 if all_wires else 0

        instructions: list[Instruction] = []
        measurements: list[Measurement] = []

        for op in circuit.operations:
            op_name = type(op).__name__
            canonical = _PL_TO_CANONICAL.get(op_name)
            if canonical is None:
                # Try StandardGates resolution
                resolved = StandardGates.resolve(op_name)
                canonical = resolved.canonical_name if resolved else op_name.lower()

            qubits = tuple(int(w) for w in op.wires)
            params = tuple(float(p) for p in op.parameters) if op.parameters else ()
            instructions.append(Instruction(gate=canonical, qubits=qubits, params=params))

        # PennyLane measurements
        clbit = 0
        for mp in circuit.measurements:
            if mp.wires:
                for w in mp.wires:
                    measurements.append(Measurement(qubit=int(w), clbit=clbit))
                    clbit += 1
            else:
                # All-qubit measurement
                for q in range(num_qubits):
                    measurements.append(Measurement(qubit=q, clbit=clbit))
                    clbit += 1

        num_clbits = clbit if clbit > 0 else num_qubits

        return UniversalCircuit(
            num_qubits=num_qubits,
            num_clbits=num_clbits,
            instructions=instructions,
            measurements=measurements,
            name=name,
            metadata={
                "source_framework": "pennylane",
                "pennylane_version": self.framework_version,
            },
        )

    # ------------------------------------------------------------------
    # UniversalCircuit → PennyLane tape
    # ------------------------------------------------------------------

    def to_native(self, circuit: UniversalCircuit) -> Any:
        """Convert a UniversalCircuit to a PennyLane QuantumScript."""
        pl = self._pennylane

        ops: list[Any] = []

        for inst in circuit.instructions:
            pl_name = _CANONICAL_TO_PL.get(inst.gate)
            if pl_name is None:
                raise AdapterError(f"Gate {inst.gate!r} has no PennyLane mapping.")

            op_cls = getattr(pl, pl_name, None) or getattr(pl.ops, pl_name, None)
            if op_cls is None:
                raise AdapterError(
                    f"PennyLane op {pl_name!r} not found in pennylane namespace."
                )

            wires = list(inst.qubits)
            if inst.params:
                ops.append(op_cls(*inst.params, wires=wires))
            else:
                ops.append(op_cls(wires=wires))

        # Add measurements
        measurements_ops: list[Any] = []
        if circuit.measurements:
            measured_wires = [m.qubit for m in circuit.measurements]
            measurements_ops.append(pl.counts(wires=measured_wires))
        else:
            measurements_ops.append(pl.counts(wires=list(range(circuit.num_qubits))))

        tape = pl.tape.QuantumScript(ops, measurements_ops)
        return tape

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

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
        pl = self._pennylane

        device_name = "default.qubit"
        if backend is not None and isinstance(backend, str):
            device_name = backend

        device_kwargs: dict[str, Any] = {
            "wires": circuit.num_qubits,
            "shots": shots,
        }
        if seed_simulator is not None:
            device_kwargs["seed"] = seed_simulator

        dev = pl.device(device_name, **device_kwargs)
        backend_name = device_name

        tape = self.to_native(circuit)

        t0 = time.perf_counter()
        try:
            result = pl.execute(tape, dev)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            # Parse PennyLane counts result
            counts: dict[str, int] = {}
            if isinstance(result, dict):
                counts = {str(k): int(v) for k, v in result.items()}
            elif hasattr(result, "item"):
                # numpy scalar
                counts = {"0": int(result.item())}
            elif isinstance(result, tuple) and len(result) > 0:
                r = result[0]
                if isinstance(r, dict):
                    counts = {str(k): int(v) for k, v in r.items()}

            return ExecutionResult(
                counts=counts,
                shots=shots,
                backend_name=backend_name,
                success=True,
                execution_time_ms=elapsed_ms,
                seed_simulator=seed_simulator,
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("PennyLane execution failed: %s", exc)
            return ExecutionResult(
                counts={},
                shots=shots,
                backend_name=backend_name,
                success=False,
                error_message=str(exc),
                execution_time_ms=elapsed_ms,
                seed_simulator=seed_simulator,
            )

    # ------------------------------------------------------------------
    # Noise profiling
    # ------------------------------------------------------------------

    def get_noise_snapshot(self, backend: Any) -> NoiseSnapshot:
        backend_name = backend if isinstance(backend, str) else type(backend).__name__
        return NoiseSnapshot(
            backend_name=backend_name,
            timestamp=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Backend discovery
    # ------------------------------------------------------------------

    def list_backends(self, **filters: Any) -> list[dict[str, Any]]:
        return [
            {
                "name": "default.qubit",
                "num_qubits": 30,
                "simulator": True,
                "framework": "pennylane",
            },
            {
                "name": "default.mixed",
                "num_qubits": 20,
                "simulator": True,
                "framework": "pennylane",
            },
            {
                "name": "lightning.qubit",
                "num_qubits": 30,
                "simulator": True,
                "framework": "pennylane",
                "note": "High-performance C++ simulator (requires pennylane-lightning)",
            },
        ]
