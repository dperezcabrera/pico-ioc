from __future__ import annotations
import inspect as _inspect
import logging
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from typing import get_origin, get_args, Annotated

from .interceptors import MethodInterceptor, ContainerInterceptor
from .container import PicoContainer, _is_compatible
from .policy import apply_policy, _conditional_active
from .plugins import PicoPlugin, run_plugin_hook
from .scanner import scan_and_configure
from .resolver import Resolver, _get_hints
from . import _state
from .config import ConfigRegistry

class PicoContainerBuilder:
    def __init__(self):
        self._scan_plan: List[Tuple[Any, Optional[Callable[[str], bool]], Tuple[PicoPlugin, ...]]] = []
        self._overrides: Dict[Any, Any] = {}
        self._profiles: Optional[List[str]] = None
        self._plugins: Tuple[PicoPlugin, ...] = ()
        self._include_tags: Optional[set[str]] = None
        self._exclude_tags: Optional[set[str]] = None
        self._roots: Iterable[type] = ()
        self._providers: Dict[Any, Dict] = {}
        self._eager: bool = True
        self._config_registry: ConfigRegistry | None = None

    def with_config(self, registry: ConfigRegistry) -> "PicoContainerBuilder":
        self._config_registry = registry
        return self

    def with_plugins(self, plugins: Tuple[PicoPlugin, ...]) -> "PicoContainerBuilder":
        self._plugins = plugins or ()
        return self

    def with_profiles(self, profiles: Optional[List[str]]) -> "PicoContainerBuilder":
        self._profiles = profiles
        return self

    def add_scan_package(self, package: Any, exclude: Optional[Callable[[str], bool]] = None) -> "PicoContainerBuilder":
        self._scan_plan.append((package, exclude, self._plugins))
        return self

    def with_overrides(self, overrides: Optional[Dict[Any, Any]]) -> "PicoContainerBuilder":
        self._overrides = overrides or {}
        return self

    def with_tag_filters(self, include: Optional[set[str]], exclude: Optional[set[str]]) -> "PicoContainerBuilder":
        self._include_tags = include
        self._exclude_tags = exclude
        return self

    def with_roots(self, roots: Iterable[type]) -> "PicoContainerBuilder":
        self._roots = roots or ()
        return self

    def with_eager(self, eager: bool) -> "PicoContainerBuilder":
        self._eager = bool(eager)
        return self

    def build(self) -> PicoContainer:
        requested_profiles = _resolve_profiles(self._profiles)
        container = PicoContainer(providers=self._providers)
        container._active_profiles = tuple(requested_profiles)
        setattr(container, "_config_registry", self._config_registry)
        all_infras: list[tuple[type, dict]] = []
        for pkg, exclude, scan_plugins in self._scan_plan:
            with _state.scanning_flag():
                c, f, infra_decls = scan_and_configure(pkg, container, exclude=exclude, plugins=scan_plugins)
                logging.info("Scanned '%s' (components: %d, factories: %d)", getattr(pkg, "__name__", pkg), c, f)
                all_infras.extend(infra_decls)
        _run_infrastructure(container=container, infra_decls=all_infras, profiles=requested_profiles)
        binder = container.binder()
        if self._overrides:
            _apply_overrides(container, self._overrides)
        run_plugin_hook(self._plugins, "after_bind", container, binder)
        run_plugin_hook(self._plugins, "before_eager", container, binder)
        apply_policy(container, profiles=requested_profiles)
        _filter_by_tags(container, self._include_tags, self._exclude_tags)
        if self._roots:
            _restrict_to_subgraph(container, self._roots, self._overrides)
        run_plugin_hook(self._plugins, "after_ready", container, binder)
        if self._eager:
            container.eager_instantiate_all()
        logging.info("Container configured and ready.")
        return container

def _resolve_profiles(profiles: Optional[List[str]]) -> List[str]:
    if profiles is not None:
        return list(profiles)
    env_val = os.getenv("PICO_PROFILE", "")
    return [p.strip() for p in env_val.split(",") if p.strip()]

def _as_provider(val):
    if isinstance(val, tuple) and len(val) == 2 and callable(val[0]) and isinstance(val[1], bool):
        return val[0], val[1]
    if callable(val):
        return val, False
    return (lambda v=val: v), False

def _apply_overrides(container: PicoContainer, overrides: Dict[Any, Any]) -> None:
    for key, val in overrides.items():
        provider, lazy = _as_provider(val)
        container.bind(key, provider, lazy=lazy)

def _filter_by_tags(container: PicoContainer, include_tags: Optional[set[str]], exclude_tags: Optional[set[str]]) -> None:
    if not include_tags and not exclude_tags:
        return
    def _tag_ok(meta: dict) -> bool:
        tags = set(meta.get("tags", ()))
        if include_tags and not tags.intersection(include_tags):
            return False
        if exclude_tags and tags.intersection(exclude_tags):
            return False
        return True
    container._providers = {k: v for k, v in container._providers.items() if _tag_ok(v)}

def _compute_allowed_subgraph(container: PicoContainer, roots: Iterable[type]) -> set:
    allowed: set[Any] = set(roots)
    stack = list(roots or ())
    def _add_impls_for_base(base_t):
        for prov_key, meta in container._providers.items():
            cls = prov_key if isinstance(prov_key, type) else None
            if cls is not None and _is_compatible(cls, base_t):
                if prov_key not in allowed:
                    allowed.add(prov_key)
                    stack.append(prov_key)
    while stack:
        k = stack.pop()
        allowed.add(k)
        if isinstance(k, type):
            _add_impls_for_base(k)
        cls = k if isinstance(k, type) else None
        if cls is None or not container.has(k):
            continue
        try:
            sig = _inspect.signature(cls.__init__)
            hints = _get_hints(cls.__init__, owner_cls=cls)
        except Exception:
            continue
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            ann = hints.get(pname, param.annotation)
            origin = get_origin(ann) or ann
            if origin in (list, tuple):
                inner = (get_args(ann) or (object,))[0]
                if get_origin(inner) is Annotated:
                    inner = (get_args(inner) or (object,))[0]
                if isinstance(inner, type):
                    if inner not in allowed:
                        stack.append(inner)
                continue
            if isinstance(ann, type) and ann not in allowed:
                stack.append(ann)
            elif container.has(pname) and pname not in allowed:
                stack.append(pname)
    return allowed

def _restrict_to_subgraph(container: PicoContainer, roots: Iterable[type], overrides: Optional[Dict[Any, Any]]) -> None:
    allowed = _compute_allowed_subgraph(container, roots)
    keep_keys: set[Any] = allowed | (set(overrides.keys()) if overrides else set())
    container._providers = {k: v for k, v in container._providers.items() if k in keep_keys}

def _run_infrastructure(*, container: PicoContainer, infra_decls: List[tuple[type, dict]], profiles: List[str]) -> None:
    def _active(meta: dict) -> bool:
        profs = tuple(meta.get("profiles", ())) or ()
        if profs and (not profiles or not any(p in profs for p in profiles)):
            return False
        req_env = tuple(meta.get("require_env", ())) or ()
        if req_env:
            import os
            if not all(os.getenv(k) not in (None, "") for k in req_env):
                return False
        pred = meta.get("predicate", None)
        if callable(pred):
            try:
                if not bool(pred()):
                    return False
            except Exception:
                return False
        return True
    from .resolver import Resolver
    from .infra import Infra
    resolver = Resolver(container)
    active_infras: List[tuple[int, type]] = []
    for cls, meta in infra_decls:
        if not _active(meta):
            continue
        order = int(meta.get("order", 0))
        active_infras.append((order, cls))
    active_infras.sort(key=lambda t: (t[0], getattr(t[1], "__qualname__", "")))
    for _ord, cls in active_infras:
        try:
            inst = resolver.create_instance(cls)
        except Exception:
            import logging
            logging.exception("Failed to construct infrastructure %r", cls)
            continue
        infra = Infra(container=container, profiles=tuple(profiles))
        fn = getattr(inst, "configure", None)
        if callable(fn):
            try:
                fn(infra)
            except Exception:
                import logging
                logging.exception("Infrastructure configure() failed for %r", cls)

