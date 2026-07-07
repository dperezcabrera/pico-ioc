"""Hot config refresh: ConfigResolver.refresh, container.refresh_config, ConfigChanged."""

import types
from dataclasses import dataclass

from pico_ioc import ConfigChanged, DictSource, EventBus, configuration, configured, init
from pico_ioc.config_runtime import ConfigResolver


@dataclass
class DbSettings:
    host: str


def _app_module():
    @configured(target=DbSettings, prefix="db", mapping="tree")
    class ConfiguredDb:
        pass

    mod = types.ModuleType("refresh_test_mod")
    mod.ConfiguredDb = ConfiguredDb
    return mod


def test_refresh_returns_only_changed_top_level_prefixes():
    data = {"db": {"host": "a"}, "app": {"name": "x"}}
    r = ConfigResolver((DictSource(data),))
    assert r.tree()["db"]["host"] == "a"
    data["db"]["host"] = "b"
    assert r.refresh() == frozenset({"db"})
    assert r.tree()["db"]["host"] == "b"


def test_refresh_detects_added_and_removed_prefixes():
    data = {"db": {"host": "a"}}
    r = ConfigResolver((DictSource(data),))
    r.tree()
    del data["db"]
    data["cache"] = {"ttl": 5}
    assert r.refresh() == frozenset({"db", "cache"})


def test_refresh_without_changes_returns_empty_set():
    r = ConfigResolver((DictSource({"db": {"host": "a"}}),))
    r.tree()
    assert r.refresh() == frozenset()


def test_container_refresh_config_publishes_config_changed():
    data = {"db": {"host": "a"}}
    container = init(modules=[_app_module(), "pico_ioc.event_bus"], config=configuration(DictSource(data)))
    assert container.get(DbSettings).host == "a"
    seen = []
    container.get(EventBus).subscribe(ConfigChanged, seen.append)
    data["db"]["host"] = "b"
    assert container.refresh_config() == frozenset({"db"})
    assert [e.prefixes for e in seen] == [frozenset({"db"})]


def test_container_refresh_config_without_changes_publishes_nothing():
    container = init(
        modules=[_app_module(), "pico_ioc.event_bus"],
        config=configuration(DictSource({"db": {"host": "a"}})),
    )
    seen = []
    container.get(EventBus).subscribe(ConfigChanged, seen.append)
    assert container.refresh_config() == frozenset()
    assert seen == []


def test_container_refresh_config_without_config_is_noop():
    container = init(modules=[])
    assert container.refresh_config() == frozenset()
