"""Cross-framework conversion — build in Qiskit, convert to UniversalCircuit."""

from qiskit import QuantumCircuit

from qledger.adapters.registry import AdapterRegistry


def main() -> None:
    # Build a circuit in Qiskit
    qc = QuantumCircuit(3, 3)
    qc.h(0)
    qc.cx(0, 1)
    qc.cx(1, 2)
    qc.measure([0, 1, 2], [0, 1, 2])

    # Convert to universal IR
    adapter = AdapterRegistry.get("qiskit")
    uc = adapter.from_native(qc, name="GHZ-3")

    print(f"Universal Circuit: {uc.summary()}")
    print(f"Content hash: {uc.content_hash()}")
    print(f"Gate counts: {uc.gate_counts}")
    print(f"Depth: {uc.depth}")
    print(f"Validation: {uc.validate() or 'OK'}")
    print()

    # Convert back to Qiskit
    restored = adapter.to_native(uc)
    print(f"Restored Qiskit circuit: {restored.num_qubits} qubits, "
          f"{restored.num_clbits} clbits")

    # The hash is stable — same structural content = same hash
    uc2 = adapter.from_native(restored)
    print(f"Hash match after roundtrip: {uc.content_hash() == uc2.content_hash()}")


if __name__ == "__main__":
    main()
