"""Qiskit adapter — converts between Qiskit circuits and UniversalCircuit.

Supports Qiskit >= 1.0 and qiskit-aer >= 0.13.  Handles both the legacy
``circuit.qasm()`` API and the modern ``qiskit.qasm2`` module.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from qledger.schema.circuit import Instruction, Measurement, UniversalCircuit
from qledger.schema.gates import StandardGates
from qledger.schema.noise import (
    GateFidelity,
    NoiseSnapshot,
    QubitProperties,
)
from qledger.schema.result import ExecutionResult

from .base import AdapterError, BaseAdapter
from .registry import AdapterRegistry

logger = logging.getLogger(__name__)


@AdapterRegistry.register
class QiskitAdapter(BaseAdapter):
    """Adapter for IBM Qiskit."""

    _FRAMEWORK_NAME = "qiskit"

    def __init__(self) -> None:
        # Deferred import — only pay the cost when actually used
        import qiskit

        self._qiskit = qiskit

    @property
    def framework_name(self) -> str:
        return "qiskit"

    @property
    def framework_version(self) -> str:
        return str(self._qiskit.__version__)

    # ------------------------------------------------------------------
    # Circuit conversion: Qiskit → UniversalCircuit
    # ------------------------------------------------------------------

    def from_native(self, circuit: Any, name: str = "") -> UniversalCircuit:
        from qiskit import QuantumCircuit

        if not isinstance(circuit, QuantumCircuit):
            raise AdapterError(f"Expected qiskit.QuantumCircuit, got {type(circuit).__name__}")

        instructions: list[Instruction] = []
        measurements: list[Measurement] = []

        for inst_data in circuit.data:
            op = inst_data.operation
            gate_name = op.name

            # Extract qubit indices
            qubit_indices = tuple(circuit.find_bit(q).index for q in inst_data.qubits)

            # Handle measurements separately
            if gate_name == "measure":
                clbit_indices = [circuit.find_bit(c).index for c in inst_data.clbits]
                for qi, ci in zip(qubit_indices, clbit_indices, strict=True):
                    measurements.append(Measurement(qubit=qi, clbit=ci))
                continue

            # Skip barriers (they don't affect the circuit semantically)
            if gate_name == "barrier":
                continue

            # Resolve to canonical name
            canonical = StandardGates.canonical_name_for(gate_name)
            if canonical is None:
                canonical = gate_name  # preserve unknown gates as-is

            # Extract parameters (resolve symbolic to float)
            params: tuple[float, ...] = ()
            if op.params:
                resolved = []
                for p in op.params:
                    if isinstance(p, (int, float)):
                        resolved.append(float(p))
                    else:
                        try:
                            resolved.append(float(p))
                        except (TypeError, ValueError) as exc:
                            raise AdapterError(
                                f"Cannot resolve symbolic parameter {p!r} in gate {gate_name}. "
                                f"Bind all parameters before converting."
                            ) from exc
                params = tuple(resolved)

            instructions.append(Instruction(gate=canonical, qubits=qubit_indices, params=params))

        circuit_name = name or getattr(circuit, "name", "")

        return UniversalCircuit(
            num_qubits=circuit.num_qubits,
            num_clbits=circuit.num_clbits,
            instructions=instructions,
            measurements=measurements,
            name=circuit_name,
            metadata={"source_framework": "qiskit", "qiskit_version": self.framework_version},
        )

    # ------------------------------------------------------------------
    # Circuit conversion: UniversalCircuit → Qiskit
    # ------------------------------------------------------------------

    def to_native(self, circuit: UniversalCircuit) -> Any:
        from qiskit import QuantumCircuit
        from qiskit.circuit.library import standard_gates as sg

        qc = QuantumCircuit(circuit.num_qubits, circuit.num_clbits, name=circuit.name)

        # Map canonical names → Qiskit gate constructors
        gate_map: dict[str, Any] = {
            "id": sg.IGate,
            "h": sg.HGate,
            "x": sg.XGate,
            "y": sg.YGate,
            "z": sg.ZGate,
            "s": sg.SGate,
            "sdg": sg.SdgGate,
            "t": sg.TGate,
            "tdg": sg.TdgGate,
            "sx": sg.SXGate,
            "rx": sg.RXGate,
            "ry": sg.RYGate,
            "rz": sg.RZGate,
            "p": sg.PhaseGate,
            "u": sg.UGate,
            "cx": sg.CXGate,
            "cy": sg.CYGate,
            "cz": sg.CZGate,
            "swap": sg.SwapGate,
            "iswap": sg.iSwapGate,
            "ecr": sg.ECRGate,
            "rxx": sg.RXXGate,
            "ryy": sg.RYYGate,
            "rzz": sg.RZZGate,
            "cp": sg.CPhaseGate,
            "crx": sg.CRXGate,
            "cry": sg.CRYGate,
            "crz": sg.CRZGate,
            "ccx": sg.CCXGate,
            "cswap": sg.CSwapGate,
        }

        for inst in circuit.instructions:
            gate_cls = gate_map.get(inst.gate)
            if gate_cls is None:
                raise AdapterError(
                    f"Gate {inst.gate!r} has no Qiskit mapping. "
                    f"Register it or decompose it before conversion."
                )
            gate = gate_cls(*inst.params) if inst.params else gate_cls()
            qc.append(gate, list(inst.qubits))

        for m in circuit.measurements:
            qc.measure(m.qubit, m.clbit)

        return qc

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
        from qiskit import transpile

        # Resolve backend
        if backend is None:
            try:
                from qiskit_aer import AerSimulator
                backend = AerSimulator()
            except ImportError as exc:
                raise AdapterError(
                    "No backend provided and qiskit-aer is not installed."
                ) from exc

        # Convert to native Qiskit circuit
        qc = self.to_native(circuit)

        # Extract backend info
        backend_name = getattr(backend, "name", type(backend).__name__)
        if callable(backend_name):
            backend_name = backend_name()
        backend_version = ""
        if hasattr(backend, "backend_version"):
            backend_version = str(backend.backend_version)

        # Transpile
        opt_level = optimization_level if optimization_level is not None else 1
        transpiled = transpile(
            qc,
            backend=backend,
            optimization_level=opt_level,
            seed_transpiler=transpiler_seed,
        )

        # Run
        run_kwargs: dict[str, Any] = {"shots": shots}
        if seed_simulator is not None:
            run_kwargs["seed_simulator"] = seed_simulator
        if save_memory:
            run_kwargs["memory"] = True
        if extra_run_options:
            run_kwargs.update(extra_run_options)

        t0 = time.perf_counter()
        try:
            job = backend.run(transpiled, **run_kwargs)
            raw_result = job.result()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            counts = raw_result.get_counts()
            if isinstance(counts, list):
                counts = counts[0]
            counts = {str(k): int(v) for k, v in counts.items()}

            statevector = None
            if save_statevector:
                try:
                    sv = raw_result.get_statevector()
                    statevector = list(sv)
                except Exception:
                    logger.warning("Statevector not available for this backend/circuit.")

            memory_data = None
            if save_memory:
                try:
                    memory_data = raw_result.get_memory()
                except Exception:
                    logger.warning("Per-shot memory not available.")

            # Extract simulator config
            sim_config: dict[str, Any] = {}
            if hasattr(backend, "options"):
                try:
                    opts = backend.options
                    if hasattr(opts, "__dict__"):
                        sim_config = {k: v for k, v in opts.__dict__.items() if v is not None}
                except Exception:
                    pass

            return ExecutionResult(
                counts=counts,
                shots=shots,
                backend_name=backend_name,
                backend_version=backend_version,
                success=True,
                statevector=statevector,
                memory=memory_data,
                execution_time_ms=elapsed_ms,
                seed_simulator=seed_simulator,
                optimization_level=opt_level,
                transpiler_seed=transpiler_seed,
                simulator_config=sim_config,
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("Qiskit execution failed: %s", exc)
            return ExecutionResult(
                counts={},
                shots=shots,
                backend_name=backend_name,
                backend_version=backend_version,
                success=False,
                error_message=str(exc),
                execution_time_ms=elapsed_ms,
                seed_simulator=seed_simulator,
                optimization_level=opt_level,
                transpiler_seed=transpiler_seed,
            )

    # ------------------------------------------------------------------
    # Noise profiling
    # ------------------------------------------------------------------

    def get_noise_snapshot(self, backend: Any) -> NoiseSnapshot:
        backend_name = getattr(backend, "name", type(backend).__name__)
        if callable(backend_name):
            backend_name = backend_name()

        snapshot = NoiseSnapshot(
            backend_name=backend_name,
            timestamp=datetime.now(timezone.utc),
        )

        # Try to extract properties from the backend
        try:
            if hasattr(backend, "properties") and callable(backend.properties):
                props = backend.properties()
                if props is not None:
                    snapshot = self._extract_from_properties(snapshot, props)
        except Exception:
            logger.debug("Could not extract properties from backend %s", backend_name)

        # Try configuration
        try:
            if hasattr(backend, "configuration") and callable(backend.configuration):
                config = backend.configuration()
                snapshot.num_qubits = getattr(config, "n_qubits", 0)
                cmap = getattr(config, "coupling_map", None)
                if cmap:
                    snapshot.coupling_map = [tuple(edge) for edge in cmap]
                bgates = getattr(config, "basis_gates", None)
                if bgates:
                    snapshot.basis_gates = list(bgates)
        except Exception:
            logger.debug("Could not extract configuration from backend %s", backend_name)

        # For Aer backends, extract num_qubits from options
        if snapshot.num_qubits == 0 and hasattr(backend, "num_qubits"):
            try:
                nq = backend.num_qubits
                if isinstance(nq, int):
                    snapshot.num_qubits = nq
            except Exception:
                pass

        return snapshot

    @staticmethod
    def _extract_from_properties(
        snapshot: NoiseSnapshot, props: Any
    ) -> NoiseSnapshot:
        """Populate a NoiseSnapshot from Qiskit BackendProperties."""
        qubit_props = []
        for i in range(props.num_qubits):
            try:
                t1 = props.t1(i) * 1e6 if props.t1(i) else None  # s → µs
                t2 = props.t2(i) * 1e6 if props.t2(i) else None
                freq = props.frequency(i) * 1e-9 if props.frequency(i) else None  # Hz → GHz
                re = props.readout_error(i)
            except Exception:
                t1 = t2 = freq = re = None
            qubit_props.append(QubitProperties(
                index=i, t1_us=t1, t2_us=t2, frequency_ghz=freq, readout_error=re,
            ))
        snapshot.qubit_properties = qubit_props

        gate_fids = []
        try:
            for gate_name in props.gate_property:
                for qubits_key in props.gate_property[gate_name]:
                    err = props.gate_error(gate_name, qubits_key)
                    length = props.gate_length(gate_name, qubits_key)
                    canonical = StandardGates.canonical_name_for(gate_name) or gate_name
                    gate_fids.append(GateFidelity(
                        gate=canonical,
                        qubits=(
                            tuple(qubits_key) if isinstance(qubits_key, (list, tuple))
                            else (qubits_key,)
                        ),
                        fidelity=1.0 - err if err else 1.0,
                        error_rate=err or 0.0,
                        gate_length_ns=length * 1e9 if length else None,
                    ))
        except Exception:
            pass
        snapshot.gate_fidelities = gate_fids

        return snapshot

    # ------------------------------------------------------------------
    # Backend discovery
    # ------------------------------------------------------------------

    def list_backends(self, **filters: Any) -> list[dict[str, Any]]:
        backends: list[dict[str, Any]] = []
        # Aer simulators
        try:
            from qiskit_aer import AerSimulator  # noqa: F401
            backends.append({
                "name": "aer_simulator",
                "num_qubits": 30,
                "simulator": True,
                "framework": "qiskit",
                "methods": ["automatic", "statevector", "density_matrix", "stabilizer"],
            })
        except ImportError:
            pass
        return backends
