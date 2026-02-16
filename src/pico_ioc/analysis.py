import collections
import collections.abc
import inspect
import typing
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    Callable,
    Collection,
    Deque,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    MutableSequence,
    MutableSet,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
    get_args,
    get_origin,
)

from .constants import LOGGER
from .decorators import Qualifier

KeyT = Union[str, type]


@dataclass(frozen=True)
class DependencyRequest:
    parameter_name: str
    key: KeyT
    is_list: bool = False
    qualifier: Optional[str] = None
    is_optional: bool = False
    is_dict: bool = False
    dict_key_type: Any = None


def _extract_annotated(ann: Any) -> Tuple[Any, Optional[str]]:
    qualifier = None
    base = ann
    origin = get_origin(ann)

    if origin is Annotated:
        args = get_args(ann)
        base = args[0] if args else Any
        metas = args[1:] if len(args) > 1 else ()
        for m in metas:
            if isinstance(m, Qualifier):
                qualifier = str(m)
                break
    return base, qualifier


def _check_optional(ann: Any) -> Tuple[Any, bool]:
    origin = get_origin(ann)
    if origin is Union:
        args = [a for a in get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return ann, False


_SUPPORTED_COLLECTION_ORIGINS = (
    list,
    set,
    tuple,
    frozenset,
    collections.deque,
    collections.abc.Iterable,
    collections.abc.Collection,
    collections.abc.Sequence,
    collections.abc.MutableSequence,
    collections.abc.MutableSet,
)

_SUPPORTED_DICT_ORIGINS = (dict, collections.abc.Mapping)


def analyze_callable_dependencies(callable_obj: Callable[..., Any]) -> Tuple[DependencyRequest, ...]:
    try:
        sig = inspect.signature(callable_obj)
    except (ValueError, TypeError) as e:
        LOGGER.debug(f"Could not analyze dependencies for {callable_obj!r}: {e}")
        return ()

    try:
        resolved_hints = typing.get_type_hints(callable_obj, include_extras=True)
    except Exception:
        resolved_hints = {}

    plan: List[DependencyRequest] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        plan.append(_build_dep_request(name, param, resolved_hints))

    return tuple(plan)


def _build_dep_request(name: str, param: inspect.Parameter, resolved_hints: Dict[str, Any]) -> DependencyRequest:
    ann = resolved_hints.get(name, param.annotation)

    base_type, is_optional = _check_optional(ann)
    base_type, qualifier = _extract_annotated(base_type)

    is_list, is_dict, elem_t, dict_key_t = _classify_collection(base_type)
    if is_list or is_dict:
        elem_t, coll_qualifier = _extract_annotated(elem_t)
        if qualifier is None:
            qualifier = coll_qualifier

    final_key, final_dict_key_type = _resolve_key(is_list, is_dict, elem_t, dict_key_t, base_type, ann, name)

    return DependencyRequest(
        parameter_name=name,
        key=final_key,
        is_list=is_list,
        qualifier=qualifier,
        is_optional=is_optional or (param.default is not inspect._empty),
        is_dict=is_dict,
        dict_key_type=final_dict_key_type,
    )


def _classify_collection(base_type: Any) -> Tuple[bool, bool, Any, Any]:
    origin = get_origin(base_type)
    if origin in _SUPPORTED_COLLECTION_ORIGINS:
        elem_t = get_args(base_type)[0] if get_args(base_type) else Any
        return True, False, elem_t, None
    if origin in _SUPPORTED_DICT_ORIGINS:
        args = get_args(base_type)
        dict_key_t = args[0] if args else Any
        elem_t = args[1] if len(args) > 1 else Any
        return False, True, elem_t, dict_key_t
    return False, False, None, None


def _resolve_key(is_list: bool, is_dict: bool, elem_t: Any, dict_key_t: Any,
                 base_type: Any, ann: Any, name: str) -> Tuple[KeyT, Any]:
    if is_list:
        return (elem_t if isinstance(elem_t, type) else Any), None
    if is_dict:
        return (elem_t if isinstance(elem_t, type) else Any), dict_key_t
    if isinstance(base_type, type):
        return base_type, None
    if isinstance(base_type, str):
        return base_type, None
    if ann is inspect._empty:
        return name, None
    return base_type, None
