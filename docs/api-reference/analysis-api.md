# Analysis API

This module provides utilities for inspecting Python callables (functions and methods) to build an explicit injection plan for your dependency-injection system. It processes parameter names, type annotations, default values, and metadata to produce a set of DependencyRequest objects—one per injectable parameter—that describe what needs to be resolved at runtime.

The primary entry point is analyze_callable_dependencies(callable_obj), which returns DependencyRequest instances for each parameter in the callable. These requests capture the dependency type or key, optionality, qualifiers, and collection/dict semantics so that your container can resolve and inject the appropriate values.

## What is this?

In a dependency-injection setup, you often want to declare required dependencies on function or constructor parameters via type hints and metadata, and let the container supply them. This module inspects those declarations and turns them into a structured, container-friendly plan:

- It reads type annotations to determine the dependency’s key (usually a type).
- It detects optional parameters (via typing.Optional/Union[…] or default values).
- It recognizes qualifiers from annotation metadata (e.g., typing.Annotated[…]).
- It understands collection and mapping semantics:
  - List[T], Set[T] indicate multi-bindings or collection dependencies.
  - Dict[K, V] indicates a mapping dependency.

DependencyRequest instances encapsulate all the information the resolver needs to supply a value for a given parameter.

## API

### DependencyRequest

Represents one parameter’s dependency requirements. A DependencyRequest is created for each parameter that should be injected.

A DependencyRequest typically includes:

- Parameter name
- Dependency key or type (the token used by the container to look up a binding)
- Optionality (whether the absence of a binding is acceptable)
- Qualifiers (metadata to disambiguate bindings)
- Collection or dict semantics:
  - Whether the parameter expects a single value or a collection/mapping
  - Element type for collections (List[T], Set[T])
  - Key and value types for mappings (Dict[K, V])
- Default value presence (used to infer optionality)
- Original annotation (for debugging or advanced resolution)

Refer to the class definition in your codebase for the exact property names and additional fields.

### analyze_callable_dependencies(callable_obj)

Inspects a callable’s signature and annotations and returns a sequence of DependencyRequest objects describing each injectable parameter.

Parameters:
- callable_obj: A Python callable (function or method). Methods are supported; parameters that are clearly not intended for injection (such as unannotated `self`/`cls`) are typically skipped.

Returns:
- An ordered collection (e.g., list or tuple) of DependencyRequest instances, aligned with the callable’s parameter order (excluding any skipped parameters).

Behavior highlights:
- Type hints drive the dependency key. For example, a parameter annotated as `Service` yields a request keyed by `Service`.
- Optionality is inferred from `typing.Optional[T]` (or `Union[T, None]`) and also from parameters that have default values.
- Qualifiers can be extracted from `typing.Annotated[T, ...]` metadata. The specific qualifier type is project-specific (e.g., a `Qualifier("auth")` object).
- Collections:
  - `List[T]` and `Set[T]` requests indicate a multi-binding; the element type `T` is used to collect all matching bindings.
  - `Dict[K, V]` requests indicate a mapping; `K` and `V` types are captured for resolution.
- Unannotated parameters are generally not considered injectable. Prefer explicit type annotations for all dependencies.
- Variadic parameters (`*args`, `**kwargs`) are not typically injectable and may be ignored.

## How do I use it?

Call `analyze_callable_dependencies` with the function or method you want to inject. Iterate over the returned `DependencyRequest` objects and let your container resolve each request.

### Example: Function with single and optional dependencies

```python
from typing import Optional

# Import from your analysis module
from analysis import analyze_callable_dependencies

class Service: ...
class Cache: ...

def handler(service: Service, cache: Optional[Cache] = None) -> None:
    ...

requests = analyze_callable_dependencies(handler)

for req in requests:
    print({
        "param": req.param_name,
        "key": req.key,                  # e.g., Service or Cache type
        "optional": req.optional,        # True for Optional[Cache]
        "qualifiers": req.qualifiers,    # [] if none
        "kind": req.kind,                # "single", "list", "set", or "dict"
    })
```

You can then pass each request to your container/resolver to obtain the appropriate value, and call the function with the resolved arguments.

### Example: Qualifiers and collections

```python
from typing import List, Annotated

from analysis import analyze_callable_dependencies

class Plugin: ...
class Qualifier:
    def __init__(self, name: str) -> None:
        self.name = name

def build_pipeline(
    plugins: Annotated[List[Plugin], Qualifier("auth")],
) -> None:
    ...

requests = analyze_callable_dependencies(build_pipeline)

for req in requests:
    assert req.kind == "list"
    assert req.element_key is Plugin
    assert any(isinstance(q, Qualifier) and q.name == "auth" for q in req.qualifiers)
```

This indicates that `build_pipeline` expects a list of `Plugin` instances with the `"auth"` qualifier.

### Example: Dict dependencies

```python
from typing import Dict

from analysis import analyze_callable_dependencies

def configure(options: Dict[str, int]) -> None:
    ...

requests = analyze_callable_dependencies(configure)

r = requests[0]
print(r.kind)           # "dict"
print(r.map_key_type)   # str
print(r.map_value_type) # int
```

Your container can use this to supply a mapping from `str` keys to `int` values.

### Example: Constructors and methods

```python
from analysis import analyze_callable_dependencies

class Repository: ...
class Service:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

requests = analyze_callable_dependencies(Service.__init__)

# Typically, 'self' is skipped. Only 'repo' produces a DependencyRequest.
assert len(requests) == 1
assert requests[0].key is Repository
```

## Supported annotations and conventions

- Use standard `typing` annotations to express dependency types and optionality:
  - `T`: single required dependency
  - `Optional[T]` or `Union[T, None]`: optional dependency
  - `List[T]`, `Set[T]`: collection dependencies
  - `Dict[K, V]`: mapping dependencies
- Use `typing.Annotated[T, qualifier, ...]` to attach qualifiers or metadata recognized by your DI system.
- Provide default values to mark parameters as optional when appropriate.
- Avoid variadic parameters for injection (`*args`, `**kwargs`); these are not typically supported.
- Prefer explicit annotations for all injectable parameters. Unannotated parameters may be skipped or treated as non-injectable.

## Integration

The typical flow in your DI container:

1. Call `analyze_callable_dependencies` on the target callable.
2. For each `DependencyRequest`, resolve a value:
   - Use `.key` plus any `.qualifiers` to select bindings.
   - Respect `.optional` to decide how to handle missing bindings.
   - For `.kind == "list"/"set"`, collect all matching bindings of `.element_key`.
   - For `.kind == "dict"`, prepare a mapping with the requested key and value types.
3. Invoke the callable with the resolved arguments.

This module isolates signature parsing and annotation interpretation from resolution, making your container logic simpler and more consistent.