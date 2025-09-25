# Integration: AI & LangChain 🦜🔗

AI applications, especially those built with libraries like **LangChain**, often involve creating complex graphs of interconnected objects:
* **LLMs** (e.g., `ChatOpenAI`, `ChatAnthropic`), requiring API keys and model configurations.
* **Prompt Templates**, containing the core instructions and logic.
* **Retrievers** (like `VectorStore` retrievers), needing database connections or index paths.
* **Chains** (e.g., `RetrievalQA`, `LCEL Runnables`), orchestrating the flow between these components.

**Problem:** 😟 Manually wiring these components together often leads to hard-coded factory functions or monolithic scripts. This makes it difficult to:
* **Configure:** Swap LLMs (e.g., `GPT-4o` vs. `Claude 3`) or prompt versions without code changes.
* **Test:** Isolate and mock components like the LLM for unit tests.
* **Maintain:** Understand and modify the complex object graph.

```python
# The "hard-coded" way 😥
def create_my_app():
    # Hard-coded keys, models, paths...
    llm = ChatOpenAI(api_key="sk-...", model="gpt-4o")
    embeddings = OpenAIEmbeddings(api_key="sk-...")

    # Hard-coded connection/path
    db = FAISS.load_local("my_index", embeddings)
    retriever = db.as_retriever()

    # Hard-coded prompt logic
    prompt = PromptTemplate.from_template("Answer based on context: {context} \nQuestion: {question}")

    # Final object construction is rigid
    chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, prompt=prompt)
    return chain
```

**Solution:** ✅ Use `pico-ioc` to manage these LangChain objects as **configurable components**. Define recipes for creating LLMs, prompts, retrievers, and chains using factories, and inject them where needed. This makes your AI application flexible, testable, and easier to manage.

-----

## 1\. The Pattern: Factories for AI Components

The recommended pattern is to use `@factory` and `@provides` to define how each piece of your AI stack is created. Your main application services then simply request the final `Chain`, `Runnable`, or `Agent` by its type.

Let's refactor the example above using `pico-ioc`.

### Step 1: Configure API Keys and Settings

Use `@configuration` or `@configured` (for more complex setups) to load API keys, model names, and other settings securely, typically from environment variables or configuration files.

```python
# app/config.py
from dataclasses import dataclass
from pico_ioc import configuration

# Example using flat key-value from environment variables
@configuration(prefix="AI_") # Looks for AI_OPENAI_API_KEY, etc.
@dataclass
class AiConfig:
    OPENAI_API_KEY: str
    ANTHROPIC_API_KEY: str | None = None # Optional key
    DEFAULT_MODEL: str = "gpt-4o"
```

*(See [Configuration Guides](../user-guide/configuration-basic.md) for more on `@configuration` and `@configured`)*

-----

### Step 2: Create Factories for Primitives (LLMs, Embeddings, Retrievers)

Define `@factory` classes that depend on the `AiConfig` and provide the necessary LangChain primitives. Use `@provides(InterfaceType)` to register implementations.

```python
# app/llms.py
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from pico_ioc import factory, provides
from .config import AiConfig # Import the config dataclass

@factory
class LlmFactory:
    def __init__(self, config: AiConfig):
        # Inject the configuration
        self.config = config

    # Provides the BaseChatModel interface. If you added another provider
    # for BaseChatModel (e.g., ChatAnthropic), you would need to mark one
    # as primary=True to resolve ambiguity for direct injection requests.
    @provides(BaseChatModel)
    def build_default_openai_llm(self) -> BaseChatModel:
        print(f"🏭 Creating ChatOpenAI with model: {self.config.DEFAULT_MODEL}")
        return ChatOpenAI(
            api_key=self.config.OPENAI_API_KEY,
            model=self.config.DEFAULT_MODEL
        )

    # Provides the Embeddings interface. Similar to above, primary=True
    # would be needed if multiple implementations existed.
    @provides(Embeddings)
    def build_default_openai_embeddings(self) -> Embeddings:
        print("🏭 Creating OpenAIEmbeddings")
        return OpenAIEmbeddings(api_key=self.config.OPENAI_API_KEY)

    # --- Add other providers if needed ---
    # @provides(BaseChatModel, qualifiers=["claude"])
    # def build_claude_llm(self) -> BaseChatModel:
    #     if not self.config.ANTHROPIC_API_KEY: raise ValueError(...)
    #     return ChatAnthropic(api_key=self.config.ANTHROPIC_API_KEY, ...)
```

```python
# app/retrievers.py
# Example for a retriever - adapt based on your vector store
from langchain_community.vectorstores import FAISS # Example
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.embeddings import Embeddings
from pico_ioc import factory, provides, component

# Assume FAISS index is pre-built and saved at this path
INDEX_PATH = "my_faiss_index"

@factory
class RetrieverFactory:
    def __init__(self, embeddings: Embeddings):
        # Inject the Embeddings component (provided by LlmFactory)
        self.embeddings = embeddings

    @provides(VectorStoreRetriever)
    def build_faiss_retriever(self) -> VectorStoreRetriever:
        print(f"🏭 Loading FAISS index from: {INDEX_PATH}")
        # In a real app, handle index existence checks
        try:
            # Adjust security as needed for deserialization
            db = FAISS.load_local(INDEX_PATH, self.embeddings, allow_dangerous_deserialization=True)
            return db.as_retriever()
        except Exception as e:
            print(f"❌ Error loading FAISS index: {e}")
            # Fallback or raise - depending on application needs
            raise RuntimeError(f"Could not load vector index from {INDEX_PATH}") from e

# Alternative: Define retriever directly if simple
# @component
# class MyRetriever(VectorStoreRetriever): ...
```

-----

### Step 3: Create a Factory for Your Chain/Runnable

Now, define another factory that builds your final LangChain object (e.g., `RetrievalQA` or a custom LCEL `Runnable`). This factory injects the *base types* (`BaseChatModel`, `VectorStoreRetriever`, etc.) provided by the other factories.

```python
# app/chains.py
from pico_ioc import factory, provides
from langchain_core.language_models import BaseChatModel
from langchain_core.vectorstores import VectorStoreRetriever
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable # For LCEL example

@factory
class ChainFactory:
    # Inject the LLM and Retriever provided by other factories
    def __init__(self, llm: BaseChatModel, retriever: VectorStoreRetriever):
        self.llm = llm
        self.retriever = retriever
        print(f"🏭 ChainFactory initialized with LLM: {type(llm).__name__}, Retriever: {type(retriever).__name__}")

    @provides(PromptTemplate) # Provide the specific prompt for this chain
    def build_qa_prompt(self) -> PromptTemplate:
        # Prompt logic is cleanly encapsulated here
        template_str = """Use the following pieces of context to answer the question at the end.
If you don't know the answer, just say that you don't know, don't try to make up an answer.
Context: {context}
Question: {question}
Helpful Answer:"""
        return PromptTemplate.from_template(template_str)

    @provides(RetrievalQA) # Provide the final chain object
    def build_qa_chain(self, prompt: PromptTemplate) -> RetrievalQA:
        # This builds the RetrievalQA chain using the injected components
        # (llm, retriever) and the prompt provided by this same factory.
        print("🏭 Building RetrievalQA chain...")
        return RetrievalQA.from_chain_type(
            llm=self.llm,
            retriever=self.retriever,
            chain_type_kwargs={"prompt": prompt},
            return_source_documents=False # Example option
        )

    # --- Alternative using LCEL (LangChain Expression Language) ---
    # @provides(Runnable, name="qa_runnable") # Give it a name if providing Runnable interface
    # def build_qa_runnable(self, prompt: PromptTemplate) -> Runnable:
    #     from langchain_core.output_parsers import StrOutputParser
    #     from langchain_core.runnables import RunnablePassthrough
    #
    #     def format_docs(docs):
    #         return "\n\n".join(doc.page_content for doc in docs)
    #
    #     rag_chain = (
    #         {"context": self.retriever | format_docs, "question": RunnablePassthrough()}
    #         | prompt
    #         | self.llm
    #         | StrOutputParser()
    #     )
    #     print("🏭 Building LCEL Runnable chain...")
    #     return rag_chain
```

-----

### Step 4: Use the Chain/Runnable in Your Service

Your final application service becomes very clean and focused. It simply injects the final LangChain object (`RetrievalQA` or `Runnable`) by its type and uses it. It's completely decoupled from *how* the chain was configured or constructed.

```python
# app/services.py
from pico_ioc import component
from langchain.chains import RetrievalQA # Or 'Runnable' for LCEL
# from langchain_core.runnables import Runnable

@component
class AiService:
    # Inject the final chain object provided by ChainFactory
    def __init__(self, qa_chain: RetrievalQA):
    # Or for LCEL: def __init__(self, qa_runnable: Runnable):
        self.qa_chain = qa_chain
        print(f"✅ AiService initialized with chain: {type(qa_chain).__name__}")

    def ask_question(self, query: str) -> str:
        # Just use the injected chain/runnable
        print(f"❓ AiService processing query: '{query}'")
        # For RetrievalQA
        result = self.qa_chain.invoke({"query": query})
        # For LCEL Runnable directly taking string input
        # result = self.qa_chain.invoke(query)

        # Extract answer (may vary based on chain type)
        answer = result.get("result", str(result)) if isinstance(result, dict) else str(result)
        print(f"💡 AiService received answer: '{answer[:50]}...'")
        return answer
```

-----

## 2\. Benefits of This Pattern 🌟

1.  **Testability:** Unit testing `AiService` is now straightforward. Use `init(overrides={...})` in your tests to replace `RetrievalQA` (or `Runnable`) with a simple mock that returns predefined answers, completely isolating your service from actual LLM calls or database access.
    ```python
    # tests/test_ai_service.py
    import pytest
    from pico_ioc import init
    from app.services import AiService
    from langchain.chains import RetrievalQA # Or Runnable

    class MockQaChain: # Mock needs to match the expected interface
        def invoke(self, inputs: dict) -> dict:
            print(f" MOCK Chain received: {inputs}")
            return {"result": f"Mock answer for '{inputs.get('query')}'"}

    @pytest.fixture
    def test_container():
        # Override the chain component for testing
        container = init(
            modules=["app.services"], # Only need the service module
            overrides={
                RetrievalQA: MockQaChain() # Replace real chain with mock
             # Or for LCEL: Runnable: MockQaChain() # Assuming registered by type
            }
        )
        return container

    def test_ask_question_uses_mock(test_container):
        service = test_container.get(AiService)
        answer = service.ask_question("What is pico-ioc?")
        assert answer == "Mock answer for 'What is pico-ioc?'"
    ```
2.  **Configurability:** Need to switch from `gpt-4o` to `Claude 3` or change the prompt? You only need to modify the relevant **factory** (`LlmFactory` or `ChainFactory`) or the **configuration source** (e.g., `config.yml` or environment variables). Your `AiService` remains completely unchanged. This is ideal for A/B testing prompts, models, or adapting to different environments. ⚙️
3.  **Separation of Concerns:** Each part of your AI application has a clear responsibility:
      * `config.py`: Handles **settings** and **keys**. 🔑
      * `llms.py`, `retrievers.py`, `embeddings.py`: Handle **primitive component creation**. 🧱
      * `chains.py`: Handles **orchestration logic** and **prompt engineering**. 🧠
      * `services.py`: Handles the **business use case** of the AI functionality. 🎯

This pattern significantly improves the structure, maintainability, and testability of complex AI applications built with libraries like LangChain.

-----

## Next Steps

This concludes the "Integrations" section. You've seen patterns for using `pico-ioc` effectively with popular web frameworks and complex libraries like LangChain.

The next section, **Cookbook**, provides complete, runnable examples of full architectural patterns combining multiple `pico-ioc` features.

  * **[Cookbook Overview](../cookbook/README.md)**: Explore common architectural patterns like Multi-Tenancy, Hot Reload, CQRS, and more. 🧑‍🍳

