import inspect
from typing import Any, Callable, Dict, Tuple, Type, Union

from .analysis import DependencyRequest, analyze_callable_dependencies
from .aop import UnifiedComponentProxy

KeyT = Union[str, type]


class _ResolutionMixin:
    def _resolve_args(self, dependencies: Tuple[DependencyRequest, ...]) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        if not dependencies or self._locator is None:
            return kwargs

        for dep in dependencies:
            if dep.is_list:
                self._resolve_list_dep(dep, kwargs)
            elif dep.is_dict:
                self._resolve_dict_dep(dep, kwargs)
            else:
                self._resolve_single_dep(dep, kwargs)
        return kwargs

    def _resolve_list_dep(self, dep: DependencyRequest, kwargs: Dict[str, Any]) -> None:
        keys: Tuple[KeyT, ...] = ()
        if isinstance(dep.key, type):
            keys = tuple(self._locator.collect_by_type(dep.key, dep.qualifier))
        kwargs[dep.parameter_name] = [self.get(k) for k in keys]

    def _resolve_dict_dep(self, dep: DependencyRequest, kwargs: Dict[str, Any]) -> None:
        value_type = dep.key
        key_type = dep.dict_key_type
        result_map: Dict[Any, Any] = {}

        keys_to_resolve: Tuple[KeyT, ...] = ()
        if isinstance(value_type, type):
            keys_to_resolve = tuple(self._locator.collect_by_type(value_type, dep.qualifier))

        for comp_key in keys_to_resolve:
            instance = self.get(comp_key)
            md = self._locator._metadata.get(comp_key)
            if md is None:
                continue

            dict_key = self._extract_dict_key(comp_key, md, key_type)
            if dict_key is not None:
                if (key_type is type or key_type is Type) and not isinstance(dict_key, type):
                    continue
                result_map[dict_key] = instance

        kwargs[dep.parameter_name] = result_map

    def _extract_dict_key(self, comp_key: KeyT, md: Any, key_type: Any) -> Any:
        if key_type is str or key_type is Any:
            if md.pico_name is not None:
                return md.pico_name
            if isinstance(comp_key, str):
                return comp_key
            return getattr(comp_key, "__name__", str(comp_key))
        if key_type is type or key_type is Type:
            return md.concrete_class or md.provided_type
        return None

    def _resolve_single_dep(self, dep: DependencyRequest, kwargs: Dict[str, Any]) -> None:
        primary_key = dep.key
        if isinstance(primary_key, str):
            mapped = self._locator.find_key_by_name(primary_key)
            primary_key = mapped if mapped is not None else primary_key

        try:
            kwargs[dep.parameter_name] = self.get(primary_key)
        except Exception as first_error:
            if primary_key != dep.parameter_name:
                try:
                    kwargs[dep.parameter_name] = self.get(dep.parameter_name)
                except Exception:
                    raise first_error from None
            else:
                raise first_error from None

    def _maybe_wrap_with_aspects(self, key, instance: Any) -> Any:
        if isinstance(instance, UnifiedComponentProxy):
            return instance
        cls = type(instance)
        for _, fn in inspect.getmembers(
            cls, predicate=lambda m: inspect.isfunction(m) or inspect.ismethod(m) or inspect.iscoroutinefunction(m)
        ):
            if getattr(fn, "_pico_interceptors_", None):
                return UnifiedComponentProxy(container=self, target=instance, component_key=key)
        return instance

    def build_class(self, cls: type, locator: Any, dependencies: Tuple[DependencyRequest, ...]) -> Any:
        init = cls.__init__
        if init is object.__init__:
            inst = cls()
        else:
            deps = self._resolve_args(dependencies)
            inst = cls(**deps)

        ainit = getattr(inst, "__ainit__", None)
        has_async = callable(ainit) and inspect.iscoroutinefunction(ainit)

        if has_async:

            async def runner():
                if callable(ainit):
                    kwargs = {}
                    try:
                        ainit_deps = analyze_callable_dependencies(ainit)
                        kwargs = self._resolve_args(ainit_deps)
                    except Exception:
                        kwargs = {}
                    res = ainit(**kwargs)
                    if inspect.isawaitable(res):
                        await res
                return inst

            return runner()

        return inst

    def build_method(self, fn: Callable[..., Any], locator: Any, dependencies: Tuple[DependencyRequest, ...]) -> Any:
        deps = self._resolve_args(dependencies)
        obj = fn(**deps)
        return obj
