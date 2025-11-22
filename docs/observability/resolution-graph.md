# Resolution graph

The resolution graph is the dependency-injection system’s internal plan for constructing components. It is derived by inspecting callables (functions, constructors, factory methods) and their type annotations to produce DependencyRequest objects describing each parameter’s dependency: the dependency key/type, whether it is required or optional, any qualifiers, and whether it expects a collection or mapping.

This document explains what the resolution graph is and how to use the provided API to analyze callables and validate/resolve dependency graphs.

## What is this?

At a high level:

- Each component (a class to instantiate or a factory function to call) has dependencies, expressed in its signature and type annotations.
- The analyzer constructs a list of DependencyRequest objects for a callable, one per parameter, capturing:
  - The dependency’s key (typically a type, or a string key)
  - Optionality (e.g., Optional[T] means the dependency may be missing)
  - Qualifiers (to distinguish between multiple bindings of the same type)
  - Collection semantics (e.g., list[T] meaning “multi-binding of T”)
  - Mapping semantics (e.g., dict[str, T] meaning “qualified/bucketed bindings of T”)
- The resolver uses these requests to build a directed acyclic graph (DAG) from providers to their dependencies. It validates acyclicity and performs a topological resolution order.
- If the binding graph contains a cycle, resolution fails with InvalidBindingError.

The module’s core public pieces:

- Class DependencyRequest: a structured description of a single parameter’s dependency.
- Function analyze_callable_dependencies(callable_obj): inspects a callable and returns the plan of DependencyRequest objects.

Property-based tests in the project validate that randomized acyclic graphs resolve successfully and that circular graphs are detected and rejected:

- test_dag_validates_and_resolves(n)
- test_cycle_detected(n)

## When to use the resolution graph

Use the resolution graph whenever you need to:

- Automatically discover dependencies from Python type annotations and signatures.
- Validate that your DI bindings form a DAG before attempting resolution.
- Support optional dependencies, multi-bindings (lists/sets), and keyed mappings (dicts) without bespoke glue code.
- Diagnose resolution failures (e.g., missing required dependency, incorrect qualifier, or dependency cycle).

## How to use it

### Analyze a callable’s dependencies

Given a class constructor or factory function, call analyze_callable_dependencies to obtain the set of DependencyRequest objects. These requests are the edges you will use to wire your DI bindings.

Example: a service that depends on a repository, an optional cache, a set of plugins, and a mapping of named plugins.

```python
from typing import Optional

# Your domain types
class Repository: ...
class Cache: ...
class Plugin: ...

# The component we want to construct via DI
class Service:
    def __init__(
        self,
        repo: Repository,
        cache: Optional[Cache],        # optional dependency
        plugins: list[Plugin],         # multi-binding: all Plugin providers
        plugin_map: dict[str, Plugin], # mapping: named Plugin providers
    ) -> None:
        self.repo = repo
        self.cache = cache
        self.plugins = plugins
        self.plugin_map = plugin_map

# Analyze the constructor
from your_project.di import analyze_callable_dependencies  # adjust import path

requests = analyze_callable_dependencies(Service.__init__)

# Inspect the plan
for r in requests:
    # DependencyRequest includes key/type, optionality, qualifiers, and collection/dict info
    print(r)
```

Notes:

- Optional[T] indicates that missing bindings should not fail resolution; the parameter will be set to None if no binding is found.
- list[T] (or set[T]) indicates multi-binding semantics: gather all bindings for T and pass the collection.
- dict[str, T] indicates keyed/mapped bindings: gather all T bindings keyed by a string (other key types may be supported depending on your project’s conventions).
- Qualifiers can be used to disambiguate multiple bindings of the same type. If your project uses typing.Annotated for qualifiers, e.g., Annotated[Logger, Qualifier("audit")], the analyzer will carry the qualifier into the request.

### Build and validate the resolution graph

The resolution graph is typically constructed by your DI resolver/container based on a registry of bindings. The general pattern:

1. Register providers (factories, singletons, instances) keyed by type or name/qualifier.
2. For each component to construct, call analyze_callable_dependencies on its callable.
3. Build edges from the component to each dependency request and validate acyclicity.
4. Resolve in topological order.

Pseudocode:

```python
# Example resolver interface (illustrative; adapt to your project)
class Resolver:
    def bind(self, key, provider): ...
    def bind_multi(self, key, providers): ...
    def bind_mapping(self, key, mapping): ...
    def resolve(self, target): ...
    def validate(self): ...

from your_project.di import analyze_callable_dependencies, InvalidBindingError

resolver = Resolver()

# Register bindings
resolver.bind(Repository, lambda: Repository())
resolver.bind(Cache, lambda: Cache())  # omit to test Optional behavior
resolver.bind_multi(Plugin, [Plugin(), Plugin()])
resolver.bind_mapping(Plugin, {"alpha": Plugin(), "beta": Plugin()})

# Validate graph (raises on cycles)
resolver.validate()

# Resolve target
service = resolver.resolve(Service)  # resolver will use analyze_callable_dependencies(Service.__init__)
```

The validate step guarantees the binding graph is a DAG. If a cycle exists, resolution is rejected early.

### Resolving an acyclic graph

When your graph is acyclic and bindings satisfy all DependencyRequest objects:

- Required dependencies must have a matching binding.
- Optional dependencies may be missing; they resolve to None.
- Multi-bindings resolve to a collection, possibly empty.
- Mappings resolve to a dict, possibly empty.

Example:

```python
service = resolver.resolve(Service)
assert isinstance(service.repo, Repository)
assert service.cache is None or isinstance(service.cache, Cache)
assert all(isinstance(p, Plugin) for p in service.plugins)
assert all(isinstance(p, Plugin) for p in service.plugin_map.values())
```

### Detecting cycles

If a cycle exists (e.g., A depends on B and B depends on A), resolution fails with InvalidBindingError.

Example:

```python
class A:
    def __init__(self, b: 'B') -> None:
        self.b = b

class B:
    def __init__(self, a: A) -> None:
        self.a = a

resolver.bind(A, A)  # assume class binding uses its __init__ signature
resolver.bind(B, B)

try:
    # Either validate() or the first resolve() will detect the cycle
    resolver.validate()
except InvalidBindingError as e:
    print(f"Cycle detected: {e}")
```

The project’s property-based tests cover this behavior at scale:

- test_dag_validates_and_resolves(n) generates randomized acyclic graphs and asserts they validate and resolve correctly.
- test_cycle_detected(n) generates randomized cyclic graphs and asserts resolution fails with InvalidBindingError.

## Best practices

- Prefer precise type annotations. The analyzer relies on Python typing to correctly infer dependency keys and collection/mapping semantics.
- Use Optional[T] only when the component can operate correctly without T; optional dependencies should be rare and well-justified.
- Model multi-bindings and keyed mappings via list[T]/set[T] and dict[str, T] to keep signatures declarative.
- Use qualifiers to disambiguate multiple bindings for the same type. If your project uses Annotated, standardize qualifier encoding and document it for your team.
- Validate the graph during startup to catch configuration issues (missing bindings, cycles) early.

## Summary

- DependencyRequest captures the intent of each parameter’s dependency: key/type, required/optional, qualifiers, and collection/mapping semantics.
- analyze_callable_dependencies(callable_obj) is the entry point for turning a callable’s signature into a resolution plan.
- The resolver constructs and validates a resolution graph from these requests; it resolves acyclic graphs in topological order and raises InvalidBindingError for cycles.