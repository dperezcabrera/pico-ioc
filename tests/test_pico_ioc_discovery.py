# tests/test_pico_ioc_discovery.py

from __future__ import annotations

import sys
import importlib
from pathlib import Path
import textwrap
import pytest

import pico_ioc


def _make_pkg(tmp_path: Path, name: str, files: dict[str, str]) -> object:
    pkg_dir = tmp_path / name
    pkg_dir.mkdir(parents=True)

    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    for relpath, content in files.items():
        p = pkg_dir / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content), encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        return importlib.import_module(name)
    finally:
        pass


def test_component_injection_by_type_works(tmp_path: Path):
    pkg = _make_pkg(
        tmp_path,
        "samplepkg_ok",
        {
            "service_b.py": """
                from __future__ import annotations
                from pico_ioc import component

                @component
                class ServiceB:
                    def __init__(self):
                        self.value = 42
            """,

            "service_a.py": """
                from __future__ import annotations
                from pico_ioc import component
                from .service_b import ServiceB

                @component
                class ServiceA:
                    def __init__(self, service_b: ServiceB):
                        self.dep = service_b
            """,
        },
    )

    container = pico_ioc.init(pkg)

    from samplepkg_ok.service_a import ServiceA
    from samplepkg_ok.service_b import ServiceB

    a = container.get(ServiceA)
    assert isinstance(a.dep, ServiceB)
    assert a.dep.value == 42


def test_missing_provider_raises_clear_error(tmp_path: Path):
    pkg = _make_pkg(
        tmp_path,
        "samplepkg_bad",
        {
            "service_a.py": """
                from __future__ import annotations
                from pico_ioc import component

                class ServiceB:
                    pass

                @component
                class ServiceA:
                    def __init__(self, service_b: ServiceB):
                        self.dep = service_b
            """,
        },
    )

    pico_ioc.reset()
    with pytest.raises(NameError) as ei:
        pico_ioc.init(pkg)

    msg = str(ei.value)
    assert "No provider found for key" in msg
    assert "ServiceB" in msg

