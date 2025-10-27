# Pico-IoC Configuration Spec (v1)

This is the normative reference for configuration after ADR-0010.

## 1. Goals
- Single binding model with `@configured`.
- Deterministic resolution across heterogeneous sources (ENV, files, dicts, CLI).
- Pythonic DX: `snake_case` in code, `UPPER_CASE` in ENV, minimal ceremony.

## 2. Terminology
- Flat mapping: top-level fields mapped directly to `PREFIX_FIELD` keys.
- Tree mapping: nested structure mapped under a `prefix` with path segments joined by `__` in ENV.
- Source: any `get(key) -> Optional[str]` provider (flat) or tree provider that can be merged.
- Precedence: `Value(...)` > `overrides` > sources left-to-right.

## 3. Decorator

### 3.1 Signature
`@configured(prefix: str = "", mapping: Literal["auto","flat","tree"]="auto")`

### 3.2 Auto-detection
- If any field type is dataclass, list, dict, or Union → `tree`.
- If all fields are primitives (`str`, `int`, `float`, `bool`) → `flat`.
- Explicit `mapping` overrides detection.

### 3.3 Normalization
- Code fields use `snake_case`.
- ENV keys use `UPPER_CASE`.
- Conversion is bijective on ASCII letters and underscores.
- Tree path separator in ENV is `__`.

## 4. Runtime Builder

### 4.1 `ContextConfig`
Opaque object that encapsulates an ordered pipeline of sources and optional overrides.

### 4.2 `configuration(...)`
Creates a `ContextConfig`.

Parameters:
- `*sources`: ordered list of sources. The last source has highest priority among sources unless overridden.
- `overrides`: dict-like patches applied after all sources.
- `values`: explicit field assignments equivalent to `Value(...)` annotations but applied externally.
- `profiles`: optional activation tags for conditional bindings.

Return:
- `ContextConfig`

## 5. Sources

### 5.1 Flat Sources
- `EnvSource(prefix: str = "")`
- `FlatDictSource(data: Mapping[str, Any], prefix: str = "", case_sensitive: bool = True)`

Behavior:
- Keys are looked up as `prefix + FIELD`.
- `FIELD` is the UPPER_CASE of the dataclass field name.
- Values are strings and are coerced per type rules.

### 5.2 Tree Sources
- `EnvTreeSource(prefix: str = "", case_sensitive: bool = True)`
- `DictSource(data: Mapping[str, Any])`
- `JsonTreeSource(path: str)`
- `YamlTreeSource(path: str)`

Behavior:
- Keys are resolved by walking the tree under `prefix`.
- ENV keys use `prefix + A__B__C` where `A,B,C` are UPPER_CASE of path segments.

### 5.3 Merging Rules
- Tree sources are merged by deep-merge:
  - Dict vs Dict: merge per key; right side wins on conflicts.
  - List vs List: right side replaces left (no per-index merge).
  - Scalar vs anything: right side replaces left.

## 6. Precedence

1. `Value(...)` (from `Annotated` or `configuration(values=...)`)
2. `overrides` passed to `configuration(...)`
3. Sources in the order provided to `configuration(...)` (left to right). Later sources override earlier ones.

If both flat and tree provide a value for the same field:
- The flat value wins.

## 7. Coercion and Validation

### 7.1 Primitives
- `str`: identity
- `int`: decimal or prefixed with `+`/`-`
- `float`: standard float literals
- `bool`: `1,true,yes,on,y,t` → True; `0,false,no,off,n,f` → False (case-insensitive)

### 7.2 Collections
- `list[T]`: accept JSON array string in flat sources, or array in tree sources.
- `dict[str, T]`: accept JSON object string in flat, or object in tree.

### 7.3 Dataclasses
- Built field-by-field. Missing required fields cause an error.

### 7.4 Unions and Discriminators
- If `Annotated[Union[A,B], Discriminator("type")]` is used and the node contains `"type": "A"`,
  resolve to `A` after removing the discriminator key from the node.
- If no match, raise an error with the dot-path.

### 7.5 Errors
- Always include the field path in error messages.
- On coercion failures, error out; do not silently default.

## 8. Interpolation (Optional)
If interpolation is enabled, `${VAR}` within string values is resolved using the same precedence chain.
Unresolved variables cause an error unless `allow_unresolved=True` is explicitly set.

## 9. Examples

### 9.1 Flat-only dataclass
```python
@configured(prefix="APP_", mapping="auto")
@dataclass
class Server:
    host: str
    port: int
```

ENV:

```
APP_HOST=0.0.0.0
APP_PORT=8080
```

### 9.2 Tree with ENV and JSON

```python
@configured(prefix="APP_", mapping="tree")
@dataclass
class Db:
    host: str
    port: int
```

ENV:

```
APP_DB__HOST=127.0.0.1
APP_DB__PORT=5432
```

### 9.3 Mixed precedence

`configuration(EnvTreeSource("APP_"), JsonTreeSource("local.json"), overrides={"db": {"port": 5433}})`

## 10. Backwards Compatibility

* `@configuration` is removed.
* `tree_config` argument in `init(...)` is removed.
* Provide `DeprecationWarning` for one cycle if legacy code paths are still present during migration.

## 11. Test Matrix

* Auto vs explicit mapping
* Flat vs tree collisions
* ENV normalization on/off
* Primitive and collection coercion
* Discriminator success/failure
* Interpolation on/off
* Deep-merge edge cases
* Value(...) precedence


