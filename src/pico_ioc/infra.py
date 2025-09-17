from __future__ import annotations
import re
from typing import Any, Callable, Iterable, Optional, Sequence, Tuple

class Select:
    def __init__(self):
        self._tags: set[str] = set()
        self._profiles: set[str] = set()
        self._class_name_regex: Optional[re.Pattern[str]] = None
        self._method_name_regex: Optional[re.Pattern[str]] = None

    def has_tag(self, *tags: str) -> "Select":
        self._tags.update(t for t in tags if t)
        return self

    def profile_in(self, *profiles: str) -> "Select":
        self._profiles.update(p for p in profiles if p)
        return self

    def class_name(self, regex: str) -> "Select":
        self._class_name_regex = re.compile(regex)
        return self

    def method_name(self, regex: str) -> "Select":
        self._method_name_regex = re.compile(regex)
        return self

    def is_effectively_empty(self) -> bool:
        return not (self._tags or self._profiles or self._class_name_regex or self._method_name_regex)

    def match_provider(self, key: Any, meta: dict, *, active_profiles: Sequence[str]) -> bool:
        if self.is_effectively_empty():
            return False
        if self._tags:
            tags = set(meta.get("tags", ()))
            if not tags.intersection(self._tags):
                return False
        if self._profiles:
            if not set(active_profiles).intersection(self._profiles):
                return False
        if self._class_name_regex and isinstance(key, type):
            if not self._class_name_regex.search(getattr(key, "__name__", "")):
                return False
        return True

    def match_method_name(self, method: str) -> bool:
        if self._method_name_regex is None:
            return True
        return bool(self._method_name_regex.search(method))


class InfraQuery:
    def __init__(self, container, profiles: Tuple[str, ...]):
        self.c = container
        self.profiles = profiles

    def providers(self, where: Optional[Select] = None, *, limit: Optional[int] = None) -> list[tuple[Any, dict]]:
        sel = where or Select()
        items: list[tuple[Any, dict]] = []
        for k, m in self.c._providers.items():
            if sel.match_provider(k, m, active_profiles=self.profiles):
                items.append((k, m))
                if limit is not None and len(items) >= limit:
                    break
        return items

    def components(self, where: Optional[Select] = None, *, limit: Optional[int] = None) -> list[type]:
        out: list[type] = []
        for k, _m in self.providers(where=where, limit=limit):
            if isinstance(k, type):
                out.append(k)
        return out


class InfraIntercept:
    def __init__(self, container, profiles: Tuple[str, ...]):
        self.c = container
        self.profiles = profiles
        self._per_method_cap: Optional[int] = None

    def _collect_target_classes(self, where: Select) -> tuple[set[type], set[Any]]:
        classes: set[type] = set()
        keys: set[Any] = set()
        for key, meta in self.c._providers.items():
            if where.match_provider(key, meta, active_profiles=self.profiles):
                keys.add(key)
                if isinstance(key, type):
                    classes.add(key)
        return classes, keys

    def _guard_method_interceptor(self, interceptor, where: Select):
        target_classes, _keys = self._collect_target_classes(where)
        class_names = {cls.__name__ for cls in target_classes}
        class Guarded:
            def invoke(self, ctx, call_next):
                tgt_cls = type(ctx.instance)
                ok_class = any(isinstance(ctx.instance, cls) for cls in target_classes) or (getattr(tgt_cls, "__name__", "") in class_names)
                ok_method = where.match_method_name(ctx.name)
                if ok_class and ok_method:
                    return interceptor.invoke(ctx, call_next) if hasattr(interceptor, "invoke") else interceptor(ctx, call_next)
                return call_next(ctx)
        return Guarded()

    def _guard_container_interceptor(self, interceptor, where: Select):
        target_classes, keys = self._collect_target_classes(where)
        class_names = {cls.__name__ for cls in target_classes}
        def _ok(key: Any) -> bool:
            if key in keys:
                return True
            if isinstance(key, type) and (key in target_classes or getattr(key, "__name__", "") in class_names):
                return True
            return False
        class GuardedCI:
            def around_resolve(self, ctx, call_next):
                if _ok(ctx.key):
                    return interceptor.around_resolve(ctx, call_next)
                return call_next(ctx)
            def around_create(self, ctx, call_next):
                if _ok(ctx.key):
                    return interceptor.around_create(ctx, call_next)
                return call_next(ctx)
        return GuardedCI()

    def add(self, *, interceptor, where: Select) -> None:
        sel = where or Select()
        if sel.is_effectively_empty():
            raise ValueError("empty selector for interceptor")
        is_container = all(hasattr(interceptor, m) for m in ("around_resolve", "around_create"))
        if is_container:
            guarded = self._guard_container_interceptor(interceptor, sel)
            self.c.add_container_interceptor(guarded)
            return
        guarded = self._guard_method_interceptor(interceptor, sel)
        self.c.add_method_interceptor(guarded)

    def limit_per_method(self, max_n: int) -> None:
        self._per_method_cap = int(max_n)


class InfraMutate:
    def __init__(self, container, profiles: Tuple[str, ...]):
        self.c = container
        self.profiles = profiles

    def add_tags(self, component_or_key: Any, tags: Iterable[str]) -> None:
        key = component_or_key
        if key in self.c._providers:
            meta = self.c._providers[key]
            cur = tuple(meta.get("tags", ()))
            new = tuple(dict.fromkeys(list(cur) + [t for t in tags if t]))
            meta["tags"] = new
            self.c._providers[key] = meta

    def set_qualifiers(self, provider_key: Any, qualifiers: dict[str, Any]) -> None:
        if provider_key in self.c._providers:
            meta = self.c._providers[provider_key]
            meta["qualifiers"] = tuple(qualifiers or ())
            self.c._providers[provider_key] = meta

    def replace_provider(self, *, key: Any, with_factory: Callable[[], object]) -> None:
        if key in self.c._providers:
            lazy = bool(self.c._providers[key].get("lazy", False))
            self.c.bind(key, with_factory, lazy=lazy, tags=self.c._providers[key].get("tags", ()))

    def wrap_provider(self, *, key: Any, around: Callable[[Callable[[], object]], Callable[[], object]]) -> None:
        if key in self.c._providers:
            meta = self.c._providers[key]
            base_factory = meta.get("factory")
            if callable(base_factory):
                wrapped = around(base_factory)
                self.c.bind(key, wrapped, lazy=bool(meta.get("lazy", False)), tags=meta.get("tags", ()))

    def rename_key(self, *, old: Any, new: Any) -> None:
        if old in self.c._providers and new not in self.c._providers:
            self.c._providers[new] = self.c._providers.pop(old)

class Infra:
    def __init__(self, *, container, profiles: Tuple[str, ...]):
        self._c = container
        self._profiles = profiles
        self._query = InfraQuery(container, profiles)
        self._intercept = InfraIntercept(container, profiles)
        self._mutate = InfraMutate(container, profiles)

    @property
    def query(self) -> InfraQuery:
        return self._query

    @property
    def intercept(self) -> InfraIntercept:
        return self._intercept

    @property
    def mutate(self) -> InfraMutate:
        return self._mutate

