# Integration: Django

Django is a powerful, "batteries-included" framework with its own monolithic structure, ORM, and request lifecycle. Unlike Flask or FastAPI, you typically don't replace its core systems.

Instead, `pico-ioc` is most effective in Django when used to create a clean, decoupled **service layer** that lives *alongside* Django's views and models.

**The Goal:** Keep your `views.py` thin. All complex business logic should live in `pico-ioc`-managed services.

This recipe shows you how to:
1.  Initialize a global `pico-ioc` container when your Django app starts.
2.  Use `pico-ioc` to manage your business logic (`services`, `repositories`, etc.).
3.  Call these services from your Django views.
4.  Easily test your business logic in isolation from the Django request/response cycle.

---

## 1. Container Initialization (in `apps.py`)

The best place to initialize your `pico-ioc` container is in the `ready()` method of your app's `AppConfig`. This code runs once when Django starts up.

We'll create a global container instance that your views can access.

```python
# my_django_app/apps.py

from django.apps import AppConfig
from pico_ioc import init, PicoContainer

# 1. Define a global variable to hold the container
container: PicoContainer | None = None

class MyAppConfig(AppConfig):
    name = 'my_django_app'

    def ready(self):
        """
        This method is called by Django when the app is ready.
        """
        global container
        if container is None:
            print("Django app ready. Initializing pico-ioc container...")
            
            # 2. Initialize your container
            container = init(
                modules=[
                    "my_django_app.services",
                    "my_django_app.repositories",
                ],
                profiles=("prod",) # Or load from settings
            )

def get_container() -> PicoContainer:
    """A helper function to safely get the container."""
    if not container:
        raise RuntimeError("pico-ioc container has not been initialized.")
    return container
````

Don't forget to tell Django to use this config in your `my_django_app/__init__.py`:

```python
# my_django_app/__init__.py
default_app_config = 'my_django_app.apps.MyAppConfig'
```

-----

## 2\. Defining Your Service Layer

Now, you can define your components just as you would in any other app. These classes live *outside* the normal Django request flow. They are pure Python, managed by `pico-ioc`.

```python
# my_django_app/services.py
from pico_ioc import component

# This could be a 3rd-party API client
@component
class EmailApiClient:
    def send_email(self, to: str, body: str):
        print(f"Sending email to {to}...")

@component
class UserService:
    def __init__(self, email_client: EmailApiClient):
        self.email_client = email_client
        
    def register_user(self, username: str, email: str):
        # 1. Use Django's ORM (it's fine to import it)
        from .models import User
        user = User.objects.create_user(username=username, email=email)
        
        # 2. Use other injected services
        self.email_client.send_email(
            to=email,
            body=f"Welcome, {username}!"
        )
        return user
```

Notice that `UserService` is a plain class. It's easy to test because you can just inject a `MockEmailApiClient`.

-----

## 3\. Using Services in Django Views

Now, your `views.py` becomes much simpler. Its only job is to handle HTTP, parse data, and call your service layer.

```python
# my_django_app/views.py
import json
from django.http import JsonResponse, HttpRequest
from .apps import get_container # Import our helper
from .services import UserService

def register_user_view(request: HttpRequest):
    if request.method != 'POST':
        return JsonResponse({"error": "Bad method"}, status=405)

    # 1. Get data from the web layer
    data = json.loads(request.body)
    email = data.get('email')
    username = data.get('username')

    try:
        # 2. Get the pico-ioc container
        container = get_container()
        
        # 3. Get your service
        # We use .get() because views are synchronous.
        # .get() is fast because the service is a singleton.
        user_service = container.get(UserService)
        
        # 4. Call your business logic
        user_service.register_user(username, email)
        
        return JsonResponse({"success": True}, status=201)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
```

### What about Request Scopes?

This pattern is simpler and **does not** use `pico-ioc`'s `scope("request")`. Why?

  * Django's request object (`request`) is already passed everywhere and acts as the "request scope."
  * If you need request-specific data, you can pass the `request` object from your view directly into your service method: `user_service.register_user(request, username, email)`.

This keeps your service layer testable, as you only need to mock the `request` object, not a complex `contextvar`.

-----

## Next Steps

This pattern can be adapted for managing complex, non-web parts of a Django application, such as in `management commands` or `celery workers`.

  * **[AI & LangChain](./ai-langchain.md)**: Learn a generic pattern for using `pico-ioc` to manage complex tools, which is very useful for modern AI applications.

