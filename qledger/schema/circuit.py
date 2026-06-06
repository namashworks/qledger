"""Universal circuit intermediate representation.

``UniversalCircuit`` is the core abstraction that makes QLedger
framework-agnostic.  Every adapter converts its native circuit into this
representation before storage, and can restore a native circuit from it.

The IR is intentionally simple — a flat sequence of ``Instruction`` objects
plus a list of ``Measurement`` mappings.  This mirrors how QASM works and
keeps serialisation straightforward.

Invariants
----------
* Qubit and clbit indices are **0-based** contiguous integers.
* Gate names are **canonical** (as defined in ``qledger.schema.gates``).
* Parameters are plain Python floats (no symbolic expressions).  Adapters
  must resolve symbolic parameters before conversion.
* The ``metadata`` dict is free-form and never interpreted by the core — it
  exists so adapters can round-trip framework-specific information.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .gates import StandardGates


@dataclass(frozen=True)
class Instruction:
    """A single gate application in the circuit.

    Parameters
    ----------
    gate : str
        Canonical gate name (e.g. ``"h"``, ``"cx"``, ``"rx"``).
    qubits : tuple[int, ...]
        Qubit indices the gate acts on.
    params : tuple[float, ...]
        Continuous real-valued parameters (empty for fixed gates).
    """

    gate: str
    qubits: tuple[int, ...]
    params: tuple[float, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"gate": self.gate, "qubits": list(self.qubits)}
        if self.params:
            d["params"] = list(self.params)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Instruction:
        return cls(
            gate=d["gate"],
            qubits=tuple(d["qubits"]),
            params=tuple(d.get("params", ())),
        )


@dataclass(frozen=True)
class Measurement:
    """Maps a qubit to a classical bit for readout.

    Parameters
    ----------
    qubit : int
        Source qubit index.
    clbit : int
        Target classical bit index.
    """

    qubit: int
    clbit: int

    def to_dict(self) -> dict[str, int]:
        return {"qubit": self.qubit, "clbit": self.clbit}

    @classmethod
    def from_dict(cls, d: dict[str, int]) -> Measurement:
        return cls(qubit=d["qubit"], clbit=d["clbit"])


@dataclass
class UniversalCircuit:
    """Framework-agnostic quantum circuit representation.

    This is the single source of truth that QLedger stores.  Adapters are
    responsible for converting to and from their native circuit types.

    Parameters
    ----------
    num_qubits : int
        Total number of qubits.
    num_clbits : int
        Total number of classical bits.
    instructions : list[Instruction]
        Ordered sequence of gate applications.
    measurements : list[Measurement]
        Qubit-to-clbit measurement mappings.
    name : str
        Optional human-readable circuit name.
    metadata : dict
        Adapter-specific or user-supplied metadata that round-trips
        through storage unchanged.
    """

    num_qubits: int
    num_clbits: int
    instructions: list[Instruction] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def depth(self) -> int:
        """Compute circuit depth (longest path of dependent gates).

        A gate on qubit *q* depends on all prior gates that also touch *q*.
        This mirrors the standard definition used by Qiskit and Cirq.
        """
        if not self.instructions:
            return 0
        # Track the current depth of each qubit
        qubit_depth: dict[int, int] = {}
        for inst in self.instructions:
            # This gate's depth = max depth across its qubits + 1
            current_max = max((qubit_depth.get(q, 0) for q in inst.qubits), default=0)
            new_depth = current_max + 1
            for q in inst.qubits:
                qubit_depth[q] = new_depth
        return max(qubit_depth.values(), default=0)

    @property
    def gate_counts(self) -> dict[str, int]:
        """Count occurrences of each gate type."""
        counts: dict[str, int] = {}
        for inst in self.instructions:
            counts[inst.gate] = counts.get(inst.gate, 0) + 1
        return counts

    @property
    def total_gates(self) -> int:
        return len(self.instructions)

    @property
    def used_qubits(self) -> set[int]:
        """Set of qubit indices that appear in at least one instruction."""
        qubits: set[int] = set()
        for inst in self.instructions:
            qubits.update(inst.qubits)
        return qubits

    @property
    def two_qubit_gate_count(self) -> int:
        return sum(1 for inst in self.instructions if len(inst.qubits) >= 2)

    # ------------------------------------------------------------------
    # Content hashing
    # ------------------------------------------------------------------

    def content_hash(self) -> str:
        """SHA-256 hash of the circuit's structural content.

        Two circuits with identical instructions and measurements always
        produce the same hash, regardless of name or metadata.  This is the
        basis for circuit versioning.
        """
        canonical = json.dumps(
            {
                "num_qubits": self.num_qubits,
                "num_clbits": self.num_clbits,
                "instructions": [i.to_dict() for i in self.instructions],
                "measurements": [m.to_dict() for m in self.measurements],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Return a list of validation warnings (empty = valid)."""
        warnings: list[str] = []
        for i, inst in enumerate(self.instructions):
            for q in inst.qubits:
                if q < 0 or q >= self.num_qubits:
                    warnings.append(
                        f"Instruction {i} ({inst.gate}): qubit {q} out of range "
                        f"[0, {self.num_qubits})."
                    )
            gate_def = StandardGates.get(inst.gate)
            if (
                gate_def is not None
                and gate_def.num_params > 0
                and len(inst.params) != gate_def.num_params
            ):
                warnings.append(
                    f"Instruction {i} ({inst.gate}): expected {gate_def.num_params} "
                    f"params, got {len(inst.params)}."
                )
        for m in self.measurements:
            if m.qubit < 0 or m.qubit >= self.num_qubits:
                warnings.append(f"Measurement: qubit {m.qubit} out of range.")
            if m.clbit < 0 or m.clbit >= self.num_clbits:
                warnings.append(f"Measurement: clbit {m.clbit} out of range.")
        return warnings

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "num_qubits": self.num_qubits,
            "num_clbits": self.num_clbits,
            "instructions": [i.to_dict() for i in self.instructions],
            "measurements": [m.to_dict() for m in self.measurements],
            "name": self.name,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> UniversalCircuit:
        """Reconstruct from a dict produced by ``to_dict``."""
        return cls(
            num_qubits=d["num_qubits"],
            num_clbits=d["num_clbits"],
            instructions=[Instruction.from_dict(i) for i in d.get("instructions", [])],
            measurements=[Measurement.from_dict(m) for m in d.get("measurements", [])],
            name=d.get("name", ""),
            metadata=d.get("metadata", {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> UniversalCircuit:
        return cls.from_dict(json.loads(s))

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """One-line summary of the circuit."""
        return (
            f"UniversalCircuit(name={self.name!r}, qubits={self.num_qubits}, "
            f"depth={self.depth}, gates={self.total_gates}, "
            f"2q_gates={self.two_qubit_gate_count})"
        )

    def __repr__(self) -> str:
        return self.summary()
