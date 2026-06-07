# QLedger

**The Universal Quantum Experiment Lifecycle Platform.**

Execute circuits across Qiskit, Cirq, and PennyLane. Track noise. Benchmark hardware. Version circuits. Persist everything in a portable SQLite file.

[![CI](https://github.com/namashworks/qledger/actions/workflows/ci.yml/badge.svg)](https://github.com/namashworks/qledger/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/qledger.svg)](https://pypi.org/project/qledger/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/namashworks/qledger/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## Why QLedger?

The quantum computing ecosystem is **fragmented**. Every framework has its own circuit format, every backend returns results differently, and there's no standard way to track experiments, compare hardware, or reproduce results.

QLedger fixes this with a single platform that:

- **Runs circuits on any framework** — Qiskit, Cirq, PennyLane — through a universal adapter layer
- **Persists everything** — circuits, results, metadata, seeds, timing, noise profiles — in one portable `.db` file
- **Versions circuits** — git-like tracking of how your circuits evolve over time
- **Benchmarks hardware** — Quantum Volume, CLOPS, and algorithmic fidelity benchmarks with standardised scoring
- **Tracks noise** — capture T1/T2, gate fidelities, and readout errors over time to monitor hardware drift
- **Enables reproducibility** — every seed, every setting, every result is stored for exact replay

## Installation

```bash
# Core only (no framework dependencies)
pip install qledger

# With specific frameworks
pip install qledger[qiskit]
pip install qledger[cirq]
pip install qledger[pennylane]
pip install qledger[all]
```

From source:

```bash
git clone https://github.com/namashworks/qledger.git
cd qledger
pip install -e ".[dev]"
```

## Quick Start

```python
from qiskit import QuantumCircuit
from qledger import QLedger

with QLedger("my_research.db") as db:
    # Create an experiment
    exp_id = db.create_experiment("Bell States", tags=["entanglement"])

    # Build and run a circuit — everything is saved automatically
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    result = db.run(qc, experiment_id=exp_id, shots=4096, seed_simulator=42)

    print(result.counts)          # {'00': 2009, '11': 2087}
    print(result.probabilities)   # {'00': 0.490, '11': 0.510}
    print(result.most_frequent()) # '11'
    print(result.entropy())       # ~1.000 (near-maximum for 2 equally likely outcomes)
```

## Core Features

### 1. Universal Circuit IR

Convert between frameworks seamlessly:

```python
# Qiskit -> Universal -> Cirq
cirq_circuit = db.convert(qiskit_circuit, from_framework="qiskit", to_framework="cirq")
```

The `UniversalCircuit` is a framework-agnostic intermediate representation with content hashing, validation, and full serialisation support.

### 2. Cross-Framework Execution

```python
# Run the same circuit on different backends
result_qiskit = db.run(qc, framework="qiskit", shots=4096)
result_cirq = db.run(cirq_circuit, framework="cirq", shots=4096)
```

### 3. Circuit Versioning

Track circuit evolution like git tracks code:

```python
# Auto-versioned on every run, or manually:
db.version_circuit(circuit_id, modified_circuit, message="optimised CX count")

# View history
log = db.circuit_log(circuit_id)

# Diff between versions
diff = db.diff_circuit(circuit_id, version_a=1, version_b=3)
print(diff.summary_text())  # "+2 gates, -1 gates, depth: 5 -> 4"

# Restore any version
old_circuit = db.checkout_circuit(circuit_id, version=1)
```

### 4. Standardised Benchmarks

```python
suite = db.benchmark(framework="qiskit")

# Quantum Volume
qv = suite.run_quantum_volume(backend=my_backend, max_depth=8)
print(f"Quantum Volume: {qv.details['quantum_volume']}")

# CLOPS (throughput)
clops = suite.run_clops(num_circuits=100, shots=1024)
print(f"CLOPS: {clops.score:.0f}")

# Algorithmic fidelity (GHZ, QFT)
ghz = suite.run_algorithmic(algorithm="ghz", qubit_range=(2, 10))
print(f"Average fidelity: {ghz.score:.4f}")

# Compare backends
comparison = suite.compare_backends("quantum_volume", ["backend_a", "backend_b"])
```

### 5. Noise Profiling

```python
# Capture noise from a real backend
snapshot = db.capture_noise(backend, framework="qiskit")

print(f"Median T1: {snapshot.median_t1_us:.1f} us")
print(f"Avg CX error: {snapshot.average_cx_error:.4f}")
print(f"Avg readout error: {snapshot.average_readout_error:.4f}")

# Track drift over time
history = db.get_noise_history("ibm_kyoto")

# Find the best qubits
best = db.best_qubits("ibm_kyoto", count=5, metric="t1")
```

### 6. Batch Execution

```python
results = db.run_batch(
    [circuit_1, circuit_2, circuit_3],
    experiment_name="Parameter Sweep",
    names=["theta=0.1", "theta=0.5", "theta=1.0"],
    shots=8192,
)
```

### 7. Export

```python
# Export full experiment as JSON
data = db.export_experiment(exp_id)

# Includes: experiment metadata, all circuits (as UniversalCircuit JSON),
# all executions (with counts, timing, seeds), version history
```

## CLI

```bash
# List experiments
qledger experiments

# Show experiment details
qledger show 1

# List circuits with structural info
qledger circuits 1

# List executions with results
qledger executions --backend aer_simulator

# View circuit version history
qledger versions 1

# View benchmark results
qledger benchmarks --type quantum_volume

# View noise snapshots
qledger noise --backend ibm_kyoto

# Export experiment to JSON
qledger export 1 -o experiment.json

# List available framework adapters
qledger adapters
```

## Database Schema

Everything lives in a single SQLite file:

| Table | Purpose |
|---|---|
| `experiments` | Named containers with tags and descriptions |
| `circuits` | UniversalCircuit JSON, content hash, gate counts, depth |
| `executions` | Counts, probabilities, entropy, backend config, seeds, timing |
| `circuit_versions` | Version history with diffs and parent hashes |
| `noise_snapshots` | T1/T2, gate fidelities, readout errors per qubit |
| `benchmark_results` | QV, CLOPS, algorithmic scores with full parameters |

Foreign keys with `ON DELETE CASCADE`. WAL mode for concurrent reads.

## Architecture

```
qledger/
    schema/         # Universal data models (circuit IR, results, noise)
        gates.py    # 30+ canonical gates with cross-framework aliases
        circuit.py  # UniversalCircuit with hashing, validation, depth calc
        result.py   # ExecutionResult with entropy, fidelity computation
        noise.py    # NoiseSnapshot, QubitProperties, GateFidelity
    adapters/       # Framework adapters (Qiskit, Cirq, PennyLane)
        base.py     # Abstract adapter interface
        registry.py # Lazy auto-discovery registry
    storage/        # SQLite persistence layer
    versioning/     # Git-like circuit version tracking with diffs
    noise/          # Noise profiling and drift analysis
    benchmarks/     # Quantum Volume, CLOPS, algorithmic benchmarks
    core/           # Main QLedger engine
    cli/            # Command-line interface
```

## Development

```bash
pip install -e ".[dev]"
pytest           # 95 tests
ruff check .     # Lint
mypy qledger   # Type check
```

## License

[MIT](https://github.com/namashworks/qledger/blob/main/LICENSE)
