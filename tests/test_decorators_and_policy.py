# tests/test_decorators_and_policy.py
import types
import pytest
from pico_ioc import init, component, factory_component, provides, on_missing, primary, conditional, reset

# --- Test Setup ---
class Storage: ...
class LocalStorage(Storage): ...
class S3Storage(Storage): ...
class Logger: ...
class ConsoleLogger(Logger): ...
class FileLogger(Logger): ...
class MQ: ...
class RedisMQ(MQ): ...
class InMemoryMQ(MQ): ...

@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield
    reset()

# --- @on_missing and @primary Tests ---

def test_on_missing_is_used_when_no_other_component_is_active():
    pkg = types.ModuleType("pkg_default")
    
    @component
    @on_missing(Storage)
    class DefaultStorage(LocalStorage): pass
    
    @component
    class App:
        def __init__(self, storage: Storage): self.storage = storage

    pkg.__dict__.update(locals())
    container = init(pkg, reuse=False)
    
    assert isinstance(container.get(App).storage, DefaultStorage)
    assert isinstance(container.get(Storage), DefaultStorage)

def test_primary_component_overrides_regular_and_on_missing():
    pkg = types.ModuleType("pkg_primary_wins")

    @component
    class RegularLogger(ConsoleLogger): pass
   
    @component
    @on_missing(Logger)
    class DefaultLogger(ConsoleLogger): pass

    @component
    @primary
    class PrimaryLogger(FileLogger): pass
    
    @component
    class App:
        def __init__(self, logger: Logger): self.logger = logger

    pkg.__dict__.update(locals())
    container = init(pkg, reuse=False)
    
    assert isinstance(container.get(App).logger, PrimaryLogger)
    assert isinstance(container.get(Logger), PrimaryLogger)

def test_on_missing_selects_by_highest_priority():
    pkg = types.ModuleType("pkg_priority")

    # FIX: Stack decorators on separate lines.
    @component
    @on_missing(Logger, priority=1)
    class LowPriorityLogger(ConsoleLogger): pass

    # FIX: Stack decorators on separate lines.
    @component
    @on_missing(Logger, priority=10)
    class HighPriorityLogger(FileLogger): pass
    
    @component
    class App:
        def __init__(self, logger: Logger): self.logger = logger
    
    pkg.__dict__.update(locals())
    container = init(pkg, reuse=False)
    assert isinstance(container.get(Logger), HighPriorityLogger)

# --- @conditional Tests ---

def test_conditional_by_profile_selects_implementation():
    pkg = types.ModuleType("pkg_profile")

    # FIX: Stack decorators on separate lines.
    @component
    @conditional(profiles=["dev"])
    class DevStorage(LocalStorage): pass

    # FIX: Stack decorators on separate lines.
    @component
    @conditional(profiles=["prod"])
    class ProdStorage(S3Storage): pass
    
    @component
    class App:
        def __init__(self, storage: Storage): self.storage = storage
    
    pkg.__dict__.update(locals())
    
    c_prod = init(pkg, profiles=["prod"], reuse=False)
    assert isinstance(c_prod.get(App).storage, ProdStorage)

    c_dev = init(pkg, profiles=["dev"], reuse=False)
    assert isinstance(c_dev.get(App).storage, DevStorage)

def test_conditional_by_env_var_selects_implementation(monkeypatch):
    pkg = types.ModuleType("pkg_env")

    # FIX: Stack decorators on separate lines.
    @component
    @conditional(require_env=["USE_S3"])
    class ConditionalS3(S3Storage): pass
    
    # FIX: Stack decorators on separate lines.
    @component
    @on_missing(Storage)
    class DefaultLocal(LocalStorage): pass
    
    @component
    class App:
        def __init__(self, storage: Storage): self.storage = storage

    pkg.__dict__.update(locals())
    
    monkeypatch.delenv("USE_S3", raising=False)
    c1 = init(pkg, reuse=False)
    assert isinstance(c1.get(App).storage, DefaultLocal)

    monkeypatch.setenv("USE_S3", "true")
    c2 = init(pkg, reuse=False)
    assert isinstance(c2.get(App).storage, ConditionalS3)

@pytest.mark.parametrize("case, predicate_result, expected_impl", [
    ("true", lambda: True, RedisMQ),
    ("false", lambda: False, InMemoryMQ),
    ("error", lambda: (_ for _ in ()).throw(RuntimeError("boom")), InMemoryMQ),
])
def test_conditional_by_predicate(case, predicate_result, expected_impl):
    module_name = f"pkg_predicate_{case}"
    pkg = types.ModuleType(module_name)

    # FIX: Stack decorators on separate lines.
    @component
    @conditional(predicate=predicate_result)
    class ConditionalRedis(RedisMQ): pass
    
    # FIX: Stack decorators on separate lines.
    @component
    @on_missing(MQ)
    class DefaultInMemory(InMemoryMQ): pass

    @component
    class App:
        def __init__(self, mq: MQ): self.mq = mq

    pkg.__dict__.update(locals())
    
    container = init(pkg, reuse=False)
    assert isinstance(container.get(App).mq, expected_impl)

# --- Factory Tests ---

def test_factory_provides_with_primary_breaks_tie():
    pkg = types.ModuleType("pkg_factory_primary")
    
    @factory_component
    class LoggerFactory:
        @provides(Logger)
        def console(self) -> Logger: return ConsoleLogger()
        
        @provides(Logger)
        @primary
        def file(self) -> Logger: return FileLogger()
        
    @component
    class App:
        def __init__(self, logger: Logger): self.logger = logger
    
    pkg.__dict__.update(locals())
    container = init(pkg, reuse=False)
    assert isinstance(container.get(Logger), FileLogger)
    
def test_factory_provides_is_selected_by_profile():
    pkg = types.ModuleType("pkg_factory_profile")

    @factory_component
    class MQFactory:
        # FIX: Stack decorators on separate lines.
        @provides(MQ)
        @conditional(profiles=["prod"])
        def redis(self) -> MQ: return RedisMQ()
        
        # FIX: Stack decorators on separate lines.
        @provides(MQ)
        @conditional(profiles=["dev"])
        def in_memory(self) -> MQ: return InMemoryMQ()
    
    @component
    class App:
        def __init__(self, mq: MQ): self.mq = mq
    
    pkg.__dict__.update(locals())

    c_prod = init(pkg, profiles=["prod"], reuse=False)
    assert isinstance(c_prod.get(App).mq, RedisMQ)

    c_dev = init(pkg, profiles=["dev"], reuse=False)
    assert isinstance(c_dev.get(App).mq, InMemoryMQ)
