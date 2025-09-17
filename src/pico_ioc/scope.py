from __future__ import annotations

from typing import Any, Optional

from .container import PicoContainer

class ScopedContainer(PicoContainer):
    def __init__(self, built_container: PicoContainer, base: Optional[PicoContainer], strict: bool):
        super().__init__(providers=getattr(built_container, "_providers", {}).copy())
        self._active_profiles = getattr(built_container, "_active_profiles", ())
        base_method_its = getattr(base, "_method_interceptors", ()) if base else ()
        base_container_its = getattr(base, "_container_interceptors", ()) if base else ()
        self._method_interceptors = base_method_its
        self._container_interceptors = base_container_its
        self._seen_interceptor_types = {type(it) for it in base_container_its}
        for it in getattr(built_container, "_method_interceptors", ()):
            self.add_method_interceptor(it)
        for it in getattr(built_container, "_container_interceptors", ()):
            self.add_container_interceptor(it)
        self._base = base
        self._strict = strict
        if base:
            self._singletons.update(getattr(base, "_singletons", {}))

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return False

    def has(self, key: Any) -> bool:
        if super().has(key): return True
        if not self._strict and self._base is not None:
            return self._base.has(key)
        return False

    def get(self, key: Any):
        try:
            return super().get(key)
        except NameError as e:
            if not self._strict and self._base is not None and self._base.has(key):
                return self._base.get(key)
            raise e

