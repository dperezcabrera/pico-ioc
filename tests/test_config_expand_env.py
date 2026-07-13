"""${VAR:default} placeholder expansion in tree sources."""

import json

import pytest

from pico_ioc import DictSource, JsonTreeSource, YamlTreeSource, expand_env


def test_expand_env_resolves_set_var(monkeypatch):
    monkeypatch.setenv("DB_URL", "postgres://real")
    assert expand_env("${DB_URL}") == "postgres://real"


def test_expand_env_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("MISSING", raising=False)
    assert expand_env("${MISSING:sqlite://x}") == "sqlite://x"


def test_expand_env_empty_when_unset_no_default(monkeypatch):
    monkeypatch.delenv("MISSING", raising=False)
    assert expand_env("${MISSING}") == ""


def test_expand_env_recurses_dicts_and_lists(monkeypatch):
    monkeypatch.setenv("H", "host")
    tree = {"db": {"url": "${H}:5432", "opts": ["${H}", "static"]}}
    assert expand_env(tree) == {"db": {"url": "host:5432", "opts": ["host", "static"]}}


def test_expand_env_leaves_non_strings(monkeypatch):
    assert expand_env({"port": 5432, "on": True}) == {"port": 5432, "on": True}


def test_dict_source_off_by_default(monkeypatch):
    monkeypatch.setenv("X", "y")
    assert DictSource({"a": "${X}"}).get_tree() == {"a": "${X}"}
    assert DictSource({"a": "${X}"}, expand_env=True).get_tree() == {"a": "y"}


def test_yaml_source_expands(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    cfg = tmp_path / "app.yaml"
    cfg.write_text("auth:\n  password: ${ADMIN_PASSWORD:change-me}\n  db: ${DB:sqlite://d}\n", encoding="utf-8")
    tree = YamlTreeSource(str(cfg), expand_env=True).get_tree()
    assert tree == {"auth": {"password": "s3cret", "db": "sqlite://d"}}
    # sin el flag, el placeholder llega crudo
    assert YamlTreeSource(str(cfg)).get_tree()["auth"]["password"] == "${ADMIN_PASSWORD:change-me}"


def test_json_source_expands(tmp_path, monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    cfg = tmp_path / "app.json"
    cfg.write_text(json.dumps({"server": {"port": "${PORT:8000}"}}), encoding="utf-8")
    assert JsonTreeSource(str(cfg), expand_env=True).get_tree() == {"server": {"port": "8000"}}
