import json
from typing import Any, Mapping

from .exceptions import ConfigurationError


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
            with open(self._path, encoding="utf-8") as f:
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
            with open(self._path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data
        except Exception as e:
            raise ConfigurationError(f"Failed to load YAML config: {e}")
