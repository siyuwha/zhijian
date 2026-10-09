"""
App package initialization with dual-namespace compatibility.
Ensures both 'app' and 'backend.app' can be resolved seamlessly in Docker and local environments.
"""
import sys
import types

_current_mod = sys.modules.get(__name__)
if "backend" not in sys.modules:
    _backend_pkg = types.ModuleType("backend")
    _backend_pkg.app = _current_mod
    _backend_pkg.__path__ = []
    sys.modules["backend"] = _backend_pkg
    sys.modules["backend.app"] = _current_mod
