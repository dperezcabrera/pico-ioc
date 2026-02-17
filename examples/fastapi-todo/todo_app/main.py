from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pico_ioc import init, configuration
from pico_fastapi import PicoFastAPI

from .config import AppConfig
from .services import TodoService
from .models import Todo


class TodoCreate(BaseModel):
    title: str


class TodoResponse(BaseModel):
    id: UUID
    title: str
    completed: bool

    @classmethod
    def from_domain(cls, todo: Todo) -> "TodoResponse":
        return cls(id=todo.id, title=todo.title, completed=todo.completed)


container = init(
    modules=[
        "todo_app.config",
        "todo_app.repositories",
        "todo_app.services",
    ],
    config=configuration(),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await container.ashutdown()


app = FastAPI(lifespan=lifespan)
pico = PicoFastAPI(container)
pico.install(app)

app_config = container.get(AppConfig)
app.title = app_config.name


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
