from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from .factory import ProviderMetadata

KeyT = Union[str, type]

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