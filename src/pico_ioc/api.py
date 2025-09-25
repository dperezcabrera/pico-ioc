import os
import json
import inspect
import functools
import importlib
import pkgutil
import logging
from dataclasses import is_dataclass, fields, dataclass, MISSING
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union, get_args, get_origin, Annotated, Protocol
from .constants import LOGGER, PICO_INFRA, PICO_NAME, PICO_KEY, PICO_META
from .exceptions import (
    ProviderNotFoundError,
    CircularDependencyError,
    ScopeError,
    ConfigurationError,
    SerializationError,
    InvalidBindingError,
)
from .factory import ComponentFactory, ProviderMetadata, DeferredProvider
from .locator import ComponentLocator
from .scope import ScopeManager, ScopedCaches
from .container import PicoContainer
from .aop import UnifiedComponentProxy

KeyT = Union[str, type]
Provider = Callable[[], Any]

class ConfigSource(Protocol):
    def get(self, key: str) -> Optional[str]: ...

class EnvSource:
    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix
    def get(self, key: str) -> Optional[str]:
        return os.environ.get(self.prefix + key)

class FileSource:
    def __init__(self, path: str, prefix: str = "") -> None:
        self.prefix = prefix
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}
    def get(self, key: str) -> Optional[str]:
        k = self.prefix + key
        v = self._data
        for part in k.split("__"):
            if isinstance(v, dict) and part in v:
                v = v[part]
            else:
                return None
        if isinstance(v, (str, int, float, bool)):
            return str(v)
        return None

def _meta_get(obj: Any) -> Dict[str, Any]:
    m = getattr(obj, PICO_META, None)
    if m is None:
        m = {}
        setattr(obj, PICO_META, m)
    return m

def component(
    cls=None,
    *,
    name: Any = None,
    qualifiers: Iterable[str] = (),
    scope: str = "singleton",
    primary: bool = False,
    lazy: bool = False,
    conditional_profiles: Iterable[str] = (),
    conditional_require_env: Iterable[str] = (),
    conditional_predicate: Optional[Callable[[], bool]] = None,
    on_missing_selector: Optional[object] = None,
    on_missing_priority: int = 0,
):
    def dec(c):
        setattr(c, PICO_INFRA, "component")
        setattr(c, PICO_NAME, name if name is not None else getattr(c, "__name__", str(c)))
        setattr(c, PICO_KEY, name if name is not None else c)
        m = _meta_get(c)
        m["qualifier"] = tuple(str(q) for q in qualifiers or ())
        m["scope"] = scope
        if primary:
            m["primary"] = True
        if lazy:
            m["lazy"] = True
        if conditional_profiles or conditional_require_env or conditional_predicate is not None:
            m["conditional"] = {
                "profiles": tuple(p for p in conditional_profiles or ()),
                "require_env": tuple(e for e in conditional_require_env or ()),
                "predicate": conditional_predicate,
            }
        if on_missing_selector is not None:
            m["on_missing"] = {"selector": on_missing_selector, "priority": int(on_missing_priority)}
        return c
    return dec(cls) if cls else dec

def factory(
    cls=None,
    *,
    name: Any = None,
    qualifiers: Iterable[str] = (),
    scope: str = "singleton",
    primary: bool = False,
    lazy: bool = False,
    conditional_profiles: Iterable[str] = (),
    conditional_require_env: Iterable[str] = (),
    conditional_predicate: Optional[Callable[[], bool]] = None,
    on_missing_selector: Optional[object] = None,
    on_missing_priority: int = 0,
):
    def dec(c):
        setattr(c, PICO_INFRA, "factory")
        setattr(c, PICO_NAME, name if name is not None else getattr(c, "__name__", str(c)))
        m = _meta_get(c)
        m["qualifier"] = tuple(str(q) for q in qualifiers or ())
        m["scope"] = scope
        if primary:
            m["primary"] = True
        if lazy:
            m["lazy"] = True
        if conditional_profiles or conditional_require_env or conditional_predicate is not None:
            m["conditional"] = {
                "profiles": tuple(p for p in conditional_profiles or ()),
                "require_env": tuple(e for e in conditional_require_env or ()),
                "predicate": conditional_predicate,
            }
        if on_missing_selector is not None:
            m["on_missing"] = {"selector": on_missing_selector, "priority": int(on_missing_priority)}
        return c
    return dec(cls) if cls else dec

def provides(
    key: Any,
    *,
    name: Any = None,
    qualifiers: Iterable[str] = (),
    scope: str = "singleton",
    primary: bool = False,
    lazy: bool = False,
    conditional_profiles: Iterable[str] = (),
    conditional_require_env: Iterable[str] = (),
    conditional_predicate: Optional[Callable[[], bool]] = None,
    on_missing_selector: Optional[object] = None,
    on_missing_priority: int = 0,
):
    def dec(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            return fn(*a, **k)
        setattr(w, PICO_INFRA, "provides")
        setattr(w, PICO_NAME, name if name is not None else key)
        setattr(w, PICO_KEY, key)
        m = _meta_get(w)
        m["qualifier"] = tuple(str(q) for q in qualifiers or ())
        m["scope"] = scope
        if primary:
            m["primary"] = True
        if lazy:
            m["lazy"] = True
        if conditional_profiles or conditional_require_env or conditional_predicate is not None:
            m["conditional"] = {
                "profiles": tuple(p for p in conditional_profiles or ()),
                "require_env": tuple(e for e in conditional_require_env or ()),
                "predicate": conditional_predicate,
            }
        if on_missing_selector is not None:
            m["on_missing"] = {"selector": on_missing_selector, "priority": int(on_missing_priority)}
        return w
    return dec

class Qualifier(str):
    __slots__ = ()

def configuration(cls=None, *, prefix: Optional[str] = None):
    def dec(c):
        setattr(c, PICO_INFRA, "configuration")
        m = _meta_get(c)
        if prefix is not None:
            m["config_prefix"] = prefix
        return c
    return dec(cls) if cls else dec

def configure(fn):
    m = _meta_get(fn)
    m["configure"] = True
    return fn

def cleanup(fn):
    m = _meta_get(fn)
    m["cleanup"] = True
    return fn

def configured(target: Any, *, prefix: Optional[str] = None):
    def dec(cls):
        setattr(cls, PICO_INFRA, "configured")
        m = _meta_get(cls)
        m["configured"] = {"target": target, "prefix": prefix}
        return cls
    return dec

def _truthy(s: str) -> bool:
    return s.strip().lower() in {"1", "true", "yes", "on", "y", "t"}

def _coerce(val: Optional[str], t: type) -> Any:
    if val is None:
        return None
    if t is str:
        return val
    if t is int:
        return int(val)
    if t is float:
        return float(val)
    if t is bool:
        return _truthy(val)
    org = get_origin(t)
    if org is Union:
        args = [a for a in get_args(t) if a is not type(None)]
        if not args:
            return None
        return _coerce(val, args[0])
    return val

def _upper_key(name: str) -> str:
    return name.upper()

def _lookup(sources: Tuple[ConfigSource, ...], key: str) -> Optional[str]:
    for src in sources:
        v = src.get(key)
        if v is not None:
            return v
    return None

def _build_settings_instance(cls: type, sources: Tuple[ConfigSource, ...], prefix: Optional[str]) -> Any:
    if not is_dataclass(cls):
        raise ConfigurationError(f"Configuration class {getattr(cls, '__name__', str(cls))} must be a dataclass")
    values: Dict[str, Any] = {}
    for f in fields(cls):
        base_key = _upper_key(f.name)
        keys_to_try = []
        if prefix:
            keys_to_try.append(prefix + base_key)
        keys_to_try.append(base_key)
        raw = None
        for k in keys_to_try:
            raw = _lookup(sources, k)
            if raw is not None:
                break
        if raw is None:
            if f.default is not MISSING or f.default_factory is not MISSING:
                continue
            raise ConfigurationError(f"Missing configuration key: {(prefix or '') + base_key}")
        values[f.name] = _coerce(raw, f.type if isinstance(f.type, type) or get_origin(f.type) else str)
    return cls(**values)

def _extract_list_req(ann: Any):
    def read_qualifier(metas: Iterable[Any]):
        for m in metas:
            if isinstance(m, Qualifier):
                return str(m)
        return None
    origin = get_origin(ann)
    if origin is Annotated:
        args = get_args(ann)
        base = args[0] if args else Any
        metas = args[1:] if len(args) > 1 else ()
        is_list, elem_t, qual = _extract_list_req(base)
        if qual is None:
            qual = read_qualifier(metas)
        return is_list, elem_t, qual
    if origin in (list, List):
        elem = get_args(ann)[0] if get_args(ann) else Any
        if get_origin(elem) is Annotated:
            eargs = get_args(elem)
            ebase = eargs[0] if eargs else Any
            emetas = eargs[1:] if len(eargs) > 1 else ()
            qual = read_qualifier(emetas)
            return True, ebase if isinstance(ebase, type) else Any, qual
        return True, elem if isinstance(elem, type) else Any, None
    return False, None, None

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
        if name.startswith("_") or not callable(val):
            continue
    return True

def _collect_by_type(locator: ComponentLocator, t: type, q: Optional[str]):
    keys = list(locator._metadata.keys())
    out: List[KeyT] = []
    for k in keys:
        md = locator._metadata.get(k)
        if md is None:
            continue
        typ = md.provided_type or md.concrete_class
        if not isinstance(typ, type):
            continue
        ok = False
        try:
            ok = issubclass(typ, t)
        except Exception:
            ok = _implements_protocol(typ, t)
        if ok and (q is None or q in md.qualifiers):
            out.append(k)
    return out

def _find_key_by_name(locator: Optional[ComponentLocator], name: str) -> Optional[KeyT]:
    if not locator:
        return None
    for k, md in locator._metadata.items():
        if md.pico_name == name:
            return k
        typ = md.provided_type or md.concrete_class
        if isinstance(typ, type) and getattr(typ, "__name__", "") == name:
            return k
    return None

def _normalize_callable(obj):
    return getattr(obj, '__func__', obj)

def _get_signature_safe(callable_obj):
    try:
        return inspect.signature(callable_obj)
    except (ValueError, TypeError):
        wrapped = getattr(callable_obj, '__wrapped__', None)
        if wrapped is not None:
            return inspect.signature(wrapped)
        raise

@functools.lru_cache(maxsize=1024)
def _analyze_signature_template(callable_obj):
    callable_obj = _normalize_callable(callable_obj)
    sig = _get_signature_safe(callable_obj)
    plan = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"): continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD): continue
        ann = param.annotation
        is_list, elem_t, qual = _extract_list_req(ann)
        if is_list:
            plan.append(("list", name, (elem_t, qual)))
        else:
            plan.append(("key", name, ann))
    return tuple(plan)

def _compile_argplan(callable_obj, pico):
    template = _analyze_signature_template(callable_obj)
    locator = pico._locator
    items = []
    for kind, name, data in template:
        if kind == "list":
            elem_t, qual = data
            if locator is not None and isinstance(elem_t, type):
                keys = _collect_by_type(locator, elem_t, qual)
                items.append(("list", name, tuple(keys)))
            continue
        ann = data
        if ann is not inspect._empty and isinstance(ann, type):
            key = ann
        elif ann is not inspect._empty and isinstance(ann, str):
            mapped = _find_key_by_name(locator, ann)
            key = mapped if mapped is not None else ann
        else:
            key = name
        items.append(("key", name, key))
    return tuple(items)

def _resolve_args(callable_obj: Callable[..., Any], pico: "PicoContainer") -> Dict[str, Any]:
    plan = _compile_argplan(callable_obj, pico)
    kwargs: Dict[str, Any] = {}
    tracer = pico._tracer
    prev = tracer.override_via("constructor")
    try:
        for kind, name, data in plan:
            if kind == "key":
                tracer.note_param(data if isinstance(data, (str, type)) else name, name)
                kwargs[name] = pico.get(data)
            else:
                vals = [pico.get(k) for k in data]
                kwargs[name] = vals
    finally:
        tracer.restore_via(prev)
    return kwargs

def _needs_async_configure(obj: Any) -> bool:
    for _, m in inspect.getmembers(obj, predicate=inspect.ismethod):
        meta = getattr(m, PICO_META, {})
        if meta.get("configure", False) and inspect.iscoroutinefunction(m):
            return True
    return False

def _iter_configure_methods(obj: Any):
    for _, m in inspect.getmembers(obj, predicate=inspect.ismethod):
        meta = getattr(m, PICO_META, {})
        if meta.get("configure", False):
            yield m

def _build_class(cls: type, pico: "PicoContainer", locator: ComponentLocator) -> Any:
    init = cls.__init__
    if init is object.__init__:
        inst = cls()
    else:
        deps = _resolve_args(init, pico)
        inst = cls(**deps)
    ainit = getattr(inst, "__ainit__", None)
    has_async = (callable(ainit) and inspect.iscoroutinefunction(ainit)) or _needs_async_configure(inst)
    if has_async:
        async def runner():
            if callable(ainit):
                kwargs = {}
                try:
                    kwargs = _resolve_args(ainit, pico)
                except Exception:
                    kwargs = {}
                res = ainit(**kwargs)
                if inspect.isawaitable(res):
                    await res
            for m in _iter_configure_methods(inst):
                args = _resolve_args(m, pico)
                r = m(**args)
                if inspect.isawaitable(r):
                    await r
            return inst
        return runner()
    for m in _iter_configure_methods(inst):
        args = _resolve_args(m, pico)
        m(**args)
    return inst

def _build_method(fn: Callable[..., Any], pico: "PicoContainer", locator: ComponentLocator) -> Any:
    deps = _resolve_args(fn, pico)
    obj = fn(**deps)
    has_async = _needs_async_configure(obj)
    if has_async:
        async def runner():
            for m in _iter_configure_methods(obj):
                args = _resolve_args(m, pico)
                r = m(**args)
                if inspect.isawaitable(r):
                    await r
            return obj
        return runner()
    for m in _iter_configure_methods(obj):
        args = _resolve_args(m, pico)
        m(**args)
    return obj

def _get_return_type(fn: Callable[..., Any]) -> Optional[type]:
    try:
        ra = inspect.signature(fn).return_annotation
    except Exception:
        return None
    if ra is inspect._empty:
        return None
    return ra if isinstance(ra, type) else None

def _scan_package(package) -> Iterable[Any]:
    for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        yield importlib.import_module(name)

def _iter_input_modules(inputs: Union[Any, Iterable[Any]]) -> Iterable[Any]:
    seq = inputs if isinstance(inputs, Iterable) and not inspect.ismodule(inputs) and not isinstance(inputs, str) else [inputs]
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

def _normalize_override_provider(v: Any) -> Tuple[Provider, bool]:
    if isinstance(v, tuple) and len(v) == 2:
        src, lz = v
        if callable(src):
            return (lambda s=src: s()), bool(lz)
        return (lambda s=src: s), bool(lz)
    if callable(v):
        return (lambda f=v: f()), False
    return (lambda inst=v: inst), False

class Registrar:
    def __init__(
        self, 
        factory: ComponentFactory, 
        *, 
        profiles: Tuple[str, ...] = (), 
        environ: Optional[Dict[str, str]] = None, 
        logger: Optional[logging.Logger] = None, 
        config: Tuple[ConfigSource, ...] = (),
        tree_sources: Tuple["TreeSource", ...] = ()
    ) -> None:
        self._factory = factory
        self._profiles = set(p.strip() for p in profiles if p)
        self._environ = environ if environ is not None else os.environ
        self._deferred: List[DeferredProvider] = []
        self._candidates: Dict[KeyT, List[Tuple[bool, Provider, ProviderMetadata]]] = {}
        self._metadata: Dict[KeyT, ProviderMetadata] = {}
        self._indexes: Dict[str, Dict[Any, List[KeyT]]] = {}
        self._on_missing: List[Tuple[int, KeyT, type]] = []
        self._log = logger or LOGGER
        self._config_sources: Tuple[ConfigSource, ...] = tuple(config)
        from .config_runtime import ConfigResolver, TypeAdapterRegistry, ObjectGraphBuilder
        self._resolver = ConfigResolver(tuple(tree_sources))
        self._adapters = TypeAdapterRegistry()
        self._graph = ObjectGraphBuilder(self._resolver, self._adapters)
        
    def locator(self) -> ComponentLocator:
        return ComponentLocator(self._metadata, self._indexes)

    def attach_runtime(self, pico, locator: ComponentLocator) -> None:
        for deferred in self._deferred:
            deferred.attach(pico, locator)
        for key, md in list(self._metadata.items()):
            if md.lazy:
                original = self._factory.get(key)
                def lazy_proxy_provider(_orig=original, _p=pico):
                    return UnifiedComponentProxy(container=_p, object_creator=_orig)
                self._factory.bind(key, lazy_proxy_provider)

    def _queue(self, key: KeyT, provider: Provider, md: ProviderMetadata) -> None:
        lst = self._candidates.setdefault(key, [])
        lst.append((md.primary, provider, md))
        if isinstance(provider, DeferredProvider):
            self._deferred.append(provider)

    def _bind_if_absent(self, key: KeyT, provider: Provider) -> None:
        if not self._factory.has(key):
            self._factory.bind(key, provider)

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
        provider = DeferredProvider(lambda pico, loc, c=cls: _build_class(c, pico, loc))
        qset = set(str(q) for q in getattr(cls, PICO_META, {}).get("qualifier", ()))
        sc = getattr(cls, PICO_META, {}).get("scope", "singleton")
        md = ProviderMetadata(key=key, provided_type=cls, concrete_class=cls, factory_class=None, factory_method=None, qualifiers=qset, primary=bool(getattr(cls, PICO_META, {}).get("primary")), lazy=bool(getattr(cls, PICO_META, {}).get("lazy", False)), infra=getattr(cls, PICO_INFRA, None), pico_name=getattr(cls, PICO_NAME, None), scope=sc)
        self._queue(key, provider, md)

    def _register_factory_class(self, cls: type) -> None:
        if not self._enabled_by_condition(cls):
            return
        for name in dir(cls):
            try:
                real = getattr(cls, name)
            except Exception:
                continue
            if callable(real) and getattr(real, PICO_INFRA, None) == "provides":
                if not self._enabled_by_condition(real):
                    continue
                k = getattr(real, PICO_KEY)
                provider = DeferredProvider(lambda pico, loc, fc=cls, mn=name: _build_method(getattr(_build_class(fc, pico, loc), mn), pico, loc))
                rt = _get_return_type(real)
                qset = set(str(q) for q in getattr(real, PICO_META, {}).get("qualifier", ()))
                sc = getattr(real, PICO_META, {}).get("scope", getattr(cls, PICO_META, {}).get("scope", "singleton"))
                md = ProviderMetadata(key=k, provided_type=rt if isinstance(rt, type) else (k if isinstance(k, type) else None), concrete_class=None, factory_class=cls, factory_method=name, qualifiers=qset, primary=bool(getattr(real, PICO_META, {}).get("primary")), lazy=bool(getattr(real, PICO_META, {}).get("lazy", False)), infra=getattr(cls, PICO_INFRA, None), pico_name=getattr(real, PICO_NAME, None), scope=sc)
                self._queue(k, provider, md)

    def _register_configuration_class(self, cls: type) -> None:
        if not self._enabled_by_condition(cls):
            return
        pref = getattr(cls, PICO_META, {}).get("config_prefix", None)
        if is_dataclass(cls):
            key = cls
            provider = DeferredProvider(lambda pico, loc, c=cls, p=pref, src=self._config_sources: _build_settings_instance(c, src, p))
            md = ProviderMetadata(key=key, provided_type=cls, concrete_class=cls, factory_class=None, factory_method=None, qualifiers=set(), primary=True, lazy=False, infra="configuration", pico_name=getattr(cls, PICO_NAME, None), scope="singleton")
            self._queue(key, provider, md)

    def _register_configured_class(self, cls: type) -> None:
        if not self._enabled_by_condition(cls):
            return
        meta = getattr(cls, PICO_META, {})
        cfg = meta.get("configured", None)
        if not cfg:
            return
        target = cfg.get("target")
        prefix = cfg.get("prefix")
        if not isinstance(target, type):
            return
        provider = DeferredProvider(lambda pico, loc, t=target, p=prefix, g=self._graph: g.build_from_prefix(t, p))
        qset = set(str(q) for q in meta.get("qualifier", ()))
        sc = meta.get("scope", "singleton")
        md = ProviderMetadata(key=target, provided_type=target, concrete_class=None, factory_class=None, factory_method=None, qualifiers=qset, primary=True, lazy=False, infra="configured", pico_name=prefix, scope=sc)
        self._queue(target, provider, md)

    def register_module(self, module: Any) -> None:
        for _, obj in inspect.getmembers(module):
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
                elif infra == "configuration":
                    self._register_configuration_class(obj)
                elif infra == "configured":
                    self._register_configured_class(obj)

    def _prefix_exists(self, md: ProviderMetadata) -> bool:
        if md.infra != "configured":
            return False
        try:
            _ = self._resolver.subtree(md.pico_name)
            return True
        except Exception:
            return False

    def select_and_bind(self) -> None:
        for key, lst in self._candidates.items():
            def rank(item: Tuple[bool, Provider, ProviderMetadata]) -> Tuple[int, int, int]:
                is_present = 1 if self._prefix_exists(item[2]) else 0
                pref = str(item[2].pico_name or "")
                pref_len = len(pref)
                is_primary = 1 if item[0] else 0
                return (is_present, pref_len, is_primary)
            lst_sorted = sorted(lst, key=rank, reverse=True)
            chosen = lst_sorted[0]
            self._bind_if_absent(key, chosen[1])
            self._metadata[key] = chosen[2]

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

    def _iter_param_types(self, callable_obj: Callable[..., Any]) -> Iterable[type]:
        sig = inspect.signature(callable_obj)
        for name, param in sig.parameters.items():
            if name in ("self", "cls"):
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            ann = param.annotation
            is_list, elem_t, _ = _extract_list_req(ann)
            t = elem_t if is_list else (ann if isinstance(ann, type) else None)
            if isinstance(t, type):
                yield t

    def _infer_narrower_scope(self, md: ProviderMetadata) -> Optional[str]:
        if md.concrete_class is not None:
            init = md.concrete_class.__init__
            for t in self._iter_param_types(init):
                dep = self._find_md_for_type(t)
                if dep and dep.scope != "singleton":
                    return dep.scope
        if md.factory_class is not None and md.factory_method is not None:
            fn = getattr(md.factory_class, md.factory_method)
            for t in self._iter_param_types(fn):
                dep = self._find_md_for_type(t)
                if dep and dep.scope != "singleton":
                    return dep.scope
        return None

    def _promote_scopes(self) -> None:
        for k, md in list(self._metadata.items()):
            if md.scope == "singleton":
                ns = self._infer_narrower_scope(md)
                if ns and ns != "singleton":
                    self._metadata[k] = ProviderMetadata(
                        key=md.key,
                        provided_type=md.provided_type,
                        concrete_class=md.concrete_class,
                        factory_class=md.factory_class,
                        factory_method=md.factory_method,
                        qualifiers=md.qualifiers,
                        primary=md.primary,
                        lazy=md.lazy,
                        infra=md.infra,
                        pico_name=md.pico_name,
                        override=md.override,
                        scope=ns
                    )

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

    def _find_md_for_name(self, name: str) -> Optional[KeyT]:
        for k, md in self._metadata.items():
            if md.pico_name == name:
                return k
            t = md.provided_type or md.concrete_class
            if isinstance(t, type) and getattr(t, "__name__", "") == name:
                return k
        return None
        
    def _validate_bindings(self) -> None:
        errors: List[str] = []

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

        def _should_validate(param: inspect.Parameter) -> bool:
            if param.default is not inspect._empty:
                return False
            ann = param.annotation
            origin = get_origin(ann)
            if origin is Union:
                args = get_args(ann)
                if type(None) in args:
                    return False
            return True

        loc = ComponentLocator(self._metadata, self._indexes)

        for k, md in self._metadata.items():
            if md.infra == "configuration":
                continue

            callables_to_check: List[Callable[..., Any]] = []
            loc_name = "unknown"

            if md.concrete_class is not None:
                callables_to_check.append(md.concrete_class.__init__)
                loc_name = "constructor"
            elif md.factory_class is not None and md.factory_method is not None:
                try:
                    fn = getattr(md.factory_class, md.factory_method)
                    callables_to_check.append(fn)
                    loc_name = f"factory {_fmt(md.factory_class)}.{md.factory_method}"
                except AttributeError:
                     errors.append(f"Component '{_fmt(k)}' refers to missing factory method '{md.factory_method}' on class '{_fmt(md.factory_class)}'")
                     continue
            else:
                 if not md.concrete_class and not md.factory_class and md.override:
                     continue


            for callable_obj in callables_to_check:
                try:
                    sig = inspect.signature(callable_obj)
                except (ValueError, TypeError):
                    continue

                for name, param in sig.parameters.items():
                    if name in ("self", "cls"):
                        continue
                    if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                        continue
                    if not _should_validate(param):
                        continue

                    ann = param.annotation
                    is_list, elem_t, qual = _extract_list_req(ann)

                    if is_list:
                        if qual:
                            matching = loc.with_qualifier_any(qual).keys()
                            if not matching and isinstance(elem_t, type) and not _skip_type(elem_t):
                                errors.append(f"{_fmt(k)} ({loc_name}) expects List[{_fmt(elem_t)}] with qualifier '{qual}' but no matching components exist")
                        continue

                    elif isinstance(ann, str):
                        key_found_by_name = self._find_md_for_name(ann)
                        directly_bound = ann in self._metadata or self._factory.has(ann)

                        if not key_found_by_name and not directly_bound:
                            errors.append(f"{_fmt(k)} ({loc_name}) depends on string key '{ann}' which is not bound")
                        continue

                    elif isinstance(ann, type) and not _skip_type(ann):
                        dep_key_found = self._factory.has(ann) or ann in self._metadata
                        if not dep_key_found:
                             assignable_md = self._find_md_for_type(ann)
                             if assignable_md is None:
                                 by_name_key = self._find_md_for_name(getattr(ann, "__name__", ""))
                                 if by_name_key is None:
                                      errors.append(f"{_fmt(k)} ({loc_name}) depends on {_fmt(ann)} which is not bound")
                        continue

                    elif ann is inspect._empty:
                         name_key = name
                         key_found_by_name = self._find_md_for_name(name_key)
                         directly_bound = name_key in self._metadata or self._factory.has(name_key)
                         if not key_found_by_name and not directly_bound:
                              errors.append(f"{_fmt(k)} ({loc_name}) depends on parameter '{name}' with no type hint, and key '{name_key}' is not bound")
                         continue
                         
        if errors:
            raise InvalidBindingError(errors)
            
    def finalize(self, overrides: Optional[Dict[KeyT, Any]]) -> None:
        self.select_and_bind()
        self._promote_scopes()
        self._rebuild_indexes()
        for _, selector, default_cls in sorted(self._on_missing, key=lambda x: -x[0]):
            key = selector
            if key in self._metadata or self._factory.has(key) or _can_be_selected_for(self._metadata, selector):
                continue
            provider = DeferredProvider(lambda pico, loc, c=default_cls: _build_class(c, pico, loc))
            qset = set(str(q) for q in getattr(default_cls, PICO_META, {}).get("qualifier", ()))
            sc = getattr(default_cls, PICO_META, {}).get("scope", "singleton")
            md = ProviderMetadata(
                key=key,
                provided_type=key if isinstance(key, type) else None,
                concrete_class=default_cls,
                factory_class=None,
                factory_method=None,
                qualifiers=qset,
                primary=True,
                lazy=bool(getattr(default_cls, PICO_META, {}).get("lazy", False)),
                infra=getattr(default_cls, PICO_INFRA, None),
                pico_name=getattr(default_cls, PICO_NAME, None),
                override=True,
                scope=sc
            )
            self._bind_if_absent(key, provider)
            self._metadata[key] = md
            if isinstance(provider, DeferredProvider):
                self._deferred.append(provider)
        self._rebuild_indexes()
        self._validate_bindings()

def init(modules: Union[Any, Iterable[Any]], *, profiles: Tuple[str, ...] = (), allowed_profiles: Optional[Iterable[str]] = None, environ: Optional[Dict[str, str]] = None, overrides: Optional[Dict[KeyT, Any]] = None, logger: Optional[logging.Logger] = None, config: Tuple[ConfigSource, ...] = (), custom_scopes: Optional[Dict[str, "ScopeProtocol"]] = None, validate_only: bool = False, container_id: Optional[str] = None, tree_config: Tuple["TreeSource", ...] = (), observers: Optional[List["ContainerObserver"]] = None,) -> PicoContainer:
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
        for n, impl in custom_scopes.items():
            scopes.register_scope(n, impl)
    pico = PicoContainer(
        factory,
        caches,
        scopes,
        container_id=container_id,
        profiles=active,
        observers=observers or [],
    )
    registrar = Registrar(factory, profiles=active, environ=environ, logger=logger, config=config, tree_sources=tree_config)
    for m in _iter_input_modules(modules):
        registrar.register_module(m)
    if overrides:
        for k, v in overrides.items():
            prov, _ = _normalize_override_provider(v)
            factory.bind(k, prov)
    registrar.finalize(overrides)
    if validate_only:
        locator = registrar.locator()
        pico.attach_locator(locator)
        _fail_fast_cycle_check(pico)
        return pico
    locator = registrar.locator()
    registrar.attach_runtime(pico, locator)
    pico.attach_locator(locator)
    _fail_fast_cycle_check(pico)
    return pico

def _dependency_keys_for(key: KeyT, pico: "PicoContainer") -> Tuple[KeyT, ...]:
    loc = pico._locator
    if not loc:
        return ()
    md = loc._metadata.get(key)
    if not md:
        return ()
    if md.concrete_class is not None:
        fn = md.concrete_class.__init__
    elif md.factory_class is not None and md.factory_method is not None:
        fn = getattr(md.factory_class, md.factory_method)
    else:
        return ()
    plan = _compile_argplan(fn, pico)
    deps: List[KeyT] = []
    for kind, _, data in plan:
        if kind == "key":
            deps.append(data)
        else:
            for k in data:
                deps.append(k)
    return tuple(deps)

def _get_signature_static(fn: Callable[..., Any]) -> inspect.Signature:
    return inspect.signature(fn)

def _compile_argplan_static(callable_obj: Callable[..., Any], locator: ComponentLocator) -> Tuple[Tuple[str, str, Any], ...]:
    sig = _get_signature_static(callable_obj)
    items: List[Tuple[str, str, Any]] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        ann = param.annotation
        is_list, elem_t, qual = _extract_list_req(ann)
        if is_list and locator is not None and isinstance(elem_t, type):
            keys = _collect_by_type(locator, elem_t, qual)
            items.append(("list", name, tuple(keys)))
            continue
        if ann is not inspect._empty and isinstance(ann, type):
            key: KeyT = ann
        elif ann is not inspect._empty and isinstance(ann, str):
            mapped = _find_key_by_name(locator, ann)
            key = mapped if mapped is not None else ann
        else:
            key = name
        items.append(("key", name, key))
    return tuple(items)

def _dependency_keys_for_static(md: ProviderMetadata, locator: ComponentLocator) -> Tuple[KeyT, ...]:
    if md.concrete_class is not None:
        fn = md.concrete_class.__init__
    elif md.factory_class is not None and md.factory_method is not None:
        fn = getattr(md.factory_class, md.factory_method)
    else:
        return ()
    plan = _compile_argplan_static(fn, locator)
    deps: List[KeyT] = []
    for kind, _, data in plan:
        if kind == "key":
            deps.append(data)
        else:
            for k in data:
                deps.append(k)
    return tuple(deps)

def _build_resolution_graph(pico: "PicoContainer") -> Dict[KeyT, Tuple[KeyT, ...]]:
    loc = pico._locator
    if not loc:
        return {}
    graph: Dict[KeyT, Tuple[KeyT, ...]] = {}
    for key, md in list(loc._metadata.items()):
        deps = []
        for d in _dependency_keys_for_static(md, loc):
            canon = pico._canonical_key(d)
            deps.append(canon)
        graph[key] = tuple(deps)
    return graph

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
    graph = _build_resolution_graph(pico)
    cyc = _find_cycle(graph)
    if not cyc:
        return
    path = " -> ".join(_format_key(k) for k in cyc)
    raise InvalidBindingError([f"Circular dependency detected: {path}"])

