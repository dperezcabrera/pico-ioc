import logging

# Suppress griffe warnings about missing type annotations in strict mode.
# These are cosmetic and don't affect documentation generation.
# griffe's logger is patched by mkdocstrings to use mkdocs.plugins.* namespace.
for name in ("griffe", "mkdocs.plugins.griffe", "_griffe"):
    logging.getLogger(name).setLevel(logging.ERROR)
