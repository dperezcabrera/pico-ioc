# tests/test_defaults_and_overrides.py
from types import ModuleType
import pytest

from pico_ioc import init, component, on_missing, primary

# --- Test Components ---
class Logger:
    def log(self, message: str): ...

@component
@on_missing(Logger)
class ConsoleLogger(Logger):
    def log(self, message: str):
        print(f"[DEFAULT LOG]: {message}")

@component
class LibraryService:
    def __init__(self, logger: Logger):
        self._logger = logger
    def do_work(self):
        self._logger.log("LibraryService is working...")

@component
@primary
class FileLogger(Logger):
    def __init__(self):
        self.last_message = ""
    def log(self, message: str):
        self.last_message = message

# --- Tests ---
def test_init_uses_default_provider_when_no_override_is_present(capsys):
    # This test proves `apply_defaults` is necessary.
    # The scanner will only register `ConsoleLogger`, not its base `Logger`.
    # `apply_defaults` must run to create the alias for `Logger`.
    library_module = ModuleType("library_module")
    library_module.__dict__.update({
        "Logger": Logger,
        "ConsoleLogger": ConsoleLogger,
        "LibraryService": LibraryService,
    })

    container = init(root_package=library_module)
    service = container.get(LibraryService)
    service.do_work()

    captured = capsys.readouterr()
    assert "[DEFAULT LOG]: LibraryService is working..." in captured.out
    assert isinstance(container.get(Logger), ConsoleLogger)


def test_init_uses_primary_provider_when_override_is_present():
    # This test proves that `@primary` components take precedence.
    # The scanner will register `FileLogger` and also alias it to `Logger`
    # because it is primary. `apply_defaults` will then do nothing.
    combined_module = ModuleType("combined_module")
    combined_module.__dict__.update({
        "Logger": Logger,
        "ConsoleLogger": ConsoleLogger,
        "FileLogger": FileLogger,
        "LibraryService": LibraryService,
    })
    
    container = init(root_package=combined_module)
    service = container.get(LibraryService)
    service.do_work()

    logger_instance = container.get(Logger)
    assert isinstance(logger_instance, FileLogger)
    assert logger_instance.last_message == "LibraryService is working..."
