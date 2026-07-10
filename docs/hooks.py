import logging

# Suppress griffe warnings about missing type annotations in strict mode.
# These are cosmetic and don't affect documentation generation.
# griffe's logger is patched by mkdocstrings to use mkdocs.plugins.* namespace.
for name in ("griffe", "mkdocs.plugins.griffe", "_griffe"):
    logging.getLogger(name).setLevel(logging.ERROR)


# --- AI-first: generate /llms-full.txt at build (full docs, one file) ---
def on_post_build(config):
    import pathlib

    docs = pathlib.Path(config["docs_dir"])
    site = pathlib.Path(config["site_dir"])
    parts = []
    for md in sorted(docs.rglob("*.md")):
        rel = md.relative_to(docs)
        try:
            body = md.read_text(encoding="utf-8")
        except Exception:
            continue
        parts.append(f"<!-- {rel} -->\n\n{body}")
    (site / "llms-full.txt").write_text("\n\n---\n\n".join(parts), encoding="utf-8")
