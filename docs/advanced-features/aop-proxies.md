# AOP proxies: UnifiedComponentProxy

This page introduces UnifiedComponentProxy, a general-purpose, AOP-style proxy that makes heavy or remote components feel local while creating them only when actually needed.

The proxy delays instantiation of the real object until the first meaningful interaction and then transparently delegates virtually all Python operations to it: attribute access, method calls, magic/dunder methods, arithmetic and container operations, context management, and more. It also mirrors the proxied class so that type-based code like isinstance behaves as if it operated on the underlying object.

## What is this?

UnifiedComponentProxy is a transparent, lazy proxy for any Python object constructed via a factory. It is designed to:

- Defer construction until first use (lazy instantiation).
- Behave like the underlying object in most situations:
  - Regular attribute access and method calls
  - All common magic/dunder operations (len, iter, contains, item get/set/delete)
  - Arithmetic, bitwise, shift, unary ops, comparisons, divmod, matmul
  - Callables (delegates __call__)
  - Context managers (delegates __enter__/__exit__)
  - dir(), getattr(), setattr(), delattr() passthrough
  - Mirrored class/type for isinstance-style checks and display-friendly repr/str

This lets you decouple object creation cost and side effects from program wiring, enabling cross-cutting concerns like lazy loading, tracing, and boundary indirection without rewriting consumers.

## How do I use it?

You wrap a factory (callable) that returns the real object. Constructing the proxy does not instantiate the object; the first operation on the proxy triggers it.

Below are usage patterns that mirror the capabilities verified by the test suite.

Note: Replace the import path with the one appropriate for your project.

```python
from yourlib import UnifiedComponentProxy
```

### Quick start: lazy instantiation on first use

```python
create_log = []

def make_heavy():
    create_log.append("constructed")
    return {"answer": 42}

proxy = UnifiedComponentProxy(make_heavy)

# No instantiation yet:
assert create_log == []

# First meaningful interaction instantiates:
val = proxy["answer"]
assert val == 42
assert create_log == ["constructed"]
```

Any of the operations shown below will trigger construction if it hasn't happened yet.

### Attribute access and method calls

```python
class Service:
    def __init__(self):
        self._status = "ready"
    def ping(self):
        return "pong"
    def set_status(self, s):
        self._status = s

svc = UnifiedComponentProxy(Service)

# Attribute get/set/delete passthrough
assert svc._status == "ready"
svc.set_status("busy")
assert svc._status == "busy"
del svc._status
setattr(svc, "_status", "restored")
assert getattr(svc, "_status") == "restored"

# dir() shows attributes of the real object
assert "ping" in dir(svc)

# __repr__/__str__ delegate to the real object
print(str(svc))   # Uses Service.__str__ if defined, else default
print(repr(svc))  # Uses Service.__repr__ if defined, else default
```

### Calling a proxied callable (delegates __call__)

```python
class Tracker:
    def __init__(self):
        self.calls = 0
    def __call__(self, x):
        self.calls += 1
        return x * 2

fn = UnifiedComponentProxy(Tracker)
assert fn(21) == 42
assert fn.calls == 1
```

### Context manager delegation

```python
class Resource:
    def __init__(self):
        self.open = False
    def __enter__(self):
        self.open = True
        return self
    def __exit__(self, exc_type, exc, tb):
        self.open = False
        # Swallow or propagate exceptions as needed
        return False

res = UnifiedComponentProxy(Resource)
with res as r:
    assert r.open is True
assert res.open is False
```

### Container semantics: lists, dicts and iteration

```python
# List-like
lst = UnifiedComponentProxy(lambda: [1, 2, 3])
assert len(lst) == 3
assert 2 in lst
assert list(iter(lst)) == [1, 2, 3]

# Dict-like
dct = UnifiedComponentProxy(lambda: {"a": 1})
assert dct["a"] == 1
dct["b"] = 2
assert "b" in dct and dct["b"] == 2
del dct["a"]
assert "a" not in dct
```

### Arithmetic and comparisons (including reflected ops)

UnifiedComponentProxy forwards both left-hand and right-hand (reflected) operations to the underlying object.

```python
num = UnifiedComponentProxy(lambda: 10)

# Basic arithmetic
assert num + 5 == 15
assert 5 + num == 15
assert num - 3 == 7
assert 3 - num == -7
assert num * 2 == 20
assert 2 * num == 20

# Division and modulo
assert num / 4 == 2.5
assert 100 / num == 10
assert divmod(num, 3) == (3, 1)
assert divmod(23, num) == (2, 3)

# Unary ops and comparisons
assert -num == -10
assert +num == 10
assert abs(-num) == 10
assert num > 5 and num >= 10 and num < 20 and num <= 10
```

### Bitwise and shift operations

```python
mask = UnifiedComponentProxy(lambda: 0b1010)

assert (mask & 0b0110) == 0b0010
assert (0b0110 & mask) == 0b0010
assert (mask | 0b0011) == 0b1011
assert (0b0011 | mask) == 0b1011
assert (mask ^ 0b1111) == 0b0101
assert (0b1111 ^ mask) == 0b0101

assert (mask << 1) == 0b10100
assert (1 << mask) == (1 << 10)  # reflected shift
assert (mask >> 1) == 0b0101
assert (1024 >> mask) == 1
```

### True division, reflected division, and divmod

```python
a = UnifiedComponentProxy(lambda: 8)
assert a / 2 == 4.0
assert 16 / a == 2.0
assert divmod(a, 3) == (2, 2)
assert divmod(20, a) == (2, 4)
```

### Matrix multiplication (delegates __matmul__ and __rmatmul__)

```python
class Mat:
    def __init__(self, val):
        self.val = val
    def __matmul__(self, other):
        return ("L", self.val, getattr(other, "val", other))
    def __rmatmul__(self, other):
        return ("R", getattr(other, "val", other), self.val)

A = UnifiedComponentProxy(lambda: Mat("A"))
B = UnifiedComponentProxy(lambda: Mat("B"))

assert (A @ B) == ("L", "A", "B")
assert (B @ A) == ("L", "B", "A")
assert ("X" @ A) == ("R", "X", "A")
assert (A @ "Y") == ("L", "A", "Y")
```

### Class/type mirroring

The proxy mirrors the class/type of the underlying object so that type-oriented code sees what it expects.

```python
d = UnifiedComponentProxy(dict)

# After the proxy materializes, isinstance behaves as if d were a dict
d["x"] = 1  # triggers instantiation
assert isinstance(d, dict)
assert d.__class__ is dict
```

This mirroring is especially helpful for libraries that branch on the observed type, or for developer ergonomics (repr/str, shells, and IDEs).

### Introspection and attribute management

```python
obj = UnifiedComponentProxy(lambda: type("X", (), {"a": 1, "b": 2})())

# dir() lists attributes from the real object
names = dir(obj)
assert "a" in names and "b" in names

# getattr/setattr/delattr pass through
assert getattr(obj, "a") == 1
setattr(obj, "c", 3)
assert obj.c == 3
delattr(obj, "b")
assert not hasattr(obj, "b")
```

## Behavior summary

- Construction is lazy. The proxy does not create the target object until the first operation that requires it (attribute/method access, magic op, entering a with-block, etc.).
- Delegation is broad. The proxy forwards:
  - Attribute access: getattr, setattr, delattr, dir
  - Callables: __call__
  - Context management: __enter__, __exit__
  - Containers: __len__, __iter__, __contains__, __getitem__, __setitem__, __delitem__
  - Arithmetic: +, -, *, /, //, %, **, and their reflected forms
  - Bitwise: &, |, ^, ~ and their reflected forms
  - Shifts: <<, >> and their reflected forms
  - Unary operations: +x, -x, abs(x)
  - Comparisons: <, <=, >, >=, ==, !=
  - Special: divmod, matmul (@) including reflected variants
  - Representation: __repr__, __str__
- Class mirroring. The proxy mirrors the underlying class for user-facing type checks and introspection.

## When to use UnifiedComponentProxy

- Deferring expensive construction or I/O until actually needed.
- Wrapping remote resources or IPC handles with a local, Pythonic interface.
- Enabling AOP scenarios (e.g., logging, timing, tracing) around object creation and use, without changing consumers.
- Maintaining transparent semantics with existing code that expects native Python types and operations.

## Notes and tips

- The proxy becomes indistinguishable from the real object for most day-to-day Python code. If your code relies on identity or very low-level type checks, validate behavior in your environment.
- For best ergonomics, wrap a zero-argument factory: UnifiedComponentProxy(MyClass) or UnifiedComponentProxy(lambda: MyClass(cfg)). If your factory requires arguments, curry them via a lambda or functools.partial.