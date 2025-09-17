import types
from pico_ioc import component, factory_component, provides, on_missing, primary, conditional

def make_pkg(name: str, *definitions) -> types.ModuleType:
    pkg = types.ModuleType(name)
    for d in definitions:
        if hasattr(d, '__name__'):
            setattr(pkg, d.__name__, d)
    return pkg

class BaseService: ...

@component
class ServiceImpl(BaseService): ...

@component
class ServiceConsumer:
    def __init__(self, svc: BaseService):
        self.svc = svc

class Storage: ...
class LocalStorage(Storage): ...
class S3Storage(Storage): ...

@component
class AppWithStorage:
    def __init__(self, storage: Storage):
        self.storage = storage

class Logger: ...
class ConsoleLogger(Logger): ...
class FileLogger(Logger): ...

@component
class AppWithLogger:
    def __init__(self, logger: Logger):
        self.logger = logger

class MQ: ...
class RedisMQ(MQ): ...
class InMemoryMQ(MQ): ...

@component
class AppWithMQ:
    def __init__(self, mq: MQ):
        self.mq = mq
