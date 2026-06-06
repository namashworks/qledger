"""Noise profile models for characterising quantum hardware.

These models capture the physical properties of qubits, gates, and readout
channels at a specific point in time.  By storing snapshots regularly,
QLedger can track how hardware quality drifts — critical for reproducibility
and for the intelligent circuit router.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class QubitProperties:
    """Physical properties of a single qubit.

    Parameters
    ----------
    index : int
        Qubit index on the device.
    t1_us : float | None
        T1 relaxation time in microseconds.
    t2_us : float | None
        T2 dephasing time in microseconds.
    frequency_ghz : float | None
        Qubit transition frequency in GHz.
    anharmonicity_ghz : float | None
        Anharmonicity in GHz.
    readout_error : float | None
        Probability of a readout error (0-1).
    readout_length_ns : float | None
        Readout duration in nanoseconds.
    """

    index: int
    t1_us: float | None = None
    t2_us: float | None = None
    frequency_ghz: float | None = None
    anharmonicity_ghz: float | None = None
    readout_error: float | None = None
    readout_length_ns: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QubitProperties:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class GateFidelity:
    """Error rate for a specific gate on specific qubits.

    Parameters
    ----------
    gate : str
        Canonical gate name.
    qubits : tuple[int, ...]
        Qubit indices the gate acts on.
    fidelity : float
        Gate fidelity (1.0 = perfect).
    error_rate : float
        Gate error rate (1 - fidelity).
    gate_length_ns : float | None
        Duration of the gate in nanoseconds.
    """

    gate: str
    qubits: tuple[int, ...]
    fidelity: float
    error_rate: float
    gate_length_ns: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "gate": self.gate,
            "qubits": list(self.qubits),
            "fidelity": self.fidelity,
            "error_rate": self.error_rate,
        }
        if self.gate_length_ns is not None:
            d["gate_length_ns"] = self.gate_length_ns
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GateFidelity:
        return cls(
            gate=d["gate"],
            qubits=tuple(d["qubits"]),
            fidelity=d["fidelity"],
            error_rate=d["error_rate"],
            gate_length_ns=d.get("gate_length_ns"),
        )


@dataclass(frozen=True)
class ReadoutError:
    """Readout confusion matrix for a single qubit.

    Parameters
    ----------
    qubit : int
        Qubit index.
    prob_meas1_prep0 : float
        P(measure 1 | prepared 0).
    prob_meas0_prep1 : float
        P(measure 0 | prepared 1).
    """

    qubit: int
    prob_meas1_prep0: float
    prob_meas0_prep1: float

    @property
    def average_error(self) -> float:
        return (self.prob_meas1_prep0 + self.prob_meas0_prep1) / 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "qubit": self.qubit,
            "prob_meas1_prep0": self.prob_meas1_prep0,
            "prob_meas0_prep1": self.prob_meas0_prep1,
            "average_error": self.average_error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReadoutError:
        return cls(
            qubit=d["qubit"],
            prob_meas1_prep0=d["prob_meas1_prep0"],
            prob_meas0_prep1=d["prob_meas0_prep1"],
        )


@dataclass
class NoiseSnapshot:
    """A point-in-time snapshot of a backend's noise characteristics.

    Adapters populate this by querying hardware calibration data.  QLedger
    stores these over time so users can track drift and correlate noise
    changes with execution results.

    Parameters
    ----------
    backend_name : str
        Name of the backend.
    timestamp : datetime
        When this snapshot was captured.
    num_qubits : int
        Number of qubits on the device.
    qubit_properties : list[QubitProperties]
        Per-qubit physical properties.
    gate_fidelities : list[GateFidelity]
        Per-gate error rates.
    readout_errors : list[ReadoutError]
        Per-qubit readout confusion data.
    coupling_map : list[tuple[int, int]]
        Directed edges representing qubit connectivity.
    basis_gates : list[str]
        Native gate set of the backend.
    extra : dict
        Additional backend-specific calibration data.
    """

    backend_name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    num_qubits: int = 0
    qubit_properties: list[QubitProperties] = field(default_factory=list)
    gate_fidelities: list[GateFidelity] = field(default_factory=list)
    readout_errors: list[ReadoutError] = field(default_factory=list)
    coupling_map: list[tuple[int, int]] = field(default_factory=list)
    basis_gates: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Aggregate metrics
    # ------------------------------------------------------------------

    @property
    def median_t1_us(self) -> float | None:
        vals = sorted(q.t1_us for q in self.qubit_properties if q.t1_us is not None)
        if not vals:
            return None
        mid = len(vals) // 2
        return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2

    @property
    def median_t2_us(self) -> float | None:
        vals = sorted(q.t2_us for q in self.qubit_properties if q.t2_us is not None)
        if not vals:
            return None
        mid = len(vals) // 2
        return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2

    @property
    def average_cx_error(self) -> float | None:
        cx_errors = [g.error_rate for g in self.gate_fidelities if g.gate == "cx"]
        if not cx_errors:
            return None
        return sum(cx_errors) / len(cx_errors)

    @property
    def average_readout_error(self) -> float | None:
        if not self.readout_errors:
            return None
        return sum(r.average_error for r in self.readout_errors) / len(self.readout_errors)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_name": self.backend_name,
            "timestamp": self.timestamp.isoformat(),
            "num_qubits": self.num_qubits,
            "qubit_properties": [q.to_dict() for q in self.qubit_properties],
            "gate_fidelities": [g.to_dict() for g in self.gate_fidelities],
            "readout_errors": [r.to_dict() for r in self.readout_errors],
            "coupling_map": [list(edge) for edge in self.coupling_map],
            "basis_gates": self.basis_gates,
            "aggregate": {
                "median_t1_us": self.median_t1_us,
                "median_t2_us": self.median_t2_us,
                "average_cx_error": self.average_cx_error,
                "average_readout_error": self.average_readout_error,
            },
            "extra": self.extra,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NoiseSnapshot:
        ts = d.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif ts is None:
            ts = datetime.now(timezone.utc)
        return cls(
            backend_name=d["backend_name"],
            timestamp=ts,
            num_qubits=d.get("num_qubits", 0),
            qubit_properties=[QubitProperties.from_dict(q) for q in d.get("qubit_properties", [])],
            gate_fidelities=[GateFidelity.from_dict(g) for g in d.get("gate_fidelities", [])],
            readout_errors=[ReadoutError.from_dict(r) for r in d.get("readout_errors", [])],
            coupling_map=[tuple(e) for e in d.get("coupling_map", [])],
            basis_gates=d.get("basis_gates", []),
            extra=d.get("extra", {}),
        )
