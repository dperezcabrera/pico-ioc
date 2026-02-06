from dataclasses import is_dataclass, fields, MISSING
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, get_args, get_origin, Annotated
from .constants import PICO_META, SCOPE_SINGLETON
from .exceptions import ConfigurationError
from .factory import ProviderMetadata, DeferredProvider
from .config_builder import ContextConfig, ConfigSource, FlatDictSource, Value
from .config_runtime import ConfigResolver, TypeAdapterRegistry, ObjectGraphBuilder, TreeSource
from .analysis import analyze_callable_dependencies

KeyT = Union[str, type]
Provider = Callable[[], Any]

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

class ConfigurationManager:
    def __init__(self, config: Optional[ContextConfig]) -> None:
        cfg = config or ContextConfig(flat_sources=(), tree_sources=(), overrides={})
        
        self._flat_config = cfg.flat_sources
        self._overrides = cfg.overrides
        
        self._resolver = ConfigResolver(cfg.tree_sources)
        self._adapters = TypeAdapterRegistry()
        self._graph = ObjectGraphBuilder(self._resolver, self._adapters)

    def _lookup_flat(self, key: str) -> Optional[str]:
        if key in self._overrides:
            return str(self._overrides[key])
        for src in self._flat_config:
            v = src.get(key)
            if v is not None:
                return v
        return None

    def _build_flat_instance(self, cls: type, prefix: Optional[str]) -> Any:
        if not is_dataclass(cls):
            raise ConfigurationError(f"Configuration class {getattr(cls, '__name__', str(cls))} must be a dataclass")
        values: Dict[str, Any] = {}
        for f in fields(cls):
            field_type = f.type
            value_override = None
            
            if get_origin(field_type) is Annotated:
                args = get_args(field_type)
                field_type = args[0] if args else Any
                metas = args[1:] if len(args) > 1 else ()
                for m in metas:
                    if isinstance(m, Value):
                        value_override = m.value
                        break
            
            if value_override is not None:
                values[f.name] = value_override
                continue
            
            base_key = _upper_key(f.name)
            keys_to_try = []
            if prefix:
                keys_to_try.append(prefix + base_key)
            keys_to_try.append(base_key)
            
            raw = None
            for k in keys_to_try:
                raw = self._lookup_flat(k)
                if raw is not None:
                    break
                    
            if raw is None:
                if f.default is not MISSING or f.default_factory is not MISSING:
                    continue
                raise ConfigurationError(f"Missing configuration key: {(prefix or '') + base_key}")
            values[f.name] = _coerce(raw, field_type if isinstance(field_type, type) or get_origin(field_type) else str)
        return cls(**values)
    
    def _auto_detect_mapping(self, target_type: type) -> str:
        if not is_dataclass(target_type):
            return "tree"
        
        primitives = (str, int, float, bool)
        for f in fields(target_type):
            t = f.type
            
            if get_origin(t) is Annotated:
                args = get_args(t)
                t = args[0] if args else Any

            origin = get_origin(t)
            
            if origin in (list, List, dict, Dict, Union):
                return "tree"
            if isinstance(t, type) and is_dataclass(t):
                return "tree"

            base_type = t
            is_optional = origin is Union and type(None) in get_args(t)
            if is_optional:
                real_args = [a for a in get_args(t) if a is not type(None)]
                if real_args:
                    base_type = real_args[0]
                else:
                    continue
            
            if isinstance(base_type, type) and base_type not in primitives:
                return "tree"
                
        return "flat"

    def register_configured_class(self, cls: type, enabled: bool) -> Optional[Tuple[KeyT, Provider, ProviderMetadata]]:
        if not enabled:
            return None
        
        meta = getattr(cls, PICO_META, {})
        cfg = meta.get("configured", None)
        if not cfg:
            return None
            
        target = cfg.get("target")
        prefix = cfg.get("prefix")
        mapping = cfg.get("mapping", "auto")
        
        if target == "self":
            target = cls
        
        if not isinstance(target, type):
            return None
            
        if mapping == "auto":
            mapping = self._auto_detect_mapping(target)
            
        graph_builder = self._graph
        qset = set(str(q) for q in meta.get("qualifier", ()))
        sc = meta.get("scope", SCOPE_SINGLETON)
        
        if mapping == "tree":
            provider = DeferredProvider(lambda pico, loc, t=target, p=prefix, g=graph_builder: g.build_from_prefix(t, p))
            deps = ()
            if not is_dataclass(target) and hasattr(target, "__init__"):
                deps = analyze_callable_dependencies(target.__init__)
            md = ProviderMetadata(
                key=target,
                provided_type=target,
                concrete_class=None,
                factory_class=None,
                factory_method=None,
                qualifiers=qset,
                primary=True,
                lazy=bool(meta.get("lazy", False)),
                infra="configured",
                pico_name=prefix,
                scope=sc,
                dependencies=deps
            )
            return (target, provider, md)
            
        elif mapping == "flat":
            if not is_dataclass(target):
                raise ConfigurationError(f"Target class {target.__name__} for flat mapping must be a dataclass")
            
            provider = DeferredProvider(lambda pico, loc, c=target, p=prefix: self._build_flat_instance(c, p))
            md = ProviderMetadata(
                key=target,
                provided_type=target,
                concrete_class=target,
                factory_class=None,
                factory_method=None,
                qualifiers=qset,
                primary=True,
                lazy=bool(meta.get("lazy", False)),
                infra="configured",
                pico_name=prefix,
                scope=sc,
                dependencies=()
            )
            return (target, provider, md)
            
        return None

    def prefix_exists(self, md: ProviderMetadata) -> bool:
        if md.infra != "configured":
            return False
            
        target_type = md.provided_type or md.concrete_class
        if not isinstance(target_type, type):
            return False
            
        meta = getattr(target_type, PICO_META, {})
        cfg = meta.get("configured", {})
        mapping = cfg.get("mapping", "auto")
        
        if mapping == "auto":
            mapping = self._auto_detect_mapping(target_type)
            
        if mapping == "tree":
            try:
                _ = self._resolver.subtree(md.pico_name)
                return True
            except Exception:
                return False
        else:
            if not is_dataclass(target_type):
                return False
            prefix = md.pico_name or ""
            keys = [_upper_key(f.name) for f in fields(target_type)]
            return any(self._lookup_flat(prefix + k) is not None for k in keys)

