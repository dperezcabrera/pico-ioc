# Complete Example: FastAPI TODO App with pico-ioc

A full working example of a REST API using FastAPI and pico-ioc for dependency injection.

---

## Project Structure

```
todo_app/
├── __init__.py
├── main.py           # FastAPI application
├── config.py         # Configuration dataclasses
├── models.py         # Domain models
├── repositories.py   # Data access layer
├── services.py       # Business logic
└── tests/
    └── test_api.py   # Integration tests
```

---

## Installation

```bash
pip install fastapi uvicorn pico-ioc pico-fastapi
```

---

## Step 1: Configuration (`config.py`)

```python
# todo_app/config.py
from dataclasses import dataclass, field
from pico_ioc import configured

@configured(prefix="APP_")
@dataclass
class AppConfig:
    name: str = "TODO API"
    debug: bool = False

@configured(prefix="DB_")
@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "todos"

    @property
    def url(self) -> str:
        return f"postgresql://{self.host}:{self.port}/{self.name}"
```

---

## Step 2: Models (`models.py`)

```python
# todo_app/models.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

@dataclass
class Todo:
    title: str
    completed: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.now)

    def complete(self) -> None:
        self.completed = True
```

---

## Step 3: Repository Layer (`repositories.py`)

```python
# todo_app/repositories.py
from typing import Protocol, Optional
from uuid import UUID
from pico_ioc import component
from .models import Todo
from .config import DatabaseConfig

# Abstract interface
class TodoRepository(Protocol):
    def save(self, todo: Todo) -> Todo: ...
    def find_by_id(self, id: UUID) -> Optional[Todo]: ...
    def find_all(self) -> list[Todo]: ...
    def delete(self, id: UUID) -> bool: ...

# In-memory implementation for demo
@component
class InMemoryTodoRepository:
    """Simple in-memory repository for demonstration."""

    def __init__(self, config: DatabaseConfig):
        self.config = config  # Could use for real DB connection
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
```

---

## Step 4: Service Layer (`services.py`)

```python
# todo_app/services.py
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
```

---

## Step 5: FastAPI Application (`main.py`)

```python
# todo_app/main.py
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pico_ioc import init, configuration
from pico_fastapi import PicoFastAPI

from .config import AppConfig
from .services import TodoService
from .models import Todo

# Pydantic models for API
class TodoCreate(BaseModel):
    title: str

class TodoResponse(BaseModel):
    id: UUID
    title: str
    completed: bool

    @classmethod
    def from_domain(cls, todo: Todo) -> "TodoResponse":
        return cls(id=todo.id, title=todo.title, completed=todo.completed)

# Initialize container
container = init(
    modules=["todo_app.config", "todo_app.repositories", "todo_app.services"],
    config=configuration()
)

# Create FastAPI app with pico-ioc integration
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await container.ashutdown()

app = FastAPI(lifespan=lifespan)
pico = PicoFastAPI(container)
pico.install(app)

# Get config for app title
app_config = container.get(AppConfig)
app.title = app_config.name

# Routes - dependencies are injected automatically!
@app.post("/todos", response_model=TodoResponse, status_code=201)
def create_todo(data: TodoCreate, service: TodoService):
    todo = service.create_todo(data.title)
    return TodoResponse.from_domain(todo)

@app.get("/todos", response_model=list[TodoResponse])
def list_todos(service: TodoService):
    todos = service.list_todos()
    return [TodoResponse.from_domain(t) for t in todos]

@app.get("/todos/{todo_id}", response_model=TodoResponse)
def get_todo(todo_id: UUID, service: TodoService):
    todo = service.get_todo(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse.from_domain(todo)

@app.post("/todos/{todo_id}/complete", response_model=TodoResponse)
def complete_todo(todo_id: UUID, service: TodoService):
    todo = service.complete_todo(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse.from_domain(todo)

@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: UUID, service: TodoService):
    if not service.delete_todo(todo_id):
        raise HTTPException(status_code=404, detail="Todo not found")
```

---

## Step 6: Tests (`tests/test_api.py`)

```python
# todo_app/tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from pico_ioc import init, configuration

# Fake repository for testing
class FakeTodoRepository:
    def __init__(self):
        self._todos = {}

    def save(self, todo):
        self._todos[todo.id] = todo
        return todo

    def find_by_id(self, id):
        return self._todos.get(id)

    def find_all(self):
        return list(self._todos.values())

    def delete(self, id):
        if id in self._todos:
            del self._todos[id]
            return True
        return False

@pytest.fixture
def test_container():
    from todo_app.repositories import InMemoryTodoRepository

    container = init(
        modules=["todo_app.config", "todo_app.services"],
        config=configuration(),
        overrides={
            InMemoryTodoRepository: FakeTodoRepository()
        }
    )
    yield container
    container.shutdown()

@pytest.fixture
def client(test_container):
    from fastapi import FastAPI
    from pico_fastapi import PicoFastAPI
    from todo_app.main import (
        create_todo, list_todos, get_todo,
        complete_todo, delete_todo, TodoCreate, TodoResponse
    )

    app = FastAPI()
    pico = PicoFastAPI(test_container)
    pico.install(app)

    # Re-register routes with test container
    app.post("/todos")(create_todo)
    app.get("/todos")(list_todos)
    app.get("/todos/{todo_id}")(get_todo)
    app.post("/todos/{todo_id}/complete")(complete_todo)
    app.delete("/todos/{todo_id}")(delete_todo)

    return TestClient(app)

def test_create_todo(client):
    response = client.post("/todos", json={"title": "Buy milk"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Buy milk"
    assert data["completed"] is False

def test_list_todos(client):
    # Create some todos
    client.post("/todos", json={"title": "Task 1"})
    client.post("/todos", json={"title": "Task 2"})

    response = client.get("/todos")
    assert response.status_code == 200
    assert len(response.json()) == 2

def test_complete_todo(client):
    # Create a todo
    create_response = client.post("/todos", json={"title": "Task"})
    todo_id = create_response.json()["id"]

    # Complete it
    response = client.post(f"/todos/{todo_id}/complete")
    assert response.status_code == 200
    assert response.json()["completed"] is True

def test_delete_todo(client):
    # Create a todo
    create_response = client.post("/todos", json={"title": "Task"})
    todo_id = create_response.json()["id"]

    # Delete it
    response = client.delete(f"/todos/{todo_id}")
    assert response.status_code == 204

    # Verify it's gone
    response = client.get(f"/todos/{todo_id}")
    assert response.status_code == 404

def test_get_nonexistent_todo(client):
    from uuid import uuid4
    response = client.get(f"/todos/{uuid4()}")
    assert response.status_code == 404
```

---

## Running the App

### Set environment variables (optional)

```bash
export APP_NAME="My TODO API"
export APP_DEBUG=true
export DB_HOST=localhost
export DB_PORT=5432
```

### Start the server

```bash
uvicorn todo_app.main:app --reload
```

### Test the API

```bash
# Create a todo
curl -X POST http://localhost:8000/todos \
  -H "Content-Type: application/json" \
  -d '{"title": "Buy groceries"}'

# List all todos
curl http://localhost:8000/todos

# Complete a todo
curl -X POST http://localhost:8000/todos/{id}/complete

# Delete a todo
curl -X DELETE http://localhost:8000/todos/{id}
```

---

## Key Takeaways

1. **Clean separation**: Config, models, repositories, services are all independent
2. **Easy testing**: Swap real repository with fake using `overrides`
3. **No boilerplate**: Dependencies are injected automatically via type hints
4. **Type-safe**: Full typing throughout the codebase
5. **Async-ready**: Use `aget()` and `ashutdown()` when needed

---

## Next Steps

- Add a real database (PostgreSQL, SQLite)
- Add authentication with AOP interceptors
- Add caching layer
- Deploy with Docker

See the [Cookbook](../cookbook/README.md) for more advanced patterns.
