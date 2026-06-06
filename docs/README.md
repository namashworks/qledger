# QLedger Documentation

Full API and feature documentation. For a quick overview, start with the
[project README](../README.md).

## Guides

The fastest way to learn QLedger is by example. Each script in
[`examples/`](../examples) is runnable end-to-end:

| Example | What it shows |
|---|---|
| [`01_basic_usage.py`](../examples/01_basic_usage.py) | Create an experiment, run a circuit, read results |
| [`02_cross_framework.py`](../examples/02_cross_framework.py) | Convert circuits between frameworks via the universal IR |
| [`03_circuit_versioning.py`](../examples/03_circuit_versioning.py) | Git-like circuit version tracking, diffs, and checkout |
| [`04_benchmarking.py`](../examples/04_benchmarking.py) | Quantum Volume, CLOPS, and algorithmic fidelity benchmarks |
| [`05_noise_profiling.py`](../examples/05_noise_profiling.py) | Capture and compare hardware noise snapshots |

## Reference

| Topic | Where |
|---|---|
| Universal circuit IR | `qledger/schema/circuit.py` |
| Canonical gate set & aliases | `qledger/schema/gates.py` |
| Storage schema (SQLite) | `qledger/storage/database.py` |
| Framework adapters | `qledger/adapters/` |
| CLI | `qledger <command> --help` |

## Development

```bash
pip install -e ".[dev]"
pytest           # test suite
ruff check .     # lint
mypy qledger   # type check (strict)
```
