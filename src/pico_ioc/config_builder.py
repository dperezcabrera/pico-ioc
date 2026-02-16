"""Configuration builder and source abstractions.

Provides the :func:`configuration` builder that assembles flat and tree-based
configuration sources into an immutable :class:`ContextConfig`, and the
built-in flat source classes :class:`EnvSource`, :class:`FileSource`, and
:class:`FlatDictSource`.
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple, Union

from .config_runtime import DictSource, JsonTreeSource, TreeSource, Value, YamlTreeSource
from .exceptions import ConfigurationError


class ConfigSource(Protocol):
    """Protocol for flat (key-value) configuration sources."""

    pass


class EnvSource(ConfigSource):
    """Configuration source backed by OS environment variables.

    Args:
        prefix: Optional prefix prepended to every key lookup
            (e.g. ``"APP_"`` turns a lookup for ``"HOST"`` into ``"APP_HOST"``).

    Example:
        >>> src = EnvSource(prefix="DB_")
        >>> src.get("HOST")  # reads os.environ["DB_HOST"]
    """
    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    def get(self, key: str) -> Optional[str]:
        return os.environ.get(self.prefix + key)


class FileSource(ConfigSource):
    """Configuration source backed by a JSON file with flat key lookup.

    Keys are resolved by splitting on ``__`` and walking the JSON tree.

    Args:
        path: Path to the JSON file.
        prefix: Optional prefix prepended to every key lookup.
    """

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
    """Configuration source backed by an in-memory dictionary.

    Args:
        data: The key-value mapping.
        prefix: Optional prefix prepended to every key lookup.
        case_sensitive: If ``False``, keys are normalised to upper-case
            for lookup.
    """

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
    """Immutable configuration object passed to :func:`init`.

    Created by the :func:`configuration` builder. Holds all flat and tree
    sources plus optional override values.

    Attributes:
        flat_sources: Flat (key-value) configuration sources.
        tree_sources: Tree-based (nested dict) configuration sources.
        overrides: Manual key-value overrides that take highest precedence.
    """

    flat_sources: Tuple[Union[EnvSource, FileSource, FlatDictSource], ...]
    tree_sources: Tuple[TreeSource, ...]
    overrides: Dict[str, Any]


def configuration(*sources: Any, overrides: Optional[Dict[str, Any]] = None) -> ContextConfig:
    """Build an immutable :class:`ContextConfig` from one or more sources.

    Sources are classified automatically as flat or tree based on their type.

    Args:
        *sources: Configuration source instances (``EnvSource``,
            ``FileSource``, ``FlatDictSource``, ``DictSource``,
            ``JsonTreeSource``, ``YamlTreeSource``).
        overrides: Optional dictionary of key-value overrides that take
            highest precedence over all sources.

    Returns:
        An immutable :class:`ContextConfig` ready to pass to ``init()``.

    Raises:
        ConfigurationError: If an unknown source type is provided.

    Example:
        >>> cfg = configuration(
        ...     EnvSource(prefix="APP_"),
        ...     DictSource({"db": {"host": "localhost"}}),
        ...     overrides={"DEBUG": "true"},
        ... )
    """

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
