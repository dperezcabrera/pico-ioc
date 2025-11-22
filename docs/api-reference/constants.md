# Constants

Overview

This module provides a single source of truth for:

- The project-level logger name and a shared logger instance.
- String constants used as keys and identifiers across the pico_ioc project.

Centralizing these values reduces magic strings, typos, and inconsistencies in logging and configuration. Importing and reusing these constants helps ensure your code integrates predictably with pico_ioc internals.

## Importing

Use the module directly from the package:

```python
from pico_ioc import constants
```

Or import specific attributes as needed:

```python
from pico_ioc.constants import LOGGER_NAME, LOGGER
```

## Logger

What is it?

- LOGGER_NAME: The canonical name of the pico_ioc logger.
- LOGGER: The shared logging.Logger instance configured with LOGGER_NAME.

How do I use it?

- Configure handlers, formatters, and level once on the shared LOGGER.
- Create child loggers for subsystems using the known LOGGER_NAME.
- Integrate pico_ioc logs into your application’s logging setup without guessing names.

Examples

Configure pico_ioc logging in your application:

```python
import logging
from pico_ioc.constants import LOGGER_NAME, LOGGER

# Option A: Use the shared instance, if provided.
LOGGER.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(levelname)s %(name)s: %(message)s'))
LOGGER.addHandler(handler)

# Option B: Derive a child logger by name.
component_logger = logging.getLogger(f"{LOGGER_NAME}.container")
component_logger.debug("Container initialized")
```

Silence pico_ioc logs or route them to a separate handler:

```python
import logging
from pico_ioc import constants

# Silence all pico_ioc logs below WARNING
logging.getLogger(constants.LOGGER_NAME).setLevel(logging.WARNING)

# Send pico_ioc logs to a dedicated file
file_handler = logging.FileHandler("pico_ioc.log")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.getLogger(constants.LOGGER_NAME).addHandler(file_handler)
```

## Keys and Identifiers

What is it?

The module defines multiple string constants used as keys/identifiers across pico_ioc. These values are shared by container components, configuration structures, metadata, and integration points where consistent keys are required.

How do I use it?

- Prefer the exported constants over hard-coded strings when building or consuming pico_ioc metadata and configuration.
- Use these constants as dictionary keys, attribute names, or annotations where the project expects specific identifiers.
- Introspect the module to discover available keys at runtime if you are building generic tooling.

Examples

Avoid magic strings in configuration:

```python
from pico_ioc import constants

# Example: building a config or metadata dict for a component
component_meta = {
    # Replace "id", "scope", etc. with constants defined in pico_ioc.constants
    # e.g., constants.COMPONENT_ID, constants.SCOPE, constants.FACTORY, ...
    # The actual constant names are defined in the module.
    # This is illustrative; prefer constants to hard-coded strings.
}

# Later in processing:
def process_meta(meta: dict):
    # Example of reading values using known constants
    # id_value = meta.get(constants.COMPONENT_ID)
    # scope = meta.get(constants.SCOPE)
    pass
```

Discover all exported string keys for debugging or tooling:

```python
from pico_ioc import constants

string_keys = [
    (name, value)
    for name, value in vars(constants).items()
    if isinstance(value, str) and name.isupper()
]

for name, value in string_keys:
    print(f"{name} = {value}")
```

## Reference

Exports

- LOGGER_NAME: str
  - The canonical logger name used by pico_ioc. Use this to retrieve or configure the library logger via logging.getLogger(LOGGER_NAME) and to create hierarchical child loggers.
- LOGGER: logging.Logger
  - The shared logger instance bound to LOGGER_NAME. Attach handlers and set levels here to manage pico_ioc logging across your application.

String constants

- The module provides multiple uppercase, snake-case string constants representing keys and identifiers used throughout pico_ioc internals and extension points.
- For the authoritative list in your installed version, introspect the module at runtime or view the source. Prefer these constants to hard-coded strings to maintain compatibility over time.

## Notes

- Treat the constants as stable identifiers; do not reassign or mutate them.
- If you replace or wrap logging in your application, respect LOGGER_NAME to keep pico_ioc logs coherent.
- The shared LOGGER uses standard Python logging; configuration follows normal logging practices (handlers, formatters, levels, propagation).