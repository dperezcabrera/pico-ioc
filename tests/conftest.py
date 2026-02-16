import logging

import pytest

log_capture: list[str] = []


class ListLogHandler(logging.Handler):
    def emit(self, record):
        log_capture.append(self.format(record))


@pytest.fixture(autouse=True)
def reset_logging_capture():
    log_capture.clear()
