# Cookbook: Pattern: Dynamic LangChain Model/Prompt Selection & Caching

**Goal:** Build a flexible AI application (using LangChain primitives) where the specific LLM model and prompt template can be switched via configuration (e.g., in a `config.yml`) without code changes, and cache LLM responses based on the input.

**Key `pico-ioc` Features:** Tree Configuration (`@configured`), Factories (`@factory`, `@provides`), AOP (`MethodInterceptor`, `@intercepted_by`), Component Injection.

## The Pattern

1.  **Configuration (`config.yml` + `dataclasses`):** Define available LLMs (with keys, models) and Prompts (with templates) in YAML. Also specify the `active_llm_key` and `active_prompt_key`. Use `@configured` to bind this YAML to `dataclass`es.
2.  **LLM Factory:** A `@factory` that:
    * Injects the configuration (`@configured` dataclass).
    * Has `@provides(BaseChatModel)` method that reads `active_llm_key` from config and returns the corresponding instantiated LLM client (e.g., `ChatOpenAI` or `ChatAnthropic`).
3.  **Prompt Factory:** Similar `@factory` for `PromptTemplate`, providing the one specified by `active_prompt_key`.
4.  **Cache Component:** A simple `@component` providing caching (e.g., in-memory dict or Redis client).
5.  **Caching Interceptor (`CachingInterceptor`):** A `@component` implementing `MethodInterceptor`. It:
    * Injects the `Cache` component.
    * Generates a cache key based on method name, args (especially the prompt/input), and potentially the active model name.
    * Checks cache before `call_next`. If hit, returns cached value.
    * If miss, calls `call_next`, stores the result in cache, and returns it.
6.  **Alias (`@cacheable`):** Alias for `@intercepted_by(CachingInterceptor)`.
7.  **AI Service (`AiService`):** A `@component` that:
    * Injects the base types `BaseChatModel` and `PromptTemplate`. `pico-ioc` provides the *active* ones via the factories.
    * Has a method (e.g., `generate_response`) decorated with `@cacheable` that uses the injected LLM and prompt.
8.  **(Optional Hot-Reload):** If using external dynamic configuration, the factories could observe `ConfigurationChangedEvent` to update the active LLM/Prompt if the config changes at runtime.

## Conceptual Implementation

#### Configuration (`config.yml`)
```yaml
llms:
  openai_gpt4:
    type: "openai"
    api_key: "${ENV:OPENAI_KEY}"
    model: "gpt-4o"
  anthropic_claude3:
    type: "anthropic"
    api_key: "${ENV:ANTHROPIC_KEY}"
    model: "claude-3-opus"

prompts:
  summary_v1:
    template: "Summarize this text concisely: {text}"
  summary_v2_detailed:
    template: "Provide a detailed bullet-point summary of the key ideas in: {text}"

# --- Active Configuration ---
active_llm_key: "openai_gpt4"
active_prompt_key: "summary_v2_detailed"
```

#### Dataclasses & Factories (`app/config.py`, `app/factories.py`)

```python
# app/config.py
from dataclasses import dataclass, field
from typing import Dict
from pico_ioc import configured

@dataclass
class LlmConfig:
    type: str
    api_key: str
    model: str

@dataclass
class PromptConfig:
    template: str

@dataclass
class AiAppConfig:
    llms: Dict[str, LlmConfig] = field(default_factory=dict)
    prompts: Dict[str, PromptConfig] = field(default_factory=dict)
    active_llm_key: str = ""
    active_prompt_key: str = ""

@configured(target=AiAppConfig, prefix=None) # Bind the whole YAML
class BoundAiConfig: pass

# app/factories.py
from pico_ioc import factory, provides
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
# from langchain_anthropic import ChatAnthropic # Example
from .config import AiAppConfig

@factory
class AiFactory:
    def __init__(self, config: AiAppConfig):
        self.config = config
        self._llm_cache = {} # Simple instance cache

    @provides(BaseChatModel)
    def provide_active_llm(self) -> BaseChatModel:
        key = self.config.active_llm_key
        if not key: raise ValueError("No active LLM configured")
        
        if key in self._llm_cache: return self._llm_cache[key]

        llm_conf = self.config.llms.get(key)
        if not llm_conf: raise ValueError(f"Config for LLM key '{key}' not found")

        if llm_conf.type == "openai":
            instance = ChatOpenAI(api_key=llm_conf.api_key, model=llm_conf.model)
        # elif llm_conf.type == "anthropic":
        #     instance = ChatAnthropic(api_key=llm_conf.api_key, model=llm_conf.model)
        else:
            raise ValueError(f"Unsupported LLM type: {llm_conf.type}")
        
        self._llm_cache[key] = instance
        print(f"[Factory] Created LLM instance for key: {key}")
        return instance

    @provides(PromptTemplate)
    def provide_active_prompt(self) -> PromptTemplate:
        key = self.config.active_prompt_key
        if not key: raise ValueError("No active prompt configured")
        
        prompt_conf = self.config.prompts.get(key)
        if not prompt_conf: raise ValueError(f"Config for prompt key '{key}' not found")
            
        print(f"[Factory] Providing prompt template for key: {key}")
        return PromptTemplate.from_template(prompt_conf.template)

```

#### Caching (`app/cache.py`, `app/interceptors.py`)

```python
# app/cache.py - Simple in-memory cache
from pico_ioc import component
@component
class SimpleCache:
    def __init__(self): self._cache = {}
    def get(self, key): return self._cache.get(key)
    def set(self, key, value, ttl=None): self._cache[key] = value

# app/interceptors.py - Caching Interceptor
import hashlib
import json
from pico_ioc import component, MethodInterceptor, MethodCtx, intercepted_by
from .cache import SimpleCache

@component
class CachingInterceptor(MethodInterceptor):
    def __init__(self, cache: SimpleCache): self.cache = cache
    
    def generate_key(self, ctx: MethodCtx) -> str:
        # Simple key based on class, method, args, kwargs
        # Use hashing for complex args
        key_data = {
            "cls": ctx.cls.__name__,
            "method": ctx.name,
            "args": ctx.args,
            "kwargs": ctx.kwargs,
        }
        # Use json.dumps with sort_keys for stable serialization
        serialized = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    def invoke(self, ctx: MethodCtx, call_next):
        cache_key = self.generate_key(ctx)
        cached_result = self.cache.get(cache_key)
        
        if cached_result is not None:
            print(f"[Cache] HIT for key {cache_key}")
            return cached_result
        else:
            print(f"[Cache] MISS for key {cache_key}")
            result = call_next(ctx)
            # Add ttl metadata if needed via a @cacheable decorator
            self.cache.set(cache_key, result) 
            return result

cacheable = intercepted_by(CachingInterceptor)
```

#### AI Service (`app/services.py`)

```python
# app/services.py
from pico_ioc import component
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import PromptTemplate
from .interceptors import cacheable # Import the alias

@component
class AiService:
    def __init__(self, llm: BaseChatModel, prompt: PromptTemplate):
        self.llm = llm
        self.prompt = prompt
        print(f"[AiService] Initialized with LLM: {type(llm).__name__}, Prompt template starting with: '{prompt.template[:30]}...'")

    @cacheable # Apply the caching interceptor
    def generate_summary(self, text: str) -> str:
        print("[AiService] Generating summary (cacheable)...")
        chain = self.prompt | self.llm
        response = chain.invoke({"text": text})
        # Assuming response is content string or similar
        return response.content if hasattr(response, 'content') else str(response)

```

*(The `main.py` would initialize with `YamlTreeSource` and `tree_config`, then call `generate_summary` multiple times to show caching and potentially demonstrate changing the `active_...` keys in config between runs).*

## Benefits

  * **Flexibility:** Switch models/prompts via config, ideal for A/B testing or environment differences.
  * **Performance:** Caching reduces redundant LLM calls, saving time and cost.
  * **Testability:** Factories and the service can be tested by injecting mock configs or mock LLM/Prompts.
  * **Clean Code:** Service logic remains simple, unaware of complex configuration or caching details.

