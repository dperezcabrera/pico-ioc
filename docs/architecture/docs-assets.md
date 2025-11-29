# Docs assets

## Overview

This front-end asset provides small, site-wide enhancements for the pico-ioc documentation when rendered with MkDocs and the Material theme.

What it does:
- Improves the copy button on code blocks so that copied snippets are “cleaned” (for example, shell prompts like $ or >>> are stripped).
- Logs a console notice when readers are viewing an older documentation version, helping you surface upgrade cues without intrusive UI.

This asset is pure client-side JavaScript that you include via mkdocs.yml. It is designed to be defensive and theme-friendly, requiring minimal maintenance.

## Quick start

1) Add the script to your docs
- Place the file at docs/javascripts/assets.js (or any path under docs/).

2) Register it in mkdocs.yml
```yaml
theme:
  name: material

extra_javascript:
  - javascripts/assets.js
```

3) (Optional) Provide version metadata for better “old version” notices
- If you version your docs, add meta tags via a theme override so the script can identify the current and latest versions.

Create overrides/partials/head.html and wire it in mkdocs.yml:

```yaml
theme:
  name: material
  custom_dir: overrides
```

overrides/partials/head.html:
```jinja
{% if config.extra and config.extra.docs %}
  {% if config.extra.docs.version %}
    <meta name="doc-version" content="{{ config.extra.docs.version }}">
  {% endif %}
  {% if config.extra.docs.latest %}
    <meta name="doc-latest" content="{{ config.extra.docs.latest }}">
  {% endif %}
{% endif %}
```

Then set values in mkdocs.yml:
```yaml
extra:
  docs:
    version: 1.4.2
    latest: 2.0
```

If you use mike for versioned docs, you can skip the meta tags and let the script fall back to a URL-based heuristic (see “Old version notice” below).

## How-to guides

### Enhance the copy button for code blocks

Goal:
- When users click the copy button on a code block, the clipboard should contain runnable code (no shell prompts, REPL symbols, or line numbers).

Example implementation for docs/javascripts/docs-assets.js:
```js
(function () {
  'use strict';

  // Copy button enhancement: sanitize copied text from code blocks.
  document.addEventListener('click', async (ev) => {
    // Material provides a copy button; use event delegation to catch clicks.
    const btn = ev.target.closest('[data-clipboard-target], .md-clipboard, .md-clipboard--inline');
    if (!btn) return;

    // Resolve the code element the button is associated with.
    const selector = btn.getAttribute('data-clipboard-target');
    const container = selector ? document.querySelector(selector) : btn.closest('.highlight, pre, code, .md-typeset');
    if (!container) return;

    const codeEl = container.querySelector('code, pre code') || container.querySelector('pre') || container;
    if (!codeEl) return;

    // Read visible text to preserve wrapping as rendered.
    let text = codeEl.innerText || codeEl.textContent || '';

    // Strip common prompts and artifacts.
    const sanitize = (s) => s
      .split('\n')
      // Remove typical shell and REPL prompts: $, #, >>>, ..., In [1]:
      .map(line => line
        .replace(/^\s*(\$|#|>>>|\.\.\.)\s?/, '')
        .replace(/^\s*In \[\d+\]:\s?/, '')
        .replace(/^\s*\(\d+\)\s/, '')
      )
      .join('\n')
      // Drop trailing blank lines, keep original newlines otherwise.
      .replace(/\s+$/, '');

    const cleaned = sanitize(text);

    try {
      await navigator.clipboard.writeText(cleaned);
      // Optional visual feedback for the user
      btn.classList.add('is-copied');
      setTimeout(() => btn.classList.remove('is-copied'), 1200);
      ev.preventDefault();
      ev.stopPropagation();
    } catch (err) {
      // If Clipboard API is unavailable (older browsers), fall back silently.
      console.warn('[docs-assets] Clipboard write failed; using default behavior', err);
    }
  }, true);
})();
```

Optional CSS for a subtle “Copied” state:
```css
/* Place under docs/stylesheets/docs-assets.css and register via extra_css */
.md-clipboard.is-copied::after,
.md-clipboard--inline.is-copied::after {
  content: 'Copied';
  margin-left: .25rem;
  font-size: .75em;
  color: var(--md-accent-fg-color);
}
```

Register the stylesheet in mkdocs.yml if you add it:
```yaml
extra_css:
  - stylesheets/docs-assets.css
```

Notes:
- The script uses event delegation to stay compatible with Material’s dynamic content loading and partial page reloads.
- Sanitization keeps code runnable by removing leading prompts and common REPL markers while preserving original structure.

### Log a notice for older documentation versions

Goal:
- Surface a non-intrusive console notice when a user is browsing an older version of the docs, to encourage upgrades or cross-checks.

Approach:
- Prefer meta tags to declare the current and latest versions; fall back to URL heuristics commonly used by versioned docs (e.g., mike’s /latest/ path).

Example implementation (add to the same docs-assets.js, below the copy handler):
```js
(function () {
  'use strict';

  // Version awareness: log a console notice if this isn't the latest docs.
  const metaVersion = document.querySelector('meta[name="doc-version"]')?.getAttribute('content') || null;
  const metaLatest  = document.querySelector('meta[name="doc-latest"]')?.getAttribute('content') || null;

  const byMeta = metaVersion && metaLatest && metaVersion !== metaLatest;

  // Common heuristic for mike or similar setups: latest or stable in the URL is current.
  const byUrl = !/\/(latest|stable)\//.test(window.location.pathname);

  if (byMeta || byUrl) {
    const current = metaVersion || '(unknown)';
    const latest  = metaLatest  || 'latest';
    // Console-only notice to avoid layout shifts.
    // You can replace with a banner if desired.
    console.info(`[docs] You are viewing an older version of the documentation (current: ${current}, latest: ${latest}).`);
  }
})();
```

Options:
- If you prefer a visible banner, replace the console.info call with DOM insertion at the top of .md-content. Keep it lightweight to avoid Cumulative Layout Shift.

## Reference

### File layout

- JavaScript: docs/javascripts/docs-assets.js
- Optional CSS: docs/stylesheets/docs-assets.css
- Optional Jinja override for meta tags: overrides/partials/head.html

### mkdocs.yml entries

- Register scripts and styles:
```yaml
extra_javascript:
  - javascripts/docs-assets.js

extra_css:
  - stylesheets/docs-assets.css
```

- Provide version info (optional but recommended if you need precise semantics):
```yaml
theme:
  name: material
  custom_dir: overrides

extra:
  docs:
    version: 1.4.2
    latest: 2.0
```

### DOM hooks and selectors

- Copy button:
  - The script listens at document level for clicks on:
    - [data-clipboard-target]
    - .md-clipboard
    - .md-clipboard--inline
  - It resolves the target code element by the data-clipboard-target selector or by finding a nearby pre/code.

- Version notice:
  - Meta tags: <meta name="doc-version" content="...">, <meta name="doc-latest" content="...">
  - URL heuristic: window.location.pathname checked for /latest/ or /stable/.

### Environment expectations

- Material for MkDocs renders copy buttons when content.code.copy is enabled (default in recent versions). Even without it, the script defensively locates code blocks.
- Clipboard API support is required for the enhanced copy behavior; users on very old browsers will fall back to the theme’s default behavior.

## Rationale and caveats

Why sanitize copied code?
- Code examples often include shell prompts or REPL markers for readability. That’s noise when pasting into a terminal or file. Automatic cleanup reduces friction and errors.

Why a console notice for old versions?
- It’s a low-noise cue for power users and CI-driven link checks. You can later replace it with a visible banner if needed.

Caveats:
- If your code samples intentionally include leading $ or >>> as part of the code, consider adding a class like .no-sanitize to those blocks and skip cleanup for them in the script.
- If you rely on custom versioning paths, adjust the URL heuristic accordingly (e.g., /v1/, /docs/1.x/).
