"""Tests for PEP 563 compatibility (from __future__ import annotations).

When `from __future__ import annotations` is active, all type hints become
strings at runtime. pico-ioc must resolve them via typing.get_type_hints().
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from typing import List, Optional

import pytest

from pico_ioc import component, configuration, configure, configured, factory, init, provides
from pico_ioc.analysis import analyze_callable_dependencies
from pico_ioc.config_runtime import DictSource
from pico_ioc.decorators import get_return_type

# --- Plain classes (not decorated) for unit tests ---


class Repo:
    pass


class Service:
    def __init__(self, repo: Repo):
        self.repo = repo


class OptionalService:
    def __init__(self, repo: Repo, name: Optional[str] = None):
        self.repo = repo
        self.name = name


class ListService:
    def __init__(self, repos: List[Repo]):
        self.repos = repos


# --- Unit Tests: analyze_callable_dependencies ---


class TestAnalyzeCallableDependencies:
    def test_resolves_string_annotations(self):
        deps = analyze_callable_dependencies(Service.__init__)
        assert len(deps) == 1
        assert deps[0].parameter_name == "repo"
        assert deps[0].key is Repo

    def test_resolves_optional_annotations(self):
        deps = analyze_callable_dependencies(OptionalService.__init__)
        assert len(deps) == 2
        repo_dep = next(d for d in deps if d.parameter_name == "repo")
        name_dep = next(d for d in deps if d.parameter_name == "name")
        assert repo_dep.key is Repo
        assert name_dep.is_optional

    def test_resolves_list_annotations(self):
        deps = analyze_callable_dependencies(ListService.__init__)
        assert len(deps) == 1
        assert deps[0].is_list
        assert deps[0].key is Repo


# --- Unit Tests: get_return_type ---


class TestGetReturnType:
    def test_resolves_string_return_type(self):
        def make_repo() -> Repo:
            return Repo()

        assert get_return_type(make_repo) is Repo

    def test_none_for_no_return(self):
        def no_return():
            pass

        assert get_return_type(no_return) is None


# --- Integration Tests: container with components ---

# These are defined at module level so init(modules=[__name__]) can scan them.
# Only compatible components here — no @configured (needs config).


@component
class FutureRepo:
    pass


@component
class FutureService:
    def __init__(self, repo: FutureRepo):
        self.repo = repo


@factory
class FutureFactory:
    @provides
    def create_repo(self) -> Repo:
        return Repo()


class TestContainerIntegration:
    def test_component_injection(self):
        container = init(modules=[__name__])
        service = container.get(FutureService)
        assert isinstance(service, FutureService)
        assert isinstance(service.repo, FutureRepo)

    def test_factory_provides(self):
        container = init(modules=[__name__])
        repo = container.get(Repo)
        assert isinstance(repo, Repo)


# --- Integration Test: @configured dataclass ---


@dataclass
class AppSettings:
    host: str = "localhost"
    port: int = 8080
    debug: bool = False


class TestConfiguredDataclass:
    def test_dataclass_from_config(self):
        @configured(target=AppSettings, prefix="app", mapping="tree")
        class ConfiguredAppSettings:
            pass

        mod = types.ModuleType("test_future_cfg")
        setattr(mod, "ConfiguredAppSettings", ConfiguredAppSettings)

        cfg = configuration(DictSource({"app": {"host": "0.0.0.0", "port": 9090, "debug": True}}))
        container = init(modules=[mod], config=cfg)
        settings = container.get(AppSettings)
        assert settings.host == "0.0.0.0"
        assert settings.port == 9090
        assert settings.debug is True
