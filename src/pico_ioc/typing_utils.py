# pico_ioc/typing_utils.py

import sys
import typing


def evaluated_hints(func, owner_cls=None) -> dict:
    """Return type hints; swallow any error and return {}."""
    try:
        module = sys.modules.get(func.__module__)
        globalns = getattr(module, "__dict__", {})
        localns = vars(owner_cls) if owner_cls is not None else None
        return typing.get_type_hints(func, globalns=globalns, localns=localns, include_extras=True)
    except Exception:
        return {}


def resolve_annotation_to_type(ann, func, owner_cls=None):
    """Best-effort evaluation of a string annotation; return original on failure."""
    if not isinstance(ann, str):
        return ann
    try:
        module = sys.modules.get(func.__module__)
        globalns = getattr(module, "__dict__", {})
        localns = vars(owner_cls) if owner_cls is not None else None
        return eval(ann, globalns, localns)
    except Exception:
        return ann

