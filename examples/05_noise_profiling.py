"""Noise profiling — capture and analyse backend noise characteristics."""

from qledger.schema.noise import (
    GateFidelity,
    NoiseSnapshot,
    QubitProperties,
    ReadoutError,
)


def main() -> None:
    # Simulate what you'd get from real hardware calibration data.
    # In production, use: db.capture_noise(backend, framework="qiskit")
    # which automatically extracts T1/T2/fidelities from the backend.

    # Create a synthetic noise snapshot (as if from hardware)
    snapshot = NoiseSnapshot(
        backend_name="ibm_kyoto",
        num_qubits=5,
        qubit_properties=[
            QubitProperties(0, t1_us=120.5, t2_us=65.3, readout_error=0.012),
            QubitProperties(1, t1_us=95.2, t2_us=48.1, readout_error=0.018),
            QubitProperties(2, t1_us=110.8, t2_us=55.7, readout_error=0.015),
            QubitProperties(3, t1_us=88.3, t2_us=42.0, readout_error=0.022),
            QubitProperties(4, t1_us=105.1, t2_us=52.4, readout_error=0.016),
        ],
        gate_fidelities=[
            GateFidelity("cx", (0, 1), 0.993, 0.007, gate_length_ns=300.0),
            GateFidelity("cx", (1, 2), 0.989, 0.011, gate_length_ns=320.0),
            GateFidelity("cx", (2, 3), 0.991, 0.009, gate_length_ns=310.0),
            GateFidelity("cx", (3, 4), 0.987, 0.013, gate_length_ns=340.0),
        ],
        readout_errors=[
            ReadoutError(i, 0.01 + i * 0.003, 0.015 + i * 0.002)
            for i in range(5)
        ],
        coupling_map=[(0, 1), (1, 2), (2, 3), (3, 4)],
        basis_gates=["cx", "rz", "sx", "x", "id"],
    )

    # Display aggregate metrics
    print(f"Backend: {snapshot.backend_name}")
    print(f"Qubits: {snapshot.num_qubits}")
    print(f"Median T1: {snapshot.median_t1_us:.1f} \u00b5s")
    print(f"Median T2: {snapshot.median_t2_us:.1f} \u00b5s")
    print(f"Avg CX error: {snapshot.average_cx_error:.4f}")
    print(f"Avg readout error: {snapshot.average_readout_error:.4f}")
    print()

    # Per-qubit breakdown
    print("Per-qubit properties:")
    for qp in snapshot.qubit_properties:
        print(f"  Q{qp.index}: T1={qp.t1_us:.1f}\u00b5s  T2={qp.t2_us:.1f}\u00b5s  "
              f"readout_err={qp.readout_error:.3f}")
    print()

    # Gate fidelities
    print("CX gate fidelities:")
    for gf in snapshot.gate_fidelities:
        print(f"  CX{list(gf.qubits)}: fidelity={gf.fidelity:.4f}  "
              f"duration={gf.gate_length_ns:.0f}ns")


if __name__ == "__main__":
    main()
