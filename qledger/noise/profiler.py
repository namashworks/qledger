"""Noise profiler — captures and tracks hardware noise characteristics over time.

The profiler uses adapters to extract calibration data from quantum backends
and stores snapshots in the database.  Over time, this builds a complete
noise history that can be used for:

* Tracking T1/T2 drift on specific qubits
* Monitoring gate fidelity changes across calibration cycles
* Selecting the best qubits / backend at a given time
* Correlating execution results with noise conditions
"""

from __future__ import annotations

import json
import logging
from typing import Any

from qledger.adapters.base import BaseAdapter
from qledger.schema.noise import NoiseSnapshot
from qledger.storage.database import QLedgerStore

logger = logging.getLogger(__name__)


class NoiseProfiler:
    """Captures and queries noise profiles for quantum backends.

    Parameters
    ----------
    store : QLedgerStore
        The database to persist snapshots in.
    """

    def __init__(self, store: QLedgerStore) -> None:
        self._store = store

    def capture(
        self,
        adapter: BaseAdapter,
        backend: Any,
    ) -> NoiseSnapshot:
        """Capture a noise snapshot from a backend and store it.

        Parameters
        ----------
        adapter : BaseAdapter
            The framework adapter (e.g. QiskitAdapter).
        backend : Any
            The backend instance to profile.

        Returns
        -------
        NoiseSnapshot
            The captured snapshot.
        """
        snapshot = adapter.get_noise_snapshot(backend)
        self._persist(snapshot, framework=adapter.framework_name)
        logger.info(
            "Captured noise snapshot for %s (%d qubits)",
            snapshot.backend_name,
            snapshot.num_qubits,
        )
        return snapshot

    def _persist(self, snapshot: NoiseSnapshot, framework: str = "") -> int:
        summary = {
            "backend_name": snapshot.backend_name,
            "framework": framework,
            "num_qubits": snapshot.num_qubits,
            "median_t1_us": snapshot.median_t1_us,
            "median_t2_us": snapshot.median_t2_us,
            "avg_cx_error": snapshot.average_cx_error,
            "avg_readout_err": snapshot.average_readout_error,
        }
        return self._store.save_noise_snapshot(
            snapshot_json=snapshot.to_json(),
            summary=summary,
        )

    def get_latest(self, backend_name: str) -> NoiseSnapshot | None:
        """Return the most recent noise snapshot for a backend."""
        rows = self._store.list_noise_snapshots(backend_name=backend_name, limit=1)
        if not rows:
            return None
        return NoiseSnapshot.from_dict(json.loads(rows[0]["snapshot_json"]))

    def get_history(
        self,
        backend_name: str,
        limit: int = 50,
    ) -> list[NoiseSnapshot]:
        """Return historical noise snapshots for a backend."""
        rows = self._store.list_noise_snapshots(backend_name=backend_name, limit=limit)
        return [NoiseSnapshot.from_dict(json.loads(r["snapshot_json"])) for r in rows]

    def compare(
        self,
        snapshot_a: NoiseSnapshot,
        snapshot_b: NoiseSnapshot,
    ) -> dict[str, Any]:
        """Compare two noise snapshots and return a summary of differences.

        Returns
        -------
        dict
            Keys: ``t1_drift``, ``t2_drift``, ``cx_error_drift``,
            ``readout_error_drift``, ``improved_qubits``, ``degraded_qubits``.
        """
        result: dict[str, Any] = {
            "backend": snapshot_a.backend_name,
            "time_a": snapshot_a.timestamp.isoformat(),
            "time_b": snapshot_b.timestamp.isoformat(),
        }

        # T1 drift
        if snapshot_a.median_t1_us is not None and snapshot_b.median_t1_us is not None:
            result["t1_drift_us"] = snapshot_b.median_t1_us - snapshot_a.median_t1_us
            result["t1_drift_pct"] = (
                (snapshot_b.median_t1_us - snapshot_a.median_t1_us) / snapshot_a.median_t1_us * 100
                if snapshot_a.median_t1_us > 0 else 0
            )

        # T2 drift
        if snapshot_a.median_t2_us is not None and snapshot_b.median_t2_us is not None:
            result["t2_drift_us"] = snapshot_b.median_t2_us - snapshot_a.median_t2_us

        # CX error drift
        if snapshot_a.average_cx_error is not None and snapshot_b.average_cx_error is not None:
            result["cx_error_drift"] = snapshot_b.average_cx_error - snapshot_a.average_cx_error

        # Per-qubit comparison
        improved: list[int] = []
        degraded: list[int] = []
        props_a = {q.index: q for q in snapshot_a.qubit_properties}
        props_b = {q.index: q for q in snapshot_b.qubit_properties}
        for idx in set(props_a) & set(props_b):
            qa, qb = props_a[idx], props_b[idx]
            if qa.t1_us is not None and qb.t1_us is not None:
                if qb.t1_us > qa.t1_us * 1.1:
                    improved.append(idx)
                elif qb.t1_us < qa.t1_us * 0.9:
                    degraded.append(idx)
        result["improved_qubits"] = improved
        result["degraded_qubits"] = degraded

        return result

    def best_qubits(
        self,
        backend_name: str,
        count: int = 5,
        metric: str = "t1",
    ) -> list[dict[str, Any]]:
        """Return the best qubits on a backend according to a given metric.

        Parameters
        ----------
        backend_name : str
        count : int
            Number of qubits to return.
        metric : str
            One of ``"t1"``, ``"t2"``, ``"readout_error"``.

        Returns
        -------
        list[dict]
            Sorted list of qubit properties.
        """
        snapshot = self.get_latest(backend_name)
        if snapshot is None:
            return []

        if metric == "t1":
            props = [q for q in snapshot.qubit_properties if q.t1_us is not None]
            props.sort(key=lambda q: q.t1_us or 0, reverse=True)
        elif metric == "t2":
            props = [q for q in snapshot.qubit_properties if q.t2_us is not None]
            props.sort(key=lambda q: q.t2_us or 0, reverse=True)
        elif metric == "readout_error":
            props = [q for q in snapshot.qubit_properties if q.readout_error is not None]
            props.sort(key=lambda q: q.readout_error or 1)  # lower is better
        else:
            raise ValueError(f"Unknown metric: {metric!r}")

        return [q.to_dict() for q in props[:count]]
