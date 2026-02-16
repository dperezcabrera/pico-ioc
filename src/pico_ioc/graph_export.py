from typing import Any, Dict, List, Optional, Tuple, Union

KeyT = Union[str, type]


def _build_resolution_graph(loc) -> Dict[KeyT, Tuple[KeyT, ...]]:
    if not loc:
        return {}

    graph: Dict[KeyT, Tuple[KeyT, ...]] = {}
    for key, md in list(loc._metadata.items()):
        deps: List[KeyT] = []
        for d in loc.dependency_keys_for_static(md):
            deps.append(_map_dep_to_bound_key(loc, d))
        graph[key] = tuple(deps)
    return graph


def _map_dep_to_bound_key(loc, dep_key: KeyT) -> KeyT:
    if dep_key in loc._metadata:
        return dep_key

    if isinstance(dep_key, str):
        mapped = loc.find_key_by_name(dep_key)
        if mapped is not None:
            return mapped

    if isinstance(dep_key, type):
        return _find_subtype_key(loc, dep_key)
    return dep_key


def _find_subtype_key(loc, dep_key: type) -> KeyT:
    for k, md in loc._metadata.items():
        typ = md.provided_type or md.concrete_class
        if not isinstance(typ, type):
            continue
        try:
            if issubclass(typ, dep_key):
                return k
        except Exception:
            continue
    return dep_key


def export_graph(
    locator: Any,
    path: str,
    *,
    include_scopes: bool = True,
    include_qualifiers: bool = False,
    rankdir: str = "LR",
    title: Optional[str] = None,
) -> None:
    if not locator:
        raise RuntimeError("No locator attached; cannot export dependency graph.")

    md_by_key = locator._metadata
    graph = _build_resolution_graph(locator)

    lines: List[str] = []
    lines.append("digraph Pico {")
    lines.append(f'  rankdir="{rankdir}";')
    lines.append("  node [shape=box, fontsize=10];")
    if title:
        lines.append('  labelloc="t";')
        lines.append(f'  label="{title}";')

    def _node_id(k: KeyT) -> str:
        return f"n_{abs(hash(k))}"

    def _node_label(k: KeyT) -> str:
        name = getattr(k, "__name__", str(k))
        md = md_by_key.get(k)
        parts = [name]
        if md is not None and include_scopes:
            parts.append(f"[scope={md.scope}]")
        if md is not None and include_qualifiers and md.qualifiers:
            q = ",".join(sorted(md.qualifiers))
            parts.append(f"\\n⟨{q}⟩")
        return "\\n".join(parts)

    for key in md_by_key.keys():
        nid = _node_id(key)
        label = _node_label(key)
        lines.append(f'  {nid} [label="{label}"];')

    for parent, deps in graph.items():
        pid = _node_id(parent)
        for child in deps:
            cid = _node_id(child)
            lines.append(f"  {pid} -> {cid};")

    lines.append("}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
