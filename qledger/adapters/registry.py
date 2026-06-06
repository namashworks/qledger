"""Adapter registry — lazy discovery and instantiation of framework adapters."""

from __future__ import annotations

import contextlib
from typing import Any, ClassVar

from .base import AdapterError, BaseAdapter

_ADAPTER_MODULES = {
    "qiskit": "qledger.adapters.qiskit_adapter",
    "cirq": "qledger.adapters.cirq_adapter",
    "pennylane": "qledger.adapters.pennylane_adapter",
}


class AdapterRegistry:
    """Central registry for framework adapters.

    Adapters are registered by framework name and instantiated lazily.
    This means ``import qledger`` never triggers a heavy import of
    Qiskit, Cirq, or PennyLane.

    Usage
    -----
    >>> adapter = AdapterRegistry.get("qiskit")
    >>> uc = adapter.from_native(qiskit_circuit)
    """

    _registry: ClassVar[dict[str, type[BaseAdapter]]] = {}
    _instances: ClassVar[dict[str, BaseAdapter]] = {}

    @classmethod
    def register(cls, adapter_cls: type[BaseAdapter]) -> type[BaseAdapter]:
        """Register an adapter class.  Can be used as a decorator."""
        # We use a temporary instance just to read framework_name.
        # To avoid import costs, we store the class and instantiate lazily.
        name = adapter_cls.__dict__.get("_FRAMEWORK_NAME")
        if name is None:
            raise AdapterError(
                f"{adapter_cls.__name__} must define a _FRAMEWORK_NAME class attribute."
            )
        cls._registry[name] = adapter_cls
        return adapter_cls

    @classmethod
    def get(cls, framework: str, **kwargs: Any) -> BaseAdapter:
        """Return an adapter instance for the given framework.

        Instantiates on first call, caches thereafter.

        Parameters
        ----------
        framework : str
            Framework identifier (``"qiskit"``, ``"cirq"``, ``"pennylane"``).

        Raises
        ------
        AdapterError
            If the framework is not registered or its library is missing.
        """
        framework = framework.lower()
        if framework in cls._instances:
            return cls._instances[framework]

        # Auto-discover: if the adapter isn't registered yet, try importing it
        if framework not in cls._registry and framework in _ADAPTER_MODULES:
            import importlib
            with contextlib.suppress(ImportError):
                importlib.import_module(_ADAPTER_MODULES[framework])

        adapter_cls = cls._registry.get(framework)
        if adapter_cls is None:
            available = ", ".join(sorted(cls._registry)) or "(none)"
            raise AdapterError(
                f"No adapter registered for {framework!r}. "
                f"Available: {available}. "
                f"Install the framework and its adapter extra "
                f"(e.g. pip install qledger[{framework}])."
            )
        try:
            instance = adapter_cls(**kwargs)
        except ImportError as exc:
            raise AdapterError(
                f"Framework {framework!r} is not installed. "
                f"Install it with: pip install qledger[{framework}]"
            ) from exc
        cls._instances[framework] = instance
        return instance

    @classmethod
    def available(cls) -> list[str]:
        """Return names of all registered adapters."""
        return sorted(cls._registry)

    @classmethod
    def is_available(cls, framework: str) -> bool:
        """Check if a framework adapter is registered."""
        return framework.lower() in cls._registry

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached adapter instances (useful for testing)."""
        cls._instances.clear()
