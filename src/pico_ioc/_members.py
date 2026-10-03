"""Find pico-decorated methods without evaluating properties."""

import inspect
from typing import Any, Iterator, Tuple

from .constants import PICO_META


def pico_methods(obj: Any, flag: str) -> Iterator[Tuple[str, Any]]:
    """Yield ``(name, bound_method)`` for the methods whose metadata sets ``flag``.

    The class is scanned statically: ``inspect.getmembers`` on the instance
    evaluates every property, and third-party objects may raise from one.
    """
    real = obj._get_real_object() if hasattr(type(obj), "_get_real_object") else obj
    for name, attr in inspect.getmembers_static(type(real)):
        if getattr(attr, PICO_META, {}).get(flag, False):
            yield name, getattr(obj, name)
