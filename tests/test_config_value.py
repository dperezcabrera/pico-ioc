import os
from dataclasses import dataclass
from typing import Annotated, Union

import pytest

from pico_ioc import DictSource, Discriminator, EnvSource, Value, configuration, configured, init


@configured(prefix="TEST_", mapping="flat", lazy=True)
@dataclass(frozen=True)
class FlatValueConfig:
    host: str
    port: Annotated[int, Value(9090)]
    timeout: Annotated[int, Value(30)]


def test_value_overrides_flat_sources():
    os.environ["TEST_HOST"] = "env.host.com"
    os.environ["TEST_PORT"] = "1234"
    os.environ["TEST_TIMEOUT"] = "10"

    ctx = configuration(EnvSource(prefix=""))
    container = init(modules=[__name__], config=ctx)
    cfg = container.get(FlatValueConfig)

    assert cfg.host == "env.host.com"
    assert cfg.port == 9090
    assert cfg.timeout == 30

    del os.environ["TEST_HOST"]
    del os.environ["TEST_PORT"]
    del os.environ["TEST_TIMEOUT"]


@configured(prefix="tree", mapping="tree", lazy=True)
@dataclass(frozen=True)
class TreeValueConfig:
    host: str
    port: Annotated[int, Value(9090)]
    timeout: Annotated[int, Value(30)]


def test_value_overrides_tree_sources():
    source_data = {"tree": {"host": "dict.host.com", "port": 1234, "timeout": 10}}
    ctx = configuration(DictSource(source_data))
    container = init(modules=[__name__], config=ctx)
    cfg = container.get(TreeValueConfig)

    assert cfg.host == "dict.host.com"
    assert cfg.port == 9090
    assert cfg.timeout == 30


@configured(prefix="TEST_", mapping="flat", lazy=True)
@dataclass(frozen=True)
class FlatPrecedenceConfig:
    port: Annotated[int, Value(9090)]


def test_value_has_highest_precedence_over_overrides_and_env():
    os.environ["TEST_PORT"] = "1234"

    ctx = configuration(EnvSource(prefix=""), overrides={"TEST_PORT": 5555})
    container = init(modules=[__name__], config=ctx)
    cfg = container.get(FlatPrecedenceConfig)

    assert cfg.port == 9090

    del os.environ["TEST_PORT"]


@configured(prefix="tree", mapping="tree", lazy=True)
@dataclass(frozen=True)
class TreePrecedenceConfig:
    port: Annotated[int, Value(9090)]


def test_value_has_highest_precedence_over_overrides_and_dict():
    source_data = {"tree": {"port": 1234}}
    ctx = configuration(DictSource(source_data), overrides={"tree.port": 5555})
    container = init(modules=[__name__], config=ctx)
    cfg = container.get(TreePrecedenceConfig)

    assert cfg.port == 9090


@dataclass(frozen=True)
class NestedStatic:
    id: str = "static"


@configured(prefix="tree", mapping="tree", lazy=True)
@dataclass(frozen=True)
class ComplexValueConfig:
    nested: Annotated[NestedStatic, Value(NestedStatic(id="forced"))]


def test_value_can_be_complex_object():
    source_data = {"tree": {"nested": {"id": "dynamic"}}}
    ctx = configuration(DictSource(source_data))
    container = init(modules=[__name__], config=ctx)
    cfg = container.get(ComplexValueConfig)

    assert isinstance(cfg.nested, NestedStatic)
    assert cfg.nested.id == "forced"


@dataclass
class Postgres:
    kind: str
    host: str


@dataclass
class Sqlite:
    kind: str
    path: str


@configured(prefix="db", mapping="tree", lazy=True)
@dataclass
class DiscriminatorValueConfig:
    model: Annotated[Union[Postgres, Sqlite], Discriminator("kind"), Value("Sqlite")]


def test_value_can_force_discriminator_kind():
    source_data = {"db": {"model": {"path": "/data/db.sqlite"}}}
    ctx = configuration(DictSource(source_data))
    container = init(modules=[__name__], config=ctx)
    cfg = container.get(DiscriminatorValueConfig)

    assert isinstance(cfg.model, Sqlite)
    assert cfg.model.kind == "Sqlite"
    assert cfg.model.path == "/data/db.sqlite"
