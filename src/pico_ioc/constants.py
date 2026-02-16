"""Constants used throughout the pico-ioc framework.

This module defines the internal attribute names stamped onto decorated classes
and functions, the framework logger, and the built-in scope identifiers.
"""

import logging

LOGGER_NAME: str = "pico_ioc"
"""Default logger name for the pico-ioc framework."""

LOGGER: logging.Logger = logging.getLogger(LOGGER_NAME)
"""Pre-configured logger instance for pico-ioc internal diagnostics."""

PICO_INFRA: str = "_pico_infra"
"""Attribute name storing the infrastructure role (``'component'``, ``'factory'``, ``'provides'``, ``'configured'``)."""

PICO_NAME: str = "_pico_name"
"""Attribute name storing the human-readable provider name."""

PICO_KEY: str = "_pico_key"
"""Attribute name storing the resolution key (a type or string)."""

PICO_META: str = "_pico_meta"
"""Attribute name storing the metadata dictionary (scope, qualifiers, conditionals, etc.)."""

SCOPE_SINGLETON: str = "singleton"
"""Built-in scope: one instance per container lifetime."""

SCOPE_PROTOTYPE: str = "prototype"
"""Built-in scope: a new instance on every resolution."""
