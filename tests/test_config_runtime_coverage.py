import sys
from dataclasses import dataclass
from typing import Dict, List, Union
from unittest.mock import mock_open, patch

import pytest

from pico_ioc.config_runtime import (
    ConfigResolver,
    JsonTreeSource,
    ObjectGraphBuilder,
    TypeAdapterRegistry,
    YamlTreeSource,
    _interpolate_string,
)
from pico_ioc.exceptions import ConfigurationError


def test_yaml_source_missing_dependency():
    with patch.dict(sys.modules, {"yaml": None}):
        with pytest.raises(ConfigurationError, match="PyYAML not installed"):
            YamlTreeSource("config.yml").get_tree()

def test_yaml_source_load_error():
    with patch("builtins.open", side_effect=OSError("Boom")):
        with pytest.raises(ConfigurationError, match="Failed to load YAML"):
            YamlTreeSource("config.yml").get_tree()

def test_json_source_load_error():
    with patch("builtins.open", mock_open(read_data="{bad_json")):
        with pytest.raises(ConfigurationError, match="Failed to load JSON"):
            JsonTreeSource("config.json").get_tree()

def test_interpolate_missing_env():
    with pytest.raises(ConfigurationError, match="Missing ENV var"):
        _interpolate_string("${ENV:NON_EXISTENT_VAR}", {})

def test_interpolate_non_scalar_ref():
    root = {"config": {"nested": "value"}}
    with pytest.raises(ConfigurationError, match="non-scalar ref"):
        _interpolate_string("${ref:config}", root)

def test_object_builder_union_errors():
    resolver = ConfigResolver(())
    registry = TypeAdapterRegistry()
    builder = ObjectGraphBuilder(resolver, registry)
    
    with pytest.raises(ConfigurationError, match="No union match"):
        builder._build(
            {"unknown": 1}, 
            Union[int, float], 
            ("root",)
        )

    with pytest.raises(ConfigurationError, match="Discriminator"):
        node = {"$type": "UnknownClass", "val": 1}
        
        @dataclass
        class A: val: int
        
        @dataclass
        class B: val: int
        
        builder._build(node, Union[A, B], ("root",))

def test_object_builder_prim_errors():
    resolver = ConfigResolver(())
    registry = TypeAdapterRegistry()
    builder = ObjectGraphBuilder(resolver, registry)
    
    with pytest.raises(ConfigurationError, match="Expected int"):
        builder._build("not_int", int, ("root",))
        
    with pytest.raises(ConfigurationError, match="Expected float"):
        builder._build("not_float", float, ("root",))

    with pytest.raises(ConfigurationError, match="Expected bool"):
        builder._build("not_bool", bool, ("root",))
