from typing import Any, Callable, Dict, List, Optional, Tuple, Union, Set
from .factory import ComponentFactory, ProviderMetadata
from .locator import ComponentLocator
from .exceptions import InvalidBindingError
from .analysis import DependencyRequest

KeyT = Union[str, type]

def _fmt(k: KeyT) -> str:
    return getattr(k, '__name__', str(k))

def _skip_type(t: type) -> bool:
    if t in (str, int, float, bool, bytes):
        return True
    if t is Any:
        return True
    if getattr(t, "_is_protocol", False):
        return True
    return False

class DependencyValidator:
    def __init__(self, metadata: Dict[KeyT, ProviderMetadata], factory: ComponentFactory, locator: ComponentLocator):
        self._metadata = metadata
        self._factory = factory
        self._locator = locator

    def _find_md_for_type(self, t: type) -> Optional[ProviderMetadata]:
        cands: List[ProviderMetadata] = []
        for md in self._metadata.values():
            typ = md.provided_type or md.concrete_class
            if not isinstance(typ, type):
                continue
            try:
                if issubclass(typ, t):
                    cands.append(md)
            except TypeError:
                 pass
            except Exception:
                continue
        if not cands:
            if getattr(t, "_is_protocol", False):
                 for md in self._metadata.values():
                    typ = md.provided_type or md.concrete_class
                    if isinstance(typ, type) and ComponentLocator._implements_protocol(typ, t):
                        cands.append(md)

        if not cands:
            return None
        prim = [m for m in cands if m.primary]
        return prim[0] if prim else cands[0]


    def _find_md_for_name(self, name: str) -> Optional[KeyT]:
         return self._locator.find_key_by_name(name)


    def validate_bindings(self) -> None:
        errors: List[str] = []

        for k, md in self._metadata.items():
            if md.infra == "configuration":
                continue

            if not md.dependencies and md.infra not in ("configured", "component") and not md.override:
                 continue
            if md.infra == "component" and md.concrete_class and md.concrete_class.__init__ is object.__init__:
                 continue


            loc_name = f"component {_fmt(k)}"
            if md.factory_method:
                loc_name = f"factory method {md.factory_method}"

            for dep in md.dependencies:
                if dep.is_optional:
                    continue

                if dep.is_list:
                    if dep.qualifier:
                        if not self._locator.collect_by_type(dep.key, dep.qualifier) and isinstance(dep.key, type) and not _skip_type(dep.key):
                            errors.append(f"{_fmt(k)} ({loc_name}) expects List[{_fmt(dep.key)}] with qualifier '{dep.qualifier}' but no matching components exist")
                    continue

                dep_key = dep.key
                if isinstance(dep_key, str):
                    key_found_by_name = self._find_md_for_name(dep_key)
                    directly_bound = dep_key in self._metadata or self._factory.has(dep_key)
                    if not key_found_by_name and not directly_bound:
                        errors.append(f"{_fmt(k)} ({loc_name}) depends on string key '{dep_key}' which is not bound")
                    continue

                if isinstance(dep_key, type) and not _skip_type(dep_key):
                    dep_key_found = self._factory.has(dep_key) or dep_key in self._metadata
                    if not dep_key_found:
                        assignable_md = self._find_md_for_type(dep_key)
                        if assignable_md is None:
                            by_name_key = self._find_md_for_name(getattr(dep_key, "__name__", ""))
                            if by_name_key is None:
                                errors.append(f"{_fmt(k)} ({loc_name}) depends on {_fmt(dep_key)} which is not bound")
                    continue

        if errors:
            raise InvalidBindingError(errors)
