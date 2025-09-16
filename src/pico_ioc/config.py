# src/pico_ioc/config.py
from __future__ import annotations

import os, json, configparser, pathlib
from dataclasses import is_dataclass, fields, MISSING
from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Tuple, Protocol

# ---- Flags & metadata on classes / fields ----
_CONFIG_FLAG = "_pico_is_config_component"
_CONFIG_PREFIX = "_pico_config_prefix"
_FIELD_META = "_pico_config_field_meta"  # dict: name -> FieldSpec

# ---- Source protocol & implementations ----

class ConfigSource(Protocol):
    def get(self, key: str) -> Optional[str]: ...
    def keys(self) -> Iterable[str]: ...

class EnvSource:
    def __init__(self, prefix: str = ""):
        self.prefix = prefix or ""
    def get(self, key: str) -> Optional[str]:
        # try PREFIX+KEY first, then KEY
        v = os.getenv(self.prefix + key)
        if v is not None:
            return v
        return os.getenv(key)
    def keys(self) -> Iterable[str]:
        # best-effort; env keys only (without prefix expansion)
        return os.environ.keys()

class FileSource:
    def __init__(self, path: os.PathLike[str] | str, optional: bool = False):
        self.path = str(path)
        self.optional = bool(optional)
        self._cache: Dict[str, Any] = {}
        self._load_once()

    def _load_once(self):
        p = pathlib.Path(self.path)
        if not p.exists():
            if self.optional:
                self._cache = {}
                return
            raise FileNotFoundError(self.path)
        text = p.read_text(encoding="utf-8")

        # Try in order: JSON, INI, dotenv, YAML (if available)
        # JSON
        try:
            data = json.loads(text)
            self._cache = _flatten_obj(data)
            return
        except Exception:
            pass
        # INI
        try:
            cp = configparser.ConfigParser()
            cp.read_string(text)
            data = {s: dict(cp.items(s)) for s in cp.sections()}
            # also root-level keys under DEFAULT
            data.update(dict(cp.defaults()))
            self._cache = _flatten_obj(data)
            return
        except Exception:
            pass
        # dotenv (simple KEY=VALUE per line)
        try:
            kv = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"): 
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    kv[k.strip()] = _strip_quotes(v.strip())
            self._cache = _flatten_obj(kv)
            if self._cache:
                return
        except Exception:
            pass
        # YAML if available
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text) or {}
            self._cache = _flatten_obj(data)
            return
        except Exception:
            # if everything fails, fallback to empty (optional) or raise
            if self.optional:
                self._cache = {}
                return
            raise ValueError(f"Unrecognized file format: {self.path}")

    def get(self, key: str) -> Optional[str]:
        v = self._cache.get(key)
        return None if v is None else str(v)

    def keys(self) -> Iterable[str]:
        return self._cache.keys()

# ---- Field specs (overrides) ----

class FieldSpec:
    __slots__ = ("sources", "keys", "default", "path_is_dot")
    def __init__(self, *, sources: Tuple[str, ...], keys: Tuple[str, ...], default: Any, path_is_dot: bool):
        self.sources = sources
        self.keys = keys
        self.default = default
        self.path_is_dot = path_is_dot  # true when keys are dotted-paths for structured files

class _ValueSentinel:
    def __getitem__(self, key_default: str | Tuple[str, Any], /):
        if isinstance(key_default, tuple):
            key, default = key_default
        else:
            key, default = key_default, MISSING
        # default sources order env>file unless overridden in Value(...)
        return _ValueFactory(key, default)
Value = _ValueSentinel()

class _ValueFactory:
    def __init__(self, key: str, default: Any):
        self.key = key
        self.default = default
    def __call__(self, *, sources: Tuple[str, ...] = ("env","file")):
        return FieldSpec(sources=tuple(sources), keys=(self.key,), default=self.default, path_is_dot=False)

class _EnvSentinel:
    def __getitem__(self, key_default: str | Tuple[str, Any], /):
        key, default = (key_default if isinstance(key_default, tuple) else (key_default, MISSING))
        return FieldSpec(sources=("env",), keys=(key,), default=default, path_is_dot=False)
Env = _EnvSentinel()

class _FileSentinel:
    def __getitem__(self, key_default: str | Tuple[str, Any], /):
        key, default = (key_default if isinstance(key_default, tuple) else (key_default, MISSING))
        return FieldSpec(sources=("file",), keys=(key,), default=default, path_is_dot=False)
File = _FileSentinel()

class _PathSentinel:
    class _FilePath:
        def __getitem__(self, key_default: str | Tuple[str, Any], /):
            key, default = (key_default if isinstance(key_default, tuple) else (key_default, MISSING))
            return FieldSpec(sources=("file",), keys=(key,), default=default, path_is_dot=True)
    file = _FilePath()
Path = _PathSentinel()

# ---- Class decorator ----

def config_component(*, prefix: str = ""):
    def dec(cls):
        setattr(cls, _CONFIG_FLAG, True)
        setattr(cls, _CONFIG_PREFIX, prefix or "")
        if not hasattr(cls, _FIELD_META):
            setattr(cls, _FIELD_META, {})
        return cls
    return dec

def is_config_component(cls: type) -> bool:
    return bool(getattr(cls, _CONFIG_FLAG, False))

# ---- Registry / resolution ----

class ConfigRegistry:
    """Holds ordered sources and provides typed resolution for @config_component classes."""
    def __init__(self, sources: Sequence[ConfigSource]):
        self.sources = tuple(sources or ())

    def resolve(self, keys: Iterable[str]) -> Optional[str]:
        # try each key across sources in order
        for key in keys:
            for src in self.sources:
                v = src.get(key)
                if v is not None:
                    return v
        return None

def register_field_spec(cls: type, name: str, spec: FieldSpec) -> None:
    meta: Dict[str, FieldSpec] = getattr(cls, _FIELD_META, None) or {}
    meta[name] = spec
    setattr(cls, _FIELD_META, meta)

def build_component_instance(cls: type, registry: ConfigRegistry) -> Any:
    prefix = getattr(cls, _CONFIG_PREFIX, "")
    overrides: Dict[str, FieldSpec] = getattr(cls, _FIELD_META, {}) or {}

    if is_dataclass(cls):
        kwargs = {}
        for f in fields(cls):
            name = f.name
            spec = overrides.get(name)
            if spec:
                val = _resolve_with_spec(spec, registry)
            else:
                # auto: PREFIX+NAME or NAME (env), NAME (file)
                val = registry.resolve((prefix + name.upper(), name.upper()))
                if val is None and f.default is not MISSING:
                    val = f.default
                elif val is None and f.default_factory is not MISSING:  # type: ignore
                    val = f.default_factory()  # type: ignore
            if val is None and f.default is MISSING and getattr(f, "default_factory", MISSING) is MISSING:  # type: ignore
                raise NameError(f"Missing config for field {cls.__name__}.{name}")
            kwargs[name] = _coerce_type(val, f.type)
        return cls(**kwargs)

    # Non-dataclass: inspect __init__ signature
    import inspect
    sig = inspect.signature(cls.__init__)
    hints = _get_type_hints_safe(cls.__init__, owner=cls)
    kwargs = {}
    for pname, par in sig.parameters.items():
        if pname == "self" or par.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        ann = hints.get(pname, par.annotation)
        spec = overrides.get(pname)
        if spec:
            val = _resolve_with_spec(spec, registry)
        else:
            val = registry.resolve((prefix + pname.upper(), pname.upper()))
            if val is None and par.default is not inspect._empty:
                val = par.default
        if val is None and par.default is inspect._empty:
            raise NameError(f"Missing config for field {cls.__name__}.{pname}")
        kwargs[pname] = _coerce_type(val, ann)
    return cls(**kwargs)

# ---- helpers ----

def _resolve_with_spec(spec: FieldSpec, registry: ConfigRegistry) -> Any:
    # respect spec.sources ordering, but try all keys for each source
    for src_kind in spec.sources:
        if src_kind == "env":
            v = _resolve_from_sources(registry, spec.keys, predicate=lambda s: isinstance(s, EnvSource))
        elif src_kind == "file":
            if spec.path_is_dot:
                v = _resolve_path_from_files(registry, spec.keys)
            else:
                v = _resolve_from_sources(registry, spec.keys, predicate=lambda s: isinstance(s, FileSource))
        else:
            v = None
        if v is not None:
            return v
    return None if spec.default is MISSING else spec.default

def _resolve_from_sources(registry: ConfigRegistry, keys: Tuple[str, ...], predicate: Callable[[ConfigSource], bool]) -> Optional[str]:
    for key in keys:
        for src in registry.sources:
            if predicate(src):
                v = src.get(key)
                if v is not None:
                    return v
    return None

def _resolve_path_from_files(registry: ConfigRegistry, dotted_keys: Tuple[str, ...]) -> Optional[str]:
    for key in dotted_keys:
        path = key.split(".")
        for src in registry.sources:
            if isinstance(src, FileSource):
                # FileSource caches flattened dict already
                v = src.get(key)
                if v is not None:
                    return v
    return None

def _flatten_obj(obj: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            k2 = (prefix + "." + str(k)) if prefix else str(k)
            out.update(_flatten_obj(v, k2))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            k2 = (prefix + "." + str(i)) if prefix else str(i)
            out.update(_flatten_obj(v, k2))
    else:
        out[prefix] = obj
        if "." in prefix:
            # also expose leaf as KEY without dots if single-segment? no; keep dotted only
            pass
        # also expose top-level KEY without dots when no prefix used:
        if prefix and "." not in prefix:
            out[prefix] = obj
    # Additionally mirror top-level simple keys as UPPERCASE for convenience
    if prefix and "." not in prefix:
        out[prefix.upper()] = obj
    return out

def _strip_quotes(s: str) -> str:
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s

def _coerce_type(val: Any, ann: Any) -> Any:
    if val is None:
        return None
    # strings from sources come as str; coerce to basic types
    try:
        from typing import get_origin, get_args
        origin = get_origin(ann) or ann
        if origin in (int,):
            return int(val)
        if origin in (float,):
            return float(val)
        if origin in (bool,):
            s = str(val).strip().lower()
            if s in ("1","true","yes","y","on"): return True
            if s in ("0","false","no","n","off"): return False
            return bool(val)
    except Exception:
        pass
    return val

def _get_type_hints_safe(fn, owner=None):
    try:
        import inspect
        mod = inspect.getmodule(fn)
        g = getattr(mod, "__dict__", {})
        l = vars(owner) if owner is not None else None
        from typing import get_type_hints
        return get_type_hints(fn, globalns=g, localns=l, include_extras=True)
    except Exception:
        return {}

# ---- Public API helpers to be imported by users ----

__all__ = [
    "config_component", "EnvSource", "FileSource",
    "Env", "File", "Path", "Value",
    "ConfigRegistry", "register_field_spec", "is_config_component",
]

