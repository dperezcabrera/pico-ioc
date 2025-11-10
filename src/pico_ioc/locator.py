from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union, get_origin, Annotated, get_args
from .factory import ProviderMetadata
from .decorators import Qualifier
import inspect
from .analysis import DependencyRequest

KeyT = Union[str, type]

def _get_signature_static(fn):
    return inspect.signature(fn)

class ComponentLocator:
    def __init__(self, metadata: Dict[KeyT, ProviderMetadata], indexes: Dict[str, Dict[Any, List[KeyT]]]) -> None:
        self._metadata = metadata
        self._indexes = indexes
        self._candidates: Optional[Set[KeyT]] = None
        
    def _ensure(self) -> Set[KeyT]:
        return set(self._metadata.keys()) if self._candidates is None else set(self._candidates)
        
    def _select_index(self, name: str, values: Iterable[Any]) -> Set[KeyT]:
        out: Set[KeyT] = set()
        idx = self._indexes.get(name, {})
        for v in values:
            out.update(idx.get(v, []))
        return out
        
    def _new(self, candidates: Set[KeyT]) -> "ComponentLocator":
        nl = ComponentLocator(self._metadata, self._indexes)
        nl._candidates = candidates
        return nl
        
    def with_index_any(self, name: str, *values: Any) -> "ComponentLocator":
        base = self._ensure()
        sel = self._select_index(name, values)
        return self._new(base & sel)
        
    def with_index_all(self, name: str, *values: Any) -> "ComponentLocator":
        base = self._ensure()
        cur = base
        for v in values:
            cur = cur & set(self._indexes.get(name, {}).get(v, []))
        return self._new(cur)
        
    def with_qualifier_any(self, *qs: Any) -> "ComponentLocator":
        return self.with_index_any("qualifier", *qs)
        
    def primary_only(self) -> "ComponentLocator":
        return self.with_index_any("primary", True)
        
    def lazy(self, is_lazy: bool = True) -> "ComponentLocator":
        return self.with_index_any("lazy", True) if is_lazy else self.with_index_any("lazy", False)
        
    def infra(self, *names: Any) -> "ComponentLocator":
        return self.with_index_any("infra", *names)
        
    def pico_name(self, *names: Any) -> "ComponentLocator":
        return self.with_index_any("pico_name", *names)
        
    def by_key_type(self, t: type) -> "ComponentLocator":
        base = self._ensure()
        if t is str:
            c = {k for k in base if isinstance(k, str)}
        elif t is type:
            c = {k for k in base if isinstance(k, type)}
        else:
            c = {k for k in base if isinstance(k, t)}
        return self._new(c)
        
    def keys(self) -> List[KeyT]:
        return list(self._ensure())
        
    @staticmethod
    def _implements_protocol(typ: type, proto: type) -> bool:
        if not getattr(proto, "_is_protocol", False):
            return False
        try:
            if getattr(proto, "__runtime_protocol__", False) or getattr(proto, "__annotations__", None) is not None:
                inst = object.__new__(typ)
                return isinstance(inst, proto)
        except Exception:
            pass
        
        for name, val in proto.__dict__.items():
            if name.startswith("_") or not (callable(val) or name in getattr(proto, "__annotations__", {})):
                continue
            
            if not hasattr(typ, name):
                return False
        return True
        
    def collect_by_type(self, t: type, q: Optional[str]) -> List[KeyT]:
        keys = list(self._metadata.keys())
        out: List[KeyT] = []
        for k in keys:
            md = self._metadata.get(k)
            if md is None:
                continue
            typ = md.provided_type or md.concrete_class
            if not isinstance(typ, type):
                continue
            
            ok = False
            try:
                ok = issubclass(typ, t)
            except Exception:
                ok = ComponentLocator._implements_protocol(typ, t)
                
            if ok and (q is None or q in md.qualifiers):
                out.append(k)
        return out
        
    def find_key_by_name(self, name: str) -> Optional[KeyT]:
        for k, md in self._metadata.items():
            if md.pico_name == name:
                return k
            typ = md.provided_type or md.concrete_class
            if isinstance(typ, type) and getattr(typ, "__name__", "") == name:
                return k
        return None

    def dependency_keys_for_static(self, md: ProviderMetadata):
        deps: List[KeyT] = []
        for dep in md.dependencies:
            if dep.is_list:
                if isinstance(dep.key, type):
                    keys = self.collect_by_type(dep.key, dep.qualifier)
                    deps.extend(keys)
            elif dep.is_dict:
                if isinstance(dep.key, type):
                    keys = self.collect_by_type(dep.key, dep.qualifier)
                    deps.extend(keys)
            else:
                deps.append(dep.key)
        return tuple(deps)
