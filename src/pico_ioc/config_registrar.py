import typing
from dataclasses import MISSING, fields, is_dataclass
from typing import Annotated, Any, Callable, Dict, List, Optional, Tuple, Union, get_args, get_origin

from .analysis import analyze_callable_dependencies
from .config_builder import ContextConfig, Value
from .config_runtime import ConfigResolver, ObjectGraphBuilder, TreeSource, TypeAdapterRegistry
from .constants import PICO_META, SCOPE_SINGLETON
from .exceptions import ConfigurationError
from .factory import DeferredProvider, ProviderMetadata

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


class ConfigurationManager:
    def __init__(self, config: Optional[ContextConfig]) -> None:
        cfg = config or ContextConfig(flat_sources=(), tree_sources=(), overrides={})

        self._flat_config = cfg.flat_sources
        self._has_flat = bool(cfg.flat_sources)
        self._has_tree = bool(cfg.tree_sources)
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

    def _resolve_flat_field(self, f, field_type: Any, prefix: Optional[str]) -> Tuple[bool, Any]:
        field_type, override = self._extract_field_override(field_type)
        if override is not None:
            return True, override
        raw = self._lookup_flat_field(f.name, prefix)
        if raw is None:
            if f.default is not MISSING or f.default_factory is not MISSING:
                return False, None
            raise ConfigurationError(f"Missing configuration key: {(prefix or '') + _upper_key(f.name)}")
        return True, _coerce(raw, field_type if isinstance(field_type, type) or get_origin(field_type) else str)

    def _build_flat_instance(self, cls: type, prefix: Optional[str]) -> Any:
        if not is_dataclass(cls):
            raise ConfigurationError(f"Configuration class {getattr(cls, '__name__', str(cls))} must be a dataclass")
        try:
            dc_hints = typing.get_type_hints(cls, include_extras=True)
        except Exception:
            dc_hints = {}
        values: Dict[str, Any] = {}
        for f in fields(cls):
            found, val = self._resolve_flat_field(f, dc_hints.get(f.name, f.type), prefix)
            if found:
                values[f.name] = val
        return cls(**values)

    def _extract_field_override(self, field_type: Any) -> Tuple[Any, Any]:
        if get_origin(field_type) is not Annotated:
            return field_type, None
        args = get_args(field_type)
        base = args[0] if args else Any
        for m in args[1:]:
            if isinstance(m, Value):
                return base, m.value
        return base, None

    def _lookup_flat_field(self, field_name: str, prefix: Optional[str]) -> Optional[str]:
        base_key = _upper_key(field_name)
        if prefix:
            val = self._lookup_flat(prefix + base_key)
            if val is not None:
                return val
        return self._lookup_flat(base_key)

    def _is_tree_type(self, t: Any) -> bool:
        if get_origin(t) is Annotated:
            args = get_args(t)
            t = args[0] if args else Any

        origin = get_origin(t)
        if origin in (list, List, dict, Dict, Union):
            return True
        if isinstance(t, type) and is_dataclass(t):
            return True

        base_type = t
        if origin is Union and type(None) in get_args(t):
            real_args = [a for a in get_args(t) if a is not type(None)]
            base_type = real_args[0] if real_args else None
        if base_type is None:
            return False

        return isinstance(base_type, type) and base_type not in (str, int, float, bool)

    def _auto_detect_mapping(self, target_type: type) -> str:
        if not is_dataclass(target_type):
            return "tree"
        try:
            dc_hints = typing.get_type_hints(target_type, include_extras=True)
        except Exception:
            dc_hints = {}
        for f in fields(target_type):
            if self._is_tree_type(dc_hints.get(f.name, f.type)):
                return "tree"
        return "flat"

    def _validate_mapping_sources(self, mapping: str, original: str, prefix: str, target_name: str) -> None:
        if mapping == "flat" and not self._has_flat and self._has_tree:
            origin = "auto-detected" if original == "auto" else "explicitly set"
            raise ConfigurationError(
                f"@configured(prefix={prefix!r}): mapping='flat' ({origin}) for "
                f"{target_name}, but only tree sources (DictSource, YamlTreeSource) "
                f"are available. Use mapping='tree' or provide a flat source "
                f"(EnvSource, FlatDictSource)."
            )
        if mapping == "tree" and not self._has_tree and self._has_flat:
            origin = "auto-detected" if original == "auto" else "explicitly set"
            raise ConfigurationError(
                f"@configured(prefix={prefix!r}): mapping='tree' ({origin}) for "
                f"{target_name}, but only flat sources (EnvSource, FlatDictSource) "
                f"are available. Use mapping='flat' or provide a tree source "
                f"(DictSource, YamlTreeSource)."
            )

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

        original_mapping = mapping
        if mapping == "auto":
            mapping = self._auto_detect_mapping(target)

        self._validate_mapping_sources(mapping, original_mapping, prefix or "", target.__name__)

        if mapping not in ("tree", "flat"):
            raise ConfigurationError(
                f"@configured(prefix={prefix!r}): unknown mapping {mapping!r} for {target.__name__}. "
                f"Use 'tree', 'flat', or 'auto'."
            )

        if mapping == "flat" and not is_dataclass(target):
            raise ConfigurationError(f"Target class {target.__name__} for flat mapping must be a dataclass")

        qset = set(str(q) for q in meta.get("qualifier", ()))
        sc = meta.get("scope", SCOPE_SINGLETON)

        graph_builder = self._graph
        if mapping == "tree":
            provider = DeferredProvider(
                lambda pico, loc, t=target, p=prefix, g=graph_builder: g.build_from_prefix(t, p)
            )
            concrete = None
            deps = ()
            if not is_dataclass(target) and hasattr(target, "__init__"):
                deps = analyze_callable_dependencies(target.__init__)
        else:
            provider = DeferredProvider(lambda pico, loc, c=target, p=prefix: self._build_flat_instance(c, p))
            concrete = target
            deps = ()

        md = ProviderMetadata(
            key=target,
            provided_type=target,
            concrete_class=concrete,
            factory_class=None,
            factory_method=None,
            qualifiers=qset,
            primary=True,
            lazy=bool(meta.get("lazy", False)),
            infra="configured",
            pico_name=prefix,
            scope=sc,
            dependencies=deps,
        )
        return (target, provider, md)

    def _prefix_exists_tree(self, pico_name: Optional[str]) -> bool:
        try:
            self._resolver.subtree(pico_name)
            return True
        except Exception:
            return False

    def _prefix_exists_flat(self, target_type: type, pico_name: Optional[str]) -> bool:
        if not is_dataclass(target_type):
            return False
        prefix = pico_name or ""
        return any(self._lookup_flat(prefix + _upper_key(f.name)) is not None for f in fields(target_type))

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
            return self._prefix_exists_tree(md.pico_name)
        return self._prefix_exists_flat(target_type, md.pico_name)
