# tests/test_config_injection.py
import types
import textwrap
import sys
import pytest
from dataclasses import dataclass

from pico_ioc import init, component
from pico_ioc import (
    config_component, EnvSource, FileSource,
    Env, File, Path, Value,
)
from pico_ioc.config import register_field_spec


def _make_pkg(name: str):
    """Dynamic module for scanning."""
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


def test_config_resolution_precedence_and_types(tmp_path, monkeypatch):
    pkg = _make_pkg("pkg_cfg_precedence")

    # property files (JSON to avoid PyYAML)
    (tmp_path / "config.json").write_text(textwrap.dedent(r"""
    {
      "DB_URL": "postgresql://file/db",
      "HTTP_TIMEOUT": 20,
      "DEBUG": false,
      "services": { "api": { "base": "https://file.example.com" } }
    }
    """).strip())
    (tmp_path / "config.dev.json").write_text('{"HTTP_TIMEOUT": 7, "DEBUG": true}')

    # env
    monkeypatch.setenv("APP_DB_URL", "postgresql://env/db")
    monkeypatch.setenv("APP_HTTP_TIMEOUT", "15")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("API_TOKEN", "secret-token")

    @config_component(prefix="APP_")
    @component
    @dataclass(frozen=True)
    class Settings:
        db_url: str = "sqlite:///default.db"
        http_timeout: int = 10
        debug: bool = False
        token: str = ""
        api_base: str = "http://localhost:8000"

    # field overrides
    register_field_spec(Settings, "token", Env["API_TOKEN", ""])
    register_field_spec(Settings, "db_url", Value["DB_URL"](sources=("file", "env")))
    register_field_spec(Settings, "api_base", Path.file["services.api.base", "http://localhost"])

    @component
    class Repo:
        def __init__(self, s: Settings):
            self.url = s.db_url
            self.timeout = s.http_timeout
            self.debug = s.debug
            self.token = s.token
            self.api_base = s.api_base

    pkg.Settings = Settings
    pkg.Repo = Repo

    c = init(
        pkg,
        profiles=("dev",),
        config=(
            EnvSource(prefix="APP_"),
            FileSource(tmp_path / "config.json"),
            FileSource(tmp_path / "config.dev.json"),
        ),
    )

    repo = c.get(Repo)
    assert repo.url == "postgresql://file/db"          # file > env
    assert repo.timeout == 15 and isinstance(repo.timeout, int)  # env int
    assert repo.debug is True                          # env bool
    assert repo.token == "secret-token"                # explicit Env
    assert repo.api_base == "https://file.example.com" # dotted path


def test_path_file_dotted_keys(tmp_path, monkeypatch):
    pkg = _make_pkg("pkg_cfg_pathfile")

    (tmp_path / "app.json").write_text(textwrap.dedent("""
      {
        "services": {
          "cache": { "ttl": 42 },
          "api":   { "base": "https://api.example.org" }
        }
      }
    """))

    @config_component(prefix="APP_")
    @component
    @dataclass(frozen=True)
    class Settings:
        ttl: int = 5
        base_url: str = "http://localhost"

    register_field_spec(Settings, "ttl", Path.file["services.cache.ttl", 5])
    register_field_spec(Settings, "base_url", Path.file["services.api.base", "http://localhost"])

    @component
    class Svc:
        def __init__(self, s: Settings):
            self.ttl = s.ttl
            self.base = s.base_url

    pkg.Settings = Settings
    pkg.Svc = Svc

    c = init(pkg, config=(FileSource(tmp_path / "app.json"),))
    svc = c.get(Svc)
    assert svc.ttl == 42 and isinstance(svc.ttl, int)
    assert svc.base == "https://api.example.org"


def test_missing_required_field_raises(tmp_path, monkeypatch):
    pkg = _make_pkg("pkg_cfg_missing")

    @config_component(prefix="APP_")
    @component(lazy=True)  # defer instantiation
    @dataclass(frozen=True)
    class StrictSettings:
        required_key: str  # required

    pkg.StrictSettings = StrictSettings
    c = init(pkg, config=())

    s = c.get(StrictSettings)  # proxy returned
    with pytest.raises(NameError) as ei:
        _ = s.required_key      # triggers real build -> NameError
    assert "Missing config for field StrictSettings.required_key" in str(ei.value)




def test_lazy_component_does_not_instantiate_until_used(tmp_path, monkeypatch):
    pkg = _make_pkg("pkg_cfg_lazy")

    (tmp_path / "cfg.ini").write_text("[DEFAULT]\nHTTP_TIMEOUT = 25\n")

    events = []

    @config_component(prefix="APP_")
    @component
    @dataclass(frozen=True)
    class Settings:
        http_timeout: int = 10

    @component(lazy=True)
    class ExpensiveRepo:
        def __init__(self, s: Settings):
            events.append(("created", s.http_timeout))
            self.timeout = s.http_timeout

    pkg.Settings = Settings
    pkg.ExpensiveRepo = ExpensiveRepo

    c = init(pkg, config=(FileSource(tmp_path / "cfg.ini"),))

    # not created yet (lazy)
    assert ("created", 25) not in events

    r = c.get(ExpensiveRepo)  # returns proxy
    _ = r.timeout              # force real instantiation
    assert ("created", 25) in events
    assert r.timeout == 25

