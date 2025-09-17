import sys
import textwrap
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, Annotated, List

import pytest
from pico_ioc import (
    component,
    scope,
    init,
    on_missing,
    conditional,
    reset,
    Qualifier,
    qualifier,
)


@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield
    reset()


@contextmanager
def _make_pkg(tmp_path: Path, name: str, files: dict[str, str]):
    pkg_dir = tmp_path / name
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    for rel, content in files.items():
        p = pkg_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content), encoding="utf-8")

    added = False
    pstr = str(tmp_path)
    if pstr not in sys.path:
        sys.path.insert(0, pstr)
        added = True

    try:
        mod = __import__(name)
        yield mod
    finally:
        for k in list(sys.modules.keys()):
            if k == name or k.startswith(name + "."):
                sys.modules.pop(k, None)
        if added:
            try:
                sys.path.remove(pstr)
            except ValueError:
                pass


class TestScopeFeatures:

    def test_scope_filters_by_tags(self):
        pkg = types.ModuleType("pkg_scope_tags")

        @component(tags=("a", "common"))
        class ComponentA: ...

        @component(tags=("b", "common"))
        class ComponentB: ...

        pkg.__dict__.update(locals())

        c_include = scope(
            modules=[pkg], include_tags={"a"}, roots=[ComponentA, ComponentB]
        )
        assert c_include.has(ComponentA) is True
        assert c_include.has(ComponentB) is False

        c_exclude = scope(
            modules=[pkg], exclude_tags={"a"}, roots=[ComponentA, ComponentB]
        )
        assert c_exclude.has(ComponentA) is False
        assert c_exclude.has(ComponentB) is True

    def test_scope_with_base_container_and_strict_mode(self):
        base_pkg = types.ModuleType("base_pkg")

        @component
        class BaseService: ...

        base_pkg.BaseService = BaseService
        base_container = init(base_pkg, reuse=False)

        scope_pkg = types.ModuleType("scope_pkg")

        @component
        class ScopedComponent:
            def __init__(self, base_service: BaseService):
                self.base_service = base_service

        scope_pkg.ScopedComponent = ScopedComponent

        scoped_container = scope(
            modules=[scope_pkg],
            base=base_container,
            strict=False,
            lazy=False,
            roots=[ScopedComponent],
        )
        instance = scoped_container.get(ScopedComponent)
        assert isinstance(instance.base_service, BaseService)

        with pytest.raises(NameError):
            scope(
                modules=[scope_pkg],
                base=base_container,
                strict=True,
                lazy=False,
                roots=[ScopedComponent],
            )

    def test_scope_applies_policy_and_defaults_correctly(self):
        pkg = types.ModuleType("pkg_scope_policy")

        class MQ: ...

        @component
        @conditional(profiles=["prod"])
        class Kafka(MQ): ...

        @component
        @on_missing(MQ)
        class InMemMQ(MQ): ...

        @component
        class App:
            def __init__(self, mq: MQ):
                self.mq = mq

        pkg.__dict__.update(locals())

        c_prod = scope(modules=[pkg], roots=[App], profiles=["prod"], lazy=False)
        assert isinstance(c_prod.get(App).mq, Kafka)

        c_dev = scope(modules=[pkg], roots=[App], profiles=["dev"], lazy=False)
        assert isinstance(c_dev.get(App).mq, InMemMQ)


class TestScopeUnit:

    def test_scope_basic_resolution(self, tmp_path: Path):
        with _make_pkg(
            tmp_path,
            "pkg_scope_basic",
            {
                "mod.py": """
                    from pico_ioc import component
                    @component
                    class A: pass
                    @component
                    class B:
                        def __init__(self, a: A):
                            self.a = a
                """
            },
        ) as pkg:
            import importlib
            m = importlib.import_module("pkg_scope_basic.mod")
            c = scope(modules=[pkg], roots=[m.B], strict=True, lazy=True)
            b = c.get(m.B)
            assert type(b).__name__ == "B"
            assert type(b.a).__name__ == "A"

    def test_scope_strict_missing_dep(self, tmp_path: Path):
        with _make_pkg(
            tmp_path,
            "pkg_scope_missing",
            {
                "mod.py": """
                    from pico_ioc import component
                    class NotBound: ...
                    @component
                    class NeedsMissing:
                        def __init__(self, dep: NotBound):
                            self.dep = dep
                """
            },
        ) as pkg:
            import importlib
            m = importlib.import_module("pkg_scope_missing.mod")
            c = scope(modules=[pkg], roots=[m.NeedsMissing], strict=True, lazy=True)
            with pytest.raises(NameError):
                _ = c.get(m.NeedsMissing)

    def test_scope_overrides_precedence(self, tmp_path: Path):
        with _make_pkg(
            tmp_path,
            "pkg_scope_override",
            {
                "mod.py": """
                    from pico_ioc import component
                    @component
                    class Repo:
                        def __init__(self): self.tag = "real"
                    @component
                    class Service:
                        def __init__(self, repo: Repo): self.repo = repo
                """
            },
        ) as pkg:
            import importlib
            m = importlib.import_module("pkg_scope_override.mod")

            class FakeRepo:
                def __init__(self):
                    self.tag = "fake"

            c = scope(
                modules=[pkg],
                roots=[m.Service],
                overrides={m.Repo: FakeRepo()},
                strict=True,
                lazy=True,
            )
            svc = c.get(m.Service)
            assert svc.repo.tag == "fake"

    def test_scope_lazy_vs_eager(self, tmp_path: Path):
        with _make_pkg(
            tmp_path,
            "pkg_scope_lazy",
            {
                "mod.py": """
                    from pico_ioc import component
                    CONSTRUCT = {"a": 0, "s": 0}
                    @component
                    class A:
                        def __init__(self):
                            CONSTRUCT["a"] += 1
                    @component
                    class S:
                        def __init__(self, a: A):
                            CONSTRUCT["s"] += 1
                            self.a = a
                """
            },
        ) as pkg:
            import importlib
            m = importlib.import_module("pkg_scope_lazy.mod")

            c_lazy = scope(modules=[pkg], roots=[m.S], strict=True, lazy=True)
            assert m.CONSTRUCT["a"] == 0 and m.CONSTRUCT["s"] == 0
            _ = c_lazy.get(m.S)
            assert m.CONSTRUCT["s"] == 1 and m.CONSTRUCT["a"] == 1

            m.CONSTRUCT["a"] = 0
            m.CONSTRUCT["s"] = 0
            c_eager = scope(modules=[pkg], roots=[m.S], strict=True, lazy=False)
            _ = c_eager.get(m.S)
            assert m.CONSTRUCT["s"] >= 1 and m.CONSTRUCT["a"] >= 1

    def test_scope_collections_and_qualifiers(self, tmp_path: Path):
        with _make_pkg(
            tmp_path,
            "pkg_scope_qual",
            {
                "mod.py": """
                    from typing import Protocol, Annotated, List
                    from pico_ioc import component, Qualifier, qualifier

                    class H(Protocol):
                        def x(self) -> str: ...

                    PAY = Qualifier("payments")

                    @component
                    @qualifier(PAY)
                    class Stripe:
                        def x(self) -> str: return "stripe"

                    @component
                    @qualifier(PAY)
                    class Paypal:
                        def x(self) -> str: return "paypal"

                    @component
                    class OrchestratorAll:
                        def __init__(self, handlers: list[H]):
                            self.handlers = handlers

                    @component
                    class OrchestratorPay:
                        def __init__(self, handlers: list[Annotated[H, PAY]]):
                            self.handlers = handlers
                """
            },
        ) as pkg:
            import importlib
            m = importlib.import_module("pkg_scope_qual.mod")
            c = scope(
                modules=[pkg],
                roots=[m.OrchestratorAll, m.OrchestratorPay],
                strict=True,
                lazy=True,
            )

            all_ = c.get(m.OrchestratorAll)
            pay = c.get(m.OrchestratorPay)

            names_all = {type(h).__name__ for h in all_.handlers}
            names_pay = {type(h).__name__ for h in pay.handlers}

            assert names_all == {"Stripe", "Paypal"}
            assert names_pay == {"Stripe", "Paypal"}

    def test_scope_context_manager(self, tmp_path: Path):
        with _make_pkg(
            tmp_path, "pkg_scope_ctx", {"mod.py": """
                from pico_ioc import component
                @component
                class A: pass
            """}
        ) as pkg:
            import importlib
            m = importlib.import_module("pkg_scope_ctx.mod")
            with scope(modules=[pkg], roots=[m.A]) as c:
                a = c.get(m.A)
                assert type(a).__name__ == "A"
