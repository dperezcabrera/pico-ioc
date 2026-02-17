from typing import Optional
from uuid import UUID

from pico_ioc import component

from .models import Todo


@component
class InMemoryTodoRepository:
    """Simple in-memory repository for demonstration."""

    def __init__(self):
        self._todos: dict[UUID, Todo] = {}

    def save(self, todo: Todo) -> Todo:
        self._todos[todo.id] = todo
        return todo

    def find_by_id(self, id: UUID) -> Optional[Todo]:
        return self._todos.get(id)

    def find_all(self) -> list[Todo]:
        return list(self._todos.values())

    def delete(self, id: UUID) -> bool:
        if id in self._todos:
            del self._todos[id]
            return True
        return False
