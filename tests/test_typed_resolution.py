"""Regression for issue #30: get/aget must infer the component type.

assert_type is a runtime no-op; it fails only under a static checker, so the
isinstance calls are the runnable guard and assert_type pins the static
contract (get(type[T]) -> T, str -> Any).
"""

from typing import Any, assert_type

import pytest

from pico_ioc import component, init


@component
class Widget:
    pass


@component(name="widget-by-name")
class NamedWidget:
    pass


def test_get_infers_component_type():
    container = init(modules=[__name__])
    w = container.get(Widget)
    assert isinstance(w, Widget)
    assert_type(w, Widget)


def test_get_str_key_stays_any():
    container = init(modules=[__name__])
    w = container.get("widget-by-name")
    assert isinstance(w, NamedWidget)
    assert_type(w, Any)


@pytest.mark.asyncio
async def test_aget_infers_component_type():
    container = init(modules=[__name__])
    w = await container.aget(Widget)
    assert isinstance(w, Widget)
    assert_type(w, Widget)
