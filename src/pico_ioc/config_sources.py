"""Tree-based configuration sources.

Provides the :class:`TreeSource` base class and its concrete implementations:
:class:`DictSource`, :class:`JsonTreeSource`, and :class:`YamlTreeSource`.
"""

import json
import os
import re
from typing import Any, Mapping

from .exceptions import ConfigurationError

_PLACEHOLDER = re.compile(r"\$\{(\w+)(?::([^}]*))?\}")


def expand_env(value: Any) -> Any:
    """Resolve ``${VAR}`` and ``${VAR:default}`` placeholders from the
    environment, recursively over strings, mappings and lists.

    An unset variable with no default expands to an empty string. Enables
    the same config file to carry deployment-specific values (secrets,
    URLs) injected at boot without a hand-rolled parser in each app.
    """
    if isinstance(value, str):
        return _PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, Mapping):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


class TreeSource:
    """Base class for tree-structured configuration sources.

    Subclasses must implement :meth:`get_tree` to return a nested mapping.
    """

    def get_tree(self) -> Mapping[str, Any]:
        """Return the configuration tree as a nested mapping.

        Returns:
            A ``Mapping[str, Any]`` representing the full configuration tree.

        Raises:
            NotImplementedError: Always (must be overridden by subclasses).
        """
        raise NotImplementedError


class DictSource(TreeSource):
    """Tree source backed by an in-memory dictionary.

    Args:
        data: The nested configuration mapping.

    Example:
        >>> src = DictSource({"db": {"host": "localhost", "port": 5432}})
        >>> src.get_tree()["db"]["host"]
        'localhost'
    """

    def __init__(self, data: Mapping[str, Any], *, expand_env: bool = False):
        self._data = data
        self._expand = expand_env

    def get_tree(self) -> Mapping[str, Any]:
        return expand_env(self._data) if self._expand else self._data


class JsonTreeSource(TreeSource):
    """Tree source that reads configuration from a JSON file.

    Args:
        path: Filesystem path to the JSON file.

    Raises:
        ConfigurationError: If the file cannot be loaded or parsed.
    """

    def __init__(self, path: str, *, expand_env: bool = False):
        self._path = path
        self._expand = expand_env

    def get_tree(self) -> Mapping[str, Any]:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ConfigurationError(f"Failed to load JSON config: {e}")
        return expand_env(data) if self._expand else data


class YamlTreeSource(TreeSource):
    """Tree source that reads configuration from a YAML file.

    Requires ``PyYAML`` to be installed (``pip install pico-ioc[yaml]``).

    Args:
        path: Filesystem path to the YAML file.
        expand_env: When ``True``, resolve ``${VAR}`` / ``${VAR:default}``
            placeholders from the environment (see :func:`expand_env`).

    Raises:
        ConfigurationError: If PyYAML is not installed, or if the file
            cannot be loaded or parsed.
    """

    def __init__(self, path: str, *, expand_env: bool = False):
        self._path = path
        self._expand = expand_env

    def get_tree(self) -> Mapping[str, Any]:
        try:
            import yaml
        except Exception:
            raise ConfigurationError("PyYAML not installed")
        try:
            with open(self._path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            raise ConfigurationError(f"Failed to load YAML config: {e}")
        return expand_env(data) if self._expand else data
