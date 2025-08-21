# pico_ioc/typing_utils.py

import sys, typing

def evaluated_hints(func, owner_cls=None) -> dict:
    try:
        module = sys.modules.get(func.__module__)
        globalns = getattr(module, "__dict__", {})
        localns = vars(owner_cls) if owner_cls is not None else {}
        return typing.get_type_hints(func, globalns=globalns, localns=localns)
    except Exception:
        return {}

def resolve_annotation_to_type(ann, func, owner_cls=None):
    if not isinstance(ann, str):
        return ann
    try:
        module = sys.modules.get(func.__module__)
        globalns = getattr(module, "__dict__", {})
        localns = vars(owner_cls) if owner_cls is not None else {}
        return eval(ann, globalns, localns)
    except Exception:
        return ann

