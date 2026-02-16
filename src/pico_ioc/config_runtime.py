import hashlib
import json
import os
import re
import typing
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Annotated, Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union, get_args, get_origin

from .config_sources import DictSource, JsonTreeSource, TreeSource, YamlTreeSource
from .constants import PICO_META
from .exceptions import ConfigurationError


class Value:
    def __init__(self, value: Any):
        self.value = value


class Discriminator:
    def __init__(self, name: str):
        self.name = name


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
                setattr(
                    inst,
                    PICO_META,
                    {
                        "config_hash": h,
                        "config_prefix": prefix,
                        "config_source_order": tuple(type(s).__name__ for s in self._resolver._sources),
                    },
                )
            else:
                m.update(
                    {
                        "config_hash": h,
                        "config_prefix": prefix,
                        "config_source_order": tuple(type(s).__name__ for s in self._resolver._sources),
                    }
                )
        except Exception:
            pass
        return inst

    def _build(self, node: Any, t: Any, path: Tuple[str, ...]) -> Any:
        if t is Any or t is object:
            return node

        if isinstance(t, type):
            adapter = self._registry.get(t)
            if adapter:
                return adapter(node)

        org = get_origin(t)

        if org is Annotated:
            base, metas = self._split_annotated(t)
            return self._build_discriminated(node, base, metas, path)
        if org in (list, List):
            return self._build_list(node, t, path)
        if org in (dict, Dict, Mapping):
            return self._build_dict(node, t, path)
        if org is Union:
            return self._build_union(node, t, path)
        if isinstance(t, type):
            return self._build_type(node, t, path)
        return node

    def _build_list(self, node: Any, t: Any, path: Tuple[str, ...]) -> list:
        elem_t = get_args(t)[0] if get_args(t) else Any
        if not isinstance(node, list):
            raise ConfigurationError(f"Expected list at {'.'.join(path)}")
        return [self._build(x, elem_t, path + (str(i),)) for i, x in enumerate(node)]

    def _build_dict(self, node: Any, t: Any, path: Tuple[str, ...]) -> dict:
        args = get_args(t)
        kt = args[0] if args else str
        vt = args[1] if len(args) > 1 else Any
        if kt not in (str, Any, object):
            raise ConfigurationError(f"Only dicts with string keys supported at {'.'.join(path)}")
        if not isinstance(node, dict):
            raise ConfigurationError(f"Expected dict at {'.'.join(path)}")
        return {k: self._build(v, vt, path + (k,)) for k, v in node.items()}

    def _build_union(self, node: Any, t: Any, path: Tuple[str, ...]) -> Any:
        args = list(get_args(t))
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

    def _build_type(self, node: Any, t: type, path: Tuple[str, ...]) -> Any:
        if issubclass(t, Enum):
            return self._build_enum(node, t, path)
        if is_dataclass(t):
            return self._build_dataclass(node, t, path)
        if t in (str, int, float, bool):
            return self._coerce_prim(node, t, path)
        if hasattr(t, "__init__"):
            return self._build_constructor(node, t, path)
        return node

    def _build_enum(self, node: Any, t: type, path: Tuple[str, ...]) -> Any:
        if isinstance(node, str):
            try:
                return t[node]
            except Exception:
                for e in t:
                    if str(e.value) == node:
                        return e
        raise ConfigurationError(f"Invalid enum at {'.'.join(path)}")

    def _build_dataclass(self, node: Any, t: type, path: Tuple[str, ...]) -> Any:
        if not isinstance(node, dict):
            raise ConfigurationError(f"Expected object at {'.'.join(path)}")
        known = {f.name for f in fields(t)}
        extra = [k for k in node.keys() if k not in known]
        if extra:
            raise ConfigurationError(f"Unknown keys {extra} at {'.'.join(path)}")
        try:
            dc_hints = typing.get_type_hints(t, include_extras=True)
        except Exception:
            dc_hints = {}
        vals: Dict[str, Any] = {}
        for f in fields(t):
            if f.name in node:
                field_type = dc_hints.get(f.name, f.type)
                vals[f.name] = self._build(node[f.name], field_type, path + (f.name,))
        return t(**vals)

    def _build_constructor(self, node: Any, t: type, path: Tuple[str, ...]) -> Any:
        if not isinstance(node, dict):
            raise ConfigurationError(f"Expected object for ctor at {'.'.join(path)}")
        import inspect

        sig = inspect.signature(t.__init__)
        try:
            init_hints = typing.get_type_hints(t.__init__, include_extras=True)
        except Exception:
            init_hints = {}
        kwargs: Dict[str, Any] = {}
        for name, p in sig.parameters.items():
            if name in ("self", "cls"):
                continue
            if name in node:
                hint = init_hints.get(name, p.annotation)
                kwargs[name] = self._build(node[name], hint if hint is not inspect._empty else Any, path + (name,))
        return t(**kwargs)

    def _split_annotated(self, t: Any) -> Tuple[Any, Tuple[Any, ...]]:
        args = get_args(t)
        base = args[0] if args else Any
        metas = tuple(args[1:]) if len(args) > 1 else ()
        return base, metas

    def _build_discriminated(self, node: Any, base: Any, metas: Tuple[Any, ...], path: Tuple[str, ...]) -> Any:
        disc_name = None
        disc_value = None
        has_value = False

        for m in metas:
            if isinstance(m, Discriminator):
                disc_name = m.name
            if isinstance(m, Value):
                disc_value = m.value
                has_value = True

        tn: Optional[str] = None

        if disc_name and has_value:
            tn = str(disc_value)
        elif disc_name and isinstance(node, dict) and disc_name in node:
            tn = str(node[disc_name])

        if tn is not None and get_origin(base) is Union:
            for cand in get_args(base):
                if isinstance(cand, type) and getattr(cand, "__name__", "") == tn:
                    cleaned_node = {k: v for k, v in node.items() if k != disc_name}

                    if has_value:
                        cleaned_node[disc_name] = tn

                    return self._build(cleaned_node, cand, path)

            raise ConfigurationError(
                f"Discriminator value '{tn}' for field '{disc_name}' "
                f"did not match any type in Union {base} at {'.'.join(path)}"
            )

        if has_value and not disc_name:
            return disc_value

        return self._build(node, base, path)

    def _coerce_prim(self, node: Any, t: type, path: Tuple[str, ...]) -> Any:
        if t is str:
            return node if isinstance(node, str) else str(node)
        if t is int:
            return self._coerce_int(node, path)
        if t is float:
            return self._coerce_float(node, path)
        if t is bool:
            return self._coerce_bool(node, path)
        return node

    def _coerce_int(self, node: Any, path: Tuple[str, ...]) -> int:
        if isinstance(node, int):
            return node
        if isinstance(node, str):
            try:
                return int(node.strip())
            except ValueError:
                pass
        raise ConfigurationError(f"Expected int at {'.'.join(path)}")

    def _coerce_float(self, node: Any, path: Tuple[str, ...]) -> float:
        if isinstance(node, (int, float)):
            return float(node)
        if isinstance(node, str):
            try:
                return float(node)
            except Exception:
                pass
        raise ConfigurationError(f"Expected float at {'.'.join(path)}")

    def _coerce_bool(self, node: Any, path: Tuple[str, ...]) -> bool:
        if isinstance(node, bool):
            return node
        if isinstance(node, str):
            s = node.strip().lower()
            if s in ("1", "true", "yes", "on", "y", "t"):
                return True
            if s in ("0", "false", "no", "off", "n", "f"):
                return False
        raise ConfigurationError(f"Expected bool at {'.'.join(path)}")
