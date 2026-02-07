from typing import Any, Dict, List, Protocol, Union, runtime_checkable

import pytest

from pico_ioc.factory import ProviderMetadata
from pico_ioc.locator import ComponentLocator


class MyService:
    pass


class MyFactory:
    pass


@runtime_checkable
class MyProtocol(Protocol):
    def do_something(self): ...


class ImplementsProto:
    def do_something(self): ...


class NotProto:
    pass


@pytest.fixture
def complex_locator():
    key1 = MyService
    meta1 = ProviderMetadata(
        key=key1,
        provided_type=MyService,
        concrete_class=MyService,
        factory_class=None,
        factory_method=None,
        qualifiers={"fast", "secure"},
        primary=True,
        lazy=False,
        infra="component",
        pico_name="service_a",
        scope="singleton",
    )

    key2 = "string_key"
    meta2 = ProviderMetadata(
        key=key2,
        provided_type=MyFactory,
        concrete_class=MyFactory,
        factory_class=None,
        factory_method="build",
        qualifiers={"slow"},
        primary=False,
        lazy=True,
        infra="factory",
        pico_name="factory_b",
        scope="prototype",
    )

    metadata = {key1: meta1, key2: meta2}

    indexes = {
        "qualifier": {"fast": [key1], "secure": [key1], "slow": [key2]},
        "primary": {True: [key1], False: [key2]},
        "lazy": {False: [key1], True: [key2]},
        "infra": {"component": [key1], "factory": [key2]},
        "pico_name": {"service_a": [key1], "factory_b": [key2]},
    }

    return ComponentLocator(metadata, indexes)


def test_ensure_candidates(complex_locator):
    assert set(complex_locator.keys()) == {MyService, "string_key"}

    sub_locator = complex_locator.primary_only()
    assert set(sub_locator.keys()) == {MyService}


def test_select_index_logic(complex_locator):
    loc = complex_locator.with_qualifier_any("fast", "slow")
    assert len(loc.keys()) == 2


def test_with_index_all_intersection(complex_locator):
    loc = complex_locator.with_index_all("qualifier", "fast", "secure")
    assert list(loc.keys()) == [MyService]

    loc_empty = complex_locator.with_index_all("qualifier", "fast", "slow")
    assert len(loc_empty.keys()) == 0


def test_primary_only(complex_locator):
    loc = complex_locator.primary_only()
    assert list(loc.keys()) == [MyService]


def test_lazy_filter(complex_locator):
    assert list(complex_locator.lazy(True).keys()) == ["string_key"]
    assert list(complex_locator.lazy(False).keys()) == [MyService]


def test_infra_filter(complex_locator):
    assert list(complex_locator.infra("factory").keys()) == ["string_key"]


def test_pico_name_filter(complex_locator):
    assert list(complex_locator.pico_name("service_a").keys()) == [MyService]


def test_by_key_type(complex_locator):
    loc_str = complex_locator.by_key_type(str)
    assert list(loc_str.keys()) == ["string_key"]

    loc_type = complex_locator.by_key_type(type)
    assert list(loc_type.keys()) == [MyService]

    obj_key = object()
    meta = {obj_key: None}
    loc_obj = ComponentLocator(meta, {})

    res = loc_obj.by_key_type(object)
    assert list(res.keys()) == [obj_key]


def test_implements_protocol_check():
    assert ComponentLocator._implements_protocol(ImplementsProto, MyService) is False
    assert ComponentLocator._implements_protocol(ImplementsProto, MyProtocol) is True
    assert ComponentLocator._implements_protocol(NotProto, MyProtocol) is False


def test_collect_by_type_edge_cases():
    metadata = {
        "key1": None,
        "key2": ProviderMetadata(
            key="key2",
            provided_type=None,
            concrete_class=None,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=False,
            lazy=False,
            infra="test",
            pico_name="test",
        ),
        "key3": ProviderMetadata(
            key="key3",
            provided_type=MyService,
            concrete_class=MyService,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=False,
            lazy=False,
            infra="test",
            pico_name="test",
        ),
    }

    loc = ComponentLocator(metadata, {})

    results = loc.collect_by_type(MyService, None)

    assert results == ["key3"]


def test_find_key_by_name_fallback(complex_locator):
    assert complex_locator.find_key_by_name("service_a") == MyService

    found_key = complex_locator.find_key_by_name("MyService")
    assert found_key == MyService

    assert complex_locator.find_key_by_name("NonExistent") is None
