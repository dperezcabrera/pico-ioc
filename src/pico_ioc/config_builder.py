import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple, Union

from .config_runtime import DictSource, JsonTreeSource, TreeSource, Value, YamlTreeSource
from .exceptions import ConfigurationError


class ConfigSource(Protocol):
    pass


class EnvSource(ConfigSource):
    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    def get(self, key: str) -> Optional[str]:
        return os.environ.get(self.prefix + key)


class FileSource(ConfigSource):
    def __init__(self, path: str, prefix: str = "") -> None:
        self.prefix = prefix
        try:
            with open(path, encoding="utf-8") as f:
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


class FlatDictSource(ConfigSource):
    def __init__(self, data: Mapping[str, Any], prefix: str = "", case_sensitive: bool = True):
        base = dict(data)
        if case_sensitive:
            self._data = {str(k): v for k, v in base.items()}
            self._prefix = prefix
        else:
            self._data = {str(k).upper(): v for k, v in base.items()}
            self._prefix = prefix.upper()
        self._case_sensitive = case_sensitive

    def get(self, key: str) -> Optional[str]:
        if not key:
            return None
        k = f"{self._prefix}{key}" if self._prefix else key
        if not self._case_sensitive:
            k = k.upper()
        v = self._data.get(k)
        if v is None:
            return None
        if isinstance(v, (str, int, float, bool)):
            return str(v)
        return None


@dataclass(frozen=True)
class ContextConfig:
    flat_sources: Tuple[Union[EnvSource, FileSource, FlatDictSource], ...]
    tree_sources: Tuple[TreeSource, ...]
    overrides: Dict[str, Any]


def configuration(*sources: Any, overrides: Optional[Dict[str, Any]] = None) -> ContextConfig:

    flat: List[Union[EnvSource, FileSource, FlatDictSource]] = []
    tree: List[TreeSource] = []

    for src in sources:
        if isinstance(src, (EnvSource, FileSource, FlatDictSource)):
            flat.append(src)
        elif isinstance(src, TreeSource):
            tree.append(src)
        else:
            raise ConfigurationError(f"Unknown configuration source type: {type(src)}")

    return ContextConfig(flat_sources=tuple(flat), tree_sources=tuple(tree), overrides=dict(overrides or {}))
