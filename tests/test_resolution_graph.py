import random
import types
from dataclasses import dataclass
from typing import List

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pico_ioc import InvalidBindingError, component, init


def _build_module_from_edges(n: int, edges: List[tuple[int, int]]):
    mod = types.ModuleType(f"mod_{n}_{len(edges)}")
    classes = []
    for i in range(n):
        deps_idx = [a for a, b in edges if b == i]
        ns = {}
        body = "from __future__ import annotations\n"
        body += (
            "def __init__(self, "
            + ",".join(f"d{k}: C{k}" for k in deps_idx)
            + "):\n    "
            + "\n    ".join(f"self.d{k}=d{k}" for k in deps_idx)
            + ("\n    pass" if not deps_idx else "")
        )
        exec(body, {}, ns)
        C = type(f"C{i}", (), {})
        C.__init__ = ns["__init__"]
        C = component(C)
        classes.append(C)

    shuffled_classes = list(classes)
    random.shuffle(shuffled_classes)
    for C in shuffled_classes:
        setattr(mod, C.__name__, C)
    return mod, classes


def _acyclic_edges(n: int):
    edges = []
    for i in range(n):
        for j in range(i):
            if random.random() < 0.2:
                edges.append((j, i))
    return edges


@given(st.integers(min_value=3, max_value=15))
def test_dag_validates_and_resolves(n):
    edges = _acyclic_edges(n)
    mod, classes = _build_module_from_edges(n, edges)
    init(mod, validate_only=True)
    c = init(mod)
    sinks = [i for i in range(n) if all(b != i for a, b in edges)]
    target = classes[sinks[-1]] if sinks else classes[-1]
    c.get(target)


@given(st.integers(min_value=3, max_value=10))
def test_cycle_detected(n):
    edges = _acyclic_edges(n)
    if n >= 3:
        edges.append((n - 1, 0))
        edges.append((0, n - 1))
    mod, classes = _build_module_from_edges(n, edges)
    with pytest.raises(InvalidBindingError) as e:
        init(mod)
    assert "Circular dependency detected" in str(e.value)
