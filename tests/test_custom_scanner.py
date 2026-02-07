from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

import pytest

from pico_ioc import init
from pico_ioc.factory import DeferredProvider, ProviderMetadata


class PlainService:
    def get_value(self) -> str:
        return "I am a plain service found by custom scanner"


class MagicMarkerScanner:
    def should_scan(self, obj: Any) -> bool:
        return isinstance(obj, type) and getattr(obj, "__name__", "") == "PlainService"

    def scan(self, obj: Any) -> Optional[Tuple[Any, Callable[[], Any], ProviderMetadata]]:
        if not self.should_scan(obj):
            return None

        def builder(pico, loc):
            return obj()

        provider = DeferredProvider(builder)

        metadata = ProviderMetadata(
            key=obj,
            provided_type=obj,
            concrete_class=obj,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="custom_magic",
            pico_name="plain_service",
            scope="singleton",
            dependencies=(),
        )

        return (obj, provider, metadata)


def test_custom_scanner_registration_and_resolution():
    scanner = MagicMarkerScanner()

    container = init(modules=[__name__], custom_scanners=[scanner])

    assert container.has(PlainService)

    instance = container.get(PlainService)
    assert isinstance(instance, PlainService)
    assert instance.get_value() == "I am a plain service found by custom scanner"


def test_custom_scanner_is_ignored_if_not_registered():
    container = init(modules=[__name__])

    assert not container.has(PlainService)

    with pytest.raises(Exception):
        container.get(PlainService)
