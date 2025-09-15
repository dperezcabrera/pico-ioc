# src/pico_ioc/builder.py
from __future__ import annotations
import inspect as _inspect
import logging
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from typing import get_origin, get_args, Annotated

# Add missing imports for interceptor types
from .interceptors import MethodInterceptor, ContainerInterceptor
from .container import PicoContainer, _is_compatible
from .policy import apply_policy, _conditional_active
from .plugins import PicoPlugin, run_plugin_hook
from .scanner import scan_and_configure
from .resolver import Resolver, _get_hints
from . import _state


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
        self._interceptor_decls: List[Tuple[Any, dict]] = []

    def with_plugins(self, plugins: Tuple[PicoPlugin, ...]) -> PicoContainerBuilder:
        self._plugins = plugins
        return self

    def with_profiles(self, profiles: Optional[List[str]]) -> PicoContainerBuilder:
        self._profiles = profiles
        return self

    def add_scan_package(self, package: Any, exclude: Optional[Callable[[str], bool]] = None) -> PicoContainerBuilder:
        self._scan_plan.append((package, exclude, self._plugins))
        return self

    def with_overrides(self, overrides: Optional[Dict[Any, Any]]) -> PicoContainerBuilder:
        self._overrides = overrides or {}
        return self

    def with_tag_filters(self, include: Optional[set[str]], exclude: Optional[set[str]]) -> PicoContainerBuilder:
        self._include_tags = include
        self._exclude_tags = exclude
        return self

    def with_roots(self, roots: Iterable[type]) -> PicoContainerBuilder:
        self._roots = roots
        return self

    def build(self) -> PicoContainer:
        requested_profiles = _resolve_profiles(self._profiles)
        
        # We now create a single container instance upfront and configure it.
        container = PicoContainer(providers=self._providers)
        container._active_profiles = tuple(requested_profiles)

        for pkg, exclude, scan_plugins in self._scan_plan:
            with _state.scanning_flag():
                c, f, decls = scan_and_configure(pkg, container, exclude=exclude, plugins=scan_plugins)
                logging.info("Scanned '%s' (components: %d, factories: %d)", getattr(pkg, "__name__", pkg), c, f)
                self._interceptor_decls.extend(decls)

        _activate_and_build_interceptors(
            container=container,
            interceptor_decls=self._interceptor_decls,
            profiles=requested_profiles
        )
        
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
        container.eager_instantiate_all()
        logging.info("Container configured and ready.")
        return container

# ... (Helper functions like _resolve_profiles, _apply_overrides etc. remain here) ...
# --- Start of moved helpers ---
def _resolve_profiles(profiles: Optional[list[str]]) -> list[str]:
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
    allowed: set[Any] = set(roots) # Start with roots
    stack = list(roots or ())
    # ... (rest of the function is the same, just ensure it's here)
    def _add_impls_for_base(base_t):
        for prov_key, meta in container._providers.items():
            cls = prov_key if isinstance(prov_key, type) else None
            if cls is not None and _is_compatible(cls, base_t):
                if prov_key not in allowed:
                    allowed.add(prov_key)
                    stack.append(prov_key)

    while stack:
        k = stack.pop()
        # if k in allowed: continue # Redundant, add() handles it
        allowed.add(k)
        if isinstance(k, type): _add_impls_for_base(k)
        cls = k if isinstance(k, type) else None
        if cls is None or not container.has(k): continue
        try:
            sig = _inspect.signature(cls.__init__)
            hints = _get_hints(cls.__init__, owner_cls=cls)
        except Exception:
            continue
        for pname, param in sig.parameters.items():
            if pname == "self": continue
            ann = hints.get(pname, param.annotation)
            origin = get_origin(ann) or ann
            if origin in (list, tuple):
                inner = (get_args(ann) or (object,))[0]
                if get_origin(inner) is Annotated: inner = (get_args(inner) or (object,))[0]
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

def _activate_and_build_interceptors(
    *, container: PicoContainer, interceptor_decls: list[tuple[Any, dict]], profiles: list[str],
) -> None:
    resolver = Resolver(container)
    active: list[tuple[int, str, str, Any]] = []
    activated_method_names: list[str] = []
    activated_container_names: list[str] = []
    skipped_debug: list[str] = []

    def _interceptor_meta_active(meta: dict) -> bool:
        profs = tuple(meta.get("profiles", ())) or ()
        if profs and (not profiles or not any(p in profs for p in profiles)): return False
        req_env = tuple(meta.get("require_env", ())) or ()
        if req_env and not all(os.getenv(k) not in (None, "") for k in req_env): return False
        pred = meta.get("predicate", None)
        if callable(pred):
            try:
                if not bool(pred()): return False
            except Exception:
                logging.exception("Interceptor predicate failed; skipping")
                return False
        return True

    def _looks_like_container_interceptor(inst: Any) -> bool:
        return all(hasattr(inst, m) for m in ("on_resolve", "on_before_create", "on_after_create", "on_exception"))

    for raw_obj, meta in interceptor_decls:
        owner_cls, obj = (raw_obj[0], raw_obj[1]) if isinstance(raw_obj, tuple) and len(raw_obj) == 2 else (None, raw_obj)
        qn = getattr(obj, "__qualname__", repr(obj))
        if not _conditional_active(obj, profiles=profiles) or not _interceptor_meta_active(meta):
            skipped_debug.append(f"skip:{qn}")
            continue
        try:
            if isinstance(obj, type):
                inst = resolver.create_instance(obj)
            elif owner_cls is not None:
                owner_inst = resolver.create_instance(owner_cls)
                bound = obj.__get__(owner_inst, owner_cls)
                kwargs = resolver.kwargs_for_callable(bound, owner_cls=owner_cls)
                inst = bound(**kwargs)
            else:
                kwargs = resolver.kwargs_for_callable(obj, owner_cls=None)
                inst = obj(**kwargs)
        except Exception:
            logging.exception("Failed to construct interceptor %r", obj)
            continue
        kind = meta.get("kind", "method")
        if kind == "method" and not callable(inst):
            logging.error("Interceptor %s is not valid for kind %s; skipping", qn, kind)
            continue
        if kind == "container" and not _looks_like_container_interceptor(inst):
            logging.error("Container interceptor %s lacks required methods; skipping", qn)
            continue
        order = int(meta.get("order", 0))
        active.append((order, qn, kind, inst))
    
    active.sort(key=lambda t: (t[0], t[1]))
    
    for _order, _qn, kind, inst in active:
        if kind == "container":
            container.add_container_interceptor(inst)
            activated_container_names.append(_qn)
        else:
            container.add_method_interceptor(inst)
            activated_method_names.append(_qn)

    if activated_method_names or activated_container_names:
        logging.info("Interceptors activated: method=%d, container=%d", len(activated_method_names), len(activated_container_names))
        logging.debug("Activated method=%s; Activated container=%s", ", ".join(activated_method_names) or "-", ", ".join(activated_container_names) or "-")
    if skipped_debug:
        logging.debug("Skipped interceptors: %s", ", ".join(skipped_debug))
