"""Basic usage — run a Bell state circuit and inspect stored results."""

from qiskit import QuantumCircuit

from qledger import QLedger


def main() -> None:
    with QLedger("demo.db") as db:
        # Create an experiment
        exp_id = db.create_experiment(
            "Bell State Study",
            description="Measure entanglement via a simple Bell pair.",
            tags=["entanglement", "demo"],
        )

        # Build a Bell circuit
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure([0, 1], [0, 1])

        # Run — everything is persisted automatically
        result = db.run(
            qc,
            experiment_id=exp_id,
            name="bell-pair",
            shots=4096,
            seed_simulator=42,
        )

        # Inspect
        print("Counts:", result.counts)
        print("Probabilities:", {k: f"{v:.3f}" for k, v in result.probabilities.items()})
        print(f"Most frequent: |{result.most_frequent()}>")
        print(f"Shannon entropy: {result.entropy():.3f} bits")
        print(f"Execution time: {result.execution_time_ms:.1f} ms")

        # Query stored data
        summary = db.get_experiment_summary(exp_id)
        print(f"\nExperiment '{summary['name']}': "
              f"{summary['circuit_count']} circuit(s), "
              f"{summary['execution_count']} execution(s)")

    # Clean up demo file
    import os
    os.remove("demo.db")


if __name__ == "__main__":
    main()
