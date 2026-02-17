from typing import Optional
from uuid import UUID

from pico_ioc import component

from .models import Todo
from .repositories import InMemoryTodoRepository


@component
class TodoService:
    """Business logic for TODO operations."""

    def __init__(self, repo: InMemoryTodoRepository):
        self.repo = repo

    def create_todo(self, title: str) -> Todo:
        todo = Todo(title=title)
        return self.repo.save(todo)

    def get_todo(self, id: UUID) -> Optional[Todo]:
        return self.repo.find_by_id(id)

    def list_todos(self) -> list[Todo]:
        return self.repo.find_all()

    def complete_todo(self, id: UUID) -> Optional[Todo]:
        todo = self.repo.find_by_id(id)
        if todo:
            todo.complete()
            return self.repo.save(todo)
        return None

    def delete_todo(self, id: UUID) -> bool:
        return self.repo.delete(id)
