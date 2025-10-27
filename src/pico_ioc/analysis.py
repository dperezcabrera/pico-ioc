import inspect
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple, Union, get_args, get_origin, Annotated
from .decorators import Qualifier

KeyT = Union[str, type]

@dataclass(frozen=True)
class DependencyRequest:
    parameter_name: str
    key: KeyT
    is_list: bool = False
    qualifier: Optional[str] = None
    is_optional: bool = False

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

def analyze_callable_dependencies(callable_obj: Callable[..., Any]) -> Tuple[DependencyRequest, ...]:
    try:
        sig = inspect.signature(callable_obj)
    except (ValueError, TypeError):
        return ()

    plan: List[DependencyRequest] = []
    
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        ann = param.annotation
        
        base_type, is_optional = _check_optional(ann)
        base_type, qualifier = _extract_annotated(base_type)

        is_list = False
        elem_t = None
        
        origin = get_origin(base_type)
        if origin in (list, List):
            is_list = True
            elem_t = get_args(base_type)[0] if get_args(base_type) else Any
            elem_t, list_qualifier = _extract_annotated(elem_t)
            if qualifier is None:
                qualifier = list_qualifier
        
        final_key: KeyT
        if is_list:
            final_key = elem_t if isinstance(elem_t, type) else Any
        elif isinstance(base_type, type):
            final_key = base_type
        elif isinstance(base_type, str):
            final_key = base_type
        elif ann is inspect._empty:
            final_key = name
        else:
            final_key = base_type

        plan.append(
            DependencyRequest(
                parameter_name=name,
                key=final_key,
                is_list=is_list,
                qualifier=qualifier,
                is_optional=is_optional or (param.default is not inspect._empty)
            )
        )
    
    return tuple(plan)
    
