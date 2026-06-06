# Contributing

Contributions are welcome. Here's how to get started.

## Setup

```bash
git clone https://github.com/namashworks/qledger.git
cd qledger
pip install -e ".[dev]"
```

## Development workflow

1. Create a feature branch from `main`.
2. Write your code and add tests.
3. Run the full check suite:

```bash
pytest
ruff check .
mypy qledger
```

4. Open a pull request against `main`.

## Adding a new framework adapter

1. Create `qledger/adapters/<framework>_adapter.py`.
2. Implement the `BaseAdapter` interface (see `base.py`).
3. Add the `@AdapterRegistry.register` decorator.
4. Add the module path to `_ADAPTER_MODULES` in `registry.py`.
5. Add the framework as an optional dependency in `pyproject.toml`.
6. Add tests in `tests/integration/`.

## Code style

- [PEP 8](https://peps.python.org/pep-0008/) enforced by Ruff
- Type annotations on all public functions
- [NumPy-style](https://numpydoc.readthedocs.io/en/latest/format.html) docstrings

## Tests

All tests use in-memory SQLite (`:memory:`), so they're fast and require no external services. Integration tests that need a quantum framework are in `tests/integration/`.
