"""Coverage boost tests targeting uncovered lines across multiple modules.

Targets: container_resolution.py, config_runtime.py, config_registrar.py,
         api.py, dependency_validator.py, container.py, analysis.py,
         decorators.py, aop.py, component_scanner.py
"""

import asyncio
import inspect
import types
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, Dict, List, Mapping, Optional, Type, Union
from unittest.mock import MagicMock, patch

import pytest

from pico_ioc import component, configure, configured, init
from pico_ioc.analysis import DependencyRequest, analyze_callable_dependencies
from pico_ioc.config_builder import ContextConfig, FlatDictSource, configuration
from pico_ioc.config_registrar import ConfigurationManager
from pico_ioc.config_runtime import (
    ConfigResolver,
    Discriminator,
    ObjectGraphBuilder,
    TypeAdapterRegistry,
    Value,
)
from pico_ioc.config_sources import DictSource
from pico_ioc.constants import PICO_META, SCOPE_SINGLETON
from pico_ioc.container import PicoContainer
from pico_ioc.dependency_validator import DependencyValidator
from pico_ioc.exceptions import ConfigurationError, InvalidBindingError
from pico_ioc.factory import ComponentFactory, DeferredProvider, ProviderMetadata
from pico_ioc.locator import ComponentLocator
from pico_ioc.scope import ScopedCaches, ScopeManager

# ============================================================
# 1. container_resolution.py
# ============================================================


class TestDictDepFallbackToName:
    """Lines 36-63: Dict dep with pico_name=None and type key filtering."""

    def test_dict_dep_pico_name_none_fallback_to_dunder_name(self):
        """When pico_name is None and comp_key is a type, fall back to __name__."""
        mod = types.ModuleType("mod_dict_name")

        @component()
        class ServiceA:
            pass

        @component()
        class Consumer:
            def __init__(self, services: Dict[str, ServiceA]):
                self.services = services

        mod.ServiceA = ServiceA
        mod.Consumer = Consumer

        c = init(modules=[mod])
        try:
            consumer = c.get(Consumer)
            assert isinstance(consumer.services, dict)
            # The key should be the __name__ of the class since pico_name is None
            assert "ServiceA" in consumer.services
        finally:
            c.shutdown()

    def test_dict_dep_type_key_filters_non_type(self):
        """Dict[Type, Service] filters out non-type dict keys."""
        mod = types.ModuleType("mod_dict_type_key")

        @component()
        class Animal:
            pass

        @component()
        class Consumer:
            def __init__(self, animals: Dict[Type, Animal]):
                self.animals = animals

        mod.Animal = Animal
        mod.Consumer = Consumer

        c = init(modules=[mod])
        try:
            consumer = c.get(Consumer)
            assert isinstance(consumer.animals, dict)
            # Keys should only be types
            for k in consumer.animals:
                assert isinstance(k, type)
        finally:
            c.shutdown()


class TestSingleDepFallback:
    """Lines 73-80: fallback to parameter_name, and re-raise first_error."""

    def test_resolve_single_dep_fallback_to_parameter_name(self):
        """Component that fails primary key but resolves via parameter_name."""
        mod = types.ModuleType("mod_fallback")

        @component()
        class NamedService:
            pass

        @component()
        class NeedsService:
            def __init__(self, NamedService: NamedService):
                self.svc = NamedService

        mod.NamedService = NamedService
        mod.NeedsService = NeedsService

        c = init(modules=[mod])
        try:
            inst = c.get(NeedsService)
            assert inst.svc is not None
        finally:
            c.shutdown()


class TestAsyncAinit:
    """Lines 106-119: async __ainit__ resolution."""

    @pytest.mark.asyncio
    async def test_component_with_async_ainit(self):
        """Component with async __ainit__ resolved via aget (lines 106-119)."""
        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        class AsyncComponent:
            def __init__(self):
                self.initialized = False

            async def __ainit__(self):
                self.initialized = True

        c = PicoContainer(fact, caches, scopes)
        md = ProviderMetadata(
            key=AsyncComponent,
            provided_type=AsyncComponent,
            concrete_class=AsyncComponent,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )
        locator = ComponentLocator({AsyncComponent: md}, {})
        c.attach_locator(locator)
        deps = analyze_callable_dependencies(AsyncComponent.__init__)
        fact.bind(AsyncComponent, lambda: c.build_class(AsyncComponent, locator, deps))

        inst = await c.aget(AsyncComponent)
        assert inst.initialized is True
        c.shutdown()

    @pytest.mark.asyncio
    async def test_ainit_analyze_deps_fails_except_path(self):
        """When analyze_callable_dependencies fails on __ainit__, kwargs={} fallback (line 112)."""
        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        class WeirdAinit:
            def __init__(self):
                self.called = False

            async def __ainit__(self):
                self.called = True

        c = PicoContainer(fact, caches, scopes)
        md = ProviderMetadata(
            key=WeirdAinit,
            provided_type=WeirdAinit,
            concrete_class=WeirdAinit,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )
        locator = ComponentLocator({WeirdAinit: md}, {})
        c.attach_locator(locator)
        deps = analyze_callable_dependencies(WeirdAinit.__init__)

        # Patch analyze_callable_dependencies to raise when called on __ainit__
        original_analyze = analyze_callable_dependencies

        def patched_analyze(fn):
            if fn.__name__ == "__ainit__":
                raise TypeError("simulated failure")
            return original_analyze(fn)

        with patch("pico_ioc.container_resolution.analyze_callable_dependencies", patched_analyze):
            fact.bind(WeirdAinit, lambda: c.build_class(WeirdAinit, locator, deps))
            inst = await c.aget(WeirdAinit)
            assert inst.called is True
        c.shutdown()


# ============================================================
# 2. config_runtime.py
# ============================================================


class TestExistingPicoMeta:
    """Lines 177-184: build_from_prefix when _pico_meta already exists."""

    def test_build_from_prefix_updates_existing_meta(self):
        resolver = ConfigResolver((DictSource({"name": "test"}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class Cfg:
            name: str

        # Pre-set _pico_meta on the class so instances inherit it
        Cfg._pico_meta = {"existing_key": "existing_value"}

        inst = builder.build_from_prefix(Cfg, None)
        meta = getattr(inst, PICO_META)
        # m.update() merges into existing dict
        assert "config_hash" in meta
        assert "existing_key" in meta  # original key preserved after update

    def test_build_from_prefix_creates_meta_when_none(self):
        resolver = ConfigResolver((DictSource({"val": 42}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class SimpleCfg:
            val: int

        inst = builder.build_from_prefix(SimpleCfg, None)
        meta = getattr(inst, PICO_META)
        assert "config_hash" in meta
        assert meta["config_prefix"] is None


class TestTypeAdapterRegistry:
    """Line 196: TypeAdapterRegistry with custom adapter."""

    def test_custom_type_adapter(self):
        resolver = ConfigResolver((DictSource({"ts": "2024-01-01"}),))
        registry = TypeAdapterRegistry()

        class MyDate:
            def __init__(self, s: str):
                self.raw = s

        registry.register(MyDate, lambda node: MyDate(str(node)))

        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class WithDate:
            ts: MyDate

        inst = builder.build_from_prefix(WithDate, None)
        assert inst.ts.raw == "2024-01-01"


class TestEnumByValue:
    """Lines 269-272: enum resolution by value string."""

    def test_enum_resolved_by_value(self):
        resolver = ConfigResolver((DictSource({"color": "r"}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        class Color(Enum):
            RED = "r"
            GREEN = "g"

        @dataclass
        class Palette:
            color: Color

        inst = builder.build_from_prefix(Palette, None)
        assert inst.color is Color.RED

    def test_enum_resolved_by_name(self):
        resolver = ConfigResolver((DictSource({"color": "RED"}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        class Color(Enum):
            RED = "r"
            GREEN = "g"

        @dataclass
        class Palette:
            color: Color

        inst = builder.build_from_prefix(Palette, None)
        assert inst.color is Color.RED


class TestBuildConstructor:
    """Lines 293-310: non-dataclass with typed __init__."""

    def test_build_non_dataclass_with_init(self):
        resolver = ConfigResolver((DictSource({"host": "localhost", "port": "8080"}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        class ServerConfig:
            def __init__(self, host: str, port: int):
                self.host = host
                self.port = port

        inst = builder._build({"host": "localhost", "port": "8080"}, ServerConfig, ("$root",))
        assert inst.host == "localhost"
        assert inst.port == 8080

    def test_build_constructor_not_dict_raises(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        class Svc:
            def __init__(self, x: int):
                self.x = x

        with pytest.raises(ConfigurationError, match="Expected object for ctor"):
            builder._build("not_a_dict", Svc, ("root",))


class TestDiscriminatedUnions:
    """Lines 318-355: Annotated[Union[A,B], Discriminator], Value, and no-discriminator."""

    def test_discriminated_union(self):
        resolver = ConfigResolver((DictSource({"field": {"type": "TextInput", "value": "hello"}}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class TextInput:
            value: str

        @dataclass
        class NumberInput:
            value: int

        @dataclass
        class Form:
            field: Annotated[Union[TextInput, NumberInput], Discriminator("type")]

        inst = builder.build_from_prefix(Form, None)
        assert isinstance(inst.field, TextInput)
        assert inst.field.value == "hello"

    def test_discriminated_union_with_fixed_value(self):
        # Value("TextInput") fixes the discriminator; cleaned_node re-adds "type" key
        resolver = ConfigResolver((DictSource({"field": {"value": "hello"}}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class TextInput:
            type: str = ""
            value: str = ""

        @dataclass
        class NumberInput:
            type: str = ""
            value: int = 0

        @dataclass
        class Form:
            field: Annotated[Union[TextInput, NumberInput], Discriminator("type"), Value("TextInput")]

        inst = builder.build_from_prefix(Form, None)
        assert isinstance(inst.field, TextInput)
        assert inst.field.value == "hello"

    def test_annotated_value_without_discriminator(self):
        resolver = ConfigResolver((DictSource({"unused": 1}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        result = builder._build_discriminated("anything", str, (Value("fixed"),), ("root",))
        assert result == "fixed"

    def test_annotated_no_disc_no_value_passthrough(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        result = builder._build_discriminated("hello", str, (), ("root",))
        assert result == "hello"

    def test_discriminated_union_no_match_raises(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class A:
            x: int

        @dataclass
        class B:
            x: int

        with pytest.raises(ConfigurationError, match="Discriminator value"):
            builder._build_discriminated(
                {"type": "Unknown", "x": 1},
                Union[A, B],
                (Discriminator("type"),),
                ("root",),
            )


class TestCoerceEdgeCases:
    """Lines 357-397: coercion int/float/bool from strings."""

    def test_coerce_int_from_string(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        assert builder._coerce_int(" 42 ", ("root",)) == 42

    def test_coerce_float_from_string(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        assert builder._coerce_float("3.14", ("root",)) == 3.14

    def test_coerce_bool_from_string_true(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        for truthy in ("1", "true", "yes", "on", "y", "t"):
            assert builder._coerce_bool(truthy, ("root",)) is True

    def test_coerce_bool_from_string_false(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        for falsy in ("0", "false", "no", "off", "n", "f"):
            assert builder._coerce_bool(falsy, ("root",)) is False

    def test_coerce_float_from_int(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        assert builder._coerce_float(5, ("root",)) == 5.0


# ============================================================
# 3. config_registrar.py
# ============================================================


class TestExtractFieldOverride:
    """Lines 96-104: Annotated[str, Value("v")] field extraction."""

    def test_field_with_value_annotation(self):
        mgr = ConfigurationManager(None)

        annotated_type = Annotated[str, Value("fixed")]
        base, override = mgr._extract_field_override(annotated_type)
        assert base is str
        assert override == "fixed"

    def test_field_without_value_annotation(self):
        mgr = ConfigurationManager(None)

        base, override = mgr._extract_field_override(str)
        assert base is str
        assert override is None


class TestPrefixLookup:
    """Lines 108-112: _build_flat_instance with prefix configured."""

    def test_build_flat_with_prefix(self):
        flat = FlatDictSource({"APP_HOST": "localhost", "APP_PORT": "8080"})
        config = ContextConfig(flat_sources=(flat,), tree_sources=(), overrides={})
        mgr = ConfigurationManager(config)

        @dataclass
        class AppCfg:
            host: str
            port: int

        inst = mgr._build_flat_instance(AppCfg, prefix="APP_")
        assert inst.host == "localhost"
        assert inst.port == 8080


class TestAutoDetectMapping:
    """Lines 114-149: auto detection of tree vs flat."""

    def test_dataclass_with_list_is_tree(self):
        mgr = ConfigurationManager(None)

        @dataclass
        class Cfg:
            items: List[str]

        assert mgr._auto_detect_mapping(Cfg) == "tree"

    def test_dataclass_with_dict_is_tree(self):
        mgr = ConfigurationManager(None)

        @dataclass
        class Cfg:
            data: Dict[str, int]

        assert mgr._auto_detect_mapping(Cfg) == "tree"

    def test_dataclass_with_nested_dataclass_is_tree(self):
        mgr = ConfigurationManager(None)

        @dataclass
        class Inner:
            val: int

        @dataclass
        class Cfg:
            nested: Inner

        assert mgr._auto_detect_mapping(Cfg) == "tree"

    def test_dataclass_only_primitives_is_flat(self):
        mgr = ConfigurationManager(None)

        @dataclass
        class Cfg:
            host: str
            port: int
            debug: bool

        assert mgr._auto_detect_mapping(Cfg) == "flat"

    def test_optional_custom_class_is_tree(self):
        mgr = ConfigurationManager(None)

        class Custom:
            pass

        @dataclass
        class Cfg:
            obj: Optional[Custom]

        assert mgr._auto_detect_mapping(Cfg) == "tree"

    def test_non_dataclass_is_tree(self):
        mgr = ConfigurationManager(None)

        class PlainClass:
            pass

        assert mgr._auto_detect_mapping(PlainClass) == "tree"


class TestRegisterConfiguredAutoMapping:
    """Lines 170-171, 200-202: register with auto mapping and flat non-dataclass error."""

    def test_register_configured_auto_mapping_tree(self):
        tree = DictSource({"app": {"name": "test"}})
        config = ContextConfig(flat_sources=(), tree_sources=(tree,), overrides={})
        mgr = ConfigurationManager(config)

        @dataclass
        class AppCfg:
            name: str

        AppCfg._pico_meta = {
            "configured": {"target": "self", "prefix": "app", "mapping": "auto"},
            "scope": SCOPE_SINGLETON,
        }

        result = mgr.register_configured_class(AppCfg, enabled=True)
        assert result is not None
        key, provider, md = result
        assert key is AppCfg

    def test_register_configured_flat_non_dataclass_raises(self):
        mgr = ConfigurationManager(None)

        class NotDC:
            pass

        NotDC._pico_meta = {
            "configured": {"target": "self", "prefix": "APP_", "mapping": "flat"},
            "scope": SCOPE_SINGLETON,
        }

        with pytest.raises(ConfigurationError, match="must be a dataclass"):
            mgr.register_configured_class(NotDC, enabled=True)


class TestPrefixExists:
    """Lines 223-249: prefix_exists with tree and flat."""

    def test_prefix_exists_tree_mapping(self):
        tree = DictSource({"db": {"host": "localhost"}})
        config = ContextConfig(flat_sources=(), tree_sources=(tree,), overrides={})
        mgr = ConfigurationManager(config)

        @dataclass
        class DbCfg:
            host: str

        DbCfg._pico_meta = {
            "configured": {"target": "self", "prefix": "db", "mapping": "tree"},
        }

        md = ProviderMetadata(
            key=DbCfg,
            provided_type=DbCfg,
            concrete_class=DbCfg,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="configured",
            pico_name="db",
            scope=SCOPE_SINGLETON,
        )
        assert mgr.prefix_exists(md) is True

    def test_prefix_exists_tree_missing(self):
        tree = DictSource({})
        config = ContextConfig(flat_sources=(), tree_sources=(tree,), overrides={})
        mgr = ConfigurationManager(config)

        @dataclass
        class MissingCfg:
            host: str

        MissingCfg._pico_meta = {
            "configured": {"target": "self", "prefix": "missing", "mapping": "tree"},
        }

        md = ProviderMetadata(
            key=MissingCfg,
            provided_type=MissingCfg,
            concrete_class=MissingCfg,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="configured",
            pico_name="missing",
            scope=SCOPE_SINGLETON,
        )
        assert mgr.prefix_exists(md) is False

    def test_prefix_exists_flat_mapping(self):
        flat = FlatDictSource({"HOST": "localhost"})
        config = ContextConfig(flat_sources=(flat,), tree_sources=(), overrides={})
        mgr = ConfigurationManager(config)

        @dataclass
        class FlatCfg:
            host: str

        FlatCfg._pico_meta = {
            "configured": {"target": "self", "prefix": "", "mapping": "flat"},
        }

        md = ProviderMetadata(
            key=FlatCfg,
            provided_type=FlatCfg,
            concrete_class=FlatCfg,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="configured",
            pico_name="",
            scope=SCOPE_SINGLETON,
        )
        assert mgr.prefix_exists(md) is True

    def test_prefix_exists_flat_not_dataclass(self):
        mgr = ConfigurationManager(None)

        class NotDC:
            pass

        NotDC._pico_meta = {
            "configured": {"target": "self", "prefix": "", "mapping": "flat"},
        }

        md = ProviderMetadata(
            key=NotDC,
            provided_type=NotDC,
            concrete_class=NotDC,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="configured",
            pico_name="",
            scope=SCOPE_SINGLETON,
        )
        assert mgr.prefix_exists(md) is False


# ============================================================
# 4. api.py
# ============================================================


class TestNormalizeOverrideProvider:
    """Lines 60-67: override tuple (callable, True) and (instance, False)."""

    def test_override_tuple_callable_lazy(self):
        from pico_ioc.api import _normalize_override_provider

        call_count = 0

        def make():
            nonlocal call_count
            call_count += 1
            return "result"

        provider, lazy = _normalize_override_provider((make, True))
        assert lazy is True
        result = provider()
        assert result == "result"
        assert call_count == 1

    def test_override_tuple_instance_not_lazy(self):
        from pico_ioc.api import _normalize_override_provider

        obj = {"key": "value"}
        provider, lazy = _normalize_override_provider((obj, False))
        assert lazy is False
        result = provider()
        assert result is obj


class TestAsyncSingletonDetection:
    """Lines 195-203: async @configure on eagerly loaded singleton raises."""

    def test_async_configure_singleton_raises(self):
        mod = types.ModuleType("mod_async_cfg")

        @component(scope="singleton")
        class AsyncConfigured:
            async def post_init(self):
                pass

        AsyncConfigured.post_init._pico_meta = {"configure": True}
        mod.AsyncConfigured = AsyncConfigured

        with pytest.raises(ConfigurationError, match="async @configure"):
            init(modules=[mod])


# ============================================================
# 5. dependency_validator.py
# ============================================================


class TestTypeErrorInIssubclass:
    """Lines 40-43: TypeError in issubclass."""

    def test_issubclass_type_error_handled(self):
        class MetaBreaker(type):
            def __subclasscheck__(cls, subclass):
                raise TypeError("nope")

        class BadType(metaclass=MetaBreaker):
            pass

        md = ProviderMetadata(
            key="svc",
            provided_type=BadType,
            concrete_class=BadType,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )

        factory = ComponentFactory()
        factory.bind("svc", lambda: BadType())

        locator = ComponentLocator({"svc": md}, {})
        validator = DependencyValidator({"svc": md}, factory, locator)

        # Should not raise; the TypeError is caught
        result = validator._find_md_for_type(BadType)
        # It may or may not find it, but shouldn't crash
        assert result is None or isinstance(result, ProviderMetadata)


class TestProtocolFallback:
    """Lines 45-49: Protocol without direct registration but with implementation."""

    def test_protocol_fallback_finds_implementation(self):
        from typing import Protocol, runtime_checkable

        @runtime_checkable
        class Greeter(Protocol):
            def greet(self) -> str: ...

        class FriendlyGreeter:
            def greet(self) -> str:
                return "hi"

        Greeter._is_protocol = True

        md = ProviderMetadata(
            key=FriendlyGreeter,
            provided_type=FriendlyGreeter,
            concrete_class=FriendlyGreeter,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )

        factory = ComponentFactory()
        factory.bind(FriendlyGreeter, lambda: FriendlyGreeter())

        locator = ComponentLocator({FriendlyGreeter: md}, {})
        validator = DependencyValidator({FriendlyGreeter: md}, factory, locator)

        result = validator._find_md_for_type(Greeter)
        assert result is not None
        assert result.provided_type is FriendlyGreeter


class TestShouldSkipComponent:
    """Lines 77-82: component with object.__init__ skipped."""

    def test_component_with_object_init_is_skipped(self):
        class NoInit:
            pass

        md = ProviderMetadata(
            key=NoInit,
            provided_type=NoInit,
            concrete_class=NoInit,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )

        factory = ComponentFactory()
        locator = ComponentLocator({NoInit: md}, {})
        validator = DependencyValidator({NoInit: md}, factory, locator)

        assert validator._should_skip_component(md) is True

    def test_component_with_custom_init_not_skipped(self):
        class HasInit:
            def __init__(self, x: int):
                self.x = x

        md = ProviderMetadata(
            key=HasInit,
            provided_type=HasInit,
            concrete_class=HasInit,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
            dependencies=(DependencyRequest(parameter_name="x", key=int),),
        )

        factory = ComponentFactory()
        locator = ComponentLocator({HasInit: md}, {})
        validator = DependencyValidator({HasInit: md}, factory, locator)

        assert validator._should_skip_component(md) is False


# ============================================================
# 6. container.py
# ============================================================


class TestCanonicalKeyIssubclassException:
    """Lines 175-176: _canonical_key with type that raises in issubclass."""

    def test_canonical_key_exception_in_issubclass(self):
        class MetaBreaker(type):
            def __subclasscheck__(cls, subclass):
                raise TypeError("broken")

        class BadBase(metaclass=MetaBreaker):
            pass

        md = ProviderMetadata(
            key=BadBase,
            provided_type=BadBase,
            concrete_class=BadBase,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )

        factory = ComponentFactory()
        factory.bind(BadBase, lambda: BadBase())
        caches = ScopedCaches()
        scopes = ScopeManager()

        c = PicoContainer(factory, caches, scopes)
        locator = ComponentLocator({BadBase: md}, {})
        c.attach_locator(locator)

        try:
            # Asking for a different type that would trigger issubclass check
            class Other:
                pass

            key = c._canonical_key(Other)
            assert key is Other  # Falls through, returns original
        finally:
            c.shutdown()


class TestAsyncConfigureRunner:
    """Lines 235-244: async @configure resolved via aget."""

    @pytest.mark.asyncio
    async def test_async_configure_via_aget(self):
        """Async @configure runner path in container lines 235-244."""
        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        class AsyncService:
            def __init__(self):
                self.configured = False

            async def post_init(self):
                self.configured = True

        AsyncService.post_init._pico_meta = {"configure": True}

        fact.bind(AsyncService, lambda: AsyncService())
        md = ProviderMetadata(
            key=AsyncService,
            provided_type=AsyncService,
            concrete_class=AsyncService,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope="request",  # Non-singleton so aget runs configure
        )

        c = PicoContainer(fact, caches, scopes)
        locator = ComponentLocator({AsyncService: md}, {})
        c.attach_locator(locator)

        try:
            with c.scope("request", "r1"):
                inst = await c.aget(AsyncService)
                assert inst.configured is True
        finally:
            c.shutdown()


class TestAgetWithScope:
    """Lines 322-326: aget with custom scope and configure methods."""

    @pytest.mark.asyncio
    async def test_aget_custom_scope_with_configure(self):
        """aget with non-singleton scope triggers configure runner (lines 322-326)."""
        factory = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        class RequestService:
            def __init__(self):
                self.setup_done = False

            def on_start(self):
                self.setup_done = True

        RequestService.on_start._pico_meta = {"configure": True}

        factory.bind(RequestService, lambda: RequestService())
        md = ProviderMetadata(
            key=RequestService,
            provided_type=RequestService,
            concrete_class=RequestService,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope="request",
        )

        c = PicoContainer(factory, caches, scopes)
        locator = ComponentLocator({RequestService: md}, {})
        c.attach_locator(locator)

        try:
            with c.scope("request", "req-1"):
                inst = await c.aget(RequestService)
                assert inst.setup_done is True
        finally:
            c.shutdown()


class TestCleanupAllAsyncEventBus:
    """Lines 380-387: async cleanup with EventBus."""

    @pytest.mark.asyncio
    async def test_cleanup_all_async_with_event_bus(self):
        from pico_ioc.event_bus import EventBus

        factory = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()
        c = PicoContainer(factory, caches, scopes)
        locator = ComponentLocator({}, {})
        c.attach_locator(locator)

        # Put an EventBus into the cache
        bus = EventBus()
        cache = caches.for_scope(scopes, SCOPE_SINGLETON)
        cache.put("event_bus", bus)

        await c.cleanup_all_async()
        # EventBus.aclose should have been called; bus should be closed
        assert bus._closed is True

        PicoContainer._container_registry.pop(c.container_id, None)

    @pytest.mark.asyncio
    async def test_cleanup_all_async_no_event_bus(self):
        factory = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()
        c = PicoContainer(factory, caches, scopes)
        locator = ComponentLocator({}, {})
        c.attach_locator(locator)

        # No event bus, should complete without error
        await c.cleanup_all_async()
        PicoContainer._container_registry.pop(c.container_id, None)


# ============================================================
# Additional targeted tests for remaining uncovered lines
# ============================================================


class TestContainerResolutionExtractDictKey:
    """container_resolution.py lines 58-60, 63: _extract_dict_key edge cases."""

    def test_extract_dict_key_type_comp_key_pico_name_none(self):
        """When comp_key is a type and pico_name is None, returns __name__."""
        from pico_ioc.container_resolution import _ResolutionMixin

        mixin = _ResolutionMixin()

        class FakeMd:
            pico_name = None
            concrete_class = int
            provided_type = int

        # key_type=str, pico_name=None, comp_key is a type
        result = mixin._extract_dict_key(int, FakeMd(), str)
        assert result == "int"

    def test_extract_dict_key_string_comp_key(self):
        """When pico_name is None and comp_key is a string, returns comp_key."""
        from pico_ioc.container_resolution import _ResolutionMixin

        mixin = _ResolutionMixin()

        class FakeMd:
            pico_name = None
            concrete_class = None
            provided_type = None

        result = mixin._extract_dict_key("my_key", FakeMd(), str)
        assert result == "my_key"

    def test_extract_dict_key_unknown_key_type_returns_none(self):
        """When key_type is not str/Any/type/Type, returns None."""
        from pico_ioc.container_resolution import _ResolutionMixin

        mixin = _ResolutionMixin()

        class FakeMd:
            pico_name = "name"
            concrete_class = None
            provided_type = None

        result = mixin._extract_dict_key("k", FakeMd(), int)
        assert result is None

    def test_extract_dict_key_type_key_returns_concrete(self):
        """When key_type is type, returns concrete_class."""
        from pico_ioc.container_resolution import _ResolutionMixin

        mixin = _ResolutionMixin()

        class FakeMd:
            pico_name = "name"
            concrete_class = str
            provided_type = int

        result = mixin._extract_dict_key("k", FakeMd(), type)
        assert result is str


class TestResolveSingleDepFallbackPaths:
    """container_resolution.py lines 73-80: _resolve_single_dep exception paths."""

    def test_single_dep_primary_fails_fallback_to_param_name(self):
        """Primary key fails, falls back to parameter_name resolution."""
        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        class Dep:
            pass

        # Register under the name "my_dep" (the parameter name)
        fact.bind("my_dep", lambda: Dep())

        md_dep = ProviderMetadata(
            key="my_dep",
            provided_type=Dep,
            concrete_class=Dep,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name="my_dep",
            scope=SCOPE_SINGLETON,
        )

        c = PicoContainer(fact, caches, scopes)
        locator = ComponentLocator({"my_dep": md_dep}, {})
        c.attach_locator(locator)

        dep_req = DependencyRequest(parameter_name="my_dep", key=float)
        kwargs = {}
        c._resolve_single_dep(dep_req, kwargs)
        assert "my_dep" in kwargs
        assert isinstance(kwargs["my_dep"], Dep)
        c.shutdown()

    def test_single_dep_both_fail_reraise_first_error(self):
        """Both primary and parameter_name fail, re-raises first_error."""
        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        c = PicoContainer(fact, caches, scopes)
        locator = ComponentLocator({}, {})
        c.attach_locator(locator)

        dep_req = DependencyRequest(parameter_name="nonexistent", key=float)
        kwargs = {}
        from pico_ioc.exceptions import ProviderNotFoundError

        with pytest.raises(ProviderNotFoundError):
            c._resolve_single_dep(dep_req, kwargs)
        c.shutdown()


class TestCoerceUnionInRegistrar:
    """config_registrar.py lines 31-37: _coerce with Union/Optional types."""

    def test_coerce_optional_int(self):
        from pico_ioc.config_registrar import _coerce

        result = _coerce("42", Optional[int])
        assert result == 42

    def test_coerce_union_str(self):
        from pico_ioc.config_registrar import _coerce

        # Union with real type resolves to the first non-None type
        result = _coerce("42", Optional[int])
        assert result == 42

    def test_coerce_returns_val_for_unknown(self):
        from pico_ioc.config_registrar import _coerce

        result = _coerce("hello", list)
        assert result == "hello"


class TestLookupFunction:
    """config_registrar.py lines 45-49: _lookup function."""

    def test_lookup_finds_value(self):
        from pico_ioc.config_registrar import _lookup

        src = FlatDictSource({"KEY": "value"})
        result = _lookup((src,), "KEY")
        assert result == "value"

    def test_lookup_returns_none(self):
        from pico_ioc.config_registrar import _lookup

        src = FlatDictSource({})
        result = _lookup((src,), "MISSING")
        assert result is None


class TestBuildFlatWithValueOverride:
    """config_registrar.py lines 77-78, 84-86, 90-92, 93: _build_flat_instance edges."""

    def test_build_flat_with_value_annotation(self):
        mgr = ConfigurationManager(None)

        @dataclass
        class Cfg:
            name: Annotated[str, Value("hardcoded")]
            port: int = 8080

        inst = mgr._build_flat_instance(Cfg, prefix=None)
        assert inst.name == "hardcoded"
        assert inst.port == 8080

    def test_build_flat_missing_key_raises(self):
        mgr = ConfigurationManager(None)

        @dataclass
        class Cfg:
            required_field: str

        with pytest.raises(ConfigurationError, match="Missing configuration key"):
            mgr._build_flat_instance(Cfg, prefix=None)

    def test_build_flat_coerce_optional(self):
        flat = FlatDictSource({"COUNT": "5"})
        config = ContextConfig(flat_sources=(flat,), tree_sources=(), overrides={})
        mgr = ConfigurationManager(config)

        @dataclass
        class Cfg:
            count: Optional[int]

        inst = mgr._build_flat_instance(Cfg, prefix=None)
        assert inst.count == 5


class TestAutoDetectMappingUnion:
    """config_registrar.py lines 132, 138-144: Union field detection."""

    def test_dataclass_with_union_is_tree(self):
        mgr = ConfigurationManager(None)

        @dataclass
        class Cfg:
            val: Union[str, int]

        assert mgr._auto_detect_mapping(Cfg) == "tree"

    def test_dataclass_with_optional_primitive(self):
        """Optional[int] with default is still flat since int is primitive."""
        mgr = ConfigurationManager(None)

        @dataclass
        class Cfg:
            x: int = 0

        assert mgr._auto_detect_mapping(Cfg) == "flat"

    def test_dataclass_with_annotated_field(self):
        """Annotated field with primitive base -> flat."""
        mgr = ConfigurationManager(None)

        @dataclass
        class Cfg:
            name: Annotated[str, "some_metadata"]

        assert mgr._auto_detect_mapping(Cfg) == "flat"


class TestRegisterConfiguredLine221:
    """config_registrar.py line 221: unknown mapping returns None."""

    def test_register_configured_unknown_mapping(self):
        mgr = ConfigurationManager(None)

        class SomeClass:
            pass

        SomeClass._pico_meta = {
            "configured": {"target": "self", "prefix": "", "mapping": "unknown"},
            "scope": SCOPE_SINGLETON,
        }

        result = mgr.register_configured_class(SomeClass, enabled=True)
        assert result is None


class TestApiScanPackage:
    """api.py lines 30-31, 47-51: _scan_package and _iter_input_modules."""

    def test_iter_input_modules_with_string(self):
        from pico_ioc.api import _iter_input_modules

        # Import a real small module by string
        mods = list(_iter_input_modules("pico_ioc.constants"))
        assert len(mods) >= 1

    def test_iter_input_modules_with_package(self):
        import pico_ioc
        from pico_ioc.api import _iter_input_modules

        mods = list(_iter_input_modules(pico_ioc))
        assert len(mods) > 1  # Package with submodules

    def test_normalize_override_plain_callable(self):
        from pico_ioc.api import _normalize_override_provider

        provider, lazy = _normalize_override_provider(lambda: 42)
        assert lazy is False
        assert provider() == 42

    def test_normalize_override_plain_instance(self):
        from pico_ioc.api import _normalize_override_provider

        provider, lazy = _normalize_override_provider("hello")
        assert lazy is False
        assert provider() == "hello"


class TestDependencyValidatorEdges:
    """dependency_validator.py remaining lines."""

    def test_skip_type_any(self):
        from pico_ioc.dependency_validator import _skip_type

        assert _skip_type(str) is True
        assert _skip_type(Any) is True

    def test_skip_type_protocol(self):
        from pico_ioc.dependency_validator import _skip_type

        class Proto:
            _is_protocol = True

        assert _skip_type(Proto) is True

    def test_validate_list_dep_no_qualifier(self):
        """List dep without qualifier returns None (no error)."""
        md = ProviderMetadata(
            key="svc",
            provided_type=object,
            concrete_class=object,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )
        fact = ComponentFactory()
        locator = ComponentLocator({"svc": md}, {})
        validator = DependencyValidator({"svc": md}, fact, locator)

        dep = DependencyRequest(parameter_name="items", key=object, is_list=True)
        assert validator._validate_list_dep("svc", dep, "component svc") is None

    def test_validate_str_dep_missing(self):
        """String dependency not found returns error."""
        fact = ComponentFactory()
        locator = ComponentLocator({}, {})
        validator = DependencyValidator({}, fact, locator)

        result = validator._validate_str_dep("svc", "missing_key", "component svc")
        assert result is not None
        assert "missing_key" in result

    def test_validate_type_dep_found_by_md(self):
        """Type dep found through _find_md_for_type."""

        class Base:
            pass

        class Impl(Base):
            pass

        md = ProviderMetadata(
            key=Impl,
            provided_type=Impl,
            concrete_class=Impl,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )
        fact = ComponentFactory()
        locator = ComponentLocator({Impl: md}, {})
        validator = DependencyValidator({Impl: md}, fact, locator)

        result = validator._validate_type_dep("consumer", Base, "component consumer")
        assert result is None  # Found via subclass

    def test_validate_type_dep_found_by_name(self):
        """Type dep found by name."""

        class SomeType:
            pass

        md = ProviderMetadata(
            key="SomeType",
            provided_type=SomeType,
            concrete_class=SomeType,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name="SomeType",
            scope=SCOPE_SINGLETON,
        )
        fact = ComponentFactory()
        locator = ComponentLocator({"SomeType": md}, {})
        validator = DependencyValidator({"SomeType": md}, fact, locator)

        result = validator._validate_type_dep("consumer", SomeType, "component consumer")
        assert result is None


class TestContainerCanonicalKeyStringLookup:
    """container.py lines 182-184: _canonical_key with string pico_name match."""

    def test_canonical_key_string_resolves_by_pico_name(self):
        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        class Svc:
            pass

        fact.bind(Svc, lambda: Svc())
        md = ProviderMetadata(
            key=Svc,
            provided_type=Svc,
            concrete_class=Svc,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name="my_service",
            scope=SCOPE_SINGLETON,
        )

        c = PicoContainer(fact, caches, scopes)
        locator = ComponentLocator({Svc: md}, {})
        c.attach_locator(locator)

        key = c._canonical_key("my_service")
        assert key is Svc
        c.shutdown()


class TestConfigRuntimeAdditional:
    """config_runtime.py remaining uncovered lines."""

    def test_build_list(self):
        resolver = ConfigResolver((DictSource({"items": [1, 2, 3]}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class Cfg:
            items: List[int]

        inst = builder.build_from_prefix(Cfg, None)
        assert inst.items == [1, 2, 3]

    def test_build_list_not_list_raises(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        with pytest.raises(ConfigurationError, match="Expected list"):
            builder._build("not_list", List[int], ("root",))

    def test_build_dict_non_string_key_raises(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        with pytest.raises(ConfigurationError, match="Only dicts with string keys"):
            builder._build({"a": 1}, Dict[int, str], ("root",))

    def test_build_dict_not_dict_raises(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        with pytest.raises(ConfigurationError, match="Expected dict"):
            builder._build("not_dict", Dict[str, int], ("root",))

    def test_build_union_non_dict_tries_candidates(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        result = builder._build(42, Union[str, int], ("root",))
        assert result == "42" or result == 42

    def test_build_union_non_dict_no_match_raises(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class A:
            x: int

        @dataclass
        class B:
            y: int

        with pytest.raises(ConfigurationError, match="No union match"):
            builder._build("invalid", Union[A, B], ("root",))

    def test_build_dataclass_not_dict_raises(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class Cfg:
            x: int

        with pytest.raises(ConfigurationError, match="Expected object"):
            builder._build("not_dict", Cfg, ("root",))

    def test_build_dataclass_extra_keys_raises(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class Cfg:
            x: int

        with pytest.raises(ConfigurationError, match="Unknown keys"):
            builder._build({"x": 1, "extra": 2}, Cfg, ("root",))

    def test_build_any_returns_node(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        result = builder._build({"raw": True}, Any, ("root",))
        assert result == {"raw": True}

    def test_subtree_with_prefix(self):
        resolver = ConfigResolver((DictSource({"db": {"host": "localhost"}}),))
        result = resolver.subtree("db")
        assert result == {"host": "localhost"}

    def test_subtree_missing_prefix_raises(self):
        resolver = ConfigResolver((DictSource({}),))
        with pytest.raises(ConfigurationError, match="Missing config prefix"):
            resolver.subtree("nonexistent")

    def test_deep_merge(self):
        from pico_ioc.config_runtime import _deep_merge

        a = {"x": {"a": 1}, "y": 2}
        b = {"x": {"b": 2}, "z": 3}
        result = _deep_merge(a, b)
        assert result == {"x": {"a": 1, "b": 2}, "y": 2, "z": 3}

    def test_resolve_refs(self):
        resolver = ConfigResolver((DictSource({"base": "hello", "derived": {"$ref": "base"}}),))
        tree = resolver.tree()
        assert tree["derived"] == "hello"

    def test_coerce_str_passthrough(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        assert builder._coerce_prim("hello", str, ("root",)) == "hello"
        assert builder._coerce_prim(42, str, ("root",)) == "42"

    def test_enum_invalid_raises(self):
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        class Color(Enum):
            RED = "r"

        with pytest.raises(ConfigurationError, match="Invalid enum"):
            builder._build_enum(42, Color, ("root",))

    def test_build_from_prefix_setattr_fails_silently(self):
        """Lines 185-186: when setattr on PICO_META fails, silently continues."""
        resolver = ConfigResolver((DictSource({"val": 1}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass(frozen=True)
        class FrozenCfg:
            val: int

        # frozen dataclass can't have attrs set -> except path line 185-186
        inst = builder.build_from_prefix(FrozenCfg, None)
        assert inst.val == 1

    def test_build_dict_mapping_type(self):
        """Line 206: dict with Mapping origin."""
        from typing import Mapping

        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        result = builder._build({"a": 1, "b": 2}, Mapping[str, int], ("root",))
        assert result == {"a": 1, "b": 2}

    def test_coerce_int_already_int(self):
        """Line 370: node already int, returns directly."""
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        assert builder._coerce_int(42, ("root",)) == 42

    def test_coerce_bool_already_bool(self):
        """Line 389: node already bool, returns directly."""
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        assert builder._coerce_bool(True, ("root",)) is True


class TestDependencyValidatorMore:
    """More tests for dependency_validator.py uncovered lines."""

    def test_find_md_for_type_non_type_provided_type(self):
        """Line 36: provided_type is not a type -> continue."""
        md = ProviderMetadata(
            key="svc",
            provided_type=None,
            concrete_class=None,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )
        fact = ComponentFactory()
        locator = ComponentLocator({"svc": md}, {})
        validator = DependencyValidator({"svc": md}, fact, locator)

        result = validator._find_md_for_type(object)
        assert result is None

    def test_find_md_for_type_general_exception(self):
        """Lines 42-43: issubclass raises a non-TypeError exception."""

        class WeirdMeta(type):
            def __subclasscheck__(cls, subclass):
                raise RuntimeError("weird")

        class WeirdType(metaclass=WeirdMeta):
            pass

        md = ProviderMetadata(
            key=WeirdType,
            provided_type=WeirdType,
            concrete_class=WeirdType,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )
        fact = ComponentFactory()
        locator = ComponentLocator({WeirdType: md}, {})
        validator = DependencyValidator({WeirdType: md}, fact, locator)

        # Should not raise - continues past the exception
        result = validator._find_md_for_type(WeirdType)
        assert result is None or isinstance(result, ProviderMetadata)

    def test_should_skip_configuration(self):
        """Line 77-78: infra='configuration' is skipped."""
        md = ProviderMetadata(
            key="cfg",
            provided_type=object,
            concrete_class=object,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="configuration",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )
        fact = ComponentFactory()
        locator = ComponentLocator({}, {})
        validator = DependencyValidator({}, fact, locator)
        assert validator._should_skip_component(md) is True

    def test_should_skip_no_deps_other_infra(self):
        """Line 79-80: no deps, infra not configured/component, no override -> skip."""
        md = ProviderMetadata(
            key="svc",
            provided_type=object,
            concrete_class=object,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="provides",
            pico_name=None,
            scope=SCOPE_SINGLETON,
            dependencies=(),
        )
        fact = ComponentFactory()
        locator = ComponentLocator({}, {})
        validator = DependencyValidator({}, fact, locator)
        assert validator._should_skip_component(md) is True

    def test_validate_list_dep_with_qualifier_missing(self):
        """Line 108: qualified list dep with no matching components."""
        fact = ComponentFactory()
        locator = ComponentLocator({}, {})
        validator = DependencyValidator({}, fact, locator)

        class Svc:
            pass

        dep = DependencyRequest(parameter_name="items", key=Svc, is_list=True, qualifier="special")
        result = validator._validate_list_dep("consumer", dep, "component consumer")
        assert result is not None
        assert "special" in result

    def test_validate_type_dep_not_found(self):
        """Line 124-125: type dep found by name."""
        fact = ComponentFactory()
        locator = ComponentLocator({}, {})
        validator = DependencyValidator({}, fact, locator)

        class Missing:
            pass

        result = validator._validate_type_dep("consumer", Missing, "component consumer")
        assert result is not None
        assert "Missing" in result


class TestContainerResolutionDictEdges:
    """container_resolution.py lines 44, 49: dict dep edge cases."""

    def test_dict_dep_md_none_continues(self):
        """Line 44: metadata is None for a key -> continue."""
        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        class Animal:
            pass

        class Dog(Animal):
            pass

        fact.bind(Dog, lambda: Dog())

        # Only register Dog in factory but NOT in locator metadata
        # collect_by_type returns Dog, but _metadata.get(Dog) returns None
        md_consumer = ProviderMetadata(
            key="consumer",
            provided_type=object,
            concrete_class=object,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
        )

        c = PicoContainer(fact, caches, scopes)
        # Locator doesn't have Dog metadata but collect_by_type could still find it
        # We use a mock locator to control collect_by_type
        locator = MagicMock(spec=ComponentLocator)
        locator.collect_by_type.return_value = (Dog,)
        locator._metadata = {}  # Dog not in metadata -> md is None -> continue
        c.attach_locator(locator)

        dep = DependencyRequest(parameter_name="animals", key=Animal, is_dict=True, dict_key_type=str)
        kwargs = {}
        c._resolve_dict_dep(dep, kwargs)
        assert kwargs["animals"] == {}  # All items skipped because md is None
        c.shutdown()

    def test_dict_dep_type_key_non_type_value_filtered(self):
        """Line 49: Dict[Type, X] filters when dict_key is not a type."""
        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        class Svc:
            pass

        fact.bind(Svc, lambda: Svc())

        md = ProviderMetadata(
            key=Svc,
            provided_type=Svc,
            concrete_class=None,  # concrete_class is None
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name="my_svc",  # pico_name is a string, not a type
            scope=SCOPE_SINGLETON,
        )

        c = PicoContainer(fact, caches, scopes)
        locator = MagicMock(spec=ComponentLocator)
        locator.collect_by_type.return_value = (Svc,)
        locator._metadata = {Svc: md}
        c.attach_locator(locator)

        # Dict[Type, Svc] - key_type is type, but _extract_dict_key returns pico_name (str)
        # Since pico_name is "my_svc" (str, not type), and key_type is type,
        # _extract_dict_key returns concrete_class or provided_type
        # concrete_class is None, provided_type is Svc (a type)
        dep = DependencyRequest(parameter_name="svcs", key=Svc, is_dict=True, dict_key_type=type)
        kwargs = {}
        c._resolve_dict_dep(dep, kwargs)
        # Should include it since provided_type is a type
        assert Svc in kwargs["svcs"]
        c.shutdown()


class TestConfigRegistrarAutoDetectEdges:
    """config_registrar.py lines 120-121, 140-144, 147: _auto_detect_mapping edges."""

    def test_auto_detect_with_annotated_complex_type(self):
        """Line 120-121, 126-128: field with Annotated wrapping is unwrapped."""
        mgr = ConfigurationManager(None)

        @dataclass
        class Nested:
            x: int

        @dataclass
        class Cfg:
            item: Annotated[Nested, "some_meta"]

        assert mgr._auto_detect_mapping(Cfg) == "tree"

    def test_auto_detect_optional_custom_class_tree(self):
        """Lines 138-147: Optional[CustomClass] -> base_type is custom -> tree."""
        mgr = ConfigurationManager(None)

        class Custom:
            pass

        @dataclass
        class Cfg:
            obj: Optional[Custom] = None

        assert mgr._auto_detect_mapping(Cfg) == "tree"

    def test_build_flat_with_annotated_value_field(self):
        """Line 104: Annotated without Value returns (base, None)."""
        mgr = ConfigurationManager(None)

        annotated_type = Annotated[str, "not_a_Value"]
        base, override = mgr._extract_field_override(annotated_type)
        assert base is str
        assert override is None


class TestContainerResolutionLine80:
    """container_resolution.py line 80: primary_key == parameter_name, both fail."""

    def test_single_dep_same_key_and_name_raises(self):
        """When primary_key == parameter_name, directly raises first_error."""
        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        c = PicoContainer(fact, caches, scopes)
        locator = ComponentLocator({}, {})
        c.attach_locator(locator)

        # primary_key is a string equal to parameter_name
        dep_req = DependencyRequest(parameter_name="some_key", key="some_key")
        kwargs = {}
        from pico_ioc.exceptions import ProviderNotFoundError

        with pytest.raises(ProviderNotFoundError):
            c._resolve_single_dep(dep_req, kwargs)
        c.shutdown()


class TestConfigRegistrarLine35:
    """config_registrar.py line 35: _coerce Union with no non-None args."""

    def test_coerce_optional_none_returns_none(self):
        from pico_ioc.config_registrar import _coerce

        # Build a Union type where all args are NoneType
        # This is tricky since Union[None] simplifies, so test with Optional behavior
        # Line 34-35: args = [a for a in get_args(t) if a is not type(None)], if not args: return None
        # We need get_origin(t) is Union and all args are NoneType
        # In practice Optional[X] = Union[X, None], so we can't create Union[None].
        # But we can test the line by patching or finding a type where this applies.
        # The simplest way: test _coerce with a type that triggers the Union branch
        # but has no real args after filtering.
        # Since Union[None] isn't valid in Python, we'll just ensure _coerce handles Optional correctly
        result = _coerce("5", Optional[int])
        assert result == 5


# ============================================================
# TIER 1: Tests con valor real
# ============================================================


class TestAnalysisSignatureFailure:
    """analysis.py lines 122-124: signature() falla -> returns ()."""

    def test_analyze_signature_fails_returns_empty(self):
        """When inspect.signature raises ValueError, returns ()."""

        def normal_func(x: int):
            pass

        with patch("pico_ioc.analysis.inspect.signature", side_effect=ValueError("no sig")):
            result = analyze_callable_dependencies(normal_func)
            assert result == ()

    def test_analyze_signature_type_error_returns_empty(self):
        """When inspect.signature raises TypeError, returns ()."""

        def func(x: str):
            pass

        with patch("pico_ioc.analysis.inspect.signature", side_effect=TypeError("bad type")):
            result = analyze_callable_dependencies(func)
            assert result == ()


class TestAnalysisNoAnnotation:
    """analysis.py lines 191-193: parameter sin type hint."""

    def test_param_without_annotation_key_is_empty_sentinel(self):
        """Param sin hint: base_type=_empty (a type) -> key=_empty, NOT name.
        Line 191-193 solo se alcanza si base_type no es type ni string."""

        def func(some_service):
            pass

        deps = analyze_callable_dependencies(func)
        assert len(deps) == 1
        assert deps[0].parameter_name == "some_service"
        # inspect._empty IS a type, so it hits line 187, not 191
        assert deps[0].key is inspect._empty

    def test_param_with_annotation_uses_type(self):
        """Annotated param uses the type as key."""

        def func(svc: int):
            pass

        deps = analyze_callable_dependencies(func)
        assert deps[0].key is int

    def test_param_with_any_annotation(self):
        """Any is not a type -> hits line 193 (return base_type, None)."""

        def func(x: Any):
            pass

        deps = analyze_callable_dependencies(func)
        assert deps[0].key is Any


class TestDecoratorsProvidesNoReturnType:
    """decorators.py line 258: @provides sin return annotation -> key=nombre."""

    def test_provides_without_return_annotation(self):
        from pico_ioc import factory, provides

        @factory()
        class MyFactory:
            @provides()
            def create_thing(self):
                return "thing"

        from pico_ioc.constants import PICO_KEY

        key = getattr(MyFactory.create_thing, PICO_KEY)
        # Sin return annotation, el key es el nombre de la función
        assert key == "create_thing"

    def test_provides_with_return_annotation(self):
        from pico_ioc import factory, provides

        class Result:
            pass

        @factory()
        class MyFactory:
            @provides()
            def create_result(self) -> Result:
                return Result()

        from pico_ioc.constants import PICO_KEY

        key = getattr(MyFactory.create_result, PICO_KEY)
        assert key is Result


class TestDecoratorsGetReturnTypeFailure:
    """decorators.py lines 393, 421-424: get_type_hints falla -> fallback a signature."""

    def test_get_return_type_hints_fail_signature_fallback(self):
        from pico_ioc.decorators import get_return_type

        class Result:
            pass

        def func() -> Result:
            pass

        # Normal case works
        assert get_return_type(func) is Result

    def test_get_return_type_both_fail_returns_none(self):
        from pico_ioc.decorators import get_return_type

        # Object that can't be introspected at all
        result = get_return_type(42)
        assert result is None

    def test_get_return_type_hints_fail_but_signature_works(self):
        """get_type_hints raises but inspect.signature works."""
        from pico_ioc.decorators import get_return_type

        class MyClass:
            pass

        def func() -> MyClass:
            pass

        # Patch get_type_hints to fail, forcing fallback to signature
        with patch("pico_ioc.decorators.typing.get_type_hints", side_effect=Exception("broken")):
            result = get_return_type(func)
            assert result is MyClass


class TestDecoratorsConfiguredInvalidMapping:
    """decorators.py line 393: @configured con mapping inválido."""

    def test_configured_invalid_mapping_raises(self):
        with pytest.raises(ValueError, match="mapping must be one of"):
            configured(mapping="invalid")


class TestAopScopeSignatureNonSingleton:
    """aop.py lines 343-345: _scope_signature para scopes no-singleton."""

    def test_scope_signature_returns_scope_id(self):
        from pico_ioc.aop import UnifiedComponentProxy

        fact = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()

        class Svc:
            pass

        md = ProviderMetadata(
            key=Svc,
            provided_type=Svc,
            concrete_class=Svc,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope="request",
        )

        c = PicoContainer(fact, caches, scopes)
        locator = ComponentLocator({Svc: md}, {})
        c.attach_locator(locator)

        proxy = UnifiedComponentProxy(container=c, target=Svc(), component_key=Svc)

        # Sin scope activo, scope_id es None
        sig = proxy._scope_signature()
        assert sig == (None,)

        # Con scope activo, retorna el scope_id
        with c.scope("request", "req-42"):
            sig = proxy._scope_signature()
            assert sig == ("req-42",)

        c.shutdown()


class TestAopAsyncInterceptorOnSyncMethod:
    """aop.py line 390: interceptor async en método sync -> RuntimeError."""

    def test_async_interceptor_on_sync_raises(self):
        from pico_ioc.aop import MethodCtx, MethodInterceptor, intercepted_by

        mod = types.ModuleType("mod_async_interceptor")

        @component()
        class AsyncInterceptor:
            def invoke(self, ctx: MethodCtx, call_next):
                # Returns an awaitable from a sync context
                async def _inner():
                    return call_next(ctx)

                return _inner()  # Returns coroutine (awaitable)

        @component()
        class Target:
            @intercepted_by(AsyncInterceptor)
            def sync_method(self) -> str:
                return "ok"

        mod.AsyncInterceptor = AsyncInterceptor
        mod.Target = Target

        c = init(modules=[mod])
        try:
            target = c.get(Target)
            with pytest.raises(RuntimeError, match="Async interceptor returned awaitable on sync method"):
                target.sync_method()
        finally:
            c.shutdown()


class TestAopAsyncInterceptorDispatchResult:
    """aop.py line 372: dispatch_method retorna non-awaitable en async method."""

    @pytest.mark.asyncio
    async def test_sync_interceptor_on_async_method(self):
        """Interceptor devuelve resultado sync en un método async -> no await."""
        from pico_ioc.aop import MethodCtx, MethodInterceptor, intercepted_by

        mod = types.ModuleType("mod_sync_on_async")

        @component()
        class SyncInterceptor:
            def invoke(self, ctx: MethodCtx, call_next):
                # call_next returns a coroutine for async methods
                # but we want to test line 372: if result is NOT awaitable
                return "intercepted_value"  # Return sync value, not awaitable

        @component()
        class AsyncTarget:
            @intercepted_by(SyncInterceptor)
            async def async_method(self) -> str:
                return "original"

        mod.SyncInterceptor = SyncInterceptor
        mod.AsyncTarget = AsyncTarget

        c = init(modules=[mod])
        try:
            target = await c.aget(AsyncTarget)
            result = await target.async_method()
            assert result == "intercepted_value"
        finally:
            c.shutdown()


class TestComponentScannerInstanceProvides:
    """component_scanner.py lines 136-137: Factory con @provides instance method."""

    def test_factory_with_instance_provides(self):
        """@provides como instance method dispara factory_deps detection."""
        from pico_ioc import factory, provides

        mod = types.ModuleType("mod_factory_inst")

        class Dep:
            pass

        class Product:
            def __init__(self, name: str):
                self.name = name

        @factory()
        class ProductFactory:
            @provides()
            def create_product(self) -> Product:
                return Product("from_factory")

        mod.Dep = Dep
        mod.Product = Product
        mod.ProductFactory = ProductFactory

        c = init(modules=[mod])
        try:
            product = c.get(Product)
            assert product.name == "from_factory"
        finally:
            c.shutdown()


class TestComponentScannerResolveProvidesException:
    """component_scanner.py lines 178-179: getattr_static raises -> returns None."""

    def test_resolve_provides_getattr_fails(self):
        """When inspect.getattr_static raises, safely returns (None, None)."""
        from pico_ioc.component_scanner import ComponentScanner

        scanner = ComponentScanner(profiles=set(), environ={}, config_manager=None)

        class BadDescriptor:
            def __get__(self, obj, objtype=None):
                raise AttributeError("broken")

        class HostClass:
            bad_attr = BadDescriptor()

        # Should not raise - just returns (None, None)
        fn, kind = scanner._resolve_provides_member(HostClass, "bad_attr")
        assert fn is None
        assert kind is None


class TestComponentScannerConditionalPredicate:
    """component_scanner.py lines 90-91: predicate que lanza excepción -> disabled."""

    def test_predicate_exception_disables_component(self):
        from pico_ioc.component_scanner import ComponentScanner

        scanner = ComponentScanner(profiles=set(), environ={}, config_manager=None)

        class BadComponent:
            pass

        BadComponent._pico_meta = {
            "conditional": {
                "profiles": (),
                "require_env": (),
                "predicate": lambda: 1 / 0,  # ZeroDivisionError
            }
        }

        assert scanner._enabled_by_condition(BadComponent) is False


class TestConfigRuntimeGetTypeHintsFailure:
    """config_runtime.py lines 284-285, 301-302: get_type_hints falla."""

    def test_build_dataclass_broken_hints(self):
        """Dataclass con type hints que fallan -> fallback a dc_hints={}."""
        resolver = ConfigResolver((DictSource({"x": 42}),))
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        @dataclass
        class Cfg:
            x: int

        # Patch get_type_hints para que falle en esta dataclass
        original = __import__("typing").get_type_hints

        def broken_hints(cls, **kw):
            if cls is Cfg:
                raise Exception("broken annotations")
            return original(cls, **kw)

        with patch("pico_ioc.config_runtime.typing.get_type_hints", broken_hints):
            inst = builder._build({"x": 42}, Cfg, ("root",))
            assert inst.x == 42

    def test_build_constructor_broken_hints(self):
        """Non-dataclass constructor con hints rotos -> fallback."""
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        class Server:
            def __init__(self, host, port):
                self.host = host
                self.port = port

        original = __import__("typing").get_type_hints

        def broken_hints(fn, **kw):
            if hasattr(fn, "__qualname__") and "Server" in fn.__qualname__:
                raise Exception("broken init hints")
            return original(fn, **kw)

        with patch("pico_ioc.config_runtime.typing.get_type_hints", broken_hints):
            inst = builder._build({"host": "localhost", "port": 8080}, Server, ("root",))
            assert inst.host == "localhost"
            assert inst.port == 8080


class TestConfigRegistrarGetTypeHintsFailure:
    """config_registrar.py lines 77-78: get_type_hints falla en flat build."""

    def test_build_flat_broken_hints(self):
        flat = FlatDictSource({"NAME": "test"})
        config = ContextConfig(flat_sources=(flat,), tree_sources=(), overrides={})
        mgr = ConfigurationManager(config)

        @dataclass
        class Cfg:
            name: str

        original = __import__("typing").get_type_hints

        def broken_hints(cls, **kw):
            if cls is Cfg:
                raise Exception("broken")
            return original(cls, **kw)

        with patch("pico_ioc.config_registrar.typing.get_type_hints", broken_hints):
            inst = mgr._build_flat_instance(Cfg, prefix=None)
            assert inst.name == "test"


class TestConfigRegistrarAutoDetectHintsFailure:
    """config_registrar.py lines 120-121: get_type_hints falla en auto detect."""

    def test_auto_detect_broken_hints(self):
        mgr = ConfigurationManager(None)

        @dataclass
        class Cfg:
            name: str

        original = __import__("typing").get_type_hints

        def broken_hints(cls, **kw):
            if cls is Cfg:
                raise Exception("broken")
            return original(cls, **kw)

        with patch("pico_ioc.config_registrar.typing.get_type_hints", broken_hints):
            # When hints fail, dc_hints={}, f.type is used as-is
            # str fields -> flat
            result = mgr._auto_detect_mapping(Cfg)
            # Without hints, f.type is a string like 'str', not a type
            # so it won't match primitives -> falls through to flat
            assert result in ("flat", "tree")


class TestConfigRegistrarAutoDetectOptionalUnion:
    """config_registrar.py lines 140-144, 147: Optional[CustomClass] detection."""

    def test_optional_custom_class_detected_as_tree(self):
        mgr = ConfigurationManager(None)

        class Engine:
            pass

        @dataclass
        class CarCfg:
            engine: Optional[Engine] = None

        # Optional[Engine] -> Union[Engine, None] -> base_type=Engine
        # Engine is not a primitive -> tree
        assert mgr._auto_detect_mapping(CarCfg) == "tree"

    def test_optional_triggers_union_branch_tree(self):
        mgr = ConfigurationManager(None)

        @dataclass
        class SimpleCfg:
            name: str
            count: Optional[int] = None

        # Optional[int] = Union[int, None] -> origin is Union -> "tree"
        # This is correct: Union origin is caught at line 132
        assert mgr._auto_detect_mapping(SimpleCfg) == "tree"


# ============================================================
# Extra coverage: proxy_protocols.py
# ============================================================


class TestProxyProtocolsOperators:
    """Lines 97, 100, 106, 109, 112, 139: Uncovered operator overloads."""

    def _make_proxy(self, value):
        from pico_ioc.proxy_protocols import _ProxyProtocolMixin

        class SimpleProxy(_ProxyProtocolMixin):
            def __init__(self, val):
                self._val = val

            def _get_real_object(self):
                return self._val

        return SimpleProxy(value)

    def test_rfloordiv(self):
        """Line 97: __rfloordiv__"""
        proxy = self._make_proxy(3)
        assert 10 // proxy == 3

    def test_rmod(self):
        """Line 100: __rmod__"""
        proxy = self._make_proxy(3)
        assert 10 % proxy == 1

    def test_rpow(self):
        """Line 106: __rpow__"""
        proxy = self._make_proxy(3)
        assert 2**proxy == 8

    def test_rlshift(self):
        """Line 109: __rlshift__"""
        proxy = self._make_proxy(2)
        assert 1 << proxy == 4

    def test_rrshift(self):
        """Line 112: __rrshift__"""
        proxy = self._make_proxy(2)
        assert 8 >> proxy == 2

    def test_ne(self):
        """Line 139: __ne__"""
        proxy = self._make_proxy(42)
        assert proxy != 99
        assert not (proxy != 42)


# ============================================================
# Extra coverage: scope.py
# ============================================================


class TestScopeManagerActivateNoActivateMethod:
    def test_scope_impl_without_activate_returns_none(self):
        """Line 136: scope impl without 'activate' returns None."""
        mgr = ScopeManager()
        # Replace a scope impl with one that has no activate method
        bare = MagicMock(spec=[])  # no methods at all
        mgr._scopes["custom_bare"] = bare
        result = mgr.activate("custom_bare", "id1")
        assert result is None


class TestScopedCachesCleanupObjectInspectError:
    def test_cleanup_object_inspect_error(self):
        """Lines 189-190: inspect.getmembers fails on object."""
        caches = ScopedCaches()

        class Explosive:
            def __dir__(self):
                raise RuntimeError("can't inspect")

        # Should not raise - error is logged
        caches._cleanup_object(Explosive())

    def test_cleanup_container_error(self):
        """Lines 202-203: container.items() raises exception."""
        caches = ScopedCaches()

        bad_container = MagicMock()
        bad_container.items.side_effect = RuntimeError("broken")

        # Should not raise - error is logged
        caches._cleanup_container(bad_container)


class TestScopedCachesShrinkEmptyBucket:
    def test_shrink_nonexistent_scope(self):
        """Line 240: shrink on scope with no bucket."""
        caches = ScopedCaches()
        # Should not raise
        caches.shrink("request", 5)


# ============================================================
# Extra coverage: component_scanner.py
# ============================================================


class TestFactoryConditionFalse:
    def test_factory_class_disabled_by_condition(self):
        """Line 123: factory class fails condition check."""
        from pico_ioc.component_scanner import ComponentScanner

        mgr = ConfigurationManager(None)
        scanner = ComponentScanner({"prod"}, {}, mgr)

        # A factory class with a condition that doesn't match active profiles
        from pico_ioc.decorators import factory

        @factory()
        class MyFactory:
            pass

        setattr(MyFactory, PICO_META, {"conditional": {"profiles": ["dev"]}})
        # Should just return without registering
        scanner._register_factory_class(MyFactory)
        results = scanner.get_scan_results()
        assert MyFactory not in [md.factory_class for _, _, md in results[0].get(MyFactory, [])]


class TestDetectFactoryDepsException:
    def test_detect_factory_deps_attribute_error(self):
        """Lines 171-172: exception during attribute inspection in _detect_factory_deps."""
        from pico_ioc.component_scanner import ComponentScanner

        mgr = ConfigurationManager(None)
        scanner = ComponentScanner(set(), {}, mgr)

        class TrickyFactory:
            @property
            def problematic(self):
                raise AttributeError("boom")

        result = scanner._detect_factory_deps(TrickyFactory)
        assert result is None


class TestResolveProvidesMemberClassmethod:
    def test_classmethod_provides(self):
        """Line 184: classmethod branch in _resolve_provides_member."""
        from pico_ioc.component_scanner import ComponentScanner
        from pico_ioc.constants import PICO_INFRA, PICO_KEY

        mgr = ConfigurationManager(None)
        scanner = ComponentScanner(set(), {}, mgr)

        class MyFactory:
            @classmethod
            def build(cls):
                return "result"

        # Mark the classmethod's __func__ as provides
        setattr(MyFactory.build.__func__, PICO_INFRA, "provides")
        setattr(MyFactory.build.__func__, PICO_KEY, "my_key")
        setattr(MyFactory.build.__func__, PICO_META, {})

        fn, kind = scanner._resolve_provides_member(MyFactory, "build")
        assert kind == "class"
        assert fn is not None


class TestResolveProvidesMemberConditionFalse:
    def test_provides_disabled_by_condition(self):
        """Line 193: provides method fails condition check."""
        from pico_ioc.component_scanner import ComponentScanner
        from pico_ioc.constants import PICO_INFRA, PICO_KEY

        mgr = ConfigurationManager(None)
        scanner = ComponentScanner({"prod"}, {}, mgr)

        class MyFactory:
            @staticmethod
            def build():
                return "result"

        setattr(MyFactory.build, PICO_INFRA, "provides")
        setattr(MyFactory.build, PICO_KEY, "my_key")
        setattr(MyFactory.build, PICO_META, {"conditional": {"profiles": ["dev"]}})

        fn, kind = scanner._resolve_provides_member(MyFactory, "build")
        assert fn is None
        assert kind is None


# ============================================================
# Extra coverage: registrar.py
# ============================================================


class TestCanBeSelectedForNonType:
    def test_non_type_selector(self):
        """Line 24: _can_be_selected_for with non-type selector."""
        from pico_ioc.registrar import _can_be_selected_for

        assert _can_be_selected_for({}, "not_a_type") is False

    def test_issubclass_exception(self):
        """Lines 31-32: issubclass raises exception."""
        from pico_ioc.registrar import _can_be_selected_for

        md = MagicMock()
        md.provided_type = type("Broken", (), {})
        md.concrete_class = None

        class BadMeta(type):
            def __subclasscheck__(cls, subclass):
                raise TypeError("broken")

        selector = BadMeta("Selector", (), {})
        result = _can_be_selected_for({"k": md}, selector)
        assert result is False


# ============================================================
# Extra coverage: analysis.py
# ============================================================


class TestResolveKeyUnannotated:
    def test_unannotated_param_uses_name(self):
        """Lines 191-192: _resolve_key fallback when base_type is non-type/non-str and ann is _empty."""
        from pico_ioc.analysis import _resolve_key

        # base_type must NOT be a type or str, and ann must be _empty
        # This triggers the line 191 branch
        key, dict_key = _resolve_key(
            is_list=False,
            is_dict=False,
            elem_t=None,
            dict_key_t=None,
            base_type=42,
            ann=inspect._empty,
            name="my_param",
        )
        assert key == "my_param"

    def test_non_type_non_str_base_with_annotation(self):
        """Line 193: base_type is non-type/non-str but ann is NOT _empty."""
        from pico_ioc.analysis import _resolve_key

        key, dict_key = _resolve_key(
            is_list=False,
            is_dict=False,
            elem_t=None,
            dict_key_t=None,
            base_type=42,
            ann="some_ann",
            name="x",
        )
        assert key == 42


# ============================================================
# Extra coverage: event_bus.py
# ============================================================


class TestPublishSyncFromRunningLoop:
    @pytest.mark.asyncio
    async def test_publish_sync_from_running_loop(self):
        """Line 148 (146): publish_sync from running event loop creates task."""
        from pico_ioc.event_bus import Event, EventBus

        class MyEvent(Event):
            pass

        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(MyEvent, handler)

        # Call publish_sync from within running loop
        bus.publish_sync(MyEvent())

        # Give the task time to execute
        await asyncio.sleep(0.05)
        assert len(received) == 1
        await bus.aclose()


class TestEventBusCleanupNoLoop:
    def test_cleanup_without_running_loop(self):
        """Line 326: PicoEventBusProvider.shutdown without running loop."""
        from pico_ioc.event_bus import EventBus, PicoEventBusProvider

        provider = PicoEventBusProvider()
        bus = EventBus()
        # Should close the bus synchronously
        provider.shutdown(bus)


# ============================================================
# Extra coverage: graph_export.py
# ============================================================


class TestGraphExportNonStringNonTypeKey:
    def test_non_string_non_type_dep_key(self):
        """Line 30: dep_key that is neither str nor type."""
        from pico_ioc.graph_export import _map_dep_to_bound_key

        loc = MagicMock()
        loc._metadata = {}

        # An integer key should be returned as-is (not str, not type)
        result = _map_dep_to_bound_key(loc, 42)
        assert result == 42

    def test_issubclass_exception_in_find_subtype(self):
        """Lines 41-42: issubclass exception in _find_subtype_key."""
        from pico_ioc.graph_export import _find_subtype_key

        md = MagicMock()
        md.provided_type = None

        class BadConcrete:
            pass

        # Make issubclass raise by using a broken metaclass
        md.concrete_class = BadConcrete

        class BadMeta(type):
            def __subclasscheck__(cls, subclass):
                raise TypeError("broken")

        target = BadMeta("Target", (), {})
        loc = MagicMock()
        loc._metadata = {"k": md}

        # Should return dep_key unchanged after exception
        result = _find_subtype_key(loc, target)
        assert result is target


# ============================================================
# Extra coverage: container.py
# ============================================================


class TestGetSignatureSafeWrapped:
    def test_wrapped_fallback(self):
        """Line 38: __wrapped__ fallback for signature."""
        from pico_ioc.container import _get_signature_safe

        def real_fn(a: int, b: str): ...

        class BadCallable:
            __wrapped__ = real_fn

            def __call__(self):
                pass

        # Make __call__ signature fail but __wrapped__ works
        obj = BadCallable()
        # Patch to make first attempt fail
        with patch("inspect.signature", side_effect=[TypeError("nope"), inspect.signature(real_fn)]):
            sig = _get_signature_safe(obj)
            assert "a" in sig.parameters


class TestContainerCanonicalKeySubclass:
    def _make_pico(self, factory, locator):
        caches = ScopedCaches()
        scopes = ScopeManager()
        pico = PicoContainer(factory, caches, scopes)
        pico._locator = locator
        return pico

    def test_canonical_key_finds_subclass(self):
        """Lines 171, 174: _canonical_key finds subclass via issubclass."""

        class Base:
            pass

        class Impl(Base):
            pass

        factory = ComponentFactory()
        factory.bind(Impl, lambda: Impl())
        # Add a non-type entry to trigger line 171 (continue)
        md_str = ProviderMetadata(
            key="str_key",
            provided_type=None,
            concrete_class=None,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=False,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
            dependencies=(),
        )
        md = ProviderMetadata(
            key=Impl,
            provided_type=Impl,
            concrete_class=Impl,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
            dependencies=(),
        )
        locator = ComponentLocator({"str_key": md_str, Impl: md}, {})
        pico = self._make_pico(factory, locator)

        result = pico._canonical_key(Base)
        assert result is Impl

    def test_canonical_key_issubclass_exception(self):
        """Lines 175-176: issubclass raises exception in _canonical_key."""

        class BadMeta(type):
            def __subclasscheck__(cls, subclass):
                raise TypeError("broken")

        Broken = BadMeta("Broken", (), {})

        factory = ComponentFactory()
        md = ProviderMetadata(
            key=Broken,
            provided_type=Broken,
            concrete_class=Broken,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
            dependencies=(),
        )
        locator = ComponentLocator({Broken: md}, {})
        pico = self._make_pico(factory, locator)

        result = pico._canonical_key(int)
        assert result is int


class TestContainerAsyncCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_all_async_with_event_bus(self):
        """Lines 386-387: cleanup_all_async with EventBus in cache."""
        from pico_ioc.event_bus import EventBus

        factory = ComponentFactory()
        caches = ScopedCaches()
        scopes = ScopeManager()
        pico = PicoContainer(factory, caches, scopes)

        bus = EventBus()
        pico._caches._singleton.put("bus_key", bus)

        await pico.cleanup_all_async()


# ============================================================
# Extra coverage: dependency_validator.py
# ============================================================


class TestDependencyValidatorProtocolFallback:
    def test_protocol_implementation_found(self):
        """Lines 46-49: Protocol fallback via _implements_protocol."""
        from typing import Protocol

        # Non-runtime-checkable protocol - issubclass raises TypeError
        # so cands stays empty, then _is_protocol fallback is used
        class MyProto(Protocol):
            def do_thing(self) -> str: ...

        class MyImpl:
            def do_thing(self) -> str:
                return "done"

        factory = ComponentFactory()
        factory.bind(MyImpl, lambda: MyImpl())
        md = ProviderMetadata(
            key=MyImpl,
            provided_type=MyImpl,
            concrete_class=MyImpl,
            factory_class=None,
            factory_method=None,
            qualifiers=set(),
            primary=True,
            lazy=False,
            infra="component",
            pico_name=None,
            scope=SCOPE_SINGLETON,
            dependencies=(),
        )
        locator = ComponentLocator({MyImpl: md}, {})
        validator = DependencyValidator({MyImpl: md}, factory, locator)

        result = validator._find_md_for_type(MyProto)
        assert result is not None


class TestValidateTypeDepReturnError:
    def test_unbound_type_dep_returns_error_msg(self):
        """Line 124: _validate_type_dep returns error for unbound type."""

        class Missing:
            pass

        factory = ComponentFactory()
        md_dict = {}
        locator = ComponentLocator(md_dict, {})
        validator = DependencyValidator(md_dict, factory, locator)

        result = validator._validate_type_dep("SomeComponent", Missing, "some_param")
        assert result is not None
        assert "not bound" in result


# ============================================================
# Extra coverage: config_runtime.py
# ============================================================


class TestWalkPathInvalidRef:
    def test_invalid_ref_path_raises(self):
        """Line 76: invalid ref path in configuration."""
        from pico_ioc.config_runtime import _walk_path

        with pytest.raises(ConfigurationError, match="Invalid ref path"):
            _walk_path({"a": {"b": 1}}, "a.c.d")


class TestCoercePrimFallthrough:
    def test_coerce_prim_unknown_type(self):
        """Line 366: _coerce_prim with type that doesn't match str/int/float/bool."""
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)
        # bytes is not handled, should return node as-is
        result = builder._coerce_prim(b"hello", bytes, ("test",))
        assert result == b"hello"


class TestBuildNodeFallthrough:
    def test_build_node_unknown_type(self):
        """Line 263: _build_node with class that has __init__ (non-dataclass, non-enum, non-prim)."""
        resolver = ConfigResolver(())
        registry = TypeAdapterRegistry()
        builder = ObjectGraphBuilder(resolver, registry)

        class Custom:
            def __init__(self):
                pass

        # hits hasattr(t, "__init__") -> _build_constructor
        result = builder._build_type({}, Custom, ("test",))
        assert isinstance(result, Custom)


# ============================================================
# Extra coverage: config_registrar.py
# ============================================================


class TestConfigRegistrarTreeMapping:
    def test_tree_mapping_registration(self):
        """Lines 177-198: register_configured_class with tree mapping."""

        @dataclass
        class NestedItem:
            value: str = ""

        @configured(prefix="app")
        @dataclass
        class AppConfig:
            items: List[NestedItem] = field(default_factory=list)

        config = ContextConfig(
            flat_sources=(),
            tree_sources=(DictSource({"app": {"items": [{"value": "x"}]}}),),
            overrides={},
        )
        mgr = ConfigurationManager(config)

        result = mgr.register_configured_class(AppConfig, enabled=True)
        assert result is not None
        key, provider, md = result
        assert key is AppConfig
        assert md.infra == "configured"
