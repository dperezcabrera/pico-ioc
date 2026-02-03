"""
Extended tests for aop.py to increase coverage.
"""
import asyncio
import pickle
import pytest
from unittest.mock import MagicMock, patch

from pico_ioc.aop import (
    UnifiedComponentProxy,
    MethodCtx,
    MethodInterceptor,
    dispatch_method,
    intercepted_by,
    _gather_interceptors_for_method,
    health
)
from pico_ioc.exceptions import SerializationError, AsyncResolutionError


class TestMethodCtx:
    """Test MethodCtx data class."""

    def test_method_ctx_slots(self):
        """MethodCtx uses __slots__ for memory efficiency."""
        assert hasattr(MethodCtx, "__slots__")

    def test_method_ctx_initialization(self):
        """MethodCtx initializes all fields correctly."""
        instance = object()
        cls = type(instance)

        def method():
            pass

        ctx = MethodCtx(
            instance=instance,
            cls=cls,
            method=method,
            name="test_method",
            args=(1, 2),
            kwargs={"key": "value"},
            container=MagicMock(),
            request_key="req-123"
        )

        assert ctx.instance is instance
        assert ctx.cls is cls
        assert ctx.method is method
        assert ctx.name == "test_method"
        assert ctx.args == (1, 2)
        assert ctx.kwargs == {"key": "value"}
        assert ctx.request_key == "req-123"
        assert ctx.local == {}

    def test_method_ctx_local_storage(self):
        """MethodCtx.local can store interceptor data."""
        ctx = MethodCtx(
            instance=None,
            cls=object,
            method=lambda: None,
            name="test",
            args=(),
            kwargs={},
            container=None
        )

        ctx.local["key1"] = "value1"
        ctx.local["key2"] = 42

        assert ctx.local["key1"] == "value1"
        assert ctx.local["key2"] == 42


class TestDispatchMethod:
    """Test dispatch_method function."""

    def test_dispatch_no_interceptors(self):
        """dispatch_method calls method directly without interceptors."""
        def method(a, b):
            return a + b

        ctx = MethodCtx(
            instance=None,
            cls=object,
            method=method,
            name="add",
            args=(1, 2),
            kwargs={},
            container=None
        )

        result = dispatch_method([], ctx)

        assert result == 3

    def test_dispatch_with_single_interceptor(self):
        """dispatch_method chains single interceptor."""
        class LoggingInterceptor:
            def invoke(self, ctx, call_next):
                ctx.local["logged"] = True
                return call_next(ctx)

        def method(x):
            return x * 2

        ctx = MethodCtx(
            instance=None,
            cls=object,
            method=method,
            name="double",
            args=(5,),
            kwargs={},
            container=None
        )

        result = dispatch_method([LoggingInterceptor()], ctx)

        assert result == 10
        assert ctx.local["logged"] is True

    def test_dispatch_with_multiple_interceptors(self):
        """dispatch_method chains multiple interceptors in order."""
        order = []

        class FirstInterceptor:
            def invoke(self, ctx, call_next):
                order.append("first_before")
                result = call_next(ctx)
                order.append("first_after")
                return result

        class SecondInterceptor:
            def invoke(self, ctx, call_next):
                order.append("second_before")
                result = call_next(ctx)
                order.append("second_after")
                return result

        def method():
            order.append("method")
            return "done"

        ctx = MethodCtx(
            instance=None,
            cls=object,
            method=method,
            name="test",
            args=(),
            kwargs={},
            container=None
        )

        result = dispatch_method(
            [FirstInterceptor(), SecondInterceptor()],
            ctx
        )

        assert result == "done"
        assert order == [
            "first_before",
            "second_before",
            "method",
            "second_after",
            "first_after"
        ]

    def test_dispatch_interceptor_can_modify_args(self):
        """Interceptors can modify args before calling next."""
        class MultiplyInterceptor:
            def invoke(self, ctx, call_next):
                new_args = tuple(a * 2 for a in ctx.args)
                ctx.args = new_args
                return call_next(ctx)

        def method(x):
            return x

        ctx = MethodCtx(
            instance=None,
            cls=object,
            method=method,
            name="identity",
            args=(5,),
            kwargs={},
            container=None
        )

        result = dispatch_method([MultiplyInterceptor()], ctx)

        assert result == 10


class TestInterceptedBy:
    """Test @intercepted_by decorator."""

    def test_intercepted_by_single_class(self):
        """@intercepted_by accepts single interceptor class."""
        class MyInterceptor:
            def invoke(self, ctx, call_next):
                return call_next(ctx)

        @intercepted_by(MyInterceptor)
        def my_method():
            pass

        assert MyInterceptor in my_method._pico_interceptors_

    def test_intercepted_by_multiple_classes(self):
        """@intercepted_by accepts multiple interceptor classes."""
        class Interceptor1:
            def invoke(self, ctx, call_next):
                return call_next(ctx)

        class Interceptor2:
            def invoke(self, ctx, call_next):
                return call_next(ctx)

        @intercepted_by(Interceptor1, Interceptor2)
        def my_method():
            pass

        assert Interceptor1 in my_method._pico_interceptors_
        assert Interceptor2 in my_method._pico_interceptors_

    def test_intercepted_by_stacking(self):
        """@intercepted_by can be stacked."""
        class InterceptorA:
            def invoke(self, ctx, call_next):
                return call_next(ctx)

        class InterceptorB:
            def invoke(self, ctx, call_next):
                return call_next(ctx)

        @intercepted_by(InterceptorB)
        @intercepted_by(InterceptorA)
        def my_method():
            pass

        assert InterceptorA in my_method._pico_interceptors_
        assert InterceptorB in my_method._pico_interceptors_

    def test_intercepted_by_no_args_raises(self):
        """@intercepted_by with no args raises TypeError."""
        with pytest.raises(TypeError):
            @intercepted_by()
            def my_method():
                pass

    def test_intercepted_by_non_class_raises(self):
        """@intercepted_by with non-class raises TypeError."""
        with pytest.raises(TypeError):
            @intercepted_by("not_a_class")
            def my_method():
                pass

    def test_intercepted_by_on_non_callable_raises(self):
        """@intercepted_by on non-callable raises TypeError."""
        class Interceptor:
            pass

        with pytest.raises(TypeError):
            intercepted_by(Interceptor)("not_callable")


class TestGatherInterceptors:
    """Test _gather_interceptors_for_method function."""

    def test_gather_interceptors_returns_tuple(self):
        """_gather_interceptors_for_method returns tuple of classes."""
        class MyInterceptor:
            pass

        class MyClass:
            @intercepted_by(MyInterceptor)
            def intercepted_method(self):
                pass

        result = _gather_interceptors_for_method(MyClass, "intercepted_method")

        assert result == (MyInterceptor,)

    def test_gather_interceptors_no_attribute(self):
        """_gather_interceptors_for_method returns empty for missing method."""
        class MyClass:
            pass

        result = _gather_interceptors_for_method(MyClass, "nonexistent")

        assert result == ()

    def test_gather_interceptors_no_interceptors(self):
        """_gather_interceptors_for_method returns empty for plain method."""
        class MyClass:
            def plain_method(self):
                pass

        result = _gather_interceptors_for_method(MyClass, "plain_method")

        assert result == ()


class TestHealthDecorator:
    """Test @health decorator."""

    def test_health_decorator_sets_metadata(self):
        """@health decorator sets _pico_meta."""
        @health
        def check_status():
            return True

        assert check_status._pico_meta["health_check"] is True

    def test_health_decorator_preserves_function(self):
        """@health decorator preserves function behavior."""
        @health
        def check_value():
            return 42

        assert check_value() == 42


class TestUnifiedComponentProxySerialization:
    """Test proxy serialization."""

    def test_proxy_getstate_serializes_target(self):
        """__getstate__ serializes the target object."""
        target = {"key": "value", "number": 42}
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        state = proxy.__getstate__()

        assert "data" in state

    def test_proxy_setstate_restores_target(self):
        """__setstate__ restores the target object."""
        target = {"key": "value"}
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        state = proxy.__getstate__()

        # Create new proxy and restore
        new_proxy = UnifiedComponentProxy.__new__(UnifiedComponentProxy)
        new_proxy.__setstate__(state)

        assert new_proxy._get_real_object() == target

    def test_proxy_pickle_roundtrip(self):
        """Proxy survives pickle roundtrip - returns unpacked target."""
        target = [1, 2, 3]
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        pickled = pickle.dumps(proxy)
        restored = pickle.loads(pickled)

        # Pickling a proxy returns the underlying target, not another proxy
        assert restored == target

    def test_proxy_unpicklable_target_raises(self):
        """Proxy with unpicklable target raises SerializationError."""
        # Lambda cannot be pickled
        target = lambda x: x
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        with pytest.raises(SerializationError):
            proxy.__getstate__()


class TestUnifiedComponentProxyDunderMethods:
    """Test proxy dunder method delegation."""

    def test_proxy_hash(self):
        """Proxy delegates __hash__ to target."""
        target = "hashable_string"
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        assert hash(proxy) == hash(target)

    def test_proxy_bool_true(self):
        """Proxy delegates __bool__ (truthy)."""
        target = [1, 2, 3]
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        assert bool(proxy) is True

    def test_proxy_bool_false(self):
        """Proxy delegates __bool__ (falsy)."""
        target = []
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        assert bool(proxy) is False

    def test_proxy_call(self):
        """Proxy delegates __call__."""
        def target(x):
            return x * 2

        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        assert proxy(5) == 10

    def test_proxy_reversed(self):
        """Proxy delegates __reversed__."""
        target = [1, 2, 3]
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        assert list(reversed(proxy)) == [3, 2, 1]

    def test_proxy_divmod(self):
        """Proxy delegates __divmod__."""
        target = 17
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=target
        )

        assert divmod(proxy, 5) == (3, 2)


class TestUnifiedComponentProxyLazyInit:
    """Test lazy initialization of proxy."""

    def test_lazy_proxy_defers_creation(self):
        """Proxy with creator defers object creation."""
        created = []

        def creator():
            obj = {"created": True}
            created.append(obj)
            return obj

        container = MagicMock()
        container._run_configure_methods = MagicMock(return_value=None)

        proxy = UnifiedComponentProxy(
            container=container,
            target=None,
            object_creator=creator
        )

        # Not created yet
        assert len(created) == 0

        # Access triggers creation
        _ = proxy._get_real_object()

        assert len(created) == 1

    def test_lazy_proxy_caches_result(self):
        """Proxy caches created object."""
        creation_count = 0

        def creator():
            nonlocal creation_count
            creation_count += 1
            return {"id": creation_count}

        container = MagicMock()
        container._run_configure_methods = MagicMock(return_value=None)

        proxy = UnifiedComponentProxy(
            container=container,
            target=None,
            object_creator=creator
        )

        # Multiple accesses
        obj1 = proxy._get_real_object()
        obj2 = proxy._get_real_object()
        obj3 = proxy._get_real_object()

        assert creation_count == 1
        assert obj1 is obj2 is obj3

    def test_lazy_proxy_creator_returns_none_raises(self):
        """Proxy raises if creator returns None."""
        def bad_creator():
            return None

        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=None,
            object_creator=bad_creator
        )

        with pytest.raises(RuntimeError, match="returned None"):
            proxy._get_real_object()

    def test_lazy_proxy_non_callable_creator_raises(self):
        """Proxy raises if creator is not callable."""
        container = MagicMock()

        proxy = UnifiedComponentProxy(
            container=container,
            target=None,
            object_creator="not_callable"
        )

        with pytest.raises(TypeError, match="must be callable"):
            proxy._get_real_object()


class TestUnifiedComponentProxyValidation:
    """Test proxy initialization validation."""

    def test_proxy_requires_container(self):
        """Proxy requires non-null container."""
        with pytest.raises(ValueError, match="non-null container"):
            UnifiedComponentProxy(
                container=None,
                target={}
            )

    def test_proxy_requires_target_or_creator(self):
        """Proxy requires either target or object_creator."""
        container = MagicMock()

        with pytest.raises(ValueError, match="target or an object_creator"):
            UnifiedComponentProxy(
                container=container,
                target=None,
                object_creator=None
            )
