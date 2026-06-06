"""Canonical gate definitions and cross-framework name mapping.

Every quantum framework uses different names for the same gates.  This module
defines a *canonical* gate vocabulary and provides bidirectional mappings so
that ``UniversalCircuit`` can translate between Qiskit, Cirq, and PennyLane
without ambiguity.

Design principles
-----------------
* The canonical name is always **lowercase** and follows Qiskit conventions
  where possible (``"h"``, ``"cx"``, ``"rx"``).
* Each ``GateDefinition`` records the canonical name, number of qubits,
  number of classical float parameters, a human-readable label, and the
  aliases used by other frameworks.
* ``StandardGates`` is a registry that supports lookup by any alias, so
  adapters can call ``StandardGates.resolve("CNOT")`` and get back the
  canonical ``"cx"`` definition regardless of which framework produced it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import ClassVar


class ParametricType(enum.Enum):
    """Whether a gate carries continuous parameters."""

    FIXED = "fixed"
    PARAMETRIC = "parametric"


@dataclass(frozen=True)
class GateSignature:
    """Minimal signature used for fast equality checks and hashing."""

    canonical_name: str
    num_qubits: int
    num_params: int


@dataclass(frozen=True)
class GateDefinition:
    """Full definition of a canonical gate.

    Parameters
    ----------
    canonical_name : str
        The QLedger-internal name (e.g. ``"cx"``).
    num_qubits : int
        Number of qubits the gate acts on.
    num_params : int
        Number of continuous real-valued parameters (0 for fixed gates).
    label : str
        Human-readable name for display (e.g. ``"Hadamard"``).
    parametric : ParametricType
        Whether the gate is fixed or parametric.
    aliases : dict[str, str]
        Framework-specific names.  Keys are framework identifiers
        (``"qiskit"``, ``"cirq"``, ``"pennylane"``), values are the names
        each framework uses for this gate.
    """

    canonical_name: str
    num_qubits: int
    num_params: int
    label: str
    parametric: ParametricType = ParametricType.FIXED
    aliases: dict[str, str] = field(default_factory=dict)

    @property
    def signature(self) -> GateSignature:
        return GateSignature(self.canonical_name, self.num_qubits, self.num_params)


class StandardGates:
    """Registry of canonical gate definitions with cross-framework resolution.

    Usage
    -----
    >>> gate = StandardGates.resolve("CNOT")  # any alias works
    >>> gate.canonical_name
    'cx'
    >>> StandardGates.get("h").label
    'Hadamard'
    """

    _definitions: ClassVar[dict[str, GateDefinition]] = {}
    _alias_index: ClassVar[dict[str, str]] = {}  # alias (lower) → canonical_name

    @classmethod
    def register(cls, gate: GateDefinition) -> None:
        """Add a gate definition to the registry."""
        cls._definitions[gate.canonical_name] = gate
        cls._alias_index[gate.canonical_name] = gate.canonical_name
        for alias in gate.aliases.values():
            cls._alias_index[alias.lower()] = gate.canonical_name

    @classmethod
    def get(cls, canonical_name: str) -> GateDefinition | None:
        """Look up by canonical name only."""
        return cls._definitions.get(canonical_name)

    @classmethod
    def resolve(cls, name: str) -> GateDefinition | None:
        """Look up by *any* alias (case-insensitive) or canonical name."""
        canonical = cls._alias_index.get(name.lower())
        if canonical is None:
            return None
        return cls._definitions.get(canonical)

    @classmethod
    def canonical_name_for(cls, alias: str) -> str | None:
        """Return the canonical name for a given alias, or None."""
        return cls._alias_index.get(alias.lower())

    @classmethod
    def all_definitions(cls) -> list[GateDefinition]:
        """Return all registered gate definitions."""
        return list(cls._definitions.values())

    @classmethod
    def alias_for(cls, canonical_name: str, framework: str) -> str | None:
        """Return the framework-specific alias for a canonical gate name."""
        gate = cls._definitions.get(canonical_name)
        if gate is None:
            return None
        return gate.aliases.get(framework, canonical_name)


# ---------------------------------------------------------------------------
# Register the standard gate set
# ---------------------------------------------------------------------------

_STANDARD_GATES: list[GateDefinition] = [
    # -- Single-qubit fixed gates --
    GateDefinition(
        canonical_name="id",
        num_qubits=1,
        num_params=0,
        label="Identity",
        aliases={"qiskit": "id", "cirq": "I", "pennylane": "Identity"},
    ),
    GateDefinition(
        canonical_name="h",
        num_qubits=1,
        num_params=0,
        label="Hadamard",
        aliases={"qiskit": "h", "cirq": "H", "pennylane": "Hadamard"},
    ),
    GateDefinition(
        canonical_name="x",
        num_qubits=1,
        num_params=0,
        label="Pauli-X",
        aliases={"qiskit": "x", "cirq": "X", "pennylane": "PauliX"},
    ),
    GateDefinition(
        canonical_name="y",
        num_qubits=1,
        num_params=0,
        label="Pauli-Y",
        aliases={"qiskit": "y", "cirq": "Y", "pennylane": "PauliY"},
    ),
    GateDefinition(
        canonical_name="z",
        num_qubits=1,
        num_params=0,
        label="Pauli-Z",
        aliases={"qiskit": "z", "cirq": "Z", "pennylane": "PauliZ"},
    ),
    GateDefinition(
        canonical_name="s",
        num_qubits=1,
        num_params=0,
        label="S (Phase)",
        aliases={"qiskit": "s", "cirq": "S", "pennylane": "S"},
    ),
    GateDefinition(
        canonical_name="sdg",
        num_qubits=1,
        num_params=0,
        label="S-dagger",
        aliases={"qiskit": "sdg", "cirq": "S**-1", "pennylane": "Adjoint(S)"},
    ),
    GateDefinition(
        canonical_name="t",
        num_qubits=1,
        num_params=0,
        label="T",
        aliases={"qiskit": "t", "cirq": "T", "pennylane": "T"},
    ),
    GateDefinition(
        canonical_name="tdg",
        num_qubits=1,
        num_params=0,
        label="T-dagger",
        aliases={"qiskit": "tdg", "cirq": "T**-1", "pennylane": "Adjoint(T)"},
    ),
    GateDefinition(
        canonical_name="sx",
        num_qubits=1,
        num_params=0,
        label="Sqrt(X)",
        aliases={"qiskit": "sx", "cirq": "X**0.5", "pennylane": "SX"},
    ),
    # -- Single-qubit parametric gates --
    GateDefinition(
        canonical_name="rx",
        num_qubits=1,
        num_params=1,
        label="Rotation-X",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "rx", "cirq": "rx", "pennylane": "RX"},
    ),
    GateDefinition(
        canonical_name="ry",
        num_qubits=1,
        num_params=1,
        label="Rotation-Y",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "ry", "cirq": "ry", "pennylane": "RY"},
    ),
    GateDefinition(
        canonical_name="rz",
        num_qubits=1,
        num_params=1,
        label="Rotation-Z",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "rz", "cirq": "rz", "pennylane": "RZ"},
    ),
    GateDefinition(
        canonical_name="p",
        num_qubits=1,
        num_params=1,
        label="Phase",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "p", "cirq": "ZPowGate", "pennylane": "PhaseShift"},
    ),
    GateDefinition(
        canonical_name="u",
        num_qubits=1,
        num_params=3,
        label="General Unitary U(θ,φ,λ)",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "u", "cirq": "PhasedXZGate", "pennylane": "Rot"},
    ),
    # -- Two-qubit gates --
    GateDefinition(
        canonical_name="cx",
        num_qubits=2,
        num_params=0,
        label="CNOT",
        aliases={"qiskit": "cx", "cirq": "CNOT", "pennylane": "CNOT"},
    ),
    GateDefinition(
        canonical_name="cy",
        num_qubits=2,
        num_params=0,
        label="Controlled-Y",
        aliases={"qiskit": "cy", "cirq": "ControlledGate(Y)", "pennylane": "CY"},
    ),
    GateDefinition(
        canonical_name="cz",
        num_qubits=2,
        num_params=0,
        label="Controlled-Z",
        aliases={"qiskit": "cz", "cirq": "CZ", "pennylane": "CZ"},
    ),
    GateDefinition(
        canonical_name="swap",
        num_qubits=2,
        num_params=0,
        label="SWAP",
        aliases={"qiskit": "swap", "cirq": "SWAP", "pennylane": "SWAP"},
    ),
    GateDefinition(
        canonical_name="iswap",
        num_qubits=2,
        num_params=0,
        label="iSWAP",
        aliases={"qiskit": "iswap", "cirq": "ISWAP", "pennylane": "ISWAP"},
    ),
    GateDefinition(
        canonical_name="ecr",
        num_qubits=2,
        num_params=0,
        label="Echoed Cross-Resonance",
        aliases={"qiskit": "ecr", "cirq": "ECR", "pennylane": "ECR"},
    ),
    GateDefinition(
        canonical_name="rxx",
        num_qubits=2,
        num_params=1,
        label="Ising XX",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "rxx", "cirq": "XXPowGate", "pennylane": "IsingXX"},
    ),
    GateDefinition(
        canonical_name="ryy",
        num_qubits=2,
        num_params=1,
        label="Ising YY",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "ryy", "cirq": "YYPowGate", "pennylane": "IsingYY"},
    ),
    GateDefinition(
        canonical_name="rzz",
        num_qubits=2,
        num_params=1,
        label="Ising ZZ",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "rzz", "cirq": "ZZPowGate", "pennylane": "IsingZZ"},
    ),
    GateDefinition(
        canonical_name="cp",
        num_qubits=2,
        num_params=1,
        label="Controlled-Phase",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "cp", "cirq": "CZPowGate", "pennylane": "ControlledPhaseShift"},
    ),
    GateDefinition(
        canonical_name="crx",
        num_qubits=2,
        num_params=1,
        label="Controlled-RX",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "crx", "cirq": "ControlledGate(rx)", "pennylane": "CRX"},
    ),
    GateDefinition(
        canonical_name="cry",
        num_qubits=2,
        num_params=1,
        label="Controlled-RY",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "cry", "cirq": "ControlledGate(ry)", "pennylane": "CRY"},
    ),
    GateDefinition(
        canonical_name="crz",
        num_qubits=2,
        num_params=1,
        label="Controlled-RZ",
        parametric=ParametricType.PARAMETRIC,
        aliases={"qiskit": "crz", "cirq": "ControlledGate(rz)", "pennylane": "CRZ"},
    ),
    # -- Three-qubit gates --
    GateDefinition(
        canonical_name="ccx",
        num_qubits=3,
        num_params=0,
        label="Toffoli (CCX)",
        aliases={"qiskit": "ccx", "cirq": "CCX", "pennylane": "Toffoli"},
    ),
    GateDefinition(
        canonical_name="cswap",
        num_qubits=3,
        num_params=0,
        label="Fredkin (CSWAP)",
        aliases={"qiskit": "cswap", "cirq": "CSWAP", "pennylane": "CSWAP"},
    ),
    # -- Barriers / non-unitary --
    GateDefinition(
        canonical_name="barrier",
        num_qubits=0,  # variable
        num_params=0,
        label="Barrier",
        aliases={"qiskit": "barrier", "cirq": "barrier", "pennylane": "Barrier"},
    ),
    GateDefinition(
        canonical_name="measure",
        num_qubits=1,
        num_params=0,
        label="Measurement",
        aliases={"qiskit": "measure", "cirq": "measure", "pennylane": "measure"},
    ),
]

for _gate in _STANDARD_GATES:
    StandardGates.register(_gate)
