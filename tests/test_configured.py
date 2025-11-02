import pytest
import sys
import json
import types
from dataclasses import dataclass
from typing import List, Dict, Union, Annotated, Optional

from pico_ioc import (
    init,
    configured,
    component,
    configuration,
    DictSource,
    JsonTreeSource,
    YamlTreeSource,
    Discriminator,
    ComponentCreationError,
    ConfigurationError,
)

@dataclass
class DBSettings:
    host: str
    port: int
    user: Optional[str] = "default"

@dataclass
class RedisSettings:
    url: str

@dataclass
class CacheSettings:
    ttl: int
    redis: RedisSettings

@dataclass
class FeatureConfig:
    features: List[str]

@dataclass
class User:
    name: str

@dataclass
class UserList:
    users: List[User]

@dataclass
class HeadersConfig:
    headers: Dict[str, str]

class SimpleService:
    def __init__(self, endpoint: str, timeout: int = 10):
        self.endpoint = endpoint
        self.timeout = timeout

@dataclass
class Cat:
    name: str
    lives: int = 9

@dataclass
class Dog:
    name: str
    breed: str

@dataclass
class PetOwnerDefault:
    pet: Union[Cat, Dog]

@dataclass
class PetOwnerCustom:
    pet: Annotated[Union[Cat, Dog], Discriminator("animal_type")]

@pytest.fixture
def temp_json_file(tmp_path):
    file_path = tmp_path / "config.json"
    def _create(data: dict):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return str(file_path)
    return _create

@pytest.fixture
def temp_yaml_file(tmp_path):
    file_path = tmp_path / "config.yaml"
    def _create(data: str):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(data)
        return str(file_path)
    return _create

def test_configured_basic_dataclass():
    @configured(target=DBSettings, prefix="db")
    class ConfiguredDBSettings:
        pass
    
    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredDBSettings", ConfiguredDBSettings)

    config_data = {"db": {"host": "localhost", "port": 5432}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    settings = container.get(DBSettings)
    
    assert isinstance(settings, DBSettings)
    assert settings.host == "localhost"
    assert settings.port == 5432
    assert settings.user == "default"

def test_configured_nested_dataclass():
    @configured(target=CacheSettings, prefix="cache")
    class ConfiguredCacheSettings:
        pass

    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredCacheSettings", ConfiguredCacheSettings)

    config_data = {"cache": {"ttl": 3600, "redis": {"url": "redis://host:6379"}}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    settings = container.get(CacheSettings)
    
    assert isinstance(settings, CacheSettings)
    assert settings.ttl == 3600
    assert isinstance(settings.redis, RedisSettings)
    assert settings.redis.url == "redis://host:6379"

def test_configured_list_of_primitives():
    @configured(target=FeatureConfig, prefix="app")
    class ConfiguredFeatureConfig:
        pass
        
    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredFeatureConfig", ConfiguredFeatureConfig)
    
    config_data = {"app": {"features": ["foo", "bar", "baz"]}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    config = container.get(FeatureConfig)
    
    assert isinstance(config, FeatureConfig)
    assert config.features == ["foo", "bar", "baz"]

def test_configured_list_of_dataclasses():
    @configured(target=UserList, prefix="user_config")
    class ConfiguredUserList:
        pass

    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredUserList", ConfiguredUserList)

    config_data = {"user_config": {"users": [{"name": "Alice"}, {"name": "Bob"}]}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    config = container.get(UserList)
    
    assert isinstance(config, UserList)
    assert len(config.users) == 2
    assert isinstance(config.users[0], User)
    assert config.users[0].name == "Alice"
    assert config.users[1].name == "Bob"

def test_configured_dict():
    @configured(target=HeadersConfig, prefix="api")
    class ConfiguredHeadersConfig:
        pass

    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredHeadersConfig", ConfiguredHeadersConfig)
    
    config_data = {"api": {"headers": {"X-Auth": "token123", "User-Agent": "pico"}}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    config = container.get(HeadersConfig)
    
    assert isinstance(config, HeadersConfig)
    assert config.headers == {"X-Auth": "token123", "User-Agent": "pico"}

def test_configured_plain_class_init():
    @configured(target=SimpleService, prefix="service")
    class ConfiguredSimpleService:
        pass

    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredSimpleService", ConfiguredSimpleService)

    config_data = {"service": {"endpoint": "http://api.com", "timeout": 5}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    service = container.get(SimpleService)
    
    assert isinstance(service, SimpleService)
    assert service.endpoint == "http://api.com"
    assert service.timeout == 5

def test_configured_json_tree_source(temp_json_file):
    @configured(target=DBSettings, prefix="db_file")
    class ConfiguredDBSettingsFile:
        pass

    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredDBSettingsFile", ConfiguredDBSettingsFile)
    
    config_path = temp_json_file({"db_file": {"host": "file.host", "port": 1234, "user": "file_user"}})
    ctx = configuration(JsonTreeSource(config_path))
    container = init(modules=[mod], config=ctx)
    settings = container.get(DBSettings)
    
    assert isinstance(settings, DBSettings)
    assert settings.host == "file.host"
    assert settings.port == 1234
    assert settings.user == "file_user"

def test_configured_yaml_tree_source(temp_yaml_file):
    yaml = pytest.importorskip("yaml")
    
    @configured(target=DBSettings, prefix="db_yaml")
    class ConfiguredDBSettingsYaml:
        pass

    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredDBSettingsYaml", ConfiguredDBSettingsYaml)
    
    config_content = """
db_yaml:
  host: yaml.host
  port: 5678
"""
    config_path = temp_yaml_file(config_content)
    ctx = configuration(YamlTreeSource(config_path))
    container = init(modules=[mod], config=ctx)
    settings = container.get(DBSettings)
    
    assert isinstance(settings, DBSettings)
    assert settings.host == "yaml.host"
    assert settings.port == 5678

def test_configured_env_interpolation(monkeypatch):
    @configured(target=DBSettings, prefix="db_env")
    class ConfiguredDBSettingsEnv:
        pass

    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredDBSettingsEnv", ConfiguredDBSettingsEnv)

    monkeypatch.setenv("DB_HOST_ENV", "env.host")
    config_data = {"db_env": {"host": "${ENV:DB_HOST_ENV}", "port": 9999}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    settings = container.get(DBSettings)
    
    assert settings.host == "env.host"
    assert settings.port == 9999

def test_configured_ref_interpolation():
    @configured(target=DBSettings, prefix="db_ref")
    class ConfiguredDBSettingsRef:
        pass
        
    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredDBSettingsRef", ConfiguredDBSettingsRef)

    config_data = {"defaults": {"user": "ref_user"}, "db_ref": {"host": "ref.host", "port": 1111, "user": "${ref:defaults.user}"}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    settings = container.get(DBSettings)
    
    assert settings.host == "ref.host"
    assert settings.port == 1111
    assert settings.user == "ref_user"

def test_configured_error_on_missing_prefix():
    @configured(target=DBSettings, prefix="missing.prefix")
    class ConfiguredDBSettingsMissing:
        pass
        
    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredDBSettingsMissing", ConfiguredDBSettingsMissing)

    ctx = configuration(DictSource({}))
    
    with pytest.raises(ComponentCreationError) as e:
        init(modules=[mod], config=ctx)
        
    assert isinstance(e.value.cause, ConfigurationError)
    assert "Missing config prefix: missing.prefix" in str(e.value.cause)

def test_configured_union_default_discriminator():
    @configured(target=PetOwnerDefault, prefix="pet_owner_default")
    class ConfiguredPetOwnerDefault:
        pass
        
    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredPetOwnerDefault", ConfiguredPetOwnerDefault)

    config_data = {"pet_owner_default": {"pet": {"$type": "Cat", "name": "Fluffy"}}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    owner = container.get(PetOwnerDefault)
    
    assert isinstance(owner.pet, Cat)
    assert owner.pet.name == "Fluffy"

def test_configured_union_custom_discriminator():
    @configured(target=PetOwnerCustom, prefix="pet_owner_custom")
    class ConfiguredPetOwnerCustom:
        pass
        
    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredPetOwnerCustom", ConfiguredPetOwnerCustom)

    config_data = {"pet_owner_custom": {"pet": {"animal_type": "Dog", "name": "Buddy", "breed": "Labrador"}}}
    ctx = configuration(DictSource(config_data))
    container = init(modules=[mod], config=ctx)
    owner = container.get(PetOwnerCustom)
    
    assert isinstance(owner.pet, Dog)
    assert owner.pet.name == "Buddy"
    assert owner.pet.breed == "Labrador"

def test_configured_selects_existing_and_longest_prefix():
    @configured(target=DBSettings, prefix="db")
    class CfgA:
        pass
    @configured(target=DBSettings, prefix="db_prod")
    class CfgB:
        pass
        
    mod = types.ModuleType("test_mod")
    setattr(mod, "CfgA", CfgA)
    setattr(mod, "CfgB", CfgB)
    
    ctx = configuration(DictSource({"db_prod": {"host": "h", "port": 1}}))
    container = init([mod], config=ctx)
    s = container.get(DBSettings)
    
    assert s.host == "h"

def test_configured_sets_config_metadata():
    @configured(target=DBSettings, prefix="db")
    class ConfiguredDBSettings:
        pass
        
    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredDBSettings", ConfiguredDBSettings)

    data = {"db": {"host": "x", "port": 1}}
    ctx = configuration(DictSource(data))
    c = init([mod], config=ctx)
    s = c.get(DBSettings)
    meta = getattr(s, "_pico_meta")
    
    assert meta["config_prefix"] == "db"
    assert "config_hash" in meta
    assert tuple(meta["config_source_order"])

def test_union_wrong_discriminator_raises_clear_error():
    @configured(target=PetOwnerDefault, prefix="pet_owner_default")
    class ConfiguredPetOwnerDefault:
        pass

    mod = types.ModuleType("test_mod")
    setattr(mod, "ConfiguredPetOwnerDefault", ConfiguredPetOwnerDefault)

    data = {"pet_owner_default": {"pet": {"$type": "Bird", "name": "Kiwi"}}}
    ctx = configuration(DictSource(data))
    
    with pytest.raises(ComponentCreationError) as e:
        init([mod], config=ctx)
        
    assert "Discriminator $type did not match" in str(e.value.cause)

def test_configured_typed_dict_and_type_errors():
    @dataclass
    class D:
        m: Dict[str, int]
    @configured(target=D, prefix="d")
    class C:
        pass
        
    mod = types.ModuleType("test_mod")
    setattr(mod, "D", D)
    setattr(mod, "C", C)
    
    ctx = configuration(DictSource({"d": {"m": {"a": "1"}}}))
    c = init([mod], config=ctx)
    assert c.get(D).m == {"a": 1}

def test_string_injection_resolves_by_pico_name_or_classname():
    @component(name="SpecialWidget")
    class W:
        pass
    @component
    class Needs:
        def __init__(self, w: "SpecialWidget"):
            self.w = w
            
    mod = types.ModuleType("test_mod")
    setattr(mod, "W", W)
    setattr(mod, "Needs", Needs)
    
    c = init([mod])
    assert isinstance(c.get(Needs).w, W)
