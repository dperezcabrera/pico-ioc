import pytest
from pico_ioc import init, on_missing, primary, conditional, component, factory_component, provides

from tests.helpers import (
    make_pkg,
    Storage, LocalStorage, S3Storage, AppWithStorage,
    Logger, ConsoleLogger, FileLogger, AppWithLogger,
    MQ, RedisMQ, InMemoryMQ, AppWithMQ,
)

def test_on_missing_is_used_when_no_other_component_is_active():
    @component
    @on_missing(Storage)
    class DefaultStorage(LocalStorage): pass

    pkg = make_pkg("pkg_default", DefaultStorage, AppWithStorage)
    container = init(pkg)
    assert isinstance(container.get(AppWithStorage).storage, DefaultStorage)

def test_primary_overrides_others():
    @component 
    class RegularLogger(ConsoleLogger): pass
    
    @component 
    @on_missing(Logger) 
    class DefaultLogger(ConsoleLogger): pass
    
    @component 
    @primary 
    class PrimaryLogger(FileLogger): pass
    
    pkg = make_pkg("pkg_primary", RegularLogger, DefaultLogger, PrimaryLogger, AppWithLogger)
    container = init(pkg)
    assert isinstance(container.get(AppWithLogger).logger, PrimaryLogger)

def test_on_missing_selects_by_highest_priority():
    @component
    @on_missing(Logger, priority=1)
    class LowPriority(ConsoleLogger): pass

    @component
    @on_missing(Logger, priority=10)
    class HighPriority(FileLogger): pass

    pkg = make_pkg("pkg_prio", LowPriority, HighPriority, AppWithLogger)
    container = init(pkg)
    assert isinstance(container.get(Logger), HighPriority)

def test_conditional_by_profile():
    @component
    @conditional(profiles=["dev"])
    class DevStorage(LocalStorage): pass

    @component
    @conditional(profiles=["prod"])
    class ProdStorage(S3Storage): pass

    pkg = make_pkg("pkg_profile", DevStorage, ProdStorage, AppWithStorage)
    
    c_prod = init(pkg, profiles=["prod"], reuse=False)
    assert isinstance(c_prod.get(AppWithStorage).storage, ProdStorage)

    c_dev = init(pkg, profiles=["dev"], reuse=False)
    assert isinstance(c_dev.get(AppWithStorage).storage, DevStorage)

def test_conditional_by_env_var(monkeypatch):
    @component
    @conditional(require_env=["USE_S3"])
    class ConditionalS3(S3Storage): pass
    
    @component
    @on_missing(Storage)
    class DefaultLocal(LocalStorage): pass
    
    pkg = make_pkg("pkg_env", ConditionalS3, DefaultLocal, AppWithStorage)

    monkeypatch.delenv("USE_S3", raising=False)
    c1 = init(pkg, reuse=False)
    assert isinstance(c1.get(AppWithStorage).storage, DefaultLocal)

    monkeypatch.setenv("USE_S3", "true")
    c2 = init(pkg, reuse=False)
    assert isinstance(c2.get(AppWithStorage).storage, ConditionalS3)

@pytest.mark.parametrize(
    "case, predicate_result, expected_impl",
    [
        ("true", lambda: True, RedisMQ),
        ("false", lambda: False, InMemoryMQ),
        ("error", lambda: (_ for _ in ()).throw(RuntimeError("boom")), InMemoryMQ),
    ],
)
def test_conditional_by_predicate(case, predicate_result, expected_impl):
    @component
    @conditional(predicate=predicate_result)
    class ConditionalRedis(RedisMQ): pass

    @component
    @on_missing(MQ)
    class DefaultInMemory(InMemoryMQ): pass
    
    pkg = make_pkg(f"pkg_pred_{case}", ConditionalRedis, DefaultInMemory, AppWithMQ)
    container = init(pkg)
    assert isinstance(container.get(AppWithMQ).mq, expected_impl)

def test_factory_provides_primary_for_logger():
    @factory_component
    class LoggerFactory:
        @provides(Logger)
        def console(self) -> Logger: return ConsoleLogger()
        
        @provides(Logger)
        @primary
        def file(self) -> Logger: return FileLogger()

    pkg = make_pkg("pkg_logger_factory", LoggerFactory, AppWithLogger)
    
    container = init(pkg, reuse=False)
    
    assert isinstance(container.get(AppWithLogger).logger, FileLogger)
    
def test_factory_provides_conditional_for_mq():
    @factory_component
    class MqFactory:
        @provides(MQ)
        @conditional(profiles=["prod"])
        def redis(self) -> MQ: return RedisMQ()
        
        @provides(MQ)
        @conditional(profiles=["dev"])
        def in_memory(self) -> MQ: return InMemoryMQ()

    pkg = make_pkg("pkg_mq_factory", MqFactory, AppWithMQ)

    c_prod = init(pkg, profiles=["prod"], reuse=False)
    assert isinstance(c_prod.get(AppWithMQ).mq, RedisMQ)

    c_dev = init(pkg, profiles=["dev"], reuse=False)
    assert isinstance(c_dev.get(AppWithMQ).mq, InMemoryMQ)
