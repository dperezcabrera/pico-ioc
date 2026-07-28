"""The public introspection seam: container.keys()/metadata_for() replace
reaching into container._locator._metadata. Also pins that the scanner ABI
(Provider/ProviderMetadata/DeferredProvider) is importable from the facade,
so downstream never needs the private module path.
"""

import pico_ioc
from pico_ioc import DeferredProvider, Provider, ProviderMetadata, component, init


@component
class Alpha:
    pass


@component(name="beta")
class Beta:
    pass


def test_keys_lists_registered_components():
    c = init(modules=[__name__])
    keys = c.keys()
    assert Alpha in keys
    assert "beta" in keys


def test_metadata_for_returns_provider_metadata():
    c = init(modules=[__name__])
    md = c.metadata_for(Alpha)
    assert isinstance(md, ProviderMetadata)
    assert md.scope == "singleton"
    assert c.metadata_for("does-not-exist") is None


def test_scanner_abi_is_public():
    assert all(hasattr(pico_ioc, n) for n in ("Provider", "ProviderMetadata", "DeferredProvider"))
    _ = (Provider, ProviderMetadata, DeferredProvider)


def test_private_module_path_is_gone():
    # The internal module must not be importable under its old public name,
    # so the @factory decorator no longer collides with a submodule.
    import importlib

    for gone in ("pico_ioc.factory",):
        try:
            importlib.import_module(gone)
        except ImportError:
            continue
        raise AssertionError(f"{gone} should no longer exist")
