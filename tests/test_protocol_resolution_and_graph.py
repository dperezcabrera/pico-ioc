from typing import Protocol, runtime_checkable

import pytest

from pico_ioc import PicoContainer, component, init


@runtime_checkable
class Database(Protocol):
    def get_user(self, user_id: int) -> str: ...


@component
class RealDatabase(Database):
    def get_user(self, user_id: int) -> str:
        return "Real User"


@component
class UserService:
    def __init__(self, db: Database):
        self.db = db


@pytest.fixture(scope="module")
def container() -> PicoContainer:
    container = init(modules=[__name__])
    return container


def test_service_resolves_with_correct_implementation(container: PicoContainer):
    service = container.get(UserService)

    assert service is not None
    assert service.db is not None

    assert isinstance(service.db, RealDatabase)

    assert service.db.get_user(1) == "Real User"


def test_protocol_resolves_directly_as_singleton(container: PicoContainer):
    service_db = container.get(UserService).db
    direct_db = container.get(Database)

    assert isinstance(direct_db, RealDatabase)

    assert service_db is direct_db


def test_dependency_graph_is_correct(container: PicoContainer):
    edge_map = container.build_resolution_graph()

    assert UserService in edge_map
    assert RealDatabase in edge_map

    assert Database not in edge_map

    assert edge_map[UserService] == (RealDatabase,)

    assert edge_map[RealDatabase] == ()
