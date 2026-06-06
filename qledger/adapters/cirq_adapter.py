"""Cirq adapter — converts between Google Cirq circuits and UniversalCircuit.

Supports cirq-core >= 1.3.
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

# Cirq gate class name → canonical name (None = handled via decomposition)
_CIRQ_TO_CANONICAL: dict[str, str | None] = {
    "HPowGate": "h",
    "XPowGate": "x",
    "YPowGate": "y",
    "ZPowGate": "z",
    "CXPowGate": "cx",
    "CNotPowGate": "cx",
    "CZPowGate": "cz",
    "SwapPowGate": "swap",
    "ISwapPowGate": "iswap",
    "CCXPowGate": "ccx",
    "CCZPowGate": "ccx",
    "MeasurementGate": "measure",
    "_InverseCompositeGate": None,  # handled via decomposition
}


@AdapterRegistry.register
class CirqAdapter(BaseAdapter):
    """Adapter for Google Cirq."""

    _FRAMEWORK_NAME = "cirq"

    def __init__(self) -> None:
        import cirq

        self._cirq = cirq

    @property
    def framework_name(self) -> str:
        return "cirq"

    @property
    def framework_version(self) -> str:
        return str(self._cirq.__version__)

    # ------------------------------------------------------------------
    # Cirq → UniversalCircuit
    # ------------------------------------------------------------------

    def from_native(self, circuit: Any, name: str = "") -> UniversalCircuit:
        cirq = self._cirq

        if not isinstance(circuit, cirq.Circuit):
            raise AdapterError(f"Expected cirq.Circuit, got {type(circuit).__name__}")

        # Collect all qubits and assign contiguous indices
        all_qubits = sorted(circuit.all_qubits())
        qubit_map = {q: i for i, q in enumerate(all_qubits)}

        instructions: list[Instruction] = []
        measurements: list[Measurement] = []
        clbit_counter = 0

        for moment in circuit:
            for op in moment:
                gate = op.gate
                qubit_indices = tuple(qubit_map[q] for q in op.qubits)

                # Handle measurements
                if isinstance(gate, cirq.MeasurementGate):
                    for qi in qubit_indices:
                        measurements.append(Measurement(qubit=qi, clbit=clbit_counter))
                        clbit_counter += 1
                    continue

                # Resolve gate name
                canonical = self._resolve_cirq_gate(gate)
                params = self._extract_cirq_params(gate)

                instructions.append(Instruction(
                    gate=canonical,
                    qubits=qubit_indices,
                    params=params,
                ))

        num_qubits = len(all_qubits)
        num_clbits = clbit_counter if clbit_counter > 0 else num_qubits

        return UniversalCircuit(
            num_qubits=num_qubits,
            num_clbits=num_clbits,
            instructions=instructions,
            measurements=measurements,
            name=name,
            metadata={"source_framework": "cirq", "cirq_version": self.framework_version},
        )

    def _resolve_cirq_gate(self, gate: Any) -> str:
        """Map a Cirq gate to its canonical name."""
        gate_type = type(gate).__name__

        # Check our mapping table first
        canonical = _CIRQ_TO_CANONICAL.get(gate_type)
        if canonical is not None:
            # For power gates, check if the exponent is 1.0 (standard gate)
            if hasattr(gate, "exponent"):
                exp = gate.exponent
                if gate_type == "HPowGate" and exp == 1.0:
                    return "h"
                elif gate_type == "XPowGate":
                    if exp == 1.0:
                        return "x"
                    elif exp == 0.5:
                        return "sx"
                    else:
                        return "rx"  # treat as rotation
                elif gate_type == "YPowGate":
                    return "y" if exp == 1.0 else "ry"
                elif gate_type == "ZPowGate":
                    if exp == 1.0:  # noqa: SIM116
                        return "z"
                    elif exp == 0.5:
                        return "s"
                    elif exp == 0.25:
                        return "t"
                    else:
                        return "rz"
                elif gate_type == "CXPowGate" and exp == 1.0:
                    return "cx"
                elif gate_type == "CZPowGate" and exp == 1.0:
                    return "cz"
                elif gate_type == "SwapPowGate" and exp == 1.0:
                    return "swap"
            return canonical

        # Try string matching
        gate_str = str(gate).upper()
        resolved = StandardGates.resolve(gate_str)
        if resolved is not None:
            return resolved.canonical_name

        # Fallback: use the type name in lowercase
        logger.warning("Unknown Cirq gate %s — storing as-is.", gate_type)
        return gate_type.lower()

    def _extract_cirq_params(self, gate: Any) -> tuple[float, ...]:
        """Extract continuous parameters from a Cirq gate."""
        import math

        if hasattr(gate, "exponent"):
            exp = gate.exponent
            if isinstance(exp, (int, float)):
                # Cirq stores rotations as exponents of π
                # RX(θ) in Qiskit = X^(θ/π) in Cirq
                # Only return params for parametric gates
                gate_type = type(gate).__name__
                if (
                    gate_type in ("HPowGate", "CXPowGate", "CZPowGate", "SwapPowGate")
                    and exp == 1.0
                ):
                    return ()  # standard gate, no params
                if gate_type in ("XPowGate", "YPowGate", "ZPowGate"):
                    if exp in (0.0, 0.25, 0.5, 1.0):
                        return ()  # known fixed gates
                    return (float(exp) * math.pi,)
                if "Pow" in gate_type:
                    return (float(exp) * math.pi,)
        if hasattr(gate, "rads"):
            return (float(gate.rads),)
        return ()

    # ------------------------------------------------------------------
    # UniversalCircuit → Cirq
    # ------------------------------------------------------------------

    def to_native(self, circuit: UniversalCircuit) -> Any:
        cirq = self._cirq
        import math

        qubits = cirq.LineQubit.range(circuit.num_qubits)

        ops: list[Any] = []

        gate_map: dict[str, Any] = {
            "id": cirq.I,
            "h": cirq.H,
            "x": cirq.X,
            "y": cirq.Y,
            "z": cirq.Z,
            "s": cirq.S,
            "t": cirq.T,
            "cx": cirq.CNOT,
            "cz": cirq.CZ,
            "swap": cirq.SWAP,
            "iswap": cirq.ISWAP,
            "ccx": cirq.CCX,
        }

        for inst in circuit.instructions:
            target_qubits = [qubits[q] for q in inst.qubits]

            if inst.gate in gate_map:
                ops.append(gate_map[inst.gate].on(*target_qubits))
            elif inst.gate == "rx" and inst.params:
                ops.append(cirq.rx(inst.params[0]).on(*target_qubits))
            elif inst.gate == "ry" and inst.params:
                ops.append(cirq.ry(inst.params[0]).on(*target_qubits))
            elif inst.gate == "rz" and inst.params:
                ops.append(cirq.rz(inst.params[0]).on(*target_qubits))
            elif inst.gate == "sx":
                ops.append((cirq.X ** 0.5).on(*target_qubits))
            elif inst.gate == "sdg":
                ops.append((cirq.S ** -1).on(*target_qubits))
            elif inst.gate == "tdg":
                ops.append((cirq.T ** -1).on(*target_qubits))
            elif inst.gate == "p" and inst.params:
                ops.append(cirq.ZPowGate(exponent=inst.params[0] / math.pi).on(*target_qubits))
            elif inst.gate == "cp" and inst.params:
                ops.append(cirq.CZPowGate(exponent=inst.params[0] / math.pi).on(*target_qubits))
            else:
                raise AdapterError(
                    f"Gate {inst.gate!r} has no Cirq mapping."
                )

        # Add measurements
        if circuit.measurements:
            measured_qubits = [qubits[m.qubit] for m in circuit.measurements]
            ops.append(cirq.measure(*measured_qubits, key="result"))

        return cirq.Circuit(ops)

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
        cirq = self._cirq

        native_circuit = self.to_native(circuit)

        # Resolve simulator
        if backend is None:
            backend = cirq.Simulator(seed=seed_simulator)
        backend_name = type(backend).__name__

        t0 = time.perf_counter()
        try:
            if save_statevector and not circuit.measurements:
                sim_result = backend.simulate(native_circuit)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                sv = list(sim_result.final_state_vector)
                return ExecutionResult(
                    counts={},
                    shots=0,
                    backend_name=backend_name,
                    success=True,
                    statevector=sv,
                    execution_time_ms=elapsed_ms,
                    seed_simulator=seed_simulator,
                )

            result = backend.run(native_circuit, repetitions=shots)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            # Extract counts from Cirq result
            counts: dict[str, int] = {}
            hist = result.histogram(key="result")
            num_bits = circuit.num_clbits or circuit.num_qubits
            for val, count in hist.items():
                bitstring = format(val, f"0{num_bits}b")
                counts[bitstring] = count

            memory_data = None
            if save_memory:
                measurements_array = result.measurements.get("result")
                if measurements_array is not None:
                    memory_data = [
                        "".join(str(b) for b in row) for row in measurements_array
                    ]

            return ExecutionResult(
                counts=counts,
                shots=shots,
                backend_name=backend_name,
                success=True,
                memory=memory_data,
                execution_time_ms=elapsed_ms,
                seed_simulator=seed_simulator,
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("Cirq execution failed: %s", exc)
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
        backend_name = type(backend).__name__

        snapshot = NoiseSnapshot(
            backend_name=backend_name,
            timestamp=datetime.now(timezone.utc),
        )

        # Cirq noise models expose properties differently depending on device
        if hasattr(backend, "metadata"):
            meta = backend.metadata
            if hasattr(meta, "qubit_set"):
                snapshot.num_qubits = len(meta.qubit_set)

        return snapshot

    # ------------------------------------------------------------------
    # Backend discovery
    # ------------------------------------------------------------------

    def list_backends(self, **filters: Any) -> list[dict[str, Any]]:
        return [
            {
                "name": "Simulator",
                "num_qubits": 30,
                "simulator": True,
                "framework": "cirq",
            },
            {
                "name": "DensityMatrixSimulator",
                "num_qubits": 20,
                "simulator": True,
                "framework": "cirq",
            },
        ]
