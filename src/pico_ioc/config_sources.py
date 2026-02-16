"""Tree-based configuration sources.

Provides the :class:`TreeSource` base class and its concrete implementations:
:class:`DictSource`, :class:`JsonTreeSource`, and :class:`YamlTreeSource`.
"""

import json
from typing import Any, Mapping

from .exceptions import ConfigurationError


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

    def __init__(self, data: Mapping[str, Any]):
        self._data = data

    def get_tree(self) -> Mapping[str, Any]:
        return self._data


class JsonTreeSource(TreeSource):
    """Tree source that reads configuration from a JSON file.

    Args:
        path: Filesystem path to the JSON file.

    Raises:
        ConfigurationError: If the file cannot be loaded or parsed.
    """

    def __init__(self, path: str):
        self._path = path

    def get_tree(self) -> Mapping[str, Any]:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise ConfigurationError(f"Failed to load JSON config: {e}")


class YamlTreeSource(TreeSource):
    """Tree source that reads configuration from a YAML file.

    Requires ``PyYAML`` to be installed (``pip install pico-ioc[yaml]``).

    Args:
        path: Filesystem path to the YAML file.

    Raises:
        ConfigurationError: If PyYAML is not installed, or if the file
            cannot be loaded or parsed.
    """

    def __init__(self, path: str):
        self._path = path

    def get_tree(self) -> Mapping[str, Any]:
        try:
            import yaml
        except Exception:
            raise ConfigurationError("PyYAML not installed")
        try:
            with open(self._path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data
        except Exception as e:
            raise ConfigurationError(f"Failed to load YAML config: {e}")
