import pytest
from typing import List, Union, Optional
from dataclasses import dataclass
from pico_ioc.config_registrar import _coerce, ConfigurationManager
from pico_ioc.config_builder import ContextConfig, FlatDictSource
from pico_ioc.exceptions import ConfigurationError
from pico_ioc.factory import ProviderMetadata

def test_coerce_edge_cases():
    assert _coerce(None, int) is None
    assert _coerce("1.5", float) == 1.5
    assert _coerce("true", bool) is True

def test_config_manager_flat_lookup_fail():
    mgr = ConfigurationManager(None)
    assert mgr._lookup_flat("NON_EXISTENT") is None

def test_register_configured_class_validation():
    mgr = ConfigurationManager(None)
    
    assert mgr.register_configured_class(int, enabled=False) is None
    assert mgr.register_configured_class(int, enabled=True) is None
    
    class BadTarget:
        _pico_meta = {"configured": {"target": "not_a_type"}}
        
    assert mgr.register_configured_class(BadTarget, enabled=True) is None

def test_build_flat_not_dataclass():
    mgr = ConfigurationManager(None)
    with pytest.raises(ConfigurationError, match="must be a dataclass"):
        mgr._build_flat_instance(int, prefix="")

def test_prefix_exists_checks():
    mgr = ConfigurationManager(None)
    md = ProviderMetadata(
        key="k", provided_type=int, concrete_class=int, 
        factory_class=None, factory_method=None, qualifiers=set(),
        primary=False, lazy=False, infra="component", pico_name="p", scope="s"
    )
    
    assert mgr.prefix_exists(md) is False
    
    md_bad = ProviderMetadata(
        key="k", provided_type=None, concrete_class=None,
        factory_class=None, factory_method=None, qualifiers=set(),
        primary=False, lazy=False, infra="configured", pico_name="p", scope="s"
    )
    assert mgr.prefix_exists(md_bad) is False
