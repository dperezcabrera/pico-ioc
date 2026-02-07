import importlib
import inspect
import logging
import pkgutil
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

from .aop import ContainerObserver
from .component_scanner import CustomScanner
from .config_builder import ContextConfig, configuration
from .constants import SCOPE_SINGLETON
from .container import PicoContainer
from .decorators import Qualifier, cleanup, component, configure, configured, factory, provides
from .exceptions import ConfigurationError, InvalidBindingError
from .factory import ComponentFactory, ProviderMetadata
from .locator import ComponentLocator
from .registrar import Registrar
from .scope import ScopedCaches, ScopeManager

KeyT = Union[str, type]
Provider = Callable[[], Any]


def _scan_package(package) -> Iterable[Any]:
    for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        yield importlib.import_module(name)


def _iter_input_modules(inputs: Union[Any, Iterable[Any]]) -> Iterable[Any]:
    seq = (
        inputs
        if isinstance(inputs, Iterable) and not inspect.ismodule(inputs) and not isinstance(inputs, str)
        else [inputs]
    )
    seen: Set[str] = set()
    for it in seq:
        if isinstance(it, str):
            mod = importlib.import_module(it)
        else:
            mod = it
        if hasattr(mod, "__path__"):
            for sub in _scan_package(mod):
                name = getattr(sub, "__name__", None)
                if name and name not in seen:
                    seen.add(name)
                    yield sub
        else:
            name = getattr(mod, "__name__", None)
            if name and name not in seen:
                seen.add(name)
                yield mod


def _normalize_override_provider(v: Any):
    if isinstance(v, tuple) and len(v) == 2:
        src, lz = v
        if callable(src):
            return (lambda s=src: s()), bool(lz)
        return (lambda s=src: s), bool(lz)
    if callable(v):
        return (lambda f=v: f()), False
    return (lambda inst=v: inst), False


def init(
    modules: Union[Any, Iterable[Any]],
    *,
    profiles: Tuple[str, ...] = (),
    allowed_profiles: Optional[Iterable[str]] = None,
    environ: Optional[Dict[str, str]] = None,
    overrides: Optional[Dict[KeyT, Any]] = None,
    logger: Optional[logging.Logger] = None,
    config: Optional[ContextConfig] = None,
    custom_scopes: Optional[Iterable[str]] = None,
    validate_only: bool = False,
    container_id: Optional[str] = None,
    observers: Optional[List[ContainerObserver]] = None,
    custom_scanners: Optional[List[CustomScanner]] = None,
) -> PicoContainer:
    active = tuple(p.strip() for p in profiles if p)

    allowed_set = set(a.strip() for a in allowed_profiles) if allowed_profiles is not None else None
    if allowed_set is not None:
        unknown = set(active) - allowed_set
        if unknown:
            raise ConfigurationError(f"Unknown profiles: {sorted(unknown)}; allowed: {sorted(allowed_set)}")

    factory = ComponentFactory()
    caches = ScopedCaches()
    scopes = ScopeManager()
    if custom_scopes:
        for name in custom_scopes:
            scopes.register_scope(name)

    pico = PicoContainer(factory, caches, scopes, container_id=container_id, profiles=active, observers=observers or [])
    registrar = Registrar(factory, profiles=active, environ=environ, logger=logger, config=config)

    if custom_scanners:
        for scanner in custom_scanners:
            registrar.register_custom_scanner(scanner)

    for m in _iter_input_modules(modules):
        registrar.register_module(m)

    if overrides:
        for k, v in overrides.items():
            prov, _ = _normalize_override_provider(v)
            factory.bind(k, prov)

    registrar.finalize(overrides, pico_instance=pico)
    if validate_only:
        locator = registrar.locator()
        pico.attach_locator(locator)
        _fail_fast_cycle_check(pico)
        return pico

    locator = registrar.locator()
    registrar.attach_runtime(pico, locator)
    pico.attach_locator(locator)
    _fail_fast_cycle_check(pico)

    if not validate_only:
        eager_singletons = []
        for key, md in locator._metadata.items():
            if md.scope == SCOPE_SINGLETON and not md.lazy:
                cache = pico._cache_for(key)
                instance = cache.get(key)
                if instance is None:
                    instance = pico.get(key)
                    eager_singletons.append(instance)
                else:
                    eager_singletons.append(instance)

        configure_awaitables = []
        for instance in eager_singletons:
            res = pico._run_configure_methods(instance)
            if inspect.isawaitable(res):
                configure_awaitables.append(res)

        if configure_awaitables:
            raise ConfigurationError(
                "Sync init() found eagerly loaded singletons with async @configure methods. "
                "This can be caused by an async __ainit__ or async @configure. "
                "Use an async main function and await pico.aget() for those components, "
                "or mark them as lazy=True."
            )

    return pico


def _find_cycle(graph: Dict[KeyT, Tuple[KeyT, ...]]) -> Optional[Tuple[KeyT, ...]]:
    temp: Set[KeyT] = set()
    perm: Set[KeyT] = set()
    stack: List[KeyT] = []

    def visit(n: KeyT) -> Optional[Tuple[KeyT, ...]]:
        if n in perm:
            return None
        if n in temp:
            try:
                idx = stack.index(n)
                return tuple(stack[idx:] + [n])
            except ValueError:
                return tuple([n, n])
        temp.add(n)
        stack.append(n)
        for m in graph.get(n, ()):
            c = visit(m)
            if c:
                return c
        stack.pop()
        temp.remove(n)
        perm.add(n)
        return None

    for node in graph.keys():
        c = visit(node)
        if c:
            return c
    return None


def _format_key(k: KeyT) -> str:
    return getattr(k, "__name__", str(k))


def _fail_fast_cycle_check(pico: "PicoContainer") -> None:
    graph = pico.build_resolution_graph()
    cyc = _find_cycle(graph)
    if not cyc:
        return
    path = " -> ".join(_format_key(k) for k in cyc)
    raise InvalidBindingError([f"Circular dependency detected: {path}"])
