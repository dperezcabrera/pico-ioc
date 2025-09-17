# tests/test_defaults.py
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
    library_components = {
        "Logger": Logger,
        "ConsoleLogger": ConsoleLogger,
        "LibraryService": LibraryService,
    }
    library_module = ModuleType("library_module")
    library_module.__dict__.update(library_components)

    container = init(root_package=library_module)
    service = container.get(LibraryService)
    service.do_work()

    captured = capsys.readouterr()
    assert "[DEFAULT LOG]: LibraryService is working..." in captured.out
    assert isinstance(container.get(Logger), ConsoleLogger)


def test_init_uses_primary_provider_when_override_is_present():
    combined_components = {
        "Logger": Logger,
        "ConsoleLogger": ConsoleLogger,
        "FileLogger": FileLogger,
        "LibraryService": LibraryService,
    }
    combined_module = ModuleType("combined_module")
    combined_module.__dict__.update(combined_components)
    
    container = init(root_package=combined_module)
    service = container.get(LibraryService)
    service.do_work()

    logger_instance = container.get(Logger)
    assert isinstance(logger_instance, FileLogger)
    assert logger_instance.last_message == "LibraryService is working..."
