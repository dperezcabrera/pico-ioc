import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

import pytest

from pico_ioc.config_builder import ContextConfig, EnvSource, FileSource, FlatDictSource, TreeSource, configuration
from pico_ioc.exceptions import ConfigurationError


class MockTreeSource(TreeSource):
    def get_tree(self) -> Mapping[str, Any]:
        return {}

def test_flat_dict_source_basic():
    data = {
        "APP_HOST": "localhost",
        "APP_PORT": 8080,
        "APP_DEBUG": True,
        "APP_SCORE": 99.9,
        "IGNORED_LIST": [1, 2]
    }
    source = FlatDictSource(data, prefix="APP_", case_sensitive=True)

    assert source.get("HOST") == "localhost"
    assert source.get("PORT") == "8080"
    assert source.get("DEBUG") == "True"
    assert source.get("SCORE") == "99.9"
    
    assert source.get("MISSING") is None
    
    source_no_prefix = FlatDictSource(data, prefix="")
    assert source_no_prefix.get("IGNORED_LIST") is None

def test_flat_dict_source_case_insensitive():
    data = {
        "app_host": "localhost",
        "APP_PORT": 8080
    }
    source = FlatDictSource(data, prefix="APP_", case_sensitive=False)

    assert source.get("host") == "localhost" 
    assert source.get("HOST") == "localhost"
    
    assert source.get("port") == "8080"

def test_flat_dict_source_edge_cases():
    source = FlatDictSource({"KEY": "val"}, prefix="")
    
    assert source.get("") is None
    assert source.get(None) is None

    assert source.get("KEY") == "val"

def test_file_source_exception_handling():
    source = FileSource("ruta/que/no/existe/config.json")
    
    assert source.get("cualquier_cosa") is None
    assert source._data == {}

def test_file_source_invalid_json(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{ esto no es json }", encoding="utf-8")
    
    source = FileSource(str(f))
    assert source._data == {}

def test_file_source_traversal_and_types(tmp_path):
    data = {
        "section": {
            "key": 123,
            "deep": {
                "val": True
            }
        },
        "list_val": [1, 2, 3]
    }
    f = tmp_path / "config.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    
    source = FileSource(str(f))

    assert source.get("section__key") == "123"
    assert source.get("section__deep__val") == "True"

    assert source.get("section") is None

    assert source.get("list_val") is None

    assert source.get("section__missing") is None

def test_configuration_builder_categorization():
    env_src = EnvSource()
    flat_src = FlatDictSource({})
    tree_src = MockTreeSource()

    config = configuration(env_src, flat_src, tree_src)

    assert isinstance(config, ContextConfig)
    assert env_src in config.flat_sources
    assert flat_src in config.flat_sources
    assert tree_src in config.tree_sources
    assert len(config.flat_sources) == 2
    assert len(config.tree_sources) == 1

def test_configuration_builder_unknown_type():
    class UnknownSource:
        pass

    with pytest.raises(ConfigurationError) as exc:
        configuration(UnknownSource())
    
    assert "Unknown configuration source type" in str(exc.value)
