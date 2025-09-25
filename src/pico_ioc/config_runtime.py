# src/pico_ioc/config_runtime.py
import json
import os
import re
import hashlib
from dataclasses import is_dataclass, fields
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union, get_args, get_origin, Annotated
from .exceptions import ConfigurationError
from .constants import PICO_META

class Discriminator:
    def __init__(self, name: str):
        self.name = name

class TreeSource:
    def get_tree(self) -> Mapping[str, Any]:
        raise NotImplementedError

class DictSource(TreeSource):
    def __init__(self, data: Mapping[str, Any]):
        self._data = data
    def get_tree(self) -> Mapping[str, Any]:
        return self._data

class JsonTreeSource(TreeSource):
    def __init__(self, path: str):
        self._path = path
    def get_tree(self) -> Mapping[str, Any]:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise ConfigurationError(f"Failed to load JSON config: {e}")

class YamlTreeSource(TreeSource):
    def __init__(self, path: str):
        self._path = path
    def get_tree(self) -> Mapping[str, Any]:
        try:
            import yaml
        except Exception:
            raise ConfigurationError("PyYAML not installed")
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data
        except Exception as e:
            raise ConfigurationError(f"Failed to load YAML config: {e}")

def _deep_merge(a: Any, b: Any) -> Any:
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            if k in out:
                out = dict(out)
                out[k] = _deep_merge(out[k], v)
            else:
                out[k] = v
        return out
    return b

def _walk_path(root: Any, path: str) -> Any:
    cur = root
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise ConfigurationError(f"Invalid ref path: {path}")
    return cur

_env_pat = re.compile(r"\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}")
_ref_pat = re.compile(r"\$\{ref:([A-Za-z0-9_.]+)\}")

def _interpolate_string(s: str, root: Any) -> str:
    def repl_env(m):
        v = os.environ.get(m.group(1))
        if v is None:
            raise ConfigurationError(f"Missing ENV var {m.group(1)}")
        return v
    def repl_ref(m):
        v = _walk_path(root, m.group(1))
        if isinstance(v, (dict, list)):
            raise ConfigurationError("Cannot interpolate non-scalar ref")
        return str(v)
    s = _env_pat.sub(repl_env, s)
    s = _ref_pat.sub(repl_ref, s)
    return s

def _resolve_refs(node: Any, root: Any) -> Any:
    if isinstance(node, dict):
        if "$ref" in node and len(node) == 1:
            return _resolve_refs(_walk_path(root, node["$ref"]), root)
        return {k: _resolve_refs(v, root) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(x, root) for x in node]
    if isinstance(node, str):
        return _interpolate_string(node, root)
    return node

def canonicalize(node: Any) -> bytes:
    return json.dumps(node, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

class ConfigResolver:
    def __init__(self, sources: Tuple[TreeSource, ...]):
        self._sources = tuple(sources)
        self._tree: Optional[Mapping[str, Any]] = None
    def tree(self) -> Mapping[str, Any]:
        if self._tree is None:
            acc: Mapping[str, Any] = {}
            for s in self._sources:
                acc = _deep_merge(acc, s.get_tree())
            acc = _resolve_refs(acc, acc)
            self._tree = acc
        return self._tree
    def subtree(self, prefix: Optional[str]) -> Any:
        t = self.tree()
        if not prefix:
            return t
        cur = t
        for part in prefix.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                raise ConfigurationError(f"Missing config prefix: {prefix}")
        return cur

class TypeAdapterRegistry:
    def __init__(self):
        self._adapters: Dict[type, Any] = {}
    def register(self, t: type, fn):
        self._adapters[t] = fn
    def get(self, t: type):
        return self._adapters.get(t)

class ObjectGraphBuilder:
    def __init__(self, resolver: ConfigResolver, registry: TypeAdapterRegistry):
        self._resolver = resolver
        self._registry = registry
    def build_from_prefix(self, target_type: type, prefix: Optional[str]) -> Any:
        node = self._resolver.subtree(prefix)
        inst = self._build(node, target_type, ("$root" if not prefix else prefix,))
        try:
            h = hashlib.sha256(canonicalize(node)).hexdigest()
            m = getattr(inst, PICO_META, None)
            if m is None:
                setattr(inst, PICO_META, {"config_hash": h, "config_prefix": prefix, "config_source_order": tuple(type(s).__name__ for s in self._resolver._sources)})
            else:
                m.update({"config_hash": h, "config_prefix": prefix, "config_source_order": tuple(type(s).__name__ for s in self._resolver._sources)})
        except Exception:
            pass
        return inst
    def _build(self, node: Any, t: Any, path: Tuple[str, ...]) -> Any:
        if t is Any or t is object:
            return node
        adapter = self._registry.get(t) if isinstance(t, type) else None
        if adapter:
            return adapter(node)
        org = get_origin(t)
        if org is Annotated:
            base, meta = self._split_annotated(t)
            return self._build_discriminated(node, base, meta, path)
        if org in (list, List):
            elem_t = get_args(t)[0] if get_args(t) else Any
            if not isinstance(node, list):
                raise ConfigurationError(f"Expected list at {'.'.join(path)}")
            return [self._build(x, elem_t, path + (str(i),)) for i, x in enumerate(node)]
        if org in (dict, Dict, Mapping):
            args = get_args(t)
            kt = args[0] if args else str
            vt = args[1] if len(args) > 1 else Any
            if kt not in (str, Any, object):
                raise ConfigurationError(f"Only dicts with string keys supported at {'.'.join(path)}")
            if not isinstance(node, dict):
                raise ConfigurationError(f"Expected dict at {'.'.join(path)}")
            return {k: self._build(v, vt, path + (k,)) for k, v in node.items()}
        if org is Union:
            args = [a for a in get_args(t)]
            if not isinstance(node, dict):
                for cand in args:
                    try:
                        return self._build(node, cand, path)
                    except Exception:
                        continue
                raise ConfigurationError(f"No union match at {'.'.join(path)}")
            if "$type" in node:
                tn = str(node["$type"])
                for cand in args:
                    if isinstance(cand, type) and getattr(cand, "__name__", "") == tn:
                        cleaned = {k: v for k, v in node.items() if k != "$type"}
                        return self._build(cleaned, cand, path)
                raise ConfigurationError(f"Discriminator $type did not match at {'.'.join(path)}")
            for cand in args:
                try:
                    return self._build(node, cand, path)
                except Exception:
                    continue
            raise ConfigurationError(f"No union match at {'.'.join(path)}")
        if isinstance(t, type) and issubclass(t, Enum):
            if isinstance(node, str):
                try:
                    return t[node]
                except Exception:
                    for e in t:
                        if str(e.value) == node:
                            return e
            raise ConfigurationError(f"Invalid enum at {'.'.join(path)}")
        if isinstance(t, type) and is_dataclass(t):
            if not isinstance(node, dict):
                raise ConfigurationError(f"Expected object at {'.'.join(path)}")
            known = {f.name for f in fields(t)}
            extra = [k for k in node.keys() if k not in known]
            if extra:
                raise ConfigurationError(f"Unknown keys {extra} at {'.'.join(path)}")
            vals: Dict[str, Any] = {}
            for f in fields(t):
                if f.name in node:
                    vals[f.name] = self._build(node[f.name], f.type, path + (f.name,))
                else:
                    continue
            return t(**vals)
        if isinstance(t, type):
            if t in (str, int, float, bool):
                return self._coerce_prim(node, t, path)
            if hasattr(t, "__init__"):
                if not isinstance(node, dict):
                    raise ConfigurationError(f"Expected object for ctor at {'.'.join(path)}")
                kwargs: Dict[str, Any] = {}
                import inspect
                sig = inspect.signature(t.__init__)
                for name, p in sig.parameters.items():
                    if name in ("self", "cls"):
                        continue
                    if name in node:
                        kwargs[name] = self._build(node[name], p.annotation if p.annotation is not inspect._empty else Any, path + (name,))
                return t(**kwargs)
        return node
    def _split_annotated(self, t: Any) -> Tuple[Any, Tuple[Any, ...]]:
        args = get_args(t)
        base = args[0] if args else Any
        metas = tuple(args[1:]) if len(args) > 1 else ()
        return base, metas
    def _build_discriminated(self, node: Any, base: Any, metas: Tuple[Any, ...], path: Tuple[str, ...]) -> Any:
        disc_name = None
        for m in metas:
            if isinstance(m, Discriminator):
                disc_name = m.name
                break
        if disc_name and isinstance(node, dict) and disc_name in node:
            if get_origin(base) is Union:
                tn = str(node[disc_name])
                for cand in get_args(base):
                    if isinstance(cand, type) and getattr(cand, "__name__", "") == tn:
                        cleaned = {k: v for k, v in node.items() if k != disc_name}
                        return self._build(cleaned, cand, path)
                raise ConfigurationError(f"Discriminator {disc_name} did not match at {'.'.join(path)}")
        return self._build(node, base, path)
    def _coerce_prim(self, node: Any, t: type, path: Tuple[str, ...]) -> Any:
        if t is str:
            if isinstance(node, str):
                return node
            return str(node)
        if t is int:
            if isinstance(node, int):
                return node
            if isinstance(node, str) and node.strip().isdigit() or (isinstance(node, str) and node.strip().startswith("-") and node.strip()[1:].isdigit()):
                return int(node)
            raise ConfigurationError(f"Expected int at {'.'.join(path)}")
        if t is float:
            if isinstance(node, (int, float)):
                return float(node)
            if isinstance(node, str):
                try:
                    return float(node)
                except Exception:
                    pass
            raise ConfigurationError(f"Expected float at {'.'.join(path)}")
        if t is bool:
            if isinstance(node, bool):
                return node
            if isinstance(node, str):
                s = node.strip().lower()
                if s in ("1", "true", "yes", "on", "y", "t"):
                    return True
                if s in ("0", "false", "no", "off", "n", "f"):
                    return False
            raise ConfigurationError(f"Expected bool at {'.'.join(path)}")
        return node

