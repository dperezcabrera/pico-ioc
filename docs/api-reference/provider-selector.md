# ProviderSelector

## Overview

ProviderSelector is a small utility that chooses the “best” provider for each logical key (for example: chat, embeddings, moderation) from a list of candidate providers. It ranks candidates using:

- Whether the provider is configured in a ConfigurationManager
- The provider’s pico_name length
- A candidate’s primary flag

The result is a mapping of keys to the selected provider and its metadata, allowing you to forward requests to the most appropriate backend with minimal decision logic scattered throughout your code.

This is useful when you maintain multiple provider options per capability and want a deterministic, configuration-aware way to pick one at runtime.

## How do I use it?

### Quick start

1. Prepare candidate providers for each key.
2. Instantiate ProviderSelector with your ConfigurationManager.
3. Call select_providers with the candidates mapping.

### Example

```python
# Example ConfigurationManager stub for illustration.
class ConfigurationManager:
    def __init__(self, configured_picos):
        # e.g., {"openai:gpt-4o-mini", "openai:text-embedding-3-large"}
        self._configured = set(configured_picos)

    def has(self, pico_name: str) -> bool:
        # Returns True if this pico_name has an active configuration
        return pico_name in self._configured


from typing import Dict, List, Any

# Example candidates: mapping of capability keys to candidate provider records
candidates: Dict[str, List[dict]] = {
    "chat": [
        {
            "pico_name": "openai:gpt-4o-mini",
            "provider": "openai",
            "primary": True,
            "meta": {"model": "gpt-4o-mini", "endpoint": "https://api.openai.com/v1/chat"}
        },
        {
            "pico_name": "openai:gpt-3.5-turbo",
            "provider": "openai",
            "primary": False,
            "meta": {"model": "gpt-3.5-turbo", "endpoint": "https://api.openai.com/v1/chat"}
        },
        {
            "pico_name": "other:chat-fast",
            "provider": "other",
            "primary": False,
            "meta": {"model": "chat-fast", "endpoint": "https://api.other.ai/chat"}
        }
    ],
    "embedding": [
        {
            "pico_name": "openai:text-embedding-3-large",
            "provider": "openai",
            "primary": True,
            "meta": {"model": "text-embedding-3-large", "endpoint": "https://api.openai.com/v1/embeddings"}
        },
        {
            "pico_name": "cohere:embed-multilingual-v3",
            "provider": "cohere",
            "primary": False,
            "meta": {"model": "embed-multilingual-v3", "endpoint": "https://api.cohere.ai/embed"}
        }
    ]
}

# Instantiate your configuration manager with the active provider configurations
config_manager = ConfigurationManager({
    "openai:gpt-4o-mini",
    "openai:text-embedding-3-large"
})

# Instantiate the selector
selector = ProviderSelector(config_manager=config_manager)

# Select the best providers per key
selected = selector.select_providers(candidates)

# Result: a mapping of key -> chosen candidate record (including its metadata)
for key, chosen in selected.items():
    print(f"{key}: {chosen['pico_name']} (provider={chosen['provider']}, primary={chosen.get('primary')})")
    # Use chosen['meta'] to configure your client
```

### Inputs and outputs

- Input to select_providers:
  - A dict mapping logical keys (str) to a list of candidate records (dict).
  - Each candidate should include at least:
    - pico_name: a unique identifier for the provider/model
    - primary: bool flag indicating preferred default among peers
    - meta: arbitrary metadata (model name, endpoint, parameters)
    - Optional fields like provider or anything else your app needs

- Output from select_providers:
  - A dict mapping each key to the single chosen candidate record.
  - The chosen record is one of the input candidates and contains its metadata.

## API reference

### ProviderSelector

#### __init__(self, config_manager)

- Parameters:
  - config_manager: ConfigurationManager instance used to check whether a pico_name is configured/available.
- Purpose:
  - Injects configuration awareness into the selection process. Providers with active configuration are ranked higher.

#### select_providers(self, candidates)

- Parameters:
  - candidates: dict[str, list[dict]]
    - Mapping of keys to candidate records.
- Returns:
  - dict[str, dict]
    - Mapping of keys to the chosen candidate record (including its original metadata).
- Behavior:
  - For each key, ranks candidate records using _rank_provider and returns the top-ranked item.

#### _rank_provider(self, item)

- Parameters:
  - item: dict
    - A single candidate record containing pico_name, primary, and other fields.
- Returns:
  - A sort key or score used internally to determine ordering.
- Notes:
  - Internal method. Not intended for external use.
  - Ranking incorporates configuration presence, pico_name length, and the primary flag.

## Selection algorithm (explanation)

ProviderSelector applies a deterministic ranking to each candidate list:

- Configuration presence:
  - Candidates whose pico_name is known to config_manager (e.g., has active credentials/settings) are prioritized.
- Primary flag:
  - If multiple candidates are equally configured, those marked primary are preferred.
- Pico_name length:
  - Used as a tie-breaker to disambiguate otherwise equivalent candidates.
  - This helps avoid non-determinism when metadata is identical across providers.
  - If your selection semantics depend on this, be consistent with your pico_name naming scheme.

The exact ordering and tie-breaking implementation depend on the version in your codebase. In general, configure the providers you intend to prefer, mark your default as primary, and rely on pico_name naming as a last resort for stable sorting.

## Tips

- Always include a primary candidate in each list to make intent explicit.
- Keep pico_name values consistent and meaningful; the selector uses them for tie-breaking.
- Ensure ConfigurationManager accurately reflects availability (credentials, endpoints, quotas).
- If you need custom ranking criteria, wrap or extend ProviderSelector to introduce your own weights or fields.

---

## Auto-generated API

::: pico_ioc.provider_selector