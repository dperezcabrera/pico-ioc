# FastAPI TODO App

A complete REST API example using FastAPI and pico-ioc for dependency injection.

## Requirements

- Python 3.11+

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
uvicorn todo_app.main:app --reload
```

## Test the API

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

## API Docs

Open http://127.0.0.1:8000/docs for interactive Swagger UI.
