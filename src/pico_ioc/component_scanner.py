import inspect
import os
from typing import Any, Callable, Dict, List, Optional, Protocol, Set, Tuple, Union

from .analysis import DependencyRequest, analyze_callable_dependencies
from .config_registrar import ConfigurationManager
from .constants import PICO_INFRA, PICO_KEY, PICO_META, PICO_NAME, SCOPE_SINGLETON
from .decorators import get_return_type
from .factory import DeferredProvider, ProviderMetadata

KeyT = Union[str, type]
Provider = Callable[[], Any]


class CustomScanner(Protocol):
    def should_scan(self, obj: Any) -> bool: ...
    def scan(self, obj: Any) -> Optional[Tuple[KeyT, Provider, ProviderMetadata]]: ...


class ComponentScanner:
    def __init__(self, profiles: Set[str], environ: Dict[str, str], config_manager: ConfigurationManager):
        self._profiles = profiles
        self._environ = environ
        self._config_manager = config_manager
        self._candidates: Dict[KeyT, List[Tuple[bool, Provider, ProviderMetadata]]] = {}
        self._on_missing: List[Tuple[int, KeyT, type]] = []
        self._deferred: List[DeferredProvider] = []
        self._provides_functions: Dict[KeyT, Callable[..., Any]] = {}
        self._custom_scanners: List[CustomScanner] = []

    def register_custom_scanner(self, scanner: CustomScanner) -> None:
        self._custom_scanners.append(scanner)

    def get_scan_results(
        self,
    ) -> Tuple[
        Dict[KeyT, List[Tuple[bool, Provider, ProviderMetadata]]],
        List[Tuple[int, KeyT, type]],
        List[DeferredProvider],
        Dict[KeyT, Callable[..., Any]],
    ]:
        return self._candidates, self._on_missing, self._deferred, self._provides_functions

    def _queue(self, key: KeyT, provider: Provider, md: ProviderMetadata) -> None:
        lst = self._candidates.setdefault(key, [])
        lst.append((md.primary, provider, md))
        if isinstance(provider, DeferredProvider):
            self._deferred.append(provider)

    def _enabled_by_condition(self, obj: Any) -> bool:
        meta = getattr(obj, PICO_META, {})
        c = meta.get("conditional", None)
        if not c:
            return True

        p = set(c.get("profiles") or ())
        if p and not (p & self._profiles):
            return False

        req = c.get("require_env") or ()
        for k in req:
            if k not in self._environ or not self._environ.get(k):
                return False

        pred = c.get("predicate")
        if pred is None:
            return True

        try:
            ok = bool(pred())
        except Exception:
            return False
        if not ok:
            return False

        return True

    def _register_component_class(self, cls: type) -> None:
        if not self._enabled_by_condition(cls):
            return
        key = getattr(cls, PICO_KEY, cls)
        qset = set(str(q) for q in getattr(cls, PICO_META, {}).get("qualifier", ()))
        sc = getattr(cls, PICO_META, {}).get("scope", SCOPE_SINGLETON)
        deps = analyze_callable_dependencies(cls.__init__)
        provider = DeferredProvider(lambda pico, loc, c=cls, d=deps: pico.build_class(c, loc, d))
        md = ProviderMetadata(
            key=key,
            provided_type=cls,
            concrete_class=cls,
            factory_class=None,
            factory_method=None,
            qualifiers=qset,
            primary=bool(getattr(cls, PICO_META, {}).get("primary")),
            lazy=bool(getattr(cls, PICO_META, {}).get("lazy", False)),
            infra=getattr(cls, PICO_INFRA, None),
            pico_name=getattr(cls, PICO_NAME, None),
            scope=sc,
            dependencies=deps,
        )
        self._queue(key, provider, md)

    def _register_factory_class(self, cls: type) -> None:
        if not self._enabled_by_condition(cls):
            return

        factory_deps: Optional[Tuple[DependencyRequest, ...]] = None
        has_instance_provides = False
        for name in dir(cls):
            try:
                raw = inspect.getattr_static(cls, name)
                if inspect.isfunction(raw) and getattr(raw, PICO_INFRA, None) == "provides":
                    has_instance_provides = True
                    break
            except Exception:
                continue

        if has_instance_provides:
            factory_deps = analyze_callable_dependencies(cls.__init__)

        for name in dir(cls):
            try:
                raw = inspect.getattr_static(cls, name)
            except Exception:
                continue

            fn = None
            kind = None
            if isinstance(raw, staticmethod):
                fn = raw.__func__
                kind = "static"
            elif isinstance(raw, classmethod):
                fn = raw.__func__
                kind = "class"
            elif inspect.isfunction(raw):
                fn = raw
                kind = "instance"
            else:
                continue

            if getattr(fn, PICO_INFRA, None) != "provides":
                continue
            if not self._enabled_by_condition(fn):
                continue

            k = getattr(fn, PICO_KEY)
            deps = analyze_callable_dependencies(fn)

            if kind == "instance":
                if factory_deps is None:
                    factory_deps = analyze_callable_dependencies(cls.__init__)
                provider = DeferredProvider(
                    lambda pico, loc, fc=cls, mn=name, df=factory_deps, dm=deps: pico.build_method(
                        getattr(pico.build_class(fc, loc, df), mn), loc, dm
                    )
                )
            else:
                provider = DeferredProvider(lambda pico, loc, f=fn, d=deps: pico.build_method(f, loc, d))

            rt = get_return_type(fn)
            qset = set(str(q) for q in getattr(fn, PICO_META, {}).get("qualifier", ()))
            sc = getattr(fn, PICO_META, {}).get("scope", getattr(cls, PICO_META, {}).get("scope", SCOPE_SINGLETON))
            md = ProviderMetadata(
                key=k,
                provided_type=rt if isinstance(rt, type) else (k if isinstance(k, type) else None),
                concrete_class=None,
                factory_class=cls,
                factory_method=name,
                qualifiers=qset,
                primary=bool(getattr(fn, PICO_META, {}).get("primary")),
                lazy=bool(getattr(fn, PICO_META, {}).get("lazy", False)),
                infra=getattr(cls, PICO_INFRA, None),
                pico_name=getattr(fn, PICO_NAME, None),
                scope=sc,
                dependencies=deps,
            )
            self._queue(k, provider, md)

    def _register_provides_function(self, fn: Callable[..., Any]) -> None:
        if not self._enabled_by_condition(fn):
            return
        k = getattr(fn, PICO_KEY)
        deps = analyze_callable_dependencies(fn)
        provider = DeferredProvider(lambda pico, loc, f=fn, d=deps: pico.build_method(f, loc, d))
        rt = get_return_type(fn)
        qset = set(str(q) for q in getattr(fn, PICO_META, {}).get("qualifier", ()))
        sc = getattr(fn, PICO_META, {}).get("scope", SCOPE_SINGLETON)
        md = ProviderMetadata(
            key=k,
            provided_type=rt if isinstance(rt, type) else (k if isinstance(k, type) else None),
            concrete_class=None,
            factory_class=None,
            factory_method=getattr(fn, "__name__", None),
            qualifiers=qset,
            primary=bool(getattr(fn, PICO_META, {}).get("primary")),
            lazy=bool(getattr(fn, PICO_META, {}).get("lazy", False)),
            infra="provides",
            pico_name=getattr(fn, PICO_NAME, None),
            scope=sc,
            dependencies=deps,
        )
        self._queue(k, provider, md)
        self._provides_functions[k] = fn

    def _try_custom_scanners(self, obj: Any) -> bool:
        for scanner in self._custom_scanners:
            if scanner.should_scan(obj):
                result = scanner.scan(obj)
                if result:
                    key, provider, md = result
                    self._queue(key, provider, md)
                    if isinstance(provider, DeferredProvider):
                        self._deferred.append(provider)
                    return True
        return False

    def scan_module(self, module: Any) -> None:
        for _, obj in inspect.getmembers(module):
            if self._try_custom_scanners(obj):
                continue

            if inspect.isclass(obj) or getattr(obj, "_is_protocol", False):
                if inspect.isclass(obj):
                    meta = getattr(obj, PICO_META, {})

                    if "on_missing" in meta:
                        sel = meta["on_missing"]["selector"]
                        pr = int(meta["on_missing"].get("priority", 0))
                        self._on_missing.append((pr, sel, obj))
                        continue

                    infra = getattr(obj, PICO_INFRA, None)
                    if infra == "component":
                        self._register_component_class(obj)
                    elif infra == "factory":
                        self._register_factory_class(obj)
                    elif infra == "configured":
                        enabled = self._enabled_by_condition(obj)
                        reg_data = self._config_manager.register_configured_class(obj, enabled)
                        if reg_data:
                            self._queue(reg_data[0], reg_data[1], reg_data[2])

            elif inspect.isfunction(obj):
                if getattr(obj, PICO_INFRA, None) == "provides":
                    self._register_provides_function(obj)
