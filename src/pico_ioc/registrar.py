import os
import inspect
import logging
import functools
from dataclasses import is_dataclass, fields, MISSING
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, get_args, get_origin, Iterable
from .constants import LOGGER, PICO_INFRA, PICO_NAME, PICO_KEY, PICO_META
from .exceptions import ConfigurationError, InvalidBindingError
from .factory import ComponentFactory, ProviderMetadata, DeferredProvider
from .locator import ComponentLocator
from .aop import UnifiedComponentProxy
from .decorators import Qualifier, get_return_type
from .config_builder import ContextConfig
from .config_runtime import TreeSource
from .config_registrar import ConfigurationManager
from .provider_selector import ProviderSelector
from .dependency_validator import DependencyValidator
from .component_scanner import ComponentScanner
from .analysis import analyze_callable_dependencies, DependencyRequest
from .container import PicoContainer

KeyT = Union[str, type]
Provider = Callable[[], Any]

def _can_be_selected_for(reg_md: Dict[KeyT, ProviderMetadata], selector: Any) -> bool:
    if not isinstance(selector, type):
        return False
    for md in reg_md.values():
        typ = md.provided_type or md.concrete_class
        if isinstance(typ, type):
            try:
                if issubclass(typ, selector):
                    return True
            except Exception:
                continue
    return False

class Registrar:
    def __init__(self, factory: ComponentFactory, *, profiles: Tuple[str, ...] = (), environ: Optional[Dict[str, str]] = None, logger: Optional[logging.Logger] = None, config: Optional[ContextConfig] = None) -> None:
        self._factory = factory
        self._profiles = set(p.strip() for p in profiles if p)
        self._environ = environ if environ is not None else os.environ
        self._metadata: Dict[KeyT, ProviderMetadata] = {}
        self._indexes: Dict[str, Dict[Any, List[KeyT]]] = {}
        self._log = logger or LOGGER
        self._config_manager = ConfigurationManager(config)
        self._provider_selector = ProviderSelector(self._config_manager)
        self._scanner = ComponentScanner(self._profiles, self._environ, self._config_manager)
        self._deferred: List[DeferredProvider] = []
        self._provides_functions: Dict[KeyT, Callable[..., Any]] = {}


    def locator(self) -> ComponentLocator:
        loc = ComponentLocator(dict(self._metadata), dict(self._indexes))
        setattr(loc, "_provides_functions", dict(self._provides_functions))
        return loc

    def attach_runtime(self, pico, locator: ComponentLocator) -> None:
        for deferred in self._deferred:
            deferred.attach(pico, locator)
        for key, md in list(self._metadata.items()):
            if md.lazy:
                original = self._factory.get(key, origin='lazy')
                def lazy_proxy_provider(_orig=original, _p=pico, _k=key):
                    return UnifiedComponentProxy(container=_p, object_creator=_orig, component_key=_k)
                self._factory.bind(key, lazy_proxy_provider)


    def _bind_if_absent(self, key: KeyT, provider: Provider) -> None:
        if not self._factory.has(key):
            self._factory.bind(key, provider)


    def register_module(self, module: Any) -> None:
        self._scanner.scan_module(module)


    def _find_md_for_type(self, t: type) -> Optional[ProviderMetadata]:
        cands: List[ProviderMetadata] = []
        for md in self._metadata.values():
            typ = md.provided_type or md.concrete_class
            if not isinstance(typ, type):
                continue
            try:
                if issubclass(typ, t):
                    cands.append(md)
            except Exception:
                continue
        if not cands:
            return None
        prim = [m for m in cands if m.primary]
        return prim[0] if prim else cands[0]

    def _find_narrower_scope_from_deps(self, deps: Tuple[DependencyRequest, ...]) -> Optional[str]:
        if not deps:
            return None

        for dep_req in deps:
            if dep_req.is_list:
                continue

            dep_md = self._metadata.get(dep_req.key)
            if dep_md is None:
                if isinstance(dep_req.key, type):
                    dep_md = self._find_md_for_type(dep_req.key)

            if dep_md and dep_md.scope != "singleton":
                return dep_md.scope
        return None

    def _promote_scopes(self) -> None:
        for k, md in list(self._metadata.items()):
            if md.scope == "singleton":
                ns = self._find_narrower_scope_from_deps(md.dependencies)
                if ns and ns != "singleton":
                    self._metadata[k] = ProviderMetadata(key=md.key, provided_type=md.provided_type, concrete_class=md.concrete_class, factory_class=md.factory_class, factory_method=md.factory_method, qualifiers=md.qualifiers, primary=md.primary, lazy=md.lazy, infra=md.infra, pico_name=md.pico_name, override=md.override, scope=ns, dependencies=md.dependencies)

    def _rebuild_indexes(self) -> None:
        self._indexes.clear()
        def add(idx: str, val: Any, key: KeyT):
            b = self._indexes.setdefault(idx, {}).setdefault(val, [])
            if key not in b:
                b.append(key)

        for k, md in self._metadata.items():
            for q in md.qualifiers:
                add("qualifier", q, k)
            if md.primary:
                add("primary", True, k)
            add("lazy", bool(md.lazy), k)
            if md.infra is not None:
                add("infra", md.infra, k)
            if md.pico_name is not None:
                add("pico_name", md.pico_name, k)


    def finalize(self, overrides: Optional[Dict[KeyT, Any]], *, pico_instance: PicoContainer) -> None:
        candidates, on_missing, deferred_providers, provides_functions = self._scanner.get_scan_results()
        self._deferred = deferred_providers
        self._provides_functions = provides_functions

        winners = self._provider_selector.select_providers(candidates)
        for key, (provider, md) in winners.items():
            self._bind_if_absent(key, provider)
            self._metadata[key] = md
            
        if PicoContainer not in self._metadata:
            self._factory.bind(PicoContainer, lambda: pico_instance)
            self._metadata[PicoContainer] = ProviderMetadata(
                key=PicoContainer,
                provided_type=PicoContainer,
                concrete_class=PicoContainer,
                factory_class=None,
                factory_method=None,
                qualifiers=set(),
                primary=True,
                lazy=False,
                infra="component",
                pico_name="PicoContainer",
                override=True,
                scope="singleton",
                dependencies=()
            )

        self._promote_scopes()
        self._rebuild_indexes()

        for _, selector, default_cls in sorted(on_missing, key=lambda x: -x[0]):
            key = selector
            if key in self._metadata or self._factory.has(key) or _can_be_selected_for(self._metadata, selector):
                continue

            deps = analyze_callable_dependencies(default_cls.__init__)
            provider = DeferredProvider(lambda pico, loc, c=default_cls, d=deps: pico.build_class(c, loc, d))
            qset = set(str(q) for q in getattr(default_cls, PICO_META, {}).get("qualifier", ()))
            sc = getattr(default_cls, PICO_META, {}).get("scope", "singleton")
            md = ProviderMetadata(key=key, provided_type=key if isinstance(key, type) else None, concrete_class=default_cls, factory_class=None, factory_method=None, qualifiers=qset, primary=True, lazy=bool(getattr(default_cls, PICO_META, {}).get("lazy", False)), infra=getattr(default_cls, PICO_INFRA, None), pico_name=getattr(default_cls, PICO_NAME, None), override=True, scope=sc, dependencies=deps)

            self._bind_if_absent(key, provider)
            self._metadata[key] = md
            if isinstance(provider, DeferredProvider):
                self._deferred.append(provider)

        self._rebuild_indexes()

        final_locator = ComponentLocator(self._metadata, self._indexes)
        validator = DependencyValidator(self._metadata, self._factory, final_locator)
        validator.validate_bindings()
