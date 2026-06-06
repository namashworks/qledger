"""Circuit version tracker — records how circuits evolve over time.

This module provides git-like versioning for quantum circuits.  Every time a
circuit is modified, a new version is created with:

* A content hash (SHA-256 of the circuit's structural content)
* A reference to the parent version
* A diff summary showing what changed
* An optional commit message

This enables researchers to trace the evolution of a circuit through an
optimisation or debugging process and to reproduce any prior version exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qledger.schema.circuit import Instruction, UniversalCircuit
from qledger.storage.database import QLedgerStore


@dataclass
class CircuitDiff:
    """Summary of changes between two circuit versions.

    Parameters
    ----------
    gates_added : list[dict]
        Instructions present in the new version but not the old.
    gates_removed : list[dict]
        Instructions present in the old version but not the new.
    qubit_count_changed : bool
        Whether the number of qubits changed.
    depth_changed : bool
        Whether the circuit depth changed.
    measurement_changed : bool
        Whether the measurement mapping changed.
    old_stats : dict
        Gate counts, depth, etc. of the old version.
    new_stats : dict
        Gate counts, depth, etc. of the new version.
    """

    gates_added: list[dict[str, Any]] = field(default_factory=list)
    gates_removed: list[dict[str, Any]] = field(default_factory=list)
    qubit_count_changed: bool = False
    depth_changed: bool = False
    measurement_changed: bool = False
    old_stats: dict[str, Any] = field(default_factory=dict)
    new_stats: dict[str, Any] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.gates_added
            or self.gates_removed
            or self.qubit_count_changed
            or self.depth_changed
            or self.measurement_changed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "gates_added": self.gates_added,
            "gates_removed": self.gates_removed,
            "gates_added_count": len(self.gates_added),
            "gates_removed_count": len(self.gates_removed),
            "qubit_count_changed": self.qubit_count_changed,
            "depth_changed": self.depth_changed,
            "measurement_changed": self.measurement_changed,
            "old_stats": self.old_stats,
            "new_stats": self.new_stats,
        }

    def summary_text(self) -> str:
        parts = []
        if self.gates_added:
            parts.append(f"+{len(self.gates_added)} gates")
        if self.gates_removed:
            parts.append(f"-{len(self.gates_removed)} gates")
        if self.qubit_count_changed:
            parts.append(
                f"qubits: {self.old_stats.get('num_qubits')} → {self.new_stats.get('num_qubits')}"
            )
        if self.depth_changed:
            parts.append(
                f"depth: {self.old_stats.get('depth')} → {self.new_stats.get('depth')}"
            )
        if self.measurement_changed:
            parts.append("measurements changed")
        return ", ".join(parts) if parts else "no changes"


def compute_diff(old: UniversalCircuit, new: UniversalCircuit) -> CircuitDiff:
    """Compute the diff between two circuit versions.

    Uses multiset comparison of instructions so that reordering within a
    moment doesn't count as a change, but adding/removing gates does.
    """
    old_insts = _instruction_multiset(old.instructions)
    new_insts = _instruction_multiset(new.instructions)

    added = _multiset_difference(new_insts, old_insts)
    removed = _multiset_difference(old_insts, new_insts)

    old_meas = {(m.qubit, m.clbit) for m in old.measurements}
    new_meas = {(m.qubit, m.clbit) for m in new.measurements}

    old_stats = {
        "num_qubits": old.num_qubits,
        "depth": old.depth,
        "total_gates": old.total_gates,
        "gate_counts": old.gate_counts,
    }
    new_stats = {
        "num_qubits": new.num_qubits,
        "depth": new.depth,
        "total_gates": new.total_gates,
        "gate_counts": new.gate_counts,
    }

    return CircuitDiff(
        gates_added=[i.to_dict() for i in added],
        gates_removed=[i.to_dict() for i in removed],
        qubit_count_changed=old.num_qubits != new.num_qubits,
        depth_changed=old.depth != new.depth,
        measurement_changed=old_meas != new_meas,
        old_stats=old_stats,
        new_stats=new_stats,
    )


def _instruction_multiset(
    instructions: list[Instruction],
) -> dict[Instruction, int]:
    """Convert a list of instructions to a multiset (counter)."""
    ms: dict[Instruction, int] = {}
    for inst in instructions:
        ms[inst] = ms.get(inst, 0) + 1
    return ms


def _multiset_difference(
    a: dict[Instruction, int], b: dict[Instruction, int]
) -> list[Instruction]:
    """Elements in *a* that are not in *b* (with multiplicity)."""
    result: list[Instruction] = []
    for inst, count_a in a.items():
        count_b = b.get(inst, 0)
        for _ in range(max(0, count_a - count_b)):
            result.append(inst)
    return result


class CircuitVersionTracker:
    """Manages version history for circuits in a QLedger store.

    Usage
    -----
    >>> tracker = CircuitVersionTracker(store)
    >>> v1 = tracker.commit(circuit_id, circuit_v1, message="initial")
    >>> # ... modify the circuit ...
    >>> v2 = tracker.commit(circuit_id, circuit_v2, message="added CNOT")
    >>> history = tracker.log(circuit_id)
    """

    def __init__(self, store: QLedgerStore) -> None:
        self._store = store

    def commit(
        self,
        circuit_id: int,
        circuit: UniversalCircuit,
        message: str = "",
    ) -> int:
        """Record a new version of a circuit.

        Parameters
        ----------
        circuit_id : int
            Database id of the circuit.
        circuit : UniversalCircuit
            The current state of the circuit.
        message : str
            Human-readable commit message.

        Returns
        -------
        int
            The version number assigned.
        """
        content_hash = circuit.content_hash()

        # Check if this exact version already exists
        existing = self._store.get_version_by_hash(content_hash)
        if existing and existing["circuit_id"] == circuit_id:
            return int(existing["version"])

        # Get previous version
        versions = self._store.get_circuit_versions(circuit_id)
        version_num = len(versions) + 1
        parent_hash = versions[-1]["content_hash"] if versions else None

        # Compute diff against parent
        diff_summary: dict[str, Any] = {}
        if parent_hash and versions:
            parent_json = versions[-1]["circuit_json"]
            parent_circuit = UniversalCircuit.from_json(parent_json)
            diff = compute_diff(parent_circuit, circuit)
            diff_summary = diff.to_dict()

        self._store.save_circuit_version(
            circuit_id=circuit_id,
            version=version_num,
            content_hash=content_hash,
            circuit_json=circuit.to_json(),
            parent_hash=parent_hash,
            message=message,
            diff_summary=diff_summary,
        )

        return version_num

    def log(self, circuit_id: int) -> list[dict[str, Any]]:
        """Return the full version history for a circuit."""
        return self._store.get_circuit_versions(circuit_id)

    def checkout(self, circuit_id: int, version: int) -> UniversalCircuit | None:
        """Restore a specific version of a circuit.

        Parameters
        ----------
        circuit_id : int
        version : int

        Returns
        -------
        UniversalCircuit | None
            The circuit at that version, or None if not found.
        """
        versions = self._store.get_circuit_versions(circuit_id)
        for v in versions:
            if v["version"] == version:
                return UniversalCircuit.from_json(v["circuit_json"])
        return None

    def diff(
        self,
        circuit_id: int,
        version_a: int,
        version_b: int,
    ) -> CircuitDiff | None:
        """Compute the diff between two versions of a circuit."""
        a = self.checkout(circuit_id, version_a)
        b = self.checkout(circuit_id, version_b)
        if a is None or b is None:
            return None
        return compute_diff(a, b)
