"""Benchmarking — run standardised benchmarks and compare results."""

from qledger import QLedger


def main() -> None:
    with QLedger(":memory:") as db:
        suite = db.benchmark(framework="qiskit")

        # Run CLOPS benchmark (fast)
        print("Running CLOPS benchmark...")
        clops = suite.run_clops(num_qubits=2, num_circuits=50, shots=512)
        print(f"  {clops.summary()}")
        print(f"  Total time: {clops.details['total_time_s']:.2f}s")
        print(f"  Avg execution: {clops.details['avg_execution_ms']:.1f}ms")
        print()

        # Run algorithmic benchmark (GHZ fidelity)
        print("Running GHZ fidelity benchmark...")
        ghz = suite.run_algorithmic(
            algorithm="ghz",
            qubit_range=(2, 6),
            shots=4096,
            seed=42,
        )
        print(f"  {ghz.summary()}")
        for n, data in ghz.details["per_qubit_results"].items():
            if data.get("success"):
                print(f"    {n} qubits: fidelity={data['fidelity']:.4f}")
        print()

        # Run QFT fidelity benchmark
        print("Running QFT fidelity benchmark...")
        qft = suite.run_algorithmic(
            algorithm="qft",
            qubit_range=(2, 5),
            shots=4096,
            seed=42,
        )
        print(f"  {qft.summary()}")
        print()

        # Query stored results
        all_results = suite.get_results()
        print(f"Stored {len(all_results)} benchmark results in the database.")


if __name__ == "__main__":
    main()
