"""Cross-framework adapters for quantum circuit interoperability.

Each adapter implements the ``BaseAdapter`` interface, providing:
* Circuit conversion (native ↔ ``UniversalCircuit``)
* Circuit execution on the framework's backends
* Noise profile extraction from hardware calibration data

Adapters are loaded lazily — importing ``qledger`` does not require any
quantum framework to be installed.  Only when you instantiate an adapter
does it import the corresponding library.
"""

from .base import AdapterError, BaseAdapter
from .registry import AdapterRegistry

__all__ = [
    "AdapterError",
    "AdapterRegistry",
    "BaseAdapter",
]
