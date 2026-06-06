"""Circuit versioning — track how a circuit evolves over time."""

from qiskit import QuantumCircuit

from qledger import QLedger


def main() -> None:
    with QLedger(":memory:") as db:
        exp_id = db.create_experiment("Version Demo")

        # V1: Simple superposition
        qc_v1 = QuantumCircuit(2, 2)
        qc_v1.h(0)
        qc_v1.measure([0, 1], [0, 1])
        db.run(qc_v1, experiment_id=exp_id, name="v1-superposition", shots=1000)

        # V2: Add entanglement
        qc_v2 = QuantumCircuit(2, 2)
        qc_v2.h(0)
        qc_v2.cx(0, 1)
        qc_v2.measure([0, 1], [0, 1])
        db.run(qc_v2, experiment_id=exp_id, name="v2-entangled", shots=1000)

        # V3: Add error correction layer
        qc_v3 = QuantumCircuit(2, 2)
        qc_v3.h(0)
        qc_v3.cx(0, 1)
        qc_v3.barrier()
        qc_v3.x(0)
        qc_v3.x(1)
        qc_v3.measure([0, 1], [0, 1])
        db.run(qc_v3, experiment_id=exp_id, name="v3-with-correction", shots=1000)

        # View execution history
        history = db.get_history(exp_id)
        print("Execution History")
        print("-" * 60)
        for row in history:
            import json
            counts = json.loads(row["counts"]) if isinstance(row["counts"], str) else row["counts"]
            top = max(counts.items(), key=lambda x: x[1]) if counts else ("?", 0)
            print(f"  {row['circuit_name']:<25}  qubits={row['num_qubits']}  "
                  f"depth={row['depth']}  top=|{top[0]}>: {top[1]}")

        # View version log for each circuit
        circuits = db.list_circuits(exp_id)
        print(f"\n{len(circuits)} circuits stored, each with auto-versioning.")


if __name__ == "__main__":
    main()
