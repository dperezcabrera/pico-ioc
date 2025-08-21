# pico_ioc/resolver.py

import inspect
from typing import Any, Dict, Optional
from .container import PicoContainer
from .typing_utils import evaluated_hints, resolve_annotation_to_type
from ._state import _resolving

class Resolver:
    def __init__(self, container: PicoContainer):
        self.c = container

    def _resolve_by_mro(self, ann) -> Optional[Any]:
        try:
            for base in getattr(ann, "__mro__", ())[1:]:
                if base is object: break
                if self.c.has(base): return self.c.get(base)
        except Exception:
            pass
        return None

    def _resolve_param(self, name: str, ann) -> Any:
        if self.c.has(name): return self.c.get(name)
        if ann is not inspect._empty and self.c.has(ann): return self.c.get(ann)
        if ann is not inspect._empty:
            mro_hit = self._resolve_by_mro(ann)
            if mro_hit is not None: return mro_hit
        if self.c.has(str(name)): return self.c.get(str(name))
        key = name if ann is inspect._empty else ann
        return self.c.get(key)

    def kwargs_for_callable(self, fn, owner_cls=None) -> Dict[str, Any]:
        sig = inspect.signature(fn)
        hints = evaluated_hints(fn, owner_cls=owner_cls)
        deps: Dict[str, Any] = {}

        tok = _resolving.set(True)
        try:
            for p in sig.parameters.values():
                if p.name == "self" or p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                    continue
                raw_ann = hints.get(p.name, p.annotation)
                ann = resolve_annotation_to_type(raw_ann, fn, owner_cls)
                try:
                    deps[p.name] = self._resolve_param(p.name, ann)
                except NameError:
                    if p.default is not inspect._empty:
                        continue
                    missing = ann if ann is not inspect._empty else p.name
                    raise NameError(f"No provider found for key: {missing}")
            return deps
        finally:
            _resolving.reset(tok)

    def create_instance(self, cls: type) -> Any:
        kw = self.kwargs_for_callable(cls.__init__, owner_cls=cls)
        return cls(**kw)

